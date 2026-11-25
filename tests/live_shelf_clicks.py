"""Live UI check of the Shelf: real notch window, simulated mouse clicks and synthesized drag-and-drop events.
Uses a stand-in clipboard and stand-in Ctrl+V, so it never touches your real clipboard or keystrokes."""
import os as _os
_os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")      # independent of your real screen and mouse
_os.environ.setdefault("QT_QUICK_BACKEND", "software")
_os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")      # real fonts, so text metrics are realistic offscreen

import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, ".")
from PySide6.QtCore import QMimeData, QObject, QPoint, QPointF, QUrl, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import wrapInstance, getCppPointer
from app.ui.controller import NotchController
from app.ui.shelf_ctl import ShelfController

app = QApplication([])


class FakeClip(QObject):
    dataChanged = Signal()
    def __init__(self): super().__init__(); self._md = None
    def mimeData(self): return self._md
    def setMimeData(self, md): self._md = md; self.dataChanged.emit()
    def text(self): return self._md.text() if self._md and self._md.hasText() else ""


class FakeSys:
    fg = 111; pasted = 0
    def foreground_window(self): return self.fg
    def press_ctrl_v(self): FakeSys.pasted += 1


clip, fsys = FakeClip(), FakeSys()
ctl = NotchController(); shelf = ShelfController(ctl, clipboard=clip, system=fsys)
eng = QQmlApplicationEngine(); eng.rootContext().setContextProperty("notch", ctl); eng.rootContext().setContextProperty("shelf", shelf)
from app.core.apps import PinnedApps
from app.ui.apps_ctl import AppsController
from app.store.db import Settings as _Set
import tempfile as _tf
_pins = PinnedApps(_Set(__import__("pathlib").Path(_tf.mkdtemp()) / "a.json"), {}, launcher=lambda t: None)
_apps_keepalive = AppsController(ctl, _pins)                          # keep a reference (Python would delete it)
eng.rootContext().setContextProperty("apps", _apps_keepalive)
from app.ui.widgets_ctl import WidgetsController as _WC
from app.store.db import Store as _St, Settings as _Se
import tempfile as _t2, pathlib as _p2
_d2 = _p2.Path(_t2.mkdtemp())
_wc_keepalive = _WC(_Se(_d2 / "w.json"), _St(_d2 / "w.db"))          # keep a reference: Python would otherwise delete it
eng.rootContext().setContextProperty("widgets", _wc_keepalive)
from app.ui.prompter_ctl import PrompterController as _PC, MenuController as _MC
_pc_keepalive = _PC(ctl, _Se(_d2 / "p.json"), clipboard=Clip() if "Clip" in dir() else None)
_mc_keepalive = _MC(ctl, _Se(_d2 / "m.json"), opener=lambda u: None, prompter=_pc_keepalive)
eng.rootContext().setContextProperty("prompter", _pc_keepalive)
eng.rootContext().setContextProperty("menu", _mc_keepalive)
eng.load(QUrl.fromLocalFile("app/ui/qml/Notch.qml"))
w = eng.rootObjects()[0]; qw = wrapInstance(getCppPointer(w)[0], QQuickWindow)
results = []


def pump(s=0.5):
    end = time.time() + s
    while time.time() < end:
        app.processEvents(); time.sleep(0.01)


def walk():
    stack = [qw.contentItem()]
    while stack:
        it = stack.pop(); yield it; stack.extend(it.childItems())


def centre(pred):
    for it in walk():
        if it.isVisible() and pred(it):
            p = it.mapToScene(it.boundingRect().center()); return QPoint(int(p.x()), int(p.y()))


def click(pred, what):
    pt = centre(pred); assert pt, f"could not find {what}"
    QTest.mouseClick(qw, Qt.LeftButton, Qt.NoModifier, pt); pump(0.4)


def check(name, cond):
    results.append(bool(cond)); print(("PASS" if cond else "FAIL"), name)


def copy_text(t):
    md = QMimeData(); md.setText(t); clip.setMimeData(md); pump(0.2)


copy_text("buy milk and eggs"); copy_text("call Maya about the invoice")
check("two copies appeared on the shelf, newest first", [i["full"] for i in shelf.items] == ["call Maya about the invoice", "buy milk and eggs"])

# open the shelf the way the tab icon does
shelf.opened(); ctl.setMode("shelf"); pump(1.2)
check("shelf panel is showing", ctl.mode == "shelf" and centre(lambda it: it.property("text") == "call Maya about the invoice") is not None)

copy_text("placeholder so the clipboard differs")
click(lambda it: it.property("text") == "buy milk and eggs", "an item row")
check("clicking an item copies it back to the clipboard", clip.text() == "buy milk and eggs" and "Copied" in shelf.message)

click(lambda it: it.property("text") == "", "paste button")
pump(0.3)
check("Paste button sends Ctrl+V to the window you were in", FakeSys.pasted == 1 and shelf.message == "Pasted")

n = shelf.count
click(lambda it: it.property("text") == "✕", "remove button")
check("remove (x) deletes an item", shelf.count == n - 1)

# synthesize a real drag-and-drop of a file onto the notch
d = Path(tempfile.mkdtemp()); f = d / "proposal.pdf"; f.write_text("x")
ctl.setMode("idle"); pump(1.0)
md = QMimeData(); md.setUrls([QUrl.fromLocalFile(str(f))])
pos = QPoint(w.width() // 2, 14)
QApplication.sendEvent(qw, QDragEnterEvent(pos, Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)); pump(0.8)
check("dragging a file over the idle notch opens the shelf", ctl.mode == "shelf")
QApplication.sendEvent(qw, QDragMoveEvent(pos, Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)); pump(0.2)
QApplication.sendEvent(qw, QDropEvent(QPointF(pos), Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)); pump(0.6)
check("dropping the file parks it on the shelf", any(i["title"] == "proposal.pdf" and i["kind"] == "file" for i in shelf.items))

click(lambda it: it.property("label") == "Clear shelf", "clear button")
check("Clear shelf empties it", shelf.count == 0 and shelf.message == "Shelf cleared")
print(f"\n{sum(results)}/{len(results)} shelf interactions behaved")
sys.exit(0 if all(results) else 1)
