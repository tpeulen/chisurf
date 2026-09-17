"""Reusing a chain under a different prior (Pareto-smoothed importance sampling).

Changing a prior changes the posterior but not the likelihood, so draws from one
posterior can be reweighted to the other by a ratio of two prior densities --
no model evaluation at all. The risk is the usual one for importance sampling:
if the new prior favours somewhere the chain did not go, a few draws carry all
the weight and the answer is noise wearing a confident face.

These tests pin both halves: that the reweighted answer is *correct* where it
should be (against a closed form, since a linear model's posterior is exactly
Gaussian), and that ``pareto_k`` *refuses* where it should.
"""

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.fitting.sample
import chisurf.core.models.parse
from chisurf.core.fitting import reweight as rw
from chisurf.core.fitting.priors import NormalPrior


def _fit(seed=0, npts=96, sigma=0.05):
    """Return a converged linear fit, whose posterior is exactly Gaussian."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.5, 3.0, npts)
    y = 3.1 + 1.2 * x + 0.4 * x**2 + rng.normal(0.0, sigma, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, sigma))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = "c+a*x+b*x**2"
    fit.model.find_parameters()
    fit.run()
    return fit


def _exact_posterior(fit, name, prior):
    """Return the exact ``(mean, sd)`` of ``name`` after adding a Gaussian prior.

    For an exactly Gaussian posterior, a Gaussian prior on one coordinate adds
    ``1/sigma^2`` to that diagonal of the precision and ``mu/sigma^2`` to the
    information vector. Everything else follows from the algebra, so this is a
    ground truth rather than a second approximation.
    """
    model = fit._model
    # ``parameter_names`` carries the group's ``fit:name`` prefixes while the
    # Parameter objects keep their short names, so index the two in parallel
    # rather than matching one against the other.
    names = [str(n).split(":")[-1] for n in model.parameter_names]
    params = list(model.parameters)
    cov, used = chisurf.core.fitting.fit.covariance_matrix(fit, model=model)
    cov = np.atleast_2d(np.asarray(cov, dtype=float))
    used_names = [names[i] for i in used]
    mean = np.array([float(params[i].value) for i in used])
    import IMP.bff

    form = IMP.bff.InferenceCanonicalForm.from_moments(used_names, mean, cov.ravel())
    # The prior is one more factor, N(mu, sigma^2) over ``name``: multiplying
    # adds 1/sigma^2 to that diagonal of K and mu/sigma^2 to h.
    prior_factor = IMP.bff.InferenceCanonicalForm.from_linear_gaussian(
        name, [], prior.mu, prior.sigma, []
    )
    updated = form.product(prior_factor).marginal([name])
    return float(updated.get_mean()[0]), float(np.sqrt(updated.get_covariance()[0]))


# -- the generalised-Pareto fit -------------------------------------------


def test_the_pareto_fit_recovers_a_known_shape():
    """The estimator has to work before anything built on it can."""
    rng = np.random.default_rng(0)
    for k_true, sigma_true in ((0.2, 1.0), (0.5, 2.0), (-0.1, 1.5)):
        u = rng.uniform(size=4000)
        # Inverse CDF of the generalised Pareto.
        x = np.sort(sigma_true * np.expm1(-k_true * np.log1p(-u)) / k_true)
        k, sigma = rw.gpd_fit(x)
        assert k == pytest.approx(k_true, abs=0.1)
        assert sigma == pytest.approx(sigma_true, rel=0.2)


def test_a_degenerate_sample_is_refused_not_guessed():
    """Too few points must give ``nan``, not a confident fit."""
    k, sigma = rw.gpd_fit(np.array([1.0, 2.0, 3.0]))
    assert np.isnan(k) and np.isnan(sigma)


# -- the weights ----------------------------------------------------------


def test_equal_ratios_give_equal_weights():
    """The no-change case must be exactly the original sample."""
    lw, k = rw.pareto_smoothed_log_weights(np.zeros(500))
    w = np.exp(lw)
    assert w.sum() == pytest.approx(1.0)
    assert np.allclose(w, 1.0 / 500)
    assert rw.importance_ess(lw) == pytest.approx(500.0, rel=1e-9)


def test_the_effective_sample_size_sees_a_dominated_weight():
    """One draw carrying everything is an ESS of one, whatever the draw count."""
    ratios = np.full(1000, -50.0)
    ratios[0] = 0.0
    assert rw.importance_ess(ratios) == pytest.approx(1.0, abs=1e-6)


def test_excluded_draws_get_no_weight_rather_than_nan():
    """A new prior with hard support will produce ``-inf`` ratios."""
    ratios = np.zeros(200)
    ratios[:50] = -np.inf
    lw, k = rw.pareto_smoothed_log_weights(ratios)
    w = np.exp(lw)
    assert np.all(np.isfinite(w))
    assert np.allclose(w[:50], 0.0)
    assert w.sum() == pytest.approx(1.0)


def test_weights_beyond_the_exponential_range_are_refused_not_ignored():
    """The diagnostic must survive the case it exists for.

    Exceedances computed as ``exp(lw) - exp(cutoff)`` underflow to zero once the
    weights span more than ~700 log units, so a naive implementation reports
    "cannot fit" -- i.e. goes blind -- exactly where the weights are most
    concentrated. It has to return a verdict instead.
    """
    rng = np.random.default_rng(3)
    ratios = rng.standard_cauchy(size=4000) * 500.0
    lw, k = rw.pareto_smoothed_log_weights(ratios)
    assert not np.isnan(k)  # not "undiagnosed"
    assert k > rw.PARETO_K_THRESHOLD  # a refusal
    assert np.exp(lw).sum() == pytest.approx(1.0)

    out = rw.reweight(rng.normal(size=(4000, 2)), ratios)
    assert not out["reliable"]


def test_weighted_quantiles_reduce_to_unweighted_ones():
    """With equal weights it must agree with numpy, or it is a different statistic."""
    rng = np.random.default_rng(1)
    values = rng.normal(size=2000)
    weights = np.ones_like(values)
    for q in (0.025, 0.25, 0.5, 0.75, 0.975):
        assert rw.weighted_quantile(values, weights, q) == pytest.approx(
            float(np.quantile(values, q)), abs=0.02
        )


def _importance_rmse(target_sd, n=2000, seeds=range(80)):
    r"""Return ``(raw, psis)`` RMSE of :math:`E[x^2]` under a narrow proposal.

    Proposal :math:`N(0, 1)`, target :math:`N(0, s)` with :math:`s > 1`, so the
    proposal has lighter tails than the target -- the situation importance
    sampling is bad at and Pareto smoothing exists for. The truth is
    :math:`s^2` exactly, so the error is measurable rather than inferred.
    """
    raw_err, psis_err = [], []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        x = rng.normal(0.0, 1.0, n)
        log_ratios = -0.5 * (x / target_sd) ** 2 + 0.5 * x**2
        w = np.exp(log_ratios - log_ratios.max())
        w /= w.sum()
        raw_err.append(float(w @ x**2) - target_sd**2)
        lw, _ = rw.pareto_smoothed_log_weights(log_ratios)
        psis_err.append(float(np.exp(lw) @ x**2) - target_sd**2)
    return (
        float(np.sqrt(np.mean(np.square(raw_err)))),
        float(np.sqrt(np.mean(np.square(psis_err)))),
    )


def test_smoothing_makes_the_estimate_better_where_it_is_meant_to():
    """What the Pareto step actually buys, measured against a known truth.

    Not "the largest weight gets smaller" -- it often does not, and the
    normalisation can even raise it. The claim is about the *estimator*: fitting
    the tail trades a little bias for a large variance reduction, so the error
    of the reweighted expectation falls.
    """
    raw, psis = _importance_rmse(target_sd=1.6)
    # Measured at a ratio of 0.66; assert a looser bound so this is not brittle.
    assert psis < 0.85 * raw


def test_smoothing_leaves_well_behaved_weights_alone():
    """And it must not *cost* anything where importance sampling already works."""
    raw, psis = _importance_rmse(target_sd=1.05)
    assert psis == pytest.approx(raw, rel=0.05)


# -- the claim ------------------------------------------------------------


def test_reweighting_matches_the_exact_posterior_under_the_new_prior():
    """The whole point: a chain sampled under one prior answers for another.

    The model is linear, so the posterior is exactly Gaussian and adding a
    Gaussian prior has a closed form. The reweighted chain must reproduce it.
    """
    np.random.seed(0)
    fit = _fit()
    c = [p for p in fit.model.parameters if p.name == "c"][0]
    c_hat, sd = float(c.value), float(c.error_estimate)

    chain = chisurf.core.fitting.sample.sample_differential_evolution(
        fit=fit, steps=3000, thin=1, seed=1
    )

    # Tight enough to move the answer several posterior widths, loose enough to
    # still overlap the draws -- the regime reweighting is for.
    prior = NormalPrior(mu=c_hat + 3.0 * sd, sigma=0.5 * sd)
    want_mean, want_sd = _exact_posterior(fit, "c", prior)

    out = rw.reweight_prior(chain, {"c": prior}, model=fit.model)
    assert out["reliable"]
    assert out["changed"] == ["c"]
    entry = [e for e in out["parameters"] if e["name"].split(":")[-1] == "c"][0]

    assert entry["mean"] == pytest.approx(want_mean, abs=0.25 * want_sd)
    assert entry["sd"] == pytest.approx(want_sd, rel=0.25)
    # And it genuinely moved -- otherwise the test would pass on a no-op. The
    # shift is measured in units of the *new* width, since that is the scale the
    # agreement above is asserted at.
    assert abs(want_mean - c_hat) > 3.0 * want_sd


def test_reweighting_agrees_with_sampling_under_the_prior_directly():
    """Against the expensive answer it replaces, not only against the algebra."""
    np.random.seed(1)
    fit = _fit(seed=3)
    c = [p for p in fit.model.parameters if p.name == "c"][0]
    c_hat, sd = float(c.value), float(c.error_estimate)
    prior = NormalPrior(mu=c_hat + 1.0 * sd, sigma=1.0 * sd)

    flat_chain = chisurf.core.fitting.sample.sample_differential_evolution(
        fit=fit, steps=3000, thin=1, seed=2
    )
    cheap = rw.reweight_prior(flat_chain, {"c": prior}, model=fit.model)
    assert cheap["reliable"]

    # Now the expensive way: put the prior on and sample again.
    c.prior = prior
    try:
        direct = chisurf.core.fitting.sample.sample_differential_evolution(
            fit=fit, steps=3000, thin=1, seed=3
        )
    finally:
        c.prior = None
    i = list(direct["parameter_names"]).index("c")
    drawn = np.asarray(direct["parameter_values"])[:, i]
    drawn = drawn[len(drawn) // 2 :]

    entry = [e for e in cheap["parameters"] if e["name"].split(":")[-1] == "c"][0]
    assert entry["mean"] == pytest.approx(float(drawn.mean()), abs=0.3 * sd)
    assert entry["sd"] == pytest.approx(float(drawn.std(ddof=1)), rel=0.35)


def test_reweighting_evaluates_no_model_at_all():
    """The reason to do this instead of sampling again."""
    np.random.seed(2)
    fit = _fit()
    chain = chisurf.core.fitting.sample.sample_differential_evolution(
        fit=fit, steps=400, thin=1, seed=4
    )
    c = [p for p in fit.model.parameters if p.name == "c"][0]
    prior = NormalPrior(mu=float(c.value), sigma=float(c.error_estimate))

    calls = [0]
    model = fit.model
    original = model._update_model

    def counting(*a, _o=original, **k):
        calls[0] += 1
        return _o(*a, **k)

    model._update_model = counting
    try:
        out = rw.reweight_prior(chain, {"c": prior}, model=fit.model)
    finally:
        model._update_model = original
    assert out["parameters"]
    assert calls[0] == 0


def test_a_prior_the_chain_never_visited_is_refused():
    """The diagnostic that makes this safe to expose.

    A prior far out in the tail is exactly where importance sampling breaks:
    the estimate would be built from a handful of draws. It must say so rather
    than return a tidy wrong number.
    """
    np.random.seed(3)
    fit = _fit()
    chain = chisurf.core.fitting.sample.sample_differential_evolution(
        fit=fit, steps=2000, thin=1, seed=5
    )
    c = [p for p in fit.model.parameters if p.name == "c"][0]
    sd = float(c.error_estimate)
    far = NormalPrior(mu=float(c.value) + 40.0 * sd, sigma=0.5 * sd)

    out = rw.reweight_prior(chain, {"c": far}, model=fit.model)
    assert not out["reliable"]
    assert out["pareto_k"] > rw.PARETO_K_THRESHOLD
    assert any("Pareto k" in w for w in out["warnings"])


def test_removing_a_prior_returns_to_the_likelihood_posterior():
    """Reweighting must work in the other direction too."""
    np.random.seed(4)
    fit = _fit(seed=6)
    c = [p for p in fit.model.parameters if p.name == "c"][0]
    c_hat, sd = float(c.value), float(c.error_estimate)

    # Sample *with* a prior, then reweight it away.
    prior = NormalPrior(mu=c_hat + 1.0 * sd, sigma=1.2 * sd)
    c.prior = prior
    try:
        chain = chisurf.core.fitting.sample.sample_differential_evolution(
            fit=fit, steps=3000, thin=1, seed=7
        )
    finally:
        c.prior = None

    out = rw.reweight_prior(chain, {"c": None}, model=None, old_priors={"c": prior})
    assert out["reliable"]
    entry = [e for e in out["parameters"] if e["name"].split(":")[-1] == "c"][0]
    # Back to the likelihood optimum, which the prior had pulled away from.
    assert entry["mean"] == pytest.approx(c_hat, abs=0.4 * sd)


def test_an_unchanged_prior_is_a_no_op_and_says_so():
    """Reweighting to the same prior must not silently look like new work."""
    np.random.seed(5)
    fit = _fit()
    chain = chisurf.core.fitting.sample.sample_differential_evolution(
        fit=fit, steps=300, thin=1, seed=8
    )
    out = rw.reweight_prior(chain, {"c": None}, model=fit.model)
    assert out["changed"] == []
    assert any("no prior actually changed" in w for w in out["warnings"])
    assert out["ess"] == pytest.approx(out["n_draws"], rel=1e-6)


def test_an_unknown_parameter_is_refused():
    """Ignoring the name would answer a different question."""
    np.random.seed(6)
    fit = _fit()
    chain = chisurf.core.fitting.sample.sample_differential_evolution(
        fit=fit, steps=200, thin=1, seed=9
    )
    with pytest.raises(KeyError):
        rw.reweight_prior(chain, {"nope": NormalPrior(mu=0.0, sigma=1.0)}, model=fit.model)


# -- reachability ---------------------------------------------------------


class _State:
    """Minimal stand-in for the server's session state."""

    def __init__(self, fits):
        """Hold the list of fits the service resolves against."""
        self.fits = fits


def _sampled_fit(tmp_path, monkeypatch, seed=0):
    """Return a fit that has been through ``sample_fit``, so it carries a chain."""
    import chisurf.macros.core_fit

    monkeypatch.setattr(
        chisurf.macros.core_fit,
        "save_project",
        lambda target_path, project_name="project", **kw: None,
    )
    np.random.seed(seed)
    fit = _fit(seed=seed)
    chisurf.core.fitting.fit.sample_fit(
        fit=fit,
        target_directory=str(tmp_path),
        method="de",
        steps=1200,
        thin=1,
        n_runs=2,
    )
    return fit


def test_sampling_leaves_the_draws_behind_not_only_their_summary(tmp_path, monkeypatch):
    """Reweighting needs the points; a summary cannot be reweighted at any price."""
    fit = _sampled_fit(tmp_path, monkeypatch)
    chain = fit.sampling_chain
    assert isinstance(chain, dict)
    assert list(chain["parameter_names"]) == list(fit.model.parameter_names)
    values = np.asarray(chain["parameter_values"])
    assert values.ndim == 2
    assert values.shape[1] == len(chain["parameter_names"])
    assert values.shape[0] > 0
    # The burn-in has already been dropped, so the draws are usable as they are.
    assert chain["burn_in"] == fit.sampling_diagnostics["burn_in"]


def test_the_rpc_reweights_a_stored_chain(tmp_path, monkeypatch):
    """The whole point has to be reachable, not merely importable."""
    import json

    from chisurf.server.services import fits as fit_service

    fit = _sampled_fit(tmp_path, monkeypatch, seed=1)
    a = [p for p in fit.model.parameters if p.name == "a"][0]
    state = _State([fit])

    r = fit_service.fit_reweight_prior(
        state,
        fit_index=0,
        priors={
            "a": {
                "kind": "normal",
                "mu": float(a.value) + float(a.error_estimate),
                "sigma": 2.0 * float(a.error_estimate),
            }
        },
    )
    assert r["ok"], r
    assert r["changed"] == ["a"]
    assert r["reliable"]
    assert 0.0 < r["ess"] <= r["n_draws"]
    # And the payload survives the trip to JSON -- pareto_k is deliberately
    # non-finite in the failure cases, which json.dumps would not accept.
    json.loads(json.dumps(r))


def test_the_rpc_refuses_a_fit_that_was_never_sampled():
    """There is nothing to reweight, and inventing an answer would be worse."""
    from chisurf.server.services import fits as fit_service

    fit = _fit()
    r = fit_service.fit_reweight_prior(
        _State([fit]),
        fit_index=0,
        priors={"a": {"kind": "normal", "mu": 1.0, "sigma": 1.0}},
    )
    assert not r["ok"]
    assert "sampling job" in r["error"]


def test_the_api_reweights_in_process(tmp_path, monkeypatch):
    """``ChiSurfAPI.reweight_prior`` is the surface a macro or the console uses."""
    import chisurf as cs
    from chisurf.core.api import ChiSurfAPI

    fit = _sampled_fit(tmp_path, monkeypatch, seed=2)
    monkeypatch.setattr(cs, "fits", [fit], raising=False)
    monkeypatch.setattr(cs, "cs", None, raising=False)

    a = [p for p in fit.model.parameters if p.name == "a"][0]
    api = ChiSurfAPI(mode="local")
    r = api.reweight_prior(
        {"a": {"kind": "normal", "mu": float(a.value), "sigma": float(a.error_estimate)}},
        fit_index=0,
    )
    assert r["ok"], r
    entry = [e for e in r["parameters"] if e["name"].split(":")[-1] == "a"][0]
    assert np.isfinite(entry["mean"]) and np.isfinite(entry["sd"])
    # A prior centred on the optimum tightens the answer rather than moving it.
    assert entry["mean"] == pytest.approx(float(a.value), abs=0.5 * float(a.error_estimate))
    assert entry["sd"] < float(a.error_estimate)
