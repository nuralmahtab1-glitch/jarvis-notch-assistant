"""Local endpoint for the browser extension (Claude Code on the web). Made by Nur Al Mahtab.

Security model:
  * listens on 127.0.0.1 only;
  * only requests from a browser *extension* origin are accepted (a web page can never talk to it);
  * every event needs the pairing code you copied into the extension (shown in Jarvis Settings, can be regenerated);
  * events carry only a state and a short label, never your conversation; bodies are size-limited and rate-limited.
"""
from __future__ import annotations
import hmac, json, re, secrets, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

PORTS = tuple(range(17894, 17900))
STATES = {"working", "needs_you", "done", "idle", "unavailable"}
MAX_BODY = 4096
RATE_PER_SECOND = 20
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def new_pair_code() -> str:
    return secrets.token_hex(4).upper()          # 8 characters, like 3F9A01BC


def origin_allowed(origin: str | None) -> bool:
    return bool(origin) and origin.startswith(("chrome-extension://", "moz-extension://", "edge-extension://"))


def clean(text, limit: int) -> str:
    return CONTROL.sub(" ", str(text or ""))[:limit].strip()


def validate(body: dict) -> dict | None:
    """Return a cleaned event, or None if it is not acceptable."""
    state = body.get("state")
    if state not in STATES:
        return None
    tab = re.sub(r"[^0-9a-zA-Z_-]", "", str(body.get("tab", "0")))[:24] or "0"
    return {"state": state, "tab": tab, "action": clean(body.get("action"), 60), "title": clean(body.get("title"), 80)}


class _Bucket:
    def __init__(self, rate: int):
        self.rate, self.tokens, self.t = rate, float(rate), time.monotonic()
        self.lock = threading.Lock()

    def take(self) -> bool:
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.rate, self.tokens + (now - self.t) * self.rate)
            self.t = now
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False


class WebBridge:
    def __init__(self, tracker, pair_code: Callable[[], str], ports=PORTS):
        self.tracker, self.pair_code, self.ports = tracker, pair_code, ports
        self.port: int | None = None
        self.httpd: ThreadingHTTPServer | None = None
        self.bucket = _Bucket(RATE_PER_SECOND)
        self.events_received = 0
        self.last_event_at = 0.0
        bridge = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def _cors(self, origin):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Jarvis-Pair")
                self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
                self.send_header("Vary", "Origin")

            def _reply(self, code, obj=None, origin=None):
                body = json.dumps(obj).encode() if obj is not None else b""
                self.send_response(code)
                if origin:
                    self._cors(origin)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _gate(self):
                """Origin + pairing checks. Returns the origin if the request may proceed, else None (already answered)."""
                origin = self.headers.get("Origin")
                if self.client_address[0] != "127.0.0.1" or not origin_allowed(origin):
                    self._reply(403, {"error": "forbidden"}); return None
                return origin

            def do_OPTIONS(self):
                origin = self._gate()
                if origin:
                    self.send_response(204); self._cors(origin); self.send_header("Access-Control-Max-Age", "600")
                    self.send_header("Content-Length", "0"); self.end_headers()

            def do_GET(self):
                origin = self._gate()
                if not origin:
                    return
                if self.path == "/web/hello":                     # lets the extension find the right port; no secrets
                    return self._reply(200, {"app": "Jarvis"}, origin)
                if self.path == "/web/ping":
                    if not hmac.compare_digest(self.headers.get("X-Jarvis-Pair", ""), bridge.pair_code()):
                        return self._reply(401, {"error": "wrong pairing code"}, origin)
                    return self._reply(200, {"ok": True, "app": "Jarvis"}, origin)
                self._reply(404, {"error": "not found"}, origin)

            def do_POST(self):
                n = min(int(self.headers.get("Content-Length", 0) or 0), MAX_BODY + 1)
                raw = self.rfile.read(n) if n else b""                 # always drain the body first
                origin = self._gate()
                if not origin:
                    return
                if self.path != "/web/event":
                    return self._reply(404, {"error": "not found"}, origin)
                if not hmac.compare_digest(self.headers.get("X-Jarvis-Pair", ""), bridge.pair_code()):
                    return self._reply(401, {"error": "wrong pairing code"}, origin)
                if len(raw) > MAX_BODY:
                    return self._reply(413, {"error": "too large"}, origin)
                if not bridge.bucket.take():
                    return self._reply(429, {"error": "slow down"}, origin)
                try:
                    ev = validate(json.loads(raw or b"{}"))
                except (ValueError, AttributeError):
                    ev = None
                if ev is None:
                    return self._reply(400, {"error": "bad event"}, origin)
                bridge.events_received += 1
                bridge.last_event_at = time.time()
                bridge.tracker.handle_web(ev)
                self._reply(200, {"ok": True}, origin)

        self._handler = H

    def start(self) -> bool:
        for p in self.ports:
            try:
                self.httpd = ThreadingHTTPServer(("127.0.0.1", p), self._handler)
                break
            except OSError:
                continue
        if not self.httpd:
            return False
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return True

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
            self.port = None
