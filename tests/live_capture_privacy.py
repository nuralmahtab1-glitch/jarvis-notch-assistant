"""Live check (real Windows, no screen needed): does the notch really get excluded from screen capture while the
teleprompter shows? Asks Windows itself for the window's display-affinity afterwards. Run manually."""
import ctypes, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, ".")
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication
from shiboken6 import wrapInstance, getCppPointer
from app.ui.controller import NotchController
from app.core.apps import PinnedApps
from app.store.db import Settings, Store
from app.ui.apps_ctl import AppsController
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
w = eng.rootObjects()[0]
hwnd = int(w.winId())
get = ctypes.windll.user32.GetWindowDisplayAffinity
val = ctypes.c_uint()


def affinity():
    get(hwnd, ctypes.byref(val)); return val.value


def pump(s):
    end = time.time() + s
    while time.time() < end: app.processEvents(); time.sleep(0.01)


# the same logic main.py uses
state = {"on": None}
def sync():
    want = ctl.mode == "prompter"
    if want != state["on"]:
        state["on"] = want
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11 if want else 0)
ctl.changed.connect(sync)

pump(0.5); before = affinity()
ctl.setMode("prompter"); pump(0.5); during = affinity()
ctl.setMode("idle"); pump(0.5); after = affinity()
print(f"display affinity: normal={before:#x}  while teleprompter={during:#x} (0x11 = excluded from capture)  after={after:#x}")
ok = before == 0 and during == 0x11 and after == 0
print("PASS" if ok else "FAIL", "- notch is hidden from screen capture only while the teleprompter is showing")
sys.exit(0 if ok else 1)
