"""Hold-to-talk using a low-level keyboard hook (RegisterHotKey cannot bind a bare modifier).
Made by Nur Al Mahtab."""
from __future__ import annotations
import ctypes, threading
from ctypes import wintypes
from typing import Callable

user32 = ctypes.WinDLL("user32", use_last_error=True)
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
VK = {"right ctrl": 0xA3, "right alt": 0xA5, "right shift": 0xA1, "f9": 0x78, "f8": 0x77}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t


class HoldKey:
    """Calls on_down() when the key goes down and on_up() when released. Never swallows the key."""

    def __init__(self, keys: dict[str, tuple[Callable, Callable]]):
        self._handlers = {VK[k]: v for k, v in keys.items()}
        self._down: set[int] = set()
        self._thread: threading.Thread | None = None
        self._hook = None
        self._tid = 0
        self._proc = HOOKPROC(self._callback)  # keep a reference

    def _callback(self, nCode, wParam, lParam):
        if nCode >= 0:
            vk = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents.vkCode
            h = self._handlers.get(vk)
            if h:
                if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN) and vk not in self._down:
                    self._down.add(vk)
                    threading.Thread(target=h[0], daemon=True).start()
                elif wParam in (WM_KEYUP, WM_SYSKEYUP) and vk in self._down:
                    self._down.discard(vk)
                    threading.Thread(target=h[1], daemon=True).start()
        return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    def _run(self):
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._tid:
            user32.PostThreadMessageW(self._tid, 0x12, 0, 0)  # WM_QUIT
