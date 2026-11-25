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
    p.drawRoundedRect(20, 25, 7, 14, 3.5, 3.5)
    p.drawRoundedRect(37, 25, 7, 14, 3.5, 3.5)
    p.end()
    return QIcon(pm)


def main() -> int:
    ap = argparse.ArgumentParser(prog=config.APP_NAME)
    ap.add_argument("--demo", action="store_true", help="cycle through every notch state")
    ap.add_argument("--state", help="start in a given state")
    ap.add_argument("--shots", help="write a PNG of every state into this folder, then quit")
    ap.add_argument("--say", help="pretend you said this (no microphone), then keep running")
    ap.add_argument("--no-voice", action="store_true", help="do not load speech models or speak")
    ap.add_argument("--no-keys", action="store_true", help="do not install the push-to-talk keyboard hook")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    lock = None
    if not args.shots:
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
    if not args.shots and not args.demo:
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
        assistant = Assistant(ctl, settings, store, speaker, stt,
                              recorder_factory=(lambda lvl: Recorder(on_level=lvl)) if not args.no_voice else None,
                              tracker=tracker)
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
        if args.say:
            QTimer.singleShot(800, lambda: assistant.handle_text(args.say, "key"))
        app.assistant = assistant      # keep alive

    # --- tray ---
    tray = QSystemTrayIcon(tray_icon(), app)
    tray.setToolTip(f"{config.APP_NAME} - {config.CREDIT}")
    menu = QMenu()
    about = QAction(f"About {config.APP_NAME}", menu)
    about.triggered.connect(lambda: QMessageBox.information(
        None, f"About {config.APP_NAME}",
        f"{config.APP_NAME} {config.VERSION}\n\n{config.CREDIT}\n\nA local-first voice assistant that lives in your notch."))
    demo = QAction("Cycle demo states", menu)
    demo.triggered.connect(ctl.startDemo)
    stop = QAction("Stop demo", menu)
    stop.triggered.connect(ctl.stopDemo)
    sleep = QAction("Sleep", menu)
    sleep.triggered.connect(lambda: ctl.setMode("sleeping"))
    quit_ = QAction("Quit", menu)
    quit_.triggered.connect(app.quit)
    for a in (about, demo, stop, sleep):
        menu.addAction(a)
    menu.addSeparator()
    menu.addAction(quit_)
    tray.setContextMenu(menu)
    tray.show()

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
