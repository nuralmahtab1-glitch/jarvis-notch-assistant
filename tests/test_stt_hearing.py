import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from app.stt.whisper_stt import Transcriber


def test_quiet_microphone_is_brought_up():
    a = (np.sin(np.linspace(0, 200, 16000)) * 0.05).astype(np.float32)
    b = Transcriber.level_fix(a)
    assert abs(float(np.abs(b).max()) - 0.7) < 0.01 and b.dtype == np.float32


def test_normal_and_silent_audio_are_left_alone():
    loud = (np.sin(np.linspace(0, 200, 16000)) * 0.6).astype(np.float32)
    assert np.array_equal(Transcriber.level_fix(loud), loud)
    silence = np.zeros(16000, np.float32)
    assert np.array_equal(Transcriber.level_fix(silence), silence)             # never amplify pure silence into noise
    hiss = (np.random.default_rng(1).normal(0, 0.0005, 16000)).astype(np.float32)
    assert float(np.abs(Transcriber.level_fix(hiss)).max()) < 0.01


def test_level_fix_never_clips():
    a = (np.random.default_rng(2).normal(0, 0.02, 16000)).astype(np.float32)
    assert float(np.abs(Transcriber.level_fix(a)).max()) <= 1.0


def _assistant(tmp_path):
    from PySide6.QtWidgets import QApplication
    from app.core.assistant import Assistant
    from app.store.db import Settings, Store
    from app.ui.controller import NotchController
    QApplication.instance() or QApplication([])
    return Assistant(NotchController(), Settings(tmp_path / "s.json"), Store(tmp_path / "t.db"))


def test_command_hint_includes_your_sites_and_stays_short(tmp_path):
    a = _assistant(tmp_path)
    a.cfg.set("websites", ["https://www.myblog.dev/home", "youtube.com"])
    h = a.command_hint()
    assert "Jarvis" in h and "myblog" in h and "youtube" in h and len(h) <= 400


def test_command_hint_survives_bad_settings(tmp_path):
    a = _assistant(tmp_path)
    a.cfg.data["websites"] = None
    assert "Jarvis" in a.command_hint()


def test_dictation_gets_no_command_hint_but_commands_do(tmp_path):
    a = _assistant(tmp_path); seen = []
    class Stt:
        def transcribe(self, audio, prompt=""): seen.append(prompt); return ""
    a.stt = Stt(); a.ui = lambda f: None
    a._process(np.zeros(16000, np.float32), "dictate", "key", 0)
    a._process(np.zeros(16000, np.float32), "command", "key", 0)
    assert seen[0] == "" and "Jarvis" in seen[1]


def test_choosing_a_model_yourself_is_remembered(tmp_path):
    from app.ui.settings_ctl import SettingsController
    a = _assistant(tmp_path)
    sc = SettingsController(a, a.ctl, a.cfg, a.store, [], {})
    assert a.cfg["stt_model"] == "base.en" and a.cfg["stt_chosen"] is False
    sc.set("stt_model", "tiny.en")
    assert a.cfg["stt_model"] == "tiny.en" and a.cfg["stt_chosen"] is True
