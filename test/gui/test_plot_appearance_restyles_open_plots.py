"""Changing a plot setting restyles every plot that is already open -- no re-plot, no new window.

Before: Settings > Plots wrote the setting and told nobody. A fit window opened earlier kept its
colours, widths, grid, band, legend and axis names until the fit was re-plotted (or the window was
reopened). The fix is one notification (``appearance.notify``) that every plot page subscribes to
(``plotbase.Plot.restyle``); this test is the invariant over *every* setting of the panel.
"""

from __future__ import annotations

import copy
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

#: Settings that style node graphs, not plots: they have their own subscriber
#: (``style_settings.refresh_open_graphs``, run by ``flush``), tested with the node editor.
NODE_GRAPH_FIELDS = {
    "ng_show_grid",
    "ng_line_width",
    "ng_grid_opacity_pct",
    "ng_grid_spacing",
    "ng_node_size",
}


@pytest.fixture
def model(monkeypatch, tmp_path):
    """A settings panel model on a private copy of the live ``gui`` settings."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path))
    import chisurf.core.settings as css
    from chisurf.plugins.core.plot_settings.gui.model import PlotSettingsModel

    monkeypatch.setitem(css.cs_settings, "gui", copy.deepcopy(css.cs_settings.get("gui", {})))
    return PlotSettingsModel(persist=False)


@pytest.fixture
def page(qapp, model):
    """An open fit plot, drawn once, as a fit window holds it."""
    from chisurf.gui.plots.lineplot.lineplot import LinePlot
    from test.gui.test_tcspc_project_visual_roundtrip import _simulated_fit

    plot = LinePlot(_simulated_fit())
    plot.update()
    yield plot
    plot.close()


def _line(page, key):
    return page.lines[key]


def _rgb(hex_color):
    from chisurf.core.plotting import appearance

    return appearance.hex_rgb(hex_color)


def _canvas(page, key):
    return page.plots[key]._canvas


#: Per field: (new value, what the open plot must show afterwards -> hashable observation).
#: ``seen(page)`` reads the drawn state straight from the chiplot handles.
OBSERVE = {
    "color_data": ("#112233", lambda p: tuple(_line(p, "data").state["color"])),
    "color_model": ("#223344", lambda p: tuple(_line(p, "model").state["color"])),
    "color_irf": ("#334455", lambda p: tuple(_line(p, "IRF").state["color"])),
    "color_residuals": (
        "#445566",
        lambda p: tuple(_line(p, "weighted residuals").state["color"]),
    ),
    "color_auto_corr": (
        "#556677",
        lambda p: tuple(_line(p, "autocorrelation").state["color"]),
    ),
    "line_width": (5.0, lambda p: _line(p, "model").state["width"]),
    "enable_region_selector": (False, lambda p: p.region.visible),
    "color_region_selector": ("#778899", lambda p: tuple(p.region.state["brush"][:3])),
    "region_alpha": (200, lambda p: p.region.state["brush"][3]),
    "label_axis": (False, lambda p: _canvas(p, "main_plot")._labels.get("left", "")),
    "show_legend": (False, lambda p: _canvas(p, "main_plot")._legend),
    "font_size": (17, lambda p: __import__("chisurf.core.plotting.appearance").core.plotting.appearance.font_size()),
    "enable_grid": (False, lambda p: _canvas(p, "main_plot")._grid),
    "grid_alpha_pct": (90, lambda p: _canvas(p, "main_plot")._grid_strength),
    "show_data_grid": (False, lambda p: _canvas(p, "main_plot")._grid),
    "show_residual_grid": (False, lambda p: _canvas(p, "top_left_plot")._grid),
    "show_acorr_grid": (False, lambda p: _canvas(p, "top_right_plot")._grid),
}


def test_every_plot_setting_is_observed_or_declared_out_of_scope():
    """A new field of the settings panel must be added to the invariant above or the node-graph set."""
    from chisurf.plugins.core.plot_settings.gui.model import PlotSettingsModel

    fields = set(PlotSettingsModel.fields())
    handled = set(OBSERVE) | NODE_GRAPH_FIELDS | {"active_transparency", "inactive_transparency"}
    assert fields == handled, sorted(fields ^ handled)


@pytest.mark.parametrize("field", sorted(OBSERVE))
def test_changing_a_setting_restyles_the_open_plot_without_a_replot(model, page, field):
    value, seen = OBSERVE[field]
    before = seen(page)
    setattr(model, field, value)  # the panel writes the setting; nothing re-plots
    after = seen(page)
    assert after != before, f"{field}: the open plot still shows {before!r}"


def test_the_colour_is_the_one_that_was_set(model, page):
    model.color_model = "#00ff00"
    assert tuple(_line(page, "model").state["color"]) == (0, 255, 0)


def test_the_selected_fit_opacity_reaches_the_open_group_plot(model, page):
    """Active and inactive fit opacity restyle the lines of a grouped plot."""
    line = next(
        line for line, look in page._looks.values() if look["group_index"] is not None
    ) if any(look["group_index"] is not None for _l, look in page._looks.values()) else None
    if line is None:
        page.settings.display_group = True
        page.update()
        line = next(line for line, look in page._looks.values() if look["group_index"] is not None)
    model.active_transparency = 0.25
    assert line.state["opacity"] == pytest.approx(0.25)


def test_reset_to_defaults_restyles_the_open_plot_too(model, page):
    model.line_width = 7.0
    assert _line(page, "model").state["width"] == 7.0
    model.reset_defaults()
    assert _line(page, "model").state["width"] == 2.0


def test_a_closed_plot_is_no_longer_restyled(model, page):
    page.close()
    model.line_width = 3.5
    assert _line(page, "model").state["width"] != 3.5


def test_a_dropped_plot_does_not_keep_the_subscriber_list_alive(model, qapp):
    import gc

    from chisurf.core.plotting import appearance
    from chisurf.gui.plots.lineplot.lineplot import LinePlot
    from test.gui.test_tcspc_project_visual_roundtrip import _simulated_fit

    count = len(appearance._subscribers)
    plot = LinePlot(_simulated_fit())
    assert len(appearance._subscribers) == count + 1
    del plot
    gc.collect()
    model.line_width = 3.5  # notify prunes the dead entry
    assert len(appearance._subscribers) == count


def test_the_residual_page_restyles_too(qapp, model):
    from chisurf.gui.plots.wr_plot import ResidualPlot
    from test.gui.test_tcspc_project_visual_roundtrip import _simulated_fit

    plot = ResidualPlot(_simulated_fit())
    try:
        model.line_width = 6.0
        assert all(curve.state["width"] == 6.0 for curve in plot.curves)
    finally:
        plot.close()


def test_the_distribution_page_restyles_too(qapp, model):
    from chisurf.gui.plots.distribution import DistributionPlot
    from chisurf.gui.widgets.models.model_editor import model_plot_specs
    from test.gui.test_classic_tcspc_editor import _fit

    fit, tcspc_model = _fit("tcspc_fret_acceptor_density")
    tcspc_model.update()
    options = next(o for c, o in model_plot_specs(tcspc_model) if c is DistributionPlot)
    page = DistributionPlot(fit, **options)
    page.update()
    try:
        model.line_width = 6.0
        model.color_data = "#102030"
        curve = page.distribution_curve
        assert curve.state["width"] == 6.0 and tuple(curve.state["color"]) == (16, 32, 48)
        model.enable_grid = False
        assert page.distribution_plot._canvas._grid is False
    finally:
        page.close()
