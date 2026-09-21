"""Statistical correctness checks for the Metropolis sampler ``walk_mcmc``.

These are regression tests for a sign error in the Metropolis acceptance test
that made the chain walk *away* from the optimum (it sampled ``exp(+chi2/2)``
instead of ``exp(-chi2/2)``), and for the chain not re-recording its state on
rejected proposals.
"""

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.fitting.sample
import chisurf.core.models.parse

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
    tuple
        The fit, the x values and the per-point standard deviation.
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
    return fit, x


def test_walk_mcmc_does_not_walk_away_from_the_optimum():
    """A chain started at the optimum must stay in its neighbourhood."""
    np.random.seed(0)
    fit, _ = _quadratic_fit()
    chi2r_best = fit.chi2r
    assert chi2r_best < 2.0

    r = chisurf.core.fitting.sample.walk_mcmc(fit=fit, steps=500, step_size=0.02, temp=1.0, thin=1)
    chi2r = np.asarray(r["chi2r"], dtype=float)

    assert len(chi2r) == 500
    assert np.all(np.isfinite(chi2r))
    # With the inverted acceptance test this reached chi2r ~ 1e6.
    assert np.median(chi2r) < 3.0 * chi2r_best
    assert chi2r.max() < 20.0 * chi2r_best


@pytest.mark.slow
def test_walk_mcmc_reproduces_the_analytic_posterior():
    """For a linear model the sampled width must match ``sigma^2 (X'X)^-1``."""
    np.random.seed(2)
    fit, x = _quadratic_fit()

    names = list(fit.model.parameter_names)
    # Columns must match the order of the free parameters.
    columns = {"c": np.ones_like(x), "a": x**2}
    design = np.column_stack([columns[n] for n in names])
    covariance = SIGMA**2 * np.linalg.inv(design.T @ design)
    analytic_std = np.sqrt(np.diag(covariance))

    best = np.array(fit.model.parameter_values, dtype=float)
    r = chisurf.core.fitting.sample.walk_mcmc(
        fit=fit, steps=20000, step_size=0.02, temp=1.0, thin=1
    )
    samples = np.asarray(r["parameter_values"], dtype=float)
    samples = samples[len(samples) // 5 :]  # discard burn-in

    assert r["acceptance_rate"] > 0.0
    for i, name in enumerate(names):
        # The posterior is centred on the least-squares solution ...
        assert samples[:, i].mean() == pytest.approx(best[i], abs=analytic_std[i])
        # ... and has the analytic width. A stuck chain would give ~0, the
        # unthinned/rejection-skipping chain a biased width.
        assert samples[:, i].std() == pytest.approx(analytic_std[i], rel=0.35)


def test_walk_mcmc_warmup_tunes_a_badly_scaled_step_size():
    """The warm-up must rescue a ``step_size`` that is far too wide.

    ``step_size`` is relative to the parameter value, so for a well determined
    parameter the default proposal can be orders of magnitude wider than the
    posterior and virtually nothing is accepted.
    """
    np.random.seed(4)
    fit, x = _quadratic_fit()

    bad_step_size = 0.05  # ~50x the posterior width of 'a'
    unadapted = chisurf.core.fitting.sample.walk_mcmc(
        fit=fit, steps=1500, step_size=bad_step_size, temp=1.0, thin=1, n_adapt=0
    )
    adapted = chisurf.core.fitting.sample.walk_mcmc(
        fit=fit, steps=1500, step_size=bad_step_size, temp=1.0, thin=1
    )

    assert unadapted["acceptance_rate"] < 0.05, "step size was not badly scaled"
    assert adapted["acceptance_rate"] > 5 * unadapted["acceptance_rate"]
    assert 0.1 < adapted["acceptance_rate"] < 0.6

    # ... and the tuned chain still reproduces the analytic posterior.
    names = list(fit.model.parameter_names)
    columns = {"c": np.ones_like(x), "a": x**2}
    design = np.column_stack([columns[n] for n in names])
    analytic_std = np.sqrt(np.diag(SIGMA**2 * np.linalg.inv(design.T @ design)))

    samples = np.asarray(adapted["parameter_values"], dtype=float)
    samples = samples[len(samples) // 5 :]
    for i, _ in enumerate(names):
        assert samples[:, i].std() == pytest.approx(analytic_std[i], rel=0.4)


def test_walk_mcmc_thinning_records_every_nth_state():
    """``thin`` reduces the number of returned states, not the chain length."""
    np.random.seed(3)
    fit, _ = _quadratic_fit()

    r = chisurf.core.fitting.sample.walk_mcmc(fit=fit, steps=200, step_size=0.02, temp=1.0, thin=10)
    assert len(r["chi2r"]) == 20
    assert np.asarray(r["parameter_values"]).shape == (20, fit.model.n_free)
