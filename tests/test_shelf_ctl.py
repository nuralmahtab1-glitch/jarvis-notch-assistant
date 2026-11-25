import os, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtWidgets import QApplication
from app.ui.shelf_ctl import ShelfController, excluded_by_source


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class Sys:
    def __init__(self): self.fg = 111; self.pasted = 0
    def foreground_window(self): return self.fg
    def press_ctrl_v(self): self.pasted += 1


def pump(qapp, s=0.25):
    end = time.time() + s
    while time.time() < end:
        qapp.processEvents(); time.sleep(0.005)


@pytest.fixture
def sh(qapp):
    clip = qapp.clipboard(); clip.clear()
    s = Sys(); c = ShelfController(notch=None, clipboard=clip, system=s)
    return c, clip, s


def copy_text(qapp, clip, text):
    clip.setText(text); pump(qapp)


def test_copying_text_anywhere_lands_on_the_shelf(sh, qapp):
    c, clip, _ = sh
    copy_text(qapp, clip, "buy milk and eggs")
    assert [i["full"] for i in c.items] == ["buy milk and eggs"] and c.count == 1


def test_password_looking_text_is_not_kept(sh, qapp):
    c, clip, _ = sh
    copy_text(qapp, clip, "Tr0ub4dor&3xyzQ!")
    assert c.count == 0


def test_copy_marked_do_not_record_is_ignored(sh, qapp):
    c, clip, _ = sh
    md = QMimeData(); md.setText("my bank pin is 4921 okay")
    md.setData('application/x-qt-windows-mime;value="ExcludeClipboardContentFromMonitorProcessing"', b"\x01\x00\x00\x00")
    assert excluded_by_source(md)
    clip.setMimeData(md); pump(qapp)
    assert c.count == 0
    md2 = QMimeData(); md2.setText("not allowed in history please")
    md2.setData('application/x-qt-windows-mime;value="CanIncludeInClipboardHistory"', b"\x00\x00\x00\x00")
    clip.setMimeData(md2); pump(qapp)
    assert c.count == 0


def test_disabled_shelf_records_nothing_and_clears(sh, qapp):
    c, clip, _ = sh
    copy_text(qapp, clip, "first thing to keep")
    c.set_enabled(False)
    assert c.count == 0
    copy_text(qapp, clip, "second thing not kept"); assert c.count == 0
    c.set_enabled(True); copy_text(qapp, clip, "third thing is kept"); assert c.count == 1


def test_clicking_an_item_copies_it_without_duplicating(sh, qapp):
    c, clip, _ = sh
    copy_text(qapp, clip, "alpha note here"); copy_text(qapp, clip, "beta note here")
    first = c.items[1]["id"]
    clip.setText("something else entirely"); pump(qapp)           # clipboard now holds a third value
    c.copy(first); pump(qapp)
    assert clip.text() == "alpha note here"
    assert c.count == 3 and "Copied" in c.message               # our own write was not re-added as a new copy


def test_paste_sends_ctrl_v_only_to_the_same_window(sh, qapp):
    c, clip, s = sh
    copy_text(qapp, clip, "paste me please")
    c.opened()                                    # shelf opened while window 111 was in front
    c.paste(c.items[0]["id"]); pump(qapp, 0.4)
    assert s.pasted == 1 and c.message == "Pasted"
    s.fg = 999                                    # user switched windows
    c.paste(c.items[0]["id"]); pump(qapp, 0.4)
    assert s.pasted == 1 and "window changed" in c.message


def test_dropped_files_are_parked_and_copy_as_files(sh, qapp, tmp_path):
    c, clip, _ = sh
    f = tmp_path / "plan.docx"; f.write_text("x")
    c.dropUrls([QUrl.fromLocalFile(str(f)).toString(), "https://not-a-file.example/x"])
    assert c.count == 1 and c.items[0]["kind"] == "file" and "Parked 1 file" in c.message
    c.copy(c.items[0]["id"]); pump(qapp)
    assert clip.mimeData().hasUrls() and clip.mimeData().urls()[0].toLocalFile().endswith("plan.docx")


def test_copying_a_file_in_explorer_adds_a_file_item(sh, qapp, tmp_path):
    c, clip, _ = sh
    f = tmp_path / "photo.png"; f.write_text("x")
    md = QMimeData(); md.setUrls([QUrl.fromLocalFile(str(f))])
    clip.setMimeData(md); pump(qapp)
    assert c.items[0]["kind"] == "file" and c.items[0]["title"] == "photo.png"


def test_remove_and_clear(sh, qapp):
    c, clip, _ = sh
    copy_text(qapp, clip, "one more thing"); copy_text(qapp, clip, "and another thing")
    c.remove(c.items[0]["id"]); assert c.count == 1
    c.clear(); assert c.count == 0 and c.message == "Shelf cleared"
