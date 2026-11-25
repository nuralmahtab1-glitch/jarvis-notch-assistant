import json, os, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from app.store.db import Settings, Store, DEFAULT_SETTINGS
from app.ui.controller import NotchController
from app.ui.settings_ctl import SettingsController
from app.core.assistant import Assistant
from app.claude_bridge.tracker import Tracker


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class Spk:
    speaking = False
    def __init__(self): self.said = []; self.speed = 1.0; self._on_state = None; self._on_level = None
    def speak(self, t): self.said.append(t)
    def stop(self): pass


@pytest.fixture
def env(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(Path_home := __import__("pathlib").Path, "home", classmethod(lambda cls: tmp_path))
    ctl = NotchController(); cfg = Settings(tmp_path / "s.json"); store = Store(tmp_path / "t.db")
    tracker = Tracker(); spk = Spk()
    a = Assistant(ctl, cfg, store, speaker=spk, tracker=tracker)
    calls = {}
    sc = SettingsController(a, ctl, cfg, store, ["Mic A", "Mic B"],
                            hooks={"wake": lambda on: calls.__setitem__("wake", on), "lyrics": lambda on: calls.__setitem__("lyrics", on)})
    return sc, a, ctl, cfg, store, tracker, spk, calls, tmp_path


def test_values_exposes_every_default(env):
    sc, *_ = env
    v = sc.values
    assert all(k in v for k in DEFAULT_SETTINGS) and v["speak_done"] is True


def test_address_applies_live_and_persists(env):
    sc, a, ctl, cfg, *_ = env
    sc.set("address", "  Sam  ")
    assert a.persona.name == "Sam" and cfg["address"] == "Sam"
    assert json.loads(cfg.path.read_text())["address"] == "Sam"
    sc.set("address", "   ")                      # blank is rejected
    assert cfg["address"] == "Sam"


def test_voice_speed_clamped_and_applied(env):
    sc, a, ctl, cfg, store, tr, spk, *_ = env
    sc.set("voice_speed", 9); assert spk.speed == 1.4 and cfg["voice_speed"] == 1.4
    sc.set("voice_speed", 0.1); assert spk.speed == 0.8
    sc.set("voice_speed", "oops"); assert spk.speed == 0.8


def test_persona_switch_changes_wording_immediately(env):
    sc, a, *_ = env
    sc.set("persona", "minimal")
    assert a.persona.say("done") == "Done."
    assert a.persona.say("greet_morning") == ""
    sc.set("persona", "nonsense")                 # unknown preset ignored
    assert a.persona.preset == "minimal"


def test_speak_mode_validated(env):
    sc, a, ctl, cfg, *_ = env
    sc.set("speak_replies", "always"); assert cfg["speak_replies"] == "always" and a.should_speak("button")
    sc.set("speak_replies", "loud"); assert cfg["speak_replies"] == "always"
    sc.set("speak_replies", "off"); assert not a.should_speak("key")


def test_sleep_minutes_applied_to_notch(env):
    sc, a, ctl, cfg, *_ = env
    sc.set("sleep_after_minutes", 2)
    assert ctl._sleep_after == 120
    sc.set("sleep_after_minutes", 999); assert cfg["sleep_after_minutes"] == 120


def test_dnd_sleeps_the_notch_and_silences_reminders(env, qapp):
    sc, a, ctl, cfg, store, tr, spk, *_ = env
    sc.set("dnd", True)
    assert ctl.mode == "sleeping" and ctl.dnd is True
    store.reminder_add("quiet", time.time() - 1); a._every_second()
    assert spk.said == [] and ctl.mode == "sleeping"                 # silent, notch stays asleep
    assert len(store.reminders_pending()) == 1                       # ...but the reminder is held, not lost
    sc.set("dnd", False); assert ctl.dnd is False
    a._every_second()
    assert ctl.mode == "reminder" and any("quiet" in x for x in spk.said)   # fires once DND ends


def test_claude_settings_apply_to_tracker_live(env):
    sc, a, ctl, cfg, store, tr, *_ = env
    sc.set("claude_hide_details", True); assert tr.hide_details is True
    sc.set("claude_approval_timeout", 2); assert tr.approval_timeout == 5          # clamped to the 5 s minimum
    sc.set("claude_quiet_when_focused", False); assert tr.quiet_when_focused is False
    sc.set("speak_needs", False); assert cfg["claude_speak"]["needs_you"] is False and cfg["claude_speak"]["done"] is True


def test_ptt_keys_must_differ_and_need_restart(env):
    sc, a, ctl, cfg, *_ = env
    assert sc.restartNeeded is False
    sc.set("ptt_command_key", "right alt")        # same as dictate key -> rejected
    assert cfg["ptt_command_key"] == "right ctrl" and "different keys" in sc.message
    sc.set("ptt_command_key", "f9")
    assert cfg["ptt_command_key"] == "f9" and sc.restartNeeded is True
    sc.set("ptt_dictate_key", "banana"); assert cfg["ptt_dictate_key"] == "right alt"


def test_wake_and_lyrics_toggle_through_hooks(env):
    sc, a, ctl, cfg, store, tr, spk, calls, _ = env
    sc.set("wake_word", False); sc.set("lyrics", False)
    assert calls == {"wake": False, "lyrics": False} and cfg["wake_word"] is False


def test_mic_and_models_validated(env):
    sc, a, ctl, cfg, *_ = env
    sc.set("mic_device", "Mic B"); assert cfg["mic_device"] == "Mic B"
    sc.set("mic_device", "Ghost mic"); assert cfg["mic_device"] == "Mic B"
    sc.set("stt_model", "huge"); assert cfg["stt_model"] == "base.en"
    sc.set("stt_model", "tiny.en"); assert cfg["stt_model"] == "tiny.en"
    sc.set("llm_model", "qwen3-4b"); assert cfg["llm_model"] == "qwen3-4b"
    sc.set("llm_model", "gpt-9"); assert cfg["llm_model"] == "qwen3-4b"


def test_unknown_keys_are_ignored(env):
    sc, a, ctl, cfg, *_ = env
    sc.set("__import__('os').system", "x"); sc.set("onboarded", False)
    assert "__import__('os').system" not in cfg.data and cfg["onboarded"] is False   # onboarded is a real key; unchanged semantics ok


def test_export_contains_data_and_wipe_keeps_settings(env):
    sc, a, ctl, cfg, store, tr, spk, calls, tmp = env
    store.todo_add("renew passport"); store.reminder_add("call dad", time.time() + 3600)
    path = sc.exportData()
    data = json.loads(open(path, encoding="utf-8").read())
    assert data["todos"][0]["text"] == "renew passport" and data["reminders"][0]["text"] == "call dad"
    assert data["settings"]["address"] == cfg["address"]
    sc.wipeData()
    assert store.todo_list() == [] and store.reminders_pending() == [] and cfg["address"] == data["settings"]["address"]


def test_reset_restores_defaults_but_not_onboarded(env):
    sc, a, ctl, cfg, *_ = env
    cfg.set("onboarded", True); sc.set("voice_speed", 1.3); sc.set("persona", "friendly")
    sc.resetSettings()
    assert cfg["voice_speed"] == 1.0 and cfg["persona"] == "butler" and cfg["onboarded"] is True
    assert a.persona.preset == "butler"


def test_greeting_once_per_day(env, qapp):
    sc, a, ctl, cfg, store, tr, spk, *_ = env
    a.greet_if_due(); a.greet_if_due()
    assert len(spk.said) == 1 and cfg["last_greeting"] == time.strftime("%Y-%m-%d")
    cfg.set("last_greeting", ""); sc.set("greeting", False); a.greet_if_due()
    assert len(spk.said) == 1                      # disabled -> silent
