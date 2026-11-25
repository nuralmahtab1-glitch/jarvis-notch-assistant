"""Keep the laptop from going to sleep. Made by Nur Al Mahtab.

Uses Windows' SetThreadExecutionState: no administrator rights, nothing to undo, and Windows drops the request
by itself if Jarvis closes or crashes. It cannot stop the *lid* from sleeping the laptop (that is a power-plan
setting) or you choosing Sleep manually.
"""
from __future__ import annotations
import ctypes, threading, time
from typing import Callable

ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x00000001, 0x00000002


def _real_api() -> Callable[[int], int]:
    k = ctypes.windll.kernel32
    k.SetThreadExecutionState.argtypes = [ctypes.c_uint]
    k.SetThreadExecutionState.restype = ctypes.c_uint
    return k.SetThreadExecutionState


class KeepAwake:
    """The request belongs to the thread that makes it, so a dedicated thread holds it until released."""

    def __init__(self, api: Callable[[int], int] | None = None, clock: Callable[[], float] = time.monotonic):
        self._api = api or _real_api()
        self._clock = clock
        self._lock = threading.Lock()
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self.active = False
        self.display = True
        self._deadline: float | None = None

    def on(self, display: bool = True, minutes: float | None = None) -> None:
        """Start (or restart with new settings). minutes=None means until you turn it off."""
        with self._lock:
            self._release_locked()
            flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | (ES_DISPLAY_REQUIRED if display else 0)
            stop = threading.Event()

            def hold():
                self._api(flags)
                stop.wait()
                self._api(ES_CONTINUOUS)               # give the request back

            self._stop, self._thread = stop, threading.Thread(target=hold, daemon=True)
            self._thread.start()
            self.active, self.display = True, display
            self._deadline = None if minutes is None else self._clock() + minutes * 60

    def off(self) -> None:
        with self._lock:
            self._release_locked()

    def _release_locked(self) -> None:
        if self._stop is not None:
            self._stop.set()
            if self._thread is not None:
                self._thread.join(timeout=2)
        self._stop = self._thread = None
        self.active, self._deadline = False, None

    def remaining(self) -> float | None:
        """Seconds left on a timed session, or None if it has no end (or is off)."""
        if not self.active or self._deadline is None:
            return None
        return max(0.0, self._deadline - self._clock())

    def expired(self) -> bool:
        return self.active and self._deadline is not None and self._clock() >= self._deadline
