"""Every plot setting reaches a fit plot built after it changed, and chiplot honours grid and text size.

Before: the fit plot took its palette, widths and band from a copy made at import, ignored
"Grid" off and the grid strength, crashed with the band switched off, and the axis text size
reached nothing -- Settings ▸ Plots changed the preview and not one plot.
"""

from __future__ import annotations

import copy
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def plot(monkeypatch):
    import chisurf.core.settings as css

    gui = copy.deepcopy(css.cs_settings.get("gui", {}))
    monkeypatch.setitem(css.cs_settings, "gui", gui)
    return gui.setdefault("plot", {})


def _lineplot(qapp):
    from chisurf.gui.plots.lineplot.lineplot import LinePlot
    from test.gui.test_tcspc_project_visual_roundtrip import _simulated_fit

    page = LinePlot(_simulated_fit())
    page.update()
    return page


def test_curves_take_the_colours_and_width_set_after_import(qapp, plot):
    plot.setdefault("colors", {})["model"] = "#00ff00"
    plot["line_width"] = 4.0
    page = _lineplot(qapp)
    director = page.settings.director
    assert director["model"]["color"] == "#00ff00"
    assert director["model"]["lw"] == 4.0 and director["data"]["lw"] == 2.0


def test_the_band_switched_off_builds_a_plot_with_the_band_hidden(qapp, plot):
    plot["enable_region_selector"] = False
    page = _lineplot(qapp)  # raised AttributeError: 'LinePlot' object has no attribute 'region'
    assert page.region is not None and not page.region.visible  # kept, hidden: switching it on restyles


def test_grid_off_turns_every_panel_grid_off(qapp, plot):
    plot["enable_grid"] = False
    page = _lineplot(qapp)
    for key in ("main_plot", "top_left_plot", "top_right_plot"):
        assert page.plots[key]._canvas._grid is False, key


def test_the_grid_strength_reaches_the_drawn_gridlines(qapp, plot, monkeypatch):
    from emtk.testing import RecordingPainter
    from emtk.widgets import plot as emtk_plot

    from chisurf.gui.chiplot.backends.emtk_backend import EmtkCanvas

    seen = []
    original = emtk_plot.Plot._draw_gridlines

    def spy(self, painter):
        seen.append(self.grid_opacity)
        return original(self, painter)

    monkeypatch.setattr(emtk_plot.Plot, "_draw_gridlines", spy)
    canvas = EmtkCanvas()
    canvas.set_grid(x=True, y=True, alpha=0.15)  # half chiplot's default 0.3
    canvas.draw(RecordingPainter(), 0.0, 0.0, 300.0, 200.0)
    canvas.set_grid(x=True, y=True, alpha=1.0)  # solid
    canvas.draw(RecordingPainter(), 0.0, 0.0, 300.0, 200.0)
    assert seen == [pytest.approx(0.5), pytest.approx(255 / 20)]


def test_the_axis_text_size_scales_the_axis_text(qapp, plot):
    from emtk import fonts
    from emtk.testing import RecordingPainter

    from chisurf.gui.chiplot.backends.emtk_backend import EmtkCanvas

    class Scaling(RecordingPainter):
        def __init__(self):
            super().__init__()
            self.scales = []

        def set_font_scale(self, scale):
            self.scales.append(scale)

    plot["font_size"] = 0
    painter = Scaling()
    EmtkCanvas().draw(painter, 0.0, 0.0, 300.0, 200.0)
    assert painter.scales == []
    plot["font_size"] = 2 * fonts.role_size_pt("ui")
    painter = Scaling()
    EmtkCanvas().draw(painter, 0.0, 0.0, 300.0, 200.0)
    assert painter.scales == [pytest.approx(2.0), 1.0]
