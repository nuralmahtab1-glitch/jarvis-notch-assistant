"""Uninstall: run by the installed app itself (`Jarvis.exe --uninstall`). Made by Nur Al Mahtab.

Cleans up everything the installer and the app created: running processes, Claude Code hooks,
start-with-Windows entry, shortcuts and the Add/Remove Programs entry. Your personal data is only
deleted if you say yes. The program files are removed by a tiny helper script after this process exits
(a program cannot delete itself while it is running).
"""
from __future__ import annotations
import ctypes, os, shutil, subprocess, sys, tempfile, winreg
from pathlib import Path

from app import config, paths

UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Jarvis"


def start_menu_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def shortcut_paths() -> list[Path]:
    desktop = Path.home() / "Desktop"
    return [start_menu_dir() / f"{config.APP_NAME}.lnk", desktop / f"{config.APP_NAME}.lnk"]


def ask_yes_no(title: str, text: str) -> bool:
    return ctypes.windll.user32.MessageBoxW(0, text, title, 0x24) == 6      # MB_YESNO | MB_ICONQUESTION -> IDYES


def kill_other_instances() -> None:
    """Stop Jarvis and its helpers (except this process) so files are not locked."""
    me = os.getpid()
    for name in ("Jarvis.exe", "jarvis-hook.exe", "llama-server.exe"):
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, creationflags=0x08000000).stdout
        for line in out.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) > 1 and parts[0].lower() == name.lower() and parts[1].isdigit() and int(parts[1]) != me:
                subprocess.run(["taskkill", "/F", "/PID", parts[1]], capture_output=True, creationflags=0x08000000)


def remove_registry() -> None:
    for root, key, value in ((winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", config.APP_NAME),):
        try:
            with winreg.OpenKey(root, key, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, value)
        except OSError:
            pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass


def removal_script(target: Path, tries: int = 8) -> str:
    """Batch file that deletes `target`, retrying if something still holds a file, then deletes itself."""
    lines = [
        "@echo off",
        "set /a n=0",
        ":retry",
        "ping 127.0.0.1 -n 3 >nul",
        f'rmdir /s /q "{target}" 2>nul',
        f'if not exist "{target}" goto done',
        "set /a n+=1",
        f"if %n% lss {tries} goto retry",
        ":done",
        '(goto) 2>nul & del "%~f0"',
    ]
    return "\r\n".join(lines) + "\r\n"


def run(silent: bool = False, delete_data: bool | None = None) -> int:
    from app.claude_bridge import installer
    from app.store.db import data_dir

    if not silent and not ask_yes_no(f"Uninstall {config.APP_NAME}", f"Remove {config.APP_NAME} from this PC?"):
        return 1
    if delete_data is None:
        delete_data = False if silent else ask_yes_no(
            f"Uninstall {config.APP_NAME}",
            "Also delete your Jarvis data (settings, list, reminders) and downloaded models (speech model and AI brain)?\n\n"
            "Choose No to keep them, so a reinstall picks up where you left off.")

    kill_other_instances()
    try:
        installer.disconnect()                       # remove only OUR Claude Code hooks (backs up first)
    except Exception:
        pass
    remove_registry()
    for p in shortcut_paths():
        try:
            p.unlink()
        except OSError:
            pass
    if delete_data:
        for d in (data_dir(), paths.user_models().parent):
            shutil.rmtree(d, ignore_errors=True)

    # the install folder is deleted by a helper after we exit (retrying: antivirus or a slow disk can hold a file briefly)
    target = paths.install_dir()
    bat = Path(tempfile.gettempdir()) / "jarvis-uninstall.bat"
    bat.write_text(removal_script(target), encoding="utf-8")
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=0x08000000 | 0x00000008, close_fds=True)
    if not silent:
        ctypes.windll.user32.MessageBoxW(0, f"{config.APP_NAME} was removed.\n\n{config.CREDIT}", f"{config.APP_NAME}", 0x40)
    return 0
