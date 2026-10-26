"""The drawn time-window app, driven with simulated pointer and keyboard events.

Every control (toolbar Process / Clear / Help, the Input section of the workspace's photon
streams with Use selected, the queue with Remove, the duration and output fields, Browse, the
preview and the log) is used the way a person uses it, and each test asserts what the next frame
shows. The Qt tool's Files / Folder / Database buttons and its drop are gone: the input is the
Datasets workspace.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from emtk.events import CONTROL_MODIFIER

from chisurf.plugins.emtk_layout import action_caption
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


def _rows(folder):
    """The workspace's photon streams as the Input section lists them."""
    return [
        {
            "uid": f"u-{n}",
            "name": f"{n}.ptu",
            "kind": "photons",
            "kind_label": "Photons",
            "source": f"{n}.ptu",
            "address": str(folder / f"{n}.ptu"),
            "result_of": "",
        }
        for n in ("a", "b")
    ]


@pytest.fixture
def ui(folder, monkeypatch):
    from chisurf.plugins.tttr.tttr_time_windows.gui.controller import TimeWindowController

    # The rows a session's workspace would hold (the files are one-byte stand-ins, no header).
    monkeypatch.setattr(TimeWindowController, "workspace_input_rows", lambda self: _rows(folder))
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
    while (
        tool.job.running or tool.job.future is not None or tool.process_pending
    ) and time.time() - t0 < limit:
        if tool.job.future is not None:
            try:
                tool.job.future.result(timeout=0.5)
            except Exception:  # noqa: BLE001 - the error is the job's to publish
                pass
        ui.frame()
    ui.frame(2)


def queue_both(ui):
    """Select both workspace rows of the Input section and press Use selected (the ``folder``
    fixture's files; it made their folder the working directory)."""
    ui.app.tool.workspace_input_selection = _rows(Path.cwd())
    ui.click("Use selected")
    settle(ui)


def click_queued(ui, index):
    """Click the queued stream *index* (its name is in the Input table above it, too)."""
    x, y, w, h = ui.app.item_rects[f"file{index}"]
    ui.click((x + w / 2, y + h / 2))


def set_time_window(ui, text):
    x, y, w, h = ui.app.item_rects["time_window"]
    ui.click((x + w / 2, y + h / 2))
    ui.key(ord("A"), "a", CONTROL_MODIFIER)
    ui.type(text)
    ui.enter()
    settle(ui)


# -- the file list ---------------------------------------------------------------------------------------
def test_streams_picked_in_the_input_section_are_queued_and_the_first_previewed(ui):
    assert ui.drawn("Nothing queued: pick photon streams above (or Load example).")
    ui.click("a.ptu")  # a row of the Input section
    ui.click("Use selected")
    settle(ui)
    assert [p.name for p in ui.app.tool._file_paths] == ["a.ptu"]
    assert ui.app.tool._sources == {str(ui.app.tool._file_paths[0]): "u-a"}
    queue_both(ui)
    assert [p.name for p in ui.app.tool._file_paths] == ["a.ptu", "b.ptu"]
    assert ui.drawn("Using a.ptu, b.ptu")
    assert (
        ui.app.time_window_gui.preview_index == 0 and ui.app.tool.preview_data is not None
    )  # the first is previewed


def test_there_is_no_input_dialog_no_drop_and_no_database_button(ui):
    """Files enter ChiSurf through the shell's drop into the workspace, never here."""
    for label in ("Files", "Folder", "Database"):
        assert not ui.drawn(label), label
    for name in ("files_dropped", "on_files_dropped", "on_paths_dropped"):
        assert not hasattr(ui.app, name), name
    assert not hasattr(ui.app.tool, "dataset_picker")


def test_the_output_folder_dialog_closes_with_its_x_and_with_escape(ui):
    ui.click(action_caption("browse"))
    x, y, w, h = ui.app._file_window.box
    ui.click((x + w - 14.0, y + 13.0))
    assert ui.app.tool.dialog is None
    ui.click(action_caption("browse"))
    ui.move((x + w / 2, y + h / 2))
    ui.key(KEY_ESCAPE)
    assert ui.app.tool.dialog is None


def test_clicking_a_file_row_previews_that_file(ui):
    queue_both(ui)
    click_queued(ui, 1)
    settle(ui)
    assert ui.app.time_window_gui.preview_index == 1
    assert ui.drawn("Preview: b.ptu") or ui.app.tool.message == "Preview: b.ptu"
    click_queued(ui, 0)
    settle(ui)
    assert ui.app.time_window_gui.preview_index == 0 and ui.app.tool.message == "Preview: a.ptu"


def test_remove_button_takes_the_previewed_file_off_the_queue(ui):
    ui.click("− Remove")  # nothing queued: nothing happens
    assert ui.app.tool._file_paths == []
    queue_both(ui)
    click_queued(ui, 1)
    settle(ui)
    ui.click("− Remove")
    settle(ui)
    assert [p.name for p in ui.app.tool._file_paths] == ["a.ptu"]
    assert ui.app.tool._sources == {str(ui.app.tool._file_paths[0]): "u-a"}  # b's source went too
    assert ui.app.time_window_gui.preview_index == 0  # the neighbour is previewed now


def test_clear_button_empties_the_queue_the_preview_and_the_log(ui):
    queue_both(ui)
    ui.click("Process")
    settle(ui)
    assert ui.app.tool._log_lines
    ui.click("Clear")
    assert (
        ui.app.tool._file_paths == []
        and ui.app.tool._log_lines == []
        and ui.app.tool.preview_data is None
    )
    assert (
        ui.drawn("Nothing queued: pick photon streams above (or Load example).")
        and ui.drawn("Cleared")
        and ui.drawn("Processing log will appear here…")
    )


# -- the duration and output fields ----------------------------------------------------------------------
def test_time_window_field_takes_typed_text_and_the_preview_follows(ui):
    queue_both(ui)
    ui.client.previews = []
    set_time_window(ui, "25")
    assert ui.app.tool.time_window_ms == 25.0 and ui.drawn("25.000")
    set_time_window(ui, "0")  # the Qt spin box's range
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
    ui.click("Beside each measurement")  # the field's hint
    ui.type("results")
    ui.enter()
    assert ui.app.tool.output_dir_text == "results" and ui.drawn("results")
    ui.key(0x01000003)  # Backspace
    assert ui.app.tool.output_dir_text == "result"


def test_browse_button_chooses_an_output_folder(ui, folder):
    ui.click(action_caption("browse"))
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
    ui.click("Beside each measurement")
    ui.type(str(folder / "out"))
    ui.enter()
    ui.click("Process")
    settle(ui)
    files, window, output = ui.client.analyzed[-1]
    assert (
        [p.name for p in files] == ["a.ptu", "b.ptu"]
        and window == 25.0
        and output == folder / "out"
    )
    assert ui.app.tool.message == "Processing complete"
    assert any(
        line.startswith("Done: 2 file(s), 3 total windows") for line in ui.app.tool._log_lines
    )
    assert ui.drawn("Processing complete") and ui.drawn("3 windows total")
    assert any("Done:" in s for s in ui.strings)  # the log window shows it


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
    assert ui.drawn("Working…") and ui.drawn("Stop")  # the job window
    ui.click("Stop")
    assert app.tool.message.startswith("Stopped publication.")
    client.gate.set()
    settle(ui)
    assert app.tool._last_result is None and not any(
        l.startswith("Done:") for l in app.tool._log_lines
    )
    app.close()


# -- Guide and Help -------------------------------------------------------------------------------------
@pytest.mark.parametrize("nth", [0, 1])
def test_each_help_button_opens_the_help_window(ui, nth):
    ui.click(action_caption("help"), nth)
    # emtk 9753aeb: the help window closes via its title-bar glyph (drawn last).
    assert ui.app.time_window_gui.help_window.open and ui.drawn("×")
    ui.click("×", nth=-1)
    assert not ui.app.time_window_gui.help_window.open


def test_guide_button_starts_the_tour_which_waits_for_each_control(ui):
    tour = ui.app.time_window_gui.tour
    ui.click(action_caption("guide"))
    assert tour.active and ui.drawn("Step 1 of 5: Queue the files") and not tour.awaiting
    tour.start(1)
    ui.frame(2)
    assert tour.awaiting
    ui.click(action_caption("example"))  # the awaited button
    assert not tour.awaiting
    tour.start(2)
    ui.frame(2)
    assert tour.awaiting
    set_time_window(ui, "12")  # the awaited field
    assert not tour.awaiting
    tour.start(4)
    ui.frame(2)
    assert tour.awaiting
    ui.click("Process")  # the awaited button
    assert not tour.awaiting
    ui.click("Close Tour")
    assert not tour.active


def test_the_tour_next_and_prev_buttons_can_be_clicked(ui):
    ui.app.time_window_gui.tour.start(3)
    ui.frame(3)
    ui.click("Next ►")
    assert ui.app.time_window_gui.tour.step_idx == 4
    ui.click("◄ Prev")
    assert ui.app.time_window_gui.tour.step_idx == 3
