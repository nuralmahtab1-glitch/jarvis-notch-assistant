import os, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QApplication
from app.store.db import Settings
from app.ui.controller import NotchController
from app.ui.prompter_ctl import MenuController, PrompterController, clean_site, clean_sites


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def pump(qapp, s=0.3):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents(); time.sleep(0.005)


class Clip:
    def __init__(self, text=None): self._md = None; self.set(text)
    def set(self, text):
        self._md = QMimeData()
        if text is not None: self._md.setText(text)
    def mimeData(self): return self._md


@pytest.fixture
def env(qapp, tmp_path):
    cfg = Settings(tmp_path / "s.json"); ctl = NotchController(); clip = Clip("word " * 200)
    return PrompterController(ctl, cfg, clipboard=clip), ctl, cfg, clip


def test_start_reads_the_copied_script_and_opens_the_prompter(env):
    pc, ctl, cfg, clip = env
    assert pc.start() is True
    assert ctl.mode == "prompter" and pc.view["running"] is True and pc.view["cur"] != ""


def test_start_with_nothing_copied_says_what_to_do_and_changes_nothing(env):
    pc, ctl, cfg, clip = env
    clip.set(None)
    assert pc.start() is False and "Copy your script" in pc.message and ctl.mode == "idle"
    clip.set("   \n  "); assert pc.start() is False


def test_it_scrolls_over_time(env, qapp):
    pc, ctl, cfg, clip = env
    pc.start(); before = pc.view["progress"]
    pump(qapp, 1.0)
    assert pc.view["progress"] > before


def test_pause_resume_restart(env, qapp):
    pc, ctl, cfg, clip = env
    pc.start(); pump(qapp, 0.4)
    pc.toggle(); frozen = pc.view["progress"]; pump(qapp, 0.4)
    assert pc.view["progress"] == frozen and pc.view["running"] is False
    pc.restart(); assert pc.view["progress"] == 0.0


def test_speed_changes_are_remembered(env):
    pc, ctl, cfg, clip = env
    pc.start(); pc.faster(); pc.faster(); pc.slower()
    assert cfg["prompter_wpm"] == 150 and Settings(cfg.path)["prompter_wpm"] == 150


def test_close_returns_to_idle_and_stops(env):
    pc, ctl, cfg, clip = env
    pc.start(); pc.close()
    assert ctl.mode == "idle" and pc.view["running"] is False


def test_prompter_keeps_the_notch_awake_while_reading(env, qapp):
    pc, ctl, cfg, clip = env
    pc.start(); ctl._busy_until = 0
    pump(qapp, 0.4)
    assert ctl._busy_until > time.monotonic()                 # so it never falls asleep in the middle of a talk


# ---------------- menu + sites ----------------
@pytest.mark.parametrize("raw,label", [("youtube.com", "youtube.com"), ("https://www.github.com/me", "github.com"),
                                       ("http://example.org/a?b=1", "example.org"), ("docs.python.org/3", "docs.python.org")])
def test_good_sites_are_accepted(raw, label):
    assert clean_site(raw)[0] == label and clean_site(raw)[1].startswith(("http://", "https://"))


@pytest.mark.parametrize("raw", ["file:///C:/Windows/System32/cmd.exe", "javascript:alert(1)", "C:\\Windows\\notepad.exe", "localhost",
                                 "two words.com", "", "ftp://example.com", "calc.exe", "http://", "https://exa mple.com", "../../etc/passwd"])
def test_dangerous_or_invalid_sites_are_rejected(raw):
    assert clean_site(raw) is None


def test_sites_are_deduplicated_and_limited():
    out = clean_sites(["a.com", "https://a.com", "b.com", "x y", *[f"s{i}.com" for i in range(20)]])
    assert out[0] == "https://a.com" and len(out) == 8 and out.count("https://a.com") == 1


def test_menu_opens_only_validated_sites(env, qapp, tmp_path):
    pc, ctl, cfg, clip = env
    opened = []
    cfg.set("websites", ["youtube.com", "file:///C:/evil.exe", "github.com"])      # a bad entry sneaks into the settings file
    m = MenuController(ctl, cfg, opener=opened.append, prompter=pc)
    assert [s["label"] for s in m.sites] == ["youtube.com", "github.com"]
    ctl.setMode("menu"); m.openSite(1)
    assert opened == ["https://github.com"] and ctl.mode == "idle"
    m.openSite(5); assert opened == ["https://github.com"]                            # out of range: ignored


def test_menu_buttons(env):
    pc, ctl, cfg, clip = env
    m = MenuController(ctl, cfg, opener=lambda u: None, prompter=pc)
    m.startPrompter(); assert ctl.mode == "prompter"
    m.openMusic(); assert ctl.mode == "music"
    assert len(m.guide) == 3
