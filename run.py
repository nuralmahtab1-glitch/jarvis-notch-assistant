"""Jarvis launcher. Made by Nur Al Mahtab."""
import os, sys
from pathlib import Path

# The installed app has no console: keep a small, self-trimming log so problems can be diagnosed.
if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
    _d = Path(os.environ.get("APPDATA", str(Path.home()))) / "Jarvis"
    _d.mkdir(parents=True, exist_ok=True)
    _log = _d / "jarvis.log"
    if _log.exists() and _log.stat().st_size > 1_000_000:
        _log.unlink()
    sys.stdout = sys.stderr = open(_log, "a", buffering=1, encoding="utf-8")

# Headless maintenance commands: handled before the (slow) UI libraries are imported.
if "--awake-only" in sys.argv or "--awake-stop" in sys.argv:
    from app.awake_only import run as _awake_run
    sys.exit(_awake_run(sys.argv))
if "--disconnect-claude" in sys.argv:
    from app.claude_bridge import installer
    try:
        installer.disconnect()
    except Exception:
        pass
    sys.exit(0)
if "--uninstall" in sys.argv:
    from app.uninstall import run
    sys.exit(run(silent="--silent" in sys.argv, delete_data=True if "--delete-data" in sys.argv else None))

from app.main import main

sys.exit(main())
