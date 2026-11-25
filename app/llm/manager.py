"""Model + runtime manager: catalog, resumable downloads, llama.cpp server binary. Made by Nur Al Mahtab."""
from __future__ import annotations
import json, os, re, shutil, urllib.request, zipfile
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2] / "models"
LLM_DIR, RUNTIME_DIR = ROOT / "llm", ROOT / "llama"

CATALOG = [
    {"id": "qwen3-1.7b", "name": "Qwen3 1.7B", "tag": "Small", "size_gb": 1.1, "file": "Qwen3-1.7B-Q4_K_M.gguf",
     "url": "https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf"},
    {"id": "qwen3-4b", "name": "Qwen3 4B", "tag": "Standard", "size_gb": 2.5, "file": "Qwen3-4B-Q4_K_M.gguf",
     "url": "https://huggingface.co/unsloth/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf"},
]
UA = {"User-Agent": "Jarvis-notch/0.1"}


def entry(model_id: str) -> dict:
    return next(m for m in CATALOG if m["id"] == model_id)


def model_path(model_id: str) -> Path:
    return LLM_DIR / entry(model_id)["file"]


def is_installed(model_id: str) -> bool:
    p = model_path(model_id)
    return p.exists() and p.stat().st_size > 0.8 * entry(model_id)["size_gb"] * 1024 ** 3


def remove(model_id: str) -> None:
    for p in (model_path(model_id), model_path(model_id).with_suffix(".part")):
        if p.exists():
            p.unlink()


def server_binary() -> Path | None:
    hits = list(RUNTIME_DIR.rglob("llama-server.exe"))
    return hits[0] if hits else None


def download(url: str, dest: Path, progress: Callable[[int, int], None] | None = None,
             cancel: Callable[[], bool] = lambda: False) -> Path:
    """Resumable download to dest (via dest.part). Raises on failure; leaves .part for a later resume."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={**UA, **({"Range": f"bytes={have}-"} if have else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        if have and r.status != 206:                 # server ignored Range: start over
            have = 0
        total = have + int(r.headers.get("Content-Length", 0))
        with open(part, "ab" if have else "wb") as f:
            done = have
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                if cancel():
                    raise InterruptedError("download cancelled")
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    if total and part.stat().st_size < total:
        raise IOError("download incomplete")
    part.replace(dest)
    return dest


def install_model(model_id: str, progress=None, cancel=lambda: False) -> Path:
    e = entry(model_id)
    return download(e["url"], model_path(model_id), progress, cancel)


def install_runtime(progress=None) -> Path:
    """Download the CPU build of llama.cpp's llama-server from the official GitHub release."""
    existing = server_binary()
    if existing:
        return existing
    req = urllib.request.Request("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=12", headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        releases = json.loads(r.read().decode())
    asset = None
    for rel in releases:                      # newest release that actually ships a Windows CPU build
        asset = next((a for a in rel["assets"] if re.search(r"llama-.*-bin-win-cpu-x64\.zip$", a["name"])), None)
        if asset:
            break
    if not asset:
        raise RuntimeError("no Windows CPU build found in recent llama.cpp releases")
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    z = download(asset["browser_download_url"], RUNTIME_DIR / asset["name"], progress)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(RUNTIME_DIR)
    z.unlink()
    b = server_binary()
    if not b:
        raise RuntimeError("llama-server.exe not found after extracting")
    return b
