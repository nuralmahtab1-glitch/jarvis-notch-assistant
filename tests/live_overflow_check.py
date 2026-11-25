"""Live visual regression check: feed every text-heavy notch state absurdly long text and verify that NOTHING is
drawn outside the notch's box (the window is transparent, so any pixel outside the body means text overflowed)."""
import os as _os
_os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_os.environ.setdefault("QT_QUICK_BACKEND", "software")
_os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, ".")
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication
from shiboken6 import wrapInstance, getCppPointer
from app.core.apps import AppEntry, PinnedApps
from app.store.db import Settings
from app.ui.apps_ctl import AppsController
from app.ui.controller import SIZES, NotchController
from app.ui.shelf_ctl import ShelfController

app = QApplication([])
ctl = NotchController()
d = Path(tempfile.mkdtemp())


class Clip(QObject):
    dataChanged = Signal()
    def mimeData(self): return None


shelf = ShelfController(ctl, clipboard=Clip())
pins = PinnedApps(Settings(d / "s.json"), {}, launcher=lambda t: None)
apps = AppsController(ctl, pins)
eng = QQmlApplicationEngine()
for k, v in (("notch", ctl), ("shelf", shelf), ("apps", apps)):
    eng.rootContext().setContextProperty(k, v)
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

LONG = "This is an extremely long piece of text that goes on and on far beyond anything that could ever fit in the notch " * 2
LONG_NOSPACE = "Supercalifragilisticexpialidocious" * 8
ctl.setMusic({"title": LONG, "artist": LONG, "frac": 0.5, "lyrics": [LONG, LONG, LONG_NOSPACE]})
ctl.setTodo([{"id": 1, "text": LONG, "done": False}, {"id": 2, "text": LONG_NOSPACE, "done": True}, {"id": 3, "text": LONG, "done": False}])
shelf.shelf.add_text(LONG); shelf.shelf.add_text(LONG_NOSPACE); shelf.changed.emit()
pins.items = [AppEntry(LONG_NOSPACE, "x"), AppEntry(LONG, "y")] * 4
apps.changed.emit()

from app.core.prompter import Prompter as _Pr
_pc_keepalive.p = _Pr((LONG_NOSPACE + " " + LONG) * 3, 140); _pc_keepalive.p.words_done = 3
CASES = [("menu", None), ("prompter", None), ("widgets", None), ("music", None), ("todo", None), ("shelf", None), ("apps", None), ("answer", (LONG, LONG)), ("confirm", (LONG, LONG)),
         ("reminder", (LONG, LONG)), ("claudeNeeds", (LONG, LONG)), ("claudeDone", (LONG, LONG)), ("claudeWorking", (LONG, LONG)),
         ("claudeError", (LONG, LONG)), ("hearing", (LONG, "")), ("speaking", (LONG, "")), ("working", (LONG, "")),
         ("done", (LONG, "")), ("listening", (LONG, "")), ("volume", (LONG, "")), ("expanded", (LONG, LONG))]


def pump(s):
    end = time.time() + s
    while time.time() < end:
        app.processEvents(); time.sleep(0.01)


bad = []
for mode, text in CASES:
    ctl.setMode("idle"); pump(0.5)
    ctl.setMode(mode)
    if text:
        ctl.setText(*text)
    pump(2.0)
    img = qw.grabWindow()
    dpr = img.devicePixelRatio() if img.devicePixelRatio() > 1 else img.width() / w.width()
    bw, bh = SIZES[mode]
    x0 = (w.width() - bw) / 2
    margin = 3                                                             # logical px of tolerance for anti-aliasing
    left, right = int((x0 - margin) * dpr), int((x0 + bw + margin) * dpr)
    bottom = int((bh + margin + 4) * dpr)                                  # +4: the spring overshoot settles by now
    stray = 0
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            if (x < left or x > right or y > bottom) and (img.pixelColor(x, y).alpha() > 8):
                stray += 1
    # ...and the box itself must really be drawn (otherwise "nothing outside" would pass for a blank window)
    filled = total = 0
    for y in range(int(6 * dpr), int((bh - 6) * dpr), 3):
        for x in range(int((x0 + 30) * dpr), int((x0 + bw - 30) * dpr), 3):
            total += 1
            filled += img.pixelColor(x, y).alpha() > 200
    drawn = filled / max(1, total)
    ok = stray == 0 and drawn > 0.6
    print(("PASS" if ok else "FAIL"), f"{mode:14s}", f"box {drawn:.0%} filled" + ("" if stray == 0 else f", {stray} stray pixels outside the box"))
    if not ok:
        bad.append(mode)
print(f"\n{len(CASES) - len(bad)}/{len(CASES)} states keep long text inside the box" + (f"   OVERFLOW IN: {bad}" if bad else ""))
sys.exit(1 if bad else 0)
