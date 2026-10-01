"""The drawn time-window app, driven with simulated pointer and keyboard events.

Every control of the Qt tool (toolbar Process / Clear / Help, the file list with Files / Folder /
Database / Remove / drop, the duration and output fields, Browse, the preview and the log) is used
the way a person uses it, and each test asserts what the next frame shows. The control -> test
list is in REPORT.md.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from emtk.events import CONTROL_MODIFIER

from chisurf.plugins.tttr.tttr_time_windows.gui.controller import create_app
from chisurf.plugins.tttr.tttr_time_windows.tests.pointer import KEY_ESCAPE, Pointer
from chisurf.plugins.tttr.tttr_time_windows.tests.test_emtk_time_windows_parity import _FakeClient


class _SlowClient(_FakeClient):
    """Analysis that waits for the test: the job window is up while it waits."""

    def __init__(self):
        super().__init__()
        self.gate = threading.Event()
        self.started = threading.Event()

    def analyze_files(self, files, time_window_ms, output_dir=None):
        self.started.set()
        assert self.gate.wait(60)
        return super().analyze_files(files, time_window_ms, output_dir)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("a.ptu", "b.ptu"):
        (tmp_path / name).write_bytes(b"x")
    return tmp_path


@pytest.fixture
def ui(folder):
    client = _FakeClient()
    app = create_app(client=client)
    pointer = Pointer(app)
    pointer.client = client
    yield pointer
    app.close()


def settle(ui, limit=60.0):
    """Frames until the running job is done, as the host draws them."""
    tool = ui.app.tool
    t0 = time.time()
    while (tool.job.running or tool.job.future is not None or tool.process_pending) and time.time() - t0 < limit:
        if tool.job.future is not None:
            try:
                tool.job.future.result(timeout=0.5)
            except Exception:  # noqa: BLE001 - the error is the job's to publish
                pass
        ui.frame()
    ui.frame(2)


def queue_both(ui):
    ui.click("Files")
    ui.click("a.ptu")
    ui.click("b.ptu")
    ui.click("Open")
    settle(ui)


def set_time_window(ui, text):
    x, y, w, h = ui.app.item_rects["time_window"]
    ui.click((x + w / 2, y + h / 2))
    ui.key(ord("A"), "a", CONTROL_MODIFIER)
    ui.type(text)
    ui.enter()
    settle(ui)


# -- the file list ---------------------------------------------------------------------------------------
def test_files_button_opens_the_dialog_cancel_closes_it_and_open_queues_the_picked_files(ui):
    ui.click("Files")
    assert ui.app.tool.dialog is not None and ui.drawn("Cancel")
    ui.click("Cancel")
    assert ui.app.tool.dialog is None and ui.app.tool._file_paths == []
    queue_both(ui)
    assert [p.name for p in ui.app.tool._file_paths] == ["a.ptu", "b.ptu"]
    assert ui.drawn("a.ptu") and ui.drawn("b.ptu") and not ui.drawn("No files queued.")
    assert ui.app.time_window_gui.preview_index == 0 and ui.app.tool.preview_data is not None   # the first is previewed


def test_the_file_dialog_closes_with_its_x_and_with_escape(ui):
    ui.click("Files")
    x, y, w, h = ui.app._file_window.box
    ui.click((x + w - 14.0, y + 13.0))
    assert ui.app.tool.dialog is None
    ui.click("Files")
    ui.move((x + w / 2, y + h / 2))
    ui.key(KEY_ESCAPE)
    assert ui.app.tool.dialog is None


def test_folder_button_queues_the_supported_files_of_a_folder(ui, folder):
    (folder / "sub").mkdir()
    (folder / "sub" / "c.ht3").write_bytes(b"x")
    (folder / "notes.txt").write_text("no")
    ui.click("Folder")
    assert ui.app.tool.dialog is not None
    ui.click("Choose")
    settle(ui)
    assert sorted(p.name for p in ui.app.tool._file_paths) == ["a.ptu", "b.ptu", "c.ht3"]


def test_database_button_opens_the_dataset_picker(ui, monkeypatch):
    from chisurf.emtk.dataset_picker import DatasetPicker

    opened = []
    monkeypatch.setattr(DatasetPicker, "open", lambda self: opened.append(self))
    ui.click("Database")
    assert len(opened) == 1 and ui.app.tool.dataset_picker is opened[0]


def test_clicking_a_file_row_previews_that_file(ui):
    queue_both(ui)
    ui.click("b.ptu")
    settle(ui)
    assert ui.app.time_window_gui.preview_index == 1
    assert ui.drawn("Preview: b.ptu") or ui.app.tool.message == "Preview: b.ptu"
    ui.click("a.ptu")
    settle(ui)
    assert ui.app.time_window_gui.preview_index == 0 and ui.app.tool.message == "Preview: a.ptu"


def test_remove_button_takes_the_previewed_file_off_the_queue(ui):
    ui.click("− Remove")                                                       # nothing queued: nothing happens
    assert ui.app.tool._file_paths == []
    queue_both(ui)
    ui.click("b.ptu")
    settle(ui)
    ui.click("− Remove")
    settle(ui)
    assert [p.name for p in ui.app.tool._file_paths] == ["a.ptu"] and not ui.drawn("b.ptu")
    assert ui.app.time_window_gui.preview_index == 0                           # the neighbour is previewed now


def test_clear_button_empties_the_queue_the_preview_and_the_log(ui):
    queue_both(ui)
    ui.click("Process")
    settle(ui)
    assert ui.app.tool._log_lines
    ui.click("Clear")
    assert ui.app.tool._file_paths == [] and ui.app.tool._log_lines == [] and ui.app.tool.preview_data is None
    assert ui.drawn("No files queued.") and ui.drawn("Cleared") and ui.drawn("Processing log will appear here…")


# -- the duration and output fields ----------------------------------------------------------------------
def test_time_window_field_takes_typed_text_and_the_preview_follows(ui):
    queue_both(ui)
    ui.client.previews = []
    set_time_window(ui, "25")
    assert ui.app.tool.time_window_ms == 25.0 and ui.drawn("25.000")
    set_time_window(ui, "0")                                                    # the Qt spin box's range
    assert ui.app.tool.time_window_ms == 0.001
    set_time_window(ui, "99999999")
    assert ui.app.tool.time_window_ms == 3_600_000.0


def test_time_window_arrows_step_by_one_millisecond(ui):
    x, y, w, h = ui.app.time_window_gui.form.rects["time_window_ms.stepper"]
    start = ui.app.tool.time_window_ms
    ui.click((x + w / 2, y + h * 0.25))
    assert ui.app.tool.time_window_ms == start + 1.0
    ui.click((x + w / 2, y + h * 0.75))
    ui.click((x + w / 2, y + h * 0.75))
    assert ui.app.tool.time_window_ms == start - 1.0


def test_output_folder_field_takes_typed_text(ui):
    ui.click("Auto (derived from first file)")                                 # the field's hint
    ui.type("results")
    ui.enter()
    assert ui.app.tool.output_dir_text == "results" and ui.drawn("results")
    ui.key(0x01000003)                                                          # Backspace
    assert ui.app.tool.output_dir_text == "result"


def test_browse_button_chooses_an_output_folder(ui, folder):
    ui.click("Browse…")
    assert ui.app.tool.dialog is not None
    ui.click("Choose")
    assert ui.app.tool.output_dir_text == str(folder)
    assert ui.drawn(str(folder)) or ui.app.tool.output_dir_text


# -- Process and the job window -------------------------------------------------------------------------
def test_process_button_without_files_says_so_in_the_log(ui):
    ui.click("Process")
    assert ui.app.tool._log_lines == ["No TTTR files to process. Add files first."]
    assert ui.drawn("No TTTR files to process. Add files first.")
    assert ui.client.analyzed == []


def test_process_button_runs_the_analysis_with_the_typed_settings_and_logs_the_windows(ui, folder):
    queue_both(ui)
    set_time_window(ui, "25")
    ui.click("Auto (derived from first file)")
    ui.type(str(folder / "out"))
    ui.enter()
    ui.click("Process")
    settle(ui)
    files, window, output = ui.client.analyzed[-1]
    assert [p.name for p in files] == ["a.ptu", "b.ptu"] and window == 25.0 and output == folder / "out"
    assert ui.app.tool.message == "Processing complete"
    assert any(line.startswith("Done: 2 file(s), 3 total windows") for line in ui.app.tool._log_lines)
    assert ui.drawn("Processing complete") and ui.drawn("3 windows total")
    assert any("Done:" in s for s in ui.strings)                                # the log window shows it


def test_a_failing_process_is_shown_on_the_status_line_after_the_click(folder):
    client = _FakeClient(fail_analyze=True)
    app = create_app(client=client)
    ui = Pointer(app)
    queue_both(ui)
    ui.click("Process")
    settle(ui)
    assert ui.drawn("Processing failed") and any("analysis broke" in s for s in ui.strings)
    app.close()


def test_stop_button_discards_the_running_job(folder):
    client = _SlowClient()
    app = create_app(client=client)
    ui = Pointer(app)
    queue_both(ui)
    ui.click("Process")
    assert client.started.wait(30)
    ui.frame(3)
    assert ui.drawn("Working…") and ui.drawn("Stop")                            # the job window
    ui.click("Stop")
    assert app.tool.message.startswith("Stopped publication.")
    client.gate.set()
    settle(ui)
    assert app.tool._last_result is None and not any(l.startswith("Done:") for l in app.tool._log_lines)
    app.close()


# -- Guide and Help -------------------------------------------------------------------------------------
@pytest.mark.parametrize("nth", [0, 1])
def test_each_help_button_opens_the_help_window(ui, nth):
    ui.click("Help", nth)
    assert ui.app.time_window_gui.help_window.open and ui.drawn("Close Help")
    ui.click("Close Help")
    assert not ui.app.time_window_gui.help_window.open


def test_guide_button_starts_the_tour_which_waits_for_each_control(ui):
    tour = ui.app.time_window_gui.tour
    ui.click("Guide")
    assert tour.active and ui.drawn("Step 1 of 5: Queue the files") and tour.awaiting
    ui.click("Files")                                                           # the awaited button
    assert not tour.awaiting
    ui.click("Cancel")
    tour.start(1)
    ui.frame(2)
    assert tour.awaiting
    set_time_window(ui, "12")                                                   # the awaited field
    assert not tour.awaiting
    tour.start(4)
    ui.frame(2)
    assert tour.awaiting
    ui.click("Process")                                                         # the awaited button
    assert not tour.awaiting
    ui.click("Close Tour")
    assert not tour.active


@pytest.mark.xfail(strict=True, reason="emtk gap: 'Close Tour##tour', '◄ Prev##tour' and 'Next ►##tour' share one id "
                   "(emtk takes only the text after ## as the id), so a click on Prev or Next never fires; see REPORT.md")
def test_the_tour_next_and_prev_buttons_can_be_clicked(ui):
    ui.app.time_window_gui.tour.start(2)
    ui.frame(3)
    ui.click("Next ►")
    assert ui.app.time_window_gui.tour.step_idx == 3
    ui.click("◄ Prev")
    assert ui.app.time_window_gui.tour.step_idx == 2


# -- drops on the hosts -------------------------------------------------------------------------------------
def test_a_drop_reaches_the_native_and_the_qt_host(ui, folder, qapp):
    from emtk.app import ControlSurface
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui

    assert ControlSurface(ui.app).on_files_dropped([str(folder / "a.ptu")]) is True
    assert [p.name for p in ui.app.tool._file_paths] == ["a.ptu"]
    other = create_app(client=_FakeClient())
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
    assert drop.isAccepted() and [p.name for p in other.tool._file_paths] == ["b.ptu"]
    other.close()
