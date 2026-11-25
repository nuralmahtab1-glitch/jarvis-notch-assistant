"""Teleprompter engine: wraps your script into lines and scrolls through it at a steady pace. Made by Nur Al Mahtab."""
from __future__ import annotations
import re, textwrap

MIN_WPM, MAX_WPM, STEP = 60, 300, 10


def wrap_script(text: str, width: int = 44) -> list[tuple[str, int]]:
    """[(line, words_in_line)], keeping paragraph breaks as empty lines."""
    out: list[tuple[str, int]] = []
    for para in re.split(r"\n\s*\n", text.strip()):
        flat = " ".join(para.split())
        if not flat:
            continue
        for line in textwrap.wrap(flat, width=width, break_long_words=True):
            out.append((line, len(line.split())))
        out.append(("", 0))
    if out and out[-1][0] == "":
        out.pop()
    return out


class Prompter:
    def __init__(self, text: str = "", wpm: int = 140, width: int = 44):
        self.lines = wrap_script(text, width)
        self.total_words = sum(n for _, n in self.lines)
        self.wpm = max(MIN_WPM, min(MAX_WPM, wpm))
        self.running = False
        self.words_done = 0.0

    @property
    def empty(self) -> bool:
        return not self.lines

    @property
    def done(self) -> bool:
        return self.total_words > 0 and self.words_done >= self.total_words

    def tick(self, seconds: float) -> None:
        """Advance by `seconds` of reading time (call from a timer while running)."""
        if self.running and not self.done:
            self.words_done = min(self.total_words, self.words_done + self.wpm / 60.0 * seconds)
            if self.done:
                self.running = False

    def toggle(self) -> None:
        if self.done:
            self.restart()
        if not self.empty:
            self.running = not self.running

    def restart(self) -> None:
        self.words_done, self.running = 0.0, False

    def faster(self) -> int:
        self.wpm = min(MAX_WPM, self.wpm + STEP); return self.wpm

    def slower(self) -> int:
        self.wpm = max(MIN_WPM, self.wpm - STEP); return self.wpm

    def current_index(self) -> int:
        """Index of the line being read: the first non-empty line that still has unread words."""
        acc = 0
        for i, (_, n) in enumerate(self.lines):
            if n and acc + n > self.words_done:
                return i
            acc += n
        return max(0, len(self.lines) - 1)

    def view(self) -> dict:
        if self.empty:
            return {"prev": "", "cur": "", "next": "", "next2": "", "progress": 0.0, "wpm": self.wpm, "running": False, "done": False, "empty": True}
        i = self.current_index()
        g = lambda k: self.lines[k][0] if 0 <= k < len(self.lines) else ""
        # skip blank separator lines when showing neighbours
        prev = next((self.lines[k][0] for k in range(i - 1, -1, -1) if self.lines[k][0]), "")
        nxt = [self.lines[k][0] for k in range(i + 1, len(self.lines)) if self.lines[k][0]]
        return {"prev": prev, "cur": g(i), "next": nxt[0] if nxt else "", "next2": nxt[1] if len(nxt) > 1 else "",
                "progress": self.words_done / self.total_words if self.total_words else 0.0, "wpm": self.wpm,
                "running": self.running, "done": self.done, "empty": False}

    def minutes_left(self) -> float:
        return max(0.0, (self.total_words - self.words_done) / self.wpm)
