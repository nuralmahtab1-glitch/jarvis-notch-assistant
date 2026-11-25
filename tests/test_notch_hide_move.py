import os, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication
from app.ui.controller import NotchController


@pytest.fixture
def ctl():
    QApplication.instance() or QApplication([])
    c = NotchController(); c._poll.stop()           # drive ticks by hand
    c.autohide, c.autohide_after = True, 0.2
    return c


def cursor(x, y, monkeypatch):
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: QPoint(x, y)))


def far(ctl, monkeypatch):
    g = QGuiApplication.primaryScreen().geometry()
    cursor(g.x() + g.width() // 2, g.y() + 600, monkeypatch)
    return g


def test_tucks_after_being_idle_and_not_before(ctl, monkeypatch):
    far(ctl, monkeypatch)
    ctl._last_active = time.monotonic(); ctl._tick()
    assert not ctl.tucked
    time.sleep(0.3); ctl._tick()
    assert ctl.tucked


def test_never_tucks_when_the_setting_is_off_or_busy(ctl, monkeypatch):
    far(ctl, monkeypatch)
    ctl.autohide = False; time.sleep(0.3); ctl._tick(); assert not ctl.tucked
    ctl.autohide = True; ctl.keepAwake(5); time.sleep(0.3); ctl._tick(); assert not ctl.tucked


@pytest.mark.parametrize("mode", ["listening", "working", "claudeNeeds", "reminder", "answer", "expanded", "music", "prompter"])
def test_only_idle_or_sleeping_tuck_and_any_activity_untucks(ctl, monkeypatch, mode):
    far(ctl, monkeypatch); time.sleep(0.3); ctl._tick(); assert ctl.tucked
    ctl.setMode(mode)
    assert not ctl.tucked
    ctl._busy_until = 0; ctl._last_active = 0; ctl._tick()
    assert not ctl.tucked, "a non-idle mode must never hide"


def test_wake_brings_it_back(ctl, monkeypatch):
    far(ctl, monkeypatch); time.sleep(0.3); ctl._tick(); assert ctl.tucked
    ctl.wake(); assert not ctl.tucked


def test_top_edge_reveals_it_and_elsewhere_does_not(ctl, monkeypatch):
    g = far(ctl, monkeypatch); time.sleep(0.3); ctl._tick(); assert ctl.tucked
    cursor(g.x() + g.width() // 2, g.y() + 20, monkeypatch); ctl._tick()          # near but not on the edge
    assert ctl.tucked
    cursor(g.x() + 5, g.y() + 2, monkeypatch); ctl._tick()                         # top edge but far to the side
    assert ctl.tucked
    cursor(g.x() + g.width() // 2, g.y() + 2, monkeypatch); ctl._tick()            # the very top, in the middle
    assert not ctl.tucked


def test_sleeping_notch_wakes_when_revealed(ctl, monkeypatch):
    g = far(ctl, monkeypatch); ctl.setMode("sleeping"); time.sleep(0.3); ctl._tick(); assert ctl.tucked
    cursor(g.x() + g.width() // 2, g.y() + 1, monkeypatch); ctl._tick()
    assert not ctl.tucked and ctl.mode in ("idle", "peek")


def test_dragging_moves_it_and_is_clamped_and_saved(ctl, monkeypatch):
    g = QGuiApplication.primaryScreen().geometry(); got = []
    ctl.offsetCommitted.connect(got.append)
    cursor(500, 10, monkeypatch); ctl.dragBegin()
    cursor(560, 10, monkeypatch); ctl.dragMove(); assert ctl.offsetX == 60
    cursor(500 - 10000, 10, monkeypatch); ctl.dragMove()
    assert ctl.offsetX == -ctl.max_offset()                                         # never off the screen
    ctl.dragEnd(); assert got == [-ctl.max_offset()]
    ctl.dragEnd(); assert len(got) == 1                                             # no double save


def test_a_dragged_notch_reveals_at_its_own_place_not_the_centre(ctl, monkeypatch):
    g = QGuiApplication.primaryScreen().geometry()
    monkeypatch.setattr(ctl, "max_offset", lambda: 600)                              # pretend the screen is wide (offscreen is small)
    ctl.setOffsetX(400); off = ctl.offsetX
    cursor(g.x() + g.width() // 2, g.y() + 600, monkeypatch); time.sleep(0.3); ctl._tick(); assert ctl.tucked
    cursor(g.x() + g.width() // 2, g.y() + 1, monkeypatch); ctl._tick()            # old centre: no longer the notch
    assert ctl.tucked
    cursor(g.x() + g.width() // 2 + off, g.y() + 1, monkeypatch); ctl._tick()
    assert not ctl.tucked


def test_reset_position(ctl):
    got = []; ctl.offsetCommitted.connect(got.append)
    ctl.setOffsetX(120); ctl.resetPosition()
    assert ctl.offsetX == 0 and got == [0]


def test_no_drag_means_dragmove_does_nothing(ctl, monkeypatch):
    cursor(900, 10, monkeypatch); ctl.dragMove(); assert ctl.offsetX == 0
