import time
import numpy as np
import pytest
from app.wake.listener import Endpointer, WakeDetector, FRAME


def test_silence_does_not_trigger():
    det = WakeDetector()
    assert not any(det.feed(np.zeros(FRAME, dtype=np.int16)) for _ in range(40))


def test_noise_does_not_trigger():
    det = WakeDetector()
    rng = np.random.default_rng(0)
    assert not any(det.feed((rng.normal(0, 800, FRAME)).astype(np.int16)) for _ in range(60))


def _speech(text):
    """Synthesize speech with the local Piper voice, as 16 kHz int16."""
    import io, wave
    from app.tts.engine import PiperEngine
    e = PiperEngine()
    if not e.available():
        pytest.skip("piper voice not downloaded")
    with wave.open(io.BytesIO(e.synth_wav(text))) as w:
        sr = w.getframerate(); x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype("float32")
    idx = np.linspace(0, len(x) - 1, int(len(x) * 16000 / sr))
    return np.interp(idx, np.arange(len(x)), x).astype(np.int16)


def test_hey_jarvis_phrase_is_detected_and_other_speech_is_not():
    det = WakeDetector(threshold=0.4)
    other = _speech("The weather is lovely today and I would like a cup of tea.")
    pad = np.zeros(16000, dtype=np.int16)
    hit_other = False
    for i in range(0, len(other) - FRAME, FRAME):
        hit_other |= det.feed(other[i:i + FRAME])
    assert not hit_other
    hey = np.concatenate([pad, _speech("Hey Jarvis."), pad])
    hits = [det.feed(hey[i:i + FRAME]) for i in range(0, len(hey) - FRAME, FRAME)]
    assert any(hits), "Piper 'Hey Jarvis' should trigger the wake word"


def test_endpointer_detects_end_of_speech():
    sr = 16000
    buf = {"a": np.zeros(0, dtype="float32")}
    ended = []
    ep = Endpointer(lambda: buf["a"], lambda spoke: ended.append(spoke), silence=0.5, no_speech_timeout=3)
    ep.start()
    t = np.linspace(0, 1, sr)
    buf["a"] = (0.2 * np.sin(2 * np.pi * 220 * t)).astype("float32")      # 1 s of "speech"
    time.sleep(0.4)
    buf["a"] = np.concatenate([buf["a"], np.zeros(sr, dtype="float32")])   # then silence
    time.sleep(1.2)
    assert ended == [True]


def test_endpointer_gives_up_when_nobody_speaks():
    ended = []
    ep = Endpointer(lambda: np.zeros(16000, dtype="float32"), lambda s: ended.append(s), no_speech_timeout=0.4)
    ep.start(); time.sleep(0.9)
    assert ended == [False]
