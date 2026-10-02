"""The drawn count-rate app, driven with simulated pointer and keyboard events.

Every control of the Qt tool (the file list with Files / Folder / Database / Remove / Clear / drop,
Calculate, Save, the results table and plot, Help / Guide, the channel editor's section and refresh
controls) is used the way a person uses it, and each test asserts what the next frame shows. The
control -> test list is in REPORT.md.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.controller import create_app
from chisurf.plugins.tttr.tttr_count_rate_analysis.tests.pointer import KEY_ESCAPE, Pointer

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
PTU = REPO / "test" / "data" / "clsm" / "Leica_SP5.ptu"
ALL = {"all": [{"detector_chs": None, "micro_time_range": None, "window_range": None}]}


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("a.ptu", "b.ptu"):
        (tmp_path / name).write_bytes(b"x")
    return tmp_path


@pytest.fixture
def ui(folder):
    app = create_app()
    pointer = Pointer(app)
    yield pointer
    app.close()


def settle(ui, limit=120.0):
    t0 = time.time()
    tool = ui.app.tool
    while tool.job.running and time.time() - t0 < limit:
        if tool.job.future is not None:
            try:
                tool.job.future.result(timeout=0.5)
            except Exception:  # noqa: BLE001
                pass
        ui.frame()
    ui.frame(3)


def add_through_the_dialog(ui, *names):
    ui.click("Add files")
    for name in names:
        ui.click(name)
    ui.click("Open")


def real_state(ui, monkeypatch, folder):
    """The Leica file queued by clicks, with one channel holding every routing channel."""
    import tttrlib

    if not PTU.exists():
        pytest.skip("sample PTU not available")
    (folder / "leica.ptu").symlink_to(PTU)
    routing = [int(c) for c in tttrlib.TTTR(str(PTU)).get_used_routing_channels()]
    channels = {"all": [{"detector_chs": routing, "micro_time_range": None, "window_range": None}]}
    monkeypatch.setattr(ui.app.tool, "channels", lambda: channels)
    add_through_the_dialog(ui, "leica.ptu")


# -- the file list ------------------------------------------------------------------------------------
def test_add_files_button_dialog_cancel_and_open(ui):
    assert ui.drawn("No files queued.")
    ui.click("Add files")
    assert ui.app.tool.dialog is not None and ui.drawn("Cancel") and ui.drawn("Open")
    ui.click("Cancel")
    assert ui.app.tool.dialog is None and ui.app.tool._model.files == []
    add_through_the_dialog(ui, "a.ptu", "b.ptu")
    assert [Path(p).name for p in ui.app.tool._model.files] == ["a.ptu", "b.ptu"]
    assert ui.drawn("a.ptu") and ui.drawn("b.ptu") and not ui.drawn("No files queued.")
    assert ui.drawn("Remove")


def test_the_file_dialog_is_a_window_with_an_x_and_closes_with_escape(ui):
    ui.click("Add files")
    x, y, w, h = ui.app._file_window.box
    assert w < 1200 and h < 800                                                  # not the whole viewport
    ui.click((x + w - 14.0, y + 13.0))                                           # the window's x button
    assert ui.app.tool.dialog is None
    ui.click("Add files")
    ui.move((x + w / 2, y + h / 2))
    ui.key(KEY_ESCAPE)
    assert ui.app.tool.dialog is None


def test_folder_button_queues_a_folder_recursively(ui, folder):
    (folder / "sub").mkdir()
    (folder / "sub" / "c.ht3").write_bytes(b"x")
    (folder / "notes.txt").write_text("no")
    ui.click("Folder…")
    assert ui.app.tool.dialog is not None
    ui.click("Choose")
    assert sorted(Path(p).name for p in ui.app.tool._model.files) == ["a.ptu", "b.ptu", "c.ht3"]


def test_database_button_opens_the_dataset_picker(ui, monkeypatch):
    opened = []
    monkeypatch.setattr(ui.app.tool.dataset_picker, "open", lambda: opened.append(1))
    ui.click("Database…")
    assert opened == [1]


def test_selecting_a_row_enables_remove_and_remove_takes_it_off(ui):
    add_through_the_dialog(ui, "a.ptu", "b.ptu")
    events = []
    ui.app.tool._model.add_observer(events.append)
    ui.click("Remove")                                                           # nothing selected: greyed
    assert len(ui.app.tool._model.files) == 2
    ui.click("a.ptu")
    assert Path(ui.app.count_rate_gui.selected_file).name == "a.ptu"
    ui.click("Remove")
    assert [Path(p).name for p in ui.app.tool._model.files] == ["b.ptu"] and "files" in events
    assert not ui.drawn("a.ptu") and ui.app.count_rate_gui.selected_file is None


def test_right_click_on_a_row_offers_remove_from_queue(ui):
    add_through_the_dialog(ui, "a.ptu", "b.ptu")
    ui.right_click("b.ptu")
    assert ui.drawn("Remove from queue")
    ui.click("Remove from queue")
    assert [Path(p).name for p in ui.app.tool._model.files] == ["a.ptu"]


def test_clear_button_empties_the_queue_and_the_results(ui, monkeypatch, folder):
    real_state(ui, monkeypatch, folder)
    ui.click("Calculate")
    settle(ui)
    assert ui.drawn("6714549")
    ui.click("Clear")
    assert ui.app.tool._model.files == [] and not ui.drawn("6714549") and ui.drawn("No files queued.")
    assert ui.drawn("No results yet — press Calculate.")


# -- Calculate, Save, Stop ----------------------------------------------------------------------------------
def test_calculate_button_fills_the_table_and_the_plot_with_the_qt_tools_row(ui, monkeypatch, folder):
    real_state(ui, monkeypatch, folder)
    assert ui.drawn("press Calculate to draw the count rates")
    ui.click("Calculate")
    settle(ui)
    assert ui.app.tool._model.results_rows()[0]["photons"] == 6714549
    for cell in ("all", "44.72", "0.00", "6714549", "150.137"):                 # the Qt cells' formats
        assert ui.drawn(cell), cell
    assert not ui.drawn("press Calculate to draw the count rates") and ui.drawn("Analyzed 1 files.")


def test_calculate_without_files_says_so(ui):
    ui.click("Calculate")
    assert ui.app.tool.message == "Please load TTTR files first." and ui.drawn("Please load TTTR files first.")


def test_calculate_with_an_unreadable_file_reports_the_reason(ui):
    add_through_the_dialog(ui, "a.ptu")
    ui.click("Calculate")
    settle(ui)
    assert ui.app.tool.message and ui.app.tool._model.results_rows() == []
    assert any(ui.app.tool.message[:20] in s or s in ui.app.tool.message for s in ui.strings if len(s) > 10)


def test_calculate_with_no_detector_channel_asks_for_a_setup(ui, monkeypatch):
    add_through_the_dialog(ui, "a.ptu")
    monkeypatch.setattr(ui.app.tool, "channels", lambda: {})
    ui.click("Calculate")
    assert ui.app.tool.message == "Select or edit a detector setup first." and ui.drawn(ui.app.tool.message)


def test_save_button_before_and_after_a_calculation(ui, monkeypatch, folder):
    ui.click("Save", nth=1)                                                      # the tool's (the editor's setup Save is drawn first)
    assert ui.app.tool.message == "There is no data to save." and ui.app.tool.dialog is None
    real_state(ui, monkeypatch, folder)
    ui.click("Calculate")
    settle(ui)
    ui.click("Save", nth=1)
    assert ui.app.tool.dialog is not None
    ui.click("file name")
    ui.type("rates.txt")
    ui.click("Save", nth=-1)                                                     # the dialog's own Save (drawn last)
    settle(ui)
    lines = (folder / "rates.txt").read_text().splitlines()
    assert lines[0].split("\t")[0] == "Channel" and lines[1] == "all\t44.72\t0.00\t6714549\t150.137"
    assert ui.app.tool.message == f"Saved {folder / 'rates.txt'}" or ui.app.tool.message.startswith("Saved")


def test_stop_analysis_button_discards_the_incomplete_run(folder):
    gate, started = threading.Event(), threading.Event()

    def slow_reader(path):
        started.set()
        assert gate.wait(60)
        raise RuntimeError("never published")

    app = create_app(reader=slow_reader)
    app.tool.channels = lambda: ALL
    ui = Pointer(app)
    add_through_the_dialog(ui, "a.ptu")
    ui.click("Calculate")
    assert started.wait(30)
    ui.frame(3)
    assert ui.drawn("Stop analysis") and ui.drawn("0/1 files")
    ui.click("Stop analysis")
    assert app.tool.message == "Stopped analysis; incomplete results will be discarded."
    gate.set()
    settle(ui)
    assert app.tool._model.results_rows() == []
    app.close()


# -- Guide, Help, drops ------------------------------------------------------------------------------------------
def test_help_button_opens_and_closes_the_help_window(ui):
    ui.click("Help")
    assert ui.app.count_rate_gui.help_window.open and ui.drawn("Close Help")
    ui.click("Close Help")
    assert not ui.app.count_rate_gui.help_window.open


def test_guide_button_starts_the_tour_which_waits_for_each_awaited_button(ui):
    tour = ui.app.count_rate_gui.tour
    ui.click("Guide")
    assert tour.active and tour.awaiting and ui.drawn("Step 1 of 5: Queue the files")
    ui.click("Add files")                                                         # the awaited button
    assert not tour.awaiting
    ui.click("Cancel")
    tour.start(2)
    ui.frame(2)
    assert tour.awaiting
    ui.click("Calculate")
    assert not tour.awaiting
    tour.start(4)
    ui.frame(2)
    assert tour.awaiting
    ui.click("Save", nth=1)
    assert not tour.awaiting
    ui.click("Close Tour")
    assert not tour.active


@pytest.mark.xfail(strict=True, reason="emtk gap: 'Close Tour##tour', '◄ Prev##tour' and 'Next ►##tour' share one id "
                   "(emtk takes only the text after ## as the id), so a click on Prev or Next never fires; see REPORT.md")
def test_the_tour_next_and_prev_buttons_can_be_clicked(ui):
    ui.app.count_rate_gui.tour.start(2)
    ui.frame(3)
    ui.click("Next ►")
    assert ui.app.count_rate_gui.tour.step_idx == 3


def test_a_drop_reaches_the_native_and_the_qt_host(ui, folder, qapp):
    from emtk.app import ControlSurface
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui

    assert ControlSurface(ui.app).on_files_dropped([str(folder)]) is True        # a dropped folder is searched
    assert sorted(Path(p).name for p in ui.app.tool._model.files) == ["a.ptu", "b.ptu"]
    ui.frame(2)
    assert ui.drawn("a.ptu")
    other = create_app()
    host = ControlHost(other)
    host.resize(1200, 800)
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(folder / "b.ptu"))])
    enter = QtGui.QDragEnterEvent(QtCore.QPoint(10, 10), QtCore.Qt.CopyAction, mime,
                                  QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    host.dragEnterEvent(enter)
    assert enter.isAccepted()
    drop = QtGui.QDropEvent(QtCore.QPointF(10, 10), QtCore.Qt.CopyAction, mime,
                            QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    host.dropEvent(drop)
    assert drop.isAccepted() and [Path(p).name for p in other.tool._model.files] == ["b.ptu"]
    other.close()


# -- the channel editor (the shared detector-channel widget) -----------------------------------------------------------
def test_the_editor_section_headers_fold_and_unfold(ui):
    editor = ui.app.tool.channel_editor
    assert ui.drawn("File Type:") and not ui.drawn("Window Name")
    ui.click("▼ TTTR Reading routine")                                             # folds the section
    assert editor.open_sections["reading"] is False and not ui.drawn("File Type:")
    ui.click("▶ TTTR Reading routine")
    assert ui.drawn("File Type:")
    ui.click("▶ PIE Windows")                                                      # folded at first, as in the Qt page
    assert editor.open_sections["windows"] is True and ui.drawn("Window Name")


def test_the_detector_setup_combo_lists_the_setups_and_a_pick_selects_it(ui):
    editor = ui.app.tool.channel_editor
    editor.model.setups = {"Leica": {"detectors": {"green": {"chs": [0], "micro_time_ranges": [[0, 4095]]}},
                                     "windows": {"all": [0, 4095]}}}
    ui.frame(2)
    ui.click("Unsaved")                                                            # the detector setup combo
    assert ui.drawn("Leica")                                                       # the saved setup is listed
    ui.click("Leica")
    assert editor.model.current_name == "Leica" and ui.app.tool.channels() and ui.drawn("Leica")


def test_the_public_check_box_is_available_for_a_saved_setup(ui):
    editor = ui.app.tool.channel_editor
    editor.model.setups = {"Leica": {"detectors": {}, "windows": {}}}
    ui.frame(2)
    ui.click("Public")                                                             # nothing saved is selected: inert
    assert editor.public is False
    ui.click("Unsaved")
    ui.click("Leica")
    ui.click("Public")
    assert editor.public is True
    ui.click("Public")
    assert editor.public is False
