import os, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from app.core import widgets as W
from app.core.assistant import Assistant
from app.store.db import Settings, Store
from app.tools.intents import parse
from app.ui.controller import NotchController
from app.ui.settings_ctl import SettingsController
from app.ui.widgets_ctl import WidgetsController


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def pump(qapp, s=0.4):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents(); time.sleep(0.005)


SUNNY = W.Weather(21, "Clear", "☀️", 24, 15, "C", "Dhaka, BD")


@pytest.fixture
def env(qapp, tmp_path):
    cfg = Settings(tmp_path / "s.json"); store = Store(tmp_path / "t.db")
    calls = {"fetch": [], "geo": []}
    def fetch(lat, lon, place, unit): calls["fetch"].append((lat, lon, place, unit)); return SUNNY
    def geo(city): calls["geo"].append(city); return {"name": "Dhaka, BD", "lat": 23.8, "lon": 90.4} if city.lower() == "dhaka" else None
    wc = WidgetsController(cfg, store, battery=lambda: (83, True), geocode=geo, fetch=fetch)
    return wc, cfg, store, calls


def test_panel_data_without_a_city_asks_you_to_set_one(env):
    wc, cfg, store, calls = env
    assert wc.weather["ok"] is False and "Settings" in wc.weather["status"]
    assert wc.battery == 83 and wc.plugged is True and len(wc.clocks) == 3 and wc.tasksLeft == 0


def test_tasks_and_next_reminder_come_from_the_real_store(env):
    wc, cfg, store, calls = env
    store.todo_add("buy milk"); store.todo_add("call bank"); store.todo_complete_match("buy milk")
    store.reminder_add("call dad", time.time() + 3600)
    assert wc.tasksLeft == 1 and wc.nextReminder.startswith("call dad at ")


def test_setting_a_city_geocodes_saves_and_fetches_weather(env, qapp):
    wc, cfg, store, calls = env
    wc.set_city("Dhaka"); pump(qapp, 0.6)
    assert calls["geo"] == ["Dhaka"] and cfg["weather_place"] == "Dhaka, BD" and cfg["weather_lat"] == 23.8
    assert calls["fetch"] and calls["fetch"][0][:3] == (23.8, 90.4, "Dhaka, BD")
    assert wc.weather["ok"] and wc.weather["temp"] == 21 and wc.weather["place"] == "Dhaka, BD"


def test_unknown_city_is_reported_and_nothing_is_saved(env, qapp):
    wc, cfg, store, calls = env
    wc.set_city("Zzyzx"); pump(qapp, 0.5)
    assert cfg["weather_place"] == "" and "could not find" in wc.weather["status"]


def test_weather_is_cached_between_opens(env, qapp):
    wc, cfg, store, calls = env
    cfg.set("weather_place", "Dhaka, BD"); cfg.set("weather_lat", 23.8); cfg.set("weather_lon", 90.4)
    wc.opened(); pump(qapp); wc.opened(); wc.opened(); pump(qapp)
    assert len(calls["fetch"]) == 1                                  # not one request per click


def test_changing_units_refetches_in_the_new_unit(env, qapp):
    wc, cfg, store, calls = env
    cfg.set("weather_place", "Dhaka, BD"); cfg.set("weather_lat", 23.8); cfg.set("weather_lon", 90.4)
    wc.opened(); pump(qapp)
    cfg.set("weather_units", "F"); wc.units_changed(); pump(qapp)
    assert calls["fetch"][-1][3] == "F"


def test_voice_weather_answers_from_cache_or_asks_for_a_city(env, qapp):
    wc, cfg, store, calls = env
    said = []
    wc.weather_async(said.append)
    assert "your city" in said[0]
    cfg.set("weather_place", "Dhaka, BD"); cfg.set("weather_lat", 23.8); cfg.set("weather_lon", 90.4)
    wc.weather_async(said.append); pump(qapp, 0.6)
    assert "21 degrees" in said[1] and "Dhaka" in said[1]
    n = len(calls["fetch"]); wc.weather_async(said.append)
    assert len(calls["fetch"]) == n and "21 degrees" in said[2]      # fresh cache: instant, no new request


def test_weather_failure_is_spoken_not_raised(qapp, tmp_path):
    cfg = Settings(tmp_path / "s.json"); cfg.set("weather_place", "X"); cfg.set("weather_lat", 1.0); cfg.set("weather_lon", 2.0)
    wc = WidgetsController(cfg, Store(tmp_path / "t.db"), fetch=lambda *a: None)
    said = []; wc.weather_async(said.append)
    import time
    end = time.time() + 5                       # wait for the result instead of a fixed pause (a busy PC is slower)
    while not said and time.time() < end:
        pump(qapp, 0.05)
    assert said and "could not reach" in said[0]


# ---------------- settings validation ----------------
@pytest.fixture
def sc(env, qapp, tmp_path):
    wc, cfg, store, calls = env
    ctl = NotchController(); a = Assistant(ctl, cfg, store)
    hooks = {"weather_city": wc.set_city, "units": wc.units_changed}
    return SettingsController(a, ctl, cfg, store, [], hooks), wc, cfg, calls


def test_clocks_setting_is_validated_and_normalised(sc):
    s, wc, cfg, calls = sc
    s.set("clocks", "Dhaka=Asia/Dhaka, Atlantis=Mars/Olympus, Paris=Europe/Paris")
    assert cfg["clocks"] == ["Dhaka=Asia/Dhaka", "Paris=Europe/Paris"]
    s.set("clocks", "Nowhere=Mars/Olympus")                          # nothing valid: rejected, old value kept
    assert cfg["clocks"] == ["Dhaka=Asia/Dhaka", "Paris=Europe/Paris"] and "did not recognise" in s.message


def test_units_validated_and_applied(sc, qapp):
    s, wc, cfg, calls = sc
    s.set("weather_units", "K"); assert cfg["weather_units"] == "C"
    cfg.set("weather_place", "Dhaka, BD"); cfg.set("weather_lat", 1.0); cfg.set("weather_lon", 2.0)
    s.set("weather_units", "F"); pump(qapp, 0.5)
    assert cfg["weather_units"] == "F" and calls["fetch"][-1][3] == "F"


def test_settings_city_slot_looks_it_up(sc, qapp):
    s, wc, cfg, calls = sc
    s.setWeatherCity("Dhaka"); pump(qapp, 0.6)
    assert cfg["weather_city"] == "Dhaka" and cfg["weather_place"] == "Dhaka, BD" and "Looking up" in s.message


# ---------------- voice ----------------
@pytest.mark.parametrize("text", ["what's the weather", "how's the weather today", "is it raining", "do I need an umbrella", "weather forecast"])
def test_weather_intent(text):
    assert parse(text).name == "weather"


def test_time_in_beats_the_plain_time_rule():
    assert parse("what time is it").name == "time"
    i = parse("what time is it in Tokyo"); assert i.name == "time_in" and i.args["city"] == "tokyo"
    assert parse("what's the time in new york").args["city"] == "new york"


def test_widgets_open_intent():
    assert parse("show my widgets").name == "widgets_open" and parse("open the world clocks").name == "widgets_open"


def test_assistant_answers_time_in_and_weather(qapp, tmp_path):
    cfg = Settings(tmp_path / "s.json"); store = Store(tmp_path / "t.db"); ctl = NotchController()
    class Spk:
        speaking = False
        def __init__(self): self.said = []; self._on_state = None; self._on_level = None; self.speed = 1.0
        def speak(self, t): self.said.append(t)
        def stop(self): pass
    spk = Spk(); a = Assistant(ctl, cfg, store, speaker=spk)
    wc = WidgetsController(cfg, store, fetch=lambda *x: SUNNY); a.widgets = wc
    a.handle_text("what time is it in tokyo")
    assert spk.said[-1].startswith("It is ") and spk.said[-1].endswith("in Tokyo.")
    a.handle_text("what time is it in atlantis")
    assert "do not know the time zone" in spk.said[-1]
    cfg.set("weather_place", "Dhaka, BD"); cfg.set("weather_lat", 1.0); cfg.set("weather_lon", 2.0)
    a.handle_text("what's the weather"); pump(qapp, 0.8)
    assert "21 degrees" in spk.said[-1]
    a.handle_text("show my widgets", src="button")
    assert ctl.mode == "widgets"
