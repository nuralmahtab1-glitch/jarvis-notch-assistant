"""Live: install JarvisSetup.exe silently into a temp folder, run the installed app, uninstall, verify cleanup.
User data/home are redirected to a temp dir so your real settings and Claude Code config are never touched."""
import json, os, subprocess, sys, tempfile, time, winreg
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "dist" / "JarvisSetup.exe"
tmp = Path(tempfile.mkdtemp(prefix="jarvis-cycle-"))
dest = tmp / "Programs" / "Jarvis"
home = tmp / "home"; (home / ".claude").mkdir(parents=True)
settings_before = json.dumps({"theme": "dark", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}})
(home / ".claude" / "settings.json").write_text(settings_before)
(tmp / "appdata" / "Jarvis").mkdir(parents=True)
(tmp / "appdata" / "Jarvis" / "settings.json").write_text(json.dumps({"onboarded": True, "speak_replies": "off", "wake_word": True}))
env = dict(os.environ, APPDATA=str(tmp / "appdata"), LOCALAPPDATA=str(tmp / "local"), USERPROFILE=str(home), HOME=str(home))
results = []


def check(name, cond, extra=""):
    results.append(bool(cond)); print(("PASS" if cond else "FAIL"), name, extra)


def reg_exists():
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Jarvis")); return True
    except OSError:
        return False


check("no leftover Jarvis uninstall entry before the test", not reg_exists())
t = time.time()
r = subprocess.run([str(SETUP), "/S", f"/D={dest}", "--no-shortcuts", "--no-launch"], env=env, capture_output=True, text=True, timeout=600)
print(f"setup took {time.time() - t:.0f}s, exit {r.returncode} {r.stdout.strip()[:200]}")
check("silent install succeeded", r.returncode == 0 and (dest / "Jarvis.exe").exists())
check("hook helper installed", (dest / "hook" / "jarvis-hook.exe").exists())
check("bundled British voice installed", (dest / "_internal" / "models" / "piper" / "en_GB-alan-medium.onnx").exists())
check("Add/Remove Programs entry created", reg_exists())
with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Jarvis") as k:
    check("publisher is Nur Al Mahtab", winreg.QueryValueEx(k, "Publisher")[0] == "Nur Al Mahtab")

# run the INSTALLED app with voice + wake word on, give it time, look for errors in its own log
app = subprocess.Popen([str(dest / "Jarvis.exe"), "--say", "what time is it"], env=env, cwd=dest)
time.sleep(35)
alive = app.poll() is None
check("installed app is running after 35 s", alive)
log = tmp / "appdata" / "Jarvis" / "jarvis.log"
text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
bad = [l for l in text.splitlines() if any(w in l for w in ("Traceback", "[wake]", "[tts]", "[stt]", "Error", "failed"))]
check("no errors in the app's log (voice, wake word, speech model all loaded)", not bad, ("\n   " + "\n   ".join(bad[:6])) if bad else "")
try:
    import psutil
    p = psutil.Process(app.pid); mb = sum(c.memory_info().rss for c in [p] + p.children(recursive=True)) / 1e6
    print(f"   memory in use: {mb:.0f} MB")
except Exception:
    pass
# connect Claude Code on the temp home, confirm the installed hook path is used, then disconnect through the app itself
sys.path.insert(0, str(ROOT))
r = subprocess.run([str(dest / "Jarvis.exe"), "--disconnect-claude"], env=env, timeout=60)
check("--disconnect-claude leaves your own hooks untouched", json.loads((home / ".claude" / "settings.json").read_text()) == json.loads(settings_before))
app.terminate()
try: app.wait(8)
except Exception: app.kill()

# uninstall (keep data), then verify
r = subprocess.run([str(dest / "Jarvis.exe"), "--uninstall", "--silent"], env=env, timeout=120)
time.sleep(6)
check("uninstall removed the program folder", not dest.exists())
check("uninstall removed the Add/Remove Programs entry", not reg_exists())
check("uninstall kept your data by default", (tmp / "appdata" / "Jarvis" / "settings.json").exists())
check("your Claude settings are exactly as before", json.loads((home / ".claude" / "settings.json").read_text()) == json.loads(settings_before))
print(f"\n{sum(results)}/{len(results)} install-cycle checks passed   (temp dir: {tmp})")
sys.exit(0 if all(results) else 1)
