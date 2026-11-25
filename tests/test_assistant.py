import os, threading, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from app.store.db import Settings, Store
from app.ui.controller import NotchController
from app.core.assistant import Assistant
from app.claude_bridge.tracker import Tracker


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeSpeaker:
    speaking = False
    def __init__(self): self.said = []; self._on_state = None; self._on_level = None
    def speak(self, t): self.said.append(t)
    def stop(self): pass


@pytest.fixture
def env(qapp, tmp_path):
    ctl = NotchController()
    cfg = Settings(tmp_path / "s.json")
    store = Store(tmp_path / "t.db")
    tracker = Tracker(approval_timeout=3, quiet_when_focused=False)
    spk = FakeSpeaker()
    a = Assistant(ctl, cfg, store, speaker=spk, tracker=tracker)
    return a, ctl, store, tracker, spk, cfg


def pump(qapp, secs=0.05):
    end = time.time() + secs
    while time.time() < end:
        qapp.processEvents(); time.sleep(0.005)


def test_todo_add_and_list(env, qapp):
    a, ctl, store, *_ = env
    a.handle_text("add buy milk to my list")
    assert [t["text"] for t in store.todo_list()] == ["buy milk"]
    assert ctl.mode == "speaking" or ctl.mode == "todo"
    a.handle_text("what's on my list")
    assert ctl.todo[0]["text"] == "buy milk"


def test_todo_complete(env):
    a, ctl, store, *_ = env
    a.handle_text("add call the bank to my list")
    a.handle_text("mark call the bank done")
    assert store.todo_list()[0]["done"] == 1
    assert ctl.todoDone == 1


def test_reminder_is_stored_with_future_time(env):
    a, ctl, store, *_ = env
    a.handle_text("remind me to stretch in 10 minutes")
    r = store.reminders_pending()
    assert len(r) == 1 and r[0]["text"] == "stretch" and 590 < r[0]["due"] - time.time() <= 601


def test_due_reminder_shows_card_and_speaks(env, qapp):
    a, ctl, store, tracker, spk, cfg = env
    store.reminder_add("call mom", time.time() - 1)
    a._every_second()
    assert ctl.mode == "reminder" and ctl.title == "Reminder" and ctl.subtitle == "call mom"
    assert any("call mom" in s for s in spk.said)


def test_dnd_silences_reminders(env):
    a, ctl, store, tracker, spk, cfg = env
    cfg.set("dnd", True)
    store.reminder_add("quiet one", time.time() - 1)
    a._every_second()
    assert spk.said == []


def test_focus_session(env):
    a, ctl, *_ = env
    a.handle_text("start a focus session for 10 minutes")
    assert ctl.mode == "focus" and ctl.focusText == "10:00"
    a._every_second()
    assert ctl.focusText in ("9:59", "10:00")
    a.handle_text("stop the focus session")
    assert ctl.mode != "focus"


def test_voice_reply_spoken_only_for_voice_source(env):
    a, ctl, store, tracker, spk, cfg = env
    a.handle_text("what time is it", src="button")
    assert spk.said == []                       # button => silent by default
    a.handle_text("what time is it", src="key")
    assert len(spk.said) == 1 and spk.said[0].startswith("It is")


def test_unknown_gets_polite_reply(env):
    a, ctl, store, tracker, spk, cfg = env
    a.handle_text("flibbertigibbet")
    assert "did not catch" in spk.said[0] and "Nur" in spk.said[0]


def test_sleep_command(env, qapp):
    a, ctl, *_ = env
    a.handle_text("goodnight")
    pump(qapp, 3.2)
    assert ctl.mode == "sleeping"


def test_claude_status_and_voice_approval(env, qapp):
    a, ctl, store, tracker, spk, cfg = env
    ev = lambda n, **kw: {"hook_event_name": n, "session_id": "s", "cwd": r"C:\proj\plant", **kw}
    tracker.handle(ev("UserPromptSubmit"))
    tracker.handle(ev("PreToolUse", tool_name="Edit", tool_input={"file_path": r"C:\proj\plant\a.py"}))
    pump(qapp)
    assert ctl.mode == "claudeWorking" and "editing a.py" in ctl.title
    a.handle_text("what's claude doing")
    assert "editing a.py" in spk.said[-1] and "plant" in spk.said[-1]

    out = {}
    th = threading.Thread(target=lambda: out.update(r=tracker.handle(ev("PermissionRequest", tool_name="Bash", tool_input={"command": "ls"}))))
    th.start(); time.sleep(0.2); pump(qapp)
    assert ctl.mode == "claudeNeeds"
    a.handle_text("approve")
    th.join(3)
    assert out["r"]["hookSpecificOutput"]["decision"]["behavior"] == "allow"

    a._speaking_changed(False)                 # the real speaker reports when it finishes
    pump(qapp, 0.7)
    tracker.handle(ev("Stop", last_assistant_message="All done. Tests pass."))
    pump(qapp)
    assert ctl.mode == "claudeDone" and ctl.subtitle == "All done."


def test_risky_needs_tap_not_voice(env, qapp):
    a, ctl, store, tracker, spk, cfg = env
    ev = lambda n, **kw: {"hook_event_name": n, "session_id": "s", "cwd": r"C:\proj", **kw}
    out = {}
    th = threading.Thread(target=lambda: out.update(r=tracker.handle(ev("PermissionRequest", tool_name="Bash", tool_input={"command": "rm -rf build"}))))
    th.start(); time.sleep(0.2); pump(qapp)
    assert "(risky)" in ctl.title
    a.handle_text("approve")
    assert "risky" in spk.said[-1]
    a.on_action("approve")                     # a tap is allowed
    th.join(3)
    assert out["r"]["hookSpecificOutput"]["decision"]["behavior"] == "allow"


def test_dictation_fails_closed_when_window_changes(env, monkeypatch):
    a, ctl, store, tracker, spk, cfg = env
    import app.core.assistant as mod
    typed, clip = [], []
    monkeypatch.setattr(mod.win, "type_text", lambda t: typed.append(t))
    monkeypatch.setattr(mod.win, "set_clipboard", lambda t: clip.append(t))
    monkeypatch.setattr(mod.win, "foreground_window", lambda: 222)
    a.insert_dictation("um hello there", hwnd=111)     # target window no longer in front
    assert typed == [] and clip == ["Hello there."]
    a.insert_dictation("um hello there", hwnd=222)
    time.sleep(0.2)
    assert typed == ["Hello there."]
