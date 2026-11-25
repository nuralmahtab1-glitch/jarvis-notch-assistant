"""Assistant: wires voice, tools, dictation, reminders, focus and Claude Code status to the notch.
Made by Nur Al Mahtab."""
from __future__ import annotations
import threading, time
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
from app.claude_bridge.tracker import TERMINAL_PROCS, Tracker, fmt_duration


class Assistant(QObject):
    _ui = Signal(object)

    def __init__(self, ctl: NotchController, settings: Settings, store: Store,
                 speaker=None, transcriber=None, recorder_factory=None, tracker: Tracker | None = None):
        super().__init__()
        self.ctl, self.cfg, self.store = ctl, settings, store
        self.speaker, self.stt = speaker, transcriber
        self._recorder_factory = recorder_factory
        self.rec = None
        self.persona = Persona("butler", settings["address"])
        self.tracker = tracker
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
        self._level_t = 0.0
        self._ui.connect(lambda fn: fn())
        ctl.action.connect(self.on_action)
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

    CARD_MODES = ("todo", "volume", "focus", "music")

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

    def _end(self):
        if not self.busy or not self.rec:
            return
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
        if hwnd and win.foreground_window() != hwnd:      # fail closed: never type into a different window
            win.set_clipboard(cleaned)
            self.say("The window changed, so I copied it instead.", src="button", hold=3.5)
            return
        threading.Thread(target=lambda: win.type_text(cleaned), daemon=True).start()
        self.ctl.setMode("done")
        self.ctl.setText("Done", "")
        QTimer.singleShot(1500, self._back_to_idle)

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
            self.say(self.persona.say("unknown"), src)
            return
        reply = self.run_intent(intent, src)
        if reply is not None:
            self.say(reply, src)

    def run_intent(self, it: Intent, src: str = "key") -> str | None:
        p, n, a = self.persona, self.persona.name, it.args
        try:
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
                return f"Opening {a['name']}." if win.open_app(a["name"]) else f"I could not open {a['name']}."
            if it.name == "open_website":
                win.open_url(a["url"]); return "Opening it now."
            if it.name == "search_web":
                win.search_web(a["query"]); return f"Searching for {a['query']}."
            if it.name == "battery":
                pct, plugged = win.battery()
                return "No battery detected." if pct is None else f"Battery is at {pct} percent{', charging' if plugged else ''}."
            if it.name in ("wifi_toggle", "night_light_toggle"):
                return "I cannot toggle that one yet, " + n + "."
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
        if self._focus_end:
            left = int(self._focus_end - now)
            self.ctl.setFocus(max(0, left), self._focus_total)
            if self.ctl.mode == "focus":
                self.ctl.keepAwake(5)
            if left <= 0:
                self._focus_end = 0
                win.chime()
                done_msg = "Break over. Back to it." if self._focus_label == "Break" else \
                    "Focus session complete. " + self.persona.say("break_hint")
                self.say(done_msg.strip(), src="voice-timer" if False else "key", hold=4)
        for r in self.store.reminders_due():
            win.chime()
            self.ctl.wake()
            self.show_card("reminder", "Reminder", r["text"], seconds=25)
            if self.speaker and not self.cfg["dnd"] and self.speak_mode != "off":
                self.speaker.speak(f"Reminder: {r['text']}.")
            self._last_reminder = r
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
