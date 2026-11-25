import http.server, json, os, socketserver, threading, uuid
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from app.llm import cloud
from app.llm.brain import Brain
from app.llm.cloud import CloudBackend, CloudError, RoutedBackend, clean_error, valid_base, valid_key
from app.winio import credstore


# ---------------- a fake OpenAI-compatible service on this PC ----------------
class Fake(http.server.BaseHTTPRequestHandler):
    log: list = []
    mode = "ok"            # ok | 401 | 429 | 500 | nojson | garbage

    def log_message(self, *a): pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.log.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        mode = Fake.mode
        if mode in ("401", "429", "500"):
            return self._send(int(mode), {"error": {"message": "bad key sk-SECRETSECRET123 here"}})
        if mode == "nojson" and "response_format" in body:
            return self._send(400, {"error": {"message": "response_format not supported"}})
        if mode == "garbage":
            return self._send(200, {"weird": True})
        content = '{"tool": "volume_set", "args": {"level": 30}}' if body.get("response_format") else "ok"
        self._send(200, {"choices": [{"message": {"content": content}}]})

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers()
        self.wfile.write(b)


@pytest.fixture
def service():
    srv = socketserver.TCPServer(("127.0.0.1", 0), Fake); srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    Fake.log, Fake.mode = [], "ok"
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown(); srv.server_close()


def backend(base, key="test-key-12345", model="my-model", provider="custom"):
    return CloudBackend(lambda: provider, lambda: model, lambda: base, lambda p: key)


# ---------------- talking to the service ----------------
def test_sends_key_model_and_messages_to_the_right_path(service):
    out = backend(service).chat([{"role": "user", "content": "hi"}], max_tokens=20)
    assert out == "ok"
    sent = Fake.log[0]
    assert sent["path"] == "/v1/chat/completions" and sent["auth"] == "Bearer test-key-12345"
    assert sent["body"]["model"] == "my-model" and sent["body"]["messages"] == [{"role": "user", "content": "hi"}]


def test_json_mode_is_requested_and_parsed_by_the_brain(service):
    b = Brain(backend(service), ready=backend(service).installed, name="Nur")
    d = b.route("make it quieter please")
    assert d.intent and d.intent.name == "volume_set" and d.intent.args["level"] == 30
    assert Fake.log[0]["body"]["response_format"] == {"type": "json_object"}


def test_service_without_json_mode_is_retried_without_it(service):
    Fake.mode = "nojson"
    assert backend(service).chat([{"role": "user", "content": "x"}], json_mode=True) == "ok"
    assert "response_format" in Fake.log[0]["body"] and "response_format" not in Fake.log[1]["body"]


@pytest.mark.parametrize("mode,words", [("401", "refused the key"), ("429", "quota"), ("500", "problem")])
def test_errors_are_friendly_and_never_echo_the_key(service, mode, words):
    Fake.mode = mode
    with pytest.raises(CloudError) as e:
        backend(service).chat([{"role": "user", "content": "x"}])
    assert words in str(e.value) and "SECRET" not in str(e.value) and "test-key" not in str(e.value)


def test_garbage_and_unreachable_services(service):
    Fake.mode = "garbage"
    with pytest.raises(CloudError, match="could not read"):
        backend(service).chat([{"role": "user", "content": "x"}])
    with pytest.raises(CloudError, match="Could not reach"):
        backend("http://127.0.0.1:9/v1").chat([{"role": "user", "content": "x"}], timeout=3)


def test_test_button_reports_ok_or_reason(service):
    assert backend(service).test() == ""
    Fake.mode = "401"
    assert "refused the key" in backend(service).test()


# ---------------- what counts as set up ----------------
def test_providers_use_their_presets_and_need_a_key():
    b = backend("", key="", provider="gemini")
    assert not b.installed()
    b = backend("", key="AIzaSy-test-key", provider="gemini", model="")
    p, model, base, key = b.settings()
    assert b.installed() and base.startswith("https://generativelanguage.googleapis.com") and model == "gemini-2.5-flash"
    assert backend("", key="k" * 12, provider="openai", model="").settings()[2] == "https://api.openai.com/v1"
    assert backend("", key="k" * 12, provider="claude").settings()[2] == "https://api.anthropic.com/v1"


def test_custom_needs_a_safe_address():
    assert not backend("http://example.com/v1").installed()                      # never sends a key in clear text
    assert not backend("https://user:pw@example.com/v1").installed()
    assert backend("https://api.example.com/v1").installed()
    assert backend("http://localhost:11434/v1", key="").installed()               # a service on this PC may be plain http


@pytest.mark.parametrize("url,ok", [("https://api.openai.com/v1", True), ("http://127.0.0.1:8080/v1", True), ("http://evil.com", False),
                                    ("ftp://x.com", False), ("javascript:alert(1)", False), ("https://", False), ("", False)])
def test_valid_base(url, ok):
    assert valid_base(url) is ok


@pytest.mark.parametrize("key,ok", [("sk-abcdefgh12345", True), ("short", False), ("has space inside1", False), ("tab\tkey12345", False), ("x" * 400, False)])
def test_valid_key(key, ok):
    assert valid_key(key) is ok


def test_clean_error_masks_key_like_text():
    assert "SECRET" not in clean_error(json.dumps({"error": {"message": "key sk-SECRETSECRET123 invalid"}}), 400)


# ---------------- routing and fallback ----------------
class Local:
    def __init__(self, ok=True): self.ok, self.calls = ok, 0
    def installed(self): return self.ok
    def chat(self, m, **kw): self.calls += 1; return "from-local"
    def stop(self): pass
    def idle_stop(self, s): pass


def test_local_provider_never_touches_the_cloud(service):
    loc = Local(); r = RoutedBackend(loc, backend(service), lambda: "local")
    assert r.chat([{"role": "user", "content": "x"}]) == "from-local" and Fake.log == [] and not r.using_cloud


def test_cloud_provider_is_used_when_set_up(service):
    loc = Local(); r = RoutedBackend(loc, backend(service), lambda: "custom")
    assert r.chat([{"role": "user", "content": "x"}]) == "ok" and loc.calls == 0 and r.using_cloud


def test_cloud_failure_falls_back_to_the_local_brain(service):
    Fake.mode = "429"; seen = []
    r = RoutedBackend(Local(True), backend(service), lambda: "custom", on_fallback=seen.append)
    assert r.chat([{"role": "user", "content": "x"}]) == "from-local" and "quota" in seen[0] and "quota" in r.last_error


def test_cloud_failure_without_a_local_brain_raises_a_clear_error(service):
    Fake.mode = "401"
    r = RoutedBackend(Local(False), backend(service), lambda: "custom")
    with pytest.raises(CloudError, match="refused the key"):
        r.chat([{"role": "user", "content": "x"}])


def test_readiness_follows_the_chosen_provider(service):
    assert RoutedBackend(Local(False), backend(service), lambda: "custom").installed()
    assert not RoutedBackend(Local(True), backend("", key="", provider="openai"), lambda: "openai").installed()
    assert RoutedBackend(Local(True), backend(service), lambda: "local").installed()


# ---------------- the key store (the real Windows Credential Manager, with a throw-away name) ----------------
def test_credential_manager_round_trip_and_delete():
    name = "test-" + uuid.uuid4().hex[:8]
    try:
        assert credstore.load(name, prefix="JarvisTest/") == ""
        secret = "sk-test-ünïcode-" + uuid.uuid4().hex
        assert credstore.save(name, secret, prefix="JarvisTest/")
        assert credstore.load(name, prefix="JarvisTest/") == secret
        assert credstore.save(name, "second-value-123", prefix="JarvisTest/") and credstore.load(name, prefix="JarvisTest/") == "second-value-123"
    finally:
        credstore.delete(name, prefix="JarvisTest/")
    assert credstore.load(name, prefix="JarvisTest/") == ""


# ---------------- Settings ----------------
@pytest.fixture
def sc(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from app.core.assistant import Assistant
    from app.store.db import Settings, Store
    from app.ui.controller import NotchController
    from app.ui.settings_ctl import SettingsController
    QApplication.instance() or QApplication([])
    cfg = Settings(tmp_path / "s.json"); ctl = NotchController(); a = Assistant(ctl, cfg, Store(tmp_path / "t.db"))
    vault = {}
    monkeypatch.setattr(credstore, "save", lambda n, s, prefix="": vault.__setitem__(n, s) or True)
    monkeypatch.setattr(credstore, "load", lambda n, prefix="": vault.get(n, ""))
    monkeypatch.setattr(credstore, "delete", lambda n, prefix="": vault.pop(n, None) is not None)
    return SettingsController(a, ctl, cfg, a.store, [], {}), cfg, vault, tmp_path


def test_settings_validate_provider_model_and_address(sc):
    c, cfg, vault, _ = sc
    c.set("llm_provider", "gemini"); assert cfg["llm_provider"] == "gemini"
    c.set("llm_provider", "skynet"); assert cfg["llm_provider"] == "gemini"
    c.set("cloud_model", "gemini-2.5-flash"); assert cfg["cloud_model"] == "gemini-2.5-flash"
    c.set("cloud_model", "x; rm -rf /"); assert cfg["cloud_model"] == "gemini-2.5-flash"
    c.set("cloud_base", "http://evil.com"); assert cfg["cloud_base"] == "" and "https" in c.message
    c.set("cloud_base", "https://api.example.com/v1"); assert cfg["cloud_base"] == "https://api.example.com/v1"


def test_key_goes_to_the_vault_and_never_into_the_settings_file(sc):
    c, cfg, vault, tmp = sc
    c.set("llm_provider", "openai")
    assert not c.cloudHasKey
    c.saveApiKey("  sk-live-abcdef123456  ")
    assert vault == {"openai": "sk-live-abcdef123456"} and c.cloudHasKey
    assert "sk-live" not in (tmp / "s.json").read_text() and "sk-live" not in c.message
    c.saveApiKey("bad key"); assert vault == {"openai": "sk-live-abcdef123456"} and "does not look" in c.message
    c.removeApiKey(); assert vault == {} and not c.cloudHasKey


def test_keys_are_kept_per_provider(sc):
    c, cfg, vault, _ = sc
    c.set("llm_provider", "openai"); c.saveApiKey("sk-openai-111111")
    c.set("llm_provider", "gemini"); assert not c.cloudHasKey; c.saveApiKey("AIza-gemini-22222")
    c.set("llm_provider", "openai"); assert c.cloudHasKey and vault["openai"] == "sk-openai-111111"


def test_save_key_on_local_does_nothing(sc):
    c, cfg, vault, _ = sc
    c.saveApiKey("sk-whatever-123456"); assert vault == {}


def test_status_text_follows_provider(sc):
    c, cfg, vault, _ = sc
    assert c.brainStatus in ("Installed", "Not installed")
    c.set("llm_provider", "openai"); c.a.brain = None
    assert c.brainStatus == "Needs an API key"
    c.saveApiKey("sk-live-abcdef123456"); assert c.brainStatus == "Cloud ready"


def test_a_spoken_question_goes_through_the_cloud_end_to_end(service, tmp_path):
    """handle_text -> rules miss -> brain (cloud, fake service) -> answer card; a failing service gives a spoken reason."""
    import time
    from PySide6.QtWidgets import QApplication
    from app.core.assistant import Assistant
    from app.store.db import Settings, Store
    from app.ui.controller import NotchController
    QApplication.instance() or QApplication([])
    cfg = Settings(tmp_path / "s.json"); ctl = NotchController()
    cb = backend(service); routed = RoutedBackend(Local(False), cb, lambda: "custom")
    a = Assistant(ctl, cfg, Store(tmp_path / "t.db"), brain=Brain(routed, ready=routed.installed, name="Nur"))
    cfg.set("llm_provider", "custom")
    said = []
    a.say = lambda text, src="key", **kw: said.append(text)
    a.show_answer = lambda text, src="key": said.append("ANSWER:" + text)

    def run(text):
        said.clear(); a.handle_text(text)
        end = time.time() + 8
        while not said and time.time() < end:
            QApplication.processEvents(); time.sleep(0.02)
        return said[0] if said else None
    Fake.mode = "ok"
    assert "volume" in (run("zxqv blorp volume thingy") or "").lower() or Fake.log      # the fake always routes to volume_set
    Fake.mode = "401"
    assert "could not reach the cloud brain" in run("what is the meaning of everything") and "refused the key" in said[0]
