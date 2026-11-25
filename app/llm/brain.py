"""The brain: turns anything the rules parser missed into a tool call or a short answer.
Made by Nur Al Mahtab.

The rules parser always goes first (fast, deterministic). The model only handles what it misses, plus
questions and writing. Tools are validated against a fixed registry: the model can only pick from it.
"""
from __future__ import annotations
import json, re, threading, time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from app import config
from app.tools.intents import Intent, parse_when

# tool name -> {arg: description}. The model may only choose from this list.
TOOLS: dict[str, dict[str, str]] = {
    "set_reminder": {"text": "what to remind about", "when": "natural time like 'in 10 minutes' or 'at 6pm'"},
    "todo_add": {"text": "task"}, "todo_list": {}, "todo_complete": {"text": "task"}, "todo_remove": {"text": "task"},
    "focus_start": {"minutes": "integer, default 25"}, "focus_stop": {},
    "volume_set": {"level": "0-100"}, "volume_change": {"delta": "+10 or -10"}, "mute_toggle": {},
    "brightness_set": {"level": "0-100"}, "brightness_change": {"delta": "+10 or -10"},
    "media_play_pause": {}, "media_next": {}, "media_prev": {}, "play_music": {"query": "song or artist"},
    "screenshot": {}, "open_app": {"name": "app name"}, "open_website": {"url": "domain or url"},
    "search_web": {"query": "search text"}, "battery": {}, "time": {}, "date": {},
    "go_to_sleep": {}, "claude_status": {}, "claude_approve": {}, "claude_deny": {},
    "wifi_toggle": {"on": "true, false, or omit to toggle"}, "bluetooth_toggle": {"on": "true, false, or omit to toggle"},
    "airplane_toggle": {"on": "true, false, or omit to toggle"}, "night_light_toggle": {},
    "power_mode_set": {"mode": "efficiency, balanced or performance"}, "controls_open": {},
    "write_text": {"instruction": "what to write, e.g. 'a polite email asking for a deadline extension'"},
}
INT_ARGS = {"minutes": 25, "level": 50, "delta": 10}


class Chat(Protocol):
    def chat(self, messages: list[dict], max_tokens: int = ..., temperature: float = ..., json_mode: bool = ...,
             timeout: float = ...) -> str: ...


@dataclass
class Decision:
    intent: Intent | None = None
    answer: str | None = None
    error: str | None = None
    retry_as_answer: bool = False      # the model used a tool the words did not justify: ask again for plain text


def time_note(now: datetime | None = None) -> str:
    """The current date/time goes in the user message, NOT the system prompt: the system prompt must stay
    byte-identical so the model server can reuse its cached processing of it (this cut a 10 s wait to 2 s)."""
    return (now or datetime.now()).strftime("[Now: %A %d %B %Y, %H:%M]")


def system_prompt(name: str, now: datetime | None = None) -> str:
    tools = "\n".join(f"- {t} {json.dumps(a) if a else ''}".rstrip() for t, a in TOOLS.items())
    return (
        f"You are {config.APP_NAME}, a calm, concise, slightly witty British butler-style assistant on {name}'s Windows PC. "
        "Each user message starts with a [Now: ...] note giving the current date and time.\n"
        "Reply with exactly ONE JSON object and nothing else.\n"
        '- If the user wants something done, use a tool: {"tool": "<name>", "args": {...}}.\n'
        '- If they ask a question or chat, answer: {"answer": "<one or two short sentences>"}.\n'
        "- Only use tools from this list. Never invent tools. Never send, delete or buy anything.\n"
        "- Prefer a tool over an answer when an action is requested.\n"
        "- Facts about THIS PC or the user's data (battery, volume, time, date, their list, what Claude is doing) "
        "must come from a tool. Never guess or invent them.\n"
        "- 'remember / don't let me forget X' with no time -> todo_add. With a time -> set_reminder.\n"
        "- 'put on / play X' -> play_music. 'is Claude done / what is Claude doing' -> claude_status.\n"
        "- If asked to delete, erase, wipe or destroy files or data, answer that you cannot do that.\n"
        "- General-knowledge questions get a direct answer. Use search_web ONLY when the user says search, look up or google.\n"
        f"Tools:\n{tools}\n"
        "Examples:\n"
        'User: how much battery is left -> {"tool":"battery","args":{}}\n'
        'User: don\'t let me forget the milk -> {"tool":"todo_add","args":{"text":"milk"}}\n'
        'User: put on some jazz -> {"tool":"play_music","args":{"query":"jazz"}}\n'
        'User: has claude finished -> {"tool":"claude_status","args":{}}\n'
        'User: a bit quieter -> {"tool":"volume_change","args":{"delta":-10}}\n'
        'User: erase my documents folder -> {"answer":"I cannot delete files, I am afraid."}\n'
        'User: what is the tallest mountain -> {"answer":"Mount Everest, at 8,849 metres."}')


def extract_json(text: str) -> dict | None:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except ValueError:
        return None


def to_intent(obj: dict, now: datetime | None = None) -> Decision:
    """Validate the model's output against the registry and turn it into an Intent."""
    if "tool" in obj:
        tool = str(obj["tool"]).strip()
        if tool not in TOOLS:
            return Decision(error=f"unknown tool {tool!r}")
        raw = obj.get("args") or {}
        if not isinstance(raw, dict):
            raw = {}
        args = {k: raw[k] for k in TOOLS[tool] if k in raw}
        for k in args:
            if k in INT_ARGS:
                try:
                    args[k] = int(float(str(args[k]).replace("+", "")))
                except ValueError:
                    args[k] = INT_ARGS[k]
        if tool in ("wifi_toggle", "bluetooth_toggle", "airplane_toggle"):
            v = raw.get("on")
            args = {"on": v if isinstance(v, bool) else (str(v).lower() in ("true", "on", "yes") if v is not None else None)}
        if tool == "power_mode_set":
            mode = str(raw.get("mode", "")).lower().strip()
            if mode not in ("efficiency", "balanced", "performance"):
                return Decision(error="unknown power mode")
            args = {"mode": mode}
        if tool == "focus_start":
            args["minutes"] = max(1, min(180, args.get("minutes", 25)))
        if tool in ("volume_set", "brightness_set"):
            args["level"] = max(0, min(100, args.get("level", 50)))
        if tool in ("volume_change", "brightness_change"):
            args["delta"] = max(-50, min(50, args.get("delta", 10)))
        if tool == "set_reminder":
            when, _ = parse_when(" ".join(str(raw.get("when", "")).lower().split()).strip() or "", now)
            args = {"text": str(raw.get("text", "")).strip() or "Reminder", "when": when}
        for k, v in list(args.items()):
            if isinstance(v, str):
                args[k] = v.strip()[:400]
        return Decision(intent=Intent(tool, args))
    if isinstance(obj.get("answer"), str) and obj["answer"].strip():
        return Decision(answer=obj["answer"].strip()[:400])
    return Decision(error="model returned neither a tool nor an answer")


class Brain:
    """Wraps a Chat backend. `ready()` says whether it can answer without a download."""

    def __init__(self, backend: Chat | None, ready: Callable[[], bool] = lambda: True, name: str = "there"):
        self.backend, self._ready, self.name = backend, ready, name
        self.history: list[tuple[str, str]] = []      # short memory of the last few turns
        self._lock = threading.Lock()

    def ready(self) -> bool:
        return self.backend is not None and self._ready()

    def warm(self) -> float | None:
        """Load the model and process the long instruction prompt once, so the first real question is fast
        (the server keeps the processed prompt cached). Returns seconds taken, or None if not possible."""
        if not self.ready():
            return None
        t0 = time.time()
        try:
            with self._lock:
                self.backend.chat([{"role": "system", "content": system_prompt(self.name)},
                                   {"role": "user", "content": f"{time_note()} hello"}], max_tokens=1, temperature=0.0, json_mode=True)
        except Exception:
            return None
        return time.time() - t0

    def route(self, text: str, now: datetime | None = None) -> Decision:
        if not self.ready():
            return Decision(error="no brain installed")
        msgs = [{"role": "system", "content": system_prompt(self.name, now)}]
        for u, a in self.history[-3:]:
            msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
        msgs.append({"role": "user", "content": f"{time_note(now)} {text}"})
        try:
            with self._lock:
                raw = self.backend.chat(msgs, max_tokens=160, temperature=0.2, json_mode=True)
        except Exception as e:
            return Decision(error=f"brain failed: {e}")
        obj = extract_json(raw)
        if obj is None:
            # a model that ignored the format: treat plain text as the answer
            plain = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
            return Decision(answer=plain[:300]) if plain else Decision(error="empty reply")
        d = to_intent(obj, now)
        d = self._guard(text, d)
        if d.retry_as_answer:
            d = self._answer_directly(text, now)
        if d.answer or d.intent:
            self.history.append((text, d.answer or json.dumps(obj)))
            del self.history[:-6]
        return d

    SEARCH_WORDS = re.compile(r"search|look up|lookup|google|bing|browse|web|find (me )?(information|info|out)|on the internet", re.I)

    def _answer_directly(self, text: str, now: datetime | None) -> Decision:
        """Second chance: a plain-text answer, no tools, for questions the model wrongly turned into a web search."""
        try:
            with self._lock:
                out = self.backend.chat(
                    [{"role": "system", "content": f"You are {config.APP_NAME}, a calm, concise British butler-style assistant. "
                      "Answer the question directly in one or two short sentences. Plain text only. "
                      "If you do not know, say so briefly."},
                     {"role": "user", "content": f"{time_note(now)} {text}"}],
                    max_tokens=120, temperature=0.2, json_mode=False)
        except Exception as e:
            return Decision(error=f"brain failed: {e}")
        plain = re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()
        return Decision(answer=plain[:300]) if plain else Decision(error="empty reply")

    DESTRUCTIVE = re.compile(
        r"\b(delete|erase|wipe|format|destroy|uninstall|shred|nuke|purge|trash|get rid of|throw (it |them )?(all )?away|"
        r"clear (out|all)|clean out|empty (the|my)|remove (all|everything))\b", re.I)
    VAGUE = {"all", "everything", "files", "file", "it", "them", "that", "this", "stuff", "documents", "folder"}

    # A small model will happily invent facts about your PC. These force a real tool for such questions.
    GROUNDED = [
        (re.compile(r"\b(my )?(list|to-?dos?|tasks?|chores?)\b", re.I), "todo_list"),
        (re.compile(r"\bbattery|charge level|how much (juice|power)\b", re.I), "battery"),
        (re.compile(r"\bclaude\b", re.I), "claude_status"),
        (re.compile(r"\bwhat('?s| is) the time|what time\b", re.I), "time"),
        (re.compile(r"\bwhat('?s| is) (the )?(date|day)|what day\b", re.I), "date"),
    ]
    # A tool must be justified by the user's own words, or it is treated as a misunderstanding.
    SANITY = {
        "mute_toggle": re.compile(r"mute|silen|quiet|shush|hush|sound off|speakers? off", re.I),
        "brightness_set": re.compile(r"bright|dim|dark|glare|screen|display|monitor|light", re.I),
        "brightness_change": re.compile(r"bright|dim|dark|glare|screen|display|monitor|light", re.I),
        "volume_set": re.compile(r"volume|loud|quiet|sound|audio|speaker|hear|decibel|turn it", re.I),
        "volume_change": re.compile(r"volume|loud|quiet|sound|audio|speaker|hear|turn it|up|down", re.I),
        "wifi_toggle": re.compile(r"wi-?fi|wireless|internet|network|online", re.I),
        "bluetooth_toggle": re.compile(r"blue ?tooth", re.I),
        "airplane_toggle": re.compile(r"air ?plane|flight|offline", re.I),
        "power_mode_set": re.compile(r"power|performance|battery|efficien|balanced|mode|saver", re.I),
        "go_to_sleep": re.compile(r"sleep|night|done for the day|switch off|shut|bed|rest|bye", re.I),
        "screenshot": re.compile(r"screen|shot|picture|capture|snap|photo|display|image", re.I),
    }

    def _guard(self, text: str, d: Decision) -> Decision:
        """Hard safety net, independent of what the model said."""
        if d.answer and not d.intent:                       # answers about the user's own data must come from a tool
            for pat, tool in self.GROUNDED:
                if pat.search(text) and not re.search(r"\b(why|how does|how do|who|when was|history)\b", text, re.I):
                    return Decision(intent=Intent(tool, {}))
        if d.intent and d.intent.name in ("todo_remove", "todo_complete") and \
                not re.search(r"\b(list|to-?dos?|tasks?|chores?|reminders?|done|finished|complete)\b", text, re.I):
            if self.DESTRUCTIVE.search(text):
                return Decision(answer="I cannot delete things from your PC, and I will not guess.")
            return Decision(error="list change was not asked for")
        if d.intent and d.intent.name == "search_web" and not self.SEARCH_WORDS.search(text):
            return Decision(error="search was not asked for", retry_as_answer=True)
        if d.intent and d.intent.name in self.SANITY and not self.SANITY[d.intent.name].search(text):
            return Decision(error=f"{d.intent.name} does not match the request")
        """Destructive wording never becomes an action unless it is an explicit, specific list removal."""
        if d.intent and self.DESTRUCTIVE.search(text):
            a = d.intent.args.get("text", "").lower().strip()
            specific = d.intent.name == "todo_remove" and len(a) >= 4 and a not in self.VAGUE and a in text.lower()
            if not specific:
                return Decision(answer="I cannot delete things from your PC, and I will not guess.")
        return d

    def write(self, instruction: str) -> str | None:
        """Draft text to type into the focused app. Returns just the text, no preamble."""
        if not self.ready():
            return None
        msgs = [{"role": "system", "content":
                 f"You write short drafts for {self.name}. Output ONLY the text to insert: no preamble, no quotes, "
                 "no explanations, no markdown. Plain, natural, concise. Do not invent facts, names or dates."},
                {"role": "user", "content": instruction}]
        try:
            with self._lock:
                out = self.backend.chat(msgs, max_tokens=400, temperature=0.5, json_mode=False, timeout=120)
        except Exception:
            return None
        out = re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip().strip('"')
        return out or None
