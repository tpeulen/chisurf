"""MaxEnt distributions as views on BFF's tcspc_maxent_lifetime and tcspc_maxent_fret.

The inversion runs in the engine (MaxEntSpectrum over TCSPCDecay's basis);
the view shows the distribution, the second chi-square and an L-curve over
the regularisation weight, the parts the classic MaxEnt models carried.
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("IMP.bff")

import chisurf.core.curve
import chisurf.core.data
import chisurf.core.fitting.fit as fitting
from chisurf.core.models.description import for_family

N, DT, PERIOD = 512, 0.032, 12.5


def _axis():
    return np.arange(N) * DT


def _irf():
    return 1000.0 * np.exp(-0.5 * ((_axis() - 1.0) / 0.06) ** 2)


def _set(model, canonical, value):
    port = model.problem.get_parameter(canonical)
    held = port.fixed
    port.fixed = False
    port.value = float(value)
    port.fixed = held


def _decay():
    """Two lifetimes, 1 and 4 ns at equal amplitude, through the lifetime view itself."""
    x = _axis()
    fit = fitting.Fit(model_class=for_family("tcspc_lifetime"),
                      data=chisurf.core.data.DataCurve(x=x, y=np.ones(N), ey=np.ones(N)))
    model = fit.model
    model.set_dataset("response", chisurf.core.curve.Curve(x=x, y=_irf()))
    model.set_scalar("period", PERIOD)
    model.structure = "lifetime.components.2"
    for name, value in {"lifetime.amplitude.0": 0.5, "lifetime.tau.0": 1.0, "lifetime.amplitude.1": 0.5,
                        "lifetime.tau.1": 4.0, "instrument.n0": 2e5, "instrument.background": 5.0}.items():
        _set(model, name, value)
    model.update()
    return np.random.default_rng(1).poisson(np.asarray(model.y)).astype(float)


def _view(family="tcspc_maxent_lifetime"):
    x = _axis()
    y = _decay()
    fit = fitting.Fit(model_class=for_family(family),
                      data=chisurf.core.data.DataCurve(x=x, y=y, ey=np.sqrt(np.maximum(y, 1.0))))
    fit.xmin, fit.xmax = 0, N
    model = fit.model
    model.set_dataset("response", chisurf.core.curve.Curve(x=x, y=_irf()))
    model.set_scalar("period", PERIOD)
    assert model.problem is not None, model.missing
    return fit, model, y


def test_the_view_recovers_the_lifetime_distribution():
    _, model, y = _view()
    for name, value in {"maxent.grid_from": 0.2, "maxent.grid_to": 8.0, "maxent.grid_bins": 80,
                        "maxent.log10_nu": -4.0, "instrument.background": 5.0}.items():
        _set(model, name, value)
    model.update()
    distribution = np.asarray(model.maxent_distribution)
    p, tau = distribution[0::2], distribution[1::2]
    p = p / p.sum()
    assert abs(p[tau < 2.0].sum() - 0.5) < 0.05
    assert abs(tau[np.argmax(np.where(tau < 2.0, p, 0))] - 1.0) < 0.15
    assert abs(tau[np.argmax(np.where(tau > 2.0, p, 0))] - 4.0) < 0.3
    outputs = {q.name: q.value for q in model.parameters_all if getattr(q, "is_output", False)}
    assert 0.5 < outputs["chi2r (model weights)"] < 1.5
    assert "distribution" in [plot.key for plot in model.view_spec().plots]


def test_an_l_curve_sweeps_the_weight_and_a_point_is_committed():
    _, model, _ = _view()
    _set(model, "maxent.grid_bins", 40)
    _set(model, "instrument.background", 5.0)
    model.compute_l_curve(n_points=6, log10_min=-4.0, log10_max=1.0)
    curve = model.l_curve
    assert len(curve.reg) == 6
    # More regularisation: more misfit, a solution closer to the prior.
    assert np.all(np.diff(curve.residual_norm) >= -1e-6)
    assert np.all(np.diff(curve.solution_norm) <= 1e-6)
    model.set_reg_from_lcurve_index(2)
    assert model.problem.get_parameter("maxent.log10_nu").value == pytest.approx(-2.0)
    assert any(getattr(s, "key", None) == "lcurve" for panel in model.view_spec().sections
               for s in getattr(panel, "sections", ()))
