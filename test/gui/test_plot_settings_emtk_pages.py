"""Distribution, parameter scan and 2D residual pages: Qt-free, settings drawn by emtk.

Each page is a plain object; its *Plot settings* are a view spec drawn by
``emtk.view_form`` over the page. These drive the settings the way the form
does (``setattr`` / the named action) and check that the plot follows, then
draw the form headlessly so a spec the renderer cannot read fails here.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _draw_settings(page, width=440.0, height=640.0):
    """Draw the page's settings once on an emtk surface; return the form's field names."""
    from emtk import im
    from emtk.app import ImApp
    from emtk.testing import RecordingPainter

    def gui():
        im.begin("##s", (0.0, 0.0, width, height), flags=im.WindowFlags.NO_TITLE_BAR)
        page.draw_settings()
        im.end()

    app = ImApp(gui)
    for _ in range(2):
        app.draw(RecordingPainter(), 0, 0, width, height)
    return set(page.settings_form.rects)


def _no_qt(module) -> None:
    import inspect

    source = inspect.getsource(module)
    assert "QtWidgets" not in source and "QtCore" not in source and "qtpy" not in source


@pytest.fixture
def quadratic_fit():
    import chisurf.core.data
    import chisurf.core.fitting.fit
    import chisurf.core.models.parse

    rng = np.random.default_rng(0)
    x = np.linspace(1.0, 2.0, 96)
    y = 1.0 + 2.0 * x + 0.5 * x**2 + rng.normal(0.0, 0.02, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, 0.02))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = "c+a*x+b*x**2"
    fit.model.find_parameters()
    fit.run()
    return fit


def test_the_parameter_scan_settings_drive_the_scan(qapp, quadratic_fit):
    import chisurf.gui.plots.parameter_scan.parameter_scan as module

    _no_qt(module)
    page = module.ParameterScanPlot(quadratic_fit)
    assert page.parameter_names() and page.parameter_name in page.parameter_names()
    fields = _draw_settings(page)
    assert {"parameter_name", "scan_lower", "scan_upper", "scan_steps", "p_values",
            "bound_range", "scan_parameter", "smart_scan_parameter",
            "refresh_parameters"} <= fields
    page.parameter_name = "a"
    page.scan_steps = 7
    page.scan_parameter()
    x, chi2 = page.parameter.parameter_scan
    assert len(x) == 7 and np.isfinite(chi2).all()
    page.p_values = "0.5; nonsense, 0.9"
    assert page._p_value_levels() == (0.5, 0.9)
    page.p_values = "junk"
    assert page._p_value_levels() == module.P_VALUE_LEVELS
    assert page.p_values == "0.68, 0.95, 0.99"
    state = page.get_settings_state()
    other = module.ParameterScanPlot(quadratic_fit)
    other.set_settings_state(state)
    assert other.get_settings_state() == state


def test_the_distribution_options_are_a_generated_form(qapp):
    import chisurf.gui.plots.distribution as module

    _no_qt(module)
    data = {"attribute": "fit", "accessor_kwargs": {"sort": False},
            "curve_options": {"stepMode": False, "connect": "all", "symbol": ["o", "x"],
                              "width": 2.0}}
    changed = []
    form = module.OptionsForm(data, lambda: changed.append(1))
    assert "curve_options.stepMode" in str(form.spec())
    setattr(form, "curve_options.connect", "pairs")
    assert data["curve_options"]["connect"] == "pairs" and changed
    getattr(form, "reset:curve_options.connect")()
    assert data["curve_options"]["connect"] == "all"
    setattr(form, "first:curve_options.symbol", "x")
    assert data["curve_options"]["symbol"] == ["x", "o"]
    assert "stepMode" in str(form.spec("step")) and "connect" not in str(form.spec("step"))


def test_the_distribution_page_reads_its_settings(qapp):
    from chisurf.gui.plots.distribution import DistributionPlot
    from test.gui.test_classic_tcspc_editor import _fit  # noqa: PLC0415

    fit, model = _fit("tcspc_fret_acceptor_density")
    model.update()
    from chisurf.gui.widgets.models.model_editor import model_plot_specs

    options = next(o for c, o in model_plot_specs(model) if c is DistributionPlot)
    page = DistributionPlot(fit, **options)
    page.update()
    fields = _draw_settings(page)
    assert {"distribution_type", "show_gaussians"} <= fields
    assert any(name.startswith("accessor_kwargs.") or name.startswith("curve_options.")
               or name == "attribute" for name in fields)
    assert page.options["attribute"] == options["distribution_options"][page.distribution_type][
        "attribute"]
    page.show_gaussians = False
    state = page.get_settings_state()
    assert state == {"distribution_type": page.distribution_type, "show_components": False}


def test_the_residual_2d_settings_follow_the_image(qapp):
    import chisurf.gui.plots.residual_image as module
    from chisurf.core.models.grid_images import get_grid_residual_image
    from test.gui.test_ics_model_editor import _make_ics_fit

    _no_qt(module)
    fit = _make_ics_fit(n_lags=3)
    fit.model.update()
    page = module.Residual2DPlot(
        fit=fit,
        accessor=get_grid_residual_image,
        accessor_kwargs={"weighted": True, "frame_index": 0},
        frame_kw="frame_index",
        frame_label="Frame lag Δ",
    )
    page.update()
    assert page.vmin == -page.vmax
    fields = _draw_settings(page)
    assert {"vmin", "vmax", "auto_contrast", "xmin", "xmax", "ymin", "ymax", "colormap"} <= fields
    assert "image_source" not in fields  # one source: no selector
    page.vmin, page.vmax = -2.0, 3.0
    assert page._image_item.get_levels() == pytest.approx((-2.0, 3.0))
    page.auto_contrast()
    assert page.vmin == -page.vmax
    page.colormap = "viridis"
    lo, hi = page.bounds("xmin")
    page.xmin = lo + 1
    assert page.get_settings_state()["xmin"] == lo + 1
    labels = str(page.settings_spec())
    assert "Frame lag Δ" in labels
