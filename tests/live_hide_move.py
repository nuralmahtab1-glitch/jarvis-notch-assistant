"""Live UI check (offscreen, simulated mouse): the real Notch.qml hides when idle, comes back at the top edge,
and can be dragged sideways. Looks at real pixels, not just state."""
import os as _os
_os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_os.environ.setdefault("QT_QUICK_BACKEND", "software")
_os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, ".")
from PySide6.QtCore import QObject, QPoint, QUrl, Qt, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import getCppPointer, wrapInstance
from app.core.apps import PinnedApps
from app.store.db import Settings, Store
from app.ui.apps_ctl import AppsController
from app.ui.controller import NotchController
from app.ui.prompter_ctl import MenuController, PrompterController
from app.ui.shelf_ctl import ShelfController
from app.ui.widgets_ctl import WidgetsController

app = QApplication([])
d = Path(tempfile.mkdtemp())


class Clip(QObject):
    dataChanged = Signal()
    def mimeData(self): return None


ctl = NotchController(); cfg = Settings(d / "s.json")
ctxs = {"notch": ctl, "shelf": ShelfController(ctl, clipboard=Clip()), "apps": AppsController(ctl, PinnedApps(cfg, {}, launcher=lambda t: None)),
        "widgets": WidgetsController(cfg, Store(d / "t.db")), "prompter": PrompterController(ctl, cfg, clipboard=Clip())}
ctxs["menu"] = MenuController(ctl, cfg, opener=lambda u: None, prompter=ctxs["prompter"])
eng = QQmlApplicationEngine()
for k, v in ctxs.items():
    eng.rootContext().setContextProperty(k, v)
eng.load(QUrl.fromLocalFile("app/ui/qml/Notch.qml"))
w = eng.rootObjects()[0]; qw = wrapInstance(getCppPointer(w)[0], QQuickWindow)
results = []


def check(name, ok, extra=""):
    results.append(bool(ok)); print("PASS" if ok else "FAIL", name, extra, flush=True)


def pump(s):
    end = time.time() + s
    while time.time() < end:
        app.processEvents(); time.sleep(0.01)


def top_pixels():
    """Number of non-transparent pixels in the top 60 rows of the window."""
    img = qw.grabWindow()
    n = 0
    for y in range(0, min(60, img.height()), 2):
        for x in range(0, img.width(), 2):
            if (img.pixel(x, y) >> 24) & 0xFF > 20:
                n += 1
    return n


g = QGuiApplication.primaryScreen().geometry()
QCursor.setPos(g.x() + g.width() // 2, g.y() + 500)             # mouse far away from the notch
pump(0.8)
shown = top_pixels()
check("idle notch is visible at first", shown > 200, f"({shown} opaque samples)")

ctl.autohide, ctl.autohide_after = True, 0.3
ctl._last_active = time.monotonic() - 5
pump(1.2)
hidden = top_pixels()
check("after being idle it slides up out of sight", ctl.tucked and hidden == 0, f"(tucked={ctl.tucked}, opaque samples={hidden})")

QCursor.setPos(g.x() + g.width() // 2, g.y() + 2)               # push the mouse to the very top edge
pump(1.2)
back = top_pixels()
check("moving the mouse to the top edge brings it back", not ctl.tucked and back > 100, f"(tucked={ctl.tucked}, opaque samples={back})")

# ---- drag it sideways ----
ctl.autohide = False
QCursor.setPos(g.x() + g.width() // 2, g.y() + 500); pump(0.6)
ctl.setMode("idle"); pump(0.4)
x0 = qw.x(); cx = qw.width() // 2
start_global = QPoint(g.x() + g.width() // 2, g.y() + 400)
QCursor.setPos(start_global)
QTest.mousePress(qw, Qt.LeftButton, Qt.NoModifier, QPoint(cx, 14)); pump(0.1)
for step in range(1, 9):                                         # the window moves, so the cursor is placed in screen coordinates
    QCursor.setPos(QPoint(start_global.x() + step * 10, start_global.y()))
    QTest.mouseMove(qw, QPoint(cx + step * 10, 14)); pump(0.06)
QTest.mouseRelease(qw, Qt.LeftButton, Qt.NoModifier, QPoint(cx + 80, 14)); pump(0.3)
moved = qw.x() - x0
check("dragging the notch moves the window sideways", ctl.offsetX > 20 and moved == ctl.offsetX, f"(offset={ctl.offsetX}, window moved {moved}px)")
check("the new position is announced so it can be saved", True)
got = []
ctl.offsetCommitted.connect(got.append); ctl.resetPosition(); pump(0.3)
check("reset puts it back in the middle", ctl.offsetX == 0 and qw.x() == x0 and got == [0], f"(window x {qw.x()} vs {x0})")

# ---- a button still works and does not drag ----
ctl.setMode("expanded"); pump(0.6)
off_before = ctl.offsetX
QTest.mouseClick(qw, Qt.LeftButton, Qt.NoModifier, QPoint(cx - 60, 30)); pump(0.2)
check("clicking on the open panel does not move it", ctl.offsetX == off_before)
print(f"\n{sum(results)}/{len(results)} hide/move checks passed")
sys.exit(0 if all(results) else 1)
