"""Tests for parameter priors and prior-augmented (MAP) fitting.

Covers three layers:

1. The prior distributions in :mod:`chisurf.core.fitting.priors` -- their log
   density, hard support, least-squares residual contribution and
   (de-)serialisation.
2. The unified :attr:`chisurf.core.parameter.Parameter.prior` view, in which a
   hard bound is the :class:`UniformPrior` special case and a smooth prior both
   stores itself and constrains the optimiser via its support.
3. End-to-end maximum-a-posteriori fitting: a Gaussian prior appended to the
   least-squares objective biases the estimate toward the prior mean, and the
   bias vanishes as the prior widens.
"""

import pathlib

import utils

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import math

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting
import chisurf.core.fitting.fit
import chisurf.core.models
import chisurf.core.models.parse
import chisurf.core.parameter
from chisurf.core.fitting import priors as _priors

# --------------------------------------------------------------------------
# 1. Prior distributions
# --------------------------------------------------------------------------


def test_uniform_prior_is_a_bound():
    p = _priors.UniformPrior(1.0, 3.0)
    assert p.support() == (1.0, 3.0)
    assert math.isfinite(p.lnpdf(2.0))
    assert p.lnpdf(0.5) == float("-inf")
    assert p.lnpdf(3.5) == float("-inf")
    # A box prior is enforced as a hard bound, not a residual.
    assert p.residuals(2.0).size == 0


def test_uniform_prior_orders_bounds():
    p = _priors.UniformPrior(3.0, 1.0)
    assert p.support() == (1.0, 3.0)


def test_normal_prior_residual_is_tikhonov():
    p = _priors.NormalPrior(mu=2.0, sigma=0.5)
    # residual == (x - mu) / sigma
    assert p.residuals(3.0) == pytest.approx(np.array([2.0]))
    assert p.residuals(2.0) == pytest.approx(np.array([0.0]))
    # unbounded support -> soft pull only
    assert p.support() == (float("-inf"), float("inf"))
    # lnpdf maximal at the mean
    assert p.lnpdf(2.0) > p.lnpdf(2.5)


def test_normal_prior_lnpdf_matches_scipy_free_formula():
    mu, sigma, x = 1.0, 2.0, 3.5
    p = _priors.NormalPrior(mu, sigma)
    expected = -0.5 * ((x - mu) / sigma) ** 2 - math.log(sigma) - 0.5 * math.log(2.0 * math.pi)
    assert p.lnpdf(x) == pytest.approx(expected)


def test_normal_prior_rejects_bad_sigma():
    with pytest.raises(ValueError):
        _priors.NormalPrior(0.0, 0.0)


def test_truncated_normal_prior_supports_and_pulls():
    p = _priors.TruncatedNormalPrior(mu=0.0, sigma=1.0, lb=-1.0, ub=2.0)
    assert p.support() == (-1.0, 2.0)
    assert p.lnpdf(3.0) == float("-inf")
    assert p.residuals(1.0) == pytest.approx(np.array([1.0]))


def test_half_normal_prior_positive_support():
    p = _priors.HalfNormalPrior(sigma=2.0, loc=0.0)
    assert p.support() == (0.0, float("inf"))
    assert p.lnpdf(-0.1) == float("-inf")
    assert p.residuals(4.0) == pytest.approx(np.array([2.0]))
    assert p.mode() == 0.0


def test_lognormal_prior():
    p = _priors.LogNormalPrior(mu=0.0, sigma=0.5)
    assert p.support() == (0.0, float("inf"))
    assert p.lnpdf(-1.0) == float("-inf")
    # residual == (ln x - mu) / sigma
    assert p.residuals(math.e) == pytest.approx(np.array([1.0 / 0.5]))


def test_exponential_prior_deviance_residual():
    p = _priors.ExponentialPrior(scale=2.0, loc=0.0)
    assert p.support() == (0.0, float("inf"))
    # negative log density linear in x -> generic deviance residual sqrt(2x/scale)
    r = p.residuals(4.0)
    assert r == pytest.approx(np.array([math.sqrt(2.0 * 4.0 / 2.0)]))


@pytest.mark.parametrize(
    "prior",
    [
        _priors.UniformPrior(-1.0, 4.0),
        _priors.NormalPrior(1.5, 0.3),
        _priors.TruncatedNormalPrior(1.0, 0.5, 0.0, 2.0),
        _priors.HalfNormalPrior(2.0, 0.1),
        _priors.LogNormalPrior(-0.5, 0.8),
        _priors.ExponentialPrior(3.0, 0.0),
    ],
)
def test_prior_state_roundtrip(prior):
    state = prior.get_state()
    import json

    json.dumps(state)  # must be JSON-serialisable
    restored = _priors.prior_from_state(state)
    assert type(restored) is type(prior)
    assert restored.get_state() == state


def test_prior_from_state_none_and_unknown():
    assert _priors.prior_from_state(None) is None
    assert _priors.prior_from_state({}) is None
    assert _priors.prior_from_state({"kind": "does-not-exist"}) is None


# --------------------------------------------------------------------------
# 2. Parameter.prior unified view (bounds are priors)
# --------------------------------------------------------------------------


def test_active_bound_surfaces_as_uniform_prior():
    p = chisurf.core.parameter.Parameter(value=2.0, bounds_on=True, lb=1.0, ub=3.0)
    prior = p.prior
    assert isinstance(prior, _priors.UniformPrior)
    assert prior.support() == (1.0, 3.0)


def test_no_bound_no_prior_is_none():
    p = chisurf.core.parameter.Parameter(value=2.0)
    assert p.prior is None


def test_setting_uniform_prior_sets_bounds():
    p = chisurf.core.parameter.Parameter(value=2.0)
    p.prior = _priors.UniformPrior(0.0, 5.0)
    assert p.bounds_on is True
    assert tuple(p.bounds) == (0.0, 5.0)
    # Round-trips back to a UniformPrior view.
    assert isinstance(p.prior, _priors.UniformPrior)


def test_setting_smooth_prior_keeps_object_and_unbounds():
    p = chisurf.core.parameter.Parameter(value=2.0)
    p.prior = _priors.NormalPrior(2.0, 0.5)
    assert isinstance(p.prior, _priors.NormalPrior)
    # Gaussian support is unbounded -> optimiser is not hard-bounded.
    assert p.bounds_on is False


def test_truncated_prior_also_bounds_optimiser():
    p = chisurf.core.parameter.Parameter(value=1.0)
    p.prior = _priors.TruncatedNormalPrior(1.0, 0.5, 0.0, 2.0)
    assert p.bounds_on is True
    assert tuple(p.bounds) == (0.0, 2.0)


def test_clearing_prior():
    p = chisurf.core.parameter.Parameter(value=2.0)
    p.prior = _priors.NormalPrior(2.0, 0.5)
    p.prior = None
    assert p.prior is None
    assert p.bounds_on is False


def test_prior_construction_kwarg():
    p = chisurf.core.parameter.Parameter(value=2.0, prior=_priors.NormalPrior(2.0, 0.5))
    assert isinstance(p.prior, _priors.NormalPrior)


def test_parameter_state_roundtrip_with_prior():
    p1 = chisurf.core.parameter.Parameter(value=2.0)
    p1.prior = _priors.NormalPrior(2.0, 0.5)
    state = p1.get_state()
    assert "prior" in state

    p2 = chisurf.core.parameter.Parameter(value=0.0)
    p2.set_state(state)
    assert isinstance(p2.prior, _priors.NormalPrior)
    assert p2.prior.get_state() == p1.prior.get_state()


def test_prior_lives_on_port_and_survives_pickle():
    """The prior spec is stored on the chinet Port and round-trips via port JSON."""
    p1 = chisurf.core.parameter.Parameter(value=2.0)
    p1.prior = _priors.LogNormalPrior(mu=0.0, sigma=0.4)
    # It is backed by the port, not a side attribute.
    assert isinstance(p1._port.prior, dict)
    assert p1._port.prior["kind"] == "lognormal"

    # __getstate__/__setstate__ (the port-JSON path used for pickling) carries it.
    p2 = chisurf.core.parameter.Parameter()
    p2.__setstate__(p1.__getstate__())
    assert isinstance(p2.prior, _priors.LogNormalPrior)
    assert p2.prior.get_state() == p1.prior.get_state()


def test_port_prior_roundtrip():
    """The port (IMP.bff, chinet's successor) carries a prior dict through
    its document round-trip.
    """
    from chisurf.core import nodes

    port = nodes._bff.GraphPort(value=1.0, name="p")
    assert port.prior is None
    port.prior = {"kind": "normal", "mu": 1.0, "sigma": 0.5}
    js = port.get_json()
    port2 = nodes._bff.GraphPort(value=0.0, name="p2")
    port2.read_json(js)
    assert port2.prior == {"kind": "normal", "mu": 1.0, "sigma": 0.5}


# --------------------------------------------------------------------------
# 3. End-to-end MAP fitting
# --------------------------------------------------------------------------


def _make_linear_fit(a_value=1.2, c_value=3.1, n_points=32):
    x = np.linspace(0.0, 10.0, n_points)
    y = c_value + a_value * x
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.model.func = "c+a*x"
    fit.fit_range = 0, len(fit.model.y) - 1
    fit.model.update()
    return fit


def test_plain_lsq_recovers_truth():
    fit = _make_linear_fit()
    fit.run()
    fit.run()
    assert fit.model.parameter_dict["a"].value == pytest.approx(1.2, abs=1e-4)
    assert fit.model.parameter_dict["c"].value == pytest.approx(3.1, abs=1e-4)


def test_tight_gaussian_prior_biases_estimate():
    """A strong Gaussian prior far from the truth pulls the MAP estimate."""
    fit = _make_linear_fit(a_value=1.2)
    a = fit.model.parameter_dict["a"]
    # Very tight prior centred at 2.0 (true value is 1.2).
    a.prior = _priors.NormalPrior(mu=2.0, sigma=1e-3)
    fit.run()
    fit.run()
    # The estimate is dragged strongly toward the prior mean.
    assert fit.model.parameter_dict["a"].value == pytest.approx(2.0, abs=0.05)


def test_loose_gaussian_prior_recovers_truth():
    """A very wide prior contributes negligibly; the data wins."""
    fit = _make_linear_fit(a_value=1.2)
    a = fit.model.parameter_dict["a"]
    a.prior = _priors.NormalPrior(mu=2.0, sigma=1e6)
    fit.run()
    fit.run()
    assert fit.model.parameter_dict["a"].value == pytest.approx(1.2, abs=1e-3)


def test_prior_does_not_change_reported_chi2_shape():
    """Reported chi² reflects data misfit only (priors excluded from get_chi2)."""
    fit = _make_linear_fit(a_value=1.2)
    a = fit.model.parameter_dict["a"]
    a.prior = _priors.NormalPrior(mu=2.0, sigma=1e-3)
    fit.run()
    fit.run()
    # get_chi2 excludes priors, so the reported residual vector length equals
    # the number of data points in the fit window (no appended prior residual).
    model = fit.model
    wres_data = chisurf.core.fitting.fit.get_wres([], model, include_priors=False)
    wres_map = chisurf.core.fitting.fit.get_wres([], model, include_priors=True)
    assert len(wres_map) == len(wres_data) + 1


def test_lnprior_uses_parameter_priors():
    fit = _make_linear_fit(a_value=1.2)
    a = fit.model.parameter_dict["a"]
    a.prior = _priors.NormalPrior(mu=0.0, sigma=1.0)
    values = fit.model.parameter_values
    lp = chisurf.core.fitting.fit.lnprior(values, fit)
    # Finite and equals the Gaussian log density of parameter 'a' at its value
    # (the other free parameter has no prior and contributes nothing).
    names = fit.model.parameter_names
    a_idx = names.index("a")
    expected = _priors.NormalPrior(0.0, 1.0).lnpdf(values[a_idx])
    assert lp == pytest.approx(expected)


def test_lnprior_legacy_bounds_branch():
    bounds = [(0.0, 2.0), (None, 1.0)]
    assert chisurf.core.fitting.fit.lnprior([1.0, 0.5], fit=None, bounds=bounds) == 0.0
    assert chisurf.core.fitting.fit.lnprior([3.0, 0.5], fit=None, bounds=bounds) == float("-inf")


# --------------------------------------------------------------------------
# 4. Callback priors (most general) + conjugate combination
# --------------------------------------------------------------------------


def test_callable_prior_matches_gaussian():
    """A callback reproducing a Gaussian log-density matches NormalPrior."""
    mu, sigma = 2.0, 0.5
    cp = _priors.CallablePrior(lambda x: -0.5 * ((x - mu) / sigma) ** 2, mode=mu)
    ref = _priors.NormalPrior(mu, sigma)
    for x in (1.0, 2.0, 2.5, 3.3):
        # lnpdf differs only by the (constant) normalisation the callback omits.
        assert (cp.lnpdf(x) - cp.lnpdf(mu)) == pytest.approx(ref.lnpdf(x) - ref.lnpdf(mu))
    # Generic deviance residual equals the Gaussian's (x-mu)/sigma in magnitude.
    assert abs(cp.residuals(3.0)[0]) == pytest.approx(abs(ref.residuals(3.0)[0]))


def test_callable_prior_explicit_residual():
    cp = _priors.CallablePrior(lambda x: -0.5 * x * x, residual=lambda x: 2.0 * x)
    assert cp.residuals(1.5) == pytest.approx(np.array([3.0]))


def test_as_prior_wraps_callable():
    pr = _priors.as_prior(lambda x: -abs(x))
    assert isinstance(pr, _priors.CallablePrior)
    assert _priors.as_prior(None) is None
    assert isinstance(
        _priors.as_prior({"kind": "normal", "mu": 0.0, "sigma": 1.0}), _priors.NormalPrior
    )


def test_normal_times_normal_precision_weighted():
    a = _priors.NormalPrior(mu=0.0, sigma=1.0)
    b = _priors.NormalPrior(mu=2.0, sigma=1.0)
    c = a * b
    assert isinstance(c, _priors.NormalPrior)
    # Equal precisions -> mean is the average; sigma shrinks by sqrt(2).
    assert c.mu == pytest.approx(1.0)
    assert c.sigma == pytest.approx(1.0 / math.sqrt(2.0))


def test_gamma_and_beta_conjugate_combination():
    g = _priors.GammaPrior(2.0, 1.0) * _priors.GammaPrior(3.0, 2.0)
    assert isinstance(g, _priors.GammaPrior)
    assert (g.alpha, g.beta) == (4.0, 3.0)
    b = _priors.BetaPrior(2.0, 2.0) * _priors.BetaPrior(3.0, 1.0)
    assert isinstance(b, _priors.BetaPrior)
    assert (b.alpha, b.beta) == (4.0, 2.0)


def test_normal_times_uniform_is_truncated():
    c = _priors.NormalPrior(0.0, 1.0) * _priors.UniformPrior(-1.0, 1.0)
    assert isinstance(c, _priors.TruncatedNormalPrior)
    assert c.support() == (-1.0, 1.0)


def test_generic_product_prior_sums_and_concatenates():
    a = _priors.LogNormalPrior(0.0, 0.5)
    b = _priors.NormalPrior(1.0, 0.3)
    prod = a * b
    assert isinstance(prod, _priors.ProductPrior)
    # log density adds
    assert prod.lnpdf(1.2) == pytest.approx(a.lnpdf(1.2) + b.lnpdf(1.2))
    # residuals concatenate (one per component)
    r = prod.residuals(1.2)
    assert r.size == 2
    # support intersects (lognormal (0,inf) with normal (-inf,inf))
    assert prod.support() == (0.0, float("inf"))
    # round-trips (both components are serialisable)
    assert type(_priors.prior_from_state(prod.get_state())) is _priors.ProductPrior


def test_callback_prior_is_runtime_only_on_parameter():
    p = chisurf.core.parameter.Parameter(value=2.0)
    p.prior = lambda x: -0.5 * ((x - 2.0) / 0.5) ** 2
    assert isinstance(p.prior, _priors.CallablePrior)
    # Not persisted to the port (cannot be serialised).
    assert p._port.prior is None
    # Its state does not survive a get_state round-trip (runtime-only).
    state = p.get_state()
    assert "prior" not in state


def test_callback_prior_enters_map_objective():
    """A callback prior contributes residuals to the fit like a distribution prior."""
    fit = _make_linear_fit(a_value=1.2)
    a = fit.model.parameter_dict["a"]
    # Tight Gaussian-shaped callback centred at 2.0 (true value 1.2).
    a.prior = _priors.CallablePrior(lambda x: -0.5 * ((x - 2.0) / 1e-3) ** 2, mode=2.0)
    fit.run()
    fit.run()
    assert fit.model.parameter_dict["a"].value == pytest.approx(2.0, abs=0.05)


# --------------------------------------------------------------------------
# 4. Prior / posterior reporting (the fit summary shown in the Info panel)
# --------------------------------------------------------------------------


def test_prior_summary_separates_informative_from_bounds():
    """A bound is a uniform prior, but it contributes nothing to the objective."""
    fit = _make_linear_fit()
    a = fit.model.parameter_dict["a"]
    c = fit.model.parameter_dict["c"]
    a.prior = _priors.NormalPrior(mu=2.0, sigma=0.5)
    c.bounds = (0.0, 10.0)
    c.bounds_on = True

    summary = {e["name"]: e for e in fit.prior_summary()}

    assert summary["a"]["informative"] is True
    assert "NormalPrior" in summary["a"]["description"]
    assert summary["c"]["informative"] is False


def test_posterior_summary_uses_the_covariance_when_no_scan_exists():
    fit = _make_linear_fit()
    fit.run()
    fit.run()

    rows = {e["name"]: e for e in fit.posterior_summary()}
    a = rows["a"]

    assert a["method"] == "laplace"
    assert a["low"] < a["value"] < a["high"]
    err = fit.model.parameter_dict["a"].error_estimate
    assert a["high"] - a["low"] == pytest.approx(2.0 * err, rel=1e-6)


def test_posterior_summary_skips_fixed_parameters():
    fit = _make_linear_fit()
    fit.run()
    fit.model.parameter_dict["c"].fixed = True

    assert "c" not in {e["name"] for e in fit.posterior_summary()}


def test_posterior_summary_prefers_a_scan_over_the_covariance():
    """A chi2 scan gives a profile interval, which may be asymmetric."""
    fit = _make_linear_fit()
    fit.run()
    fit.run()
    a = fit.model.parameter_dict["a"]
    a.scan_result = {
        "parameter_values": np.linspace(1.0, 1.4, 21),
        "chi2r": 1.0 + ((np.linspace(1.0, 1.4, 21) - 1.2) / 0.05) ** 2,
        "chi2r_min": 1.0,
        "v0": 1.2,
        "nu": 30,
        "n_extra_params": 1,
    }

    row = {e["name"]: e for e in fit.posterior_summary()}["a"]

    assert row["method"] == "profile"
    assert row["low"] < 1.2 < row["high"]


def test_fit_str_reports_priors_and_intervals():
    fit = _make_linear_fit()
    fit.model.parameter_dict["a"].prior = _priors.NormalPrior(mu=2.0, sigma=0.5)
    fit.run()
    fit.run()

    text = str(fit)

    assert "Priors" in text
    assert "NormalPrior" in text
    # An informative prior makes the optimum a posterior mode, not just an MLE.
    assert "posterior (MAP)" in text
    assert "covariance" in text


def test_fit_str_calls_it_a_likelihood_interval_without_an_informative_prior():
    """Bounds alone do not make an interval Bayesian; the wording must not claim it."""
    fit = _make_linear_fit()
    fit.run()
    fit.run()

    text = str(fit)

    assert "likelihood" in text
    assert "posterior (MAP)" not in text
