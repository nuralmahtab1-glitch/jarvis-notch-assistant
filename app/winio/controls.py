"""Quick-settings backend for the Controls panel. Made by Nur Al Mahtab.

Real, supported controls: Wi-Fi and Bluetooth radios, Airplane mode (all radios), power mode,
volume, brightness, battery, screenshot. Night light, Battery saver and Accessibility have no supported
on/off API for apps, so they open the matching Windows Settings page instead.
"""
from __future__ import annotations
import asyncio, ctypes, os, uuid
from typing import Callable

RADIO_WIFI, RADIO_BLUETOOTH = 1, 3          # Windows.Devices.Radios.RadioKind
POWER_MODES = {                              # name -> Windows power overlay GUID
    "efficiency": "961cc777-2547-4f9d-8174-7d86181b8a7a",
    "balanced": "00000000-0000-0000-0000-000000000000",
    "performance": "ded574b5-45a0-4f42-8737-46345c09c238",
}
SETTINGS_PAGES = {"nightlight": "ms-settings:nightlight", "batterysaver": "ms-settings:batterysaver",
                  "accessibility": "ms-settings:easeofaccess", "bluetooth": "ms-settings:bluetooth",
                  "wifi": "ms-settings:network-wifi", "power": "ms-settings:powersleep"}


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- radios
async def _radios():
    from winrt.windows.devices.radios import Radio
    access = await Radio.request_access_async()
    if int(access) != 1:                    # 1 = allowed
        return None, []
    return Radio, list(await Radio.get_radios_async())


def radio_states() -> dict[str, bool | None]:
    """{'wifi': True/False/None, 'bluetooth': ...}; None means the PC has no such radio."""
    async def go():
        _, radios = await _radios()
        out: dict[str, bool | None] = {"wifi": None, "bluetooth": None}
        for r in radios:
            key = {RADIO_WIFI: "wifi", RADIO_BLUETOOTH: "bluetooth"}.get(int(r.kind))
            if key:
                out[key] = int(r.state) == 1          # RadioState.ON
        return out
    try:
        return _run(go())
    except Exception:
        return {"wifi": None, "bluetooth": None}


def set_radio(kind: str, on: bool) -> bool:
    """Turn the Wi-Fi or Bluetooth radio on/off. Returns True if Windows accepted it."""
    want = {"wifi": RADIO_WIFI, "bluetooth": RADIO_BLUETOOTH}[kind]

    async def go():
        from winrt.windows.devices.radios import RadioState, RadioAccessStatus
        _, radios = await _radios()
        ok = False
        for r in radios:
            if int(r.kind) == want:
                res = await r.set_state_async(RadioState.ON if on else RadioState.OFF)
                ok = int(res) == int(RadioAccessStatus.ALLOWED)
        return ok
    try:
        return _run(go())
    except Exception:
        return False


def airplane_on(states: dict | None = None) -> bool:
    s = states or radio_states()
    present = [v for v in s.values() if v is not None]
    return bool(present) and not any(present)


def set_airplane(on: bool) -> bool:
    ok = True
    for kind in ("wifi", "bluetooth"):
        ok = set_radio(kind, not on) and ok
    return ok


# ---------------------------------------------------------------- power mode
class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


def _guid(s: str) -> _GUID:
    u = uuid.UUID(s).bytes_le
    g = _GUID()
    ctypes.memmove(ctypes.byref(g), u, 16)
    return g


def power_mode() -> str | None:
    try:
        p = ctypes.WinDLL("powrprof")
        g = _GUID()
        if p.PowerGetActualOverlayScheme(ctypes.byref(g)) != 0:
            return None
        cur = str(uuid.UUID(bytes_le=bytes(g)))
        for name, guid in POWER_MODES.items():
            if guid == cur:
                return name
        return "performance" if cur == "3af9b8d9-7c97-431d-ad78-34a8bfea439f" else None
    except Exception:
        return None


def set_power_mode(mode: str) -> bool:
    if mode not in POWER_MODES:
        return False
    try:
        return ctypes.WinDLL("powrprof").PowerSetActiveOverlayScheme(_guid(POWER_MODES[mode])) == 0
    except Exception:
        return False


# ---------------------------------------------------------------- settings pages + snapshot
def open_settings_page(name: str) -> bool:
    try:
        os.startfile(SETTINGS_PAGES[name])
        return True
    except (KeyError, OSError):
        return False


def snapshot(get_volume: Callable[[], int], get_muted: Callable[[], bool], get_brightness: Callable[[], int | None],
             get_battery: Callable[[], tuple[int | None, bool]]) -> dict:
    """Everything the panel shows, gathered in one go (slow: run it off the UI thread)."""
    radios = radio_states()
    pct, plugged = get_battery()
    def safe(fn, default):
        try:
            return fn()
        except Exception:
            return default
    return {"wifi": radios["wifi"], "bluetooth": radios["bluetooth"], "airplane": airplane_on(radios),
            "volume": safe(get_volume, 0), "muted": safe(get_muted, False),
            "brightness": safe(get_brightness, None), "battery": pct, "plugged": plugged,
            "power": power_mode() or "balanced"}
