import sys, zipfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging"))
import setup_app as sa                      # noqa: E402
import app.uninstall as un                  # noqa: E402


def make_payload(tmp_path, extra=None):
    p = tmp_path / "payload.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Jarvis.exe", "exe"); z.writestr("_internal/lib.dll", "dll"); z.writestr("jarvis-hook.exe", "hook")
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return p


@pytest.fixture(autouse=True)
def no_side_effects(monkeypatch):
    """Never touch the real registry, shortcuts or running processes in these tests."""
    reg = MagicMock()
    monkeypatch.setattr(sa, "winreg", reg)
    monkeypatch.setattr(sa, "kill_other_instances", lambda: None)
    links = []
    monkeypatch.setattr(sa, "make_shortcut", lambda link, target, wd: links.append(link))
    return reg, links


def test_rejects_drive_root_and_foreign_folders(tmp_path):
    assert sa.check_destination(Path("C:\\")) is not None
    foreign = tmp_path / "Documents"; foreign.mkdir(); (foreign / "thesis.docx").write_text("precious")
    assert "other files" in sa.check_destination(foreign)


def test_accepts_new_empty_and_existing_install(tmp_path):
    assert sa.check_destination(tmp_path / "new" / "Jarvis") is None
    e = tmp_path / "empty"; e.mkdir(); assert sa.check_destination(e) is None
    i = tmp_path / "inst"; (i / "_internal").mkdir(parents=True); (i / "Jarvis.exe").write_text("x")
    assert sa.check_destination(i) is None


def test_install_extracts_everything_and_reports_progress(tmp_path, no_side_effects):
    reg, links = no_side_effects
    seen = []
    sa.install(tmp_path / "Jarvis", make_payload(tmp_path), start_menu=True, desktop=True, progress=lambda f, t: seen.append((f, t)))
    d = tmp_path / "Jarvis"
    assert (d / "Jarvis.exe").read_text() == "exe" and (d / "_internal" / "lib.dll").exists() and (d / "jarvis-hook.exe").exists()
    assert seen[-1][0] == seen[-1][1] and len(links) == 2


def test_install_registers_uninstall_entry_with_author(tmp_path, no_side_effects):
    reg, _ = no_side_effects
    sa.install(tmp_path / "Jarvis", make_payload(tmp_path))
    calls = [c for c in reg.SetValueEx.call_args_list]
    vals = {c.args[1]: c.args[4] for c in calls}
    assert vals["Publisher"] == "Nur Al Mahtab" and vals["DisplayName"] == "Jarvis"
    assert vals["UninstallString"].endswith("Jarvis.exe\" --uninstall")


def test_autostart_is_off_unless_asked(tmp_path, no_side_effects):
    reg, _ = no_side_effects
    sa.install(tmp_path / "A", make_payload(tmp_path))
    assert not any(c.args[0] == "Jarvis" for c in reg.SetValueEx.call_args_list)
    sa.install(tmp_path / "B", make_payload(tmp_path), autostart=True)
    assert any(c.args[1] == "Jarvis" for c in reg.SetValueEx.call_args_list)


def test_upgrade_removes_stale_files_from_the_old_version(tmp_path):
    d = tmp_path / "Jarvis"
    sa.install(d, make_payload(tmp_path, {"_internal/old_only.dll": "stale"}))
    assert (d / "_internal" / "old_only.dll").exists()
    sa.install(d, make_payload(tmp_path))
    assert not (d / "_internal" / "old_only.dll").exists() and (d / "Jarvis.exe").exists()


def test_refuses_foreign_folder_and_leaves_it_untouched(tmp_path):
    foreign = tmp_path / "MyStuff"; foreign.mkdir(); (foreign / "keep.txt").write_text("mine")
    with pytest.raises(RuntimeError):
        sa.install(foreign, make_payload(tmp_path))
    assert (foreign / "keep.txt").read_text() == "mine" and not (foreign / "Jarvis.exe").exists()


def test_zip_slip_is_blocked(tmp_path):
    evil = make_payload(tmp_path, {"../escaped.txt": "gotcha"})
    with pytest.raises(RuntimeError):
        sa.install(tmp_path / "Jarvis", evil)
    assert not (tmp_path / "escaped.txt").exists()


def test_silent_mode_exit_codes(tmp_path, monkeypatch):
    payload = make_payload(tmp_path)
    ok = sa.silent(["/S", "--dir", str(tmp_path / "Good"), "--payload", str(payload), "--no-launch"])
    assert ok == 0 and (tmp_path / "Good" / "Jarvis.exe").exists()
    foreign = tmp_path / "Foreign"; foreign.mkdir(); (foreign / "x").write_text("x")
    assert sa.silent(["/S", f"/D={foreign}", "--payload", str(payload), "--no-launch"]) == 2


# ---------------------------------------------------------------- uninstall
def test_uninstall_keeps_data_by_default_and_schedules_folder_removal(tmp_path, monkeypatch):
    data, models = tmp_path / "appdata" / "Jarvis", tmp_path / "local" / "Jarvis" / "models"
    data.mkdir(parents=True); models.mkdir(parents=True); (data / "settings.json").write_text("{}")
    target = tmp_path / "Programs" / "Jarvis"; target.mkdir(parents=True)
    monkeypatch.setattr("app.store.db.data_dir", lambda: data)
    monkeypatch.setattr(un.paths, "install_dir", lambda: target)
    monkeypatch.setattr(un.paths, "user_models", lambda: models)
    monkeypatch.setattr(un, "kill_other_instances", lambda: None)
    monkeypatch.setattr(un, "remove_registry", lambda: None)
    monkeypatch.setattr(un, "shortcut_paths", lambda: [])
    monkeypatch.setattr("app.claude_bridge.installer.disconnect", lambda *a, **k: None)
    popen = MagicMock(); monkeypatch.setattr(un.subprocess, "Popen", popen)
    assert un.run(silent=True) == 0
    assert (data / "settings.json").exists() and models.exists()                  # your data survives by default
    bat = Path(un.tempfile.gettempdir()) / "jarvis-uninstall.bat"
    assert f'rmdir /s /q "{target}"' in bat.read_text()
    assert popen.called
    assert un.run(silent=True, delete_data=True) == 0
    assert not data.exists() and not models.parent.exists()                       # ...unless you ask for it
    bat.unlink(missing_ok=True)


def test_uninstall_can_be_declined(monkeypatch):
    monkeypatch.setattr(un, "ask_yes_no", lambda *a: False)
    assert un.run(silent=False) == 1
