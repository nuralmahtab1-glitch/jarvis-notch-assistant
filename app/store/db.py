"""Local storage: SQLite for lists/reminders, JSON for settings. Made by Nur Al Mahtab."""
from __future__ import annotations
import json, os, sqlite3, threading, time
from pathlib import Path

from app import config


def data_dir() -> Path:
    p = Path(os.environ.get("APPDATA", str(Path.home()))) / "Jarvis"
    p.mkdir(parents=True, exist_ok=True)
    return p


DEFAULT_SETTINGS = {
    "address": config.DEFAULT_ADDRESS,
    "speak_replies": "voice",        # off | voice | always
    "voice_speed": 1.0,
    "ptt_command_key": "right ctrl",
    "ptt_dictate_key": "right alt",
    "wake_word": True,
    "sleep_after_minutes": 5,
    "dnd": False,
    "claude_bridge": True,
    "claude_hide_details": False,
    "claude_approval_timeout": 30,
    "claude_speak": {"done": True, "needs_you": True, "error": True},
    "claude_quiet_when_focused": True,
    "greeting": True,
    "lyrics": True,
    "onboarded": False,
    "stt_model": "base.en",
    "llm_model": "qwen3-1.7b",
    "websites": ["youtube.com", "github.com", "gmail.com"],
}


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "settings.json"
        self.data = dict(DEFAULT_SETTINGS)
        try:
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
        except Exception:
            pass

    def __getitem__(self, k): return self.data[k]
    def get(self, k, d=None): return self.data.get(k, d)

    def set(self, k, v):
        self.data[k] = v
        self.save()

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        tmp.replace(self.path)


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = str(path or data_dir() / "jarvis.db")
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS todos(id INTEGER PRIMARY KEY, text TEXT NOT NULL, done INTEGER DEFAULT 0, created REAL);
            CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY, text TEXT NOT NULL, due REAL NOT NULL, fired INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS shelf(id INTEGER PRIMARY KEY, kind TEXT, content TEXT, created REAL);
        """)

    def _q(self, sql, args=()):
        with self._lock:
            cur = self._db.execute(sql, args)
            self._db.commit()
            return cur

    # ---- todos ----
    def todo_add(self, text: str) -> int:
        return self._q("INSERT INTO todos(text, created) VALUES(?,?)", (text.strip(), time.time())).lastrowid

    def todo_list(self) -> list[dict]:
        return [dict(r) for r in self._q("SELECT id, text, done FROM todos ORDER BY done, id").fetchall()]

    def todo_toggle(self, tid: int):
        self._q("UPDATE todos SET done = 1 - done WHERE id=?", (tid,))

    def todo_complete_match(self, text: str) -> str | None:
        text = text.lower().strip()
        if len(text) < 3:
            return None
        for r in self.todo_list():
            if not r["done"] and (text in r["text"].lower() or r["text"].lower() in text):
                self._q("UPDATE todos SET done=1 WHERE id=?", (r["id"],))
                return r["text"]
        return None

    def todo_remove_match(self, text: str) -> str | None:
        text = text.lower().strip()
        if len(text) < 3 or text in ("all", "everything", "the list", "my list"):
            return None
        for r in self.todo_list():
            if text in r["text"].lower():
                self._q("DELETE FROM todos WHERE id=?", (r["id"],))
                return r["text"]
        return None

    # ---- reminders ----
    def reminder_add(self, text: str, due_ts: float) -> int:
        return self._q("INSERT INTO reminders(text, due) VALUES(?,?)", (text, due_ts)).lastrowid

    def reminders_due(self, now: float | None = None) -> list[dict]:
        now = now or time.time()
        rows = [dict(r) for r in self._q("SELECT * FROM reminders WHERE fired=0 AND due<=?", (now,)).fetchall()]
        for r in rows:
            self._q("UPDATE reminders SET fired=1 WHERE id=?", (r["id"],))
        return rows

    def reminders_pending(self) -> list[dict]:
        return [dict(r) for r in self._q("SELECT * FROM reminders WHERE fired=0 ORDER BY due").fetchall()]

    # ---- privacy ----
    def wipe(self):
        for t in ("todos", "reminders", "shelf"):
            self._q(f"DELETE FROM {t}")
