"""Live end-to-end check on the real screen. Run manually: python tests/live_e2e.py"""
import json, os, subprocess, sys, tempfile, time, threading
from pathlib import Path
from PIL import ImageGrab
ROOT = Path(__file__).resolve().parents[1]
tmp = Path(tempfile.mkdtemp()); (tmp / "Jarvis").mkdir()
(tmp / "Jarvis" / "settings.json").write_text(json.dumps({"onboarded": True, "speak_replies": "off", "claude_approval_timeout": 12,
                                                          "claude_quiet_when_focused": False, "wake_word": False}))
env = dict(os.environ, APPDATA=str(tmp), PYTHONIOENCODING="utf-8")
app = subprocess.Popen([sys.executable, str(ROOT / "run.py"), "--no-keys", "--no-voice"], env=env, cwd=ROOT,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
out = ROOT / "shots" / "e2e"; out.mkdir(parents=True, exist_ok=True)


def hook(ev):
    return subprocess.run([sys.executable, str(ROOT / "app/claude_bridge/hook.py"), "--jarvis-hook"], input=json.dumps(ev),
                          capture_output=True, text=True, env=env, timeout=60)


def shot(name):
    im = ImageGrab.grab(); w, h = im.size
    im.crop((w // 2 - 520, 0, w // 2 + 520, 220)).save(out / f"{name}.png"); print("shot", name)


base = {"session_id": "e2e", "cwd": r"C:\proj\plant-design"}
try:
    for _ in range(60):
        if (tmp / "Jarvis" / "bridge.json").exists():
            break
        time.sleep(0.25)
    time.sleep(2); shot("0_idle")
    hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "fix it"})
    hook({**base, "hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": r"C:\proj\plant-design\server.ts"}})
    time.sleep(1.8); shot("1_working")
    res = {}
    t = threading.Thread(target=lambda: res.update(r=hook({**base, "hook_event_name": "PermissionRequest", "tool_name": "Bash", "tool_input": {"command": "npm test"}})))
    print("permission requested at", round(time.time(), 2), flush=True)
    t.start(); time.sleep(2.2); shot("2_needs_you")
    t.join(30)
    print("permission hook stdout after timeout (expect empty = handed back):", repr(res["r"].stdout))
    hook({**base, "hook_event_name": "Stop", "last_assistant_message": "I fixed the bug in server.ts. All tests pass."})
    time.sleep(2.0); shot("3_done")
finally:
    app.terminate()
    try:
        app.wait(5)
    except Exception:
        app.kill()
print("APPLOG>>", app.stdout.read() or "")
