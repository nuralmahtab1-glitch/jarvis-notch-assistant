"""Onboarding controller: hardware check + saving the user's choices. Made by Nur Al Mahtab."""
from __future__ import annotations
import subprocess
from PySide6.QtCore import QObject, Property, Signal, Slot
from app import config
from app.store.db import Settings


def detect_hardware() -> dict:
    import psutil
    ram = round(psutil.virtual_memory().total / 1024 ** 3, 1)
    gpus = []
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-CimInstance Win32_VideoController).Name -join '|'"],
                             capture_output=True, text=True, timeout=10, creationflags=0x08000000).stdout.strip()
        gpus = [g for g in out.split("|") if g]
    except Exception:
        pass
    discrete = next((g for g in gpus if any(k in g.upper() for k in ("NVIDIA", "RADEON", "RTX", "GTX", "MX"))), None)
    return {"ram_gb": ram, "gpus": gpus, "gpu": discrete or (gpus[0] if gpus else "integrated graphics")}


def model_verdict(size_gb: float, hw: dict) -> str:
    free_for_model = hw["ram_gb"] - 4.0          # leave room for Windows and apps
    if size_gb > free_for_model:
        return "Too large for this PC"
    if size_gb > free_for_model * 0.5 or "NVIDIA" not in hw["gpu"].upper() and size_gb > 1.5:
        return "Will be slow on this PC"
    return "Best for this PC"


class Onboarding(QObject):
    changed = Signal()
    finished = Signal()

    def __init__(self, settings: Settings, speaker=None, claude_installer=None, mic_names=None, brain=None):
        super().__init__()
        self.brain = brain
        from PySide6.QtCore import QTimer
        self._poll = QTimer(self); self._poll.setInterval(700); self._poll.timeout.connect(self.changed.emit); self._poll.start()
        self.cfg, self.speaker, self.claude = settings, speaker, claude_installer
        self._hw = detect_hardware()
        self._mics = mic_names or ["Default microphone"]

    hardware = Property(str, lambda s: f"This PC has {s._hw['gpu']}", constant=True)
    ramText = Property(str, lambda s: f"{s._hw['ram_gb']} GB memory", constant=True)
    mics = Property("QStringList", lambda s: s._mics, constant=True)
    appName = Property(str, lambda s: config.APP_NAME, constant=True)
    wakePhrase = Property(str, lambda s: config.WAKE_PHRASE, constant=True)
    credit = Property(str, lambda s: config.CREDIT, constant=True)
    address = Property(str, lambda s: s.cfg["address"], notify=changed)
    wake = Property(bool, lambda s: bool(s.cfg["wake_word"]), notify=changed)
    claudeConnected = Property(bool, lambda s: bool(s.claude and s.claude.is_connected()), notify=changed)
    def _models(self):
        from app.llm import manager
        out = []
        for m in manager.CATALOG:
            dl = self.brain.brain_dl if self.brain else {"id": None, "state": "", "pct": 0}
            if manager.is_installed(m["id"]) and manager.server_binary():
                status = "Installed \u2713"
            elif dl["id"] == m["id"] and dl["state"] == "downloading":
                status = f"Downloading {dl['pct']}%"
            elif dl["id"] == m["id"] and dl["state"] == "error":
                status = "Failed - tap to retry"
            else:
                status = model_verdict(m["size_gb"], self._hw)
            out.append({"id": m["id"], "name": m["name"], "size": f"{m['size_gb']} GB", "status": status,
                        "tooBig": status == "Too large for this PC"})
        return out

    models = Property("QVariantList", _models, notify=changed)

    @Slot(str)
    def chooseModel(self, model_id: str):
        if self.brain and not any(m["tooBig"] for m in self._models() if m["id"] == model_id):
            self.cfg.set("llm_model", model_id)
            self.brain.install_brain(model_id)
            self.changed.emit()

    @Slot(str)
    def setAddress(self, name: str):
        if name.strip():
            self.cfg.set("address", name.strip())
            self.changed.emit()

    @Slot(bool)
    def setWake(self, on: bool):
        self.cfg.set("wake_word", on)

    @Slot(bool)
    def setAutostart(self, on: bool):
        try:
            from app.winio import autostart
            autostart.set_enabled(on)
        except Exception as e:
            print("[autostart]", e)

    @Slot(str)
    def preview(self, text: str):
        if self.speaker:
            self.speaker.speak(text.replace("{name}", self.cfg["address"]))

    @Slot()
    def connectClaude(self):
        if self.claude:
            try:
                self.claude.connect()
            except Exception as e:
                print("[claude connect]", e)
            self.changed.emit()

    @Slot()
    def finish(self):
        self.cfg.set("onboarded", True)
        self.finished.emit()
