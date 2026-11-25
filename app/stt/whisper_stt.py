"""Local speech-to-text (faster-whisper, CPU int8). Made by Nur Al Mahtab."""
from __future__ import annotations
import threading
import numpy as np

from app import paths

ROOT = paths.user_models() / "whisper"


class Transcriber:
    def __init__(self, model_size: str = "base.en"):
        self.model_size = model_size
        self._model = None
        self._lock = threading.Lock()
        self._tlock = threading.Lock()   # one transcription at a time

    def cached(self) -> bool:
        """Is the speech model already on this PC? (If not, the first use downloads about 150 MB.)"""
        return (ROOT / f"models--Systran--faster-whisper-{self.model_size}").exists()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self):
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel
                ROOT.mkdir(parents=True, exist_ok=True)
                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8",
                                           download_root=str(ROOT), cpu_threads=4)
                try:                         # first real run is slow: do a throw-away one now
                    list(self._model.transcribe(np.zeros(8000, dtype=np.float32), language="en", beam_size=1)[0])
                except Exception:
                    pass
        return self._model

    @staticmethod
    def level_fix(audio: np.ndarray) -> np.ndarray:
        """A quiet microphone is the most common reason for misheard words: bring the loudest part up to a healthy level."""
        peak = float(np.abs(audio).max()) if audio.size else 0.0
        if 0.003 < peak < 0.5:
            return np.clip(audio * (0.7 / peak), -1.0, 1.0).astype(np.float32)
        return audio

    def transcribe(self, audio: np.ndarray, prompt: str = "") -> str:
        if audio.size < 1600:  # < 0.1 s
            return ""
        audio = self.level_fix(audio)
        model = self.load()
        with self._tlock:
          segments, _ = model.transcribe(
              audio, language="en", beam_size=1, vad_filter=True,
              vad_parameters={"min_silence_duration_ms": 250},
              condition_on_previous_text=False, initial_prompt=prompt or None)
          return " ".join(s.text.strip() for s in segments).strip()
