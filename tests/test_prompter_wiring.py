import os, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QApplication
from app.core.assistant import Assistant
from app.store.db import Settings, Store
from app.tools.intents import parse
from app.ui.controller import NotchController
from app.ui.prompter_ctl import MenuController, PrompterController
from app.ui.settings_ctl import SettingsController


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class Clip:
    def __init__(self, text): self._md = QMimeData(); self._md.setText(text)
    def mimeData(self): return self._md


class Spk:
    speaking = False
    def __init__(self): self.said = []; self._on_state = None; self._on_level = None; self.speed = 1.0
    def speak(self, t): self.said.append(t)
    def stop(self): pass


@pytest.fixture
def env(qapp, tmp_path):
    cfg = Settings(tmp_path / "s.json"); store = Store(tmp_path / "t.db"); ctl = NotchController(); spk = Spk()
    a = Assistant(ctl, cfg, store, speaker=spk)
    pc = PrompterController(ctl, cfg, clipboard=Clip("word " * 100)); a.prompter = pc
    return a, ctl, cfg, spk, pc


@pytest.mark.parametrize("text", ["start the teleprompter", "open the prompter", "read my script", "teleprompter"])
def test_start_phrases(text):
    assert parse(text).name == "prompter_start"


@pytest.mark.parametrize("text", ["stop the teleprompter", "close the prompter", "turn off the teleprompter"])
def test_stop_phrases(text):
    assert parse(text).name == "prompter_stop"


def test_menu_phrase_and_no_clash_with_open_app():
    assert parse("show the menu").name == "menu_open" and parse("open spotify").name == "open_app"


def test_voice_starts_and_stops_the_teleprompter(env):
    a, ctl, cfg, spk, pc = env
    a.handle_text("start the teleprompter", src="button")
    assert ctl.mode == "prompter" and pc.view["running"]
    a.handle_text("stop the teleprompter", src="button")
    assert ctl.mode == "idle" and not pc.view["running"]


def test_voice_start_with_no_script_explains(env):
    a, ctl, cfg, spk, pc = env
    pc.clip = Clip("")
    a.handle_text("start the teleprompter", src="key")
    assert "Copy your script" in spk.said[-1] and ctl.mode != "prompter"


def test_saying_something_does_not_close_the_prompter(env):
    a, ctl, cfg, spk, pc = env
    pc.start(); a.say("Noted.", src="button")
    assert ctl.mode == "prompter"


def test_menu_by_voice(env):
    a, ctl, cfg, spk, pc = env
    a.handle_text("show the menu", src="button")
    assert ctl.mode == "menu"


def test_settings_validate_favourite_sites(env):
    a, ctl, cfg, spk, pc = env
    sc = SettingsController(a, ctl, cfg, a.store, [], {})
    sc.set("websites", "youtube.com, https://github.com/me, file:///C:/evil.exe, javascript:alert(1), calc.exe")
    assert cfg["websites"] == ["https://youtube.com", "https://github.com/me"]
    sc.set("websites", "file:///C:/evil.exe, not a site")                   # nothing valid: refused, old list kept
    assert cfg["websites"] == ["https://youtube.com", "https://github.com/me"] and "do not look like" in sc.message


def test_old_settings_files_with_bare_domains_still_work(env):
    a, ctl, cfg, spk, pc = env
    opened = []
    m = MenuController(ctl, cfg, opener=opened.append, prompter=pc)         # the default setting is bare domains
    m.openSite(0)
    assert opened == ["https://youtube.com"]
