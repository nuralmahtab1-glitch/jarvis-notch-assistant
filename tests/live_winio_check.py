"""Manual/live check (not run by pytest): opens a scratch window and types into it."""
import tkinter as tk, sys, time
sys.path.insert(0, ".")
from app.winio import system as w

print("volume:", w.get_volume(), "battery:", w.battery())
root = tk.Tk(); root.attributes("-topmost", True); root.geometry("500x120+200+200")
e = tk.Entry(root, width=60); e.pack(pady=20); root.update(); e.focus_force(); root.update()
time.sleep(0.4); root.update()
print("foreground is test window:", w.window_title(w.foreground_window()) == root.title() or "tk")
w.type_text("Hello, Jarvis! ünïcode ✓ 😀")
for _ in range(20):
    root.update(); time.sleep(0.05)
got = e.get(); print("typed:", repr(got))
root.destroy()
sys.exit(0 if got.startswith("Hello, Jarvis!") else 1)
