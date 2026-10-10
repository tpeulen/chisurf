"""Code- and UI-level tests for the EMTK k² distribution calculator.

The algorithms are covered by test_algorithms.py; these pin the widget: the
EMTK app renders model state, edits schedule recomputes, and the
backward-compat surface ``kappa2_helpers`` relies on keeps working.
"""

from __future__ import annotations

import numpy as np
import pytest


class RecordingPainter:
    """Counts operations and keeps the strings, instead of drawing."""

    def __init__(self) -> None:
        self.strings: list[str] = []
        self.ops = 0
        self.stroke_widths: list[float] = []

    def _op(self) -> None:
        self.ops += 1

    def fill_rect(self, *a) -> None:
        self._op()

    def stroke_rect(self, *a, width=1.0) -> None:
        self.stroke_widths.append(width)
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


class _Widget:
    """The emtk app with the model handle the tests below read."""

    def __init__(self) -> None:
        from chisurf.plugins.calculator.kappa2_dist.gui.app import make_app

        self.app = make_app()
        self._model = self.app.tool._model


@pytest.fixture
def widget():
    return _Widget()


def test_construction_computes_a_distribution(widget):
    """The first computation leaves real results on the model."""
    assert widget._model.kappa2_true == 0.667
    assert widget._model._k2scale is not None
    assert widget._model._k2hist is not None
    # The assumed k2 must come back as the distribution's mean, +-, for a cone.
    assert widget._model.k2_mean == pytest.approx(widget._model.kappa2_true, abs=0.05)


def test_a_frame_draws_controls_plot_and_results(widget):
    painter = RecordingPainter()
    widget.app.draw(painter, 0.0, 0.0, 900.0, 620.0)

    assert painter.stroke_widths and all(width > 0 for width in painter.stroke_widths)
    assert painter.ops > 150
    assert "r₀ (fund.)" in painter.strings
    assert "Model" in painter.strings
    assert "Mean κ²" in painter.strings
    assert "δ (deg)" in painter.strings
    assert any("true κ²" in s for s in painter.strings)


def test_the_app_has_a_guide_and_help(widget):
    assert hasattr(widget.app, "start_guide") and hasattr(widget.app, "show_help")


def test_compute_now_recomputes_for_the_inputs_as_they_stand(widget):
    """The experimental-k2 dialog reads the result through ``compute_now``."""
    widget._model.model_type = "isotropic"
    widget.app.compute_now()
    assert widget._model._k2hist is not None and np.sum(widget._model._k2hist) > 0


def test_save_writes_the_csv_the_old_writer_wrote(widget, tmp_path):
    """The CSV format (header block + kappa2,probability rows) is unchanged."""
    widget.app.write_csv(tmp_path / "k2.csv")
    text = (tmp_path / "k2.csv").read_text()
    assert "# Kappa2 Distribution" in text
    assert f"# Model: {widget._model.model_type}" in text
    assert "# kappa2,probability" in text
    data_rows = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert len(data_rows) == len(widget._model._k2scale) - 1


def test_save_with_nothing_computed_refuses(widget, tmp_path):
    widget._model._k2scale = None
    widget._model._k2hist = None
    with pytest.raises(ValueError):
        widget.app.write_csv(tmp_path / "none.csv")
    assert not (tmp_path / "none.csv").exists()


def test_declared_window_and_translated_actions_keep_identity(widget, monkeypatch):
    """A translated caption keeps each action's original immediate-mode ID."""
    from emtk.im_core import split_label

    from chisurf.plugins.calculator.kappa2_dist.gui import app as module

    assert widget.app.window_size == (640, 480)
    captions = []
    original = module.im.button
    monkeypatch.setattr(module, "tr", lambda source: "Translated " + source)

    def remember(label, *args, **kwargs):
        captions.append(label)
        return original(label, *args, **kwargs)

    monkeypatch.setattr(module.im, "button", remember)
    widget.app.draw(RecordingPainter(), 0.0, 0.0, 640.0, 480.0)
    assert [split_label(label)[1] for label in captions] == ["Compute", "Save", "Guide", "Help"]
    assert all(split_label(label)[0].startswith("Translated ") for label in captions)
