"""Held-out live check: phrasings that are NOT in the prompt examples. Run manually."""
import sys, time
sys.path.insert(0, ".")
from app.llm.server import LocalBackend
from app.llm.brain import Brain
from app.tools.intents import parse

CASES = [
    ("is there anything left on my chore list", "todo_list"),
    ("jot down that I need to renew my passport", "todo_add"),
    ("alert me in forty minutes to move the laundry", "set_reminder"),
    ("what's the charge level on this machine", "battery"),
    ("start spinning up some drum and bass", "play_music"),
    ("how's claude getting along", "claude_status"),
    ("lower the glare on my monitor", "brightness_change"),
    ("silence the speakers", "mute_toggle"),
    ("open up the file explorer", "open_app"),
    ("what's the time right now", "time"),
    ("how many legs does a spider have", "answer"),
    ("why is the sky blue", "answer"),
    ("who painted the mona lisa", "answer"),
    ("wipe my downloads folder clean", "answer"),
    ("get rid of everything on my desktop", "answer"),
    ("give me twenty minutes to concentrate", "focus_start"),
    ("kill the wireless connection", "wifi_toggle"),
    ("I want the laptop to squeeze more battery life", "power_mode_set"),
    ("show me the quick settings", "controls_open"),
    ("turn the speakers off", "mute_toggle"),
]
be = LocalBackend(lambda: "qwen3-1.7b")
b = Brain(be, ready=be.installed, name="Nur")
ok = 0
for text, want in CASES:
    d = b.route(text)
    got = d.intent.name if d.intent else ("answer" if d.answer else "ERROR " + str(d.error))
    good = got == want
    ok += good
    print("PASS" if good else "FAIL", "| rules:", (parse(text).name if parse(text) else "-"), "| want", want, "| got", got,
          "|", (d.answer or (d.intent.args if d.intent else "")))
print(f"\nheld-out accuracy {ok}/{len(CASES)}")
be.stop()
