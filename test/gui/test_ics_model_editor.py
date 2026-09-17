"""Headless editor and plot tests for the image-correlation view.

The image-correlation model is a catalogue of carpet equations
(``chisurf/core/models/ics/models.yaml``) viewed on BFF. A synthetic dataset
carries what the ICS reader records -- the carpet, its coordinates, its grid
and the pixel size -- so no file I/O is needed.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("IMP.bff")


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _make_ics_data(n_lags: int = 3):
    """A DataCurve holding a synthetic carpet as the ICS reader would record it."""
    from chisurf.core.data import DataCurve
    from chisurf.core.experiments.ics.data import carpet_coordinates
    from chisurf.core.models.ics.models import image_correlation

    xi_axis = np.arange(-8, 9, dtype=float)
    psi_axis = np.arange(0, 16, dtype=float)
    pixel_shift, line_shift = np.meshgrid(xi_axis, psi_axis)
    frame_lags = np.arange(n_lags, dtype=float)
    carpet = image_correlation(
        pixel_shift[None, ...],
        line_shift[None, ...],
        frame_lags[:, None, None],
        n=2.0,
        diffusion_coefficient=1.5,
        offset=0.0,
        pixel_duration=11.1,
        line_duration=3.33,
        frame_duration=500.0,
        pixel_size=50.0,
        w_r=0.25,
        w_z=1.0,
    )
    carpet = np.broadcast_to(carpet, (n_lags,) + pixel_shift.shape).copy()
    y = carpet.ravel()
    ics = {
        "correlation": carpet,
        "pixel_shift": pixel_shift,
        "line_shift": line_shift,
        "frame_lags": frame_lags,
        "pixel_duration_us": 11.1,
        "line_duration_ms": 3.33,
        "frame_duration_ms": 500.0,
        "pixel_size_nm": 50.0,
    }
    meta = {
        "ics": ics,
        "coordinates": carpet_coordinates(ics),
        "grid": {"ndim": 3, "shape": carpet.shape, "order": "C", "size": int(y.size)},
        "parameter_defaults": {"pxl_size": 50.0},
    }
    return DataCurve(
        name="synthetic-ics",
        load_filename_on_init=False,
        y=y,
        ey=np.full(y.size, 1e-3),
        x=np.arange(y.size, dtype=float),
        meta_data=meta,
    )


def _make_ics_fit(n_lags: int = 3):
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.ics.ics import ImageCorrelationModel

    fit = fit_mod.Fit(model_class=ImageCorrelationModel, data=_make_ics_data(n_lags))
    fit.xmin, fit.xmax = 0, int(np.asarray(fit.data.y).size)
    return fit


def _set(model, **values):
    problem = model.problem
    for name, value in values.items():
        port = problem.get_parameter(name)
        held = port.fixed
        port.fixed = False
        port.value = value
        port.fixed = held
    model.update()


def test_the_editor_renders_and_declares_the_image_plots(qapp):
    from qtpy import QtWidgets

    from chisurf.gui.plots.residual_image import Residual2DPlot
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget
    from chisurf.gui.widgets.models.model_editor import build_model_editor, model_plot_specs

    fit = _make_ics_fit()
    model = fit.model
    assert model.problem is not None, model.missing
    editor = build_model_editor(model)
    assert isinstance(editor, AutoModelWidget)
    QtWidgets.QVBoxLayout().addWidget(editor)
    assert {"transport", "imaging"} <= set(model.view_spec().section_targets())

    res2d = [opts for cls, opts in model_plot_specs(model) if cls is Residual2DPlot]
    assert res2d, "residual2d plot not declared"
    opts = res2d[0]
    assert set(opts["sources"]) == {"Residual", "Data", "Model"}
    assert all(callable(s["accessor"]) for s in opts["sources"].values())
    assert callable(opts["max_frames_accessor"])


def test_image_accessors_follow_the_frame_slider(qapp):
    from chisurf.core.models.grid_images import (
        get_grid_data_image,
        get_grid_model_image,
        get_grid_n_frames,
        get_grid_residual_image,
    )

    fit = _make_ics_fit(n_lags=3)
    fit.model.update()
    assert get_grid_n_frames(fit) == 3
    first, _, _ = get_grid_data_image(fit, frame_index=0)
    last, _, _ = get_grid_data_image(fit, frame_index=2)
    assert not np.allclose(first, last), "the slider must change the shown slice"
    np.testing.assert_allclose(get_grid_data_image(fit, frame_index=99)[0], last)
    for accessor in (get_grid_model_image, get_grid_residual_image):
        img, x, y = accessor(fit, frame_index=1)
        assert img is not None and img.ndim == 2
        assert x.size == img.shape[1] and y.size == img.shape[0]


def test_the_model_matches_the_data_it_was_generated_from(qapp):
    fit = _make_ics_fit(n_lags=3)
    model = fit.model
    model.structure = "Image correlation (3D)"
    _set(model, N=2.0, D=1.5, w_r=0.25, w_z=1.0, offset=0.0)
    np.testing.assert_allclose(np.asarray(model.y), np.asarray(fit.data.y), rtol=1e-9, atol=1e-12)


def test_the_fit_is_stable_for_every_equation(qapp):
    fit = _make_ics_fit()
    model = fit.model
    for key in list(model.problem.get_structure_keys()):
        model.structure = key
        fit.run()
        assert np.all(np.isfinite(np.asarray(model.y))), key


def test_optional_terms_change_the_carpet(qapp):
    fit = _make_ics_fit()
    model = fit.model
    model.structure = "Image correlation (3D)"
    model.update()
    base = np.array(model.y)
    for name, value in (("N_imm", 0.5), ("v_x", 200.0), ("aT", 0.4), ("alpha", 0.6)):
        original = model.problem.get_parameter(name).value
        _set(model, **{name: value})
        assert not np.allclose(base, model.y), f"{name} had no effect"
        _set(model, **{name: original})
    np.testing.assert_allclose(base, model.y)


def test_ics_compute_is_finite_for_adversarial_params():
    """The numpy reference the calibration uses stays finite for bad excursions."""
    from chisurf.core.models.ics.models import ics_gaussian_2d, image_correlation

    axis = np.arange(-6, 7, dtype=float)
    ps, ls = np.meshgrid(axis, axis)
    for kw in (
        dict(n=0.0, diffusion_coefficient=1.0),
        dict(n=-5.0, diffusion_coefficient=-2.0),
        dict(n=1e-9, diffusion_coefficient=0.0, w_r=0.0, w_z=0.0),
    ):
        for delta in (0.0, 3.0):
            for extra in (
                {},
                {"n_immobile": -2.0, "w_immobile": 0.0, "shift_x": 30.0},
                {"v_x": -50.0, "v_y": 1e4},
                {"tau_triplet": -1.0, "a_triplet": 1.5},
                {"n_immobile": -2.0, "two_d": True},
                {"alpha": 0.0},
                {"alpha": 2.0, "a_triplet": 0.999},
            ):
                assert np.all(np.isfinite(image_correlation(ps, ls, delta, **{**kw, **extra})))
    assert np.all(
        np.isfinite(ics_gaussian_2d(ls, ps, amplitude=-1.0, sigma_1=0.0, sigma_2=0.0, angle=9.0))
    )


def test_residual_2d_plot_draws_and_maps_the_roi(qapp):
    from chisurf.core.models.grid_images import get_grid_residual_image
    from chisurf.gui.plots.residual_image import Residual2DPlot

    fit = _make_ics_fit(n_lags=3)
    fit.model.update()
    plot = Residual2DPlot(
        fit=fit,
        accessor=get_grid_residual_image,
        accessor_kwargs={"weighted": True, "frame_index": 0},
        frame_kw="frame_index",
    )
    plot.update()
    image = plot._image_item
    assert image is not None, "no image drawn"
    assert np.array_equal(image.get_image(), plot._image)
    for name in ("RdBu", "bwr", "viridis"):
        plot.plot_controller.cb_cmap.setCurrentText(name)  # recolours without raising
    plot.plot_controller.sb_vmin.setValue(-2.0)
    plot.plot_controller.sb_vmax.setValue(3.0)
    plot.apply_levels_from_controller()
    assert image.get_levels() == pytest.approx((-2.0, 3.0))
    seen = []
    plot.regionChanged.connect(lambda lo, hi: seen.append((lo, hi)))
    ny, nx = plot._image.shape
    plot._roi.set_size(0.5 * (nx - 1), 0.5 * (ny - 1))
    # What a drag ends in; whether a programmatic resize also notifies is up to
    # the backend, and the mapping to a range is what is under test.
    plot._on_roi_changed()
    assert seen, "the ROI did not map to regionChanged"
    lo, hi = seen[-1]
    assert 0 <= lo < hi < ny * nx
