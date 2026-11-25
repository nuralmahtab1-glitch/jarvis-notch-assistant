from app.core.prompter import MAX_WPM, MIN_WPM, Prompter, wrap_script

SCRIPT = ("Good evening everyone and welcome. Tonight I want to talk about three simple ideas that changed how I work.\n\n"
          "First, keep it small. Second, keep it local. Third, always ask before you act.")


def test_wrapping_respects_width_and_counts_words():
    lines = wrap_script(SCRIPT, width=40)
    assert all(len(l) <= 40 for l, _ in lines)
    assert sum(n for _, n in lines) == len(SCRIPT.split())
    assert ("", 0) in lines                                   # the paragraph break survives as a blank line


def test_nothing_happens_for_an_empty_script():
    p = Prompter("   \n  ")
    assert p.empty and p.view()["empty"] is True
    p.toggle(); assert not p.running
    p.tick(10); assert p.words_done == 0


def test_reads_at_the_chosen_pace():
    p = Prompter("word " * 400, wpm=120); p.toggle()
    p.tick(30)                                                # 30 s at 120 wpm = 60 words
    assert abs(p.words_done - 60) < 1e-6
    assert p.view()["progress"] == p.words_done / p.total_words


def test_paused_prompter_does_not_move():
    p = Prompter(SCRIPT); p.tick(60)
    assert p.words_done == 0
    p.toggle(); p.tick(5); moved = p.words_done
    p.toggle(); p.tick(60)
    assert p.words_done == moved and not p.running


def test_current_line_advances_and_neighbours_skip_blank_lines():
    p = Prompter(SCRIPT, wpm=300, width=40); p.toggle()
    first = p.view()["cur"]
    p.tick(2)                                                 # 10 words at 300 wpm: well inside the script
    v = p.view()
    assert not p.done and v["cur"] != first and v["prev"] == first
    assert v["next"] != "" and "" not in (v["prev"], v["cur"])


def test_finishes_stops_and_restarts_from_the_top():
    p = Prompter(SCRIPT, wpm=300); p.toggle()
    p.tick(10_000)
    assert p.done and not p.running and p.view()["done"] and p.view()["progress"] == 1.0
    p.toggle()                                                # pressing play after the end restarts
    assert p.running and p.words_done == 0


def test_speed_is_clamped():
    p = Prompter(SCRIPT, wpm=1)
    assert p.wpm == MIN_WPM
    for _ in range(100):
        p.faster()
    assert p.wpm == MAX_WPM
    for _ in range(100):
        p.slower()
    assert p.wpm == MIN_WPM


def test_minutes_left_estimate():
    p = Prompter("word " * 140, wpm=140)
    assert abs(p.minutes_left() - 1.0) < 1e-6
    p.toggle(); p.tick(30)
    assert abs(p.minutes_left() - 0.5) < 1e-6


def test_very_long_unbroken_words_do_not_overflow_the_line():
    lines = wrap_script("x" * 200, width=30)
    assert all(len(l) <= 30 for l, _ in lines)
