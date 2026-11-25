from app.tools.dictation import clean, remove_fillers


def test_reference_example():
    raw = "Um, hey Sam, I'm running about, uh, ten, actually fifteen minutes late. Save me a seat."
    assert clean(raw) == "Hey Sam, I'm running about fifteen minutes late. Save me a seat."


def test_bullets():
    out = clean("bullet point eggs bullet point milk")
    assert out == "- Eggs\n- Milk"


def test_bullets_with_lead():
    out = clean("shopping list bullet point eggs bullet point milk")
    assert out.splitlines()[-2:] == ["- Eggs", "- Milk"]


def test_fillers_only():
    assert remove_fillers("um uh so erm yes") == "so yes"


def test_scratch_that():
    assert clean("send it tonight. scratch that send it tomorrow") == "Send it tomorrow."


def test_spoken_punctuation():
    assert clean("hello comma world full stop") == "Hello, world."


def test_capital_i():
    assert clean("i think i'm done") == "I think I'm done."


def test_empty():
    assert clean("   ") == ""
