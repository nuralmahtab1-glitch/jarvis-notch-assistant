"""Microphone capture to memory only. Audio is never written to disk. Made by Nur Al Mahtab."""
from __future__ import annotations
import threading
from typing import Callable
import numpy as np

SAMPLE_RATE = 16000


class Recorder:
    def __init__(self, on_level: Callable[[float], None] | None = None, device=None):
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream = None
        self._on_level = on_level
        self.device = device

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self):
        import sounddevice as sd
        if self._stream:
            return
        with self._lock:
            self._chunks = []

        def cb(indata, frames, t, status):
            x = indata[:, 0].copy()
            with self._lock:
                self._chunks.append(x)
            if self._on_level:
                self._on_level(min(1.0, float(np.sqrt(np.mean(x * x))) * 14))

        self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                      blocksize=1024, device=self.device, callback=cb)
        self._stream.start()

    def snapshot(self) -> np.ndarray:
        with self._lock:
            return np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype="float32")

    def stop(self) -> np.ndarray:
        if self._stream:
            self._stream.stop(); self._stream.close(); self._stream = None
        audio = self.snapshot()
        with self._lock:
            self._chunks = []  # audio is discarded as soon as it has been handed over
        if self._on_level:
            self._on_level(0.0)
        return audio


def device_index(name: str):
    """Map a saved device name to a sounddevice index (None = system default)."""
    if not name or name == "Default microphone":
        return None
    for i, n in list_input_devices():
        if n == name:
            return i
    return None


def list_input_devices() -> list[tuple[int, str]]:
    import sounddevice as sd
    return [(i, d["name"]) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
