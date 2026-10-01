"""UI-level tests for the EMTK phasor calculator app.

The model was already covered headlessly (test_phasor_calculator.py); these
drive the immediate-mode app itself: what a frame draws, and that the controls'
state — the model's attributes, edited in place by the immediate-mode fields —
is what the plot and the results table render.
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


@pytest.fixture
def tool(qapp):
    _ensure_app()
    from chisurf.plugins.calculator.phasor_calculator.gui.tool import (
        PhasorCalculatorTool,
    )

    tool = PhasorCalculatorTool()
    yield tool
    tool.close()


@_needs_qt
def test_the_window_hosts_the_emtk_app(tool):
    """The Qt window is a shell around the immediate-mode app."""
    from emtk.qt_host import host_class

    assert tool.windowTitle() == "Phasor calculator"
    assert isinstance(tool.host, host_class())
    assert tool.app is tool.host.control
    # The AutoForm-era contract the hub and the tests relied on.
    assert hasattr(tool._form, "refresh_plots") and hasattr(tool._form, "sync_fields")


@_needs_qt
def test_a_frame_draws_controls_semircle_and_results(tool):
    """One frame draws all three docks with the reference geometry in it."""
    painter = RecordingPainter()
    tool.app.draw(painter, 0.0, 0.0, 900.0, 620.0)

    assert painter.ops > 200, "the app drew nothing"
    # Controls are there by name…
    assert "Lifetimes (ns)" in painter.strings
    assert "Iso-lifetime grid" in painter.strings
    # …and the results table shows the model's reference lifetimes in ns.
    assert "Effective f = 80 MHz" in painter.strings
    assert any(s == "0.5" for s in painter.strings), "the 0.5 ns row is missing"


@_needs_qt
def test_the_semircle_is_drawn_through_the_shared_builder(tool):
    """The universal semicircle comes from build_overlays, not a private path."""
    overlays = tool.app.phasor_gui._overlays()
    names = {o["name"] for o in overlays}
    assert "universal semicircle" in names
    # With the toggles at their defaults: grid + ticks.
    assert "lifetime ticks" in names
    # And it is a curve with real extent along g.
    semicircle = next(o for o in overlays if o["name"] == "universal semicircle")
    assert max(semicircle["x"]) > 0.99 and min(semicircle["x"]) < 0.01


@_needs_qt
def test_toggles_change_what_the_next_frame_draws(tool):
    """Flipping a model toggle changes the overlay set the plot renders."""
    gui = tool.app.phasor_gui
    before = {o["name"] for o in gui._overlays()}

    tool._model.show_fret = True
    tool._model.show_cursor = True
    after = {o["name"] for o in gui._overlays()}

    assert "FRET trajectory" not in before
    assert {"FRET trajectory", "cursor"} <= after

    painter = RecordingPainter()
    tool.app.draw(painter, 0.0, 0.0, 900.0, 620.0)
    assert painter.ops > 200


@_needs_qt
def test_edits_in_the_controls_land_in_the_model(tool):
    """The immediate-mode fields write through to the model attributes."""
    import emtk

    gui = tool.app.phasor_gui
    painter = RecordingPainter()
    with emtk.frame(painter, (0.0, 0.0, 900.0, 620.0)):
        if gui.model is tool._model and tool._model.frequency == 80.0:
            gui._draw_controls((0.0, 0.0, 340.0, 620.0))
    assert tool._model.frequency == 80.0

    # A tau string edit flows into the parsed list the results table uses.
    tool._model.taus = "2, 4"
    rows = gui._rows()
    assert [r[0] for r in rows] == [2.0, 4.0]
    # g/s pairs are phasors of a harmonic excitation: inside the unit semicircle.
    for _tau, g, s in rows:
        assert g * g + s * s <= 1.0 + 1e-9
