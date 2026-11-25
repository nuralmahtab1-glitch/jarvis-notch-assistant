import json, subprocess, sys, threading, time, os
from pathlib import Path
import pytest
from app.claude_bridge import installer
from app.claude_bridge.tracker import Tracker, Bridge, describe_action, is_risky, config_path

HOOK = Path(installer.HOOK_SCRIPT)


# ---------------- installer (always on a temp file, never the real settings) ----------------
def test_connect_merges_and_backs_up(tmp_path):
    p = tmp_path / "settings.json"
    existing = {"theme": "dark", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
    p.write_text(json.dumps(existing))
    b = installer.connect(p, python="python")
    assert b and json.loads(b.read_text()) == existing           # backup is the original
    cur = json.loads(p.read_text())
    assert cur["theme"] == "dark"
    stop = cur["hooks"]["Stop"]
    assert any("echo mine" in h["command"] for g in stop for h in g["hooks"])   # user's hook kept
    assert installer.is_connected(p)
    assert "PermissionRequest" in cur["hooks"]


def test_connect_is_idempotent(tmp_path):
    p = tmp_path / "s.json"; p.write_text("{}")
    installer.connect(p, python="python"); first = p.read_text()
    installer.connect(p, python="python")
    assert p.read_text() == first


def test_disconnect_removes_only_ours(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}))
    installer.connect(p, python="python")
    installer.disconnect(p)
    cur = json.loads(p.read_text())
    assert cur == {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
    assert not installer.is_connected(p)


def test_disconnect_when_nothing_else(tmp_path):
    p = tmp_path / "s.json"; p.write_text("{}")
    installer.connect(p, python="python"); installer.disconnect(p)
    assert json.loads(p.read_text()) == {}


def test_refuses_invalid_json(tmp_path):
    p = tmp_path / "s.json"; p.write_text("{not json")
    with pytest.raises(Exception):
        installer.connect(p)
    assert p.read_text() == "{not json"   # untouched


def test_preview_diff_mentions_hooks(tmp_path):
    p = tmp_path / "s.json"; p.write_text("{}")
    assert "PermissionRequest" in installer.preview(p, python="python")


def test_decision_events_block_others_async(tmp_path):
    p = tmp_path / "s.json"; p.write_text("{}"); installer.connect(p, python="python")
    hooks = json.loads(p.read_text())["hooks"]
    assert hooks["PermissionRequest"][0]["hooks"][0].get("async") is None
    assert hooks["Stop"][0]["hooks"][0]["async"] is True


# ---------------- tracker ----------------
def ev(name, sid="s1", **kw):
    return {"hook_event_name": name, "session_id": sid, "cwd": r"C:\proj\plant-design", **kw}


def test_working_then_done_with_summary():
    t = Tracker()
    t.handle(ev("UserPromptSubmit"))
    t.handle(ev("PreToolUse", tool_name="Edit", tool_input={"file_path": r"C:\proj\plant-design\server.ts"}))
    s = t.urgent()
    assert s.state == "working" and s.last_action == "Editing server.ts" and s.project == "plant-design"
    t.handle(ev("Stop", last_assistant_message="I fixed the bug. Tests pass now."))
    s = t.urgent()
    assert s.state == "done" and s.summary == "I fixed the bug."
    assert t.history[0]["result"] == "done"


def test_privacy_hides_details():
    assert describe_action("Bash", {"command": "rm -rf secret"}, hide_details=True) == "Running a command"
    assert describe_action("Read", {"file_path": r"C:\x\y\z.py"}, hide_details=True) == "Reading a file"


def test_risky_detection():
    assert is_risky("Bash", {"command": "rm -rf node_modules"}, r"C:\p")
    assert is_risky("Bash", {"command": "git push --force origin main"}, r"C:\p")
    assert is_risky("Bash", {"command": "npm install left-pad"}, r"C:\p")
    assert not is_risky("Bash", {"command": "ls -la"}, r"C:\p")
    assert is_risky("Write", {"file_path": r"C:\Windows\x.txt"}, r"C:\p")
    assert not is_risky("Write", {"file_path": r"C:\p\a.txt"}, r"C:\p")


def test_permission_allow_roundtrip():
    t = Tracker(approval_timeout=5)
    out = {}
    th = threading.Thread(target=lambda: out.update(r=t.handle(ev("PermissionRequest", tool_name="Bash", tool_input={"command": "ls"}))))
    th.start(); time.sleep(0.2)
    assert t.urgent().state == "needs_you" and len(t.pending) == 1
    assert t.resolve("allow")
    th.join(2)
    assert out["r"]["hookSpecificOutput"]["decision"]["behavior"] == "allow"


def test_permission_timeout_hands_back_never_auto_approves():
    t = Tracker(approval_timeout=0.3)
    assert t.handle(ev("PermissionRequest", tool_name="Bash", tool_input={"command": "ls"})) is None


def test_voice_cannot_approve_risky():
    t = Tracker(approval_timeout=2)
    th = threading.Thread(target=lambda: t.handle(ev("PermissionRequest", tool_name="Bash", tool_input={"command": "rm -rf build"})))
    th.start(); time.sleep(0.2)
    assert t.resolve("allow", via_voice=True) is False       # needs a tap
    assert t.resolve("deny", via_voice=True) is True         # denying by voice is always fine
    th.join(2)


def test_quiet_when_terminal_in_front():
    t = Tracker(approval_timeout=5, foreground_proc=lambda: "windowsterminal.exe")
    t0 = time.time()
    assert t.handle(ev("PermissionRequest", tool_name="Bash", tool_input={"command": "ls"})) is None
    assert time.time() - t0 < 0.5


def test_session_end_removes():
    t = Tracker(); t.handle(ev("UserPromptSubmit")); t.handle(ev("SessionEnd"))
    assert t.urgent() is None


def test_multi_session_most_urgent_first():
    t = Tracker()
    t.handle(ev("UserPromptSubmit", sid="a")); t.handle(ev("UserPromptSubmit", sid="b"))
    t.handle(ev("Notification", sid="b", notification_type="permission_prompt", message="Needs permission"))
    assert t.urgent().id == "b"


# ---------------- bridge + the real hook helper process ----------------
@pytest.fixture
def bridge(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    t = Tracker(approval_timeout=5)
    b = Bridge(t); b.start()
    yield t, b
    b.stop()


def run_hook(payload: dict, env_appdata):
    env = dict(os.environ, APPDATA=str(env_appdata))
    return subprocess.run([sys.executable, str(HOOK), "--jarvis-hook"], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=60)


def test_hook_helper_end_to_end(bridge, tmp_path):
    t, b = bridge
    r = run_hook(ev("UserPromptSubmit"), tmp_path)
    assert r.returncode == 0 and r.stdout == ""
    assert t.urgent().state == "working"


def test_hook_helper_permission_decision_over_http(bridge, tmp_path):
    t, b = bridge
    def approve_soon():
        for _ in range(100):
            if t.pending:
                t.resolve("deny"); return
            time.sleep(0.05)
    threading.Thread(target=approve_soon, daemon=True).start()
    r = run_hook(ev("PermissionRequest", tool_name="Bash", tool_input={"command": "ls"}), tmp_path)
    out = json.loads(r.stdout)
    assert out["hookSpecificOutput"]["decision"]["behavior"] == "deny"
    assert out["hookSpecificOutput"]["hookEventName"] == "PermissionRequest"


def test_hook_helper_silent_and_fast_when_jarvis_not_running(tmp_path):
    t0 = time.time()
    r = run_hook(ev("Stop"), tmp_path)          # no bridge.json at all
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    assert time.time() - t0 < 1.5


def test_bridge_rejects_bad_token(bridge):
    import http.client
    t, b = bridge
    c = http.client.HTTPConnection("127.0.0.1", b.port, timeout=3)
    c.request("POST", "/hook", body=b"{}", headers={"X-Jarvis-Token": "wrong"})
    assert c.getresponse().status == 401
    c = http.client.HTTPConnection("127.0.0.1", b.port, timeout=3)
    c.request("POST", "/hook", body=b"{}")
    assert c.getresponse().status == 401


def test_hook_ignores_a_stale_connection_file_instantly(tmp_path):
    """If Jarvis was killed, bridge.json is left behind. The hook must not wait on a dead (or reused) port."""
    import socket
    proc = subprocess.Popen([sys.executable, "-c", "pass"]); proc.wait()          # a process id that is certainly dead
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)               # a port that WOULD accept and never answer
    (tmp_path / "Jarvis").mkdir()
    (tmp_path / "Jarvis" / "bridge.json").write_text(json.dumps({"port": srv.getsockname()[1], "token": "t", "pid": proc.pid}))
    t0 = time.time()
    r = run_hook(ev("PermissionRequest", tool_name="Bash", tool_input={"command": "ls"}), tmp_path)
    srv.close()
    assert r.returncode == 0 and r.stdout == "" and time.time() - t0 < 3.0         # would have been 45 s without the pid check


def test_hook_still_works_when_the_pid_is_alive(bridge, tmp_path):
    t, b = bridge
    cfg = json.loads(config_path().read_text())
    assert cfg["pid"] == os.getpid()
    r = run_hook(ev("UserPromptSubmit"), tmp_path)
    assert r.returncode == 0 and t.urgent().state == "working"


def test_disconnect_does_not_touch_a_file_that_has_no_jarvis_hooks(tmp_path):
    p = tmp_path / "settings.json"
    original = '{\n   "theme":   "dark",\n\t"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}\n}'
    p.write_text(original)
    assert installer.disconnect(p) is None
    assert p.read_text() == original                                  # byte-for-byte, odd formatting and all
    assert list(tmp_path.glob("*.jarvis-backup-*")) == []
