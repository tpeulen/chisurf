"""Dependence that a correlation coefficient cannot see.

The posterior graph shaded its edges by ``|r|``, which is the whole story only
for a Gaussian. Two parameters lying on a banana -- the ordinary shape when a
lifetime trades against an amplitude near a bound -- have ``r ~ 0`` and
determine each other almost completely, and the old view drew no edge between
them at all. These tests pin the estimator against cases whose answer is known
by construction, and pin the two ways it can lie: claiming dependence that is
only estimator bias, and claiming independence it never measured.
"""
import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse
from chisurf.core.fitting import dependence as D
from chisurf.core.fitting import graphview as gv


def _ar1(n, rho, rng):
    """Return an AR(1) series: an MCMC chain's autocorrelation, in miniature."""
    e = rng.normal(size=n)
    x = np.empty(n)
    x[0] = e[0]
    for i in range(1, n):
        x[i] = rho * x[i - 1] + np.sqrt(1.0 - rho ** 2) * e[i]
    return x


# -- the estimator --------------------------------------------------------

@pytest.mark.parametrize("n", [200, 1000, 4000])
def test_independent_variables_are_not_called_dependent(n):
    """The plug-in estimator is positively biased; the null must absorb it."""
    rng = np.random.default_rng(n)
    d = D.dependence(rng.normal(size=n), rng.normal(size=n))
    assert not d["dependent"]
    assert not d["nonlinear"]


@pytest.mark.parametrize("rho", [0.3, 0.6, 0.9])
def test_for_a_gaussian_it_reproduces_the_correlation(rho):
    """``r_I`` equals ``|r|`` exactly for a Gaussian.

    That equality is what makes the two comparable, and a disagreement between
    them meaningful.
    """
    rng = np.random.default_rng(int(rho * 100))
    n = 8000
    a = rng.normal(size=n)
    b = rho * a + np.sqrt(1.0 - rho ** 2) * rng.normal(size=n)
    d = D.dependence(a, b)
    assert d["dependent"]
    assert d["dependence"] == pytest.approx(abs(d["pearson"]), abs=0.05)
    # Agreeing with |r| is precisely the case that must NOT be flagged.
    assert not d["nonlinear"]


@pytest.mark.parametrize("noise", [0.01, 0.1, 0.3])
def test_the_banana_a_correlation_coefficient_calls_independent(noise):
    """The case the whole measure exists for."""
    rng = np.random.default_rng(11)
    n = 8000
    t = rng.normal(size=n)
    u = t ** 2 + noise * rng.normal(size=n)
    d = D.dependence(t, u)
    assert abs(d["pearson"]) < 0.1        # a correlation matrix sees nothing
    assert d["dependence"] > 0.7          # yet they nearly determine each other
    assert d["dependent"] and d["nonlinear"]
    assert "not linearly" in d["note"]


def test_a_ring_is_dependence_too():
    """Non-monotone as well as non-linear: rank correlation would miss this."""
    rng = np.random.default_rng(3)
    n = 8000
    theta = rng.uniform(0.0, 2.0 * np.pi, n)
    radius = 1.0 + 0.08 * rng.normal(size=n)
    d = D.dependence(radius * np.cos(theta), radius * np.sin(theta))
    assert abs(d["pearson"]) < 0.1
    assert d["dependence"] > 0.5
    assert d["nonlinear"]


@pytest.mark.parametrize("rho", [0.8, 0.95])
def test_an_autocorrelated_chain_does_not_manufacture_dependence(rho):
    """Permuting destroys the autocorrelation as well as the dependence.

    Without thinning the null describes a far more informative sample than the
    one in hand: measured on independent AR(1) columns, the raw estimator called
    them dependent 7 times in 12 near an effective size of 100. Two chains that
    share nothing must never come out coupled however sticky they are.
    """
    rng = np.random.default_rng(int(rho * 1000))
    for trial in range(6):
        d = D.dependence(_ar1(4000, rho, rng), _ar1(4000, rho, rng), seed=trial)
        assert not d["dependent"], f"false positive at rho={rho}, trial {trial}"


def test_thinning_still_finds_real_dependence_in_a_sticky_chain():
    """Thinning must cost precision, not the signal."""
    rng = np.random.default_rng(5)
    t = _ar1(4000, 0.9, rng)
    u = t ** 2 + 0.1 * _ar1(4000, 0.9, rng)
    d = D.dependence(t, u)
    assert d["stride"] > 1.0
    assert d["dependent"] and d["nonlinear"]
    assert d["dependence"] > 0.6


def test_the_verdict_is_reproducible():
    """A diagnostic that changes its mind on identical data is not one."""
    rng = np.random.default_rng(0)
    x = rng.normal(size=2000)
    y = x ** 2 + 0.2 * rng.normal(size=2000)
    first = D.dependence(x, y)
    second = D.dependence(x, y)
    assert first["mi"] == second["mi"]
    assert first["nonlinear"] == second["nonlinear"]


def test_too_few_draws_is_unknown_not_independent():
    """``nan`` and ``0`` are opposite claims."""
    rng = np.random.default_rng(0)
    d = D.dependence(rng.normal(size=8), rng.normal(size=8))
    assert np.isnan(d["dependence"])
    assert not d["dependent"]
    assert "too few" in d["note"]


def test_mismatched_lengths_raise_rather_than_truncate():
    """Silently zipping two different chains would compare unrelated draws."""
    with pytest.raises(ValueError):
        D.mutual_information(np.zeros(100), np.zeros(90))


def test_informational_correlation_is_monotone_and_bounded():
    """The map from nats onto the correlation scale."""
    assert D.informational_correlation(0.0) == 0.0
    assert D.informational_correlation(-0.3) == 0.0   # null-subtracted estimates
    assert np.isnan(D.informational_correlation(float("nan")))
    values = [D.informational_correlation(m) for m in (0.1, 0.5, 2.0, 8.0)]
    assert values == sorted(values)
    assert values[-1] < 1.0


def test_an_unmeasurable_pair_is_nan_in_the_matrix_not_zero():
    """A stuck parameter is where "independent" is least likely to be true."""
    rng = np.random.default_rng(0)
    n = 400
    draws = np.column_stack([rng.normal(size=n), np.full(n, 2.5),
                             rng.normal(size=n)])
    values, flags = D.dependence_matrix(draws, n_permutations=8)
    assert np.isnan(values[0, 1]) and np.isnan(values[1, 2])
    assert not flags[0, 1]
    assert values[0, 0] == 1.0


# -- into the view --------------------------------------------------------

def _fit_with_chain(draws, converged=True):
    """Return a converged fit carrying ``draws`` as its posterior."""
    rng = np.random.default_rng(1)
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
    names = list(fit.model.parameter_names)
    n = draws.shape[0]
    fit.sampling_chain = {
        'parameter_names': names,
        'parameter_values': draws,
        'chains': draws.reshape(1, n, draws.shape[1]),
    }
    rhat, ess = (1.001, 2000.0) if converged else (1.9, 30.0)
    fit.sampling_diagnostics = {'parameters': [
        {'name': nm, 'rhat': rhat, 'ess': ess} for nm in names]}
    return fit


def _banana_draws(n=4000, seed=2):
    """Columns 0 and 1 lie on a parabola; column 2 is independent of both."""
    rng = np.random.default_rng(seed)
    t = rng.normal(size=n)
    return np.column_stack([t, t ** 2 + 0.1 * rng.normal(size=n),
                            rng.normal(size=n)])


def test_the_view_draws_an_edge_that_correlation_alone_would_omit():
    """|r| ~ 0.02 is below any sane threshold; the pair is nearly deterministic."""
    fit = _fit_with_chain(_banana_draws())
    names, corr = gv.posterior_correlation(fit)
    assert abs(corr[0, 1]) < 0.15                     # invisible to correlation

    view = gv.correlation_view(fit)
    bent = [e for e in view.edges if e.kind == "dependence"]
    assert len(bent) == 1
    assert bent[0].weight > 0.7
    # Both numbers on the label, because the disagreement is the message.
    assert "r=" in bent[0].label and "I=" in bent[0].label
    assert any("coupled along a curve" in n for n in view.notes)


def test_the_view_says_nothing_extra_about_a_gaussian_posterior():
    """No wolf-crying: a Gaussian posterior must produce no curved edges."""
    rng = np.random.default_rng(4)
    n = 4000
    a = rng.normal(size=n)
    draws = np.column_stack([a, 0.8 * a + 0.6 * rng.normal(size=n),
                             rng.normal(size=n)])
    view = gv.correlation_view(_fit_with_chain(draws))
    assert not [e for e in view.edges if e.kind == "dependence"]
    assert [e for e in view.edges if e.kind == "correlation"]


def test_an_unconverged_chain_cannot_claim_a_curve():
    """An unmixed chain looks exactly like a curved posterior."""
    fit = _fit_with_chain(_banana_draws(), converged=False)
    dep_names, dep, flags = gv.posterior_dependence(fit)
    assert dep is None
    view = gv.correlation_view(fit)
    assert not [e for e in view.edges if e.kind == "dependence"]


def test_prefixed_group_names_still_line_up_with_the_chain():
    """A chain written with plain names must still match ``fit:``-prefixed ones.

    Requiring the two lists to be equal silently disabled the whole measurement
    on every global fit, where the chain carries the sampled model's names and
    the view carries the group's prefixed ones. Matching on the short name is
    what actually lines them up.
    """
    # A constant third column makes ``corrcoef`` non-finite, so the correlation
    # falls back to the covariance and reports the *model's* names while the
    # dependence still reports the *chain's*. That is the mismatch, and it is
    # reachable exactly when some parameter did not move.
    rng = np.random.default_rng(2)
    n = 4000
    t = rng.normal(size=n)
    draws = np.column_stack([t, t ** 2 + 0.1 * rng.normal(size=n), np.full(n, 1.0)])
    fit = _fit_with_chain(draws)
    plain = list(fit.sampling_chain['parameter_names'])
    fit.sampling_chain['parameter_names'] = [f"1:{nm}" for nm in plain]
    fit.sampling_diagnostics = {'parameters': [
        {'name': f"1:{nm}", 'rhat': 1.001, 'ess': 2000.0} for nm in plain]}

    names, corr = gv.posterior_correlation(fit)
    dep_names, dep, _ = gv.posterior_dependence(fit)
    assert corr is not None and dep is not None
    assert [str(x) for x in names] != [str(x) for x in dep_names]   # really differ
    assert [e for e in gv.correlation_view(fit).edges if e.kind == "dependence"]


def test_a_stuck_parameter_pairs_with_nothing_rather_than_with_everything():
    """Rank binning is blind to how few distinct values a column has.

    A parameter pinned at a bound has identical entries, and a stable argsort
    hands them ranks ``0..n-1`` -- so a constant was coming out uniformly
    distributed and scoring 0.14 against an unrelated variable.
    """
    rng = np.random.default_rng(0)
    n = 2000
    d = D.dependence(rng.normal(size=n), np.full(n, 2.5))
    assert np.isnan(d["dependence"])
    assert not d["dependent"] and not d["nonlinear"]
    assert "barely moved" in d["note"]
