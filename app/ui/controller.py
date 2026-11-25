"""NotchController: single source of truth for what the notch shows. Made by Nur Al Mahtab."""
from __future__ import annotations
import os, time
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from app import config

TOOLTIPS = {
    "dictate": ("Dictate", "Talk, and your words appear where you type."),
    "write": ("Write", f"Say what you need, and {config.APP_NAME} writes it for you."),
    "command": ("Command", "Point at something, or tell me what to do."),
    "widgets": ("Widgets", "The time around the world, your list, battery and weather."),
    "controls": ("Controls", "Volume, brightness, Wi-Fi, power mode and a screenshot."),
    "apps": ("Apps", "Your pinned apps, one click away."),
    "shelf": ("Shelf", "What you copied and the files you dropped, kept here."),
    "timer": ("Timer", "Focus sessions, the clock and your reminders."),
    "menu": ("Menu", "Your sites, the guide, the teleprompter and more."),
}
DEFAULT_TEXT = {
    "expanded": (f"Ready. Say {config.WAKE_PHRASE}.", "Or tap one of the three buttons above."),
    "listening": ("Listening", ""),
    "hearing": ("Remind me to call Mom at six", ""),
    "working": ("Working on it", ""),
    "recording": ("Listening", ""),
    "done": ("Done", ""),
    "speaking": ("Of course.", ""),
    "confirm": ("Send the slides to Sam?", "I will only do it if you say so."),
    "volume": ("Volume", ""),
    "reminder": ("Time for water", "3 of 8 glasses today"),
    "claudeWorking": ("Claude is editing server.ts", "2:14"),
    "claudeNeeds": ("Claude needs your permission", "Run a command in plant-design"),
    "claudeDone": ("Claude finished in 4m 12s", ""),
    "claudeError": ("Claude hit an error", ""),
}
MODES = ["idle", "sleeping", "expanded", "listening", "hearing", "working", "done", "recording",
         "speaking", "confirm", "volume", "reminder", "music", "focus", "todo",
         "claudeWorking", "claudeNeeds", "claudeDone", "claudeError"]
SIZES = {  # width, height
    "idle": (180, 36), "sleeping": (180, 36), "peek": (210, 42), "expanded": (560, 150),
    "listening": (300, 44), "recording": (300, 44), "hearing": (400, 44), "working": (300, 44),
    "done": (250, 44), "speaking": (320, 44), "confirm": (450, 96), "volume": (300, 44),
    "reminder": (400, 76), "music": (560, 176), "focus": (560, 150), "todo": (560, 176),
    "claudeWorking": (420, 44), "claudeNeeds": (480, 96), "claudeDone": (400, 44), "claudeError": (380, 44),
}


class NotchController(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._mode = "idle"
        self._hover_key = ""
        self._look = (0.0, 0.0)
        self._page = 0
        self._clock = ""
        self._last_active = time.monotonic()
        self._sleep_after = float(os.environ.get("JARVIS_SLEEP_SECONDS", config.IDLE_SLEEP_SECONDS))
        self._todo = [
            {"text": "Buy coffee beans", "done": False}, {"text": "Book the dentist", "done": False},
            {"text": "Reply to Sam", "done": True}, {"text": "Call Mom at six", "done": True}]
        self._focus_left = 18 * 60 + 39
        self._level = 0.0
        self._demo = QTimer(self); self._demo.timeout.connect(self._next_demo); self._demo_i = 0
        self._poll = QTimer(self); self._poll.setInterval(33); self._poll.timeout.connect(self._tick)
        self._poll.start()
        self._clk = QTimer(self); self._clk.setInterval(1000); self._clk.timeout.connect(self._tick_clock)
        self._clk.start(); self._tick_clock()
        self._collapse = QTimer(self); self._collapse.setSingleShot(True); self._collapse.setInterval(650)
        self._collapse.timeout.connect(self._do_collapse)

    # ---- properties ----
    def _get_title(self):
        if self._hover_key in TOOLTIPS: return TOOLTIPS[self._hover_key][0]
        return DEFAULT_TEXT.get(self._mode, ("", ""))[0]

    def _get_sub(self):
        if self._hover_key in TOOLTIPS: return TOOLTIPS[self._hover_key][1]
        return DEFAULT_TEXT.get(self._mode, ("", ""))[1]

    mode = Property(str, lambda s: s._mode, notify=changed)
    title = Property(str, _get_title, notify=changed)
    subtitle = Property(str, _get_sub, notify=changed)
    clock = Property(str, lambda s: s._clock, notify=changed)
    lookX = Property(float, lambda s: s._look[0], notify=changed)
    lookY = Property(float, lambda s: s._look[1], notify=changed)
    page = Property(int, lambda s: s._page, notify=changed)
    todo = Property("QVariantList", lambda s: s._todo, notify=changed)
    todoDone = Property(int, lambda s: sum(1 for t in s._todo if t["done"]), notify=changed)
    focusText = Property(str, lambda s: f"{s._focus_left // 60}:{s._focus_left % 60:02d}", notify=changed)
    focusFrac = Property(float, lambda s: s._focus_left / 1500.0, notify=changed)
    appName = Property(str, lambda s: config.APP_NAME, constant=True)
    credit = Property(str, lambda s: config.CREDIT, constant=True)
    boxW = Property(int, lambda s: SIZES.get(s._mode, (180, 36))[0], notify=changed)
    boxH = Property(int, lambda s: SIZES.get(s._mode, (180, 36))[1], notify=changed)

    # ---- slots ----
    @Slot(str)
    def setMode(self, m: str):
        if m == self._mode:
            return
        self._mode = m
        self._hover_key = ""
        if m != "sleeping":
            self._last_active = time.monotonic()
        self.changed.emit()

    @Slot(str)
    def hoverKey(self, k: str):
        self._hover_key = k
        self.changed.emit()

    @Slot(bool)
    def bodyHover(self, inside: bool):
        if inside:
            self._collapse.stop()
            self._last_active = time.monotonic()
            if self._mode in ("idle", "sleeping", "peek"):
                self.setMode("expanded")
        elif self._mode == "expanded":
            self._collapse.start()

    def _do_collapse(self):
        if self._mode == "expanded":
            self.setMode("idle")

    @Slot(int)
    def toggleTodo(self, i: int):
        self._todo[i]["done"] = not self._todo[i]["done"]
        self.changed.emit()

    @Slot(int)
    def setPage(self, p: int):
        self._page = p
        self.changed.emit()

    @Slot()
    def startDemo(self):
        self._demo_i = 0
        self._demo.start(3200)
        self._next_demo()

    def _next_demo(self):
        self.setMode(MODES[self._demo_i % len(MODES)])
        self._demo_i += 1

    @Slot()
    def stopDemo(self):
        self._demo.stop()
        self.setMode("idle")

    # ---- timers ----
    def _tick_clock(self):
        self._clock = time.strftime("%a %d %b %H:%M")
        if self._mode == "focus" and self._focus_left > 0:
            self._focus_left -= 1
        self.changed.emit()

    def _tick(self):
        scr = QGuiApplication.primaryScreen()
        if not scr:
            return
        g = scr.geometry()
        p = QCursor.pos()
        cx = g.x() + g.width() / 2
        dx = p.x() - cx
        dy = p.y() - g.y()
        near = dy < 26 and abs(dx) < 150
        if near:
            self._last_active = time.monotonic()
            if self._mode == "sleeping":
                self.setMode("idle")
            elif self._mode == "idle":
                self.setMode("peek")
        elif self._mode == "peek":
            self.setMode("idle")
        if abs(dx) < 500 and dy < 420:
            lx, ly = max(-1.0, min(1.0, dx / 260)), max(-1.0, min(1.0, (dy - 20) / 200))
        else:
            lx = ly = 0.0
        if abs(lx - self._look[0]) > 0.02 or abs(ly - self._look[1]) > 0.02:
            self._look = (lx, ly)
            self.changed.emit()
        if self._mode == "idle" and time.monotonic() - self._last_active > self._sleep_after:
            self.setMode("sleeping")
