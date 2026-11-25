"""Model + runtime manager: catalog, resumable downloads, llama.cpp server binary. Made by Nur Al Mahtab."""
from __future__ import annotations
import json, re, shutil, urllib.request, zipfile
from pathlib import Path
from typing import Callable

from app import paths

ROOT = paths.user_models()
LLM_DIR, RUNTIME_DIR = ROOT / "llm", ROOT / "llama"

CATALOG = [
    {"id": "qwen3-1.7b", "name": "Qwen3 1.7B", "tag": "Small", "size_gb": 1.1, "file": "Qwen3-1.7B-Q4_K_M.gguf",
     "url": "https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf"},
    {"id": "qwen3-4b", "name": "Qwen3 4B", "tag": "Standard", "size_gb": 2.5, "file": "Qwen3-4B-Q4_K_M.gguf",
     "url": "https://huggingface.co/unsloth/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf"},
]
UA = {"User-Agent": "Jarvis-notch/0.1"}


CUSTOM_FILE = ROOT / "custom.json"
MAX_CUSTOM = 8


def custom_models() -> list[dict]:
    """Models you imported yourself ({id, name, file, size_gb, custom: True}); a damaged file just means none."""
    try:
        data = json.loads(CUSTOM_FILE.read_text(encoding="utf-8"))
        return [m for m in data if isinstance(m, dict) and re.fullmatch(r"custom-[a-z0-9-]{1,40}", str(m.get("id", "")))
                and re.fullmatch(r"[\w .()-]{1,120}\.gguf", str(m.get("file", "")))]
    except (OSError, ValueError):
        return []


def all_models() -> list[dict]:
    return CATALOG + custom_models()


def entry(model_id: str) -> dict:
    return next(m for m in all_models() if m["id"] == model_id)


def import_gguf(src: str | Path) -> dict:
    """Copy a .gguf file into Jarvis's models folder and register it. Raises ValueError with a friendly reason."""
    src = Path(str(src).strip().strip('"'))
    if not src.is_file() or src.suffix.lower() != ".gguf":
        raise ValueError("That is not a .gguf model file.")
    with open(src, "rb") as f:
        if f.read(4) != b"GGUF":
            raise ValueError("That file does not look like a real GGUF model.")
    cur = custom_models()
    if len(cur) >= MAX_CUSTOM:
        raise ValueError("You already imported 8 models. Remove one first.")
    stem = re.sub(r"[^\w .()-]", "_", src.stem)[:80] or "model"
    mid = "custom-" + (re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")[:30] or "model")
    n, base = 2, mid
    while any(m["id"] == mid for m in cur):
        mid = f"{base}-{n}"; n += 1
    LLM_DIR.mkdir(parents=True, exist_ok=True)
    dst = LLM_DIR / f"{stem}.gguf"
    if dst.exists() and dst.resolve() != src.resolve():
        dst = LLM_DIR / f"{stem}-{mid[-6:]}.gguf"
    if dst.resolve() != src.resolve():
        shutil.copy2(src, dst)
    rec = {"id": mid, "name": stem[:40], "tag": "Imported", "file": dst.name,
           "size_gb": round(dst.stat().st_size / 1024 ** 3, 2), "custom": True}
    CUSTOM_FILE.write_text(json.dumps(cur + [rec]), encoding="utf-8")
    return rec


def remove_custom(model_id: str) -> None:
    cur = custom_models()
    rec = next((m for m in cur if m["id"] == model_id), None)
    if rec:
        p = LLM_DIR / rec["file"]
        if p.exists():
            p.unlink()
        CUSTOM_FILE.write_text(json.dumps([m for m in cur if m["id"] != model_id]), encoding="utf-8")


def model_path(model_id: str) -> Path:
    return LLM_DIR / entry(model_id)["file"]


def is_installed(model_id: str) -> bool:
    try:
        e = entry(model_id)
    except StopIteration:
        return False
    p = model_path(model_id)
    if e.get("custom"):
        return p.exists() and p.stat().st_size > 1024 ** 2
    return p.exists() and p.stat().st_size > 0.8 * e["size_gb"] * 1024 ** 3


def remove(model_id: str) -> None:
    if model_id.startswith("custom-"):
        return remove_custom(model_id)
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
    if e.get("custom"):                      # imported by you: nothing to download (only the runtime may be needed)
        if not is_installed(model_id):
            raise FileNotFoundError("The imported model file is missing. Import it again.")
        return model_path(model_id)
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
