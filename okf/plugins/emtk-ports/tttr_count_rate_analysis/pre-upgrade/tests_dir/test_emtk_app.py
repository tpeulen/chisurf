"""UI-level tests for the EMTK Count Rate Analysis app.

The model compute/export is covered by test_widgets.py (against a real PTU);
these drive the app: what a frame draws, the channel source wiring, and the
results table.
"""

from __future__ import annotations

import os

import pytest

try:
    from qtpy import QtWidgets
except ImportError:
    QtWidgets = None  # type: ignore[assignment]

_needs_qt = pytest.mark.skipif(QtWidgets is None, reason="Qt bindings not available")

_APP: list = []


def _ensure_app():
    _APP[:] = [QtWidgets.QApplication.instance() or QtWidgets.QApplication([])]


class RecordingPainter:
    """Counts operations and keeps the strings, instead of drawing."""

    def __init__(self) -> None:
        self.strings: list[str] = []
        self.tooltips: list[str] = []
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


@pytest.fixture
def tool(qapp):
    _ensure_app()
    from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.tool import CountRateAnalyzer

    tool = CountRateAnalyzer()
    yield tool
    tool.close()


@_needs_qt
def test_the_window_hosts_the_emtk_app(tool):
    from emtk.qt_host import host_class

    assert isinstance(tool.host, host_class())
    assert tool.app is tool.host.control
    assert callable(tool._model.channels_provider)


@_needs_qt
def test_a_frame_draws_all_four_docks(tool):
    painter = RecordingPainter()
    tool.app.draw(painter, 0.0, 0.0, 900.0, 620.0)

    assert painter.ops > 60
    assert "Add files" in painter.strings
    assert "Detector setup:" in painter.strings
    assert "Calculate" in painter.strings
    assert any("No results yet" in s for s in painter.strings)


@_needs_qt
def test_the_channel_source_converts_a_saved_setup(tool, monkeypatch):
    """The selected setup's detectors become the model's channel map."""
    monkeypatch.setattr(
        tool,
        "available_setups",
        lambda: {
            "PIE-MFD": {
                "detectors": {
                    "green": {"chs": [0], "micro_time_ranges": [[100, 2000]]},
                    "red": {"chs": [1, 9], "micro_time_ranges": [[100, 2000]]},
                }
            }
        },
    )
    tool.selected_setup = "PIE-MFD"

    channels = tool.channels()
    assert set(channels) == {"green", "red"}
    assert channels["green"][0]["detector_chs"] == [0]
    assert channels["green"][0]["micro_time_range"] == [100, 2000]
    # The injected provider feeds the model the same map.
    assert tool._model.channels_provider() == channels


@_needs_qt
def test_computed_results_render_in_the_table_and_plot(tool, monkeypatch):
    """After a compute, the results table and the plot show the channels."""
    tool._model.files = ["/data/a.ptu"]
    # Bypass the real TTTR decode: inject results the way compute would.
    tool._model._per_file = {"/data/a.ptu": {"green": 5000.0, "red": 4500.0}}
    tool._model._per_file_photons = {"/data/a.ptu": {"green": 100, "red": 90}}
    tool._model._meas_times = {"/data/a.ptu": 0.02}
    tool._model._channel_order = ["green", "red"]
    tool._model.notify("computed")

    painter = RecordingPainter()
    tool.app.draw(painter, 0.0, 0.0, 900.0, 620.0)

    assert "green" in painter.strings
    assert "red" in painter.strings
    # Mean kHz of 5000 counts/s = 5.00
    assert "5.00" in painter.strings


@_needs_qt
def test_calculate_without_files_reports(tool, monkeypatch):
    warnings: list = []
    monkeypatch.setattr("chisurf.gui.dialogs.warning", lambda *a, **k: warnings.append(a))
    tool._calculate()
    assert warnings, "the cannot-calculate warning was not shown"


@_needs_qt
def test_save_without_results_reports(tool, monkeypatch):
    warnings: list = []
    monkeypatch.setattr("chisurf.gui.dialogs.warning", lambda *a, **k: warnings.append(a))
    tool._save()
    assert warnings, "the no-data warning was not shown"


@_needs_qt
def test_the_frame_carries_tooltips(tool):
    """The house rule: controls carry tooltips."""
    import emtk.im as im

    tooltips: list[str] = []
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(im, "set_item_tooltip", lambda s: tooltips.append(str(s)))
    try:
        painter = RecordingPainter()
        tool.app.draw(painter, 0.0, 0.0, 900.0, 620.0)
    finally:
        monkeypatch.undo()
    assert len(tooltips) >= 6, tooltips
