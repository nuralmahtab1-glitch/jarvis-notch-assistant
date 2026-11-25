import json
from pathlib import Path
import pytest
from app.core.apps import (AppEntry, PinnedApps, default_apps, entry_from_path, resolve, start_menu_index, MAX_PINNED)
from app.store.db import Settings


def make_menu(tmp_path, names):
    root = tmp_path / "Programs"; root.mkdir()
    for n in names:
        (root / f"{n}.lnk").write_text("x")
    sub = root / "Some Vendor"; sub.mkdir()
    (sub / "Vendor Studio.lnk").write_text("x"); (sub / "Uninstall Vendor Studio.lnk").write_text("x"); (sub / "Vendor Studio Help.lnk").write_text("x")
    return start_menu_index([root])


def test_index_skips_junk_and_walks_subfolders(tmp_path):
    idx = make_menu(tmp_path, ["Google Chrome", "Spotify", "README"])
    assert "Google Chrome" in idx and "Vendor Studio" in idx
    assert not any("Uninstall" in n or "Help" in n or n == "README" for n in idx)


def test_resolve_prefers_exact_then_prefix_then_word_then_substring(tmp_path):
    idx = {"Spotify": "a", "Spotify Beta": "b", "Visual Studio Code": "c", "Code Blocks": "d", "Microsoft Edge": "e"}
    assert resolve("spotify", idx)[0] == "Spotify"                  # exact beats the longer name
    assert resolve("visual studio", idx)[0] == "Visual Studio Code"  # prefix
    assert resolve("edge", idx)[0] == "Microsoft Edge"               # whole word
    assert resolve("sual stud", idx)[0] == "Visual Studio Code"      # substring
    assert resolve("photoshop", idx) is None and resolve("a", idx) is None


def test_defaults_include_builtins_and_only_apps_you_have(tmp_path):
    idx = make_menu(tmp_path, ["Google Chrome", "Spotify"])
    names = [e.name for e in default_apps(idx)]
    assert names[:4] == ["File Explorer", "Notepad", "Calculator", "Settings"]
    assert "Google Chrome" in names and "Spotify" in names and "Discord" not in names


def test_entry_from_path_accepts_programs_only(tmp_path):
    exe = tmp_path / "Tool.exe"; exe.write_text("x")
    doc = tmp_path / "notes.txt"; doc.write_text("x")
    assert entry_from_path(exe).name == "Tool" and entry_from_path(doc) is None and entry_from_path(tmp_path / "ghost.exe") is None


@pytest.fixture
def pins(tmp_path):
    cfg = Settings(tmp_path / "s.json"); launched = []
    idx = make_menu(tmp_path, ["Google Chrome", "Photoshop"])
    return PinnedApps(cfg, idx, launcher=launched.append), launched, cfg


def test_first_run_saves_defaults_and_they_persist(pins, tmp_path):
    p, launched, cfg = pins
    assert [e.name for e in p.items][:2] == ["File Explorer", "Notepad"]
    again = PinnedApps(Settings(cfg.path), {}, launcher=launched.append)
    assert [e.name for e in again.items] == [e.name for e in p.items]


def test_add_remove_dedupe_and_limit(pins, tmp_path):
    p, launched, cfg = pins
    exe = tmp_path / "MyTool.exe"; exe.write_text("x")
    n = len(p.items)
    p.add(exe); p.add(exe)
    assert len(p.items) == n + 1 and p.items[-1].name == "MyTool"
    assert p.remove(len(p.items) - 1) and len(p.items) == n and not p.remove(99)
    assert json.loads(cfg.path.read_text())["pinned_apps"][0]["name"] == "File Explorer"
    for i in range(MAX_PINNED + 3):
        f = tmp_path / f"a{i}.exe"; f.write_text("x"); p.add(f)
    assert len(p.items) <= MAX_PINNED


def test_launch_calls_the_launcher_and_survives_failures(pins):
    p, launched, cfg = pins
    assert p.launch(1) and launched == [p.items[1].target]
    assert not p.launch(-1) and not p.launch(500)
    p.launcher = lambda t: (_ for _ in ()).throw(OSError("nope"))
    assert p.launch(0) is False


def test_voice_launch_by_name_searches_pinned_then_start_menu(pins):
    p, launched, cfg = pins
    assert p.launch_by_name("notepad") == "Notepad" and launched[-1] == "notepad.exe"
    assert p.launch_by_name("photoshop") == "Photoshop" and launched[-1].endswith("Photoshop.lnk")
    assert p.launch_by_name("nonexistent thing") is None


def test_reset_restores_defaults(pins, tmp_path):
    p, launched, cfg = pins
    p.remove(0); p.remove(0)
    p.reset()
    assert p.items[0].name == "File Explorer"


def test_aliases_find_what_people_actually_say():
    idx = {"Visual Studio Code": "vs", "Google Chrome": "ch", "Windows Terminal": "wt", "OBS Studio": "obs"}
    for said, want in (("vs code", "Visual Studio Code"), ("vscode", "Visual Studio Code"), ("chrome", "Google Chrome"),
                       ("terminal", "Windows Terminal"), ("obs", "OBS Studio")):
        assert resolve(said, idx)[0] == want, said


def test_defaults_never_guess_loosely():
    """A trading app called '... Terminal' must not be pinned as if it were Windows Terminal."""
    idx = {"PU Prime MT5 Terminal": "x", "Word Counter Pro": "y", "Microsoft Word": "z"}
    names = [e.name for e in default_apps(idx)]
    assert "PU Prime MT5 Terminal" not in names and "Word Counter Pro" not in names
