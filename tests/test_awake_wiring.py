import os, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
import app.core.assistant as mod
from app.core.assistant import Assistant
from app.claude_bridge.tracker import Tracker
from app.store.db import Settings, Store
from app.tools.intents import parse
from app.ui.controller import NotchController
from app.ui.settings_ctl import SettingsController
from app.winio.awake import KeepAwake
from app.winio.claude_proc import ClaudeActivity


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class Api:
    def __init__(self): self.calls = []
    def __call__(self, f): self.calls.append(f); return 0


class Spk:
    speaking = False
    def __init__(self): self.said = []; self._on_state = None; self._on_level = None; self.speed = 1.0
    def speak(self, t): self.said.append(t)
    def stop(self): pass


@pytest.fixture
def env(qapp, tmp_path, monkeypatch):
    t = {"now": 1000.0}
    ctl = NotchController(); cfg = Settings(tmp_path / "s.json"); store = Store(tmp_path / "t.db")
    tracker = Tracker(); spk = Spk()
    a = Assistant(ctl, cfg, store, speaker=spk, tracker=tracker)
    a.awake = KeepAwake(Api(), clock=lambda: t["now"])
    a.claude_activity = ClaudeActivity(processes=lambda: [], clock=lambda: t["now"])
    monkeypatch.setattr(mod.win, "battery", lambda: (80, True))
    changes = []; a.on_awake_changed = changes.append
    yield a, ctl, cfg, tracker, spk, t, changes
    a.awake.off()


# ---------------- voice ----------------
@pytest.mark.parametrize("text", ["keep my laptop awake", "keep the laptop awake", "stay awake", "don't let my laptop sleep",
                                  "prevent my laptop from sleeping", "caffeinate", "keep the screen on", "keep it awake please"])
def test_keep_awake_phrases(text):
    i = parse(text)
    assert i.name == "keep_awake" and i.args["on"] is True


@pytest.mark.parametrize("text,minutes", [("keep my laptop awake for two hours", 120), ("stay awake for 45 minutes", 45),
                                          ("keep the laptop awake for half an hour", 30), ("keep it awake for an hour", 60),
                                          ("keep my laptop awake", None)])
def test_duration_is_understood(text, minutes):
    assert parse(text).args["minutes"] == minutes


@pytest.mark.parametrize("text", ["stop keeping my laptop awake", "allow my laptop to sleep", "let it sleep", "stop keeping awake",
                                  "go back to normal sleep"])
def test_turning_it_off(text):
    i = parse(text)
    assert i.name == "keep_awake" and i.args["on"] is False


def test_normal_sleep_commands_are_not_confused_with_keep_awake():
    assert parse("goodnight").name == "go_to_sleep" and parse("go to sleep").name == "go_to_sleep"


def test_voice_turns_it_on_with_a_timer_and_mentions_the_lid_once(env):
    a, ctl, cfg, tr, spk, t, changes = env
    a.handle_text("keep my laptop awake for two hours")
    assert a.awake.active and a.awake.remaining() == 7200 and "for 2 hours" in spk.said[-1] and "lid" in spk.said[-1]
    a.handle_text("keep it awake for 30 minutes")
    assert "lid" not in spk.said[-1] and a.awake.remaining() == 1800        # the lid reminder is only given once
    a.handle_text("allow my laptop to sleep")
    assert not a.awake.active and "sleep normally" in spk.said[-1]


# ---------------- the panel tile ----------------
def test_tile_toggles_and_updates_the_panel_and_tray(env):
    a, ctl, cfg, tr, spk, t, changes = env
    a.on_action("ctl_awake")
    assert a.awake.active and ctl.controls["awake"] is True and changes[-1] is True
    a.on_action("ctl_awake")
    assert not a.awake.active and ctl.controls["awake"] is False and changes[-1] is False


def test_screen_stays_on_only_if_configured(env):
    a, ctl, cfg, tr, spk, t, changes = env
    cfg.set("awake_display", False); a.set_keep_awake(True); assert a.awake.display is False
    cfg.set("awake_display", True); a.set_keep_awake(True); assert a.awake.display is True


# ---------------- safety ----------------
def test_timed_session_ends_and_says_so(env):
    a, ctl, cfg, tr, spk, t, changes = env
    a.set_keep_awake(True, minutes=10)
    t["now"] += 601; a._awake_tick(t["now"])
    assert not a.awake.active and "finished" in spk.said[-1]


def test_low_battery_releases_the_hold(env, monkeypatch):
    a, ctl, cfg, tr, spk, t, changes = env
    a.set_keep_awake(True)
    monkeypatch.setattr(mod.win, "battery", lambda: (14, False))
    a._awake_tick(1000.0)                                  # 1000 % 20 == 0: the battery check runs on this tick
    assert not a.awake.active and "14 percent" in spk.said[-1]


def test_plugged_in_low_battery_is_fine(env, monkeypatch):
    a, ctl, cfg, tr, spk, t, changes = env
    a.set_keep_awake(True)
    monkeypatch.setattr(mod.win, "battery", lambda: (5, True))
    a._awake_tick(1000.0)
    assert a.awake.active


# ---------------- automatic: while Claude Code works ----------------
def test_claude_default_is_on(env):
    a, ctl, cfg, *_ = env
    assert cfg["awake_claude"] is True


def test_awake_while_claude_works_via_hooks_then_released_after_grace(env):
    a, ctl, cfg, tr, spk, t, changes = env
    tr.handle({"hook_event_name": "UserPromptSubmit", "session_id": "s", "cwd": r"C:\p"})
    a._awake_tick(1000.0)
    assert a.awake.active and a._auto_awake
    tr.handle({"hook_event_name": "Stop", "session_id": "s", "cwd": r"C:\p", "last_assistant_message": "done."})
    a._awake_tick(1001.0); assert a.awake.active                      # grace period starts
    a._awake_tick(1100.0); assert a.awake.active                      # 99 s later: still held
    a._awake_tick(1125.0); assert not a.awake.active                  # >120 s idle: released


def test_awake_while_claude_works_via_process_activity_without_hooks(env):
    class P:
        pid = 7
        def cpu_percent(self, interval=None): return 25.0
    a, ctl, cfg, tr, spk, t, changes = env
    a.claude_activity = ClaudeActivity(processes=lambda: [P()], clock=lambda: t["now"])
    a._awake_tick(1000.0)                                             # 1000 % 5 == 0: process check runs
    assert a.awake.active and a._auto_awake


def test_manual_hold_is_never_released_by_the_automatic_rules(env):
    a, ctl, cfg, tr, spk, t, changes = env
    a.set_keep_awake(True)                                            # you asked for it by hand
    for now in (1000.0, 1200.0, 1400.0):
        a._awake_tick(now)
    assert a.awake.active and not a._auto_awake


def test_switching_the_claude_option_off_stops_the_automatic_hold(env):
    a, ctl, cfg, tr, spk, t, changes = env
    cfg.set("awake_claude", False)
    tr.handle({"hook_event_name": "UserPromptSubmit", "session_id": "s", "cwd": r"C:\p"})
    a._awake_tick(1000.0)
    assert not a.awake.active


def test_focus_sessions_can_hold_awake(env):
    a, ctl, cfg, tr, spk, t, changes = env
    cfg.set("awake_claude", False); cfg.set("awake_focus", True)
    a.start_focus(25); a._awake_tick(1000.0)
    assert a.awake.active and a._auto_awake
    a.stop_focus()
    a._awake_tick(1001.0); a._awake_tick(1125.0)
    assert not a.awake.active


# ---------------- settings ----------------
def test_settings_options_apply_and_persist(env):
    a, ctl, cfg, tr, spk, t, changes = env
    sc = SettingsController(a, ctl, cfg, a.store, [], {})
    sc.set("awake_claude", False); assert cfg["awake_claude"] is False
    sc.set("awake_focus", True); assert cfg["awake_focus"] is True
    a.set_keep_awake(True, minutes=60)
    sc.set("awake_display", True)                                     # changes the running hold, keeps the remaining time
    assert a.awake.display is True and 3500 < a.awake.remaining() <= 3600


@pytest.mark.parametrize("text", ["don't let it sleep", "do not let the laptop sleep", "never let my laptop sleep", "don't allow it to sleep"])
def test_negations_mean_keep_awake_not_allow_sleep(text):
    i = parse(text)
    assert i.name == "keep_awake" and i.args["on"] is True


def test_let_it_sleep_still_means_allow_sleep():
    assert parse("let it sleep").args["on"] is False and parse("let my laptop sleep").args["on"] is False
