"""Live UI check: open the real Settings window and click its controls with simulated mouse clicks."""
import os as _os
_os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")      # independent of your real screen and mouse
_os.environ.setdefault("QT_QUICK_BACKEND", "software")

import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, ".")
from PySide6.QtCore import QPoint, QUrl, Qt, QTimer
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import wrapInstance, getCppPointer
from app.store.db import Settings, Store
from app.ui.controller import NotchController
from app.core.assistant import Assistant
from app.ui.settings_ctl import SettingsController

app = QApplication([])
d = Path(tempfile.mkdtemp()); cfg = Settings(d / "s.json"); store = Store(d / "t.db")
ctl = NotchController(); a = Assistant(ctl, cfg, store)
sc = SettingsController(a, ctl, cfg, store, ["Mic A"])
eng = QQmlApplicationEngine(); eng.rootContext().setContextProperty("sc", sc)
eng.load(QUrl.fromLocalFile("app/ui/qml/Settings.qml"))
w = eng.rootObjects()[0]; qw = wrapInstance(getCppPointer(w)[0], QQuickWindow)
results = []


def pump(s=0.5):
    end = time.time() + s
    while time.time() < end:
        app.processEvents(); time.sleep(0.01)


def find(item, text):
    """Find the first visible QML item whose `text`/`label` property equals text; return its centre in window coords."""
    from PySide6.QtQuick import QQuickItem
    stack = [qw.contentItem()]
    while stack:
        it = stack.pop()
        for prop in ("text", "label"):
            if it.property(prop) == text and it.isVisible():
                p = it.mapToScene(it.boundingRect().center())
                return QPoint(int(p.x()), int(p.y()))
        stack.extend(it.childItems())
    return None


def click(text):
    pt = find(qw, text)
    assert pt, f"could not find {text!r} on screen"
    QTest.mouseClick(qw, Qt.LeftButton, Qt.NoModifier, pt)
    pump(0.4)


def check(name, cond):
    results.append((name, bool(cond))); print(("PASS" if cond else "FAIL"), name)


pump(1.0)
# General page: Do not disturb is the 4th toggle; click via sidebar then locate by title row geometry
w.setProperty("page", 1); pump(0.5)
click("Always");   check("Voice > Speak replies > Always", cfg["speak_replies"] == "always")
click("Minimal");  check("Voice > Personality > Minimal", cfg["persona"] == "minimal" and a.persona.preset == "minimal")
click("Never");    check("Voice > Speak replies > Never", cfg["speak_replies"] == "off")
w.setProperty("page", 2); pump(0.5)
click("Fast");     check("Listening > Speech model > Fast", cfg["stt_model"] == "tiny.en" and sc.restartNeeded)
w.setProperty("page", 5); pump(0.5)
click("Erase...")
check("Privacy > Erase asks first (nothing erased yet)", find(qw, "Yes, erase") is not None)
store.todo_add("keep me?")
click("Cancel");   check("Privacy > Cancel keeps data", store.todo_list() != [] and find(qw, "Yes, erase") is None)
click("Erase..."); click("Yes, erase"); check("Privacy > Erase twice confirms and wipes", store.todo_list() == [])
click("Export");   check("Privacy > Export wrote a file", "Saved to" in sc.message)
w.setProperty("page", 3); pump(0.5)
check("AI brain page shows a status", find(qw, "Installed") is not None or find(qw, "Not installed") is not None)
ok = all(r for _, r in results)
print(f"\n{sum(r for _, r in results)}/{len(results)} UI interactions behaved")
sys.exit(0 if ok else 1)
