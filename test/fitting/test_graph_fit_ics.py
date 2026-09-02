"""The image-correlation models fit through the graph (PRD-105 phase 3).

`ImageCorrelationModel` evaluates over three lag axes -- none of which is the
flattened index its DataCurve carries -- so it could not use the one-`x`
`Expression -> ChiSquared` builder. The builder now accepts model-declared
axes (`graph_axes()`), and both ICS models expose their compute as a generated
expression string. These tests pin:

* the generated expression against `image_correlation`/`ics_gaussian_2d`
  (the node's curve is the Python curve, machine precision);
* that ``graph_objective`` builds for both models and the fit recovers the
  parameters of a synthetic carpet with **zero** ``update_model`` calls
  inside the minimisation (the crossing contract);
* the refusals: a freed timing parameter (folded into the tau axis) and a
  carpet-less dataset both fall back to the director path, which still fits;
* that the geometry toggle regenerates the equation (the cache key carries
  the string, so a ``two_d`` flip cannot reuse the 3D graph);
* that the Gaussian fit converges under the group's own decade-spanning
  default bounds (``A0`` up to ``1e9``) on both the graph and the director
  path (PRD-120) -- it used to stall at chi2r ~600 instead of ~1.
"""
import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit as F
import chisurf.core.fitting.minimizer as M
from chisurf.core.models.ics.ics import IcsGaussian2DModel, ImageCorrelationModel
from chisurf.core.models.ics.models import ics_gaussian_2d, image_correlation

TIMING = dict(pixel_duration_us=11.1, line_duration_ms=3.33,
              frame_duration_ms=50.0)
TRUTH = dict(n=4.0, diffusion_coefficient=1.5, offset=0.01)


def _carpet_fit(model_class=ImageCorrelationModel, n_side=17, n_lags=2,
                noise=2e-4, seed=5):
    """A synthetic RICS/STICS carpet with known transport parameters."""
    half = n_side // 2
    xi, psi = np.meshgrid(np.arange(-half, half + 1, dtype=float),
                          np.arange(-half, half + 1, dtype=float))
    frame_lags = np.arange(n_lags, dtype=float)
    xi3 = np.broadcast_to(xi[None, ...], (n_lags,) + xi.shape)
    psi3 = np.broadcast_to(psi[None, ...], (n_lags,) + psi.shape)
    delta3 = frame_lags[:, None, None]
    carpet = image_correlation(
        xi3, psi3, delta3,
        n=TRUTH["n"], diffusion_coefficient=TRUTH["diffusion_coefficient"],
        offset=TRUTH["offset"],
        pixel_duration=TIMING["pixel_duration_us"],
        line_duration=TIMING["line_duration_ms"],
        frame_duration=TIMING["frame_duration_ms"],
        pixel_size=40.0, w_r=0.2, w_z=1.0)
    rng = np.random.default_rng(seed)
    y = carpet.ravel() + rng.normal(0.0, noise, carpet.size)
    data = chisurf.core.data.DataCurve(
        x=np.arange(y.size, dtype=float), y=y,
        ey=np.full(y.size, noise))
    data.meta_data["ics"] = {
        "pixel_shift": xi, "line_shift": psi, "frame_lags": frame_lags,
        # IcsTiming.from_meta vocabulary, so the model seeds the same timing
        # the carpet was generated with.
        "pixel_duration_us": TIMING["pixel_duration_us"],
        "line_duration_ms": TIMING["line_duration_ms"],
        "frame_duration_ms": TIMING["frame_duration_ms"],
        "pixel_size_nm": 40.0,
    }
    fit = F.Fit(model_class=model_class, data=data)
    fit.xmin, fit.xmax = 0, y.size
    fit.model.find_parameters()
    return fit


def test_the_graph_is_taken_for_the_carpet_model():
    fit = _carpet_fit()
    assert M.graph_objective(fit, fit.model) is not None


def test_the_node_curve_is_the_python_curve():
    """Census-style parity: evaluate the built graph at the model's own
    values and compare with ``update_model``'s carpet, element for element."""
    fit = _carpet_fit()
    model = fit.model
    # Exercise every optional term, so no branch hides behind its neutral
    # default: anomalous transport, blinking, an immobile fraction, flow and
    # a ccRICS shift all at once.
    model.transport._alpha.value = 0.8
    model.blinking._aT.value = 0.15
    model.blinking._tauT.value = 0.4
    model.immobile._n_imm.value = 1.2
    model.immobile._w_imm.value = 0.3
    model.immobile._sx.value = 120.0
    model.immobile._sy.value = -80.0
    model.flow._vx.value = 6.0
    model.flow._vy.value = -3.0
    for two_d in (False, True):
        model.two_d = two_d
        model.update()
        built = M.graph_objective(fit, model)
        assert built is not None
        m, _ = built
        chi2, _, keepalive, _ = m._graph
        curve_node = keepalive[0]
        curve_node.update()
        curve = np.asarray(
            curve_node.get_output_port("chi2_model").value, dtype=float)
        np.testing.assert_allclose(curve, model.y, rtol=1e-12, atol=1e-14)


def test_the_fit_recovers_the_truth_with_zero_python_evaluations():
    fit = _carpet_fit()
    model = fit.model
    # Displaced but within the truth's basin: from much further out both the
    # graph and the director land in the same local minimum (verified while
    # writing this), which tests the optimiser, not the seam.
    model.transport._n.value = 2.0
    model.transport._D.value = 1.0
    model.transport._offset.value = 0.005

    calls = {"n": 0}
    original = type(model)._update_model

    def counting(self, **kwargs):
        calls["n"] += 1
        return original(self, **kwargs)

    type(model)._update_model = counting
    try:
        fit.run()
        during = calls["n"]
    finally:
        type(model)._update_model = original

    assert model.transport.n == pytest.approx(TRUTH["n"], rel=5e-2)
    assert model.transport.D == pytest.approx(
        TRUTH["diffusion_coefficient"], rel=5e-2)
    # One evaluation refreshes the displayed carpet after the write-back;
    # a director fit would show one call per optimiser iteration here.
    assert during <= 2


def test_a_freed_timing_parameter_refuses_the_graph_and_still_fits():
    """The scan timing is folded into the tau axis, so freeing it must fall
    back to the director path -- silently freezing it would fit the wrong
    model."""
    fit = _carpet_fit()
    fit.model.imaging._pixel_duration.fixed = False
    fit.model.find_parameters()
    assert M.graph_objective(fit, fit.model) is None
    fit.run()   # the fallback still runs to completion
    assert np.isfinite(fit.chi2r)


def test_no_carpet_metadata_refuses_the_graph():
    fit = _carpet_fit()
    fit.data.meta_data["ics"] = {}
    assert fit.model.graph_axes() is None
    assert M.graph_objective(fit, fit.model) is None


def test_the_geometry_toggle_changes_the_cached_key():
    fit = _carpet_fit()
    model = fit.model
    key_3d = M._graph_cache_key(fit, model)
    model.two_d = True
    key_2d = M._graph_cache_key(fit, model)
    assert key_3d != key_2d


def test_the_gaussian2d_node_curve_is_the_python_curve():
    fit = _carpet_fit(model_class=IcsGaussian2DModel, n_lags=1)
    model = fit.model
    model.gaussian._angle.value = 0.7
    model.gaussian._s2.value = 310.0
    model.gaussian._xo.value = 25.0
    model.gaussian._yo.value = -40.0
    model.update()
    built = M.graph_objective(fit, model)
    assert built is not None
    m, _ = built
    _, _, keepalive, _ = m._graph
    curve_node = keepalive[0]
    curve_node.update()
    curve = np.asarray(
        curve_node.get_output_port("chi2_model").value, dtype=float)
    np.testing.assert_allclose(curve, model.y, rtol=1e-12, atol=1e-14)


def _gaussian2d_fit_near_truth():
    """The PRD-120 fixture: a close start under the group's own bounds.

    ``A0`` is bounded ``(0, 1e9)`` and the widths ``(1, 1e5)`` -- the group's
    defensive defaults, left on (``bounds_on`` defaults ``True``) -- from a
    start close enough that the unbounded problem converges in a handful of
    evaluations (chi2r ~1.0). Before PRD-120 the bounded fit stalled at
    chi2r ~608 on *both* the graph and the director path: the two-sided
    sin-transform's derivative is ~(ub-lb)/2 almost everywhere over a
    decade-spanning interval, so MINPACK's forward-difference probe lands
    physically kilometres from the start and the linearised step collapses.
    """
    fit = _carpet_fit(model_class=IcsGaussian2DModel, n_lags=1, noise=1e-3)
    # Overwrite the carpet with the Gaussian model's own truth.
    meta = fit.data.meta_data["ics"]
    xi, psi = meta["pixel_shift"], meta["line_shift"]
    truth = ics_gaussian_2d(xi, psi, amplitude=0.5, pixel_size=40.0,
                            sigma_1=180.0, sigma_2=320.0)
    rng = np.random.default_rng(9)
    fit.data.y = truth.ravel() + rng.normal(0.0, 1e-3, truth.size)
    model = fit.model
    model.gaussian._a0.value = 0.4
    model.gaussian._s1.value = 200.0
    model.gaussian._s2.value = 280.0
    model.gaussian._angle.fixed = True
    model.find_parameters()
    return fit, model


def test_the_gaussian2d_fit_recovers_the_widths():
    """PRD-120: converges under the group's own bounds, via the graph path."""
    fit, model = _gaussian2d_fit_near_truth()
    for p in (model.gaussian._a0, model.gaussian._s1,
              model.gaussian._s2, model.gaussian._offset):
        assert p.bounds_on, "the group's decade-spanning defaults are the point"
    assert M.graph_objective(fit, model) is not None
    fit.run()
    assert fit.chi2r == pytest.approx(1.0, rel=0.5)
    got = sorted([model.gaussian.sigma_1, model.gaussian.sigma_2])
    assert got[0] == pytest.approx(180.0, rel=1e-2)
    assert got[1] == pytest.approx(320.0, rel=1e-2)


def test_the_gaussian2d_fit_recovers_the_widths_through_the_director(monkeypatch):
    """PRD-120: the director fallback shares the bounds transform, so a model
    the graph refuses must converge just as well under the same bounds."""
    fit, model = _gaussian2d_fit_near_truth()
    monkeypatch.setattr(M, "graph_objective",
                        lambda fit, model, allow_priors=False: None)
    assert M.graph_objective(fit, model) is None
    fit.run()
    assert fit.chi2r == pytest.approx(1.0, rel=0.5)
    got = sorted([model.gaussian.sigma_1, model.gaussian.sigma_2])
    assert got[0] == pytest.approx(180.0, rel=1e-2)
    assert got[1] == pytest.approx(320.0, rel=1e-2)
