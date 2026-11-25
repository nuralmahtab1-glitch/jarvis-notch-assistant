"""Persona presets: wording for spoken replies. Made by Nur Al Mahtab.

"Butler" is an original calm, refined British-butler style. It does not imitate any real actor or
film character. Jokes are rare and never used for errors or confirmations.
"""
from __future__ import annotations
import random

PRESETS = {
    "butler": {
        "ack": ["Of course.", "Right away.", "Certainly.", "Very good."],
        "done": ["Done.", "All done.", "Consider it done."],
        "greet_morning": "Good morning, {name}. All systems are running smoothly.",
        "greet_afternoon": "Good afternoon, {name}.",
        "greet_evening": "Good evening, {name}. All systems are running smoothly.",
        "greet_night": "Good evening, {name}. Burning the midnight oil, I see.",
        "sleep": "Goodnight, {name}.",
        "unknown": "I am afraid I did not catch that, {name}.",
        "error": "I am sorry, {name}. That did not work.",
        "claude_done": "Claude has finished, {name}.",
        "claude_needs": "Claude needs your permission, {name}.",
        "claude_error": "Claude has run into an error, {name}.",
        "break_hint": "Might I suggest a short break?",
    },
    "friendly": {
        "ack": ["Sure!", "On it!", "You got it."], "done": ["Done!", "All set."],
        "greet_morning": "Morning, {name}!", "greet_afternoon": "Hey {name}!", "greet_evening": "Evening, {name}!",
        "greet_night": "Still up, {name}?", "sleep": "Night, {name}!", "unknown": "Sorry, I didn't catch that.",
        "error": "Oops, that didn't work.", "claude_done": "Claude's finished!", "claude_needs": "Claude needs you.",
        "claude_error": "Claude hit an error.", "break_hint": "Time for a break?",
    },
    "neutral": {
        "ack": ["Okay."], "done": ["Done."], "greet_morning": "Good morning.", "greet_afternoon": "Good afternoon.",
        "greet_evening": "Good evening.", "greet_night": "Hello.", "sleep": "Goodnight.", "unknown": "I did not catch that.",
        "error": "That did not work.", "claude_done": "Claude has finished.", "claude_needs": "Claude needs permission.",
        "claude_error": "Claude hit an error.", "break_hint": "Take a break?",
    },
    "minimal": {
        "ack": [""], "done": ["Done."], "greet_morning": "", "greet_afternoon": "", "greet_evening": "",
        "greet_night": "", "sleep": "", "unknown": "Sorry?", "error": "Failed.", "claude_done": "Claude done.",
        "claude_needs": "Claude needs you.", "claude_error": "Claude error.", "break_hint": "",
    },
}


class Persona:
    def __init__(self, preset: str = "butler", name: str = "there"):
        self.preset, self.name = preset, name

    def say(self, key: str, **kw) -> str:
        p = PRESETS.get(self.preset, PRESETS["butler"])
        v = p.get(key, "")
        if isinstance(v, list):
            v = random.choice(v)
        return v.format(name=self.name, **kw).strip()

    def greeting(self, hour: int) -> str:
        key = ("greet_night" if hour < 5 else "greet_morning" if hour < 12
               else "greet_afternoon" if hour < 18 else "greet_evening")
        return self.say(key)
