"""Pinned apps + Start menu search. Made by Nur Al Mahtab."""
from __future__ import annotations
import os, re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

LAUNCHABLE = {".exe", ".lnk", ".url", ".bat", ".cmd", ".appref-ms"}
JUNK = re.compile(r"uninstall|readme|release notes|license|documentation|\bhelp\b|website|manual|changelog|repair|"
                  r"remove |configure|support", re.I)
MAX_PINNED = 24

# Built-ins that exist on every Windows PC even though they have no Start menu .lnk we can rely on.
BUILTINS = [("File Explorer", "explorer.exe"), ("Notepad", "notepad.exe"), ("Calculator", "calc.exe"),
            ("Settings", "ms-settings:")]
# Apps we would like to pin by default IF the user has them (matched against Start menu names).
WANTED = ["Google Chrome", "Microsoft Edge", "Spotify", "Visual Studio Code", "Discord", "Windows Terminal", "WhatsApp",
          "Word", "Excel", "PowerPoint", "Steam", "OBS Studio", "Slack", "Zoom"]


@dataclass
class AppEntry:
    name: str
    target: str            # a path, or a URI such as ms-settings:

    def as_dict(self) -> dict:
        return {"name": self.name, "target": self.target}


def start_menu_roots() -> list[Path]:
    roots = []
    for var, sub in (("PROGRAMDATA", r"Microsoft\Windows\Start Menu\Programs"), ("APPDATA", r"Microsoft\Windows\Start Menu\Programs")):
        base = os.environ.get(var)
        if base:
            roots.append(Path(base) / sub)
    return roots


def start_menu_index(roots: list[Path] | None = None) -> dict[str, str]:
    """{display name: path to its shortcut}, from the Start menu. Junk entries (uninstallers, readmes) are skipped."""
    out: dict[str, str] = {}
    for root in (roots if roots is not None else start_menu_roots()):
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.suffix.lower() in (".lnk", ".url", ".appref-ms") and not JUNK.search(p.stem):
                out.setdefault(p.stem, str(p))
    return out


# what people say -> what the Start menu calls it
ALIASES = {"vs code": "visual studio code", "vscode": "visual studio code", "code": "visual studio code",
           "chrome": "google chrome", "browser": "google chrome", "edge": "microsoft edge", "ms word": "word",
           "ms excel": "excel", "ms powerpoint": "powerpoint", "terminal": "windows terminal", "obs": "obs studio"}


def resolve(query: str, index: dict[str, str], strict: bool = False) -> tuple[str, str] | None:
    """Best Start menu match for a spoken name: exact, then starts-with, then whole-word, then substring.
    strict=True drops the loose whole-word/substring steps (used for default pins: a wrong guess is worse than none)."""
    q = " ".join(query.lower().split())
    q = ALIASES.get(q, q)
    if len(q) < 2:
        return None
    items = [(n, n.lower(), p) for n, p in index.items()]
    tests = [lambda n: n == q]
    if not strict or len(q) >= 6:                 # short names ("word") must match exactly when being strict
        tests.append(lambda n: n.startswith(q))
    if not strict:
        tests += [lambda n: re.search(rf"\b{re.escape(q)}\b", n) is not None, lambda n: q in n]
    for test in tests:
        hits = sorted((i for i in items if test(i[1])), key=lambda i: len(i[1]))      # shortest name = most specific
        if hits:
            return hits[0][0], hits[0][2]
    return None


def default_apps(index: dict[str, str]) -> list[AppEntry]:
    out = [AppEntry(n, t) for n, t in BUILTINS]
    for want in WANTED:
        hit = resolve(want, index, strict=True)
        if hit and not any(e.name.lower() == hit[0].lower() for e in out):
            out.append(AppEntry(hit[0], hit[1]))
    return out[:12]


def entry_from_path(path: str | Path) -> AppEntry | None:
    p = Path(str(path))
    if not p.exists() or p.suffix.lower() not in LAUNCHABLE:
        return None
    return AppEntry(p.stem, str(p))


class PinnedApps:
    """The pinned list, persisted in settings under `pinned_apps`. `launcher(target)` is injectable for tests."""

    def __init__(self, settings, index: dict[str, str] | None = None, launcher: Callable[[str], None] | None = None):
        self.cfg = settings
        self.index = index if index is not None else {}
        self.launcher = launcher or os.startfile
        saved = settings.get("pinned_apps")
        self.items: list[AppEntry] = [AppEntry(**a) for a in saved] if saved else default_apps(self.index)
        if not saved:
            self._save()

    def _save(self):
        self.cfg.set("pinned_apps", [e.as_dict() for e in self.items])

    def add(self, path) -> AppEntry | None:
        e = entry_from_path(path)
        if not e or len(self.items) >= MAX_PINNED:
            return None
        self.items = [i for i in self.items if i.target.lower() != e.target.lower()]
        self.items.append(e)
        self._save()
        return e

    def remove(self, index: int) -> bool:
        if 0 <= index < len(self.items):
            del self.items[index]
            self._save()
            return True
        return False

    def reset(self):
        self.items = default_apps(self.index)
        self._save()

    def launch(self, index: int) -> bool:
        if not (0 <= index < len(self.items)):
            return False
        try:
            self.launcher(self.items[index].target)
            return True
        except OSError:
            return False

    def launch_by_name(self, name: str) -> str | None:
        """Voice: 'open photoshop'. Pinned apps first, then anything in the Start menu. Returns the app's name."""
        pinned = {e.name: e.target for e in self.items}
        hit = resolve(name, pinned) or resolve(name, self.index)
        if not hit:
            return None
        try:
            self.launcher(hit[1])
            return hit[0]
        except OSError:
            return None
