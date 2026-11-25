"""Rules-based intent parser: works with no model at all. Made by Nur Al Mahtab."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

NUM_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}
NUM_WORDS.update({"fifteen": 15, "twenty": 20, "thirty": 30, "forty five": 45, "forty-five": 45,
                  "forty": 40, "fifty": 50, "sixty": 60, "an": 1, "a": 1, "half an": 0.5})


@dataclass
class Intent:
    name: str
    args: dict = field(default_factory=dict)
    risky: bool = False

    def __repr__(self):
        return f"Intent({self.name}, {self.args})"


def _norm(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"^(hey|ok|okay)\s+jarvis[,.!\s]*", "", t)
    t = re.sub(r"^jarvis[,.!\s]*", "", t)
    t = re.sub(r"^(please|can you|could you|would you)\s+", "", t)
    t = re.sub(r"[.!?]+$", "", t)
    return t.strip()


def _num(s: str) -> float | None:
    s = s.strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    return NUM_WORDS.get(s)


def parse_when(text: str, now: datetime | None = None):
    """Return (datetime|None, remaining_text_without_time_phrase)."""
    now = now or datetime.now()
    t = text
    m = re.search(r"\bin (\d+|an?|half an|one|two|three|four|five|ten|fifteen|twenty|thirty) "
                  r"(second|minute|min|hour|hr)s?\b", t)
    if m:
        n = _num(m.group(1)) or 1
        unit = m.group(2)
        delta = timedelta(seconds=n) if unit.startswith("sec") else \
            timedelta(minutes=n) if unit.startswith("min") else timedelta(hours=n)
        return now + delta, (t[:m.start()] + t[m.end():]).strip()
    m = re.search(r"\bat (\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b", t) or \
        re.search(r"\bat (one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
                  r"(?: (thirty|fifteen|forty five))?\s*(am|pm)?\b", t)
    if m:
        h = _num(m.group(1))
        h = int(h) if h is not None else 0
        mins = 0
        if m.group(2):
            mins = int(m.group(2)) if m.group(2).isdigit() else int(_num(m.group(2)) or 0)
        ap = (m.group(3) or "").replace(".", "")
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        if not ap and h <= 12 and h < now.hour % 12 + (0 if now.hour % 12 else 12):
            pass
        when = now.replace(hour=h % 24, minute=mins, second=0, microsecond=0)
        if not ap and h < 12:
            # ambiguous "at six": choose the next occurrence
            cand = [when, when + timedelta(hours=12)]
            cand = [c for c in cand if c > now] or [when + timedelta(days=1)]
            when = min(cand)
        elif when <= now:
            when += timedelta(days=1)
        return when, (t[:m.start()] + t[m.end():]).strip()
    return None, t


def parse(text: str, now: datetime | None = None) -> Intent | None:
    t = _norm(text)
    if not t:
        return None

    if re.search(r"\b(go to sleep|goodnight|good night|sleep now)\b", t):
        return Intent("go_to_sleep")
    if re.search(r"^(stop|cancel|never ?mind|be quiet|shut up|quiet)$", t):
        return Intent("cancel")
    if re.search(r"what can you do|what do you do|help me|what are your (commands|features)", t):
        return Intent("what_can_you_do")
    if re.search(r"what('?s| is) the time|what time is it|tell me the time|^the time$", t):
        return Intent("time")
    if re.search(r"what('?s| is) (the )?(date|day)( today)?|what day is it|today'?s date", t):
        return Intent("date")

    m = re.match(r"^(?:write|draft|compose|type out)\s+(.{6,})", t)
    if m and not re.match(r"^(down|it down)\b", m.group(1)):
        return Intent("write_text", {"instruction": m.group(1).strip()})

    # Claude Code
    if re.search(r"(what('?s| is) claude doing|claude status|how('?s| is) claude)", t):
        return Intent("claude_status")
    if re.search(r"is claude (done|finished|ready)", t):
        return Intent("claude_done_query")
    if re.search(r"which sessions|claude sessions|list sessions", t):
        return Intent("claude_sessions")
    if re.fullmatch(r"(approve|allow|allow once|yes approve|approve it)", t):
        return Intent("claude_approve")
    if re.fullmatch(r"(deny|reject|decline|deny it|don'?t allow)", t):
        return Intent("claude_deny")

    # focus
    m = re.search(r"start (a |an )?(focus|pomodoro)( session| timer)?( for (\d+|one|two|five|ten|fifteen|twenty|thirty|forty five|forty-five|fifty|sixty) minutes?)?", t)
    if m:
        mins = _num(m.group(5)) if m.group(5) else 25
        return Intent("focus_start", {"minutes": int(mins or 25)})
    if re.search(r"(stop|end|cancel) (the |my )?(focus|pomodoro)", t):
        return Intent("focus_stop")
    if re.search(r"(take|start) a break", t):
        return Intent("focus_break")

    # to-do
    m = re.match(r"add (.+?) to (my |the )?(to-?do|task|shopping)?\s*(list)?$", t)
    if m and m.group(1):
        return Intent("todo_add", {"text": m.group(1).strip()})
    m = re.match(r"(?:add (?:a )?(?:task|todo|to-do)[: ]+|todo[: ]+)(.+)", t)
    if m:
        return Intent("todo_add", {"text": m.group(1).strip()})
    if re.search(r"what('?s| is) on my (list|to-?do)|show (me )?my (list|to-?do)|read my (list|to-?do)|my to-?do", t):
        return Intent("todo_list")
    m = re.match(r"(?:mark|tick off|check off|complete|finish)\s+(.+?)(?: (?:as )?(?:done|complete|completed))?$", t)
    if m and not re.match(r"^(claude|it)\b", m.group(1)):
        return Intent("todo_complete", {"text": m.group(1).strip()})
    m = re.match(r"(?:remove|delete) (.+?) from (my |the )?(list|to-?do)", t)
    if m:
        return Intent("todo_remove", {"text": m.group(1).strip()})

    # reminders
    m = re.match(r"remind me (?:to |about )?(.+)", t)
    if m:
        when, rest = parse_when(m.group(1), now)
        rest = re.sub(r"\s+", " ", rest).strip(" ,")
        return Intent("set_reminder", {"text": rest, "when": when})
    m = re.match(r"(?:set (?:a |an )?(?:timer|alarm) (?:for )?)(.+)", t)
    if m:
        when, rest = parse_when("in " + m.group(1) if re.match(r"\d|an?\b|one|two|five|ten", m.group(1)) else m.group(1), now)
        return Intent("set_reminder", {"text": "Timer", "when": when})

    # volume / brightness
    m = re.search(r"(?:set )?(?:the )?volume (?:to )?(\d{1,3})", t) or re.search(r"(?:set )?(?:the )?volume to (\w+)", t)
    if m and _num(m.group(1)) is not None:
        return Intent("volume_set", {"level": int(max(0, min(100, _num(m.group(1)))))})
    if re.search(r"\b(volume|turn it|sound) up|louder|raise the volume", t):
        return Intent("volume_change", {"delta": +10})
    if re.search(r"\b(volume|turn it|sound) down|quieter|lower the volume|softer", t):
        return Intent("volume_change", {"delta": -10})
    if re.search(r"^(mute|unmute)\b|\bmute (the )?(sound|volume|computer)", t):
        return Intent("mute_toggle")
    m = re.search(r"(?:set )?brightness (?:to )?(\d{1,3})", t)
    if m:
        return Intent("brightness_set", {"level": int(min(100, int(m.group(1))))})
    if re.search(r"brightness up|brighter", t):
        return Intent("brightness_change", {"delta": +10})
    if re.search(r"brightness down|dimmer|darker", t):
        return Intent("brightness_change", {"delta": -10})

    # media
    m = re.match(r"play (.+?)(?: on spotify)?$", t)
    if m and m.group(1) not in ("music", "it", "the music", "something"):
        return Intent("play_music", {"query": m.group(1).strip()})
    if re.search(r"^(play|resume)( the)?( music| song)?$", t):
        return Intent("media_play_pause")
    if re.search(r"^(pause|stop)( the)?( music| song)?$", t):
        return Intent("media_play_pause")
    if re.search(r"next (song|track)|skip( this)?( song| track)?$", t):
        return Intent("media_next")
    if re.search(r"(previous|last) (song|track)|go back a (song|track)", t):
        return Intent("media_prev")

    # system
    if re.search(r"(take|grab|capture) (a )?screenshot|screenshot", t):
        return Intent("screenshot")
    on = True if re.search(r"\b(on|enable)\b", t) else False if re.search(r"\b(off|disable)\b", t) else None
    if re.search(r"wi-?fi|wireless", t) and re.search(r"turn|switch|toggle|enable|disable|\bon\b|\boff\b", t):
        return Intent("wifi_toggle", {"on": on})
    if re.search(r"blue ?tooth", t) and re.search(r"turn|switch|toggle|enable|disable|\bon\b|\boff\b", t):
        return Intent("bluetooth_toggle", {"on": on})
    if re.search(r"air ?plane mode|flight mode", t):
        return Intent("airplane_toggle", {"on": on})
    m = re.search(r"(?:power mode|performance mode|battery saver|power saver)", t)
    if m:
        mode = "performance" if "performance" in t else "efficiency" if re.search(r"saver|efficien|battery", t) else "balanced" if "balanced" in t else None
        return Intent("power_mode_set", {"mode": mode}) if mode else Intent("controls_open")
    if re.search(r"night light", t):
        return Intent("night_light_toggle")
    if re.search(r"(open|show|bring up) (the )?(controls|quick settings|control panel)", t):
        return Intent("controls_open")
    if re.search(r"battery( level| status| percentage)?|how much battery", t):
        return Intent("battery")
    m = re.match(r"(?:open|launch|start|run) (.+)", t)
    if m:
        return Intent("open_app", {"name": m.group(1).strip()})
    m = re.match(r"(?:search|google|look up|search for|search the web for) (.+)", t)
    if m:
        return Intent("search_web", {"query": m.group(1).strip()})
    m = re.match(r"(?:go to|open website|visit) (\S+\.\S+)", t)
    if m:
        return Intent("open_website", {"url": m.group(1)})

    return None


CAPABILITIES = (
    "I can dictate into any app, keep your list, set reminders and focus sessions, control volume "
    "and brightness, take screenshots, open apps, search the web, play music on Spotify, and tell "
    "you what Claude Code is doing."
)
