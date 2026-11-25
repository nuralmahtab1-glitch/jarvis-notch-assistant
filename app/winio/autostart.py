"""Start with Windows (per-user, HKCU Run key). Made by Nur Al Mahtab."""
import sys, winreg
from pathlib import Path
from app import config

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
ROOT = Path(__file__).resolve().parents[2]


def command() -> str:
    pyw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pyw}" "{ROOT / "run.py"}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            winreg.QueryValueEx(k, config.APP_NAME)
            return True
    except OSError:
        return False


def set_enabled(on: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, config.APP_NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(k, config.APP_NAME)
            except OSError:
                pass
