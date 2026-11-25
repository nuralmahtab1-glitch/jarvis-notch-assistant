"""Build Jarvis: icon -> app bundle -> hook helper -> installer. Made by Nur Al Mahtab.

    python packaging/build.py            # everything
    python packaging/build.py app        # just the app bundle (dist/Jarvis)
    python packaging/build.py installer  # just Setup.exe (needs dist/Jarvis)
"""
from __future__ import annotations
import shutil, subprocess, sys, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DIST, WORK = ROOT / "dist", ROOT / "build"
sys.path.insert(0, str(ROOT))
from app import config  # noqa: E402


def version_info(name: str, desc: str, original: str) -> str:
    v = tuple(int(x) for x in config.VERSION.split(".")) + (0,)
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{config.AUTHOR}'),
      StringStruct('FileDescription', '{desc}'),
      StringStruct('FileVersion', '{config.VERSION}'),
      StringStruct('InternalName', '{name}'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 {config.AUTHOR}. {config.CREDIT}.'),
      StringStruct('OriginalFilename', '{original}'),
      StringStruct('ProductName', '{config.APP_NAME}'),
      StringStruct('ProductVersion', '{config.VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def run(cmd: list[str], **kw):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT, **kw)


def pyi(*args):
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", DIST, "--workpath", WORK, *args])


def build_app():
    run([sys.executable, HERE / "make_icon.py"])
    (HERE / "version_info.txt").write_text(version_info("Jarvis", f"{config.APP_NAME} voice assistant", "Jarvis.exe"), encoding="utf-8")
    pyi(HERE / "jarvis.spec")
    # the tiny helper Claude Code runs for each hook: stdlib only, so it starts fast
    (HERE / "version_hook.txt").write_text(version_info("jarvis-hook", f"{config.APP_NAME} Claude Code hook helper", "jarvis-hook.exe"), encoding="utf-8")
    # an unpacked folder (not one file): a one-file exe unpacks itself on every call, which is slow
    pyi("--onedir", "--console", "--name", "jarvis-hook", "--icon", HERE / "jarvis.ico",
        "--version-file", HERE / "version_hook.txt", ROOT / "app" / "claude_bridge" / "hook.py")
    shutil.rmtree(DIST / "Jarvis" / "hook", ignore_errors=True)
    shutil.copytree(DIST / "jarvis-hook", DIST / "Jarvis" / "hook")


def build_installer():
    app = DIST / "Jarvis"
    assert (app / "Jarvis.exe").exists(), "build the app first"
    payload = HERE / "payload.zip"
    print("zipping payload...", flush=True)
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in app.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(app))
    (HERE / "version_setup.txt").write_text(version_info("JarvisSetup", f"{config.APP_NAME} installer", "JarvisSetup.exe"), encoding="utf-8")
    pyi("--onefile", "--windowed", "--name", "JarvisSetup", "--icon", HERE / "jarvis.ico",
        "--version-file", HERE / "version_setup.txt", "--add-data", f"{payload};.",
        "--add-data", f"{ROOT / 'LICENSE'};.", "--paths", ROOT, HERE / "setup_app.py")
    payload.unlink(missing_ok=True)
    print("\nInstaller:", DIST / "JarvisSetup.exe", f"({(DIST / 'JarvisSetup.exe').stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "app"):
        build_app()
    if what in ("all", "installer"):
        build_installer()
