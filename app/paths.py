"""Where things live, whether running from source or from the installed (frozen) app. Made by Nur Al Mahtab."""
from __future__ import annotations
import os, sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def app_dir() -> Path:
    """Folder holding bundled read-only files (QML, the Piper voice, ...)."""
    return Path(getattr(sys, "_MEIPASS", project_root())) if FROZEN else project_root()


def install_dir() -> Path:
    """Folder containing the executable (installed app) or the project (source)."""
    return Path(sys.executable).resolve().parent if FROZEN else project_root()


def user_models() -> Path:
    """Writable place for downloaded models (speech model, AI brain). Not inside the install folder."""
    if FROZEN:
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Jarvis" / "models"
    return project_root() / "models"


def bundled_models() -> Path:
    """Read-only models shipped inside the installer (the British voice)."""
    return app_dir() / "models"


def qml(name: str) -> Path:
    return app_dir() / "app" / "ui" / "qml" / name
