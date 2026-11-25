import time
from app.winio.awake import ES_CONTINUOUS, ES_DISPLAY_REQUIRED, ES_SYSTEM_REQUIRED, KeepAwake


class Api:
    """Records every call and which thread made it (Windows ties the request to the calling thread)."""
    def __init__(self): self.calls = []; self.threads = []
    def __call__(self, flags):
        import threading
        self.calls.append(flags); self.threads.append(threading.get_ident()); return 0


def wait_for(cond, secs=2.0):
    end = time.time() + secs
    while time.time() < end and not cond():
        time.sleep(0.01)
    return cond()


def test_on_requests_system_and_display_then_off_gives_it_back():
    api = Api(); k = KeepAwake(api)
    k.on(display=True)
    assert wait_for(lambda: api.calls) and api.calls[0] == ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED and k.active
    k.off()
    assert api.calls[-1] == ES_CONTINUOUS and not k.active          # ES_CONTINUOUS alone clears the request


def test_system_only_leaves_the_screen_free_to_turn_off():
    api = Api(); k = KeepAwake(api)
    k.on(display=False)
    assert wait_for(lambda: api.calls) and api.calls[0] == ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    assert not (api.calls[0] & ES_DISPLAY_REQUIRED)
    k.off()


def test_set_and_clear_happen_on_the_same_thread():
    """Windows would ignore a clear made from a different thread than the set."""
    api = Api(); k = KeepAwake(api)
    k.on(); wait_for(lambda: api.calls); k.off()
    assert len(api.calls) == 2 and api.threads[0] == api.threads[1]


def test_restarting_replaces_the_old_request():
    api = Api(); k = KeepAwake(api)
    k.on(display=True); wait_for(lambda: len(api.calls) >= 1)
    k.on(display=False); wait_for(lambda: len(api.calls) >= 3)
    assert api.calls[1] == ES_CONTINUOUS and api.calls[2] == ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    k.off()


def test_timed_session_counts_down_and_expires():
    t = {"now": 100.0}; api = Api(); k = KeepAwake(api, clock=lambda: t["now"])
    k.on(minutes=30)
    assert k.remaining() == 1800 and not k.expired()
    t["now"] += 1000; assert k.remaining() == 800
    t["now"] += 900; assert k.expired() and k.remaining() == 0
    k.off(); assert k.remaining() is None and not k.expired()


def test_untimed_session_never_expires():
    t = {"now": 0.0}; k = KeepAwake(Api(), clock=lambda: t["now"])
    k.on(); t["now"] += 10 ** 7
    assert not k.expired() and k.remaining() is None
    k.off()


def test_off_when_already_off_is_harmless():
    api = Api(); k = KeepAwake(api)
    k.off(); k.off()
    assert api.calls == [] and not k.active
