"""Connect / disconnect Claude Code hooks safely. Made by Nur Al Mahtab.

- Always backs up settings.json first, merges (never overwrites), and tags our entries so
  disconnect removes ONLY entries this app added.
- preview() returns a unified diff so the user can see exactly what will change.
"""
from __future__ import annotations
import difflib, json, shutil, sys, time
from pathlib import Path

MARKER = "jarvis-hook"          # appears in the command string of every entry we add
HOOK_SCRIPT = Path(__file__).resolve().parent / "hook.py"
# (event, needs_reply). Reply events block (up to timeout); the rest run async and never block.
EVENTS = [("SessionStart", False), ("UserPromptSubmit", False), ("PreToolUse", False),
          ("PostToolUse", False), ("PostToolUseFailure", False), ("PermissionRequest", True),
          ("Notification", False), ("Stop", False), ("StopFailure", False), ("SubagentStart", False),
          ("SubagentStop", False), ("PreCompact", False), ("SessionEnd", False)]


def default_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _command(python: str | None = None) -> str:
    """The command Claude Code runs for each hook. Installed app: the small jarvis-hook.exe in the hook folder next to Jarvis.exe."""
    from app import paths
    if paths.FROZEN and python is None:
        return f'"{paths.install_dir() / "hook" / "jarvis-hook.exe"}" --{MARKER}'
    py = python or sys.executable
    return f'"{py}" "{HOOK_SCRIPT}" --{MARKER}'


def _entry(needs_reply: bool, python: str | None) -> dict:
    h = {"type": "command", "command": _command(python)}
    if needs_reply:
        h["timeout"] = 40
    else:
        h["async"] = True
        h["timeout"] = 5
    return {"hooks": [h]}


def _is_ours(group: dict) -> bool:
    return any(MARKER in str(h.get("command", "")) for h in group.get("hooks", []))


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    txt = path.read_text(encoding="utf-8").strip()
    return json.loads(txt) if txt else {}


def merged(settings: dict, python: str | None = None) -> dict:
    out = json.loads(json.dumps(settings))
    hooks = out.setdefault("hooks", {})
    for event, needs_reply in EVENTS:
        groups = [g for g in hooks.get(event, []) if not _is_ours(g)]   # idempotent: drop our old entry
        groups.append(_entry(needs_reply, python))
        hooks[event] = groups
    return out


def stripped(settings: dict) -> dict:
    out = json.loads(json.dumps(settings))
    hooks = out.get("hooks", {})
    for event in list(hooks):
        hooks[event] = [g for g in hooks[event] if not _is_ours(g)]
        if not hooks[event]:
            del hooks[event]
    if not hooks:
        out.pop("hooks", None)
    return out


def _dump(d: dict) -> str:
    return json.dumps(d, indent=2, ensure_ascii=False) + "\n"


def preview(path: Path | None = None, python: str | None = None, disconnect: bool = False) -> str:
    path = path or default_settings_path()
    cur = _load(path)
    new = stripped(cur) if disconnect else merged(cur, python)
    return "".join(difflib.unified_diff(_dump(cur).splitlines(True), _dump(new).splitlines(True),
                                        "settings.json (current)", "settings.json (after)"))


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    dest = path.with_name(f"{path.name}.jarvis-backup-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, dest)
    return dest


def _write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(_dump(data), encoding="utf-8")
    tmp.replace(path)


def connect(path: Path | None = None, python: str | None = None) -> Path | None:
    path = path or default_settings_path()
    cur = _load(path)            # raises on invalid JSON: we refuse to touch a file we cannot parse
    b = backup(path)
    _write(path, merged(cur, python))
    return b


def disconnect(path: Path | None = None) -> Path | None:
    path = path or default_settings_path()
    if not path.exists() or not is_connected(path):
        return None                      # nothing of ours in there: do not rewrite or reformat the user's file
    cur = _load(path)
    b = backup(path)
    _write(path, stripped(cur))
    return b


def is_connected(path: Path | None = None) -> bool:
    try:
        hooks = _load(path or default_settings_path()).get("hooks", {})
    except Exception:
        return False
    return any(_is_ours(g) for gs in hooks.values() for g in gs)
