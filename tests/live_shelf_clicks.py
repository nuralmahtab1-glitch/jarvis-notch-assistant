"""Live UI check of the Shelf: real notch window, simulated mouse clicks and synthesized drag-and-drop events.
Uses a stand-in clipboard and stand-in Ctrl+V, so it never touches your real clipboard or keystrokes."""
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
