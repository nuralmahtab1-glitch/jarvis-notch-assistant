import json, os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from app.llm import manager


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "ROOT", tmp_path)
    monkeypatch.setattr(manager, "LLM_DIR", tmp_path / "llm")
    monkeypatch.setattr(manager, "CUSTOM_FILE", tmp_path / "custom.json")
    return tmp_path


def gguf(path, size=2 * 1024 ** 2, magic=b"GGUF"):
    path.write_bytes(magic + b"\0" * (size - 4)); return path


def test_import_registers_copies_and_reports_installed(mgr):
    src = gguf(mgr / "My Model (v2).gguf")
    rec = manager.import_gguf(src)
    assert rec["id"].startswith("custom-") and manager.is_installed(rec["id"])
    assert (mgr / "llm" / "My Model (v2).gguf").exists() and src.exists()          # copied, original untouched
    assert rec in manager.all_models() and manager.model_path(rec["id"]).name == "My Model (v2).gguf"


@pytest.mark.parametrize("name,magic", [("notes.txt", b"GGUF"), ("fake.gguf", b"ZIP!"), ("missing.gguf", None)])
def test_bad_files_are_refused(mgr, name, magic):
    p = mgr / name
    if magic: gguf(p, magic=magic)
    with pytest.raises(ValueError):
        manager.import_gguf(p)
    assert manager.custom_models() == []


def test_same_name_twice_gets_distinct_ids_and_files(mgr):
    a = manager.import_gguf(gguf(mgr / "m.gguf"))
    (mgr / "other").mkdir(); b = manager.import_gguf(gguf(mgr / "other" / "m.gguf"))
    assert a["id"] != b["id"] and a["file"] != b["file"]


def test_limit_of_eight(mgr):
    for i in range(manager.MAX_CUSTOM):
        manager.import_gguf(gguf(mgr / f"m{i}.gguf", size=1024 ** 2 + 8))
    with pytest.raises(ValueError, match="8 models"):
        manager.import_gguf(gguf(mgr / "extra.gguf"))


def test_remove_deletes_file_and_entry_only_for_custom(mgr):
    rec = manager.import_gguf(gguf(mgr / "m.gguf"))
    manager.remove(rec["id"])
    assert manager.custom_models() == [] and not (mgr / "llm" / "m.gguf").exists()
    manager.remove("qwen3-1.7b")                                                  # catalog entries still use the normal path


def test_tampered_registry_cannot_point_outside_the_models_folder(mgr):
    (mgr / "custom.json").write_text(json.dumps([
        {"id": "custom-x", "file": "..\..\evil.gguf", "name": "x", "size_gb": 1},
        {"id": "custom-y", "file": "C:\Windows\a.gguf", "name": "y", "size_gb": 1},
        {"id": "not-custom", "file": "ok.gguf", "name": "z", "size_gb": 1}]))
    assert manager.custom_models() == []
    (mgr / "custom.json").write_text("{broken")
    assert manager.custom_models() == []


def test_install_of_missing_imported_file_fails_clearly(mgr):
    rec = manager.import_gguf(gguf(mgr / "m.gguf"))
    (mgr / "llm" / "m.gguf").unlink()
    with pytest.raises(FileNotFoundError):
        manager.install_model(rec["id"])


def test_unknown_model_is_simply_not_installed(mgr):
    assert manager.is_installed("custom-nothing") is False


def test_settings_import_selects_the_model_and_reports_errors(mgr, tmp_path):
    from PySide6.QtWidgets import QApplication
    from app.core.assistant import Assistant
    from app.store.db import Settings, Store
    from app.ui.controller import NotchController
    from app.ui.settings_ctl import SettingsController
    QApplication.instance() or QApplication([])
    cfg = Settings(tmp_path / "s.json"); ctl = NotchController(); a = Assistant(ctl, cfg, Store(tmp_path / "t.db"))
    sc = SettingsController(a, ctl, cfg, a.store, [], {})
    sc.importModel(str(mgr / "nope.gguf"))
    assert "not a .gguf" in sc.message and cfg["llm_model"] == "qwen3-1.7b"
    sc.importModel('"' + str(gguf(mgr / "mine.gguf")) + '"')                      # pasted paths often have quotes
    assert cfg["llm_model"].startswith("custom-") and "Imported" in sc.message
    assert any(m["id"] == cfg["llm_model"] and m["installed"] for m in sc.brainModels)
    sc.set("llm_model", "custom-does-not-exist")                                   # unknown ids are still refused
    assert cfg["llm_model"].startswith("custom-mine")
