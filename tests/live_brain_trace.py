"""Live: watch the notch second by second while the real brain handles one --say utterance."""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
from PIL import ImageGrab, Image
ROOT = Path(__file__).resolve().parents[1]
say = sys.argv[1] if len(sys.argv) > 1 else "give me twenty minutes to concentrate"
tmp = Path(tempfile.mkdtemp()); (tmp / "Jarvis").mkdir()
(tmp / "Jarvis" / "settings.json").write_text(json.dumps({"onboarded": True, "speak_replies": "off", "wake_word": False}))
env = dict(os.environ, APPDATA=str(tmp), PYTHONIOENCODING="utf-8")
p = subprocess.Popen([sys.executable, str(ROOT / "run.py"), "--no-keys", "--no-voice", "--say", say], env=env, cwd=ROOT,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
frames = []
try:
    t0 = time.time()
    while time.time() - t0 < 16:
        time.sleep(1.5)
        im = ImageGrab.grab(); w, h = im.size
        frames.append(im.crop((w // 2 - 380, 0, w // 2 + 380, 120)))
finally:
    p.terminate()
    try:
        p.wait(5)
    except Exception:
        p.kill()
    subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"], capture_output=True)
log = p.stdout.read() or ""
print("LOG>>", "\n".join(l for l in log.splitlines() if "symlink" not in l.lower())[-1500:])
sheet = Image.new("RGB", (760 * 2, 120 * ((len(frames) + 1) // 2)))
for i, f in enumerate(frames):
    sheet.paste(f, ((i % 2) * 760, (i // 2) * 120))
sheet.save(ROOT / "shots" / "brain" / "trace.png")
print("frames:", len(frames))
