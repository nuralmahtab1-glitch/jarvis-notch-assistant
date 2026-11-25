"""Always-on wake word ("Hey Jarvis") using openWakeWord, fully local. Made by Nur Al Mahtab.

Audio frames are scored and discarded immediately; nothing is stored or transcribed.
"""
from __future__ import annotations
import threading, time
from typing import Callable
import numpy as np

FRAME = 1280  # 80 ms at 16 kHz


class WakeDetector:
    """Pure detector (no audio device): feed int16 frames, get True when the phrase is heard."""

    def __init__(self, model: str = "hey_jarvis", threshold: float = 0.5, cooldown: float = 3.0):
        from openwakeword.model import Model
        self.name = model
        self.m = Model(wakeword_models=[model], inference_framework="onnx")
        self.threshold, self.cooldown = threshold, cooldown
        self._last = 0.0

    def feed(self, frame: np.ndarray) -> bool:
        score = float(self.m.predict(frame).get(self.name, 0.0))
        now = time.monotonic()
        if score >= self.threshold and now - self._last > self.cooldown:
            self._last = now
            self.m.reset()
            return True
        return False


class WakeListener:
    def __init__(self, on_wake: Callable[[], None], is_blocked: Callable[[], bool] = lambda: False,
                 threshold: float = 0.5, device=None):
        self.on_wake, self.is_blocked, self.device = on_wake, is_blocked, device
        self.threshold = threshold
        self._stop = threading.Event()
        self._t: threading.Thread | None = None
        self.error: str | None = None

    def start(self):
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        try:
            import sounddevice as sd
            det = WakeDetector(threshold=self.threshold)
            with sd.InputStream(samplerate=16000, channels=1, dtype="int16", blocksize=FRAME, device=self.device) as st:
                while not self._stop.is_set():
                    data, _ = st.read(FRAME)
                    if self.is_blocked():              # do not listen while speaking / capturing
                        continue
                    if det.feed(data[:, 0]):
                        self.on_wake()
        except Exception as e:
            self.error = str(e)
            print("[wake]", e)


class Endpointer:
    """Decides when you have finished speaking, from the level of the recorded audio."""

    def __init__(self, get_audio: Callable[[], np.ndarray], on_end: Callable[[bool], None],
                 silence: float = 0.7, no_speech_timeout: float = 6.0, max_len: float = 20.0, thresh: float = 0.012):
        self.get_audio, self.on_end = get_audio, on_end
        self.silence, self.no_speech, self.max_len, self.thresh = silence, no_speech_timeout, max_len, thresh
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self):
        self._stop.set()

    def _run(self):
        t0 = time.monotonic()
        spoke = False
        last_voice = t0
        while not self._stop.wait(0.1):
            a = self.get_audio()
            if a.size < 1600:
                continue
            recent = a[-1600:]                      # last 100 ms
            level = float(np.sqrt(np.mean(recent * recent)))
            now = time.monotonic()
            if level > self.thresh:
                spoke, last_voice = True, now
            if spoke and now - last_voice > self.silence:
                return self.on_end(True)
            if not spoke and now - t0 > self.no_speech:
                return self.on_end(False)
            if now - t0 > self.max_len:
                return self.on_end(spoke)
