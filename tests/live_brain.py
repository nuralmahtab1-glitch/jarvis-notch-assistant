"""Live check: real Qwen3 via llama-server. Measures routing accuracy + latency. Run manually."""
import sys, time
sys.path.insert(0, ".")
from app.llm.server import LocalBackend
from app.llm.brain import Brain
from app.tools.intents import parse

CASES = [  # (utterance the rules parser would miss, expected tool or 'answer')
    ("make it a bit louder please", "volume_change"),
    ("I can barely hear anything, crank the sound to eighty", "volume_set"),
    ("ping me in a quarter of an hour to check the oven", "set_reminder"),
    ("don't let me forget to buy batteries", "todo_add"),
    ("give me forty five minutes of uninterrupted work time", "focus_start"),
    ("shoot a picture of what's on my display", "screenshot"),
    ("fire up the calculator", "open_app"),
    ("skip to the next tune", "media_next"),
    ("pause whatever is playing", "media_play_pause"),
    ("how much juice does the laptop have left", "battery"),
    ("can you look up the weather in london", "search_web"),
    ("put on some jazz", "play_music"),
    ("make the screen darker", "brightness_change"),
    ("I'm done for the day, switch off", "go_to_sleep"),
    ("has claude finished yet", "claude_status"),
    ("what's the capital of australia", "answer"),
    ("how many days are in a leap year", "answer"),
    ("tell me a very short joke", "answer"),
    ("who wrote pride and prejudice", "answer"),
    ("what's two hundred divided by eight", "answer"),
    ("delete all my files", "answer"),            # must NOT become an action
    ("write a two line apology to my landlord for paying rent late", "write_text"),
]
be = LocalBackend(lambda: "qwen3-1.7b")
b = Brain(be, ready=be.installed, name="Nur")
print("installed:", be.installed())
t0 = time.time(); be.chat([{"role": "user", "content": "hi"}], max_tokens=4); print("cold start + first reply:", round(time.time() - t0, 1), "s")
ok = 0; lat = []
for text, want in CASES:
    rules = parse(text)
    t = time.time(); d = b.route(text); dt = time.time() - t; lat.append(dt)
    got = d.intent.name if d.intent else ("answer" if d.answer else "ERROR " + str(d.error))
    good = got == want or (want == "claude_status" and got == "claude_done_query")
    ok += good
    print(("PASS" if good else "FAIL"), f"{dt:4.1f}s", "| rules:", rules.name if rules else "-", "| want", want, "| got", got,
          "|", (d.answer or (d.intent.args if d.intent else ""))) if True else None
print(f"\naccuracy {ok}/{len(CASES)}   median latency {sorted(lat)[len(lat)//2]:.1f}s   max {max(lat):.1f}s")
t = time.time(); w = b.write("a two line apology to my landlord for paying rent late"); print("WRITE (", round(time.time() - t, 1), "s ):", w)
be.stop()
