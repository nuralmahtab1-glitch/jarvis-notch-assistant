"""Live end-to-end test of the browser extension in a REAL Chrome/Edge: mock claude.ai pages -> content script ->
service worker -> Jarvis's local endpoint -> tracker. Needs a real browser installed; run manually."""
import http.server, json, os, shutil, socketserver, subprocess, sys, tempfile, threading, time
from pathlib import Path
sys.path.insert(0, ".")
from app.claude_bridge.tracker import Tracker
from app.claude_bridge.web import WebBridge

ROOT = Path(__file__).resolve().parents[1]
CODE = "A1B2C3D4"
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe"]

PAGES = {
    "working": "<textarea></textarea><button aria-label='Stop generating'>Stop</button>",
    "needs": "<textarea></textarea><button>Allow once</button><button>Deny</button>",
    "idle": "<textarea></textarea><p>Ready.</p>",
    "nocomposer": "<h1>Some other page</h1><p>No message box here.</p>",
    "finish": "<textarea></textarea><button id=s aria-label='Stop generating'>Stop</button>"
              "<script>setTimeout(()=>document.getElementById('s').remove(), 4000)</script>",
}


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        name = self.path.rsplit("/", 1)[-1].replace(".html", "")
        if name in PAGES:
            body = f"<!doctype html><html><head><title>mock {name}</title></head><body>{PAGES[name]}</body></html>".encode()
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()


def make_test_copy(dst: Path):
    shutil.copytree(ROOT / "extension", dst)
    m = json.loads((dst / "manifest.json").read_text())
    m["content_scripts"][0]["matches"].append("http://127.0.0.1/mock/*")             # test pages only
    (dst / "manifest.json").write_text(json.dumps(m))
    sel = (dst / "selectors.js").read_text().replace("debug: false", "debug: true")
    (dst / "selectors.js").write_text(sel)
    bg = (dst / "background.js").read_text()
    (dst / "background.js").write_text(f'chrome.storage.local.set({{ pairCode: "{CODE}" }});\n' + bg)   # auto-pair (test copy only)


def run_browser(exe, ext, url, user_dir):
    args = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={user_dir}",
            f"--load-extension={ext}", f"--disable-extensions-except={ext}", "--disable-features=DisableLoadExtensionCommandLineSwitch",
            "--enable-unsafe-extension-debugging", url]
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait(cond, secs):
    end = time.time() + secs
    while time.time() < end:
        if cond(): return True
        time.sleep(0.25)
    return False


def main():
    exe = next((b for b in BROWSERS if os.path.exists(b)), None)
    srv = socketserver.TCPServer(("127.0.0.1", 0), Quiet); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tracker = Tracker(); received = []
    orig = tracker.handle_web
    tracker.handle_web = lambda ev: (received.append(dict(ev)), orig(ev))[1]
    bridge = WebBridge(tracker, lambda: CODE)
    assert bridge.start(), "ports 17894-17899 are busy (is real Jarvis running with the web option on?)"
    results = []

    def check(name, ok, extra=""):
        results.append(bool(ok)); print("PASS" if ok else "FAIL", name, extra, flush=True)

    tmp = Path(tempfile.mkdtemp(prefix="jarvis-ext-")); ext = tmp / "ext"; make_test_copy(ext)
    print("browser:", exe)
    scenarios = [
        ("working", lambda: (tracker.urgent() or type("x", (), {"state": ""})).state == "working", "page with a Stop button -> notch shows 'working'"),
        ("needs", lambda: (tracker.urgent() or type("x", (), {"state": ""})).state == "needs_you", "page with Allow + Deny -> notch shows 'needs you'"),
    ]
    for name, cond, label in scenarios:
        tracker.sessions.clear(); received.clear()
        p = run_browser(exe, ext, f"http://127.0.0.1:{port}/mock/{name}.html", tmp / f"profile-{name}")
        ok = wait(cond, 30)
        if p: p.terminate()
        try: p.wait(8)
        except Exception: p.kill()
        check(label, ok, f"(events seen: {len(received)})")
        if not ok and not received:
            print("   no event arrived at all: this browser may not allow loading the extension from the command line")
            break
    else:
        # idle page: nothing should show; page without a message box: must report unavailable (nothing shown), never 'working'
        for name, label in (("idle", "page with only a message box -> nothing shown"), ("nocomposer", "page that is not Claude Code -> nothing shown")):
            tracker.sessions.clear(); received.clear()
            p = run_browser(exe, ext, f"http://127.0.0.1:{port}/mock/{name}.html", tmp / f"profile-{name}")
            time.sleep(8); p.terminate()
            try: p.wait(8)
            except Exception: p.kill()
            check(label, tracker.urgent() is None and not any(e["state"] in ("working", "needs_you", "done") for e in received), f"(events: {[e['state'] for e in received]})")
        # a task that finishes: working -> done
        tracker.sessions.clear(); received.clear(); tracker.history.clear()
        p = run_browser(exe, ext, f"http://127.0.0.1:{port}/mock/finish.html", tmp / "profile-finish")
        ok = wait(lambda: tracker.history and tracker.history[0]["result"] == "done", 40)
        p.terminate()
        try: p.wait(8)
        except Exception: p.kill()
        check("a task that stops working is recorded as finished", ok, f"(events: {[e['state'] for e in received]})")
        # privacy: nothing but a state, a tab number and a fixed label ever left the browser
        allowed_actions = {"", "Working", "Waiting for your OK in the browser"}
        check("only state + fixed label + tab id were sent (no title, no page text)",
              all(set(e) == {"state", "tab", "action", "title"} and e["title"] == "" and e["action"] in allowed_actions for e in received) or not received)
    bridge.stop(); srv.shutdown(); shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{sum(results)}/{len(results)} extension checks passed")
    sys.exit(0 if results and all(results) else 1)


if __name__ == "__main__":
    main()
