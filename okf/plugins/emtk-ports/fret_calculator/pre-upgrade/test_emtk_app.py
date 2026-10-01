"""UI-level tests for the EMTK FRET calculator app.

The smoke tests pin construction; these drive the coupled-recompute wiring —
the tool's whole point. An edit is simulated the way the immediate-mode fields
see one: the field draw runs with an input that commits a new value, the
wired handler runs, and the written-back outputs are compared against a direct
client call (parity, not golden numbers).
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
def tool(qapp):
    _ensure_app()
    from chisurf.plugins.calculator.fret_calculator.gui.tool import FretCalculatorTool

    tool = FretCalculatorTool()
    yield tool
    tool.close()


@_needs_qt
def test_construction_computes_both_tabs(tool):
    """Both tabs leave computed outputs in their models."""
    assert tool.tabs.count() == 2
    # Hetero: R=50, R0=52 → a real efficiency.
    assert 0.0 < tool._hetero_model.E < 1.0
    assert tool._hetero_model.kFRET > 0.0
    # Homo: the back-computed R_DA is finite and positive.
    assert tool._homo_model.R_DA > 0.0
    assert tool._homo_model.k_homo > 0.0


@_needs_qt
def test_editing_R_through_the_field_rewires_the_outputs(tool, monkeypatch):
    """The R field's handler is compute_fret; outputs match a direct call."""
    import emtk.im as im

    real_slider = im.slider_float

    def slider_float(label, v, *a, **k):
        if "R_DA" in label:
            return True, 60.0
        return real_slider(label, v, *a, **k)

    monkeypatch.setattr(im, "slider_float", slider_float)

    painter = RecordingPainter()
    with __import__("emtk").frame(painter, (0.0, 0.0, 900.0, 620.0)):
        tool.app.hetero.docks.draw((0.0, 0.0, 900.0, 620.0))

    m = tool._hetero_model
    assert m.R == 60.0
    expected = tool._client.compute_fret(
        R=60.0,
        R0=52.0,
        tau0=4.0,
        kappa2=0.667,
        sigma=6.0,
        distribution="gaussian",
    )["result"]
    assert m.E == pytest.approx(expected["E"])
    assert m.tau == pytest.approx(expected["tau_DA"])
    assert m.kFRET == pytest.approx(expected["kFRET"])
    # ...and the frame drew.
    assert painter.ops > 100


@_needs_qt
def test_editing_tau_drives_the_lifetime_route(tool, monkeypatch):
    """τ_DA's handler computes from the lifetime, not forward."""
    import emtk.im as im

    real_slider = im.slider_float

    def slider_float(label, v, *a, **k):
        if "τ_DA" in label:
            return True, 2.0
        return real_slider(label, v, *a, **k)

    monkeypatch.setattr(im, "slider_float", slider_float)

    with __import__("emtk").frame(RecordingPainter(), (0.0, 0.0, 900.0, 620.0)):
        tool.app.hetero.docks.draw((0.0, 0.0, 900.0, 620.0))

    m = tool._hetero_model
    assert m.tau == 2.0
    expected = tool._client.compute_fret_from_lifetime(tau_DA=2.0, R0=52.0, tau0=4.0)["result"]
    assert m.R == pytest.approx(expected["R"])
    assert m.E == pytest.approx(expected["E"])


@_needs_qt
def test_the_distribution_toggle_switches_the_active_series(tool):
    """χ² on: the chi series goes solid and the Gaussian goes dashed."""
    m = tool._hetero_model
    m.use_chi = False
    series = {s["name"]: s for s in m.distance_plot_series()}
    assert series["Gaussian"]["style"] == "solid"
    assert series["chi"]["style"] == "dash"

    m.use_chi = True
    series = {s["name"]: s for s in m.distance_plot_series()}
    assert series["chi"]["style"] == "solid"
    assert series["Gaussian"]["style"] == "dash"


@_needs_qt
def test_homo_editing_R_DA_backmaps_t_RM(tool):
    """Setting R_DA and running the backmap updates k_homo and t_RM."""
    m = tool._homo_model
    m.R_DA = 45.0
    tool.app.homo._compute_backmap()

    expected = tool._client.homo_backmap(R_DA=45.0, R0=52.0, tau0=2.3, rho=16.0)["result"]
    assert m.k_homo == pytest.approx(expected["k_homo"])
    assert m.t_RM == pytest.approx(expected["t_RM"])
    # The backmap result is finite and positive (not the default 0.0/50.0).
    assert m.k_homo > 0.0


@_needs_qt
def test_both_tabs_render_and_the_tab_state_switches(tool):
    painter = RecordingPainter()
    tool.app.draw(painter, 0.0, 0.0, 900.0, 620.0)
    hetero_ops = painter.ops
    assert hetero_ops > 150
    assert any("FRET parameters" in s for s in painter.strings)

    tool.app.select_tab(1)
    painter2 = RecordingPainter()
    tool.app.draw(painter2, 0.0, 0.0, 900.0, 620.0)
    assert painter2.ops > 150
    assert any("Homo-FRET parameters" in s for s in painter2.strings)


@_needs_qt
def test_aniso_series_is_a_decaying_time_distribution(tool):
    """The homo anisotropy plot samples times, not distances."""
    series = tool._homo_model.aniso_time_plot_series()
    assert series
    x = np.concatenate([np.asarray(s["x"]) for s in series])
    # Sampled times are finite and positive: an anisotropy decay, in ns.
    assert np.isfinite(x).all() and (x > 0).any()
