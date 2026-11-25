import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from app.tools.intents import parse
from app.winio import layout


@pytest.mark.parametrize("text,items", [
    ("open youtube and chrome side by side each other", ["youtube", "chrome"]),
    ("open youtube and chrome side by side", ["youtube", "chrome"]),
    ("put chrome and notepad next to each other", ["chrome", "notepad"]),
    ("Hey Jarvis, open spotify and discord split screen", ["spotify", "discord"]),
    ("open the calculator and paint beside each other", ["calculator", "paint"]),
])
def test_side_by_side_phrases(text, items):
    it = parse(text)
    assert it.name == "side_by_side" and it.args["items"] == items


@pytest.mark.parametrize("text,side", [("snap this window to the left", "left"), ("move the window to the right", "right"),
                                       ("put this window to the right half", "right")])
def test_snap_phrases(text, side):
    it = parse(text)
    assert it.name == "snap_window" and it.args["side"] == side


def test_open_two_things_without_side_by_side():
    assert parse("open youtube and chrome").args == {"items": ["youtube", "chrome"]} and parse("open youtube and chrome").name == "open_many"
    assert parse("open the calculator, paint and notepad").args["items"] == ["calculator", "paint", "notepad"]


@pytest.mark.parametrize("text", ["open notepad", "open youtube", "launch spotify", "open file explorer",
                                  "what is side by side", "open the pod bay doors and tell me a long story about it please now"])
def test_single_or_unrelated_requests_are_not_layouts(text):
    it = parse(text)
    assert it is None or it.name not in ("side_by_side", "open_many", "snap_window")


def test_half_rects_split_the_work_area_exactly():
    left, right = layout.half_rects((0, 0, 1920, 1008))
    assert left == (0, 0, 960, 1008) and right == (960, 0, 960, 1008)
    left, right = layout.half_rects((1920, 40, 3841, 1000))               # odd width, second monitor: no gap, no overlap
    assert left[0] + left[2] == right[0] and right[0] + right[2] == 3841 and left[0] == 1920


def test_resolve_sites_browsers_and_apps():
    assert layout.resolve("youtube") == {"kind": "site", "label": "Youtube", "url": "https://youtube.com"}
    assert layout.resolve("Chrome")["kind"] == "browser" and layout.resolve("chrome")["exe"] == "chrome.exe"
    assert layout.resolve("github.com")["url"] == "https://github.com"
    assert layout.resolve("notepad")["kind"] == "app"
    assert layout.resolve("my blog", ["https://myblog.dev"])["kind"] == "app"
    assert layout.resolve("myblog", ["https://myblog.dev"])["url"] == "https://myblog.dev"
    assert layout.resolve("calc.exe")["kind"] == "app" and layout.resolve("evil.bat")["kind"] == "app"     # files are never treated as sites


def test_open_many_launches_each_target_in_a_new_window(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from app.core.assistant import Assistant
    from app.store.db import Settings, Store
    from app.ui.controller import NotchController
    import tempfile, pathlib
    QApplication.instance() or QApplication([])
    d = pathlib.Path(tempfile.mkdtemp())
    a = Assistant(NotchController(), Settings(d / "s.json"), Store(d / "t.db"))
    seen = []
    monkeypatch.setattr(layout, "launch", lambda spec, hint, start_app, favourites=None: seen.append((spec["label"], spec["kind"], hint)) or True)
    reply = a.run_intent(parse("open youtube and chrome"))
    assert reply == "Opening Youtube and Chrome." and seen == [("Youtube", "site", "chrome.exe"), ("Chrome", "browser", "chrome.exe")]
    monkeypatch.setattr(layout, "launch", lambda spec, hint, start_app, favourites=None: spec["label"] != "Chrome")
    assert a.run_intent(parse("open youtube and chrome")) == "I opened Youtube, but could not open Chrome."


def test_open_youtube_alone_opens_the_website(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from app.core.assistant import Assistant
    from app.store.db import Settings, Store
    from app.ui.controller import NotchController
    from app.winio import system as win
    import tempfile, pathlib
    QApplication.instance() or QApplication([])
    d = pathlib.Path(tempfile.mkdtemp())
    a = Assistant(NotchController(), Settings(d / "s.json"), Store(d / "t.db"))
    opened = []
    monkeypatch.setattr(win, "open_url", opened.append)
    assert a.run_intent(parse("open youtube")) == "Opening Youtube." and opened == ["https://youtube.com"]


# ---------------- chained commands and site search (from the user's real failures) ----------------
@pytest.mark.parametrize("text,steps", [
    ("open youtube and after that search for avengers", ["open youtube", "search for avengers"]),
    ("open youtube then search for avengers", ["open youtube", "search for avengers"]),
    ("open spotify, then play jazz", ["open spotify", "play jazz"]),
])
def test_chained_commands(text, steps):
    assert parse(text).name == "chain" and parse(text).args["steps"] == steps


def test_chain_does_not_swallow_reminders_or_todos():
    assert parse("remind me to buy milk and then call mum").name == "set_reminder"
    assert parse("add milk then eggs to my list") is None or parse("add milk then eggs to my list").name != "chain"


def test_google_chrome_and_youtube_opens_both():
    it = parse("open google chrome and youtube")
    assert it.name == "open_many" and it.args["items"] == ["google chrome", "youtube"]


@pytest.mark.parametrize("text,site,query", [
    ("search youtube for avengers trailer", "youtube", "avengers trailer"),
    ("search for batman on youtube", "youtube", "batman"),
    ("find the best laptop on amazon", "amazon", "the best laptop"),
    ("youtube search lofi beats", "youtube", "lofi beats"),
])
def test_site_search(text, site, query):
    it = parse(text)
    assert it.name == "search_site" and it.args == {"site": site, "query": query}


def test_plain_search_has_no_leftover_for():
    assert parse("search for pizza near me").args["query"] == "pizza near me"
    assert parse("search pizza near me").args["query"] == "pizza near me"


def _assistant(tmp_path):
    from PySide6.QtWidgets import QApplication
    from app.core.assistant import Assistant
    from app.store.db import Settings, Store
    from app.ui.controller import NotchController
    QApplication.instance() or QApplication([])
    return Assistant(NotchController(), Settings(tmp_path / "s.json"), Store(tmp_path / "t.db"))


def test_search_site_opens_the_right_results_page(monkeypatch, tmp_path):
    from app.winio import system as win
    a, opened = _assistant(tmp_path), []
    monkeypatch.setattr(win, "open_url", opened.append)
    assert a.run_intent(parse("search youtube for avengers trailer")) == "Searching Youtube for avengers trailer."
    assert opened == ["https://www.youtube.com/results?search_query=avengers%20trailer"]


def test_chain_opens_youtube_then_searches_on_youtube(monkeypatch, tmp_path):
    import time
    from PySide6.QtWidgets import QApplication
    from app.winio import system as win
    a, opened, said = _assistant(tmp_path), [], []
    monkeypatch.setattr(win, "open_url", opened.append)
    monkeypatch.setattr(a, "say", lambda text, src="key", **kw: said.append(text))
    a.run_intent(parse("open youtube and after that search for avengers"))
    end = time.time() + 8
    while not said and time.time() < end:
        QApplication.processEvents(); time.sleep(0.02)
    assert opened == ["https://youtube.com", "https://www.youtube.com/results?search_query=avengers"]
    assert said == ["Opening Youtube. Searching Youtube for avengers."]
