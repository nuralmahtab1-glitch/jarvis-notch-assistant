"""jarvis-hook: tiny, stdlib-only helper that Claude Code runs for each hook event.

It forwards the hook JSON to the local Jarvis bridge. It must never slow down or break Claude Code:
if Jarvis is not running it exits silently and instantly. For PermissionRequest it prints the
decision JSON Jarvis returns (or nothing, which hands back to Claude Code's normal prompt).
Made by Nur Al Mahtab.
"""
import ctypes
import http.client
import json
import os
import sys


def process_alive(pid) -> bool:
    """Is the Jarvis that wrote the connection file still running? (A stale file must never make us wait.)"""
    try:
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259                                  # STILL_ACTIVE
    except Exception:
        return True                                                              # cannot tell: try anyway


def main() -> int:
    try:
        cfg_path = os.path.join(os.environ.get("APPDATA", ""), "Jarvis", "bridge.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("pid") and not process_alive(cfg["pid"]):
            return 0                       # Jarvis is not running: exit instantly and silently
        raw = sys.stdin.read()
        event = {}
        try:
            event = json.loads(raw) if raw.strip() else {}
        except ValueError:
            pass
        wants_reply = event.get("hook_event_name") == "PermissionRequest"
        conn = http.client.HTTPConnection("127.0.0.1", int(cfg["port"]), timeout=1.0)
        conn.connect()                     # connecting must be quick...
        if wants_reply:
            conn.sock.settimeout(45)       # ...but a permission answer may take a while (you are deciding)
        conn.request("POST", "/hook", body=raw.encode("utf-8"),
                     headers={"Content-Type": "application/json", "X-Jarvis-Token": cfg["token"]})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", "replace").strip()
        if wants_reply and resp.status == 200 and body.startswith("{"):
            sys.stdout.write(body)
            sys.stdout.flush()
    except Exception:
        pass  # Jarvis not running, or any other problem: stay out of Claude Code's way
    return 0


if __name__ == "__main__":
    sys.exit(main())
