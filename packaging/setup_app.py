"""JarvisSetup: the installer. Made by Nur Al Mahtab.

GUI wizard (Welcome, Licence, Options, Installing, Finished) or silent:
    JarvisSetup.exe /S [/D=C:\\Some\\Folder] [--no-shortcuts] [--desktop] [--autostart] [--no-launch]
Per-user: no administrator rights needed. Installs to %LOCALAPPDATA%\\Programs\\Jarvis by default.
Safety: it never deletes or overwrites a folder unless that folder already contains a Jarvis install.
"""
from __future__ import annotations
import os, queue, shutil, subprocess, sys, threading, winreg, zipfile
from pathlib import Path

from app import config
from app.uninstall import UNINSTALL_KEY, kill_other_instances, shortcut_paths, start_menu_dir

APP = config.APP_NAME
DEFAULT_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / APP


def resource(name: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / name


def is_our_install(d: Path) -> bool:
    return (d / "Jarvis.exe").exists() and (d / "_internal").exists()


def check_destination(d: Path) -> str | None:
    """Return a problem description, or None if it is safe to install here."""
    d = d.resolve()
    if d == Path(d.anchor) or len(d.parts) < 3:
        return "Please choose a folder, not a drive root."
    if d.exists() and any(d.iterdir()) and not is_our_install(d):
        return "That folder already has other files in it. Choose an empty folder, or a new one (for example ...\\Jarvis)."
    return None


def make_shortcut(link: Path, target: Path, workdir: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');$s.TargetPath='%s';$s.WorkingDirectory='%s';"
          "$s.IconLocation='%s';$s.Description='%s';$s.Save()") % (link, target, workdir, target, f"{APP} - {config.CREDIT}")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True, creationflags=0x08000000)


def dir_size_kb(d: Path) -> int:
    return int(sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1024)


def install(dest: Path, payload: Path, start_menu=True, desktop=False, autostart=False, progress=lambda f, t: None) -> None:
    problem = check_destination(dest)
    if problem:
        raise RuntimeError(problem)
    kill_other_instances()
    if is_our_install(dest):                                       # upgrade: replace the old program files cleanly
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(payload) as z:
        infos = z.infolist()
        root = dest.resolve()
        for i, info in enumerate(infos):
            out = (dest / info.filename).resolve()
            if root not in out.parents and out != root:            # never write outside the install folder
                raise RuntimeError("The installer package is damaged.")
            z.extract(info, dest)
            if i % 25 == 0:
                progress(i, len(infos))
    progress(len(infos), len(infos))
    exe = dest / "Jarvis.exe"
    links = shortcut_paths()
    if start_menu:
        make_shortcut(links[0], exe, dest)
    if desktop:
        make_shortcut(links[1], exe, dest)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        for name, val in (("DisplayName", APP), ("DisplayVersion", config.VERSION), ("Publisher", config.AUTHOR),
                          ("InstallLocation", str(dest)), ("DisplayIcon", str(exe)),
                          ("UninstallString", f'"{exe}" --uninstall'), ("Comments", config.CREDIT)):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, dir_size_kb(dest))
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
    if autostart:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, f'"{exe}"')


def launch(dest: Path) -> None:
    subprocess.Popen([str(dest / "Jarvis.exe")], cwd=str(dest), creationflags=0x00000008 | 0x00000200, close_fds=True)


# ---------------------------------------------------------------------------------- silent mode
def silent(argv: list[str]) -> int:
    dest = DEFAULT_DIR
    for a in argv:
        if a.upper().startswith("/D="):
            dest = Path(a[3:].strip('"'))
    if "--dir" in argv:
        dest = Path(argv[argv.index("--dir") + 1])
    payload = Path(argv[argv.index("--payload") + 1]) if "--payload" in argv else resource("payload.zip")
    try:
        install(dest, payload, start_menu="--no-shortcuts" not in argv, desktop="--desktop" in argv, autostart="--autostart" in argv)
    except Exception as e:
        print("install failed:", e)
        return 2
    if "--no-launch" not in argv:
        launch(dest)
    return 0


# ---------------------------------------------------------------------------------- GUI wizard
def wizard() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    BG, INK, SUB, ACC = "#F5F5F8", "#17171C", "#6B6B75", "#0A84C8"
    root = tk.Tk()
    root.title(f"{APP} Setup")
    root.geometry("600x460")
    root.resizable(False, False)
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TButton", padding=(18, 8), font=("Segoe UI", 10))
    style.configure("Accent.TButton", background=INK, foreground="white", font=("Segoe UI", 10, "bold"))
    style.map("Accent.TButton", background=[("active", "#33333b")])
    style.configure("TCheckbutton", background=BG, font=("Segoe UI", 10))
    style.configure("Horizontal.TProgressbar", troughcolor="#DADAE2", background=ACC, thickness=10)

    # header: the notch with its eyes
    hdr = tk.Canvas(root, width=600, height=96, bg="#0B0B0E", highlightthickness=0)
    hdr.pack(fill="x")
    hdr.create_rectangle(230, 0, 370, 46, fill="#000", outline="")
    hdr.create_oval(230, -40, 370, 46, fill="#000", outline="")
    for x in (278, 308):
        hdr.create_rectangle(x, 18, x + 14, 26, fill="#E4F7FF", outline="")
    hdr.create_text(300, 72, text=f"{APP} Setup", fill="white", font=("Segoe UI", 15, "bold"))
    body = tk.Frame(root, bg=BG)
    body.pack(fill="both", expand=True, padx=34, pady=(18, 0))
    foot = tk.Frame(root, bg=BG)
    foot.pack(fill="x", padx=34, pady=(0, 16))
    credit = tk.Label(foot, text=config.CREDIT, bg=BG, fg=ACC, font=("Segoe UI", 9, "bold"))
    credit.pack(side="left")
    nxt = ttk.Button(foot, text="Next", style="Accent.TButton")
    nxt.pack(side="right")
    back = ttk.Button(foot, text="Back")
    back.pack(side="right", padx=8)

    state = {"page": 0, "dir": tk.StringVar(value=str(DEFAULT_DIR)), "menu": tk.BooleanVar(value=True),
             "desk": tk.BooleanVar(value=False), "auto": tk.BooleanVar(value=False), "launch": tk.BooleanVar(value=True),
             "done": False, "error": None}
    q: queue.Queue = queue.Queue()

    def clear():
        for w in body.winfo_children():
            w.destroy()

    def title(t, sub=""):
        tk.Label(body, text=t, bg=BG, fg=INK, font=("Segoe UI", 15, "bold"), anchor="w").pack(fill="x")
        if sub:
            tk.Label(body, text=sub, bg=BG, fg=SUB, font=("Segoe UI", 10), anchor="w", justify="left", wraplength=530).pack(fill="x", pady=(2, 10))

    def page_welcome():
        title(f"Welcome to {APP}", "A local-first voice assistant that lives in your notch.")
        tk.Label(body, bg=BG, fg=INK, font=("Segoe UI", 10), justify="left", anchor="w", wraplength=530,
                 text=("This installs it for you only. No administrator rights are needed.\n\n"
                       "Everything runs on your PC. There is no account and no telemetry. Your voice, the wake word and the "
                       "assistant all work offline once installed (the speech model is downloaded the first time it is needed).\n\n"
                       "Click Next to continue.")).pack(fill="x")
        back.state(["disabled"]); nxt.configure(text="Next")

    def page_license():
        title("Licence", "Please read this before installing.")
        txt = tk.Text(body, height=12, wrap="word", font=("Segoe UI", 9), bg="white", relief="flat", highlightthickness=1,
                      highlightbackground="#D0D0D8")
        txt.insert("1.0", resource("LICENSE").read_text(encoding="utf-8"))
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)
        back.state(["!disabled"]); nxt.configure(text="I agree")

    def page_options():
        title("Where to install", "")
        row = tk.Frame(body, bg=BG); row.pack(fill="x")
        ttk.Entry(row, textvariable=state["dir"], font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True, ipady=4)
        ttk.Button(row, text="Browse...", command=lambda: state["dir"].set(
            filedialog.askdirectory(initialdir=str(DEFAULT_DIR.parent)) or state["dir"].get())).pack(side="left", padx=(8, 0))
        tk.Label(body, text="", bg=BG).pack()
        ttk.Checkbutton(body, text="Add a Start menu shortcut", variable=state["menu"]).pack(anchor="w", pady=2)
        ttk.Checkbutton(body, text="Add a Desktop shortcut", variable=state["desk"]).pack(anchor="w", pady=2)
        ttk.Checkbutton(body, text=f"Start {APP} with Windows", variable=state["auto"]).pack(anchor="w", pady=2)
        tk.Label(body, bg=BG, fg=SUB, font=("Segoe UI", 9), justify="left", anchor="w", wraplength=530,
                 text="About 600 MB of disk space. Later you can add the optional AI brain (about 1.1 GB) from the tray menu.").pack(fill="x", pady=(14, 0))
        back.state(["!disabled"]); nxt.configure(text="Install")

    def page_install():
        title(f"Installing {APP}", "Copying files. This takes a minute.")
        bar = ttk.Progressbar(body, mode="determinate", maximum=100); bar.pack(fill="x", pady=14)
        status = tk.Label(body, text="Preparing...", bg=BG, fg=SUB, font=("Segoe UI", 9), anchor="w"); status.pack(fill="x")
        back.state(["disabled"]); nxt.state(["disabled"])
        dest = Path(state["dir"].get())

        def work():
            try:
                install(dest, resource("payload.zip"), state["menu"].get(), state["desk"].get(), state["auto"].get(),
                        progress=lambda f, t: q.put(("p", f, t)))
                q.put(("ok",))
            except Exception as e:
                q.put(("err", str(e)))
        threading.Thread(target=work, daemon=True).start()

        def poll():
            try:
                while True:
                    m = q.get_nowait()
                    if m[0] == "p":
                        bar["value"] = 100 * m[1] / max(1, m[2]); status.configure(text=f"Copying files ({m[1]} of {m[2]})")
                    elif m[0] == "ok":
                        state["page"] = 4; show(); return
                    else:
                        messagebox.showerror(f"{APP} Setup", f"Setup could not finish:\n\n{m[1]}")
                        state["page"] = 2; show(); return
            except queue.Empty:
                pass
            root.after(80, poll)
        poll()

    def page_done():
        title(f"{APP} is installed", f"{config.CREDIT}.")
        tk.Label(body, bg=BG, fg=INK, font=("Segoe UI", 10), justify="left", anchor="w", wraplength=530,
                 text=(f"Hold Right Ctrl and talk, or say \"{config.WAKE_PHRASE}\". The first start shows a short tour.\n\n"
                       "To remove it later, use Settings > Apps > Installed apps.")).pack(fill="x")
        ttk.Checkbutton(body, text=f"Start {APP} now", variable=state["launch"]).pack(anchor="w", pady=14)
        back.pack_forget(); nxt.state(["!disabled"]); nxt.configure(text="Finish")

    pages = [page_welcome, page_license, page_options, page_install, page_done]

    def show():
        clear(); pages[state["page"]]()

    def go_next():
        p = state["page"]
        if p == 2:
            problem = check_destination(Path(state["dir"].get()))
            if problem:
                messagebox.showwarning(f"{APP} Setup", problem); return
        if p == 4:
            if state["launch"].get():
                launch(Path(state["dir"].get()))
            root.destroy(); return
        state["page"] = p + 1; show()

    def go_back():
        state["page"] = max(0, state["page"] - 1); show()

    nxt.configure(command=go_next); back.configure(command=go_back)
    show()
    root.mainloop()
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if any(a.upper() in ("/S", "--SILENT") for a in args):
        sys.exit(silent(args))
    sys.exit(wizard())
