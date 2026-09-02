"""The sampler crosses four times, not per step (board T-20260902-09).

A graph-eligible fit samples through ``IMP.bff.Sampler``; the SWIG boundary
is crossed only at begin, per-segment progress, per-segment partial saves,
and the end. These tests pin

* that the graph route is actually taken (no per-step Python model
  evaluations),
* that its posterior agrees *statistically* with the Python samplers'
  (stream parity is disclaimed by the port -- different RNGs -- so a
  same-seed same-chain assertion across the two would fail by design),
* the segment contract: progress callbacks carry a usable partial result,
  and cancellation between segments stops the run.
"""
import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.fitting.sample
import chisurf.core.models.parse
from chisurf.core.fitting import sampler_bff

pytestmark = pytest.mark.skipif(
    not sampler_bff.have_sampler(),
    reason="IMP.bff.Sampler not available")

SIGMA = 0.02


def _collinear_fit(seed: int = 0):
    """A converged ``c + a*x + b*x**2`` fit over a narrow x-range."""
    rng = np.random.default_rng(seed)
    x = np.linspace(1.0, 2.0, 96)
    y = 1.0 + 2.0 * x + 0.5 * x ** 2 + rng.normal(0.0, SIGMA, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) * SIGMA)
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x+b*x**2'
    fit.model.find_parameters()
    fit.run()
    return fit


def test_the_graph_route_is_taken_and_python_never_evaluates_per_step():
    """The whole chain runs in C++: the Python model is not called per step."""
    fit = _collinear_fit()
    calls = {'n': 0}
    original = fit.model.update_model

    def counting_update(*a, **kw):
        calls['n'] += 1
        return original(*a, **kw)

    fit.model.update_model = counting_update
    try:
        r = chisurf.core.fitting.sample.walk_mcmc_blocked(
            fit=fit, steps=2000, step_size=0.02, thin=1, seed=7)
    finally:
        fit.model.update_model = original

    assert len(r['parameter_values']) > 0
    # The graph build reads values once; the covariance seed may re-run the
    # model a handful of times. 2000 sampling steps in Python would be
    # >= 2000 calls; the contract is that none of them happen here.
    assert calls['n'] < 50


def test_bff_and_python_samplers_agree_on_the_posterior():
    """Moments and width, not streams: the RNGs differ by design."""
    fit = _collinear_fit()
    optimum = {p.name: float(p.value) for p in fit.model.parameters}
    errors = {p.name: float(p.error_estimate) for p in fit.model.parameters}

    r_cpp = chisurf.core.fitting.sample.walk_mcmc_blocked(
        fit=fit, steps=4000, step_size=0.02, thin=1, seed=11)

    # Force the Python path for the reference run.
    saved = sampler_bff._bff
    sampler_bff._bff = None
    try:
        r_py = chisurf.core.fitting.sample.walk_mcmc_blocked(
            fit=fit, steps=4000, step_size=0.02, thin=1, seed=11)
    finally:
        sampler_bff._bff = saved

    names = r_cpp['parameter_names']
    assert names == r_py['parameter_names']
    for k, name in enumerate(names):
        cpp = np.asarray(r_cpp['parameter_values'])[:, k]
        py = np.asarray(r_py['parameter_values'])[:, k]
        # Both sit on the optimum...
        assert abs(cpp.mean() - optimum[name]) < 2.0 * errors[name]
        assert abs(py.mean() - optimum[name]) < 2.0 * errors[name]
        # ...with comparable widths (a chain that mixes 5x worse fails this).
        assert 0.4 < cpp.std() / max(py.std(), 1e-30) < 2.5


def test_segments_deliver_partial_results_and_cancellation():
    """Progress carries a partial result dict; check_cancel stops the run."""
    fit = _collinear_fit()
    seen = []

    def callback(done, total, result=None):
        seen.append((done, total, result))

    def cancel():
        return len(seen) >= 2

    r = chisurf.core.fitting.sample.walk_mcmc_blocked(
        fit=fit, steps=100000, step_size=0.02, thin=1, seed=3,
        callback=callback, check_cancel=cancel)

    # Cancelled long before the requested steps...
    assert len(r['parameter_values']) < 100000
    # ...after at least two segments, each of which carried a partial
    # result in the samplers' own shape.
    assert len(seen) >= 2
    done, total, partial = seen[0]
    assert 0 < done <= total == 100000
    assert partial is not None
    assert set(partial) >= {
        'chi2r', 'lnprior', 'parameter_values', 'parameter_names',
        'chains', 'acceptance_rate'}
    assert len(partial['parameter_values']) == done


def test_a_prior_rides_the_port_and_shifts_the_posterior():
    """A normal prior reaches the C++ sampler through the port spec."""
    fit = _collinear_fit()
    p = fit.model.parameters[0]
    mu = float(p.value) + 5.0 * float(p.error_estimate)
    p.prior = {"kind": "normal", "mu": mu, "sigma": float(p.error_estimate)}
    try:
        r = chisurf.core.fitting.sample.walk_mcmc_blocked(
            fit=fit, steps=4000, step_size=0.02, thin=1, seed=5)
    finally:
        p.prior = None

    # The prior contributed (lnprior varies), and it pulled the marginal
    # towards mu, away from the likelihood optimum.
    lnprior = np.asarray(r['lnprior'])
    assert np.ptp(lnprior[np.isfinite(lnprior)]) > 0
    marginal = np.asarray(r['parameter_values'])[:, 0].mean()
    assert marginal > float(p.value) + 0.5 * float(p.error_estimate)
