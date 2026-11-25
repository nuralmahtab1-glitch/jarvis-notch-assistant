"""Live, SAFE check of the Controls backend: reads state, and writes back exactly what is already set."""
import sys, time
sys.path.insert(0, ".")
from app.winio import controls as c, system as w

t = time.time(); st = c.radio_states(); print("radios:", st, f"({time.time()-t:.1f}s)")
for kind in ("wifi", "bluetooth"):
    if st[kind] is not None:
        ok = c.set_radio(kind, st[kind])             # set to the CURRENT state: a harmless no-op that proves the API works
        print(f"set_radio({kind}, {st[kind]}) accepted:", ok)
print("radios after:", c.radio_states(), "| airplane:", c.airplane_on())
pm = c.power_mode(); print("power mode:", pm, "| write-back ok:", c.set_power_mode(pm) if pm else None, "| now:", c.power_mode())
t = time.time(); b = w.get_brightness(); print("brightness:", b, f"({time.time()-t:.1f}s)")
if b is not None:
    w.set_brightness(b); print("brightness write-back ok, now:", w.get_brightness())
v = w.get_volume(); print("volume:", v, "muted:", w.is_muted())
t = time.time(); snap = c.snapshot(w.get_volume, w.is_muted, w.get_brightness, w.battery); print("snapshot:", snap, f"({time.time()-t:.1f}s)")
