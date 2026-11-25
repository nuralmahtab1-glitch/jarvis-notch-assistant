from app.winio.claude_proc import ClaudeActivity


class P:
    def __init__(self, pid, cpu): self.pid = pid; self.cpu = cpu
    def cpu_percent(self, interval=None): return self.cpu


def make(procs, t):
    return ClaudeActivity(processes=lambda: list(procs), clock=lambda: t["now"], threshold=3.0, grace=900)


def test_idle_claude_is_not_active():
    t = {"now": 0.0}; a = make([P(1, 0.4), P(2, 0.9)], t)
    assert a.active() is False and a.running is True


def test_busy_claude_is_active_and_stays_active_for_the_grace_period():
    t = {"now": 0.0}; p = P(1, 12.0); a = make([p], t)
    assert a.active() is True
    p.cpu = 0.0
    t["now"] = 600; assert a.active() is True          # a 10 minute lull (slow command, waiting on you): still active
    t["now"] = 901; assert a.active() is False          # past the 15 minute grace: let the laptop sleep


def test_cpu_is_summed_across_claude_processes():
    t = {"now": 0.0}; a = make([P(1, 1.6), P(2, 1.6)], t)
    assert a.active() is True                           # 3.2% together crosses the threshold


def test_no_claude_running_is_never_active():
    t = {"now": 0.0}; a = make([], t)
    assert a.active() is False and a.running is False


def test_errors_while_sampling_never_raise():
    t = {"now": 0.0}
    class Bad:
        pid = 9
        def cpu_percent(self, interval=None): raise RuntimeError("process vanished")
    a = make([Bad()], t)
    assert a.active() is False
    assert ClaudeActivity(processes=lambda: (_ for _ in ()).throw(OSError("denied"))).active() is False


def test_works_with_the_real_process_list_on_this_machine():
    import psutil
    a = ClaudeActivity()
    a.active(); a.active()                              # prime then sample for real: must not crash
    assert isinstance(a.running, bool)
