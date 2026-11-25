"""WidgetsController: data for the Widgets panel (clocks, weather, battery, tasks, next reminder). Made by Nur Al Mahtab."""
from __future__ import annotations
import threading, time
from datetime import datetime
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from app.core import widgets as W

WEATHER_TTL = 20 * 60          # do not hit the weather service more than once per 20 minutes


class WidgetsController(QObject):
    changed = Signal()
    _weather_ready = Signal(object, str)        # (Weather | None, status message): worker thread -> UI thread
    _geo_ready = Signal(object, str)            # (place dict | None, what you typed)
    _voice_ready = Signal(object, str)          # (callback, sentence)

    def __init__(self, settings, store, battery=lambda: (None, False), geocode=W.geocode, fetch=W.fetch_weather):
        super().__init__()
        self.cfg, self.store = settings, store
        self._battery, self._geocode, self._fetch = battery, geocode, fetch
        self._weather: W.Weather | None = None
        self._status = ""
        self._fetched_at = 0.0
        self._busy = False
        self._weather_ready.connect(self._on_weather)
        self._geo_ready.connect(self._on_geo)
        self._voice_ready.connect(lambda cb, sentence: cb(sentence))
        self._tick = QTimer(self); self._tick.setInterval(15000); self._tick.timeout.connect(self.changed.emit); self._tick.start()

    # ---------------- what the panel shows ----------------
    @Property("QVariantList", notify=changed)
    def clocks(self):
        return W.clock_rows(W.parse_clocks(self.cfg["clocks"]))

    @Property("QVariantMap", notify=changed)
    def weather(self):
        if not self.cfg["weather_place"]:
            return {"ok": False, "status": self._status or "Set your city in Settings to see the weather."}
        if not self._weather:
            return {"ok": False, "status": self._status or "Checking the weather..."}
        w = self._weather
        return {"ok": True, "temp": w.temp, "text": w.text, "glyph": w.glyph, "high": w.high, "low": w.low,
                "unit": w.unit, "place": w.place, "night": w.night, "status": ""}

    @Property(int, notify=changed)
    def battery(self):
        pct, _ = self._battery()
        return -1 if pct is None else int(pct)

    @Property(bool, notify=changed)
    def plugged(self):
        return bool(self._battery()[1])

    @Property(int, notify=changed)
    def tasksLeft(self):
        return sum(1 for t in self.store.todo_list() if not t["done"])

    @Property(str, notify=changed)
    def nextReminder(self):
        pend = self.store.reminders_pending()
        if not pend:
            return ""
        r = pend[0]
        return f"{r['text']} at {datetime.fromtimestamp(r['due']).strftime('%I:%M %p').lstrip('0')}"

    # ---------------- weather ----------------
    @Slot()
    def opened(self):
        self.refresh()
        self.changed.emit()

    def _settings_tuple(self):
        c = self.cfg
        return c["weather_lat"], c["weather_lon"], c["weather_place"], c["weather_units"]

    def refresh(self, force: bool = False):
        if not self.cfg["weather_place"] or self._busy:
            return
        if not force and self._weather and time.time() - self._fetched_at < WEATHER_TTL:
            return
        self._busy = True
        args = self._settings_tuple()

        def work():
            w = self._fetch(*args)
            self._weather_ready.emit(w, "" if w else "Could not reach the weather service.")
        threading.Thread(target=work, daemon=True).start()

    def _on_weather(self, w, status):
        self._busy = False
        if w:
            self._weather, self._fetched_at = w, time.time()
        self._status = status
        self.changed.emit()

    def set_city(self, city: str):
        """Look the city up (only the name is sent), save it, then fetch its weather."""
        city = (city or "").strip()
        if not city:
            self.cfg.set("weather_place", "")
            self._weather = None
            self.changed.emit()
            return
        threading.Thread(target=lambda: self._geo_ready.emit(self._geocode(city), city), daemon=True).start()

    def _on_geo(self, hit, typed):
        if not hit:
            self._status = f"I could not find a place called {typed}."
            self.changed.emit()
            return
        self.cfg.set("weather_lat", hit["lat"]); self.cfg.set("weather_lon", hit["lon"]); self.cfg.set("weather_place", hit["name"])
        self._weather, self._status = None, ""
        self.refresh(force=True)
        self.changed.emit()

    def units_changed(self):
        self._weather = None
        self.refresh(force=True)
        self.changed.emit()

    def weather_async(self, callback):
        """Voice: call callback(sentence) from the UI thread, using the cache when it is fresh."""
        if not self.cfg["weather_place"]:
            callback("Tell me your city in Settings first, and I can check the weather.")
            return
        if self._weather and time.time() - self._fetched_at < WEATHER_TTL:
            callback(self._weather.sentence())
            return
        args = self._settings_tuple()

        def work():
            w = self._fetch(*args)
            self._weather_ready.emit(w, "" if w else "Could not reach the weather service.")
            self._voice_ready.emit(callback, w.sentence() if w else "I could not reach the weather service just now.")
        threading.Thread(target=work, daemon=True).start()
