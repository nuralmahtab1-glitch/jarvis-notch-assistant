from datetime import datetime
import pytest
from app.tools.intents import parse, parse_when

NOW = datetime(2026, 11, 25, 4, 6)


def n(text):
    i = parse(text, NOW)
    return i.name if i else None


@pytest.mark.parametrize("text,name", [
    ("Hey Jarvis, remind me to call Mom at six", "set_reminder"),
    ("Start a focus session", "focus_start"),
    ("What's on my list?", "todo_list"),
    ("Play Billie Jean on Spotify", "play_music"),
    ("Take a screenshot", "screenshot"),
    ("What can you do?", "what_can_you_do"),
    ("goodnight", "go_to_sleep"),
    ("add buy milk to my list", "todo_add"),
    ("mark buy milk done", "todo_complete"),
    ("volume to 40", "volume_set"),
    ("turn it up", "volume_change"),
    ("open spotify", "open_app"),
    ("search for best pizza near me", "search_web"),
    ("what's Claude doing?", "claude_status"),
    ("is Claude done", "claude_done_query"),
    ("approve", "claude_approve"),
    ("deny", "claude_deny"),
    ("what time is it", "time"),
    ("skip", "media_next"),
])
def test_names(text, name):
    assert n(text) == name


def test_unknown_returns_none():
    assert parse("blorp flibber", NOW) is None


def test_reminder_args():
    i = parse("remind me to call Mom at six", NOW)
    assert i.args["text"] == "call mom"
    assert i.args["when"].hour == 6 and i.args["when"] > NOW


def test_reminder_relative():
    when, rest = parse_when("stretch in 10 minutes", NOW)
    assert (when - NOW).total_seconds() == 600 and rest == "stretch"


def test_pm():
    when, _ = parse_when("call at 6pm", NOW)
    assert when.hour == 18


def test_focus_minutes():
    assert parse("start a focus session for 45 minutes", NOW).args["minutes"] == 45
    assert parse("start a focus session", NOW).args["minutes"] == 25


def test_volume_level_clamped():
    assert parse("volume to 150", NOW).args["level"] == 100
