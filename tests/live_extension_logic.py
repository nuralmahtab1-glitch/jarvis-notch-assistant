"""Runs the extension's REAL content.js, selectors.js and background.js inside a real headless Chrome, against mock
claude.ai pages, talking to Jarvis's real local endpoint. Only the chrome.* APIs are stand-ins, and a relay adds the
extension 'Origin' header (a page cannot set it). Not covered: manifest/packaging and the real service-worker lifecycle
(this Chrome 158 / Edge 158 no longer load extensions from the command line). Run manually."""
import http.client, http.server, json, os, re, socketserver, subprocess, sys, tempfile, threading, time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
sys.path.insert(0, ".")
from app.claude_bridge.tracker import Tracker
from app.claude_bridge.web import PORTS, WebBridge

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extension"
CODE = "A1B2C3D4"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
EXT_ORIGIN = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"

PAGES = {
    "working": "<textarea></textarea><button aria-label='Stop generating'>Stop</button>",
    "needs": "<textarea></textarea><button>Allow once</button><button>Deny</button>",
    "idle": "<textarea></textarea><p>Ready.</p>",
    "nocomposer": "<h1>Some other page</h1><p>No message box here.</p>",
    "finish": "<textarea></textarea><button id=s aria-label='Stop generating'>Stop</button><script>setTimeout(()=>document.getElementById('s').remove(), 4000)</script>",
    "hidden": "<textarea></textarea><button style='display:none' aria-label='Stop generating'>Stop</button>",
    "lookalike": "<textarea></textarea><button>Allow</button>",               # an Allow button alone is NOT a permission prompt
}

STUBS = """<script>
const store = { pairCode: new URLSearchParams(location.search).get('code') || 'A1B2C3D4' }; const listeners = [];
window.chrome = {
  storage: { local: { get: async k => ({ [k]: store[k] }), set: async o => { Object.assign(store, o); } } },
  action: { setBadgeText() {}, setBadgeBackgroundColor() {} }, tabs: { onRemoved: { addListener() {} } },
  runtime: { lastError: null, onMessage: { addListener: f => listeners.push(f) },
             sendMessage: (msg, cb) => { for (const f of listeners) f(msg, { tab: { id: 1 } }, x => cb && cb(x)); } } };
const realFetch = window.fetch.bind(window);
window.fetch = (url, opts = {}) => realFetch('/_proxy?u=' + encodeURIComponent(url), opts);   // relay adds the extension Origin
setInterval(() => realFetch('/_status', { method: 'POST', body: JSON.stringify(store.status || null) }), 700);
</script>"""


class Handler(http.server.BaseHTTPRequestHandler):
    log = []          # every request body the relay forwarded
    status = None

    def log_message(self, *a): pass

    def _send(self, code, body=b"", ctype="text/html"):
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path.startswith("/h/"):
            name = u.path[3:]
            if name not in PAGES:
                return self._send(404)
            html = (f"<!doctype html><html><head><title>mock {name}</title></head><body>{PAGES[name]}{STUBS}"
                    f"<script src='/ext/background.js'></script><script src='/ext/selectors.js'></script><script src='/ext/content.js'></script></body></html>")
            return self._send(200, html.encode())
        if u.path.startswith("/ext/") and re.fullmatch(r"/ext/[a-z]+\.js", u.path):
            return self._send(200, (EXT / u.path[5:]).read_bytes(), "text/javascript")
        if u.path == "/_proxy":
            return self._proxy("GET", u)
        self._send(404)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0) or 0); raw = self.rfile.read(n) if n else b""
        if u.path == "/_status":
            Handler.status = json.loads(raw or b"null"); return self._send(204)
        if u.path == "/_proxy":
            return self._proxy("POST", u, raw)
        self._send(404)

    def _proxy(self, method, u, raw=b""):
        target = urlparse(parse_qs(u.query)["u"][0])
        if target.hostname != "127.0.0.1" or target.port not in PORTS:        # the relay only ever talks to Jarvis's ports
            return self._send(400)
        if method == "POST":
            Handler.log.append(json.loads(raw or b"{}"))
        try:
            c = http.client.HTTPConnection("127.0.0.1", target.port, timeout=3)
            h = {"Origin": EXT_ORIGIN, "X-Jarvis-Pair": self.headers.get("X-Jarvis-Pair", ""), "Content-Type": "application/json"}
            c.request(method, target.path, body=raw or None, headers=h)
            r = c.getresponse(); self._send(r.status, r.read(), "application/json")
        except OSError:
            self._send(502)


def wait(cond, secs):
    end = time.time() + secs
    while time.time() < end:
        if cond(): return True
        time.sleep(0.25)
    return False


def browse(url, user_dir, seconds=None, until=None, limit=40):
    p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                          f"--user-data-dir={user_dir}", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if until: return wait(until, limit)
        time.sleep(seconds); return True
    finally:
        p.terminate()
        try: p.wait(8)
        except Exception: p.kill()


def main():
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler); srv.daemon_threads = True; port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tracker = Tracker()
    bridge = WebBridge(tracker, lambda: CODE)
    assert bridge.start(), "ports 17894-17899 are busy (is real Jarvis running with the web option on?)"
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-ext-")); results = []

    def check(name, ok, extra=""):
        results.append(bool(ok)); print("PASS" if ok else "FAIL", name, extra, flush=True)

    def state():
        s = tracker.urgent(); return s.state if s else ""

    def reset():
        tracker.sessions.clear(); tracker.history.clear(); Handler.log.clear(); Handler.status = None

    url = lambda name, q="": f"http://127.0.0.1:{port}/h/{name}{q}"

    reset(); browse(url("working"), tmp / "p1", until=lambda: state() == "working")
    check("page with a Stop button -> Jarvis shows 'working'", state() == "working", f"({[e['state'] for e in Handler.log]})")
    reset(); browse(url("needs"), tmp / "p2", until=lambda: state() == "needs_you")
    check("page with Allow + Deny -> Jarvis shows 'needs you'", state() == "needs_you")
    reset(); browse(url("lookalike"), tmp / "p3", seconds=6)
    check("a lone Allow button is not mistaken for a permission prompt", state() == "")
    reset(); browse(url("hidden"), tmp / "p4", seconds=6)
    check("a hidden Stop button does not count as working", state() == "")
    reset(); browse(url("idle"), tmp / "p5", seconds=6)
    check("page with only a message box -> nothing shown", tracker.urgent() is None and not any(e["state"] in ("working", "needs_you", "done") for e in Handler.log))
    reset(); browse(url("nocomposer"), tmp / "p6", seconds=6)
    check("a page that is not Claude Code -> 'unavailable', nothing shown", tracker.urgent() is None and all(e["state"] == "unavailable" for e in Handler.log) and Handler.log)
    reset(); ok = browse(url("finish"), tmp / "p7", until=lambda: bool(tracker.history) and tracker.history[0]["result"] == "done", limit=45)
    check("a task that stops working is recorded as finished", ok, f"({[e['state'] for e in Handler.log][:6]}...)")
    sent = list(Handler.log)
    check("only state + tab + a fixed label were sent: no title, no page text",
          bool(sent) and all(set(e) == {"state", "tab", "action"} and e["action"] in ("", "Working", "Waiting for your OK in the browser") for e in sent))
    reset(); browse(url("working", "?code=WRONGCODE"), tmp / "p8", seconds=7)
    check("wrong pairing code -> refused, and the extension says so", state() == "" and Handler.status and "Wrong pairing code" in Handler.status.get("text", ""),
          f"(status: {Handler.status})")
    bridge.stop(); reset(); browse(url("working"), tmp / "p9", seconds=7)
    check("Jarvis not running -> nothing breaks, and the extension says so", state() == "" and Handler.status and "not running" in Handler.status.get("text", ""),
          f"(status: {Handler.status})")
    srv.shutdown()
    print(f"\n{sum(results)}/{len(results)} extension logic checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
