"""Open things and arrange windows (side by side / snap left / snap right). Made by Nur Al Mahtab.

Windows 11 has its own snap feature, but it cannot be driven from outside, so Jarvis places the windows itself:
it launches each target, waits for the NEW window to appear, then moves it to the left or right half of the screen
that holds the mouse (the work area, so the taskbar is never covered).
"""
from __future__ import annotations
import ctypes, os, re, subprocess, time, winreg
from ctypes import wintypes as w
from typing import Callable

user32 = ctypes.windll.user32
dwm = ctypes.windll.dwmapi
SW_RESTORE = 9
SWP_NOZORDER, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x0004, 0x0010, 0x0040
DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 9, 14

SITES = {
    "youtube": "youtube.com", "google": "google.com", "gmail": "mail.google.com", "github": "github.com",
    "netflix": "netflix.com", "reddit": "reddit.com", "twitter": "x.com", "x": "x.com", "facebook": "facebook.com",
    "instagram": "instagram.com", "whatsapp web": "web.whatsapp.com", "linkedin": "linkedin.com", "amazon": "amazon.com",
    "wikipedia": "wikipedia.org", "twitch": "twitch.tv", "chatgpt": "chatgpt.com", "claude": "claude.ai",
    "google maps": "maps.google.com", "maps": "maps.google.com", "google drive": "drive.google.com", "drive": "drive.google.com",
    "tiktok": "tiktok.com", "pinterest": "pinterest.com", "disney plus": "disneyplus.com", "prime video": "primevideo.com",
}
BROWSERS = {"chrome": "chrome.exe", "google chrome": "chrome.exe", "edge": "msedge.exe", "microsoft edge": "msedge.exe",
            "browser": None, "firefox": "firefox.exe", "brave": "brave.exe"}
SIDE_PHRASES = (r"side[- ]?by[- ]?side|side (?:by|to) (?:each other|side)|next to each other|beside each other|beside one another|"
                r"split[- ]?screen|half and half|next to one another|alongside each other|side by each other|each other")


# ------------------------------------------------------------------ parsing (pure, unit-tested)
def parse_layout(text: str):
    """'open youtube and chrome side by side' -> ('side_by_side', ['youtube', 'chrome']); else None."""
    t = re.sub(r"\s+", " ", text.lower().strip().rstrip(".!?"))
    t = re.sub(r"^(hey |ok |okay )?jarvis[, ]*", "", t)
    m = re.match(r"(?:please |can you |could you )?(?:snap|move|put|dock) (?:this|the|my|current) (?:window|app|one)? ?(?:to )?(?:the )?(left|right)(?: side| half)?$", t)
    if m:
        return ("snap", [m.group(1)])
    if not re.search(SIDE_PHRASES, t):
        return None
    body = re.sub(SIDE_PHRASES, " ", t)
    body = re.sub(r"\b(?:on|in|at|with|to|by|each|other|both|please|for me|me|them|a|an)\b(?= |$)", " ", body)
    body = re.sub(r"^\s*(?:open|put|show|launch|start|place|arrange|set up|setup|get|bring up|split)\s+", " ", body)
    body = re.sub(r"\b(?:the|my)\s+", "", body)
    parts = [p.strip(" ,") for p in re.split(r"\s+and\s+|\s*,\s*|\s+&\s+|\s+plus\s+", body) if p.strip(" ,")]
    parts = [re.sub(r"^(?:open|launch|start)\s+", "", p) for p in parts]
    if len(parts) == 2 and all(1 <= len(p) <= 40 for p in parts):
        return ("side_by_side", parts)
    return None


def half_rects(work: tuple[int, int, int, int]):
    """work = (left, top, right, bottom) -> (left half, right half) rectangles as (x, y, w, h)."""
    l, t, r, b = work
    mid = l + (r - l) // 2
    return (l, t, mid - l, b - t), (mid, t, r - mid, b - t)


# ------------------------------------------------------------------ resolving what to open
def browser_path(exe: str | None = None) -> str | None:
    names = [exe] if exe else ["chrome.exe", "msedge.exe"]
    for n in names:
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{n}") as k:
                    p = winreg.QueryValue(k, None)
                    if p and os.path.exists(p):
                        return p
            except OSError:
                continue
    return None


def resolve(name: str, favourites: list[str] | None = None) -> dict:
    """-> {'kind': 'browser'|'site'|'app', 'label', ...}"""
    key = re.sub(r"\s+", " ", name.lower().strip()).removesuffix(" app").removesuffix(" website").removesuffix(" site")
    if key in BROWSERS:
        return {"kind": "browser", "label": key.title() if key != "browser" else "Browser", "exe": BROWSERS[key]}
    if key in SITES:
        return {"kind": "site", "label": key.title() if len(key) > 2 else key.upper(), "url": "https://" + SITES[key]}
    for f in favourites or []:
        host = re.sub(r"^https?://(www\.)?", "", f).split("/")[0]
        if key == host.split(".")[0].lower():
            return {"kind": "site", "label": key.title(), "url": f if "://" in f else "https://" + f}
    if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", key) and not key.endswith((".exe", ".bat", ".cmd", ".msi", ".lnk", ".ps1", ".vbs", ".js")):
        return {"kind": "site", "label": key, "url": "https://" + key}
    return {"kind": "app", "label": name.strip().title()}


# ------------------------------------------------------------------ windows
def _cloaked(hwnd) -> bool:
    v = ctypes.c_int(0)
    dwm.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(v), 4)
    return bool(v.value)


def visible_windows() -> set[int]:
    out: set[int] = set()
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)

    def cb(h, _):
        if user32.IsWindowVisible(h) and not _cloaked(h) and user32.GetWindowTextLengthW(h) > 0 and not user32.GetWindow(h, 4):
            ex = user32.GetWindowLongW(h, -20)
            if not (ex & 0x80):                       # skip tool windows (WS_EX_TOOLWINDOW)
                out.add(int(h))
        return True
    user32.EnumWindows(CB(cb), 0)
    return out


def work_area() -> tuple[int, int, int, int]:
    """Work area (no taskbar) of the monitor that holds the mouse."""
    class MI(ctypes.Structure):
        _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT), ("dwFlags", w.DWORD)]
    pt = w.POINT(); user32.GetCursorPos(ctypes.byref(pt))
    mon = user32.MonitorFromPoint(pt, 2)
    mi = MI(); mi.cbSize = ctypes.sizeof(MI)
    user32.GetMonitorInfoW(mon, ctypes.byref(mi))
    r = mi.rcWork
    return r.left, r.top, r.right, r.bottom


def place(hwnd: int, rect: tuple[int, int, int, int]) -> bool:
    """Move a window so its VISIBLE edges fill rect (Windows adds invisible borders, which we compensate for)."""
    x, y, ww, hh = rect
    want = (x, y, x + ww, y + hh)
    for attempt in range(5):              # some apps resize themselves just after opening: keep placing until it sticks
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetWindowPos(hwnd, 0, x, y, ww, hh, SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        wr, fr = w.RECT(), w.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(wr)) and dwm.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(fr), 16) == 0:
            dl, dt, dr, db = fr.left - wr.left, fr.top - wr.top, wr.right - fr.right, wr.bottom - fr.bottom
            user32.SetWindowPos(hwnd, 0, x - dl, y - dt, ww + dl + dr, hh + dt + db, SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        time.sleep(0.35)
        if not user32.IsWindow(hwnd):
            return False
        if all(abs(a - b) <= 3 for a, b in zip(visible_rect(hwnd), want)):
            return True
    return True                           # placed as well as the app allows (some have a minimum size)


def visible_rect(hwnd: int) -> tuple[int, int, int, int]:
    fr = w.RECT()
    dwm.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(fr), 16)
    return fr.left, fr.top, fr.right, fr.bottom


def close_window(hwnd: int) -> None:
    user32.PostMessageW(hwnd, 0x0010, 0, 0)            # WM_CLOSE: a polite close, never a kill


# ------------------------------------------------------------------ launching
def launch(spec: dict, browser_hint: str | None, start_app: Callable[[str], bool], favourites=None) -> bool:
    """Start the target in a NEW window where that makes sense."""
    if spec["kind"] in ("browser", "site"):
        exe = spec.get("exe") if spec["kind"] == "browser" else browser_hint
        path = browser_path(exe) or browser_path(None)
        if not path:
            import webbrowser
            webbrowser.open(spec.get("url", "about:blank"))
            return True
        args = [path, "--new-window", spec.get("url", "about:blank")] if "firefox" not in path else [path, "-new-window", spec.get("url", "about:blank")]
        subprocess.Popen(args, creationflags=0x08000000)
        return True
    return start_app(spec["label"].lower())


def wait_new_window(before: set[int], timeout: float = 9.0, also_ignore: set[int] = frozenset()) -> int | None:
    end = time.time() + timeout
    while time.time() < end:
        new = visible_windows() - before - set(also_ignore)
        if new:
            return max(new)                             # the newest one
        time.sleep(0.25)
    return None


def side_by_side(names: list[str], start_app: Callable[[str], bool], favourites=None, progress: Callable[[str], None] | None = None):
    """Open two things and put them on the left and right halves. Returns (placed: list[(label, side)], failed: list[label])."""
    specs = [resolve(n, favourites) for n in names]
    hint = next((s["exe"] for s in specs if s["kind"] == "browser" and s.get("exe")), None)
    left, right = half_rects(work_area())
    placed, failed, claimed = [], [], set()
    for spec, rect, side in zip(specs, (left, right), ("left", "right")):
        before = visible_windows()
        if progress:
            progress(f"Opening {spec['label']}")
        if not launch(spec, hint, start_app, favourites):
            failed.append(spec["label"]); continue
        hwnd = wait_new_window(before, also_ignore=claimed)
        if hwnd is None:                                 # it may have been running already and just came forward
            fg = user32.GetForegroundWindow()
            hwnd = int(fg) if fg and int(fg) not in claimed and int(fg) in visible_windows() else None
        if hwnd is None:
            failed.append(spec["label"]); continue
        claimed.add(hwnd)
        place(hwnd, rect)
        placed.append((spec["label"], side, hwnd))
    return placed, failed


def snap_foreground(side: str) -> str | None:
    fg = int(user32.GetForegroundWindow() or 0)
    if not fg or fg not in visible_windows():
        return None
    left, right = half_rects(work_area())
    place(fg, left if side == "left" else right)
    return side
