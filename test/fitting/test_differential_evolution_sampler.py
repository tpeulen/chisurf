"""Differential-Evolution MCMC (ter Braak) — the gradient-free answer to HMC.

HMC and NUTS need the gradient of the log-posterior, which ChiSurf cannot supply
(see ``okf/references/autodiff-assessment.md``). A systematic benchmark of
gradient-free samplers found differential evolution to outperform every
alternative tested, including the affine-invariant stretch move.

DE proposes from the *differences between chains*, so the proposal acquires the
posterior's correlation structure without a covariance being estimated at all.
These tests pin that it samples the right distribution, that it needs no
covariance, and where it beats the covariance proposal.
"""
import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.fitting.sample
import chisurf.core.models.parse
from chisurf.core.fitting import diagnostics as dg


def _fit(func='c+a*x**2', seed=0, npts=64, sigma=0.05, converge=True):
    """Return a fit of ``func`` to noisy data."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.5, 5.0, npts)
    y = 3.1 + 1.2 * x ** 2 + rng.normal(0.0, sigma, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, sigma))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = func
    fit.model.find_parameters()
    if converge:
        fit.run()
    return fit


def _collinear(seed=0):
    """Return a converged fit whose parameters are ~0.99 correlated."""
    rng = np.random.default_rng(seed)
    x = np.linspace(1.0, 2.0, 96)
    y = 1.0 + 2.0 * x + 0.5 * x ** 2 + rng.normal(0.0, 0.02, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, 0.02))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x+b*x**2'
    fit.model.find_parameters()
    fit.run()
    return fit


def test_the_result_has_the_shape_every_sampler_promises():
    """It must be usable by the diagnostics and the chain writer unchanged."""
    np.random.seed(0)
    fit = _fit()
    r = chisurf.core.fitting.sample.sample_differential_evolution(
        fit=fit, steps=200, thin=1, seed=1
    )
    assert set(r) >= {
        'chi2r', 'lnprior', 'parameter_values', 'parameter_names',
        'chains', 'acceptance_rate',
    }
    chains = np.asarray(r['chains'])
    assert chains.ndim == 3
    assert chains.shape[0] == r['n_chains']
    assert chains.shape[2] == len(r['parameter_names'])
    # The flat view is the chains stacked.
    assert r['parameter_values'].shape[0] == chains.shape[0] * chains.shape[1]
    assert r['chi2r'].shape == r['lnprior'].shape
    assert np.all(np.isfinite(r['chi2r']))
    assert 0.0 <= r['acceptance_rate'] <= 1.0


def test_it_recovers_the_posterior():
    """The chain must sit on the optimum with a sane width."""
    np.random.seed(1)
    fit = _fit()
    optimum = {p.name: float(p.value) for p in fit.model.parameters}
    errors = {p.name: float(p.error_estimate) for p in fit.model.parameters}

    r = chisurf.core.fitting.sample.sample_differential_evolution(
        fit=fit, steps=600, thin=1, seed=2
    )
    summary = dg.summarize(np.asarray(r['chains']), names=r['parameter_names'])
    for e in summary:
        short = e['name'].split(':')[-1]
        assert abs(e['mean'] - optimum[short]) < 1.5 * errors[short]
        assert 0.4 < e['sd'] / errors[short] < 2.5


def test_it_honours_priors():
    """A dominant prior must move the population."""
    from chisurf.core.fitting.priors import NormalPrior
    np.random.seed(2)
    fit = _fit()
    c = [p for p in fit.model.parameters if p.name == 'c'][0]
    c_hat = float(c.value)
    sd = float(c.error_estimate)
    # Tight relative to the likelihood, but reachable. A prior that is both
    # tight *and* far tests long-distance migration of the population, which is
    # a different property from whether the prior enters the target at all.
    mu = c_hat + 20.0 * sd
    c.prior = NormalPrior(mu=mu, sigma=0.5 * sd)

    r = chisurf.core.fitting.sample.sample_differential_evolution(
        fit=fit, steps=1500, thin=1, seed=3
    )
    i = list(r['parameter_names']).index('c')
    sampled = np.asarray(r['parameter_values'])[:, i]
    mean = float(sampled[len(sampled) // 2:].mean())
    assert abs(mean - mu) < 5.0 * sd
    assert abs(mean - c_hat) > 5.0 * sd


def test_it_needs_no_covariance_at_all():
    """The proposal is built from the population, so a singular fit is fine.

    ``blocked`` seeds its proposal from the curvature at the optimum. Where that
    curvature is unusable -- a parameter the model does not respond to -- DE is
    unaffected, because a difference between two chains is always well defined.
    """
    np.random.seed(3)
    fit = _fit(func='c+a*x**2+0*b')     # 'b' does not enter the model
    fit.model.update_model()
    r = chisurf.core.fitting.sample.sample_differential_evolution(
        fit=fit, steps=300, thin=1, seed=4
    )
    assert np.all(np.isfinite(r['parameter_values']))
    assert r['acceptance_rate'] > 0.0


def test_it_beats_the_covariance_proposal_away_from_the_optimum():
    """Where a covariance taken at the wrong point misleads, DE does not.

    The covariance proposal is only as good as the point it was taken at. On a
    curved posterior, started away from the optimum, it proposes in the wrong
    shape; DE learns the shape from the population as it goes.

    The margin used to be ~36x. It is now ~3x, because `blocked` got much better
    at exactly this case: its warm-up was spending half the chain re-estimating a
    covariance it could not improve on, and now spends a tenth of it adapting
    only the proposal scale. DE still wins here -- a wrong shape is a wrong shape
    and no amount of scale tuning fixes it -- but this is no longer the rout it
    was, and the assertion says so rather than passing on a stale margin.
    """
    def _ess_per_eval(sampler):
        np.random.seed(11)
        rng = np.random.default_rng(0)
        x = np.linspace(0.1, 4.0, 80)
        y = 2.0 * np.exp(-x / 1.3) + 0.4 + rng.normal(0, 0.01, x.size)
        data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, 0.01))
        fit = chisurf.core.fitting.fit.FitGroup(
            data=chisurf.core.data.DataGroup([data]),
            model_class=chisurf.core.models.parse.ParseModel,
        )
        fit.fit_range = 0, len(fit.model.y)
        fit.model.func = 'a*exp(-x/t)+c'
        fit.model.find_parameters()
        fit.run()
        fit.model.parameter_values = [1.0, 0.6, 0.2]   # away from the optimum
        fit.model.update_model()

        calls = [0]
        m = fit.model
        original = m.update_model

        def counting(*a, _o=original, **k):
            calls[0] += 1
            return _o(*a, **k)

        m.update_model = counting
        r = sampler(fit)
        ess = dg.effective_sample_size(np.asarray(r['chains']))
        return float(ess.min()) / max(1, calls[0])

    blocked = _ess_per_eval(lambda f: chisurf.core.fitting.sample.walk_mcmc_blocked(
        fit=f, steps=6000, step_size=0.05, thin=1))
    de = _ess_per_eval(lambda f: chisurf.core.fitting.sample.sample_differential_evolution(
        fit=f, steps=600, thin=1, seed=3))
    # Measured at ~3x since the blocked warm-up was fixed; assert well below
    # that so this is not brittle.
    assert de > 1.8 * blocked


def test_it_is_competitive_on_a_collinear_posterior():
    """And it must not be *worse* where the covariance proposal is at its best."""
    def _ess_per_eval(sampler):
        np.random.seed(11)
        fit = _collinear()
        calls = [0]
        m = fit.model
        original = m.update_model

        def counting(*a, _o=original, **k):
            calls[0] += 1
            return _o(*a, **k)

        m.update_model = counting
        r = sampler(fit)
        ess = dg.effective_sample_size(np.asarray(r['chains']))
        return float(ess.min()) / max(1, calls[0])

    emcee_ess = _ess_per_eval(lambda f: chisurf.core.fitting.sample.sample_emcee(
        f, steps=800, nwalkers=10, thin=1))
    de = _ess_per_eval(lambda f: chisurf.core.fitting.sample.sample_differential_evolution(
        fit=f, steps=800, thin=1, seed=3))
    # Measured at ~2.3x the affine-invariant stretch move.
    assert de > 1.5 * emcee_ess


def test_the_population_size_is_configurable_and_defaults_sensibly():
    """DE wants a population; the default must scale with the dimension."""
    np.random.seed(4)
    fit = _collinear()
    r = chisurf.core.fitting.sample.sample_differential_evolution(
        fit=fit, steps=100, thin=1, seed=5
    )
    assert r['n_chains'] >= 8

    r = chisurf.core.fitting.sample.sample_differential_evolution(
        fit=fit, steps=100, thin=1, n_chains=6, seed=5
    )
    assert r['n_chains'] == 6
    assert np.asarray(r['chains']).shape[0] == 6


def test_it_restores_the_fit_afterwards():
    """Sampling must not leave the model somewhere the population wandered."""
    np.random.seed(5)
    fit = _fit()
    before = list(fit.model.parameter_values)
    chisurf.core.fitting.sample.sample_differential_evolution(
        fit=fit, steps=200, thin=1, seed=6
    )
    after = list(fit.model.parameter_values)
    assert after == pytest.approx(before)


def test_sample_fit_accepts_the_de_method(tmp_path, monkeypatch):
    """It has to be reachable from the top-level entry point."""
    np.random.seed(6)
    fit = _collinear()

    import chisurf.macros.core_fit
    monkeypatch.setattr(
        chisurf.macros.core_fit, "save_project",
        lambda target_path, project_name="project", **kw: None,
    )
    report = chisurf.core.fitting.fit.sample_fit(
        fit=fit, target_directory=str(tmp_path), method='de',
        steps=400, thin=1, n_runs=2,
    )
    assert report is not None
    assert {e['name'] for e in report['parameters']} == set(fit.model.parameter_names)
