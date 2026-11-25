import os
import pytest
from app.core.shelf import Shelf, looks_secret, age


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


def test_newest_first_and_dedupe_moves_to_top():
    s = Shelf(Clock())
    s.add_text("one"); s.add_text("two"); s.add_text("one")
    assert [i.text for i in s.items()] == ["one", "two"]


def test_blank_text_ignored():
    s = Shelf(Clock())
    assert s.add_text("") is None and s.add_text("   \n ") is None and len(s) == 0


def test_limit_and_truncation():
    s = Shelf(Clock(), max_items=3)
    for i in range(6):
        s.add_text(f"item {i}")
    assert [i.text for i in s.items()] == ["item 5", "item 4", "item 3"]
    assert len(s.add_text("x" * 5000).text) == 2000


def test_files_only_if_they_exist(tmp_path):
    f = tmp_path / "report.pdf"; f.write_text("x")
    s = Shelf(Clock())
    added = s.add_files([f, tmp_path / "ghost.txt", ""])
    assert len(added) == 1 and added[0].kind == "file"
    v = s.view()[0]
    assert v["title"] == "report.pdf" and v["url"].startswith("file:///")


def test_remove_and_clear():
    s = Shelf(Clock()); a = s.add_text("a"); s.add_text("b")
    assert s.remove(a.id) and not s.remove(a.id) and len(s) == 1
    s.clear(); assert len(s) == 0


@pytest.mark.parametrize("text", ["hunter2Hunter2!x9", "sk-proj-abc123DEF456ghi789", "ghp_1234567890abcdefABCDEF1234",
                                  "Tr0ub4dor&3xyzQ!", "eyJhbGciOiJIUzI1NiJ9"])
def test_secret_looking_text_is_never_kept(text):
    assert looks_secret(text)
    assert Shelf(Clock()).add_text(text) is None


@pytest.mark.parametrize("text", ["hello world this is fine", "https://example.com/some/page?x=1", "C:\\Users\\me\\file.txt",
                                  "maya@example.com", "short", "buy milk and eggs", "meeting at 5pm tomorrow"])
def test_normal_text_is_kept(text):
    assert not looks_secret(text)
    assert Shelf(Clock()).add_text(text) is not None


def test_view_formats_preview_and_age():
    c = Clock(); s = Shelf(c)
    s.add_text("line one\nline   two " + "z" * 100)
    c.t += 200
    v = s.view()[0]
    assert "\n" not in v["title"] and v["title"].endswith("...") and len(v["title"]) <= 64
    assert "3 min ago" in v["sub"] and "characters" in v["sub"]


def test_age_labels():
    assert age(5) == "just now" and age(120) == "2 min ago" and age(7200) == "2 h ago" and age(200000) == "2 d ago"
