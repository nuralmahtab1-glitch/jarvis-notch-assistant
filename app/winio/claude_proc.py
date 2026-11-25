"""Notice that Claude Code is busy, with no hooks needed: watch its processes' CPU use. Made by Nur Al Mahtab.

Claude Code sits at ~0% CPU while idle and uses noticeably more while it streams, edits and runs tools. We call it
"active" while that is happening, and for a grace period afterwards so a long pause (a slow command, a permission
question) does not let the laptop fall asleep mid-task.
"""
from __future__ import annotations
import time
from typing import Callable, Iterable

ACTIVE_CPU = 3.0                 # percent of one core, summed over Claude Code's processes
GRACE_SECONDS = 15 * 60          # stay "active" this long after the last burst of work


def default_processes() -> Iterable:
    import psutil
    for p in psutil.process_iter(["name"]):
        name = (p.info.get("name") or "").lower()
        if name.startswith("claude"):
            yield p


class ClaudeActivity:
    def __init__(self, processes: Callable[[], Iterable] = default_processes, clock: Callable[[], float] = time.monotonic,
                 threshold: float = ACTIVE_CPU, grace: float = GRACE_SECONDS):
        self._processes, self._clock = processes, clock
        self.threshold, self.grace = threshold, grace
        self._known: dict[int, object] = {}          # psutil needs the same Process object between samples
        self._last_busy: float | None = None
        self.running = False

    def sample(self) -> bool:
        """Look now. True if Claude Code is using CPU right now."""
        total, seen = 0.0, {}
        try:
            for p in self._processes():
                proc = self._known.get(p.pid, p)
                seen[p.pid] = proc
                try:
                    total += proc.cpu_percent(interval=None)      # first call per process returns 0.0 and primes it
                except Exception:
                    pass
        except Exception:
            pass
        self._known = seen
        self.running = bool(seen)
        busy = total >= self.threshold
        if busy:
            self._last_busy = self._clock()
        return busy

    def active(self) -> bool:
        """Busy now, or was busy within the grace period."""
        self.sample()
        return self._last_busy is not None and self._clock() - self._last_busy <= self.grace
