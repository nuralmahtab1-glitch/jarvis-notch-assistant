"""Download the llama.cpp runtime and the default model (run manually, resumable)."""
import sys, time
sys.path.insert(0, ".")
from app.llm import manager as m

mid = sys.argv[1] if len(sys.argv) > 1 else "qwen3-1.7b"
t0 = time.time(); last = [0]
def prog(tag):
    def f(done, total):
        if time.time() - last[0] > 5:
            last[0] = time.time(); print(f"{tag}: {done / 1e6:.0f}/{total / 1e6:.0f} MB", flush=True)
    return f
print("runtime:", m.install_runtime(prog("runtime")))
print("model:", m.install_model(mid, prog("model")))
print("done in", round(time.time() - t0), "s; installed =", m.is_installed(mid))
