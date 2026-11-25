"""Live UI check: click the real Controls panel with simulated mouse clicks.
All hardware calls are replaced by recorders, so nothing here touches your radios, volume or brightness."""
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, ".")
from PySide6.QtCore import QPoint, QUrl, Qt
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import wrapInstance, getCppPointer
from app.store.db import Settings, Store
from app.ui.controller import NotchController
from app.core.assistant import Assistant
import app.core.assistant as mod

sys.path.insert(0, "tests")
from test_controls import FakeQS      # the same stand-in backend the unit tests use

app = QApplication([])
vol, bri, shots = [], [], []
mod.win.set_volume = lambda v: vol.append(v) or v
mod.win.set_brightness = lambda v: bri.append(v) or True
mod.win.toggle_mute = lambda: True
mod.win.screenshot = lambda: shots.append(1) or "x.png"
mod.win.get_volume = lambda: 40
mod.win.is_muted = lambda: False
mod.win.get_brightness = lambda: 60
mod.win.battery = lambda: (77, True)
d = Path(tempfile.mkdtemp())
ctl = NotchController(); a = Assistant(ctl, Settings(d / "s.json"), Store(d / "t.db")); a.qs = FakeQS()
eng = QQmlApplicationEngine(); eng.rootContext().setContextProperty("notch", ctl)
from app.ui.shelf_ctl import ShelfController
from PySide6.QtCore import QObject, Signal
class _Clip(QObject):
    dataChanged = Signal()
    def mimeData(self): return None
shelf = ShelfController(ctl, clipboard=_Clip()); eng.rootContext().setContextProperty("shelf", shelf)
from app.core.apps import PinnedApps
from app.ui.apps_ctl import AppsController
from app.store.db import Settings as _Set
import tempfile as _tf
_pins = PinnedApps(_Set(__import__("pathlib").Path(_tf.mkdtemp()) / "a.json"), {}, launcher=lambda t: None)
eng.rootContext().setContextProperty("apps", AppsController(ctl, _pins))
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


def click_text(text):
    pt = centre(lambda it: it.property("text") == text or it.property("label") == text)
    assert pt, f"could not find {text!r}"
    QTest.mouseClick(qw, Qt.LeftButton, Qt.NoModifier, pt); pump(0.5)


def check(name, cond):
    results.append(bool(cond)); print(("PASS" if cond else "FAIL"), name)


a.open_controls(); pump(1.5)
check("panel opened with real battery/volume/brightness numbers",
      ctl.mode == "controls" and ctl.controls["battery"] == 77 and ctl.controls["volume"] == 40)
click_text("Wi-Fi");        check("click Wi-Fi tile -> radio switched off via Windows API", ("radio", "wifi", False) in a.qs.calls)
click_text("Bluetooth");    check("click Bluetooth tile -> radio switched off", ("radio", "bluetooth", False) in a.qs.calls)
click_text("Airplane");     check("click Airplane tile -> airplane mode toggled", any(c[0] == "airplane" for c in a.qs.calls))
click_text("Night light");  check("Night light tile opens its Windows page (no fake toggle)", ("page", "nightlight") in a.qs.calls)
click_text("Accessibility");check("Accessibility tile opens its Windows page", ("page", "accessibility") in a.qs.calls)
click_text("Performance");  check("click Performance -> power mode set", ("power", "performance") in a.qs.calls)

# drag the volume slider to ~75 % and the brightness slider to ~20 %
def slider(name):
    for it in walk():
        if it.isVisible() and it.property("name") == name and it.property("commitOnRelease") is not None:
            return it
vs = slider("volume"); p = vs.mapToScene(vs.boundingRect().topLeft())
QTest.mouseClick(qw, Qt.LeftButton, Qt.NoModifier, QPoint(int(p.x() + 0.75 * vs.width()), int(p.y() + vs.height() / 2))); pump(0.4)
check("click volume slider at 75% -> volume set live", vol and 70 <= vol[-1] <= 80)
bs = slider("brightness"); p = bs.mapToScene(bs.boundingRect().topLeft())
QTest.mouseClick(qw, Qt.LeftButton, Qt.NoModifier, QPoint(int(p.x() + 0.2 * bs.width()), int(p.y() + bs.height() / 2))); pump(0.6)
check("click brightness slider at 20% -> brightness applied on release", bri and 15 <= bri[-1] <= 25)

click_text("  Screenshot")
check("click Screenshot -> screenshot taken and confirmed on the panel", shots == [1] and "Screenshot saved" in ctl.controls["msg"])

# the click shield / panel stays open and does not collapse while you use it
pump(1.0); check("panel stays open while in use", ctl.mode == "controls")
ok = all(results)
print(f"\n{sum(results)}/{len(results)} panel interactions behaved")
sys.exit(0 if ok else 1)
