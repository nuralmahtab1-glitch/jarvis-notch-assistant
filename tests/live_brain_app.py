"""Live: run the real app with the real model, send one utterance via --say, screenshot the notch."""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
from PIL import ImageGrab
ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "shots" / "brain"; out.mkdir(parents=True, exist_ok=True)


def run(say, name, wait=14):
    tmp = Path(tempfile.mkdtemp()); (tmp / "Jarvis").mkdir()
    (tmp / "Jarvis" / "settings.json").write_text(json.dumps({"onboarded": True, "speak_replies": "off", "wake_word": False}))
    env = dict(os.environ, APPDATA=str(tmp), PYTHONIOENCODING="utf-8")
    p = subprocess.Popen([sys.executable, str(ROOT / "run.py"), "--no-keys", "--no-voice", "--say", say], env=env, cwd=ROOT,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        t0 = time.time()
        time.sleep(wait / 2)
        im = ImageGrab.grab(); w, h = im.size
        im.crop((w // 2 - 520, 0, w // 2 + 520, 220)).save(out / f"{name}_thinking.png")
        time.sleep(wait / 2)
        im = ImageGrab.grab(); im.crop((w // 2 - 520, 0, w // 2 + 520, 220)).save(out / f"{name}.png")
        print("shot", name, "after", round(time.time() - t0, 1), "s")
    finally:
        p.terminate()
        try:
            p.wait(5)
        except Exception:
            p.kill()
        log = [l for l in (p.stdout.read() or "").splitlines() if "[brain" in l or "Traceback" in l or "Error" in l]
        print("log:", log[:5])
        subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"], capture_output=True)


run("how many legs does a spider have", "answer")
run("give me twenty minutes to concentrate", "focus")
