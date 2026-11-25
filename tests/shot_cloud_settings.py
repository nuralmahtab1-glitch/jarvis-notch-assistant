"""Screenshots of the AI brain page: This PC vs a cloud provider (offscreen; uses a temp config and a fake key store)."""
import os as _os
_os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_os.environ.setdefault("QT_QUICK_BACKEND", "software")
_os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, ".")
from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication
from shiboken6 import wrapInstance, getCppPointer
from app.core.assistant import Assistant
from app.store.db import Settings, Store
from app.ui.controller import NotchController
from app.ui.settings_ctl import SettingsController
from app.winio import credstore

vault = {}
credstore.save = lambda n, s, prefix="": vault.__setitem__(n, s) or True
credstore.load = lambda n, prefix="": vault.get(n, "")
app = QApplication([])
d = Path(tempfile.mkdtemp()); cfg = Settings(d / "s.json"); ctl = NotchController(); a = Assistant(ctl, cfg, Store(d / "t.db"))
sc = SettingsController(a, ctl, cfg, a.store, ["Mic A"])
eng = QQmlApplicationEngine(); eng.rootContext().setContextProperty("sc", sc)
eng.load(QUrl.fromLocalFile("app/ui/qml/Settings.qml"))
w = eng.rootObjects()[0]; qw = wrapInstance(getCppPointer(w)[0], QQuickWindow)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else d


def pump(s=0.4):
    end = time.time() + s
    while time.time() < end:
        app.processEvents(); time.sleep(0.01)


w.setProperty("page", 3); pump(0.8); qw.grabWindow().save(str(out / "brain_local.png"))
sc.set("llm_provider", "gemini"); pump(0.6); qw.grabWindow().save(str(out / "brain_gemini_nokey.png"))
sc.saveApiKey("AIzaSy-fake-key-for-screenshot"); pump(0.6); qw.grabWindow().save(str(out / "brain_gemini_key.png"))
sc.set("llm_provider", "custom"); pump(0.6); qw.grabWindow().save(str(out / "brain_custom.png"))
print("saved to", out)
