"""ShelfController: clipboard watcher + copy/paste/drop glue for the Shelf panel. Made by Nur Al Mahtab."""
from __future__ import annotations
from PySide6.QtCore import QMimeData, QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication

from app.core.shelf import Shelf


def excluded_by_source(md) -> bool:
    """Windows lets apps (password managers, banking sites) mark clipboard data as 'do not record'.
    We honour both markers, and keep nothing from such a copy."""
    for fmt in md.formats():
        if "ExcludeClipboardContentFromMonitorProcessing" in fmt:
            return True
        if "CanIncludeInClipboardHistory" in fmt:
            data = bytes(md.data(fmt))
            if data and not any(data):            # DWORD 0 = not allowed
                return True
    return False


class ShelfController(QObject):
    changed = Signal()

    def __init__(self, notch, clipboard=None, system=None, shelf: Shelf | None = None, enabled: bool = True,
                 demo: bool = False):
        super().__init__()
        self.notch = notch
        self.shelf = shelf or Shelf()
        self.sys = system                         # app.winio.system (foreground_window, press_ctrl_v), injectable
        self.clip = clipboard or QGuiApplication.clipboard()
        self._enabled = enabled
        self._msg = ""
        self._target = 0                          # the window that was in front when the shelf opened
        self._own = 0                             # ignore the clipboard change we cause ourselves a moment ago
        self.clip.dataChanged.connect(self._on_clip)
        self._tick = QTimer(self); self._tick.setInterval(30000); self._tick.timeout.connect(self.changed.emit); self._tick.start()
        if demo:
            self.shelf.add_text("Meeting notes: ship the beta on Friday, ask Maya about the invoice.")
            self.shelf.add_text("https://example.com/launch-checklist")
            self.shelf.add_text("Call the dentist before noon")

    # ---------------- properties ----------------
    items = Property("QVariantList", lambda s: s.shelf.view(), notify=changed)
    message = Property(str, lambda s: s._msg, notify=changed)
    count = Property(int, lambda s: len(s.shelf), notify=changed)
    enabled = Property(bool, lambda s: s._enabled, notify=changed)

    def set_enabled(self, on: bool):
        self._enabled = bool(on)
        if not on:
            self.shelf.clear()
        self.changed.emit()

    def _say(self, text: str):
        self._msg = text
        self.changed.emit()
        QTimer.singleShot(2800, lambda: self._clear_msg(text))

    def _clear_msg(self, text: str):
        if self._msg == text:
            self._msg = ""
            self.changed.emit()

    # ---------------- clipboard in ----------------
    def _on_clip(self):
        if not self._enabled:
            return
        if self._own > 0:
            self._own -= 1
            return
        md = self.clip.mimeData()
        if md is None or excluded_by_source(md):
            return
        if md.hasUrls() and all(u.isLocalFile() for u in md.urls()):
            self.shelf.add_files(u.toLocalFile() for u in md.urls())
        elif md.hasText():
            self.shelf.add_text(md.text())
        else:
            return
        self.changed.emit()

    # ---------------- panel actions ----------------
    @Slot()
    def opened(self):
        """Remember which window you were in, so Paste goes back to it (and only it)."""
        self._target = self.sys.foreground_window() if self.sys else 0

    def _put(self, it) -> None:
        md = QMimeData()
        if it.kind == "file":
            md.setUrls([QUrl.fromLocalFile(it.text)])
        else:
            md.setText(it.text)
        self._own += 1                             # this write is ours: do not re-add it as a new copy
        self.clip.setMimeData(md)

    @Slot(int)
    def copy(self, item_id: int):
        it = self.shelf.get(item_id)
        if not it:
            return
        self._put(it)
        self._say("File copied" if it.kind == "file" else "Copied")

    @Slot(int)
    def paste(self, item_id: int):
        """Copy the item, then press Ctrl+V in the window you were using. Fails closed if that window changed."""
        it = self.shelf.get(item_id)
        if not it:
            return
        self._put(it)
        if self.sys and self._target and self.sys.foreground_window() == self._target:
            QTimer.singleShot(120, self.sys.press_ctrl_v)
            self._say("Pasted")
        else:
            self._say("Copied. The window changed, so press Ctrl+V yourself")

    @Slot(int)
    def remove(self, item_id: int):
        self.shelf.remove(item_id)
        self.changed.emit()

    @Slot()
    def clear(self):
        self.shelf.clear()
        self._say("Shelf cleared")

    # ---------------- drops ----------------
    @Slot("QVariantList")
    def dropUrls(self, urls):
        paths = []
        for u in urls:
            q = u if isinstance(u, QUrl) else QUrl(str(u))
            if q.isLocalFile():
                paths.append(q.toLocalFile())
        added = self.shelf.add_files(paths)
        self._say(f"Parked {len(added)} file{'s' if len(added) != 1 else ''}" if added else "Nothing to park")

    @Slot(str)
    def dropText(self, text: str):
        if self.shelf.add_text(text):
            self._say("Parked the text")
        else:
            self._say("Nothing to park")
