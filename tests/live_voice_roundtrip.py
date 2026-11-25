"""Live check: Piper speaks -> WAV -> Whisper transcribes. Run manually."""
import sys, time, wave, io
import numpy as np
sys.path.insert(0, ".")
from app.tts.engine import PiperEngine
from app.stt.whisper_stt import Transcriber
e = PiperEngine()
print("piper available:", e.available())
t0 = time.time(); wav = e.synth_wav("Hey Sam, I'm running fifteen minutes late. Save me a seat.")
print("synth seconds:", round(time.time() - t0, 2))
with wave.open(io.BytesIO(wav)) as w:
    sr = w.getframerate(); pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
print("audio seconds:", round(len(pcm) / sr, 2), "sr", sr)
x = pcm.astype("float32") / 32768.0
if sr != 16000:
    idx = np.linspace(0, len(x) - 1, int(len(x) * 16000 / sr)); x = np.interp(idx, np.arange(len(x)), x).astype("float32")
tr = Transcriber("base.en")
t0 = time.time(); tr.load(); print("model load seconds:", round(time.time() - t0, 1))
t0 = time.time(); text = tr.transcribe(x); print("transcribe seconds:", round(time.time() - t0, 2))
print("HEARD:", text)
