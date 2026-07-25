"""Headless model-editor tests for the AutoForm image-correlation models.

Mirror the PDA editor tests: each pure model builds through the real AutoForm
seam, every parameter-group section renders, the 2D plot's lag-aware accessors
resolve, and the model computes a finite carpet. A synthetic ICS dataset (lag
grids + carpet in ``meta_data['ics']``) avoids any file I/O.
"""
from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _make_ics_data(n_lags: int = 3):
    """Return a DataCurve with a synthetic correlation carpet.

    Parameters
    ----------
    n_lags : int
        Number of frame lags in the carpet. ``1`` is a plain RICS map.

    Returns
    -------
    chisurf.core.data.DataCurve
        Curve whose ``y`` is the flattened carpet.
    """
    from chisurf.core.data import DataCurve
    from chisurf.core.models.ics.models import image_correlation

    xi_axis = np.arange(-8, 9, dtype=float)     # fast (pixel) lags
    psi_axis = np.arange(0, 16, dtype=float)    # slow (line) lags
    pixel_shift, line_shift = np.meshgrid(xi_axis, psi_axis)
    frame_lags = np.arange(n_lags, dtype=float)

    carpet = image_correlation(
        pixel_shift[None, ...], line_shift[None, ...], frame_lags[:, None, None],
        n=2.0, diffusion_coefficient=1.5, offset=0.0,
        pixel_duration=11.1, line_duration=3.33, frame_duration=500.0,
        pixel_size=50.0, w_r=0.25, w_z=1.0,
    )
    carpet = np.broadcast_to(carpet, (n_lags,) + pixel_shift.shape).copy()
    y = carpet.ravel()
    meta = {
        "ics": {
            "correlation": carpet,
            "pixel_shift": pixel_shift,
            "line_shift": line_shift,
            "frame_lags": frame_lags,
            "ics_mean": carpet[0],
            "pixel_duration_us": 11.1,
            "line_duration_ms": 3.33,
            "frame_duration_ms": 500.0,
            "pixel_size_nm": 50.0,
        }
    }
    return DataCurve(name="synthetic-ics", load_filename_on_init=False,
                     y=y, x=np.arange(y.size, dtype=float), meta_data=meta)


def _make_ics_fit(model_class, n_lags: int = 3):
    """Return a Fit over synthetic ICS data for a model class."""
    import chisurf.core.fitting.fit as fit_mod

    return fit_mod.Fit(model_class=model_class, data=_make_ics_data(n_lags))


ICS_MODELS = [
    "chisurf.core.models.ics.ics.ImageCorrelationModel",
    "chisurf.core.models.ics.ics.IcsGaussian2DModel",
]


def _resolve(path):
    import importlib

    mod, _, name = path.rpartition(".")
    return getattr(importlib.import_module(mod), name)


@pytest.mark.parametrize("model_path", ICS_MODELS)
def test_ics_model_editor_renders_and_computes(qapp, model_path):
    from qtpy import QtWidgets

    from chisurf.core.models import view_spec as vs
    from chisurf.gui.plots.residual_image import Residual2DPlot
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget
    from chisurf.gui.widgets.models.model_editor import (
        build_model_editor,
        model_plot_specs,
    )

    model_class = _resolve(model_path)
    assert getattr(model_class, "view_spec_file", None), f"{model_path} has no view_spec_file"

    fit = _make_ics_fit(model_class)
    model = fit.model

    editor = build_model_editor(model)
    assert isinstance(editor, AutoModelWidget)
    QtWidgets.QVBoxLayout().addWidget(editor)
    from chisurf.gui.autoform.sections.parameter_table import ParameterGroupTableWidget
    table_rows = sum(t.table_model.rowCount() for t in editor.findChildren(ParameterGroupTableWidget))
    assert len(editor.parameter_widgets) + table_rows > 3, "parameter groups rendered empty"

    spec = model.view_spec()
    for section in spec.flat_sections():
        if isinstance(section, (vs.ParameterGroupSection, vs.ParameterGroupTableSection)):
            group = getattr(model, section.target)
            if hasattr(group, "find_parameters") and not list(group.parameters_all):
                group.find_parameters()
            assert list(group.parameters_all), f"group {section.target!r} has no parameters"

    # The 2D plot resolves every named source plus the lag-count accessor.
    specs = model_plot_specs(model)
    res2d = [opts for cls, opts in specs if cls is Residual2DPlot]
    assert res2d, "residual2d plot not declared"
    opts = res2d[0]
    assert set(opts["sources"]) == {"Residual", "Data", "Model"}
    for spec_ in opts["sources"].values():
        assert callable(spec_["accessor"]), "source accessor not resolved"
    assert callable(opts["max_frames_accessor"]), "lag-count accessor not resolved"
    assert opts["frame_kw"] == "lag_index"

    # Model computes a finite carpet (and its flattened 1D form).
    model.update()
    y = np.asarray(model.y)
    assert y.size > 0 and np.all(np.isfinite(y))
    assert model.model_carpet is not None and model.model_carpet.ndim == 3


def test_plot_accessors_follow_the_lag_slider(qapp):
    """Each accessor returns the requested frame-lag slice, not always lag 0."""
    from chisurf.core.models.ics.ics import (
        ImageCorrelationModel,
        get_ics_data_image,
        get_ics_model_image,
        get_ics_n_lags,
        get_ics_residual_image,
    )

    fit = _make_ics_fit(ImageCorrelationModel, n_lags=3)
    model = fit.model
    model.update()

    assert get_ics_n_lags(fit) == 3

    first, _, _ = get_ics_data_image(fit, lag_index=0)
    last, _, _ = get_ics_data_image(fit, lag_index=2)
    assert first is not None and last is not None
    assert not np.allclose(first, last), "the slider must change the shown slice"

    # Out-of-range indices clamp instead of raising.
    clamped, _, _ = get_ics_data_image(fit, lag_index=99)
    np.testing.assert_allclose(clamped, last)

    for accessor in (get_ics_model_image, get_ics_residual_image):
        img, x, y = accessor(fit, lag_index=1)
        assert img is not None and img.ndim == 2
        assert x.size == img.shape[1] and y.size == img.shape[0]


def test_model_matches_the_data_it_was_generated_from(qapp):
    """Seeded with the generating parameters, the residual is numerically zero."""
    from chisurf.core.models.ics.ics import ImageCorrelationModel

    fit = _make_ics_fit(ImageCorrelationModel, n_lags=3)
    model = fit.model
    model.transport._n.value = 2.0
    model.transport._D.value = 1.5
    model.imaging._w_r.value = 0.25
    model.imaging._w_z.value = 1.0
    model.update()

    np.testing.assert_allclose(
        np.asarray(model.y), np.asarray(fit.data.y), rtol=1e-9, atol=1e-12
    )


def test_ics_compute_is_finite_for_adversarial_params():
    """The model stays finite for zero/negative optimizer excursions.

    The fit divides by N and the beam waists, so unconstrained excursions to
    zero/negative values previously produced inf/nan and crashed leastsq. The
    function takes magnitudes and floors divisors instead.
    """
    from chisurf.core.models.ics.models import ics_gaussian_2d, image_correlation

    axis = np.arange(-6, 7, dtype=float)
    ps, ls = np.meshgrid(axis, axis)
    bad = [
        dict(n=0.0, diffusion_coefficient=1.0),
        dict(n=-5.0, diffusion_coefficient=-2.0),
        dict(n=1e-9, diffusion_coefficient=0.0, w_r=0.0, w_z=0.0),
    ]
    extras = [
        {},
        {"n_immobile": -2.0, "w_immobile": 0.0, "shift_x": 30.0},
        {"v_x": -50.0, "v_y": 1e4},
        {"tau_triplet": -1.0, "a_triplet": 1.5},
        {"n_immobile": -2.0, "two_d": True},
        {"alpha": 0.0},
        {"alpha": 2.0, "a_triplet": 0.999},
    ]
    for kw in bad:
        for delta in (0.0, 3.0):
            for extra in extras:
                out = image_correlation(ps, ls, delta, **{**kw, **extra})
                assert np.all(np.isfinite(out)), f"not finite for {kw} / {extra}"

    # anisotropic Gaussian with degenerate widths / angle
    g = ics_gaussian_2d(ls, ps, amplitude=-1.0, sigma_1=0.0, sigma_2=0.0, angle=9.0)
    assert np.all(np.isfinite(g))


def test_ics_fit_is_stable(qapp):
    """Each model runs a real fit to completion with finite parameters."""
    import chisurf.core.fitting.fit as fit_mod

    for path in ICS_MODELS:
        fit = fit_mod.Fit(model_class=_resolve(path), data=_make_ics_data())
        m = fit.model
        fit.xmin, fit.xmax = 0, int(np.asarray(fit.data.y).size)
        m.update()
        fit.run()  # must not raise ("array must not contain infs or NaNs")
        assert np.all(np.isfinite(np.asarray(m.y)))


def test_optional_terms_change_the_carpet(qapp):
    """Releasing a term from its neutral value actually perturbs the model."""
    from chisurf.core.models.ics.ics import ImageCorrelationModel

    model = _make_ics_fit(ImageCorrelationModel).model
    model.update()
    base = model.model_carpet.copy()

    for group, attr, value in (
        ("immobile", "_n_imm", 0.5),
        ("flow", "_vx", 200.0),
        ("blinking", "_aT", 0.4),
        ("transport", "_alpha", 0.6),
    ):
        model.update()
        before = model.model_carpet.copy()
        param = getattr(getattr(model, group), attr)
        original = param.value
        param.value = value
        model.update()
        assert not np.allclose(before, model.model_carpet), f"{group}.{attr} had no effect"
        param.value = original

    model.update()
    np.testing.assert_allclose(base, model.model_carpet)
