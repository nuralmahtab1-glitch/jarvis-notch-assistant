"""Live UI check of the Apps panel: real notch window, simulated clicks/hover, synthesized drag-and-drop.
A stand-in launcher is used, so no program is ever started by this test."""
import os as _os
_os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")      # independent of your real screen and mouse
_os.environ.setdefault("QT_QUICK_BACKEND", "software")

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
from app.core.apps import PinnedApps
from app.store.db import Settings
from app.ui.apps_ctl import AppsController
from app.ui.controller import NotchController
from app.ui.shelf_ctl import ShelfController

app = QApplication([])
d = Path(tempfile.mkdtemp())
launched = []
picked = {"path": ""}
ctl = NotchController()
pins = PinnedApps(Settings(d / "s.json"), {"Photoshop": str(d / "Photoshop.lnk")}, launcher=launched.append)
apps = AppsController(ctl, pins, picker=lambda: picked["path"])


class Clip(QObject):
    dataChanged = Signal()
    def mimeData(self): return None


shelf = ShelfController(ctl, clipboard=Clip())
eng = QQmlApplicationEngine()
for k, v in (("notch", ctl), ("shelf", shelf), ("apps", apps)):
    eng.rootContext().setContextProperty(k, v)
from app.ui.widgets_ctl import WidgetsController as _WC
from app.store.db import Store as _St, Settings as _Se
import tempfile as _t2, pathlib as _p2
_d2 = _p2.Path(_t2.mkdtemp())
_wc_keepalive = _WC(_Se(_d2 / "w.json"), _St(_d2 / "w.db"))          # keep a reference: Python would otherwise delete it
eng.rootContext().setContextProperty("widgets", _wc_keepalive)
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


def text_pt(t):
    return centre(lambda it: it.property("text") == t or it.property("label") == t)


def click(pt):
    QTest.mouseClick(qw, Qt.LeftButton, Qt.NoModifier, pt); pump(0.4)


def check(name, cond):
    results.append(bool(cond)); print(("PASS" if cond else "FAIL"), name)


ctl.setMode("apps"); pump(1.4)
check("apps panel is showing the default pinned apps", ctl.mode == "apps" and text_pt("Notepad") is not None and text_pt("File Explorer") is not None)

click(text_pt("Notepad"))
check("clicking an app launches it", launched and launched[-1] == "notepad.exe" and apps.message == "Opening Notepad")
pump(0.8)
check("the panel gets out of the way after launching", ctl.mode == "idle")
ctl.setMode("apps"); pump(1.2)                      # reopen it

exe = d / "Cool Tool.exe"; exe.write_text("x"); picked["path"] = str(exe)
n = apps.count
click(text_pt("Pin an app"))
check("'Pin an app' tile pins the chosen program", apps.count == n + 1 and text_pt("Cool Tool") is not None)

# hover a tile to reveal its x, then click it
tile = text_pt("Cool Tool")
QTest.mouseMove(qw, tile); pump(0.3)
x = centre(lambda it: it.property("text") == "✕" and it.isVisible())
check("hovering a tile shows an unpin x", x is not None)
click(x)
check("clicking the x unpins it", apps.count == n and text_pt("Cool Tool") is None)

# drag a program onto the open panel: it must be pinned (NOT sent to the clipboard shelf)
shelf_before = shelf.count
exe2 = d / "Dropped App.exe"; exe2.write_text("x"); txt = d / "readme.txt"; txt.write_text("x")
md = QMimeData(); md.setUrls([QUrl.fromLocalFile(str(exe2))])
pos = QPoint(w.width() // 2, 60)
QApplication.sendEvent(qw, QDragEnterEvent(pos, Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)); pump(0.3)
QApplication.sendEvent(qw, QDragMoveEvent(pos, Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)); pump(0.2)
QApplication.sendEvent(qw, QDropEvent(QPointF(pos), Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)); pump(0.6)
check("dropping a program on the panel pins it", any(e.name == "Dropped App" for e in pins.items) and ctl.mode == "apps")
check("...and does not leak into the clipboard shelf", shelf.count == shelf_before)
md2 = QMimeData(); md2.setUrls([QUrl.fromLocalFile(str(txt))]); k = apps.count
QApplication.sendEvent(qw, QDragEnterEvent(pos, Qt.CopyAction, md2, Qt.LeftButton, Qt.NoModifier)); pump(0.2)
QApplication.sendEvent(qw, QDropEvent(QPointF(pos), Qt.CopyAction, md2, Qt.LeftButton, Qt.NoModifier)); pump(0.5)
check("dropping a text file is refused", apps.count == k and "Only programs" in apps.message)

click(text_pt("Reset"))
check("Reset restores the default apps", pins.items[0].name == "File Explorer" and not any(e.name == "Dropped App" for e in pins.items))
print(f"\n{sum(results)}/{len(results)} apps-panel interactions behaved")
sys.exit(0 if all(results) else 1)
