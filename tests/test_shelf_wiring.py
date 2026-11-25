import os, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from datetime import datetime
import pytest
from PySide6.QtWidgets import QApplication
from app.store.db import Settings, Store
from app.ui.controller import NotchController
from app.ui.settings_ctl import SettingsController
from app.core.assistant import Assistant
from app.tools.intents import parse
from app.llm.brain import Brain, to_intent

NOW = datetime(2026, 11, 25, 4, 6)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("text", ["show my shelf", "open the clipboard", "what did I copy", "bring up my clipboard"])
def test_voice_opens_the_shelf(text):
    assert parse(text).name == "shelf_open"


def test_other_phrases_do_not_open_the_shelf():
    assert parse("what's on my list").name == "todo_list"


class Shelf:
    def __init__(self): self.opened_n = 0; self.enabled = True; self.cleared = 0
    def opened(self): self.opened_n += 1
    def set_enabled(self, on): self.enabled = on
    def clear(self): self.cleared += 1


@pytest.fixture
def env(qapp, tmp_path):
    ctl = NotchController(); cfg = Settings(tmp_path / "s.json"); store = Store(tmp_path / "t.db")
    a = Assistant(ctl, cfg, store); a.shelf = Shelf()
    hooks = {"shelf": a.shelf.set_enabled, "shelf_clear": a.shelf.clear}
    sc = SettingsController(a, ctl, cfg, store, [], hooks)
    return a, ctl, cfg, sc


def test_assistant_opens_the_shelf_by_voice(env):
    a, ctl, cfg, sc = env
    a.handle_text("show my shelf", src="button")
    assert ctl.mode == "shelf" and a.shelf.opened_n == 1


def test_saying_something_does_not_close_the_shelf(env):
    a, ctl, cfg, sc = env
    a.handle_text("show my shelf"); a.say("Copied.", src="button")
    assert ctl.mode == "shelf"


def test_settings_toggle_turns_the_shelf_off_and_persists(env):
    a, ctl, cfg, sc = env
    assert cfg["shelf_enabled"] is True
    sc.set("shelf_enabled", False)
    assert a.shelf.enabled is False and cfg["shelf_enabled"] is False
    sc.set("shelf_enabled", True); assert a.shelf.enabled is True


def test_settings_clear_shelf_button(env):
    a, ctl, cfg, sc = env
    sc.clearShelf()
    assert a.shelf.cleared == 1 and "Shelf cleared" in sc.message


def test_brain_shelf_tool_is_validated_and_justified():
    class F:
        def __init__(self, r): self.r = r
        def chat(self, m, **k): return self.r
    assert to_intent({"tool": "shelf_open", "args": {}}, NOW).intent.name == "shelf_open"
    b = Brain(F('{"tool": "shelf_open", "args": {}}'), name="Nur")
    assert b.route("lower the glare on my monitor", NOW).intent is None            # words must justify it
    assert b.route("what did I copy a minute ago from the clipboard", NOW).intent.name == "shelf_open"
