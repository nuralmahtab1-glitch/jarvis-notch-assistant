"""Claude Code session tracker + local bridge server. Made by Nur Al Mahtab."""
from __future__ import annotations
import hmac, json, os, re, secrets, threading, time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

TERMINAL_PROCS = {"windowsterminal.exe", "wt.exe", "code.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
                  "conhost.exe", "claude.exe", "alacritty.exe", "wezterm-gui.exe", "cursor.exe"}
RISKY_BASH = re.compile(
    r"\brm\s+-[a-z]*[rf]|\brmdir\b|\bdel\s+/|remove-item|\bformat\b|git\s+push\s+.*(--force|-f\b)|"
    r"git\s+reset\s+--hard|git\s+clean|\bshutdown\b|curl[^|]*\|\s*(ba)?sh|iwr[^|]*\|\s*iex|"
    r"\b(npm|pnpm|yarn|pip|pip3|winget|choco|cargo)\s+(install|add|i)\b|\bchmod\b|\bsudo\b|drop\s+table",
    re.I)


def config_path() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "Jarvis" / "bridge.json"


def describe_action(tool: str, tin: dict, hide_details: bool = False) -> str:
    base = lambda p: os.path.basename(str(p).replace("\\", "/")) if p else "a file"
    t = tool or ""
    if t == "Read": return f"Reading {base(tin.get('file_path'))}" if not hide_details else "Reading a file"
    if t in ("Edit", "MultiEdit", "NotebookEdit"): return f"Editing {base(tin.get('file_path') or tin.get('notebook_path'))}" if not hide_details else "Editing a file"
    if t == "Write": return f"Writing {base(tin.get('file_path'))}" if not hide_details else "Writing a file"
    if t == "Bash":
        cmd = str(tin.get("command", "")).strip()
        return "Running a command" if hide_details or not cmd else "Running " + (cmd[:44] + ("..." if len(cmd) > 44 else ""))
    if t in ("Grep", "Glob", "LS"): return "Searching the code"
    if t in ("WebFetch", "WebSearch"): return "Fetching a web page"
    if t in ("Task", "Agent"): return "Running a subagent"
    if t in ("TodoWrite", "TaskCreate", "TaskUpdate"): return "Planning the work"
    if t.startswith("mcp__"): return "Using " + t.split("__")[1].replace("_", " ")
    return f"Using {t}" if t else "Working"


def is_risky(tool: str, tin: dict, cwd: str) -> bool:
    if tool == "Bash":
        return bool(RISKY_BASH.search(str(tin.get("command", ""))))
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        p = str(tin.get("file_path") or tin.get("notebook_path") or "")
        try:
            return bool(p) and bool(cwd) and not os.path.abspath(p).lower().startswith(os.path.abspath(cwd).lower())
        except Exception:
            return True
    return False


@dataclass
class Approval:
    id: str
    session_id: str
    tool: str
    description: str
    risky: bool
    event: threading.Event = field(default_factory=threading.Event)
    result: str | None = None  # "allow" | "deny" | None


@dataclass
class Session:
    id: str
    cwd: str = ""
    project: str = ""
    state: str = "idle"          # idle | working | needs_you | done | error
    started: float = 0.0
    updated: float = field(default_factory=time.time)
    last_action: str = ""
    summary: str = ""
    duration: float = 0.0
    permission_mode: str = ""
    source: str = "code"         # "code" (terminal / VS Code hooks) or "web" (browser extension)


WEB_STALE_SECONDS = 90           # a web tab that stops reporting is treated as closed


def fmt_duration(sec: float) -> str:
    sec = int(sec)
    m, s = divmod(sec, 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def first_sentence(text: str, limit: int = 140) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    t = re.sub(r"[`*#>]+", "", t)
    m = re.match(r"(.+?[.!?])(\s|$)", t)
    s = m.group(1) if m else t
    return s if len(s) <= limit else s[:limit - 1].rstrip() + "..."


class Tracker:
    def __init__(self, on_update: Callable[[], None] | None = None, approval_timeout: float = 30.0,
                 hide_details: bool = False, quiet_when_focused: bool = True,
                 foreground_proc: Callable[[], str] | None = None):
        self.sessions: dict[str, Session] = {}
        self.pending: dict[str, Approval] = {}
        self.history: list[dict] = []
        self.on_update = on_update or (lambda: None)
        self.approval_timeout = approval_timeout
        self.hide_details = hide_details
        self.quiet_when_focused = quiet_when_focused
        self.foreground_proc = foreground_proc or (lambda: "")
        self._lock = threading.RLock()

    # ---------------- events ----------------
    def handle(self, ev: dict) -> dict | None:
        name = ev.get("hook_event_name", "")
        sid = ev.get("session_id", "unknown")
        perm = None
        with self._lock:
            s = self.sessions.setdefault(sid, Session(id=sid))
            cwd = ev.get("cwd") or s.cwd
            if cwd:
                s.cwd, s.project = cwd, os.path.basename(cwd.rstrip("\\/")) or cwd
            s.permission_mode = ev.get("permission_mode", s.permission_mode)
            s.updated = time.time()
            tin = ev.get("tool_input") or {}
            tool = ev.get("tool_name", "")

            if name == "SessionStart":
                s.state = "idle"
            elif name == "UserPromptSubmit":
                s.state, s.started, s.last_action, s.summary = "working", time.time(), "Thinking", ""
            elif name in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
                if s.state in ("idle", "done", "needs_you", "error"):
                    s.state = "working"
                    s.started = s.started or time.time()
                if name == "PreToolUse":
                    s.last_action = describe_action(tool, tin, self.hide_details)
            elif name in ("SubagentStart", "SubagentStop"):
                s.last_action = "Running a subagent" if name == "SubagentStart" else s.last_action
            elif name == "PreCompact":
                s.last_action = "Compacting memory"
            elif name == "Notification":
                if ev.get("notification_type") == "permission_prompt":
                    s.state, s.last_action = "needs_you", ev.get("message", "Needs your permission")
            elif name == "Stop":
                s.duration = time.time() - s.started if s.started else 0.0
                s.state = "done"
                s.summary = first_sentence(ev.get("last_assistant_message", ""))
                self.history.insert(0, {"project": s.project, "duration": s.duration, "result": "done",
                                        "summary": s.summary, "at": time.time()})
                del self.history[20:]
            elif name == "StopFailure":
                s.state, s.last_action = "error", ev.get("error", "Claude hit an error")
                self.history.insert(0, {"project": s.project, "duration": 0, "result": "error",
                                        "summary": s.last_action, "at": time.time()})
            elif name == "SessionEnd":
                self.sessions.pop(sid, None)
            elif name == "PermissionRequest":
                perm = (s, ev, tool, tin)
        if perm:                      # wait for the user OUTSIDE the lock so resolve() can get in
            return self._permission(*perm)
        self.on_update()
        return None

    # ---------------- approvals ----------------
    def _permission(self, s: Session, ev: dict, tool: str, tin: dict) -> dict | None:
        if self.quiet_when_focused and self.foreground_proc() in TERMINAL_PROCS:
            return None  # you are already looking at the prompt
        risky = is_risky(tool, tin, s.cwd)
        ap = Approval(id=secrets.token_hex(4), session_id=s.id, tool=tool,
                      description=describe_action(tool, tin, self.hide_details).replace("Running ", "Run: ", 1)
                      if tool == "Bash" else describe_action(tool, tin, self.hide_details), risky=risky)
        self.pending[ap.id] = ap
        s.state, s.last_action = "needs_you", ap.description
        self.on_update()
        ap.event.wait(self.approval_timeout)
        with self._lock:
            self.pending.pop(ap.id, None)
            if s.state == "needs_you":
                s.state = "working"
        self.on_update()
        if ap.result in ("allow", "deny"):
            dec = {"behavior": ap.result}
            if ap.result == "deny":
                dec["message"] = "Denied from Jarvis"
            return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": dec}}
        return None  # timeout: hand back to Claude Code's own prompt. Never auto-approve.

    def resolve(self, result: str, approval_id: str | None = None, via_voice: bool = False) -> bool:
        with self._lock:
            ap = self.pending.get(approval_id) if approval_id else next(iter(self.pending.values()), None)
            if not ap:
                return False
            if via_voice and ap.risky and result == "allow":
                return False  # risky actions need a tap, never a voice yes
            ap.result = result
            ap.event.set()
            return True

    # ---------------- views ----------------
    def handle_web(self, ev: dict) -> None:
        """An event from the browser extension: {state, tab, action, title}. Never contains conversation text."""
        sid = "web:" + ev["tab"]
        with self._lock:
            if ev["state"] == "unavailable":              # the page does not look like Claude Code: show nothing, not a guess
                self.sessions.pop(sid, None)
            else:
                s = self.sessions.setdefault(sid, Session(id=sid, source="web", project="Claude on the web"))
                prev, now = s.state, time.time()
                s.updated, s.source = now, "web"
                if ev["state"] == "working":
                    if prev != "working":
                        s.started = now
                    s.state, s.last_action = "working", ev["action"] or "Working"
                elif ev["state"] == "needs_you":
                    s.state, s.last_action = "needs_you", ev["action"] or "Waiting for your OK in the browser"
                elif ev["state"] == "done":
                    if prev == "working":                 # only a real working -> done transition counts as finishing
                        s.duration = now - s.started if s.started else 0.0
                        s.state, s.summary = "done", ""
                        self.history.insert(0, {"project": s.project, "duration": s.duration, "result": "done", "summary": "", "at": now})
                        del self.history[20:]
                else:                                      # idle
                    if prev in ("working", "needs_you"):
                        s.state = "idle"
                    elif prev == "done":
                        pass                               # keep showing "finished" until you dismiss it
                    else:
                        s.state = "idle"
        self.on_update()

    def _drop_stale_web(self) -> None:
        cutoff = time.time() - WEB_STALE_SECONDS
        for sid in [k for k, v in self.sessions.items() if v.source == "web" and v.updated < cutoff]:
            del self.sessions[sid]

    def urgent(self) -> Session | None:
        order = {"needs_you": 0, "error": 1, "working": 2, "done": 3, "idle": 4}
        with self._lock:
            self._drop_stale_web()
            live = sorted(self.sessions.values(), key=lambda x: (order.get(x.state, 9), -x.updated))
            return live[0] if live and live[0].state != "idle" else None

    def status_sentence(self) -> str:
        s = self.urgent()
        if not s:
            return "Claude is not running anything right now."
        el = fmt_duration(time.time() - s.started) if s.started else ""
        where = "on the web" if s.source == "web" else f"in {s.project}"
        if s.state == "working":
            return f"Claude is {s.last_action[:1].lower() + s.last_action[1:]} {where}, {el} in."
        if s.state == "needs_you":
            return f"Claude {where} needs your permission" + (", in the browser." if s.source == "web" else ".")
        if s.state == "done":
            return f"Claude finished {where} after {fmt_duration(s.duration)}. {s.summary}".strip()
        return f"Claude hit an error {where}."


class Bridge:
    """127.0.0.1-only HTTP server that receives hook events from jarvis-hook."""

    def __init__(self, tracker: Tracker, port: int = 0):
        self.tracker = tracker
        self.token = secrets.token_urlsafe(24)
        tracker_ref, token = tracker, self.token

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def _deny(self, code=403):
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                if self.path == "/health":
                    self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
                else:
                    self._deny(404)

            def do_POST(self):
                n = min(int(self.headers.get("Content-Length", 0) or 0), 1_000_000)
                raw = self.rfile.read(n) if n else b""          # always drain the body first
                if self.client_address[0] != "127.0.0.1":
                    return self._deny()
                if not hmac.compare_digest(self.headers.get("X-Jarvis-Token", ""), token):
                    return self._deny(401)
                if self.path != "/hook":
                    return self._deny(404)
                try:
                    ev = json.loads(raw or b"{}")
                except ValueError:
                    return self._deny(400)
                out = tracker_ref.handle(ev)
                body = json.dumps(out).encode() if out else b""
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), H)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self._t = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self):
        p = config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"port": self.port, "token": self.token, "pid": os.getpid()}), encoding="utf-8")
        self._t.start()

    def stop(self):
        self.httpd.shutdown()
        try:
            config_path().unlink()
        except OSError:
            pass
