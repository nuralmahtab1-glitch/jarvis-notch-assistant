"""Which speech settings hear commands best on THIS PC? Uses the bundled British voice to speak typical commands, then makes
the audio harder (quiet microphone + background noise), and measures word error rate and time. Run manually."""
import io, re, sys, time, wave
import numpy as np
sys.path.insert(0, ".")
from app import paths
from app.tts.engine import PiperEngine

PHRASES = [
    "open youtube and chrome side by side",
    "open youtube and after that search for avengers",
    "set a timer for ten minutes",
    "turn the volume up to eighty",
    "open google chrome and spotify",
    "what is the weather in london",
    "remind me to call mum at six",
    "add milk to my to do list",
    "hey jarvis open notepad",
    "snap this window to the left",
    "play some jazz on spotify",
    "take a screenshot",
]
PROMPT = ("Jarvis, open YouTube and Chrome side by side. Open Spotify, Discord, Notepad, Google Chrome. Set a timer. "
          "Search for. Volume. Remind me to. Add to my to-do list. Snap this window to the left.")


def speak(pe, text, speed):
    w = wave.open(io.BytesIO(pe.synth_wav(text, speed)))
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    sr = w.getframerate()
    if sr != 16000:
        a = np.interp(np.linspace(0, len(a) - 1, int(len(a) * 16000 / sr)), np.arange(len(a)), a).astype(np.float32)
    return a


def degrade(a, peak, snr_db, rng):
    a = a / (np.abs(a).max() + 1e-9) * peak                       # quiet microphone
    noise = rng.normal(0, 1, a.size).astype(np.float32)
    p_sig = float(np.mean(a ** 2)); p_noise = p_sig / (10 ** (snr_db / 10))
    noise *= np.sqrt(p_noise / (np.mean(noise ** 2) + 1e-12))
    pad = np.zeros(int(0.4 * 16000), np.float32)
    return np.concatenate([pad, a + noise[:a.size], pad])


def norm_audio(a):
    pk = float(np.abs(a).max())
    return np.clip(a * (0.7 / pk), -1, 1) if 0.003 < pk < 0.5 else a


def words(t):
    return re.sub(r"[^a-z0-9 ]", "", t.lower().replace("-", " ")).split()


def wer(ref, hyp):
    r, h = words(ref), words(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)] / max(1, len(r))


def main():
    from faster_whisper import WhisperModel
    pe = PiperEngine(); rng = np.random.default_rng(7)
    clips = []
    for text in PHRASES:
        for speed, peak, snr in ((1.0, 0.25, 20), (1.15, 0.06, 12)):       # a normal mic, and a quiet noisy one
            clips.append((text, degrade(speak(pe, text, speed), peak, snr, rng)))
    configs = [
        ("tiny.en  greedy, no prompt (old default)", "tiny.en", dict(beam_size=1), False, False),
        ("tiny.en  + prompt + loudness fix", "tiny.en", dict(beam_size=1), True, True),
        ("base.en  greedy, no prompt", "base.en", dict(beam_size=1), False, False),
        ("base.en  + prompt + loudness fix", "base.en", dict(beam_size=1), True, True),
        ("base.en  + prompt + loudness fix + beam 3", "base.en", dict(beam_size=3), True, True),
        ("small.en + prompt + loudness fix", "small.en", dict(beam_size=1), True, True),
    ]
    models = {}
    print(f"{len(clips)} clips; lower error is better\n")
    for label, size, kw, use_prompt, fix in configs:
        if size not in models:
            models[size] = WhisperModel(size, device="cpu", compute_type="int8", download_root=str(paths.user_models() / "whisper"), cpu_threads=4)
            list(models[size].transcribe(np.zeros(8000, np.float32), language="en", beam_size=1)[0])
        m = models[size]; errs, t0, bad = [], time.time(), []
        for ref, a in clips:
            a2 = norm_audio(a) if fix else a
            segs, _ = m.transcribe(a2, language="en", vad_filter=True, vad_parameters={"min_silence_duration_ms": 250},
                                   condition_on_previous_text=False, initial_prompt=PROMPT if use_prompt else None, **kw)
            hyp = " ".join(s.text.strip() for s in segs)
            e = wer(ref, hyp); errs.append(e)
            if e > 0.3: bad.append((ref, hyp))
        dt = (time.time() - t0) / len(clips)
        print(f"{label:46s} word error {100 * np.mean(errs):5.1f}%   perfect {sum(e == 0 for e in errs):2d}/{len(clips)}   {dt:4.2f}s per command", flush=True)
        for ref, hyp in bad[:2]:
            print(f"      said '{ref}'  ->  heard '{hyp}'")


if __name__ == "__main__":
    main()
