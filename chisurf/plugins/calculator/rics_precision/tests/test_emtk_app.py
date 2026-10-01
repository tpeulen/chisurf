"""Construction and render smoke tests for the EMTK RICS-precision app.

Builds the real window offscreen (import / side-effect regressions), drives the
Qt-free model through one small sweep, and draws the immediate-mode app against
a recording painter — the full EMTK path without a raster.
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
    """Counts the six operations instead of performing them."""

    def __init__(self) -> None:
        self.strings: list[str] = []
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
        return len(string) * 7.0

    def line_height(self) -> float:
        return 12.0

    def set_font(self, font) -> None:
        pass

    def set_font_scale(self, scale) -> None:
        pass


@_needs_qt
def test_the_tool_hosts_the_emtk_app(qapp):
    """The window is a Qt shell around the immediate-mode app."""
    from emtk.qt_host import host_class

    from chisurf.plugins.calculator.rics_precision.gui.tool import RicsPrecisionTool

    tool = RicsPrecisionTool()
    try:
        assert tool.windowTitle() == "RICS precision"
        assert isinstance(tool.host, host_class())
        assert tool.app is tool.host.control
        assert hasattr(tool.app, "start_guide") and hasattr(tool.app, "show_help")
    finally:
        tool.close()


@_needs_qt
def test_one_sweep_flows_through_the_app(qapp):
    """Compute → series/rows → the app draws the verdict and the table."""
    from chisurf.plugins.calculator.rics_precision.gui.tool import RicsPrecisionTool

    tool = RicsPrecisionTool()
    try:
        # A small sweep: the point is the path, not the statistics.
        tool.model.n_images = 10
        tool.model.n_repeats = 5
        assert tool.model.compute(progress=lambda f, t: None)

        series = tool.model.sweep_series()
        rows = tool.model.sweep_rows()
        assert len(rows) == len(tool.model.sweep.dwell)
        # The curve, and the user's own setting marked on it.
        assert len(series) == 2 and series[1]["name"] == "your setting"

        painter = RecordingPainter()
        tool.app.draw(painter, 0.0, 0.0, 900.0, 600.0)
        assert painter.ops > 50, "the app drew nothing"
        assert tool.model.status in painter.strings
    finally:
        tool.close()
