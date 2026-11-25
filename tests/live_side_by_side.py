"""Live check on the real desktop: opens Notepad + a blank Chrome window side by side, verifies where they landed,
then closes ONLY the windows it opened. Run manually (it briefly shows two windows)."""
import ctypes, sys, time
sys.path.insert(0, ".")
ctypes.windll.shcore.SetProcessDpiAwareness(2)      # like the real app (Qt is per-monitor DPI aware)
from app.winio import layout, system as win

before = layout.visible_windows()
work = layout.work_area()
placed, failed = layout.side_by_side(["notepad", "chrome"], win.open_app)
print("work area:", work, "| placed:", [(p[0], p[1]) for p in placed], "| failed:", failed)
time.sleep(1.0)
left, right = layout.half_rects(work)
ok = []
for label, side, hwnd in placed:
    r = layout.visible_rect(hwnd); want = left if side == "left" else right
    exp = (want[0], want[1], want[0] + want[2], want[1] + want[3])
    close = all(abs(a - b) <= 3 for a, b in zip(r, exp))
    ok.append(close); print(("PASS" if close else "FAIL"), label, side, "got", r, "want", exp)
print("PASS" if len(placed) == 2 and not failed else "FAIL", "both windows opened and found")
ok.append(len(placed) == 2 and not failed)
if len(placed) == 2:
    a, b = layout.visible_rect(placed[0][2]), layout.visible_rect(placed[1][2])
    gap_ok = a[2] <= b[0] + 3 and a[0] < b[0]
    ok.append(gap_ok); print("PASS" if gap_ok else "FAIL", "windows do not overlap")
for _, _, hwnd in placed:
    layout.close_window(hwnd)
time.sleep(2)
for h in layout.visible_windows() - before:
    pass
print("left open that we did not close:", len(layout.visible_windows() - before))
sys.exit(0 if all(ok) else 1)
