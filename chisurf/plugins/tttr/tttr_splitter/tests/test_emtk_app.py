"""UI-level tests for the EMTK TTTR Split / Convert app.

The split algorithms are covered by test_splitter.py; these drive the app:
what a frame draws, the edit → load flow, and the run/batch progress states.
"""

from __future__ import annotations

import os
import pathlib

import pytest




from emtk.testing import RecordingPainter  # noqa: E402


@pytest.fixture
def tool():
    from chisurf.plugins.tttr.tttr_splitter.gui.controller import SplitterController

    controller = SplitterController()
    yield controller
    controller.app.close()


def test_the_controller_owns_the_native_app(tool):
    assert hasattr(tool.app, "start_guide") and hasattr(tool.app, "show_help")


def test_a_frame_draws_all_three_docks(tool):
    painter = RecordingPainter()
    tool.app.draw(painter, 0.0, 0.0, 900.0, 620.0)

    assert len(painter.calls) > 60
    # Input/Output dock (captions + the run button)…
    assert "Input file:" in painter.strings
    assert "✂ Convert / Split" in painter.strings
    # …options…
    assert "Input format" in painter.strings
    # …and batch panel.
    assert "➕ Files" in painter.strings
    assert any("No files queued" in s for s in painter.strings)


def test_editing_the_input_path_loads_the_file(tool, monkeypatch):
    """Typing a path into the input row runs the loader with it."""
    import emtk.im as im

    loaded: list[str] = []
    real_input = im.input_text_with_hint

    def input_spy(label, value, *a, **k):
        if label == "##Input file":
            return True, "/data/run.ptu"
        return real_input(label, value, *a, **k)

    monkeypatch.setattr(im, "input_text_with_hint", input_spy)
    monkeypatch.setattr(tool, "load_input", lambda p: loaded.append(p))

    with __import__("emtk").frame(RecordingPainter(), (0.0, 0.0, 900.0, 620.0)):
        tool.app.splitter_gui.docks.draw((0.0, 0.0, 900.0, 620.0))

    assert loaded == ["/data/run.ptu"]


def test_load_input_rejects_a_missing_file(tool, monkeypatch):
    tool.load_input("/nowhere/never.ptu")
    assert tool.message == "Could not load /nowhere/never.ptu: file does not exist"
    assert tool._model.input_file == ""


def test_run_progress_and_reason_reach_the_canvas(tool, monkeypatch):
    """A running split shows its percentage; a cannot-split reason shows."""
    # No file loaded → the run reports why instead of splitting.
    tool._run()
    assert tool.message, "the cannot-split reason was not reported"

    # A running state renders the progress bar with its percentage.
    tool.run_running = True
    tool.run_progress = 40
    painter = RecordingPainter()
    tool.app.draw(painter, 0.0, 0.0, 900.0, 620.0)
    assert any("40%" in s for s in painter.strings), painter.strings[:20]


def test_batch_progress_renders_per_file_counts(tool):
    tool._model.batch_files = ["/data/a.ptu", "/data/b.ptu", "/data/c.ptu"]
    tool.batch_progress = (2, 3)
    painter = RecordingPainter()
    tool.app.draw(painter, 0.0, 0.0, 900.0, 620.0)
    assert "2/3" in painter.strings
    # The queued files are listed in the batch table.
    assert "/data/a.ptu" in painter.strings


def test_batch_queue_child_keeps_output_option_below_long_paths(tool, monkeypatch):
    import emtk.im as im

    path = "/data/measurements/very_long_recording_name_with_many_channel_tags.ptu"
    tool._model.batch_files = [path]
    rects = {}
    selectable = im.selectable
    checkbox = im.checkbox

    def track_selectable(label, *args, **kwargs):
        result = selectable(label, *args, **kwargs)
        if label.startswith(path):
            rects["file"] = im.get_item_rect()
        return result

    def track_checkbox(label, *args, **kwargs):
        result = checkbox(label, *args, **kwargs)
        if label == "Output next to each file":
            rects["output"] = im.get_item_rect()
        return result

    monkeypatch.setattr(im, "selectable", track_selectable)
    monkeypatch.setattr(im, "checkbox", track_checkbox)
    tool.app.draw(RecordingPainter(), 0, 0, 900, 620)
    assert rects["output"][1] >= rects["file"][1] + rects["file"][3]


def test_batch_start_without_files_reports(tmp_path, tool, monkeypatch):
    tool._start_batch()
    assert tool.message == "Add PTU files or folders first."


def test_the_view_json_still_loads(tool):
    """The declarative spec stays loadable for the RPC/CLI consumers."""
    assert tool._model.view_spec() is not None


def test_split_options_restore_qt_controls(tool, monkeypatch):
    import emtk.im as im

    seen = []
    real_checkbox = im.checkbox

    def checkbox(label, value, *a, **k):
        seen.append(label)
        result = real_checkbox(label, value, *a, **k)
        return (True, False) if label == "Split into files" else result

    monkeypatch.setattr(im, "checkbox", checkbox)
    tool.app.draw(RecordingPainter(), 0, 0, 900, 620)
    assert {"Split into files", "Reset macro times", "Keep original"} <= set(seen)
    assert tool._model.split_files is False
    assert tool._model.keep_original is True
    assert len(tool.app.splitter_gui.tour.steps) == 4


def test_batch_count_reports_successes_only(monkeypatch):
    from chisurf.plugins.tttr.tttr_splitter.gui.view_model import SplitterViewModel

    model = SplitterViewModel()
    model.batch_files = ["a.ptu", "b.ptu"]
    monkeypatch.setattr("tttrlib.TTTR", lambda *args: object())
    monkeypatch.setattr(model, "set_tttr", lambda *args: None)
    outcomes = iter([False, True])

    def split():
        if not next(outcomes):
            raise RuntimeError("bad container")

    monkeypatch.setattr(model, "do_split", split)
    assert model.run_batch() == 1
