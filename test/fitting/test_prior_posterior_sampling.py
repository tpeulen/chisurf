"""The sampled posterior must include the parameter priors (PRD-68, phase 1).

``lnprior`` used to short-circuit to a flat box prior whenever ``bounds`` were
passed, and both samplers pass them unconditionally. Every informative prior was
therefore silently dropped from the MCMC posterior while maximum-a-posteriori
estimation still honoured it, so the optimiser and the sampler targeted
different distributions. These tests pin the repaired behaviour: a prior tight
enough to dominate the likelihood must visibly move the sampled marginal, and
the recorded chi2 must stay the *data* misfit rather than absorbing the prior.
"""

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.fitting.sample
import chisurf.core.models.parse
from chisurf.core.fitting.priors import NormalPrior

SIGMA = 0.05
C_TRUE = 3.1
A_TRUE = 1.2


def _quadratic_fit(seed: int = 1):
    """Return a converged ``c + a*x**2`` fit to noisy data with known sigma.

    Parameters
    ----------
    seed : int, optional
        Seed of the random-number generator used to draw the noise.

    Returns
    -------
    chisurf.core.fitting.fit.FitGroup
        The converged fit.
    """
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, 64)
    y = C_TRUE + A_TRUE * x**2 + rng.normal(0.0, SIGMA, x.size)

    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) * SIGMA)
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = "c+a*x**2"
    fit.model.find_parameters()
    fit.run()
    return fit


def _parameter(fit, name):
    """Return the named free parameter of a fit's model."""
    for p in fit.model.parameters:
        if p.name == name:
            return p
    raise AssertionError(f"no free parameter named {name!r}")


def test_lnprior_sums_priors_even_when_bounds_are_given():
    """Passing ``bounds`` must not suppress a parameter's own prior."""
    fit = _quadratic_fit()
    c = _parameter(fit, "c")
    prior = NormalPrior(mu=C_TRUE + 1.0, sigma=0.25)
    c.prior = prior

    values = list(fit.model.parameter_values)
    bounds = fit.model.parameter_bounds

    with_bounds = chisurf.core.fitting.fit.lnprior(values, fit, bounds=bounds)
    without_bounds = chisurf.core.fitting.fit.lnprior(values, fit, bounds=None)

    # The prior is unbounded, so the box contributes nothing and the two agree.
    assert np.isfinite(with_bounds)
    assert with_bounds == pytest.approx(without_bounds, abs=1e-9)
    # And it is the actual Gaussian density, not the flat 0.0 of the old path.
    i = fit.model.parameter_names.index("c")
    assert with_bounds == pytest.approx(prior.lnpdf(values[i]), abs=1e-9)
    assert with_bounds != 0.0


def test_lnprob_parts_splits_likelihood_and_prior():
    """``lnprob`` must equal ``lnlike + lnprior`` with chi2 free of the prior."""
    fit = _quadratic_fit()
    _parameter(fit, "c").prior = NormalPrior(mu=C_TRUE + 1.0, sigma=0.25)

    values = list(fit.model.parameter_values)
    bounds = fit.model.parameter_bounds

    lnlike, lnpr, chi2 = chisurf.core.fitting.fit.lnprob_parts(values, fit, bounds=bounds)
    total = chisurf.core.fitting.fit.lnprob(values, fit, bounds=bounds)

    assert total == pytest.approx(lnlike + lnpr)
    assert lnlike == pytest.approx(-0.5 * chi2)
    # chi2 is the data misfit only -- it must match the prior-free objective.
    chi2_data = chisurf.core.fitting.fit.get_chi2(values, model=fit.model, reduced=False)
    assert chi2 == pytest.approx(chi2_data)
    assert lnpr < 0.0


def test_walk_mcmc_marginal_is_pulled_by_a_dominant_prior():
    """A prior far tighter than the likelihood must move the sampled marginal."""
    np.random.seed(0)
    fit = _quadratic_fit()

    c = _parameter(fit, "c")
    c_hat = float(c.value)
    mu_prior = c_hat + 0.5
    c.prior = NormalPrior(mu=mu_prior, sigma=0.002)

    r = chisurf.core.fitting.sample.walk_mcmc(fit=fit, steps=3000, step_size=0.01, temp=1.0, thin=1)
    i = list(r["parameter_names"]).index("c")
    sampled = np.asarray(r["parameter_values"], dtype=float)[:, i]
    mean = float(sampled[len(sampled) // 2 :].mean())

    # The prior is ~100x tighter than the likelihood on c, so the posterior
    # sits essentially at the prior mean and nowhere near the least-squares one.
    assert abs(mean - mu_prior) < 0.05
    assert abs(mean - c_hat) > 0.3


def test_walk_mcmc_reports_prior_and_data_chi2_separately():
    """The chain must carry ``lnprior`` and a data-only ``chi2r``."""
    np.random.seed(1)
    fit = _quadratic_fit()
    _parameter(fit, "c").prior = NormalPrior(mu=C_TRUE, sigma=0.05)

    r = chisurf.core.fitting.sample.walk_mcmc(fit=fit, steps=200, step_size=0.01, temp=1.0, thin=1)
    assert "lnprior" in r
    lnprior = np.asarray(r["lnprior"], dtype=float)
    chi2r = np.asarray(r["chi2r"], dtype=float)
    assert lnprior.shape == chi2r.shape
    # An informative prior contributes a genuine, finite density...
    assert np.all(np.isfinite(lnprior))
    assert np.any(lnprior != 0.0)
    # ...and chi2r stays a goodness-of-fit number rather than absorbing it.
    assert np.all(chi2r > 0.0)

    # Recomputing the objective at a recorded state must reproduce its chi2r.
    dof = float(fit.model.n_points - fit.model.n_free - 1.0)
    state = list(np.asarray(r["parameter_values"], dtype=float)[-1])
    chi2_direct = chisurf.core.fitting.fit.get_chi2(state, model=fit.model, reduced=False)
    assert chi2r[-1] == pytest.approx(chi2_direct / dof, rel=1e-6)


def test_flat_prior_chain_is_unchanged_by_the_fix():
    """Without any prior the chain must still be plain likelihood sampling."""
    np.random.seed(2)
    fit = _quadratic_fit()

    r = chisurf.core.fitting.sample.walk_mcmc(fit=fit, steps=300, step_size=0.01, temp=1.0, thin=1)
    lnprior = np.asarray(r["lnprior"], dtype=float)
    # Bounds are handled by the cheap box check, so nothing is added on top.
    assert np.allclose(lnprior, 0.0)


def test_ensemble_chain_carries_the_prior_blob():
    """The ensemble sampler must report ``lnprior`` alongside the data chi2."""
    np.random.seed(3)
    fit = _quadratic_fit()
    _parameter(fit, "c").prior = NormalPrior(mu=C_TRUE, sigma=0.05)

    r = chisurf.core.fitting.sample.sample_ensemble(fit, steps=40, nwalkers=8, thin=1)
    lnprior = np.asarray(r["lnprior"], dtype=float)
    chi2r = np.asarray(r["chi2r"], dtype=float)
    assert lnprior.shape[0] == r["parameter_values"].shape[0]
    assert chi2r.shape == lnprior.shape
    finite = np.isfinite(lnprior)
    assert finite.any()
    assert np.any(lnprior[finite] != 0.0)
