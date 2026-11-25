from app.awake_only import AwakeOnly, arg_value, LOW_BATTERY
from app.winio.awake import KeepAwake
from app.winio.claude_proc import ClaudeActivity


class Api:
    def __init__(self): self.calls = []
    def __call__(self, flags): self.calls.append(flags); return 0


class P:
    def __init__(self, cpu): self.pid = 1; self.cpu = cpu
    def cpu_percent(self, interval=None): return self.cpu


def make(t, **kw):
    api = Api(); keep = KeepAwake(api, clock=lambda: t["now"])
    return AwakeOnly(keep, clock=lambda: t["now"], **kw), keep, api


def test_holds_until_stopped_by_default():
    t = {"now": 0.0}; a, keep, api = make(t)
    assert keep.active
    t["now"] += 10 ** 6
    assert a.tick() is True and keep.active
    keep.off()


def test_timed_hold_ends_by_itself():
    t = {"now": 0.0}; a, keep, api = make(t, minutes=30)
    assert a.tick() is True
    t["now"] += 31 * 60
    assert a.tick() is False and not keep.active and a.reason == "time is up"


def test_unplugged_low_battery_lets_go_immediately():
    t = {"now": 0.0}; a, keep, api = make(t, battery=lambda: (LOW_BATTERY, False))
    assert a.tick() is False and not keep.active and "battery" in a.reason


def test_plugged_in_low_battery_keeps_holding():
    t = {"now": 0.0}; a, keep, api = make(t, battery=lambda: (5, True))
    assert a.tick() is True and keep.active
    keep.off()


def test_no_battery_desktop_is_fine():
    t = {"now": 0.0}; a, keep, api = make(t, battery=lambda: (None, True))
    assert a.tick() is True
    keep.off()


def test_while_claude_holds_only_while_claude_is_busy_then_exits_after_the_grace():
    t = {"now": 0.0}; proc = P(20.0)
    act = ClaudeActivity(processes=lambda: [proc], clock=lambda: t["now"], threshold=3.0, grace=900)
    a, keep, api = make(t, while_claude=True, activity=act)
    assert not keep.active                                     # nothing to hold until Claude does something
    assert a.tick() is True and keep.active                     # busy: hold
    proc.cpu = 0.0; t["now"] += 600
    assert a.tick() is True and keep.active                     # quiet for 10 minutes: still within the grace
    t["now"] += 400
    assert a.tick() is False and not keep.active and a.reason == "Claude Code finished"


def test_arg_parsing():
    argv = ["--awake-only", "--minutes", "480", "--display"]
    assert arg_value(argv, "--minutes") == 480.0 and arg_value(argv, "--missing") is None
    assert arg_value(["--minutes"], "--minutes") is None and arg_value(["--minutes", "abc"], "--minutes") is None
