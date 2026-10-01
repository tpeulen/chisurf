"""Construction smoke + UI tests for the EMTK TTTR Time-Window tool.

Builds the real window offscreen to catch import / side-effect-on-init
regressions, asserts it reuses the shared ``ChisurfDockTool`` base, and drives
the file queue / preview / processing flow the EMTK app renders.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

try:
    from qtpy import QtWidgets
except ImportError:
    QtWidgets = None  # type: ignore[assignment]

_needs_qt = pytest.mark.skipif(QtWidgets is None, reason="Qt bindings not available")
_needs_offscreen = pytest.mark.skipif(
    os.environ.get("QT_QPA_PLATFORM", "") != "offscreen",
    reason="Set QT_QPA_PLATFORM=offscreen for headless test",
)

#: Keeps the QApplication alive; a locally-created one is garbage-collected
#: before the first widget is built, which aborts the interpreter.
_APP: list = []


def _ensure_app() -> None:
    """Create the offscreen QApplication once and keep a strong reference."""
    _APP[:] = [QtWidgets.QApplication.instance() or QtWidgets.QApplication([])]


@_needs_qt
@_needs_offscreen
def test_tool_constructs_and_reuses_base() -> None:
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import TTTRTimeWindowTool

    _ensure_app()
    tool = TTTRTimeWindowTool()
    try:
        from chisurf.gui.widgets.tools import ChisurfDockTool

        assert isinstance(tool, ChisurfDockTool)
        # the UI is the EMTK app; the window is its Qt host
        assert hasattr(tool.app, "start_guide") and hasattr(tool.app, "show_help")
        assert tool.time_window_ms == 10.0
    finally:
        tool.close()


@_needs_qt
@_needs_offscreen
def test_add_paths_queues_files_and_feeds_the_preview(tmp_path) -> None:
    """Queuing updates _file_paths, the canvas list, and selects a preview."""
    from unittest.mock import MagicMock

    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import TTTRTimeWindowTool

    _ensure_app()
    tool = TTTRTimeWindowTool()
    tool._load_preview = MagicMock(return_value=None)  # skip real TTTR decode
    try:
        f1 = tmp_path / "a.ptu"
        f1.write_bytes(b"x")
        f2 = tmp_path / "b.ht3"
        f2.write_bytes(b"x")
        tool.add_paths([f1, f2])
        assert len(tool._file_paths) == 2
        # The first queued file is selected for the preview automatically…
        assert tool.app.time_window_gui.preview_index == 0
        # …and the preview loader ran for it.
        assert tool._load_preview.called

        tool._clear_all()
        assert len(tool._file_paths) == 0
        assert tool.app.time_window_gui.preview_index == -1
    finally:
        tool.close()


@_needs_qt
def test_supported_path_filter_accepts_tttr_and_rejects_others() -> None:
    """The extension predicate every queue entry passes through."""
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import _is_supported_path

    assert _is_supported_path("/data/run.ptu") is True
    assert _is_supported_path("/data/run.ptu.gz") is True
    assert _is_supported_path("/data/run.txt") is False


@_needs_qt
@_needs_offscreen
def test_unsupported_and_duplicate_drops_are_filtered(tmp_path) -> None:
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import TTTRTimeWindowTool

    _ensure_app()
    tool = TTTRTimeWindowTool()
    try:
        good = tmp_path / "a.ptu"
        good.write_bytes(b"x")
        bad = tmp_path / "a.txt"
        bad.write_bytes(b"x")
        tool.on_paths_dropped([good, bad])
        assert [p.name for p in tool._file_paths] == ["a.ptu"]
        # A second drop of the same file does not duplicate it.
        tool.on_paths_dropped([good])
        assert len(tool._file_paths) == 1
    finally:
        tool.close()


@_needs_qt
@_needs_offscreen
def test_processing_logs_per_file_windows(tmp_path, monkeypatch) -> None:
    """Process runs the client for the queue and logs the outcome."""
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import TTTRTimeWindowTool

    _ensure_app()
    tool = TTTRTimeWindowTool()
    try:
        good = tmp_path / "a.ptu"
        good.write_bytes(b"x")
        tool.add_paths([good])

        out_dir = tmp_path / "out"
        out_dir.mkdir()
        captured: dict = {}

        def fake_analyze(files, time_window_ms, output_dir):
            captured["files"] = [Path(f) for f in files]
            captured["tw"] = time_window_ms
            captured["out"] = output_dir
            return {
                "files": [str(f) for f in files],
                "output_paths": {str(good): str(out_dir / "a.bst")},
                "n_windows": {str(good): 7},
                "metadata": {"output_dir": str(out_dir), "total_windows": 7},
            }

        monkeypatch.setattr(tool._client, "analyze_files", fake_analyze)
        tool._process_all()

        assert captured["files"] == [good]
        assert captured["tw"] == 10.0
        assert captured["out"] is None  # no output folder typed → auto
        assert tool._last_result is not None
        log = "\n".join(tool._log_lines)
        assert "7 total windows" in log
        assert "a.ptu: 7 windows" in log
        # The auto-derived output folder is written back into the field.
        assert tool.output_dir_text == str(out_dir)
    finally:
        tool.close()


@pytest.fixture
def tool():
    _ensure_app()
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import TTTRTimeWindowTool

    tool = TTTRTimeWindowTool()
    yield tool
    tool.close()


@_needs_qt
@_needs_offscreen
def test_processing_without_files_logs_and_does_not_raise(tool) -> None:
    tool._process_all()
    assert any("No TTTR files" in line for line in tool._log_lines)


class RecordingPainter:
    """Counts operations and keeps the strings, instead of drawing."""

    def __init__(self) -> None:
        self.strings: list[str] = []
        self.inf_values: list = []
        self.ops = 0

    def _op(self) -> None:
        self.ops += 1

    def fill_rect(self, *a) -> None:
        self._op()

    def stroke_rect(self, *a) -> None:
        self._op()

    def gradient_rect(self, *a) -> None:
        self._op()

    def fill_triangle(self, *a) -> None:
        self._op()

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        self.strings.append(string)
        self._op()

    def text_rotated(self, *a) -> None:
        self._op()

    def image(self, *a) -> None:
        self._op()

    def push_clip(self, *a) -> None:
        pass

    def pop_clip(self) -> None:
        pass

    def text_width(self, string) -> float:
        return len(str(string)) * 7.0

    def line_height(self) -> float:
        return 12.0

    def set_font(self, font) -> None:
        pass

    def set_font_scale(self, scale) -> None:
        pass


@_needs_qt
@_needs_offscreen
def test_the_preview_draws_the_trace_and_window_boundaries(tool, monkeypatch):
    """With preview data set, one frame draws the trace and its boundaries."""
    import emtk
    import emtk.im as im
    import emtk.implot as implot

    gui = tool.app.time_window_gui
    gui.preview = {
        "counts": [1.0, 5.0, 3.0, 8.0],
        "time_axis": [0.0, 0.01, 0.02, 0.03],
        "time_window_ms": 10.0,  # → boundaries at 0.01, 0.02, 0.03 s
    }

    drawn: dict = {}
    real_inf = implot.plot_inf_lines

    def inf_spy(label, values, *a, **k):
        drawn["boundaries"] = list(values)
        return real_inf(label, values, *a, **k)

    monkeypatch.setattr(implot, "plot_inf_lines", inf_spy)

    painter = RecordingPainter()
    try:
        with emtk.frame(painter, (0.0, 0.0, 600.0, 400.0)):
            if im.begin("w"):
                gui._draw_preview((0.0, 0.0, 600.0, 400.0))
                im.end()
    except Exception as exc:
        raise AssertionError(f"preview draw failed: {exc}")

    # The three window boundaries the preview draws as dashed verticals.
    assert drawn.get("boundaries") == [0.01, 0.02, 0.03]


@_needs_qt
@_needs_offscreen
def test_remove_preview_selects_neighbor_and_clears_last(tool, monkeypatch):
    monkeypatch.setattr(tool, "_load_preview", lambda *a: {"counts": [1], "time_axis": [0]})
    tool.add_paths(["/data/a.ptu", "/data/b.ptu"])
    tool._remove_preview_file()
    assert [p.name for p in tool._file_paths] == ["b.ptu"]
    assert tool.app.time_window_gui.preview_index == 0
    tool._remove_preview_file()
    assert tool.preview_data is None
    assert tool.app.time_window_gui.preview is None
    assert tool.app.time_window_gui.preview_index == -1


@_needs_qt
@_needs_offscreen
def test_folder_queue_recurses_and_filters(tool, tmp_path, monkeypatch):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.ptu.gz").write_bytes(b"x")
    (tmp_path / "a.ht3").write_bytes(b"x")
    (sub / "ignore.txt").write_text("x")
    monkeypatch.setattr(tool, "_load_preview", lambda *a: None)
    monkeypatch.setattr("chisurf.gui.widgets.general.get_directory", lambda **k: (tmp_path, None))
    tool._add_folder_dialog()
    assert [p.name for p in tool._file_paths] == ["a.ht3", "b.ptu.gz"]


@_needs_qt
@_needs_offscreen
def test_help_and_guide_have_real_content(tool):
    gui = tool.app.time_window_gui
    assert len(gui.tour.steps) == 4
    assert all("No documentation" not in str(section) for section in gui.help_window.sections)
