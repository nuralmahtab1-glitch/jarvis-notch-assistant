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

QML = Path(__file__).parent / "ui" / "qml" / "Notch.qml"


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
    ap.add_argument("--no-voice", action="store_true", help="do not load speech models or speak")
    ap.add_argument("--no-keys", action="store_true", help="do not install the push-to-talk keyboard hook")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    lock = None
    if not args.shots and not args.onboarding_shots:
        lock = QLockFile(QDir.temp().absoluteFilePath("jarvis-notch.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(100):
            return 0  # already running

    ctl = NotchController(demo_text=bool(args.demo or args.shots))
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("notch", ctl)
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

    # --- assistant (voice, tools, Claude Code bridge) ---
    assistant = None
    if not args.shots and not args.demo and not args.onboarding_shots:
        import threading
        from app.store.db import Settings, Store
        from app.core.assistant import Assistant
        from app.claude_bridge.tracker import Bridge, Tracker
        settings, store = Settings(), Store()
        ctl._sleep_after = settings["sleep_after_minutes"] * 60 if not os.environ.get("JARVIS_SLEEP_SECONDS") else ctl._sleep_after
        speaker = stt = None
        if not args.no_voice:
            from app.tts.engine import Speaker
            from app.stt.whisper_stt import Transcriber
            speaker = Speaker(speed=settings["voice_speed"])
            stt = Transcriber(settings["stt_model"])
            threading.Thread(target=stt.load, daemon=True).start()      # warm the model in the background
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
        from app.audio.recorder import Recorder
        from app.llm.brain import Brain
        from app.llm.server import LocalBackend
        local = LocalBackend(lambda: settings["llm_model"])
        app.aboutToQuit.connect(local.stop)
        brain = Brain(local, ready=local.installed, name=settings["address"])
        if local.installed():
            threading.Thread(target=brain.warm, daemon=True).start()      # first question is then fast
        assistant = Assistant(ctl, settings, store, speaker, stt,
                              recorder_factory=(lambda lvl: Recorder(on_level=lvl)) if not args.no_voice else None,
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
        if settings["wake_word"] and not args.no_voice and not args.no_keys:
            from app.wake.listener import WakeListener
            wake = WakeListener(on_wake=lambda: assistant.begin_capture("command", "wake"),
                                is_blocked=lambda: assistant.busy or bool(speaker and speaker.speaking))
            wake.start()
            app.aboutToQuit.connect(wake.stop)
        from app.winio.media import MediaWatcher
        media = MediaWatcher(assistant.on_media, assistant.on_track_change, lyrics=bool(settings["lyrics"]))
        media.start()
        app.aboutToQuit.connect(media.stop)
        if args.say:
            QTimer.singleShot(800, lambda: assistant.handle_text(args.say, "key"))
        app.assistant = assistant      # keep alive

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
        eng.load(QUrl.fromLocalFile(str(Path(__file__).parent / "ui" / "qml" / "Onboarding.qml")))
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
