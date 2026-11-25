"""Headless keep-awake: no window, no microphone, nothing but "do not sleep". Made by Nur Al Mahtab.

    Jarvis.exe --awake-only                    # hold until you stop it
    Jarvis.exe --awake-only --minutes 480      # hold for 8 hours, then let go
    Jarvis.exe --awake-only --while-claude     # hold while Claude Code is working (and 15 min after), then exit
    Jarvis.exe --awake-only --display          # also keep the screen on
    Jarvis.exe --awake-stop                    # stop a running one

It also lets go by itself when the laptop is unplugged and the battery drops to 15%.
"""
from __future__ import annotations
import os, subprocess, time
from pathlib import Path
from typing import Callable

from app.winio.awake import KeepAwake
from app.winio.claude_proc import ClaudeActivity

LOW_BATTERY = 15


def pid_file() -> Path:
    d = Path(os.environ.get("APPDATA", str(Path.home()))) / "Jarvis"
    d.mkdir(parents=True, exist_ok=True)
    return d / "awake.pid"


class AwakeOnly:
    """The decision logic, separate from the loop so it can be tested with a fake clock."""

    def __init__(self, keep: KeepAwake, minutes: float | None = None, while_claude: bool = False, display: bool = False,
                 activity: ClaudeActivity | None = None, battery: Callable[[], tuple[int | None, bool]] = lambda: (None, True),
                 clock: Callable[[], float] = time.monotonic):
        self.keep, self.minutes, self.while_claude, self.display = keep, minutes, while_claude, display
        self.activity, self.battery, self.clock = activity or ClaudeActivity(), battery, clock
        self.start = clock()
        self.reason = ""
        if not while_claude:
            keep.on(display=display, minutes=minutes)

    def tick(self) -> bool:
        """Call about once a second. Returns False when it is time to stop."""
        pct, plugged = self.battery()
        if pct is not None and not plugged and pct <= LOW_BATTERY:
            self.keep.off(); self.reason = f"battery at {pct}%"
            return False
        if self.while_claude:
            if self.activity.active():
                if not self.keep.active:
                    self.keep.on(display=self.display)
            elif self.keep.active:                        # idle past the grace period: done
                self.keep.off(); self.reason = "Claude Code finished"
                return False
            return True
        if self.keep.expired():
            self.keep.off(); self.reason = "time is up"
            return False
        return True


def arg_value(argv: list[str], name: str, cast=float):
    if name in argv:
        try:
            return cast(argv[argv.index(name) + 1])
        except (IndexError, ValueError):
            return None
    return None


def stop_running() -> bool:
    try:
        pid = int(pid_file().read_text().strip())
    except (OSError, ValueError):
        return False
    r = subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, creationflags=0x08000000)
    pid_file().unlink(missing_ok=True)
    return r.returncode == 0


def run(argv: list[str]) -> int:
    from app.winio import system as win
    if "--awake-stop" in argv:
        return 0 if stop_running() else 1
    pid_file().write_text(str(os.getpid()))
    a = AwakeOnly(KeepAwake(), minutes=arg_value(argv, "--minutes"), while_claude="--while-claude" in argv,
                  display="--display" in argv, battery=win.battery)
    print(f"[awake-only] started (minutes={a.minutes}, while_claude={a.while_claude}, display={a.display})", flush=True)
    try:
        while a.tick():
            time.sleep(1.0)
    finally:
        a.keep.off()
        pid_file().unlink(missing_ok=True)
    print(f"[awake-only] stopped: {a.reason}", flush=True)
    return 0
