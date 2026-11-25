from app.winio.media import parse_lrc, lyric_window

LRC = """[ar:Someone]
[00:12.50] The light comes in low
[00:20.00] And everything slows
[00:31.20] We follow it home
"""


def test_parse_lrc_ignores_tags_and_sorts():
    lines = parse_lrc(LRC)
    assert lines == [(12.5, "The light comes in low"), (20.0, "And everything slows"), (31.2, "We follow it home")]


def test_window_before_first_line():
    assert lyric_window(parse_lrc(LRC), 3.0) == ["", "", "The light comes in low"]


def test_window_middle():
    assert lyric_window(parse_lrc(LRC), 22.0) == ["The light comes in low", "And everything slows", "We follow it home"]


def test_window_last_line_has_no_next():
    assert lyric_window(parse_lrc(LRC), 99.0) == ["And everything slows", "We follow it home", ""]


def test_no_lyrics():
    assert lyric_window([], 10) == ["", "", ""]
