import os, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from datetime import datetime
import pytest
from PySide6.QtWidgets import QApplication
from app.store.db import Settings, Store
from app.ui.controller import NotchController
from app.core.assistant import Assistant
from app.tools.intents import parse
from app.llm.brain import Brain, to_intent
import app.core.assistant as mod


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeQS:
    """Stands in for app.winio.controls so no test ever touches the real radios or power plan."""
    def __init__(self):
        self.calls = []; self.radios = {"wifi": True, "bluetooth": True}; self.power = "balanced"; self.accept = True
    def set_radio(self, kind, on): self.calls.append(("radio", kind, on)); self.radios[kind] = on if self.accept else self.radios[kind]; return self.accept
    def set_airplane(self, on): self.calls.append(("airplane", on)); self.radios = {"wifi": not on, "bluetooth": not on}; return self.accept
    def set_power_mode(self, m): self.calls.append(("power", m)); self.power = m if self.accept else self.power; return self.accept
    def open_settings_page(self, n): self.calls.append(("page", n)); return True
    def snapshot(self, *a):
        return {"wifi": self.radios["wifi"], "bluetooth": self.radios["bluetooth"],
                "airplane": not any(self.radios.values()), "volume": 40, "muted": False, "brightness": 60,
                "battery": 77, "plugged": True, "power": self.power}


class Spk:
    speaking = False
    def __init__(self): self.said = []; self._on_state = None; self._on_level = None; self.speed = 1.0
    def speak(self, t): self.said.append(t)
    def stop(self): pass


@pytest.fixture
def env(qapp, tmp_path, monkeypatch):
    ctl = NotchController(); cfg = Settings(tmp_path / "s.json"); store = Store(tmp_path / "t.db")
    spk = Spk(); a = Assistant(ctl, cfg, store, speaker=spk)
    a.qs = FakeQS()
    vol, bri, shots = [], [], []
    monkeypatch.setattr(mod.win, "set_volume", lambda v: vol.append(v) or v)
    monkeypatch.setattr(mod.win, "set_brightness", lambda v: bri.append(v) or True)
    monkeypatch.setattr(mod.win, "toggle_mute", lambda: True)
    monkeypatch.setattr(mod.win, "screenshot", lambda: shots.append(1) or "x.png")
    monkeypatch.setattr(mod.win, "get_volume", lambda: 40)
    monkeypatch.setattr(mod.win, "is_muted", lambda: False)
    monkeypatch.setattr(mod.win, "get_brightness", lambda: 60)
    monkeypatch.setattr(mod.win, "battery", lambda: (77, True))
    return a, ctl, spk, vol, bri, shots


def pump(qapp, secs=0.3):
    end = time.time() + secs
    while time.time() < end:
        qapp.processEvents(); time.sleep(0.005)


# ---------------- opening + state ----------------
def test_open_controls_shows_panel_with_real_state(env, qapp):
    a, ctl, *_ = env
    a.open_controls(); pump(qapp, 0.6)
    c = ctl.controls
    assert ctl.mode == "controls" and c["battery"] == 77 and c["plugged"] is True and c["volume"] == 40 and c["brightness"] == 60


def test_say_does_not_close_the_panel(env, qapp):
    a, ctl, *_ = env
    a.open_controls(); a.say("Volume 40.", src="button")
    assert ctl.mode == "controls"


# ---------------- tiles ----------------
def test_wifi_tile_flips_instantly_then_confirms_with_windows(env, qapp):
    a, ctl, *_ = env
    a.open_controls(); pump(qapp, 0.5)
    a.on_action("ctl_wifi")
    assert ctl.controls["wifi"] is False                       # instant feedback
    pump(qapp, 0.6)
    assert ("radio", "wifi", False) in a.qs.calls and ctl.controls["wifi"] is False


def test_tile_reverts_if_windows_refuses(env, qapp):
    a, ctl, *_ = env
    a.open_controls(); pump(qapp, 0.5)
    a.qs.accept = False
    a.on_action("ctl_bluetooth"); pump(qapp, 0.8)
    assert ctl.controls["bluetooth"] is True and "would not change" in ctl.controls["msg"]


def test_airplane_turns_everything_off_and_back_on(env, qapp):
    a, ctl, *_ = env
    a.open_controls(); pump(qapp, 0.5)
    a.on_action("ctl_airplane"); pump(qapp, 0.6)
    assert ctl.controls["airplane"] is True and ctl.controls["wifi"] is False and ctl.controls["bluetooth"] is False
    a.on_action("ctl_airplane"); pump(qapp, 0.6)
    assert ctl.controls["airplane"] is False and ctl.controls["wifi"] is True


def test_page_tiles_open_windows_settings_not_fake_toggles(env):
    a, *_ = env
    for name in ("nightlight", "batterysaver", "accessibility"):
        a.on_action(f"ctl_page_{name}")
    assert [c for c in a.qs.calls if c[0] == "page"] == [("page", "nightlight"), ("page", "batterysaver"), ("page", "accessibility")]
    assert not [c for c in a.qs.calls if c[0] in ("radio", "airplane")]


# ---------------- sliders, power, screenshot ----------------
def test_volume_slider_applies_live(env):
    a, ctl, spk, vol, *_ = env
    ctl.setControl("volume", 30); ctl.setControl("volume", 35)
    assert vol == [30, 35] and ctl.controls["volume"] == 35


def test_brightness_applies_in_background(env, qapp):
    a, ctl, spk, vol, bri, _ = env
    ctl.setControl("brightness", 20); pump(qapp, 0.4)
    assert bri == [20]


def test_power_segment_sets_mode_and_failure_is_reported(env, qapp):
    a, ctl, *_ = env
    ctl.setControl("power", 2)
    assert ("power", "performance") in a.qs.calls and ctl.controls["power"] == "performance"
    a.qs.accept = False
    ctl.setControl("power", 0); pump(qapp, 0.1)
    assert "power mode" in ctl.controls["msg"]


def test_mute_icon_and_screenshot_button(env, qapp):
    a, ctl, spk, vol, bri, shots = env
    a.on_action("ctl_mute"); assert ctl.controls["muted"] is True
    a.on_action("ctl_screenshot"); pump(qapp, 0.4)
    assert shots == [1] and "Screenshot saved" in ctl.controls["msg"]


def test_panel_is_refreshed_while_open(env, qapp):
    a, ctl, *_ = env
    a.open_controls(); pump(qapp, 0.5)
    a.qs.radios["wifi"] = False                       # changed behind our back (e.g. from the Windows tray)
    for _ in range(3):
        a._every_second()
    pump(qapp, 0.6)
    assert ctl.controls["wifi"] is False


# ---------------- voice + intents ----------------
@pytest.mark.parametrize("text,name,on", [
    ("turn bluetooth off", "bluetooth_toggle", False), ("switch the wifi on", "wifi_toggle", True),
    ("toggle bluetooth", "bluetooth_toggle", None), ("airplane mode on", "airplane_toggle", True),
    ("flight mode off", "airplane_toggle", False)])
def test_radio_intents(text, name, on):
    i = parse(text)
    assert i.name == name and i.args["on"] is on


def test_other_new_intents():
    assert parse("set power mode to performance").args == {"mode": "performance"}
    assert parse("turn on battery saver").args == {"mode": "efficiency"}
    assert parse("turn on night light").name == "night_light_toggle"
    assert parse("open the controls").name == "controls_open"
    assert parse("how much battery is left") is None or parse("how much battery is left").name == "battery"


def test_voice_wifi_off_asks_first_and_only_acts_on_yes(env, qapp):
    a, ctl, spk, *_ = env
    a.handle_text("turn the wifi off", src="key")
    assert ctl.mode == "confirm" and a.qs.calls == []             # nothing happened yet
    a.handle_text("yes", src="key"); pump(qapp, 0.6)
    assert ("radio", "wifi", False) in a.qs.calls


def test_voice_wifi_off_can_be_cancelled(env, qapp):
    a, ctl, *_ = env
    a.handle_text("turn the wifi off", src="key"); a.handle_text("no", src="key")
    assert a.qs.calls == [] and ctl.mode != "confirm"


def test_voice_bluetooth_off_does_not_need_confirmation(env, qapp):
    a, ctl, spk, *_ = env
    a.handle_text("turn bluetooth off", src="key"); pump(qapp, 0.4)
    assert ("radio", "bluetooth", False) in a.qs.calls and any("Bluetooth off" in s for s in spk.said)


def test_night_light_voice_is_honest(env):
    a, ctl, spk, *_ = env
    a.handle_text("turn on night light", src="key")
    assert ("page", "nightlight") in a.qs.calls and "does not let apps" in spk.said[-1]


def test_open_controls_by_voice(env, qapp):
    a, ctl, *_ = env
    a.handle_text("open the controls", src="key"); pump(qapp, 0.3)
    assert ctl.mode == "controls"


# ---------------- brain tools ----------------
NOW = datetime(2026, 11, 25, 4, 6)


def test_brain_new_tools_validated():
    d = to_intent({"tool": "power_mode_set", "args": {"mode": "Performance"}}, NOW)
    assert d.intent.args == {"mode": "performance"}
    assert to_intent({"tool": "power_mode_set", "args": {"mode": "turbo"}}, NOW).error
    assert to_intent({"tool": "wifi_toggle", "args": {"on": "false"}}, NOW).intent.args == {"on": False}
    assert to_intent({"tool": "bluetooth_toggle", "args": {}}, NOW).intent.args == {"on": None}


class Fake:
    def __init__(self, r): self.r = r
    def chat(self, m, **k): return self.r


def test_brain_cannot_toggle_wifi_unless_you_mentioned_it():
    b = Brain(Fake('{"tool": "wifi_toggle", "args": {"on": false}}'), name="Nur")
    assert b.route("lower the glare on my monitor", NOW).intent is None
    assert b.route("switch off the wireless", NOW).intent.name == "wifi_toggle"
