"""Text-to-speech behind one interface. Made by Nur Al Mahtab.

Engines: Piper (offline, British butler default) and Windows SAPI (zero-download fallback).
speak() is non-blocking; sentences are queued and played back to back; stop() barges in.
"""
from __future__ import annotations
import io, queue, re, threading, wave
from typing import Callable

from app import paths

# the voice ships inside the installer (read-only); a downloaded copy in the user folder also works
MODEL_DIRS = [paths.user_models() / "piper", paths.bundled_models() / "piper"]


def voice_file(name: str):
    return next((d / f"{name}.onnx" for d in MODEL_DIRS if (d / f"{name}.onnx").exists()), None)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


class SapiEngine:
    name = "sapi"

    def __init__(self):
        self._lock = threading.Lock()

    def available(self) -> bool:
        try:
            import win32com.client  # noqa: F401
            return True
        except Exception:
            return False

    def _voice(self, rate: int = 0, volume: int = 100):
        import pythoncom, win32com.client
        pythoncom.CoInitialize()
        v = win32com.client.Dispatch("SAPI.SpVoice")
        v.Rate, v.Volume = rate, volume
        try:  # prefer a British male voice if installed
            for t in v.GetVoices():
                d = t.GetDescription()
                if "George" in d or "Ryan" in d or "Hazel" not in d and "United Kingdom" in d:
                    v.Voice = t
                    break
        except Exception:
            pass
        return v

    def synth_play(self, sentence: str, speed: float, stop_flag: threading.Event, level_cb):
        rate = max(-10, min(10, round((speed - 1.0) * 10)))
        v = self._voice(rate)
        v.Speak(sentence, 1)  # async
        while not v.WaitUntilDone(60):
            if stop_flag.is_set():
                v.Speak("", 3)  # purge
                return
        if level_cb:
            level_cb(0.0)


class PiperEngine:
    name = "piper"

    def __init__(self, voice: str = "en_GB-alan-medium"):
        self.voice_name = voice
        self._voice = None

    def available(self) -> bool:
        return voice_file(self.voice_name) is not None

    def _load(self):
        if self._voice is None:
            from piper import PiperVoice
            self._voice = PiperVoice.load(str(voice_file(self.voice_name)))
        return self._voice

    def synth_wav(self, text: str, speed: float = 1.0) -> bytes:
        from piper import SynthesisConfig
        voice = self._load()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            voice.synthesize_wav(text, wf, syn_config=SynthesisConfig(length_scale=1.0 / max(0.5, speed) * 1.05))
        return buf.getvalue()

    def synth_play(self, sentence: str, speed: float, stop_flag: threading.Event, level_cb):
        import numpy as np, sounddevice as sd
        data = self.synth_wav(sentence, speed)
        with wave.open(io.BytesIO(data)) as wf:
            sr = wf.getframerate()
            pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        chunk = int(sr * 0.04)
        with sd.OutputStream(samplerate=sr, channels=1, dtype="int16") as out:
            for i in range(0, len(pcm), chunk):
                if stop_flag.is_set():
                    break
                c = pcm[i:i + chunk]
                out.write(c)
                if level_cb:
                    level_cb(min(1.0, float(np.abs(c).mean()) / 6000.0))
        if level_cb:
            level_cb(0.0)


class Speaker:
    """Queue of sentences spoken in order. on_state(True/False) brackets speech for ducking and the UI."""

    def __init__(self, on_state: Callable[[bool], None] | None = None,
                 on_level: Callable[[float], None] | None = None, speed: float = 1.0):
        self.engines = [e for e in (PiperEngine(), SapiEngine()) if e.available()]
        self.speed = speed
        self.enabled = True
        self._q: queue.Queue[str | None] = queue.Queue()
        self._stop = threading.Event()
        self._on_state, self._on_level = on_state, on_level
        self._speaking = False
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    @property
    def engine_name(self) -> str:
        return self.engines[0].name if self.engines else "none"

    @property
    def speaking(self) -> bool:
        return self._speaking or not self._q.empty()

    def speak(self, text: str):
        if not self.enabled or not text.strip():
            return
        self._stop.clear()
        for s in split_sentences(text):
            self._q.put(s)

    def stop(self):
        self._stop.set()
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def _loop(self):
        while True:
            s = self._q.get()
            if s is None:
                return
            if self._stop.is_set():
                continue
            if not self._speaking:
                self._speaking = True
                self._on_state and self._on_state(True)
            for eng in self.engines:
                try:
                    eng.synth_play(s, self.speed, self._stop, self._on_level)
                    break
                except Exception as e:  # fall through to the next engine
                    print(f"[tts] {eng.name} failed: {e}")
            if self._q.empty():
                self._speaking = False
                self._on_state and self._on_state(False)
