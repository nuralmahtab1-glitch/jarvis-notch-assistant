"""AppsController: the pinned-apps grid (icons, launching, pinning by drop or file picker). Made by Nur Al Mahtab."""
from __future__ import annotations
import base64, os, shutil
from pathlib import Path
from PySide6.QtCore import QBuffer, QByteArray, QFileInfo, QIODevice, QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QFileIconProvider

from app.core.apps import LAUNCHABLE, PinnedApps


class AppsController(QObject):
    changed = Signal()

    def __init__(self, notch, pins: PinnedApps, picker=None):
        super().__init__()
        self.notch, self.pins = notch, pins
        self._msg = ""
        self._icons: dict[str, str] = {}
        self._provider = None
        self._picker = picker or self._native_picker       # injectable so tests never open a real dialog

    # ---------------- icons (rendered to small PNG data URLs; safe on the GUI thread) ----------------
    def _icon_for(self, target: str) -> str:
        if target in self._icons:
            return self._icons[target]
        path = target if os.path.exists(target) else (shutil.which(target) or "")
        url = ""
        if path:
            try:
                if self._provider is None:
                    self._provider = QFileIconProvider()
                info = QFileInfo(path)
                real = info.symLinkTarget() if path.lower().endswith(".lnk") else ""      # icon of the program itself,
                if real and os.path.exists(real):                                         # not the shortcut-arrow overlay
                    info = QFileInfo(real)
                pm = self._provider.icon(info).pixmap(48, 48)
                if not pm.isNull():
                    ba, buf = QByteArray(), QBuffer()
                    buf.setBuffer(ba); buf.open(QIODevice.WriteOnly)
                    pm.save(buf, "PNG")
                    url = "data:image/png;base64," + base64.b64encode(bytes(ba)).decode()
            except Exception:
                url = ""
        self._icons[target] = url
        return url

    def _items(self):
        return [{"id": i, "name": e.name, "icon": self._icon_for(e.target), "letter": (e.name[:1] or "?").upper()}
                for i, e in enumerate(self.pins.items)]

    items = Property("QVariantList", _items, notify=changed)
    message = Property(str, lambda s: s._msg, notify=changed)
    count = Property(int, lambda s: len(s.pins.items), notify=changed)

    def _say(self, text: str):
        self._msg = text
        self.changed.emit()
        QTimer.singleShot(2800, lambda: self._clear(text))

    def _clear(self, text: str):
        if self._msg == text:
            self._msg = ""
            self.changed.emit()

    # ---------------- actions ----------------
    @Slot(int)
    def launch(self, index: int):
        if not (0 <= index < len(self.pins.items)):
            return
        name = self.pins.items[index].name
        if self.pins.launch(index):
            self._say(f"Opening {name}")
            if self.notch is not None:
                QTimer.singleShot(500, lambda: self.notch.setMode("idle") if self.notch.mode == "apps" else None)
        else:
            self._say(f"Could not open {name}")

    @Slot(int)
    def remove(self, index: int):
        if 0 <= index < len(self.pins.items):
            name = self.pins.items[index].name
            self.pins.remove(index)
            self._say(f"Unpinned {name}")

    @Slot("QVariantList")
    def dropUrls(self, urls):
        added, refused = [], 0
        for u in urls:
            q = u if isinstance(u, QUrl) else QUrl(str(u))
            e = self.pins.add(q.toLocalFile()) if q.isLocalFile() else None
            added.append(e.name) if e else None
            refused += 0 if e else 1
        if added:
            self._say("Pinned " + ", ".join(added[:3]))
        else:
            self._say("Only programs and shortcuts can be pinned")

    @Slot()
    def addDialog(self):
        path = self._picker()
        if not path:
            return
        e = self.pins.add(path)
        self._say(f"Pinned {e.name}" if e else "Only programs and shortcuts can be pinned")

    @Slot()
    def reset(self):
        self.pins.reset()
        self._say("Back to the default apps")

    def _native_picker(self) -> str:
        exts = " ".join("*" + x for x in sorted(LAUNCHABLE))
        start = os.environ.get("APPDATA", str(Path.home())) + r"\Microsoft\Windows\Start Menu\Programs"
        path, _ = QFileDialog.getOpenFileName(None, "Pin an app", start, f"Programs and shortcuts ({exts})")
        return path
