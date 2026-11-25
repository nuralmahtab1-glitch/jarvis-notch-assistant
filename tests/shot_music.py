"""Render the music card with realistic LONG text and save a picture (visual check, run manually)."""
import sys, time
sys.path.insert(0, ".")
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication
from shiboken6 import wrapInstance, getCppPointer
from app.ui.controller import NotchController
from app.ui.shelf_ctl import ShelfController
from app.ui.apps_ctl import AppsController
from app.core.apps import PinnedApps
from app.store.db import Settings
import tempfile
from pathlib import Path

app = QApplication([])
ctl = NotchController()
class Clip(QObject):
    dataChanged = Signal()
    def mimeData(self): return None
d = Path(tempfile.mkdtemp())
eng = QQmlApplicationEngine()
for k, v in (("notch", ctl), ("shelf", ShelfController(ctl, clipboard=Clip())), ("apps", AppsController(ctl, PinnedApps(Settings(d / "s.json"), {}, launcher=lambda t: None)))):
    eng.rootContext().setContextProperty(k, v)
eng.load(QUrl.fromLocalFile("app/ui/qml/Notch.qml"))
w = eng.rootObjects()[0]; qw = wrapInstance(getCppPointer(w)[0], QQuickWindow)
LONG = {"title": "Everything I Wanted (Live from the Roundhouse, London)", "artist": "Billie Eilish & Finneas O'Connell",
        "frac": 0.4, "lyrics": ["I had a dream, I got everything I wanted, not what you'd think",
                                "And I was fine, I was lost in a crowd of faces I'd never seen before",
                                "You said as much as you could never really stay with me"]}
which = sys.argv[2] if len(sys.argv) > 2 else "music"
if which == "todo":
    ctl.setTodo([{"id": 1, "text": "Email the landlord about the broken boiler and ask for a written repair date before the end of the month", "done": False},
                 {"id": 2, "text": "Pay the electricity bill", "done": True}])
    ctl.setMode("todo")
else:
    ctl.setMusic(LONG); ctl.setMode("music")
end = time.time() + 2.2
while time.time() < end: app.processEvents(); time.sleep(0.01)
qw.grabWindow().save(sys.argv[1] if len(sys.argv) > 1 else "shots/music_long.png")
print("saved")
