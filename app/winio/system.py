"""Windows integration: typing, volume, screenshots, apps, media keys. Made by Nur Al Mahtab."""
from __future__ import annotations
import ctypes, os, subprocess, time, webbrowser
from ctypes import wintypes
from pathlib import Path
from urllib.parse import quote

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN, VK_CONTROL, VK_V = 0x0D, 0x11, 0x56
VK_MEDIA_NEXT, VK_MEDIA_PREV, VK_MEDIA_PLAY = 0xB0, 0xB1, 0xB3


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _send(inputs):
    arr = (INPUT * len(inputs))(*inputs)
    return user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _key(vk=0, scan=0, flags=0):
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, scan, flags, 0, 0))


def foreground_window() -> int:
    return user32.GetForegroundWindow()


def window_title(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def window_process_name(hwnd: int) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(h)
    return ""


def type_text(text: str, delay: float = 0.0) -> None:
    """Type text into whatever window has focus using Unicode key events (layout independent)."""
    for ch in text:
        if ch == "\n":
            _send([_key(VK_RETURN), _key(VK_RETURN, flags=KEYEVENTF_KEYUP)])
        else:
            code = ord(ch)
            if code > 0xFFFF:  # surrogate pair
                code -= 0x10000
                hi, lo = 0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)
                units = [hi, lo]
            else:
                units = [code]
            evs = []
            for u in units:
                evs += [_key(0, u, KEYEVENTF_UNICODE), _key(0, u, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
            _send(evs)
        if delay:
            time.sleep(delay)


def paste_text(text: str) -> None:
    """Fallback: clipboard paste (restores nothing; used when typing is blocked)."""
    subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"],
                   input=text, text=True, timeout=5)
    _send([_key(VK_CONTROL), _key(VK_V), _key(VK_V, flags=KEYEVENTF_KEYUP), _key(VK_CONTROL, flags=KEYEVENTF_KEYUP)])


def is_elevated(hwnd: int) -> bool:
    """True if the target window belongs to an elevated process (we cannot type into it)."""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h:
        return True
    kernel32.CloseHandle(h)
    return False


def media_key(vk: int) -> None:
    _send([_key(vk), _key(vk, flags=KEYEVENTF_KEYUP)])


def media_play_pause(): media_key(VK_MEDIA_PLAY)
def media_next(): media_key(VK_MEDIA_NEXT)
def media_prev(): media_key(VK_MEDIA_PREV)


# ---------------- volume (pycaw) ----------------
def _endpoint():
    from pycaw.pycaw import AudioUtilities
    return AudioUtilities.GetSpeakers().EndpointVolume


def get_volume() -> int:
    return round(_endpoint().GetMasterVolumeLevelScalar() * 100)


def set_volume(level: int) -> int:
    level = max(0, min(100, int(level)))
    _endpoint().SetMasterVolumeLevelScalar(level / 100.0, None)
    return level


def change_volume(delta: int) -> int:
    return set_volume(get_volume() + delta)


def toggle_mute() -> bool:
    ep = _endpoint()
    new = not ep.GetMute()
    ep.SetMute(new, None)
    return bool(new)


# ---------------- misc actions ----------------
def screenshot() -> Path:
    from PIL import ImageGrab
    folder = Path.home() / "Pictures" / "Screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / time.strftime("Jarvis %Y-%m-%d %H-%M-%S.png")
    ImageGrab.grab(all_screens=True).save(path)
    return path


APP_ALIASES = {
    "chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "browser": "msedge",
    "notepad": "notepad", "calculator": "calc", "calc": "calc", "paint": "mspaint",
    "file explorer": "explorer", "explorer": "explorer", "files": "explorer",
    "task manager": "taskmgr", "settings": "ms-settings:", "terminal": "wt", "command prompt": "cmd",
    "powershell": "powershell", "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "spotify": "spotify:", "discord": "discord", "vs code": "code", "vscode": "code", "visual studio code": "code",
    "camera": "microsoft.windows.camera:", "calendar": "outlookcal:", "mail": "outlookmail:",
    "whatsapp": "whatsapp:", "steam": "steam:", "snipping tool": "snippingtool",
}


def open_app(name: str) -> bool:
    key = name.lower().strip().removeprefix("the ").removesuffix(" app")
    target = APP_ALIASES.get(key, key)
    try:
        if target.endswith(":"):
            os.startfile(target)
        else:
            subprocess.Popen(["cmd", "/c", "start", "", target], creationflags=0x08000000)
        return True
    except Exception:
        return False


def open_url(url: str) -> None:
    if "://" not in url:
        url = "https://" + url
    webbrowser.open(url)


def search_web(query: str) -> None:
    webbrowser.open("https://www.google.com/search?q=" + quote(query))


def play_spotify(query: str) -> None:
    try:
        os.startfile("spotify:search:" + quote(query))
    except Exception:
        webbrowser.open("https://open.spotify.com/search/" + quote(query))


def battery() -> tuple[int | None, bool]:
    import psutil
    b = psutil.sensors_battery()
    return (round(b.percent), bool(b.power_plugged)) if b else (None, False)
