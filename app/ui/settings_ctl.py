"""Settings controller: validates, saves and live-applies every setting. Made by Nur Al Mahtab."""
from __future__ import annotations
import json, os, re, time
from pathlib import Path
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from app import config
from app.core.persona import PRESETS
from app.store.db import DEFAULT_SETTINGS

KEY_CHOICES = ["right ctrl", "right alt", "right shift", "f8", "f9"]
STT_CHOICES = ["tiny.en", "base.en", "small.en"]
PERSONAS = list(PRESETS)
SPEAK_CHOICES = ["off", "voice", "always"]

# settings that only take effect after Jarvis restarts
RESTART_KEYS = {"ptt_command_key", "ptt_dictate_key", "mic_device", "stt_model", "claude_bridge"}


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class SettingsController(QObject):
    changed = Signal()
    toast = Signal(str)

    def __init__(self, assistant, ctl, settings, store, mic_names: list[str] | None = None,
                 hooks: dict | None = None, installer=None):
        super().__init__()
        self.a, self.ctl, self.cfg, self.store = assistant, ctl, settings, store
        self.hooks = hooks or {}              # optional callbacks: wake(bool), lyrics(bool)
        self.installer = installer
        self._mics = ["Default microphone"] + (mic_names or [])
        self._restart = False
        self._msg = ""
        self._poll = QTimer(self)
        self._poll.setInterval(800)
        self._poll.timeout.connect(self.changed.emit)   # live brain-download progress
        self._poll.start()

    # ---------------- read side ----------------
    def _all(self) -> dict:
        d = dict(self.cfg.data)
        sp = d.get("claude_speak", {})
        d.update(speak_done=bool(sp.get("done")), speak_needs=bool(sp.get("needs_you")), speak_error=bool(sp.get("error")))
        return d

    values = Property("QVariantMap", _all, notify=changed)
    mics = Property("QStringList", lambda s: s._mics, constant=True)
    keyChoices = Property("QStringList", lambda s: KEY_CHOICES, constant=True)
    sttChoices = Property("QStringList", lambda s: STT_CHOICES, constant=True)
    personas = Property("QStringList", lambda s: PERSONAS, constant=True)
    speakChoices = Property("QStringList", lambda s: SPEAK_CHOICES, constant=True)
    appName = Property(str, lambda s: config.APP_NAME, constant=True)
    version = Property(str, lambda s: config.VERSION, constant=True)
    credit = Property(str, lambda s: config.CREDIT, constant=True)
    restartNeeded = Property(bool, lambda s: s._restart, notify=changed)
    message = Property(str, lambda s: s._msg, notify=changed)

    @Property(str, notify=changed)
    def brainStatus(self) -> str:
        from app.llm import manager
        if self.cfg["llm_provider"] != "local":
            from app.llm.cloud import CloudBackend
            from app.winio import credstore
            cb = CloudBackend(lambda: self.cfg["llm_provider"], lambda: self.cfg["cloud_model"], lambda: self.cfg["cloud_base"], credstore.load)
            if cb.installed():
                return "Cloud ready"
            return "Needs a web address and key" if self.cfg["llm_provider"] == "custom" and not self.cfg["cloud_base"] else "Needs an API key"
        mid = self.cfg["llm_model"]
        dl = getattr(self.a, "brain_dl", {"id": None, "state": "", "pct": 0})
        if dl["id"] == mid and dl["state"] == "downloading":
            return f"Downloading {dl['pct']}%"
        if manager.is_installed(mid) and manager.server_binary():
            return "Installed"
        return "Not installed"

    @Property("QVariantList", notify=changed)
    def brainModels(self):
        from app.llm import manager
        return [{"id": m["id"], "name": f"{m['name']} ({m['size_gb']} GB)", "installed": manager.is_installed(m["id"])}
                for m in manager.all_models()]

    @Property(bool, notify=changed)
    def claudeConnected(self) -> bool:
        return bool(self.installer and self.installer.is_connected())

    # ---------------- write side ----------------
    def _say(self, msg: str):
        self._msg = msg
        self.toast.emit(msg)
        self.changed.emit()

    @Slot(str, "QVariant")
    def set(self, key: str, value):
        """Validate, save and apply one setting. Unknown keys are ignored."""
        if key not in DEFAULT_SETTINGS and key not in ("speak_done", "speak_needs", "speak_error"):
            return
        value = self._validate(key, value)
        if value is None:
            return
        if key in ("speak_done", "speak_needs", "speak_error"):
            sp = dict(self.cfg["claude_speak"])
            sp[{"speak_done": "done", "speak_needs": "needs_you", "speak_error": "error"}[key]] = bool(value)
            self.cfg.set("claude_speak", sp)
        else:
            self.cfg.set(key, value)
        self._apply(key, value)
        if key in RESTART_KEYS:
            self._restart = True
        self.changed.emit()

    def _validate(self, key, v):
        try:
            if key in ("wake_word", "dnd", "greeting", "claude_bridge", "claude_hide_details",
                       "claude_quiet_when_focused", "claude_web", "lyrics", "shelf_enabled", "autohide", "awake_display", "awake_claude", "awake_focus", "speak_done", "speak_needs", "speak_error"):
                return bool(v)
            if key == "address":
                v = str(v).strip()[:40]
                return v or None
            if key == "speak_replies":
                return v if v in SPEAK_CHOICES else None
            if key == "persona":
                return v if v in PERSONAS else None
            if key == "voice_speed":
                return round(clamp(float(v), 0.8, 1.4), 2)
            if key == "sleep_after_minutes":
                return int(clamp(int(float(v)), 1, 120))
            if key == "autohide_seconds":
                return int(clamp(int(float(v)), 2, 120))
            if key == "claude_approval_timeout":
                return int(clamp(int(float(v)), 5, 120))
            if key in ("ptt_command_key", "ptt_dictate_key"):
                if v not in KEY_CHOICES:
                    return None
                other = self.cfg["ptt_dictate_key" if key == "ptt_command_key" else "ptt_command_key"]
                if v == other:
                    self._say("Command and Dictate need two different keys.")
                    return None
                return v
            if key == "weather_units":
                return v if v in ("C", "F") else None
            if key == "clocks":
                from app.core.widgets import parse_clocks
                raw = [p.strip() for p in (v.split(",") if isinstance(v, str) else list(v)) if p.strip()]
                good = parse_clocks(raw)
                if raw and not good:
                    self._say("I did not recognise those places. Use the form London=Europe/London.")
                    return None
                return [f"{a}={b}" for a, b in good]
            if key == "stt_model":
                return v if v in STT_CHOICES else None
            if key == "llm_provider":
                from app.llm.cloud import ORDER
                return v if v in ORDER else None
            if key == "cloud_model":
                v = str(v).strip()
                return v if re.fullmatch(r"[\w.:/@+-]{0,80}", v) else None
            if key == "cloud_base":
                from app.llm.cloud import valid_base
                v = str(v).strip()
                if v and not valid_base(v):
                    self._say("The address must start with https:// (or http://localhost).")
                    return None
                return v
            if key == "llm_model":
                from app.llm import manager
                return v if any(m["id"] == v for m in manager.all_models()) else None
            if key == "mic_device":
                return str(v) if str(v) in self._mics else None
            if key == "websites":
                from app.ui.prompter_ctl import clean_sites
                raw = [p.strip() for p in (v.split(",") if isinstance(v, str) else list(v)) if p.strip()]
                good = clean_sites(raw)
                if raw and not good:
                    self._say("Those do not look like website addresses. Use something like youtube.com.")
                    return None
                return good
        except (TypeError, ValueError):
            return None
        return v

    def _apply(self, key, v):
        a = self.a
        if key == "address":
            a.persona.name = v
            if a.brain:
                a.brain.name = v
        elif key == "persona":
            a.persona.preset = v
        elif key == "voice_speed" and a.speaker:
            a.speaker.speed = v
        elif key == "autohide":
            self.ctl.autohide = bool(v)
            self.ctl.wake()
        elif key == "autohide_seconds":
            self.ctl.autohide_after = float(v)
        elif key == "sleep_after_minutes" and not os.environ.get("JARVIS_SLEEP_SECONDS"):
            self.ctl._sleep_after = v * 60
        elif key == "dnd":
            a.set_dnd(v)
        elif key == "claude_hide_details" and a.tracker:
            a.tracker.hide_details = v
        elif key == "claude_approval_timeout" and a.tracker:
            a.tracker.approval_timeout = v
        elif key == "claude_quiet_when_focused" and a.tracker:
            a.tracker.quiet_when_focused = v
        elif key == "wake_word" and "wake" in self.hooks:
            self.hooks["wake"](v)
        elif key == "lyrics" and "lyrics" in self.hooks:
            self.hooks["lyrics"](v)
        elif key == "awake_display" and a.awake.active:
            a.set_keep_awake(True, display=v, minutes=a.awake.remaining() / 60 if a.awake.remaining() else None)
        elif key == "claude_web" and "web" in self.hooks:
            self.hooks["web"](v)
        elif key == "weather_units" and "units" in self.hooks:
            self.hooks["units"]()
        elif key == "shelf_enabled" and "shelf" in self.hooks:
            self.hooks["shelf"](v)
        elif key == "llm_model" and a.local:
            a.local.stop()                       # next question loads the newly chosen model

    # ---------------- actions ----------------
    @Slot(bool)
    def setAutostart(self, on: bool):
        from app.winio import autostart
        try:
            autostart.set_enabled(on)
        except OSError as e:
            self._say(f"Could not change startup: {e}")

    @Slot(result=bool)
    def autostartOn(self) -> bool:
        from app.winio import autostart
        return autostart.is_enabled()

    @Slot()
    def previewVoice(self):
        if self.a.speaker:
            self.a.speaker.speak(self.a.persona.greeting(time.localtime().tm_hour))

    @Slot()
    def connectClaude(self):
        if not self.installer:
            return
        try:
            b = self.installer.connect()
            self._say("Claude Code connected." + (f" Backup saved as {b.name}." if b else ""))
        except Exception as e:
            self._say(f"Could not connect: {e}")

    @Slot()
    def disconnectClaude(self):
        if not self.installer:
            return
        try:
            self.installer.disconnect()
            self._say("Claude Code disconnected. Your other hooks were left alone.")
        except Exception as e:
            self._say(f"Could not disconnect: {e}")

    @Slot()
    def downloadBrain(self):
        self.a.install_brain(self.cfg["llm_model"])
        self.changed.emit()

    @Slot()
    def removeBrain(self):
        from app.llm import manager
        if self.a.local:
            self.a.local.stop()
        manager.remove(self.cfg["llm_model"])
        self._say("AI brain removed. Commands still work without it.")

    @Slot(result=str)
    def exportData(self) -> str:
        """Write everything Jarvis keeps about you (settings, list, reminders) to a readable JSON file."""
        data = {"exported": time.strftime("%Y-%m-%d %H:%M:%S"), "settings": self.cfg.data,
                "todos": self.store.todo_list(), "reminders": self.store.reminders_pending()}
        folder = Path.home() / "Documents"
        folder.mkdir(exist_ok=True)
        path = folder / time.strftime("Jarvis-export-%Y%m%d-%H%M%S.json")
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        self._say(f"Saved to {path}")
        return str(path)

    @Slot(str)
    def setWeatherCity(self, city: str):
        """Save the city you typed and look it up (only the name is sent)."""
        self.cfg.set("weather_city", city.strip())
        if "weather_city" in self.hooks:
            self.hooks["weather_city"](city.strip())
        self._say(f"Looking up {city.strip()}..." if city.strip() else "Weather turned off.")

    @Property(str, notify=changed)
    def pairCode(self) -> str:
        """The code you paste into the browser extension (created the first time it is needed)."""
        from app.claude_bridge.web import new_pair_code
        if not self.cfg["web_pair_code"]:
            self.cfg.set("web_pair_code", new_pair_code())
        return self.cfg["web_pair_code"]

    @Slot()
    def regenPairCode(self):
        """A new code: the old one stops working, so a browser you no longer trust is locked out."""
        from app.claude_bridge.web import new_pair_code
        self.cfg.set("web_pair_code", new_pair_code())
        self._say("New pairing code created. Paste it into the extension again.")

    # ---------------- cloud brain (ChatGPT / Gemini / Claude / other) ----------------
    @Property("QVariantList", constant=True)
    def providers(self):
        from app.llm.cloud import ORDER, PROVIDERS
        return [{"id": p, "label": "This PC" if p == "local" else PROVIDERS[p]["label"]} for p in ORDER]

    @Property(str, notify=changed)
    def cloudNote(self) -> str:
        if self.cfg["llm_provider"] == "local":
            return "This PC is private and free but slower. A cloud service is much smarter, but your questions are sent to it."
        return "Only your questions and the last few replies are sent, never your screen, files or clipboard. Simple commands stay on this PC."

    @Property(str, notify=changed)
    def cloudModelHint(self) -> str:
        from app.llm.cloud import PROVIDERS
        return PROVIDERS.get(self.cfg["llm_provider"], {}).get("model", "")

    @Property(str, notify=changed)
    def cloudKeysUrl(self) -> str:
        from app.llm.cloud import PROVIDERS
        return PROVIDERS.get(self.cfg["llm_provider"], {}).get("keys", "")

    @Property(bool, notify=changed)
    def cloudHasKey(self) -> bool:
        from app.winio import credstore
        p = self.cfg["llm_provider"]
        return p != "local" and bool(credstore.load(p))

    @Slot(str)
    def saveApiKey(self, key: str):
        """Store the key in the Windows Credential Manager for the chosen provider."""
        from app.llm.cloud import valid_key
        from app.winio import credstore
        p = self.cfg["llm_provider"]
        if p == "local":
            return
        key = key.strip()
        if not valid_key(key):
            self._say("That does not look like an API key (no spaces, at least 8 characters).")
            return
        self._say("Key saved securely in Windows." if credstore.save(p, key) else "Windows would not store the key.")

    @Slot()
    def removeApiKey(self):
        from app.winio import credstore
        credstore.delete(self.cfg["llm_provider"])
        self._say("Key removed.")

    @Slot()
    def testCloud(self):
        """Ask the service one tiny question in the background and report the result."""
        import threading
        from app.llm.cloud import CloudBackend
        from app.winio import credstore
        cb = CloudBackend(lambda: self.cfg["llm_provider"], lambda: self.cfg["cloud_model"], lambda: self.cfg["cloud_base"], credstore.load)
        if self.cfg["llm_provider"] == "local":
            self._say("Pick a cloud service first.")
            return
        if not cb.installed():
            self._say("Save an API key first (and a web address if you chose Other).")
            return
        self._say("Testing...")

        def work():
            err = cb.test()
            self.a.ui(lambda: self._say("Connected. The cloud brain works." if not err else err))
        threading.Thread(target=work, daemon=True).start()

    @Slot()
    def resetNotchPosition(self):
        self.ctl.resetPosition()
        self._say("Jarvis is back in the middle.")

    @Slot(str)
    def importModel(self, path: str):
        """Add a .gguf model you already have. It is copied into Jarvis's own folder and selected."""
        from app.llm import manager
        try:
            rec = manager.import_gguf(path)
        except (ValueError, OSError) as e:
            self._say(str(e) if isinstance(e, ValueError) else "Could not copy that file.")
            return
        self.cfg.set("llm_model", rec["id"])
        if self.a.local:
            self.a.local.stop()
        self._say(f"Imported {rec['name']} and selected it.")

    @Slot()
    def openPowerSettings(self):
        from app.winio import controls
        controls.open_settings_page("power")

    @Slot()
    def clearShelf(self):
        if "shelf_clear" in self.hooks:
            self.hooks["shelf_clear"]()
        self._say("Shelf cleared.")

    @Slot()
    def wipeData(self):
        self.store.wipe()
        self.a.refresh_todo()
        self._say("Your list, reminders and shelf were erased. Settings were kept.")

    @Slot()
    def resetSettings(self):
        for k, v in DEFAULT_SETTINGS.items():
            if k != "onboarded":
                self.cfg.data[k] = v if not isinstance(v, (dict, list)) else json.loads(json.dumps(v))
        self.cfg.save()
        self._apply("persona", self.cfg["persona"])
        self._apply("voice_speed", self.cfg["voice_speed"])
        self._apply("dnd", self.cfg["dnd"])
        self._restart = True
        self._say("Settings were reset to their defaults.")

    @Slot()
    def openFolder(self):
        from app.store.db import data_dir
        try:
            os.startfile(str(data_dir()))
        except OSError as e:
            self._say(f"Could not open the folder: {e}")

    @Slot()
    def clearMessage(self):
        self._msg = ""
        self.changed.emit()
