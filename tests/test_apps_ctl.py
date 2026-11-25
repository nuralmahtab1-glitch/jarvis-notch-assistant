import os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from datetime import datetime
import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication
from app.core.apps import AppEntry, PinnedApps
from app.store.db import Settings, Store
from app.ui.apps_ctl import AppsController
from app.ui.controller import NotchController
from app.core.assistant import Assistant
from app.tools.intents import parse
from app.llm.brain import Brain, to_intent
import app.core.assistant as mod


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def pump(qapp, s=0.2):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents(); time.sleep(0.005)


@pytest.fixture
def env(qapp, tmp_path):
    cfg = Settings(tmp_path / "s.json"); launched = []
    idx = {"Photoshop": str(tmp_path / "Photoshop.lnk")}
    pins = PinnedApps(cfg, idx, launcher=launched.append)
    ctl = NotchController()
    picked = {"path": ""}
    c = AppsController(ctl, pins, picker=lambda: picked["path"])
    return c, pins, launched, ctl, picked, tmp_path


def test_items_have_real_icons_or_a_letter_badge(env):
    c, pins, *_ = env
    pins.items = [AppEntry("Python", sys.executable), AppEntry("Settings", "ms-settings:")]
    it = c.items
    assert it[0]["icon"].startswith("data:image/png;base64,") and len(it[0]["icon"]) > 200
    assert it[1]["icon"] == "" and it[1]["letter"] == "S"


def test_launch_reports_and_closes_the_panel(env, qapp):
    c, pins, launched, ctl, *_ = env
    ctl.setMode("apps")
    c.launch(1)
    assert launched == [pins.items[1].target] and c.message == f"Opening {pins.items[1].name}"
    pump(qapp, 0.8)
    assert ctl.mode == "idle"                         # the panel gets out of your way once the app is opening


def test_launch_failure_is_reported_and_panel_stays(env, qapp):
    c, pins, launched, ctl, *_ = env
    ctl.setMode("apps")
    pins.launcher = lambda t: (_ for _ in ()).throw(OSError("blocked"))
    c.launch(0)
    pump(qapp, 0.7)
    assert "Could not open" in c.message and ctl.mode == "apps"


def test_remove_and_out_of_range(env):
    c, pins, *_ = env
    n = c.count; name = pins.items[0].name
    c.remove(0); assert c.count == n - 1 and c.message == f"Unpinned {name}"
    c.remove(999); c.launch(999)                      # ignored quietly


def test_drop_pins_programs_and_refuses_everything_else(env):
    c, pins, launched, ctl, picked, tmp = env
    exe = tmp / "Cool Tool.exe"; exe.write_text("x"); doc = tmp / "notes.txt"; doc.write_text("x")
    n = c.count
    c.dropUrls([QUrl.fromLocalFile(str(exe)).toString(), QUrl.fromLocalFile(str(doc)).toString(), "https://evil.example/x.exe"])
    assert c.count == n + 1 and pins.items[-1].name == "Cool Tool" and c.message == "Pinned Cool Tool"
    c.dropUrls([QUrl.fromLocalFile(str(doc)).toString()])
    assert c.count == n + 1 and "Only programs" in c.message


def test_pin_an_app_dialog(env):
    c, pins, launched, ctl, picked, tmp = env
    exe = tmp / "Picked.exe"; exe.write_text("x"); n = c.count
    picked["path"] = ""; c.addDialog(); assert c.count == n                       # cancelled
    picked["path"] = str(tmp / "ghost.exe"); c.addDialog(); assert c.count == n and "Only programs" in c.message
    picked["path"] = str(exe); c.addDialog(); assert c.count == n + 1 and c.message == "Pinned Picked"


def test_reset(env):
    c, pins, *_ = env
    c.remove(0); c.remove(0); c.reset()
    assert pins.items[0].name == "File Explorer" and "default" in c.message


# ---------------- voice + brain ----------------
@pytest.fixture
def asst(env, qapp, monkeypatch, tmp_path):
    c, pins, launched, ctl, *_ = env
    a = Assistant(ctl, Settings(tmp_path / "s2.json"), Store(tmp_path / "t.db"))
    a.apps = pins
    sys_calls = []
    monkeypatch.setattr(mod.win, "open_app", lambda n: sys_calls.append(n) or True)
    return a, ctl, launched, sys_calls


def test_voice_opens_any_start_menu_app_by_name(asst):
    a, ctl, launched, sys_calls = asst
    a.handle_text("open photoshop")
    assert launched and launched[-1].endswith("Photoshop.lnk") and sys_calls == []


def test_well_known_names_keep_their_exact_windows_mapping(asst):
    a, ctl, launched, sys_calls = asst
    a.handle_text("open notepad")                     # 'notepad' is a built-in alias: no fuzzy matching
    assert sys_calls == ["notepad"] and launched == []


def test_unknown_app_falls_back_to_windows(asst):
    a, ctl, launched, sys_calls = asst
    a.handle_text("open frobnicator")
    assert sys_calls == ["frobnicator"]


@pytest.mark.parametrize("text", ["show my apps", "open the app launcher", "bring up the apps", "my apps"])
def test_voice_opens_the_apps_panel(asst, text):
    a, ctl, *_ = asst
    assert parse(text).name == "apps_open"
    a.handle_text(text, src="button")
    assert ctl.mode == "apps"


def test_open_x_is_not_mistaken_for_the_apps_panel():
    assert parse("open spotify").name == "open_app" and parse("open my notes app").name == "open_app"


def test_brain_apps_tool_needs_justification():
    class F:
        def chat(self, m, **k): return '{"tool": "apps_open", "args": {}}'
    b = Brain(F(), name="Nur"); now = datetime(2026, 11, 25, 4, 6)
    assert b.route("lower the glare on my monitor", now).intent is None
    assert b.route("show me the launcher with my programs", now).intent.name == "apps_open"
