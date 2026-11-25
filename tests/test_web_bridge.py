import http.client, json, os, socket, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from app.claude_bridge import tracker as trk
from app.claude_bridge.tracker import Tracker
from app.claude_bridge.web import MAX_BODY, WebBridge, clean, new_pair_code, origin_allowed, validate

EXT = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
CODE = "A1B2C3D4"


def free_ports(n=3):
    socks, ports = [], []
    for _ in range(n):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); ports.append(s.getsockname()[1]); socks.append(s)
    for s in socks: s.close()
    return tuple(ports)


@pytest.fixture
def web():
    t = Tracker()
    b = WebBridge(t, lambda: CODE, ports=free_ports())
    assert b.start()
    yield t, b
    b.stop()


def call(b, method, path, body=None, origin=EXT, code=CODE, raw=None):
    c = http.client.HTTPConnection("127.0.0.1", b.port, timeout=5)
    h = {}
    if origin is not None: h["Origin"] = origin
    if code is not None: h["X-Jarvis-Pair"] = code
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    if data is not None: h["Content-Type"] = "application/json"
    c.request(method, path, body=data, headers=h)
    r = c.getresponse(); out = r.read()
    return r.status, dict(r.getheaders()), (json.loads(out) if out else None)


def ev(state, tab="7", **kw): return {"state": state, "tab": tab, **kw}


# ---------------- who may talk to it ----------------
@pytest.mark.parametrize("origin", [None, "https://evil.example", "http://localhost:3000", "https://claude.ai", "null"])
def test_ordinary_web_pages_can_never_use_it(web, origin):
    t, b = web
    for method, path, body in (("GET", "/web/hello", None), ("GET", "/web/ping", None), ("POST", "/web/event", ev("working")), ("OPTIONS", "/web/event", None)):
        status, _, _ = call(b, method, path, body, origin=origin)
        assert status == 403, (method, path, origin)
    assert t.urgent() is None


def test_extension_origins_are_recognised():
    assert origin_allowed(EXT) and origin_allowed("moz-extension://x") and origin_allowed("edge-extension://y")
    assert not origin_allowed("https://chrome-extension.evil.com") and not origin_allowed("") and not origin_allowed(None)


def test_wrong_or_missing_pairing_code_is_refused(web):
    t, b = web
    assert call(b, "POST", "/web/event", ev("working"), code="WRONG")[0] == 401
    assert call(b, "POST", "/web/event", ev("working"), code=None)[0] == 401
    assert call(b, "GET", "/web/ping", code="")[0] == 401
    assert t.urgent() is None


def test_hello_needs_no_code_but_reveals_nothing(web):
    t, b = web
    status, _, body = call(b, "GET", "/web/hello", code=None)
    assert status == 200 and body == {"app": "Jarvis"}


def test_ping_with_the_right_code(web):
    t, b = web
    assert call(b, "GET", "/web/ping")[0] == 200


def test_preflight_gives_cors_headers_only_to_extensions(web):
    t, b = web
    status, headers, _ = call(b, "OPTIONS", "/web/event")
    assert status == 204 and headers["Access-Control-Allow-Origin"] == EXT and "X-Jarvis-Pair" in headers["Access-Control-Allow-Headers"]
    assert "*" not in headers["Access-Control-Allow-Origin"]


# ---------------- what it accepts ----------------
def test_bad_events_are_rejected(web):
    t, b = web
    assert call(b, "POST", "/web/event", {"state": "exploding"})[0] == 400
    assert call(b, "POST", "/web/event", raw=b"not json{")[0] == 400
    assert call(b, "POST", "/web/event", raw=b"[1,2,3]")[0] == 400
    assert call(b, "POST", "/web/nope", ev("working"))[0] == 404
    assert t.urgent() is None


def test_oversized_body_is_refused(web):
    t, b = web
    assert call(b, "POST", "/web/event", raw=b"x" * (MAX_BODY + 50))[0] == 413


def test_text_is_cleaned_and_length_limited():
    e = validate({"state": "working", "tab": "12; DROP", "action": "Work\x00ing\x07" + "x" * 500, "title": "T" * 500})
    assert e["tab"] == "12DROP" and "\x00" not in e["action"] and len(e["action"]) <= 60 and len(e["title"]) <= 80
    assert clean("a\nb\tc", 10) == "a b c"


def test_burst_of_events_is_rate_limited(web):
    t, b = web
    codes = [call(b, "POST", "/web/event", ev("working"))[0] for _ in range(60)]
    assert codes.count(200) >= 15 and 429 in codes


# ---------------- what it does to the notch's data ----------------
def test_working_then_done_records_a_finished_run(web, monkeypatch):
    t, b = web
    now = {"t": 1000.0}; monkeypatch.setattr(trk.time, "time", lambda: now["t"])
    call(b, "POST", "/web/event", ev("working", action="Working"))
    s = t.urgent(); assert s.state == "working" and s.source == "web" and s.project == "Claude on the web"
    now["t"] += 125
    call(b, "POST", "/web/event", ev("done"))
    s = t.urgent(); assert s.state == "done" and round(s.duration) == 125 and t.history[0]["result"] == "done"
    call(b, "POST", "/web/event", ev("idle"))
    assert t.urgent().state == "done"                          # still "finished" until you dismiss it


def test_done_without_working_is_ignored(web):
    t, b = web
    call(b, "POST", "/web/event", ev("done"))
    assert t.urgent() is None or t.urgent().state != "done"
    assert t.history == []


def test_needs_you_has_no_approval_to_resolve(web):
    t, b = web
    call(b, "POST", "/web/event", ev("working")); call(b, "POST", "/web/event", ev("needs_you"))
    assert t.urgent().state == "needs_you" and t.pending == {}
    assert t.resolve("allow") is False                         # approving is only possible in the browser itself


def test_unavailable_removes_the_session_instead_of_guessing(web):
    t, b = web
    call(b, "POST", "/web/event", ev("working"))
    assert t.urgent() is not None
    call(b, "POST", "/web/event", ev("unavailable"))
    assert t.urgent() is None


def test_a_tab_that_stops_reporting_is_treated_as_closed(web, monkeypatch):
    t, b = web
    now = {"t": 1000.0}; monkeypatch.setattr(trk.time, "time", lambda: now["t"])
    call(b, "POST", "/web/event", ev("working"))
    now["t"] += trk.WEB_STALE_SECONDS + 5
    assert t.urgent() is None and t.sessions == {}


def test_two_tabs_are_tracked_separately_and_terminal_sessions_coexist(web):
    t, b = web
    call(b, "POST", "/web/event", ev("working", tab="1")); call(b, "POST", "/web/event", ev("needs_you", tab="2"))
    t.handle({"hook_event_name": "UserPromptSubmit", "session_id": "term", "cwd": r"C:\p\site"})
    assert set(t.sessions) == {"web:1", "web:2", "term"} and t.urgent().id == "web:2"


def test_voice_status_sentences_for_the_web(web, monkeypatch):
    t, b = web
    now = {"t": 1000.0}; monkeypatch.setattr(trk.time, "time", lambda: now["t"])
    call(b, "POST", "/web/event", ev("working", action="Working")); now["t"] += 65
    assert t.status_sentence() == "Claude is working on the web, 1m 05s in."
    call(b, "POST", "/web/event", ev("needs_you"))
    assert "on the web needs your permission, in the browser" in t.status_sentence()


# ---------------- plumbing ----------------
def test_falls_back_to_the_next_port_and_stop_frees_it():
    ports = free_ports(2)
    blocker = socket.socket(); blocker.bind(("127.0.0.1", ports[0])); blocker.listen(1)
    b = WebBridge(Tracker(), lambda: CODE, ports=ports)
    try:
        assert b.start() and b.port == ports[1]
        b.stop()
        with socket.socket() as s:
            s.bind(("127.0.0.1", ports[1]))                    # really released
    finally:
        blocker.close(); b.stop()


def test_start_fails_cleanly_when_every_port_is_taken():
    ports = free_ports(2); socks = []
    for p in ports:
        s = socket.socket(); s.bind(("127.0.0.1", p)); s.listen(1); socks.append(s)
    try:
        assert WebBridge(Tracker(), lambda: CODE, ports=ports).start() is False
    finally:
        for s in socks: s.close()


def test_pair_codes_are_8_hex_chars_and_not_repeated():
    codes = {new_pair_code() for _ in range(50)}
    assert len(codes) == 50 and all(len(c) == 8 and int(c, 16) >= 0 for c in codes)
