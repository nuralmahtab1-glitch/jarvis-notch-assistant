"""Shelf: recent clipboard items and parked files. Memory only, never written to disk. Made by Nur Al Mahtab."""
from __future__ import annotations
import os, re, time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

MAX_ITEMS = 30
MAX_TEXT = 2000


def looks_secret(text: str) -> bool:
    """Heuristic: a single long 'word' mixing letters, digits and symbols is probably a password or API key.
    Better to miss a clipboard entry than to keep a secret on the shelf."""
    t = text.strip()
    if len(t) < 12 or len(t) > 200 or re.search(r"\s", t):
        return False
    if re.match(r"^(sk|pk|ghp|gho|xox[bp]|AKIA|eyJ)[-_A-Za-z0-9]{8,}", t):          # common token prefixes
        return True
    classes = sum(bool(re.search(p, t)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if re.match(r"^(https?://|[A-Za-z]:\\|/)", t) or re.match(r"^[\w.+-]+@[\w-]+\.[\w.]+$", t):
        return False                                                                  # URLs, paths and emails are fine
    return classes >= 3


@dataclass
class Item:
    id: int
    kind: str          # "text" or "file"
    text: str          # the text, or the full path
    t: float


def age(seconds: float) -> str:
    s = int(max(0, seconds))
    if s < 45:
        return "just now"
    if s < 3600:
        return f"{max(1, s // 60)} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    return f"{s // 86400} d ago"


class Shelf:
    def __init__(self, clock: Callable[[], float] = time.time, max_items: int = MAX_ITEMS):
        self.clock, self.max_items = clock, max_items
        self._items: list[Item] = []
        self._next = 1

    def _push(self, kind: str, text: str) -> Item:
        self._items = [i for i in self._items if not (i.kind == kind and i.text == text)]    # dedupe: move to top
        it = Item(self._next, kind, text, self.clock())
        self._next += 1
        self._items.insert(0, it)
        del self._items[self.max_items:]
        return it

    def add_text(self, text: str) -> Item | None:
        if not text or not text.strip() or looks_secret(text):
            return None
        return self._push("text", text[:MAX_TEXT])

    def add_files(self, paths) -> list[Item]:
        out = []
        for p in paths:
            p = str(p)
            if p and os.path.exists(p):
                out.append(self._push("file", os.path.normpath(p)))
        return out

    def get(self, item_id: int) -> Item | None:
        return next((i for i in self._items if i.id == item_id), None)

    def remove(self, item_id: int) -> bool:
        n = len(self._items)
        self._items = [i for i in self._items if i.id != item_id]
        return len(self._items) != n

    def clear(self) -> None:
        self._items = []

    def __len__(self) -> int:
        return len(self._items)

    def items(self) -> list[Item]:
        return list(self._items)

    def view(self) -> list[dict]:
        """What the UI shows: one dict per item, newest first."""
        now = self.clock()
        out = []
        for i in self._items:
            if i.kind == "file":
                p = Path(i.text)
                title, sub = p.name or i.text, f"{str(p.parent)}  ·  {age(now - i.t)}"
                url = p.as_uri()
            else:
                one = " ".join(i.text.split())
                title = one if len(one) <= 64 else one[:61] + "..."
                n = len(i.text)
                sub = f"{n} character{'s' if n != 1 else ''}  ·  {age(now - i.t)}"
                url = ""
            out.append({"id": i.id, "kind": i.kind, "title": title, "sub": sub, "full": i.text, "url": url})
        return out
