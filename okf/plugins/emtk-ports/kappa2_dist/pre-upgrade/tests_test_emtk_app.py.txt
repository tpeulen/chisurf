"""Code- and UI-level tests for the EMTK k² distribution calculator.

The algorithms are covered by test_algorithms.py; these pin the widget: the
EMTK app renders model state, edits schedule recomputes, and the
backward-compat surface ``kappa2_helpers`` relies on keeps working.
"""

from __future__ import annotations

import os

import numpy as np
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
def widget(qapp):
    _ensure_app()
    from chisurf.plugins.calculator.kappa2_dist.gui.tool import Kappa2Dist

    widget = Kappa2Dist()
    yield widget
    widget.close()


@_needs_qt
def test_construction_computes_a_distribution(widget):
    """The constructor's initial compute leaves real results on the model."""
    assert widget.kappa2 == 0.667
    assert widget._model._k2scale is not None
    assert widget._model._k2hist is not None
    # The assumed κ² must come back as the distribution's mean, ±, for a cone.
    assert widget._model.k2_mean == pytest.approx(widget._model.kappa2_true, abs=0.05)


@_needs_qt
def test_the_window_hosts_the_emtk_app(widget):
    from emtk.qt_host import host_class

    assert isinstance(widget.host, host_class())
    assert widget.app is widget.host.control
    assert hasattr(widget.app, "start_guide") and hasattr(widget.app, "show_help")


@_needs_qt
def test_a_frame_draws_controls_plot_and_results(widget):
    painter = RecordingPainter()
    widget.app.draw(painter, 0.0, 0.0, 900.0, 620.0)

    assert painter.ops > 150
    # Controls…
    assert "r₀ (fund.)" in painter.strings
    assert "Model" in painter.strings
    # …results (the statistics table)…
    assert "Mean κ²" in painter.strings
    assert "δ (deg)" in painter.strings
    # …and the assumed-κ² marker on the plot.
    assert any("true κ²" in s for s in painter.strings)


@_needs_qt
def test_an_edit_schedules_a_debounced_recompute(widget, qtbot):
    """A parameter edit goes through the 50 ms debounce, as before."""
    assert widget._model._k2scale is not None  # computed at construction

    widget._model.step = 2.0
    widget.app.kappa2_gui._schedule_compute()
    assert widget._compute_timer.isActive()
    qtbot.wait(150)
    assert not widget._compute_timer.isActive()
    # The recomputation ran with the edited step and still succeeded.
    assert widget._model._k2scale is not None


@_needs_qt
def test_the_model_radio_shims_drive_the_model(widget):
    """``radioButton_2`` / ``radioButton`` / ``radioButton_iso`` still work."""
    assert widget.radioButton_2.isChecked()  # "cone" is the default
    assert not widget.radioButton.isChecked()

    widget.radioButton.setChecked(True)
    assert widget._model.model_type == "diffusion"
    assert widget.radioButton.isChecked()
    assert not widget.radioButton_2.isChecked()
    # setChecked recomputes: the histogram is present for the new model.
    assert widget._model._k2hist is not None and np.sum(widget._model._k2hist) > 0

    widget.radioButton_iso.setChecked(True)
    assert widget._model.model_type == "isotropic"


@_needs_qt
def test_backward_compat_properties_read_the_model(widget):
    assert widget.k2scale is widget._model._k2scale
    assert widget.k2hist is widget._model._k2hist
    widget.k2_mean = 0.5
    assert widget._model.k2_mean == 0.5
    widget.onUpdateHist()
    assert widget.k2scale is widget._model._k2scale


@_needs_qt
def test_save_writes_the_csv_the_old_writer_wrote(widget, tmp_path, monkeypatch):
    """The CSV format (header block + kappa2,probability rows) is unchanged."""
    calls: list = []
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "k2.csv"), "")),
    )
    monkeypatch.setattr("chisurf.gui.dialogs.information", lambda *a, **k: calls.append(a))
    widget._on_save()

    text = (tmp_path / "k2.csv").read_text()
    assert "# Kappa2 Distribution" in text
    assert f"# Model: {widget._model.model_type}" in text
    assert "# kappa2,probability" in text
    data_rows = [l for l in text.splitlines() if l and not l.startswith("#")]
    assert len(data_rows) == len(widget._model._k2scale) - 1
    assert calls, "the success dialog was not shown"


@_needs_qt
def test_save_with_nothing_computed_warns(widget, tmp_path, monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "none.csv"), "")),
    )
    monkeypatch.setattr("chisurf.gui.dialogs.warning", lambda *a, **k: calls.append(a))
    widget._model._k2scale = None
    widget._model._k2hist = None
    widget._on_save()
    assert calls, "the nothing-to-save warning was not shown"
    assert not (tmp_path / "none.csv").exists()
