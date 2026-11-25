"""Live end-to-end test of the PACKAGED app: dist/Jarvis/Jarvis.exe + dist/Jarvis/jarvis-hook.exe."""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
from PIL import ImageGrab
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "dist" / "Jarvis"
tmp = Path(tempfile.mkdtemp()); (tmp / "Jarvis").mkdir()
(tmp / "Jarvis" / "settings.json").write_text(json.dumps({"onboarded": True, "speak_replies": "off", "wake_word": False,
                                                          "claude_quiet_when_focused": False, "claude_approval_timeout": 6}))
env = dict(os.environ, APPDATA=str(tmp), LOCALAPPDATA=str(tmp / "local"))
app = subprocess.Popen([str(D / "Jarvis.exe"), "--no-keys", "--no-voice"], env=env, cwd=D)
out = ROOT / "shots" / "frozen_e2e"; out.mkdir(parents=True, exist_ok=True)
base = {"session_id": "f1", "cwd": r"C:\proj\web-app"}


def hook(ev):
    t = time.time()
    r = subprocess.run([str(D / "hook" / "jarvis-hook.exe"), "--jarvis-hook"], input=json.dumps(ev), capture_output=True, text=True, env=env, timeout=60)
    return r, time.time() - t


def shot(name):
    im = ImageGrab.grab(); w, h = im.size
    im.crop((w // 2 - 520, 0, w // 2 + 520, 220)).save(out / f"{name}.png")


results = []
try:
    for _ in range(80):
        if (tmp / "Jarvis" / "bridge.json").exists(): break
        time.sleep(0.25)
    results.append(("packaged app started its Claude bridge", (tmp / "Jarvis" / "bridge.json").exists()))
    time.sleep(2.5)
    r, dt = hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "go"})
    print(f"hook call took {dt:.2f}s"); results.append(("hook exe exits 0 with no output", r.returncode == 0 and r.stdout == ""))
    r, dt2 = hook({**base, "hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": r"C:\proj\web-app\api.py"}})
    time.sleep(2.0); shot("working")
    print(f"second hook call took {dt2:.2f}s")
    r, _ = hook({**base, "hook_event_name": "Stop", "last_assistant_message": "Added the login page. The tests pass."})
    time.sleep(2.0); shot("done")
    results.append(("hook calls are fast enough not to slow Claude Code (<2 s each)", max(dt, dt2) < 2.0))
finally:
    app.terminate()
    try: app.wait(8)
    except Exception: app.kill()
# when Jarvis is NOT running the hook must stay silent and instant
t = time.time(); r, dt3 = hook({**base, "hook_event_name": "Stop"});
results.append(("hook is silent and quick when Jarvis is closed", r.returncode == 0 and r.stdout == "" and r.stderr == "" and dt3 < 2.0))
print(f"hook with Jarvis closed took {dt3:.2f}s")
log = tmp / "Jarvis" / "jarvis.log"
print("log file written:", log.exists(), "| size", log.stat().st_size if log.exists() else 0)
for n, ok in results: print("PASS" if ok else "FAIL", n)
sys.exit(0 if all(ok for _, ok in results) else 1)
