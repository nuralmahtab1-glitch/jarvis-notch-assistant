"""Runs llama.cpp's llama-server locally and talks to it. Made by Nur Al Mahtab."""
from __future__ import annotations
import http.client, json, os, socket, subprocess, threading, time, urllib.error, urllib.request
from pathlib import Path


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LlamaServer:
    def __init__(self, binary: Path, model: Path, ctx: int = 4096, threads: int = 4):
        self.binary, self.model, self.ctx, self.threads = binary, model, ctx, threads
        self.port = 0
        self.proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self.last_used = time.monotonic()

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, timeout: float = 180.0):
        with self._lock:
            if self.running:
                return
            self.port = _free_port()
            from app.store.db import data_dir
            self._log = open(data_dir() / "llama.log", "wb")          # overwritten on every start; helps debugging
            self.proc = subprocess.Popen(
                [str(self.binary), "-m", str(self.model), "--host", "127.0.0.1", "--port", str(self.port),
                 "-c", str(self.ctx), "-t", str(self.threads), "-tb", str(max(self.threads, min(8, (os.cpu_count() or 4)))), "--no-webui"],
                stdout=self._log, stderr=subprocess.STDOUT, creationflags=0x08000000)
            t0 = time.time()
            while time.time() - t0 < timeout:
                if self.proc.poll() is not None:
                    raise RuntimeError("llama-server exited while starting")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=1) as r:
                        if r.status == 200:
                            self.last_used = time.monotonic()
                            return
                except Exception:
                    time.sleep(0.4)
            self.stop()
            raise TimeoutError("llama-server did not become ready")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except Exception:
                self.proc.kill()
        self.proc = None

    def chat(self, messages: list[dict], max_tokens: int = 200, temperature: float = 0.2,
             json_mode: bool = False, timeout: float = 60.0) -> str:
        body = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stream": False,
                "chat_template_kwargs": {"enable_thinking": False}, "cache_prompt": True}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        payload = json.dumps(body).encode()
        last: Exception | None = None
        for attempt in (1, 2):               # if the server died mid-request, restart it once and retry
            try:
                self.start()
                req = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/chat/completions", data=payload,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    out = json.loads(r.read().decode())
                self.last_used = time.monotonic()
                return out["choices"][0]["message"]["content"].strip()
            except (ConnectionError, urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as e:
                last = e
                self.stop()
        raise last


class LocalBackend:
    """Chat backend that starts llama-server on first use and stops it when idle (RAM is precious)."""

    def __init__(self, model_id_getter):
        self._model_id = model_id_getter
        self.srv: LlamaServer | None = None
        self._srv_model = None

    def installed(self) -> bool:
        from app.llm import manager
        try:
            return bool(manager.server_binary()) and manager.is_installed(self._model_id())
        except Exception:
            return False

    def _server(self) -> LlamaServer:
        from app.llm import manager
        mid = self._model_id()
        if self.srv is None or self._srv_model != mid:
            self.stop()
            import os
            self.srv = LlamaServer(manager.server_binary(), manager.model_path(mid),
                                   threads=max(2, min(4, (os.cpu_count() or 4) // 2)))
            self._srv_model = mid
        return self.srv

    def chat(self, messages, **kw):
        return self._server().chat(messages, **kw)

    @property
    def loaded(self) -> bool:
        return bool(self.srv and self.srv.running)

    def idle_stop(self, seconds: float = 600.0):
        if self.srv and self.srv.running and time.monotonic() - self.srv.last_used > seconds:
            self.srv.stop()

    def stop(self):
        if self.srv:
            self.srv.stop()
            self.srv = None
