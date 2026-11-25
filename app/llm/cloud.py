"""Optional cloud brain: ChatGPT (OpenAI), Gemini, Claude or any OpenAI-compatible service, using YOUR API key.
Made by Nur Al Mahtab.

Privacy: only the text of your question (plus the last few turns and the fixed instructions) is sent, and only when
you pick a cloud provider in Settings. Screen contents, clipboard, shelf files and your to-do list are never sent.
Simple commands (timers, volume, opening apps...) are understood on this PC by rules and never reach the cloud.
"""
from __future__ import annotations
import json, re, urllib.error, urllib.request
from urllib.parse import urlparse

PROVIDERS = {
    "openai": {"label": "ChatGPT", "base": "https://api.openai.com/v1", "model": "gpt-4o-mini",
               "keys": "platform.openai.com/api-keys"},
    "gemini": {"label": "Gemini", "base": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.5-flash",
               "keys": "aistudio.google.com/apikey"},
    "claude": {"label": "Claude", "base": "https://api.anthropic.com/v1", "model": "claude-haiku-5-5",
               "keys": "console.anthropic.com/settings/keys"},
    "custom": {"label": "Other", "base": "", "model": "", "keys": ""},
}
ORDER = ["local", "openai", "gemini", "claude", "custom"]


def valid_base(url: str) -> bool:
    """https only (so the key is never sent in clear text), except for a service on this very PC."""
    try:
        u = urlparse(url.strip())
    except ValueError:
        return False
    if not u.hostname or u.username or u.password:
        return False
    return u.scheme == "https" or (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1"))


def valid_key(key: str) -> bool:
    return bool(re.fullmatch(r"[\x21-\x7e]{8,300}", key.strip()))           # printable, no spaces


def clean_error(body: str, status: int) -> str:
    """A short, safe reason for the user (never echoes the key)."""
    if status in (401, 403):
        return "The service refused the key. Check that it is correct and has access."
    if status == 404:
        return "The service did not recognise that model name."
    if status == 429:
        return "The service says you are out of quota or going too fast."
    if status >= 500:
        return "The service had a problem. Try again in a minute."
    try:
        msg = json.loads(body).get("error", {})
        msg = msg.get("message") if isinstance(msg, dict) else str(msg)
        return re.sub(r"(sk|key|AIza)[-\w]{8,}", "[key]", str(msg))[:140] or f"The service answered {status}."
    except Exception:
        return f"The service answered {status}."


class CloudError(Exception):
    pass


class CloudBackend:
    def __init__(self, provider, model, base, key):
        self._provider, self._model, self._base, self._key = provider, model, base, key

    def settings(self):
        p = self._provider()
        preset = PROVIDERS.get(p, PROVIDERS["custom"])
        return p, (self._model().strip() or preset["model"]), (self._base().strip() if p == "custom" else preset["base"]), self._key(p)

    def installed(self) -> bool:                    # "ready to answer without a download"
        p, model, base, key = self.settings()
        return p in PROVIDERS and bool(model) and valid_base(base) and (bool(key) or urlparse(base).hostname in ("localhost", "127.0.0.1"))

    def chat(self, messages, max_tokens: int = 200, temperature: float = 0.2, json_mode: bool = False, timeout: float = 30.0) -> str:
        p, model, base, key = self.settings()
        if not self.installed():
            raise CloudError("The cloud brain is not set up.")
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        for attempt in (1, 2):
            req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "User-Agent": "Jarvis-notch/0.1",
                                                  **({"Authorization": "Bearer " + key} if key else {})})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = json.load(r)
                return (data["choices"][0]["message"].get("content") or "").strip()
            except urllib.error.HTTPError as e:
                text = e.read().decode("utf-8", "replace")[:600]
                if e.code == 400 and attempt == 1 and "response_format" in body:
                    body.pop("response_format")     # a service that does not know JSON mode: ask again without it
                    continue
                raise CloudError(clean_error(text, e.code)) from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                raise CloudError("Could not reach the service. Check your internet connection.") from None
            except (KeyError, IndexError, ValueError):
                raise CloudError("The service sent a reply I could not read.") from None
        raise CloudError("The service did not accept the request.")

    def test(self) -> str:
        """Returns '' if it works, else a short reason."""
        try:
            out = self.chat([{"role": "user", "content": "Reply with the single word: ok"}], max_tokens=8, temperature=0.0, timeout=20)
            return "" if out else "The service answered with nothing."
        except CloudError as e:
            return str(e)

    def stop(self): pass


class RoutedBackend:
    """Picks cloud or this PC for each question. If the cloud fails (offline, no quota) and a local brain is installed,
    the local one answers instead, so Jarvis never goes quiet."""

    def __init__(self, local, cloud: CloudBackend, provider, on_fallback=None):
        self.local, self.cloud, self._provider, self.on_fallback = local, cloud, provider, on_fallback
        self.last_error = ""

    @property
    def using_cloud(self) -> bool:
        return self._provider() != "local" and self.cloud.installed()

    def installed(self) -> bool:
        return self.cloud.installed() if self._provider() != "local" else self.local.installed()

    def chat(self, messages, **kw):
        if self._provider() != "local":
            try:
                out = self.cloud.chat(messages, **kw)
                self.last_error = ""
                return out
            except CloudError as e:
                self.last_error = str(e)
                if not self.local.installed():
                    raise
                if self.on_fallback:
                    self.on_fallback(str(e))
        return self.local.chat(messages, **kw)

    def stop(self): self.local.stop()
    def idle_stop(self, seconds): return self.local.idle_stop(seconds)
