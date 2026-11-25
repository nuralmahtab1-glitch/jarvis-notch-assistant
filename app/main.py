"""Jarvis entry point. Made by Nur Al Mahtab."""
from __future__ import annotations
import argparse, os, sys
from pathlib import Path
from PySide6.QtCore import QLockFile, QDir, QRect, QTimer, QUrl, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap, QRegion
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from shiboken6 import wrapInstance, getCppPointer
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from app import config
from app.ui.controller import MODES, SIZES, NotchController

from app import paths

QML = paths.qml("Notch.qml")


def tray_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#0B0B0E")); p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 18, 56, 28, 14, 14)
    p.setBrush(QColor("#FFFFFF"))
    p.setBrush(QColor('#E4F7FF'))
    p.drawRoundedRect(17, 29, 12, 7, 3.5, 3.5)
    p.drawRoundedRect(35, 29, 12, 7, 3.5, 3.5)
    p.end()
    return QIcon(pm)


def main() -> int:
    ap = argparse.ArgumentParser(prog=config.APP_NAME)
    ap.add_argument("--demo", action="store_true", help="cycle through every notch state")
    ap.add_argument("--state", help="start in a given state")
    ap.add_argument("--shots", help="write a PNG of every state into this folder, then quit")
    ap.add_argument("--say", help="pretend you said this (no microphone), then keep running")
    ap.add_argument("--onboarding", action="store_true", help="show the first-run tour now")
    ap.add_argument("--onboarding-shots", help="write a PNG of every onboarding step into this folder, then quit")
    ap.add_argument("--settings", action="store_true", help="open the Settings window at startup")
    ap.add_argument("--settings-shots", help="write a PNG of every Settings page into this folder, then quit")
    ap.add_argument("--no-voice", action="store_true", help="do not load speech models or speak")
    ap.add_argument("--no-keys", action="store_true", help="do not install the push-to-talk keyboard hook")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    lock = None
    if not args.shots and not args.onboarding_shots and not args.settings_shots:
        lock = QLockFile(QDir.temp().absoluteFilePath("jarvis-notch.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(100):
            return 0  # already running

    ctl = NotchController(demo_text=bool(args.demo or args.shots))
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("notch", ctl)
    from app.store.db import Settings
    from app.core.apps import PinnedApps, start_menu_index
    from app.ui.apps_ctl import AppsController
    import tempfile
    from app.ui.shelf_ctl import ShelfController
    preview = bool(args.shots or args.demo or args.onboarding_shots or args.settings_shots)
    settings = Settings(Path(tempfile.mkdtemp()) / "s.json") if preview else Settings()   # ONE shared settings object
    from app.store.db import Store
    from app.ui.widgets_ctl import WidgetsController
    from app.ui.prompter_ctl import MenuController, PrompterController
    from app.winio import system as _winsys
    store = Store(Path(tempfile.mkdtemp()) / "t.db") if preview else Store()                       # ONE shared store
    pins = PinnedApps(settings, start_menu_index(), launcher=(lambda t: None) if preview else None)
    widgets_ctl = WidgetsController(settings, store, battery=_winsys.battery)
    prompter_ctl = PrompterController(ctl, settings)
    menu_ctl = MenuController(ctl, settings, opener=(lambda u: None) if preview else None, prompter=prompter_ctl)
    if args.shots or args.demo:
        from app.core.prompter import Prompter as _P
        prompter_ctl.p = _P("Good evening everyone, and welcome. Tonight I want to talk about three simple ideas that changed how I work. First, keep it small. Second, keep it local. Third, always ask before you act.", 140)
        prompter_ctl.p.words_done = 14
    if args.shots or args.demo:                       # realistic sample data for screenshots, no network
        import time as _time
        from app.core import widgets as _W
        settings.set("weather_place", "London, GB")
        widgets_ctl._weather = _W.Weather(7, "Partly cloudy", "⛅", 9, 3, "C", "London, GB")
        widgets_ctl._fetched_at = _time.time()
    apps_ctl = AppsController(ctl, pins)
    from app.winio import system as winsys
    shelf_ctl = ShelfController(ctl, system=winsys, demo=bool(args.shots or args.demo))
    engine.rootContext().setContextProperty("shelf", shelf_ctl)
    engine.rootContext().setContextProperty("apps", apps_ctl)
    engine.rootContext().setContextProperty("widgets", widgets_ctl)
    engine.rootContext().setContextProperty("prompter", prompter_ctl)
    engine.rootContext().setContextProperty("menu", menu_ctl)
    engine.warnings.connect(lambda ws: [print("QML:", w.toString(), file=sys.stderr) for w in ws])
    engine.load(QUrl.fromLocalFile(str(QML)))
    if not engine.rootObjects():
        print("QML failed to load", file=sys.stderr)
        return 1
    win = engine.rootObjects()[0]
    qwin = wrapInstance(getCppPointer(win)[0], QQuickWindow)

    # --- click-through: only the notch rectangle receives mouse input ---
    state = {"w": 0, "h": 0}

    def apply_mask(extra: bool):
        w, h = SIZES.get(ctl.mode, (180, 36))
        ww = win.width()
        pad = 44 if extra else 6
        ow, oh = (max(w, state["w"]), max(h, state["h"])) if extra else (w, h)
        rect = QRect((ww - ow) // 2 - pad, 0, ow + pad * 2, oh + pad)
        win.setMask(QRegion(rect))
        state["w"], state["h"] = w, h

    shrink = QTimer(); shrink.setSingleShot(True); shrink.setInterval(450)
    shrink.timeout.connect(lambda: apply_mask(False))

    def on_change():
        w, h = SIZES.get(ctl.mode, (180, 36))
        if (w, h) != (state["w"], state["h"]):
            apply_mask(True)
            shrink.start()
    ctl.changed.connect(on_change)
    apply_mask(False)

    # --- while the teleprompter shows, ask Windows to keep the notch out of screen recordings and screen-sharing ---
    privacy = {"on": None}

    def sync_capture_privacy():
        want = ctl.mode == "prompter"
        if want != privacy["on"]:
            privacy["on"] = want
            try:
                import ctypes
                ctypes.windll.user32.SetWindowDisplayAffinity(int(win.winId()), 0x11 if want else 0)   # WDA_EXCLUDEFROMCAPTURE
            except Exception:
                pass
    ctl.changed.connect(sync_capture_privacy)

    # --- assistant (voice, tools, Claude Code bridge) ---
    assistant = None
    hooks: dict = {}
    if not args.shots and not args.demo and not args.onboarding_shots and not args.settings_shots:
        import threading
        from app.store.db import Settings, Store
        from app.core.assistant import Assistant
        from app.claude_bridge.tracker import Bridge, Tracker
        ctl._sleep_after = settings["sleep_after_minutes"] * 60 if not os.environ.get("JARVIS_SLEEP_SECONDS") else ctl._sleep_after
        speaker = stt = None
        if not args.no_voice:
            from app.tts.engine import Speaker
            from app.stt.whisper_stt import Transcriber
            speaker = Speaker(speed=settings["voice_speed"])
            def _warm_voice():                    # load the voice now so the first reply is not slow
                try:
                    for eng in speaker.engines:
                        if hasattr(eng, "synth_wav"):
                            eng.synth_wav("Ready.")
                except Exception as e:
                    print("[voice warm]", e)
            threading.Thread(target=_warm_voice, daemon=True).start()
            stt = Transcriber(settings["stt_model"])
            threading.Thread(target=stt.load, daemon=True).start()      # warm the model in the background
            first_download = not stt.cached()
        tracker = bridge = None
        if settings["claude_bridge"]:
            tracker = Tracker(approval_timeout=settings["claude_approval_timeout"],
                              hide_details=settings["claude_hide_details"],
                              quiet_when_focused=settings["claude_quiet_when_focused"])
            try:
                bridge = Bridge(tracker); bridge.start()
                app.aboutToQuit.connect(bridge.stop)
            except OSError as e:
                print("[bridge]", e)
        from app.audio.recorder import Recorder, device_index
        from app.llm.brain import Brain
        from app.llm.server import LocalBackend
        local = LocalBackend(lambda: settings["llm_model"])
        app.aboutToQuit.connect(local.stop)
        from app.llm.cloud import CloudBackend, RoutedBackend
        from app.winio import credstore
        cloud = CloudBackend(lambda: settings["llm_provider"], lambda: settings["cloud_model"], lambda: settings["cloud_base"],
                             lambda p: credstore.load(p))
        routed = RoutedBackend(local, cloud, lambda: settings["llm_provider"])
        brain = Brain(routed, ready=routed.installed, name=settings["address"])
        if settings["llm_provider"] == "local" and local.installed():
            threading.Thread(target=brain.warm, daemon=True).start()      # first question is then fast (not needed for the cloud)
        assistant = Assistant(ctl, settings, store, speaker, stt,
                              recorder_factory=(lambda lvl: Recorder(on_level=lvl, device=device_index(settings["mic_device"]))) if not args.no_voice else None,
                              tracker=tracker, brain=brain, local_backend=local)
        if not args.no_keys and not args.no_voice:
            from app.winio.hotkey import HoldKey
            pending = {}

            def make(kind):
                def down():
                    t = threading.Timer(0.25, lambda: assistant.begin_capture(kind, "key"))
                    pending[kind] = t; t.start()
                def up():
                    t = pending.pop(kind, None)
                    if t and t.is_alive():
                        t.cancel()              # a quick tap (e.g. Ctrl+C): ignore
                    else:
                        assistant.end_capture()
                return down, up
            keys = HoldKey({settings["ptt_command_key"]: make("command"), settings["ptt_dictate_key"]: make("dictate")})
            keys.start()
            app.aboutToQuit.connect(keys.stop)
        wake_ref = {"w": None}

        def set_wake(on: bool):
            """Start or stop the always-on wake word listener (also called live from Settings)."""
            if args.no_voice or args.no_keys:
                return
            if on and wake_ref["w"] is None:
                from app.wake.listener import WakeListener
                wake_ref["w"] = WakeListener(on_wake=lambda: assistant.begin_capture("command", "wake"),
                                             is_blocked=lambda: assistant.busy or bool(speaker and speaker.speaking),
                                             device=device_index(settings["mic_device"]))
                wake_ref["w"].start()
            elif not on and wake_ref["w"] is not None:
                wake_ref["w"].stop()
                wake_ref["w"] = None
        set_wake(bool(settings["wake_word"]))
        app.aboutToQuit.connect(lambda: set_wake(False))
        hooks["wake"] = set_wake
        from app.winio.media import MediaWatcher
        media = MediaWatcher(assistant.on_media, assistant.on_track_change, lyrics=bool(settings["lyrics"]))
        media.start()
        app.aboutToQuit.connect(media.stop)
        hooks["lyrics"] = lambda on: setattr(media, "use_lyrics", on)
        shelf_ctl.set_enabled(bool(settings["shelf_enabled"]))
        hooks["shelf"] = shelf_ctl.set_enabled
        hooks["shelf_clear"] = shelf_ctl.clear
        assistant.shelf = shelf_ctl
        assistant.apps = pins
        assistant.widgets = widgets_ctl
        assistant.prompter = prompter_ctl
        # --- Claude Code on the web: a local endpoint that only the paired browser extension can talk to ---
        web_ref = {"w": None}

        def set_web(on: bool):
            if tracker is None:
                return
            from app.claude_bridge.web import WebBridge, new_pair_code
            if on and web_ref["w"] is None:
                if not settings["web_pair_code"]:
                    settings.set("web_pair_code", new_pair_code())
                web_ref["w"] = WebBridge(tracker, lambda: settings["web_pair_code"])
                if not web_ref["w"].start():
                    print("[web] could not open a local port")
                    web_ref["w"] = None
            elif not on and web_ref["w"] is not None:
                web_ref["w"].stop()
                web_ref["w"] = None
        hooks["web"] = set_web
        set_web(bool(settings["claude_web"]))
        app.aboutToQuit.connect(lambda: set_web(False))
        hooks["weather_city"] = widgets_ctl.set_city
        hooks["units"] = widgets_ctl.units_changed
        if settings["onboarded"] and speaker and not args.say:
            QTimer.singleShot(3000, assistant.greet_if_due)      # once per day
        if not args.no_voice and first_download:
            QTimer.singleShot(4000, lambda: assistant.say("Getting my speech model ready. This takes a minute the first time.", src="button", hold=7))
        if args.say:
            QTimer.singleShot(800, lambda: assistant.handle_text(args.say, "key"))
        app.assistant = assistant      # keep alive

    # --- settings window ---
    def open_settings(a, ctl_, settings_, store_, shots: str | None = None):
        from app.ui.settings_ctl import SettingsController
        from app.claude_bridge import installer
        existing = getattr(app, "_settings", None)
        if existing and not shots:
            w = existing[2]
            w.show(); w.raise_(); w.requestActivate()
            return
        try:
            from app.audio.recorder import list_input_devices
            mics = [n for _, n in list_input_devices()]
        except Exception:
            mics = []
        sc = SettingsController(a, ctl_, settings_, store_, mics, hooks, installer)
        eng = QQmlApplicationEngine()
        eng.warnings.connect(lambda ws: [print("QML:", w.toString(), file=sys.stderr) for w in ws])
        eng.rootContext().setContextProperty("sc", sc)
        eng.load(QUrl.fromLocalFile(str(paths.qml("Settings.qml"))))
        if not eng.rootObjects():
            return
        w = eng.rootObjects()[0]
        app._settings = (eng, sc, w)
        if shots:
            qw = wrapInstance(getCppPointer(w)[0], QQuickWindow)
            out = Path(shots); out.mkdir(parents=True, exist_ok=True)
            i = {"n": 0}

            def snap():
                qw.grabWindow().save(str(out / f"settings_{i['n']}.png"))
                i["n"] += 1
                if i["n"] >= 7:
                    return app.quit()
                w.setProperty("page", i["n"]); QTimer.singleShot(700, snap)
            QTimer.singleShot(900, snap)

    if args.settings_shots:
        from app.store.db import Settings, Store
        from app.core.assistant import Assistant
        import tempfile
        d = Path(tempfile.mkdtemp())
        s_ = Settings(d / "s.json")
        a_ = Assistant(ctl, s_, Store(d / "t.db"))
        open_settings(a_, ctl, s_, a_.store, args.settings_shots)
    if assistant:
        ctl.action.connect(lambda name: open_settings(assistant, ctl, assistant.cfg, assistant.store) if name == "open_settings" else None)
    if args.settings_shots:
        pass
    elif assistant and args.settings:
        QTimer.singleShot(400, lambda: open_settings(assistant, ctl, assistant.cfg, assistant.store))

    # --- tray ---
    tray = QSystemTrayIcon(tray_icon(), app)
    tray.setToolTip(f"{config.APP_NAME} - {config.CREDIT}")
    menu = QMenu()

    def act(text, fn, checkable=False, checked=False):
        a = QAction(text, menu)
        a.setCheckable(checkable)
        if checkable:
            a.setChecked(checked)
            a.toggled.connect(fn)
        else:
            a.triggered.connect(lambda: fn())
        menu.addAction(a)
        return a

    def show_about():
        QMessageBox.information(None, f"About {config.APP_NAME}",
            f"{config.APP_NAME} {config.VERSION}"
            f"\n\n{config.CREDIT}"
            "\n\nA local-first voice assistant that lives in your notch."
            f"\nSay \"{config.WAKE_PHRASE}\", or hold Right Ctrl to talk and Right Alt to dictate.")

    if assistant:
        act("Settings...", lambda: open_settings(assistant, ctl, assistant.cfg, assistant.store))
    act(f"About {config.APP_NAME}", show_about)
    menu.addSeparator()
    if assistant:
        from app.claude_bridge import installer

        def connect_claude():
            path = installer.default_settings_path()
            try:
                diff = installer.preview(path)
            except Exception as e:
                QMessageBox.warning(None, "Connect Claude Code", f"I could not read {path}:\n{e}\n\nNothing was changed.")
                return
            box = QMessageBox(QMessageBox.Question, "Connect Claude Code",
                              "This adds hooks to your Claude Code settings so the notch can show what Claude is "
                              "doing and let you approve actions."
                              "\n\nYour existing settings are backed up first and "
                              "your own hooks are kept. You can disconnect any time.",
                              QMessageBox.Yes | QMessageBox.Cancel)
            box.setDetailedText(diff or "(no changes needed)")
            if box.exec() == QMessageBox.Yes:
                b = installer.connect(path)
                tray.showMessage(config.APP_NAME, "Claude Code connected." + (f" Backup: {b.name}" if b else ""))
                refresh_claude_items()

        def disconnect_claude():
            b = installer.disconnect()
            tray.showMessage(config.APP_NAME, "Claude Code disconnected." + (f" Backup: {b.name}" if b else ""))
            refresh_claude_items()

        from app.llm import manager as llm_manager

        def refresh_brain_items():
            have = llm_manager.is_installed(assistant.cfg["llm_model"]) and bool(llm_manager.server_binary())
            b_get.setVisible(not have)
            b_rm.setVisible(have)

        def get_brain():
            assistant.install_brain(assistant.cfg["llm_model"], on_done=lambda: assistant.ui(refresh_brain_items))

        def remove_brain():
            local.stop()
            llm_manager.remove(assistant.cfg["llm_model"])
            tray.showMessage(config.APP_NAME, "AI brain removed. Commands still work without it.")
            refresh_brain_items()

        b_get = act("Download AI brain (1.1 GB)", get_brain)
        b_rm = act("Remove AI brain", remove_brain)
        refresh_brain_items()
        c_on = act("Connect Claude Code...", connect_claude)
        c_off = act("Disconnect Claude Code", disconnect_claude)

        def refresh_claude_items():
            on = installer.is_connected()
            c_on.setVisible(not on)
            c_off.setVisible(on)
        refresh_claude_items()
        menu.addSeparator()
        awake_act = act("Keep awake (no sleep)", lambda on: assistant.set_keep_awake(on) if on != assistant.awake.active else None, True, False)
        assistant.on_awake_changed = lambda on: (awake_act.blockSignals(True), awake_act.setChecked(on), awake_act.blockSignals(False))
        app.aboutToQuit.connect(assistant.awake.off)
        act("Do not disturb", lambda on: (assistant.cfg.set("dnd", on), setattr(ctl, "dnd", on), ctl.setMode("sleeping") if on else ctl.wake()),
            True, bool(assistant.cfg["dnd"]))
        act("Speak replies", lambda on: assistant.cfg.set("speak_replies", "voice" if on else "off"),
            True, assistant.cfg["speak_replies"] != "off")
        from app.winio import autostart
        act("Start with Windows", lambda on: autostart.set_enabled(on), True, autostart.is_enabled())
        menu.addSeparator()
    demo = QAction("Cycle demo states", menu)
    demo.triggered.connect(ctl.startDemo)
    menu.addAction(demo)
    act("Sleep", lambda: ctl.setMode("sleeping"))
    menu.addSeparator()
    act("Quit", app.quit)
    tray.setContextMenu(menu)
    tray.show()

    # --- onboarding (first run, --onboarding, or --onboarding-shots DIR) ---
    def start_onboarding(settings, speaker, shots: str | None = None):
        from app.ui.onboarding import Onboarding
        from app.claude_bridge import installer
        try:
            from app.audio.recorder import list_input_devices
            mics = [n for _, n in list_input_devices()][:1] or ["Default microphone"]
        except Exception:
            mics = ["Default microphone"]
        ob = Onboarding(settings, speaker, installer, mics, brain=assistant)
        eng = QQmlApplicationEngine()
        eng.warnings.connect(lambda ws: [print("QML:", w.toString(), file=sys.stderr) for w in ws])
        eng.rootContext().setContextProperty("ob", ob)
        eng.load(QUrl.fromLocalFile(str(paths.qml("Onboarding.qml"))))
        if not eng.rootObjects():
            return
        w = eng.rootObjects()[0]
        qw = wrapInstance(getCppPointer(w)[0], QQuickWindow)
        app._onboarding = (eng, ob)

        def close():
            w.close(); eng.deleteLater()
            if ctl.mode == "sleeping":
                ctl.wake()
            if shots:
                app.quit()
        ob.finished.connect(close)
        if shots:
            out = Path(shots); out.mkdir(parents=True, exist_ok=True)
            i = {"n": 0}

            def snap():
                qw.grabWindow().save(str(out / f"onboarding_{i['n']:02d}.png"))
                i["n"] += 1
                if i["n"] >= 17:
                    return app.quit()
                w.setProperty("step", i["n"]); QTimer.singleShot(int(os.environ.get("JARVIS_SHOT_DELAY", "1100")), snap)
            QTimer.singleShot(900, snap)

    if args.onboarding_shots:
        from app.store.db import Settings
        import tempfile
        start_onboarding(Settings(Path(tempfile.mkdtemp()) / "s.json"), None, args.onboarding_shots)
    elif assistant and (args.onboarding or not assistant.cfg["onboarded"]):
        start_onboarding(assistant.cfg, assistant.speaker)

    if args.state:
        ctl.setMode(args.state)
    if args.demo:
        ctl.startDemo()

    if args.shots:
        out = Path(args.shots); out.mkdir(parents=True, exist_ok=True)
        modes = list(dict.fromkeys(MODES + ["peek"]))
        idx = {"i": 0}

        def snap():
            m = modes[idx["i"]]
            img = qwin.grabWindow()
            print(m, 'dpr', img.devicePixelRatio(), 'size', img.width(), img.height(), 'logical body', SIZES.get(m))
            img.save(str(out / f"{idx['i']:02d}_{m}.png"))
            idx["i"] += 1
            if idx["i"] >= len(modes):
                app.quit(); return
            ctl.setMode(modes[idx["i"]]); QTimer.singleShot(int(os.environ.get('JARVIS_SHOT_DELAY','900')), snap)
        ctl.setMode(modes[0]); QTimer.singleShot(1200, snap)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
