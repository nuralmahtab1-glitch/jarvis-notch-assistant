"""Teleprompter + Menu controllers. Made by Nur Al Mahtab."""
from __future__ import annotations
import re
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

from app.core.prompter import Prompter

SITE_OK = re.compile(r"^(?:https?://)?([a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+)(/[^\s]*)?$", re.I)
FILE_ENDINGS = {"exe", "bat", "cmd", "msi", "ps1", "vbs", "lnk", "scr", "dll", "jar", "zip", "iso"}
GUIDE = ["Hold Right Ctrl and say what you need. Hold Right Alt to dictate.",
         "Say \"Hey Jarvis\" for hands-free. Say \"What can you do?\" for the full list.",
         "Drag a file onto the notch to park it. Drop a program on the Apps panel to pin it."]


def clean_site(entry: str) -> tuple[str, str] | None:
    """Accept only plain web addresses. Returns (label, https url) or None (rejects file:, javascript:, spaces, ...)."""
    e = entry.strip()
    m = SITE_OK.match(e)
    if not m:
        return None
    host = m.group(1).lower()
    if host.rsplit(".", 1)[-1] in FILE_ENDINGS:          # "calc.exe" is a program, not a website
        return None
    url = e if e.lower().startswith(("http://", "https://")) else "https://" + e
    label = host[4:] if host.startswith("www.") else host
    return label[:28], url


def clean_sites(entries) -> list[str]:
    seen, out = set(), []
    for e in entries:
        c = clean_site(str(e))
        if c and c[1].lower() not in seen:
            seen.add(c[1].lower()); out.append(c[1])
    return out[:8]


class PrompterController(QObject):
    changed = Signal()

    def __init__(self, notch, settings, clipboard=None):
        super().__init__()
        self.notch, self.cfg = notch, settings
        self.clip = clipboard or QGuiApplication.clipboard()
        self.p = Prompter("", settings["prompter_wpm"])
        self._msg = ""
        self._timer = QTimer(self); self._timer.setInterval(100); self._timer.timeout.connect(self._tick)
        self._timer.start()

    view = Property("QVariantMap", lambda s: s.p.view(), notify=changed)
    message = Property(str, lambda s: s._msg, notify=changed)
    minutesLeft = Property(float, lambda s: s.p.minutes_left(), notify=changed)

    def _tick(self):
        if self.p.running:
            self.p.tick(0.1)
            if self.notch is not None:
                self.notch.keepAwake(8)
            self.changed.emit()

    def _say(self, text: str):
        self._msg = text
        self.changed.emit()
        QTimer.singleShot(3500, lambda: (setattr(self, "_msg", ""), self.changed.emit()) if self._msg == text else None)

    @Slot(result=bool)
    def start(self) -> bool:
        """Read the script you copied. Returns False (and says why) if there is nothing to read."""
        md = self.clip.mimeData()
        text = md.text() if md is not None and md.hasText() else ""
        if not text.strip():
            self._say("Copy your script first, then start the teleprompter.")
            return False
        self.p = Prompter(text, self.cfg["prompter_wpm"])
        if self.p.empty:
            self._say("That did not look like a script.")
            return False
        self.p.running = True
        if self.notch is not None:
            self.notch.setMode("prompter")
        self.changed.emit()
        return True

    @Slot()
    def toggle(self):
        self.p.toggle(); self.changed.emit()

    @Slot()
    def restart(self):
        self.p.restart(); self.changed.emit()

    @Slot()
    def faster(self):
        self.cfg.set("prompter_wpm", self.p.faster()); self.changed.emit()

    @Slot()
    def slower(self):
        self.cfg.set("prompter_wpm", self.p.slower()); self.changed.emit()

    @Slot()
    def close(self):
        self.p.running = False
        if self.notch is not None and self.notch.mode == "prompter":
            self.notch.setMode("idle")
        self.changed.emit()


class MenuController(QObject):
    changed = Signal()

    def __init__(self, notch, settings, opener=None, prompter: PrompterController | None = None):
        super().__init__()
        self.notch, self.cfg, self.prompter = notch, settings, prompter
        if opener is None:
            from app.winio import system
            opener = system.open_url
        self._open = opener

    @Property("QVariantList", notify=changed)
    def sites(self):
        out = []
        for i, entry in enumerate(clean_sites(self.cfg["websites"])):
            label, _ = clean_site(entry)
            out.append({"id": i, "label": label})
        return out

    guide = Property("QStringList", lambda s: GUIDE, constant=True)

    @Slot(int)
    def openSite(self, index: int):
        sites = clean_sites(self.cfg["websites"])
        if 0 <= index < len(sites):
            self._open(sites[index])                       # only validated https/http addresses ever reach the browser
            if self.notch is not None:
                self.notch.setMode("idle")

    @Slot()
    def startPrompter(self):
        if self.prompter is not None:
            self.prompter.start()

    @Slot()
    def openMusic(self):
        if self.notch is not None:
            self.notch.setMode("music")
