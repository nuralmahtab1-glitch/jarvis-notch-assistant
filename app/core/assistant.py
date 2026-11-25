"""Assistant: wires voice, tools, dictation, reminders, focus and Claude Code status to the notch.
Made by Nur Al Mahtab."""
from __future__ import annotations
import re, threading, time
from datetime import datetime
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from app import config
from app.core.persona import Persona
from app.store.db import Settings, Store
from app.tools import dictation
from app.tools.intents import CAPABILITIES, Intent, parse
from app.ui.controller import NotchController
from app.winio import system as win
from app.winio import controls as qs
from app.claude_bridge.tracker import TERMINAL_PROCS, Tracker, fmt_duration


class Assistant(QObject):
    _ui = Signal(object)

    def __init__(self, ctl: NotchController, settings: Settings, store: Store,
                 speaker=None, transcriber=None, recorder_factory=None, tracker: Tracker | None = None,
                 brain=None, local_backend=None):
        super().__init__()
        self.ctl, self.cfg, self.store = ctl, settings, store
        self.speaker, self.stt = speaker, transcriber
        self._recorder_factory = recorder_factory
        self.rec = None
        self.persona = Persona(settings["persona"], settings["address"])
        self.tracker = tracker
        self.brain, self.local = brain, local_backend
        self.brain_dl = {"id": None, "pct": 0, "state": ""}     # download status for the UI
        self.busy = False                 # a user interaction owns the notch
        self._capture_kind = None
        self._capture_src = "key"
        self._target_hwnd = 0
        self._partial_stop = threading.Event()
        self._pending_confirm: Callable | None = None
        self._focus_end = 0.0
        self._focus_total = 0
        self._focus_label = "Focus"
        self._claude_seen: dict[str, str] = {}
        self.apps = None                   # set by main: the pinned apps (voice 'open <app>')
        self.shelf = None                  # set by main: the Shelf controller
        self.qs = qs                       # quick-settings backend (swappable in tests)
        self._ctl_tick = 0
        self._brightness_lock = threading.Lock()
        self._level_t = 0.0
        self._ui.connect(lambda fn: fn())
        ctl.action.connect(self.on_action)
        ctl.controlChanged.connect(self.on_control)
        ctl.todoToggled.connect(lambda tid: (self.store.todo_toggle(tid), self.refresh_todo()))
        if speaker:
            speaker._on_state = lambda on: self.ui(lambda: self._speaking_changed(on))
            speaker._on_level = lambda v: self.ui(lambda: self.ctl.setLevel(v if self.ctl.mode == "speaking" else -1))
        self._tick = QTimer(self); self._tick.setInterval(1000); self._tick.timeout.connect(self._every_second)
        self._tick.start()
        if tracker:
            tracker.on_update = lambda: self.ui(self.sync_claude)
            tracker.foreground_proc = lambda: win.window_process_name(win.foreground_window())
        self.refresh_todo()

    # ------------------------------------------------------------------ plumbing
    def ui(self, fn: Callable):
        self._ui.emit(fn)

    @property
    def speak_mode(self) -> str:
        return self.cfg["speak_replies"]

    def should_speak(self, src: str) -> bool:
        m = self.speak_mode
        return m == "always" or (m == "voice" and src in ("key", "wake"))

    CARD_MODES = ("todo", "volume", "focus", "music", "controls", "shelf", "apps")

    def say(self, text: str, src: str = "key", mode: str = "done", hold: float = 2.6):
        """Show the reply in the notch and speak it if the interaction was by voice.
        If a card (list, volume, focus...) is already showing, keep it and only speak."""
        self.ctl.keepAwake(hold + 6)
        speak = bool(text) and self.should_speak(src) and self.speaker and not self.cfg["dnd"]
        card = self.ctl.mode in self.CARD_MODES
        if not card:
            self.ctl.setMode("speaking" if speak else mode)
            self.ctl.setText(text[:70] if text else "Done", "")
        if speak:
            self.speaker.speak(text)
        elif not card:
            QTimer.singleShot(int(hold * 1000), self._back_to_idle)

    def _speaking_changed(self, on: bool):
        if on:
            self.ctl.keepAwake(30)
        else:
            self.ctl.setLevel(-1)
            QTimer.singleShot(500, self._back_to_idle)

    def _back_to_idle(self):
        if self.ctl.mode in ("done", "speaking", "working", "hearing", "listening", "recording", "todo", "volume") \
                and not (self.speaker and self.speaker.speaking) and not self.busy:
            self.ctl.setMode("idle")
        self.sync_claude()

    def show_card(self, mode: str, title: str = "", sub: str = "", seconds: float = 7.0):
        self.ctl.keepAwake(seconds + 3)
        self.ctl.setMode(mode)
        if title:
            self.ctl.setText(title, sub)
        def expire():
            if self.ctl.mode == mode and not self.busy:
                self.ctl.setMode("idle")
                self.sync_claude()
        QTimer.singleShot(int(seconds * 1000), expire)

    # ------------------------------------------------------------------ capture (hold-to-talk / wake / button)
    def begin_capture(self, kind: str, src: str = "key"):
        """kind: 'command' or 'dictate'. Safe to call from any thread."""
        self.ui(lambda: self._begin(kind, src))

    def end_capture(self):
        self.ui(self._end)

    def _begin(self, kind: str, src: str):
        if self.busy or not self._recorder_factory:
            return
        if self.speaker:
            self.speaker.stop()                      # barge-in
        self.ctl.wake()
        self.busy = True
        self._capture_kind, self._capture_src = kind, src
        self._target_hwnd = win.foreground_window()
        self.ctl.setMode("recording" if kind == "dictate" else "listening")
        self.ctl.setText("Listening", "")
        self.ctl.keepAwake(60)

        def level(v):
            now = time.monotonic()
            if now - self._level_t > 0.05:
                self._level_t = now
                self.ui(lambda: self.ctl.setLevel(v))
        self.rec = self._recorder_factory(level)
        try:
            self.rec.start()
        except Exception as e:
            self.busy = False
            self.say(f"I cannot reach the microphone.", src="button")
            print("[mic]", e)
            return
        self._partial_stop.clear()
        threading.Thread(target=self._partials, daemon=True).start()
        self._endpointer = None
        if src == "wake":                       # no key to release: detect the end of speech ourselves
            from app.wake.listener import Endpointer
            self._endpointer = Endpointer(self.rec.snapshot,
                                          lambda spoke: self.ui(self._end if spoke else self.cancel_capture))
            self._endpointer.start()

    def _partials(self):
        last = ""
        while not self._partial_stop.wait(1.4):
            if not self.rec or not self.stt or not self.stt.loaded:
                continue
            audio = self.rec.snapshot()
            if audio.size < 16000 * 1.0:
                continue
            try:
                txt = self.stt.transcribe(audio[-16000 * 12:])
            except Exception:
                continue
            if txt and txt != last and not self._partial_stop.is_set():
                last = txt
                tail = txt if len(txt) <= 46 else "..." + txt[-44:]
                self.ui(lambda t=tail: (self.ctl.setMode("hearing"), self.ctl.setText(t, "")) if self.busy else None)

    def cancel_capture(self):
        """Stop recording and throw the audio away (nobody spoke)."""
        if getattr(self, "_endpointer", None):
            self._endpointer.cancel()
        self._partial_stop.set()
        if self.rec:
            self.rec.stop(); self.rec = None
        self.busy = False
        self.ctl.setLevel(-1)
        self.ctl.setMode("idle")

    def _end(self):
        if not self.busy or not self.rec:
            return
        if getattr(self, "_endpointer", None):
            self._endpointer.cancel()
        self._partial_stop.set()
        audio = self.rec.stop()
        self.rec = None
        kind, src, hwnd = self._capture_kind, self._capture_src, self._target_hwnd
        self.ctl.setLevel(-1)
        self.ctl.setMode("working")
        self.ctl.setText("Writing it down" if kind == "dictate" else "Working on it", "")
        threading.Thread(target=self._process, args=(audio, kind, src, hwnd), daemon=True).start()

    def _process(self, audio, kind, src, hwnd):
        try:
            text = self.stt.transcribe(audio) if self.stt else ""
        except Exception as e:
            print("[stt]", e)
            text = ""
        self.ui(lambda: self._finish(text, kind, src, hwnd))

    def _finish(self, text: str, kind: str, src: str, hwnd: int):
        self.busy = False
        if not text.strip():
            if src == "wake":
                self.say(self.persona.say("unknown"), src)
            else:
                self.ctl.setMode("idle")      # an accidental tap of the key: stay quiet
            return
        if kind == "dictate":
            self.insert_dictation(text, hwnd)
        else:
            self.handle_text(text, src)

    # ------------------------------------------------------------------ dictation
    def insert_dictation(self, raw: str, hwnd: int | None = None):
        cleaned = dictation.clean(raw)
        if not cleaned:
            self.ctl.setMode("idle")
            return
        self.insert_text(cleaned, hwnd)        # fails closed: never types into a different window

    # ------------------------------------------------------------------ commands
    def handle_text(self, text: str, src: str = "key"):
        """Entry point for a spoken/typed command. Also used by --say for testing."""
        if self._pending_confirm:
            t = text.lower()
            if any(w in t for w in ("yes", "confirm", "go ahead", "do it", "sure")):
                self.on_action("confirm"); return
            if any(w in t for w in ("no", "cancel", "not now", "don't", "stop")):
                self.on_action("cancel"); return
        intent = parse(text)
        if not intent:
            self.ask_brain(text, src)
            return
        reply = self.run_intent(intent, src)
        if reply is not None:
            self.say(reply, src)

    def run_intent(self, it: Intent, src: str = "key") -> str | None:
        p, n, a = self.persona, self.persona.name, it.args
        try:
            if it.name == "write_text":
                return self.write_with_brain(a["instruction"], src)
            if it.name == "go_to_sleep":
                self.say(p.say("sleep"), src)
                QTimer.singleShot(2800, lambda: self.ctl.setMode("sleeping"))
                return None
            if it.name == "cancel":
                if self.speaker: self.speaker.stop()
                self.ctl.setMode("idle"); return None
            if it.name == "what_can_you_do": return CAPABILITIES
            if it.name == "time": return "It is " + datetime.now().strftime("%I:%M %p").lstrip("0") + "."
            if it.name == "date": return "It is " + datetime.now().strftime("%A, %d %B").replace(" 0", " ") + "."
            if it.name == "todo_add":
                self.store.todo_add(a["text"]); self.refresh_todo(); self.show_card("todo")
                return f"Added {a['text']} to your list."
            if it.name == "todo_list":
                items = [t for t in self.store.todo_list() if not t["done"]]
                self.refresh_todo(); self.show_card("todo", seconds=9)
                if not items: return "Your list is empty."
                return f"You have {len(items)} things: " + ", ".join(t["text"] for t in items[:4]) + "."
            if it.name == "todo_complete":
                m = self.store.todo_complete_match(a["text"]); self.refresh_todo(); self.show_card("todo")
                return f"Marked {m} as done." if m else f"I could not find {a['text']} on your list."
            if it.name == "todo_remove":
                m = self.store.todo_remove_match(a["text"]); self.refresh_todo()
                return f"Removed {m}." if m else f"I could not find {a['text']}."
            if it.name == "set_reminder":
                when = a.get("when")
                if not when: return "When should I remind you?"
                self.store.reminder_add(a["text"] or "Reminder", when.timestamp())
                return f"I will remind you {'at ' + when.strftime('%I:%M %p').lstrip('0') if (when - datetime.now()).total_seconds() > 3600 else 'in ' + fmt_duration((when - datetime.now()).total_seconds())}."
            if it.name == "focus_start":
                self.start_focus(a["minutes"]); return f"Focus session started. {a['minutes']} minutes."
            if it.name in ("focus_stop",):
                self.stop_focus(); return "Focus session stopped."
            if it.name == "focus_break":
                self.start_focus(5, label="Break"); return "Enjoy your break. Five minutes."
            if it.name == "volume_set":
                v = win.set_volume(a["level"]); self.show_card("volume", "Volume", seconds=2.5); return f"Volume {v}."
            if it.name == "volume_change":
                v = win.change_volume(a["delta"]); self.show_card("volume", "Volume", seconds=2.5); return f"Volume {v}."
            if it.name == "mute_toggle":
                return "Muted." if win.toggle_mute() else "Unmuted."
            if it.name == "brightness_set":
                win.set_brightness(a["level"]); return f"Brightness {a['level']}."
            if it.name == "brightness_change":
                cur = win.get_brightness();
                if cur is None: return "I cannot change the brightness on this display."
                win.set_brightness(cur + a["delta"]); return "Done."
            if it.name == "media_play_pause": win.media_play_pause(); return ""
            if it.name == "media_next": win.media_next(); return ""
            if it.name == "media_prev": win.media_prev(); return ""
            if it.name == "play_music":
                win.play_spotify(a["query"]); return f"Searching Spotify for {a['query']}."
            if it.name == "screenshot":
                path = win.screenshot(); return "Screenshot saved to your Pictures folder."
            if it.name == "open_app":
                key = a["name"].lower().strip()
                if self.apps and key not in win.APP_ALIASES:      # well-known names (notepad, terminal...) keep their exact mapping
                    hit = self.apps.launch_by_name(a["name"])
                    if hit:
                        return f"Opening {hit}."
                return f"Opening {a['name']}." if win.open_app(a["name"]) else f"I could not open {a['name']}."
            if it.name == "apps_open":
                self.ctl.wake(); self.ctl.setMode("apps"); return ""
            if it.name == "open_website":
                win.open_url(a["url"]); return "Opening it now."
            if it.name == "search_web":
                win.search_web(a["query"]); return f"Searching for {a['query']}."
            if it.name == "battery":
                pct, plugged = win.battery()
                return "No battery detected." if pct is None else f"Battery is at {pct} percent{', charging' if plugged else ''}."
            if it.name in ("wifi_toggle", "bluetooth_toggle", "airplane_toggle"):
                return self.voice_quick(it.name[:-7], a.get("on"), src)
            if it.name == "power_mode_set":
                ok = self.qs.set_power_mode(a["mode"]); self.refresh_controls()
                return f"Power mode set to {a['mode']}." if ok else "Windows would not change the power mode."
            if it.name == "night_light_toggle":
                self.qs.open_settings_page("nightlight")
                return "Windows does not let apps switch night light, so I opened its settings."
            if it.name == "shelf_open":
                self.ctl.wake()
                if self.shelf:
                    self.shelf.opened()
                self.ctl.setMode("shelf"); return ""
            if it.name == "controls_open":
                self.open_controls(); return ""
            if it.name == "claude_status":
                return self.tracker.status_sentence() if self.tracker else "Claude is not connected."
            if it.name == "claude_done_query":
                s = self.tracker.urgent() if self.tracker else None
                return "Claude is still working." if s and s.state == "working" else self.tracker.status_sentence() if self.tracker else "Claude is not connected."
            if it.name == "claude_sessions":
                ss = list(self.tracker.sessions.values()) if self.tracker else []
                return "No Claude sessions are running." if not ss else "; ".join(f"{s.project} is {s.state.replace('_', ' ')}" for s in ss) + "."
            if it.name in ("claude_approve", "claude_deny"):
                if not self.tracker or not self.tracker.pending:
                    return "Nothing is waiting for approval."
                ok = self.tracker.resolve("allow" if it.name == "claude_approve" else "deny", via_voice=True)
                return ("Approved." if it.name == "claude_approve" else "Denied.") if ok else \
                    "That one is flagged as risky. Please tap Approve."
        except Exception as e:
            print(f"[intent {it.name}]", e)
            return p.say("error")
        return None

    # ------------------------------------------------------------------ todo / focus / reminders
    def refresh_todo(self):
        self.ctl.setTodo(self.store.todo_list())

    def start_focus(self, minutes: int, label: str = "Focus"):
        self._focus_total = minutes * 60
        self._focus_end = time.time() + self._focus_total
        self._focus_label = label
        self.ctl.setFocus(self._focus_total, self._focus_total)
        self.ctl.setMode("focus")
        self.ctl.keepAwake(5)

    def stop_focus(self):
        self._focus_end = 0
        if self.ctl.mode == "focus":
            self.ctl.setMode("idle")

    def _every_second(self):
        now = time.time()
        if self.local:
            self.local.idle_stop(600)
        if self._focus_end:
            left = int(self._focus_end - now)
            self.ctl.setFocus(max(0, left), self._focus_total)
            if self.ctl.mode == "focus":
                self.ctl.keepAwake(5)
            if left <= 0:
                self._focus_end = 0
                if not self.cfg["dnd"]:
                    win.chime()
                done_msg = "Break over. Back to it." if self._focus_label == "Break" else \
                    "Focus session complete. " + self.persona.say("break_hint")
                self.say(done_msg.strip(), src="voice-timer" if False else "key", hold=4)
        # Do not disturb holds reminders (they stay pending and fire when it ends); nothing is lost.
        for r in ([] if self.cfg["dnd"] else self.store.reminders_due()):
            win.chime()
            self.ctl.wake()
            self.show_card("reminder", "Reminder", r["text"], seconds=25)
            if self.speaker and self.speak_mode != "off":
                self.speaker.speak(f"Reminder: {r['text']}.")
            self._last_reminder = r
        if self.ctl.mode == "controls":
            self.ctl.keepAwake(5)
            self._ctl_tick += 1
            if self._ctl_tick % 3 == 0:
                self.refresh_controls()
        if self.tracker and self.ctl.mode == "claudeWorking":
            self.sync_claude()

    # ------------------------------------------------------------------ UI actions
    @Slot(str)
    def on_action(self, name: str):
        if name == "approve" and self.tracker: self.tracker.resolve("allow")
        elif name == "deny" and self.tracker: self.tracker.resolve("deny")
        elif name == "confirm":
            cb, self._pending_confirm = self._pending_confirm, None
            self.ctl.setMode("idle"); cb and cb()
        elif name == "cancel":
            self._pending_confirm = None; self.ctl.setMode("idle")
        elif name == "dismiss":
            if self.ctl.mode == "claudeDone" and self.tracker:
                for s in self.tracker.sessions.values():
                    if s.state == "done": s.state = "idle"
            self.ctl.setMode("idle"); self.sync_claude()
        elif name == "snooze":
            r = getattr(self, "_last_reminder", None)
            if r: self.store.reminder_add(r["text"], time.time() + 600)
            self.ctl.setMode("idle")
        elif name == "open_controls": self.open_controls()
        elif name in ("ctl_wifi", "ctl_bluetooth", "ctl_airplane"): self.toggle_quick(name[4:])
        elif name.startswith("ctl_page_"): self.qs.open_settings_page(name[9:])
        elif name == "ctl_mute": self.on_control("mute", 0)
        elif name == "ctl_screenshot": self.take_screenshot_from_panel()
        elif name == "focus_stop": self.stop_focus()
        elif name == "focus_break": self.start_focus(5, label="Break")
        elif name == "media_play": win.media_play_pause()
        elif name == "media_next": win.media_next()
        elif name == "media_prev": win.media_prev()
        elif name == "btn_dictate": self.toggle_button_capture("dictate")
        elif name == "btn_command": self.toggle_button_capture("command")
        elif name == "btn_write": self.toggle_button_capture("command")

    def toggle_button_capture(self, kind: str):
        if self.busy:
            self.end_capture()
        else:
            self.ctl.setMode("idle")
            QTimer.singleShot(250, lambda: self.begin_capture(kind, "button"))

    def confirm(self, prompt: str, on_yes: Callable, src: str = "key"):
        self._pending_confirm = on_yes
        self.ctl.setMode("confirm"); self.ctl.setText(prompt, "Say yes or no, or tap.")
        self.ctl.keepAwake(30)
        if self.speaker and self.should_speak(src):
            self.speaker.speak(prompt)

    # ------------------------------------------------------------------ Claude Code
    def sync_claude(self):
        """Reflect the most urgent Claude Code session in the notch, unless the user owns it right now."""
        if not self.tracker or self.busy:
            return
        urgent = self.tracker.urgent()
        needs = bool(urgent and urgent.state == "needs_you")     # needs-you outranks everything but live capture
        if not needs:
            if self.speaker and self.speaker.speaking:
                return
            if self.ctl.mode in ("listening", "recording", "hearing", "working", "confirm", "reminder",
                                 "focus", "music", "todo", "expanded", "speaking"):
                return
        s = self.tracker.urgent()
        if not s:
            if self.ctl.mode.startswith("claude"): self.ctl.setMode("idle")
            return
        quiet = win.window_process_name(win.foreground_window()) in TERMINAL_PROCS
        prev = self._claude_seen.get(s.id)
        if s.state == "needs_you":
            ap = next(iter(self.tracker.pending.values()), None)
            self.ctl.wake(); self.ctl.keepAwake(40); win.chime() if prev != "needs_you" else None
            self.ctl.setMode("claudeNeeds")
            self.ctl.setText("Claude needs your permission" + (" (risky)" if ap and ap.risky else ""),
                             (ap.description if ap else s.last_action)[:60])
            if prev != "needs_you" and self.cfg["claude_speak"].get("needs_you") and not quiet and self.speaker and not self.cfg["dnd"]:
                self.speaker.speak(self.persona.say("claude_needs"))
        elif s.state == "working":
            el = fmt_duration(time.time() - s.started) if s.started else ""
            self.ctl.keepAwake(5)
            if self.ctl.mode != "claudeWorking": self.ctl.wake(); self.ctl.setMode("claudeWorking")
            act = s.last_action or "working"
            self.ctl.setText(f"Claude is {act[:1].lower() + act[1:]}"[:46], el)
        elif s.state == "done":
            self.ctl.wake(); self.ctl.keepAwake(12)
            self.ctl.setMode("claudeDone")
            self.ctl.setText(f"Claude finished in {fmt_duration(s.duration)}", s.summary[:90])
            if prev != "done":
                win.chime()
                if self.cfg["claude_speak"].get("done") and not quiet and self.speaker and not self.cfg["dnd"]:
                    self.speaker.speak(self.persona.say("claude_done"))
                QTimer.singleShot(9000, lambda: self.ctl.mode == "claudeDone" and self.on_action("dismiss"))
        elif s.state == "error":
            self.ctl.wake(); self.ctl.keepAwake(8)
            self.ctl.setMode("claudeError"); self.ctl.setText("Claude hit an error", s.last_action[:60])
            if prev != "error" and self.cfg["claude_speak"].get("error") and not quiet and self.speaker and not self.cfg["dnd"]:
                self.speaker.speak(self.persona.say("claude_error"))
            QTimer.singleShot(8000, lambda: self.ctl.mode == "claudeError" and self.ctl.setMode("idle"))
        self._claude_seen[s.id] = s.state

    # ------------------------------------------------------------------ music
    def on_media(self, st: dict):
        """Called from the media thread once a second."""
        def apply():
            if st["title"]:
                frac = (st["pos"] / st["dur"]) if st["dur"] else 0.0
                self.ctl.setMusic({"title": st["title"], "artist": st["artist"], "frac": max(0.0, min(1.0, frac)),
                                   "lyrics": st.get("lyrics", ["", "", ""])})
            else:
                self.ctl.setMusic({"title": "Nothing playing", "artist": "", "frac": 0.0, "lyrics": ["", "", ""]})
        self.ui(apply)

    def on_track_change(self, st: dict):
        """A new song started: peek the music card for a few seconds (unless you are busy)."""
        def peek():
            if not self.busy and self.ctl.mode in ("idle", "peek", "sleeping") and not self.cfg["dnd"]:
                self.ctl.wake()
                self.show_card("music", seconds=6)
        self.ui(peek)

    # ------------------------------------------------------------------ settings helpers
    def set_dnd(self, on: bool):
        """Do not disturb: the notch sleeps and stays quiet (only 'needs you' still shows, silently)."""
        self.ctl.dnd = on
        if on:
            if self.speaker:
                self.speaker.stop()
            self.ctl.setMode("sleeping")
        else:
            self.ctl.wake()

    def greet_if_due(self):
        """Say a short greeting the first time Jarvis starts each day (if enabled and not in DND)."""
        today = time.strftime("%Y-%m-%d")
        if not self.cfg["greeting"] or self.cfg["dnd"] or self.cfg["last_greeting"] == today:
            return
        self.cfg.set("last_greeting", today)
        text = self.persona.greeting(datetime.now().hour)
        if text:
            self.ctl.wake()
            self.say(text, src="key", hold=4)

    # ------------------------------------------------------------------ AI brain
    def brain_available(self) -> bool:
        return bool(self.brain and self.brain.ready())

    def _need_brain(self, src: str):
        self.say(f"I have not got my brain installed yet, {self.persona.name}. "
                 "Choose Download AI brain from the tray menu.", src, hold=6)

    def ask_brain(self, text: str, src: str = "key"):
        """The rules parser did not understand: let the model decide (tool call or short answer)."""
        if not self.brain or not self.brain.backend:
            self.say(self.persona.say("unknown"), src)
            return
        if not self.brain.ready():
            self._need_brain(src)
            return
        self.ctl.keepAwake(40)
        self.ctl.setMode("working")
        self.ctl.setText("Thinking", "")

        def work():
            d = self.brain.route(text)
            self.ui(lambda: self._brain_result(d, src))
        threading.Thread(target=work, daemon=True).start()

    def _brain_result(self, d, src: str):
        if d.intent:
            reply = self.run_intent(d.intent, src)
            if reply is not None:
                self.say(reply, src)
            elif self.ctl.mode == "working":
                self.ctl.setMode("idle")
        elif d.answer:
            self.show_answer(d.answer, src)
        else:
            print("[brain]", d.error)
            self.say(self.persona.say("unknown"), src)

    def show_answer(self, text: str, src: str = "key"):
        """A short answer: shown on a card (so you can read it) and spoken if the request was by voice."""
        m = re.match(r"(.+?[.!?])\s+(.*)", text, flags=re.S)
        title, sub = (m.group(1), m.group(2)) if m else (text, "")
        self.ctl.keepAwake(20)
        self.ctl.setMode("answer")
        self.ctl.setText(title[:90], sub[:120])
        if self.should_speak(src) and self.speaker and not self.cfg["dnd"]:
            self.speaker.speak(text)
        QTimer.singleShot(int(max(8, len(text) / 12) * 1000),
                          lambda: self.ctl.mode == "answer" and self.ctl.setMode("idle"))

    def write_with_brain(self, instruction: str, src: str) -> str | None:
        if not self.brain_available():
            self._need_brain(src)
            return None
        hwnd = self._target_hwnd or win.foreground_window()
        self.ctl.keepAwake(60)
        self.ctl.setMode("working")
        self.ctl.setText("Writing it for you", "")

        def work():
            text = self.brain.write(instruction)
            self.ui(lambda: self._type_draft(text, hwnd, src))
        threading.Thread(target=work, daemon=True).start()
        return None

    def _type_draft(self, text: str | None, hwnd: int, src: str):
        if not text:
            self.say("I could not write that just now.", src)
            return
        self.insert_text(text, hwnd)

    def install_brain(self, model_id: str, on_done=None):
        """Download llama.cpp + the model in the background, with progress shown in the notch."""
        from app.llm import manager
        if self.brain_dl["state"] == "downloading":
            return
        self.brain_dl.update(id=model_id, pct=0, state="downloading")

        def prog(done, total):
            pct = int(100 * done / total) if total else 0
            if pct != self.brain_dl["pct"]:
                self.brain_dl["pct"] = pct
                self.ui(lambda: (self.ctl.keepAwake(30), self.ctl.setMode("working") if not self.busy else None,
                                 self.ctl.setText("Downloading my brain", f"{pct}%")))

        def work():
            try:
                manager.install_runtime()
                manager.install_model(model_id, prog)
                self.cfg.set("llm_model", model_id)
                self.brain_dl.update(state="done", pct=100)
                self.ui(lambda: self.say(f"My brain is installed, {self.persona.name}. Ask me anything.", "key", hold=5))
            except Exception as e:
                print("[brain install]", e)
                self.brain_dl.update(state="error")
                self.ui(lambda: self.say("The download did not finish. You can try again from the tray menu.", "key", hold=5))
            if on_done:
                on_done()
        threading.Thread(target=work, daemon=True).start()

    def insert_text(self, text: str, hwnd: int | None = None):
        """Type text into the target window, failing closed if the window changed."""
        if hwnd and win.foreground_window() != hwnd:
            win.set_clipboard(text)
            self.say("The window changed, so I copied it instead.", src="button", hold=3.5)
            return
        threading.Thread(target=lambda: win.type_text(text), daemon=True).start()
        self.ctl.setMode("done")
        self.ctl.setText("Done", "")
        QTimer.singleShot(1500, self._back_to_idle)

    # ------------------------------------------------------------------ Controls panel (quick settings)
    def open_controls(self):
        self.ctl.wake()
        self.ctl.keepAwake(30)
        self.ctl.setMode("controls")
        self.refresh_controls()

    def refresh_controls(self):
        """Read the real state off the UI thread (brightness is slow) and show it."""
        def work():
            try:
                snap = self.qs.snapshot(win.get_volume, win.is_muted, win.get_brightness, win.battery)
            except Exception as e:
                print("[controls]", e)
                return
            snap["brightness"] = snap["brightness"] if snap["brightness"] is not None else -1
            self.ui(lambda: self.ctl.setControls({k: v for k, v in snap.items() if v is not None or k in ("wifi", "bluetooth")}))
        threading.Thread(target=work, daemon=True).start()

    def _panel_msg(self, text: str, seconds: float = 3.0):
        self.ctl.setControls({"msg": text})
        QTimer.singleShot(int(seconds * 1000), lambda: self.ctl.controls.get("msg") == text and self.ctl.setControls({"msg": ""}))

    def toggle_quick(self, which: str, on: bool | None = None):
        """Flip Wi-Fi / Bluetooth / Airplane from a tile click (a deliberate tap, so no confirmation)."""
        cur = self.ctl.controls
        if which == "airplane":
            want = (not cur["airplane"]) if on is None else on
            self.ctl.setControls({"airplane": want, "wifi": False if want else True, "bluetooth": False if want else True})
        else:
            want = (not cur[which]) if on is None else on
            self.ctl.setControls({which: want, "airplane": False if want else cur["airplane"]})

        def work():
            ok = self.qs.set_airplane(want) if which == "airplane" else self.qs.set_radio(which, want)
            if not ok:
                self.ui(lambda: self._panel_msg("Windows would not change that"))
            self.ui(self.refresh_controls)
        threading.Thread(target=work, daemon=True).start()

    def voice_quick(self, which: str, on: bool | None, src: str) -> str | None:
        """Voice version: turning Wi-Fi/Airplane OFF cuts your connection, so it asks first."""
        label = {"wifi": "Wi-Fi", "bluetooth": "Bluetooth", "airplane": "Airplane mode"}[which]
        cur = self.ctl.controls
        state = {"wifi": cur["wifi"], "bluetooth": cur["bluetooth"], "airplane": cur["airplane"]}[which]
        want = (not state) if on is None else on
        turning_off_net = (which == "wifi" and not want) or (which == "airplane" and want)
        if turning_off_net:
            self.confirm(f"Turn {label} {'off' if which == 'wifi' else 'on'}? That disconnects you.",
                         lambda: self.toggle_quick(which, want), src)
            return None
        self.toggle_quick(which, want)
        return f"{label} {'on' if (want if which != 'airplane' else not want) else 'off'}." if which != "airplane" else f"Airplane mode {'on' if want else 'off'}."

    def on_control(self, name: str, value: int):
        """A slider/segment was used in the panel."""
        if name == "volume":
            win.set_volume(value)
        elif name == "mute":
            muted = win.toggle_mute()
            self.ctl.setControls({"muted": muted})
        elif name == "brightness":
            def work():
                with self._brightness_lock:
                    win.set_brightness(value)
            threading.Thread(target=work, daemon=True).start()
        elif name == "power":
            mode = ["efficiency", "balanced", "performance"][max(0, min(2, value))]
            ok = self.qs.set_power_mode(mode)
            self.ctl.setControls({"power": mode} if ok else {})
            if not ok:
                self._panel_msg("Windows would not change the power mode")

    def take_screenshot_from_panel(self):
        def work():
            try:
                path = win.screenshot()
                self.ui(lambda: self._panel_msg("Screenshot saved to Pictures"))
            except Exception as e:
                print("[screenshot]", e)
                self.ui(lambda: self._panel_msg("Could not take the screenshot"))
        threading.Thread(target=work, daemon=True).start()
