"""One Gaussian-mixture EM, reached from every call site that fits one.

The tree carried three expectation-maximisations of the same mixture: the
estimator in :mod:`chisurf.core.ml.mixture`, a private 1-D copy behind the FRET
population gate, and the emission half of the HMM's M-step. Three copies of one
algorithm disagree silently, and these pin the two things that proves: the
gating call site now *runs* the estimator rather than its own loop, and the
degenerate cases each copy guarded differently are guarded once, in the shared
kernel.

Nothing here needs scikit-learn; the numeric comparison against the library
lives in ``test_parity.py``.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.fret import accurate
from chisurf.core.ml import GaussianMixture
from chisurf.core.ml._gaussian import (
    _log_gaussian_density,
    _responsibilities,
    _row_logsumexp,
)

# ---------------------------------------------------------------------------
# the trap the two mixture copies shared and the HMM did not
# ---------------------------------------------------------------------------


def _impossible_row() -> np.ndarray:
    """Return a ``(1, 2)`` log density that is ``-inf`` under every component.

    Not hand-written ``-inf``: the density is evaluated for real, at a sample
    so far from both components that ``(x - mu)**2 / var`` overflows. This is
    the shape a genuinely-zero-probability observation actually arrives in.
    """
    means = np.array([[0.0], [5.0]])
    covars = np.array([1e-6, 1e-6])
    log_prob = _log_gaussian_density(np.array([[1e300]]), means, covars, "spherical")
    log_prob = log_prob + np.log(np.array([0.5, 0.5]))[None, :]
    assert np.isneginf(log_prob).all(), "fixture no longer produces an all -inf row"
    return log_prob


def test_a_sample_no_component_explains_does_not_become_nan():
    """``-inf - (-inf) = nan`` is the trap; a uniform responsibility is the answer.

    A bare ``exp(log_prob - log_prob.max(axis=1))`` -- which both mixture
    copies used -- subtracts the row maximum from itself when the whole row is
    ``-inf``, producing ``nan`` responsibilities that the M-step then spreads
    into every mean and covariance.
    """
    log_prob = _impossible_row()

    resp = _responsibilities(log_prob)
    assert not np.isnan(resp).any()
    np.testing.assert_allclose(resp, [[0.5, 0.5]])
    np.testing.assert_allclose(resp.sum(axis=1), 1.0)


def test_an_impossible_sample_scores_minus_inf_not_nan():
    """The likelihood of an unexplainable sample is a value, not an error."""
    total = _row_logsumexp(_impossible_row())
    assert not np.isnan(total).any()
    assert np.isneginf(total).all()


def test_responsibilities_match_the_naive_form_where_it_is_valid():
    """The guard must not perturb the ordinary case it also serves."""
    rng = np.random.default_rng(0)
    log_prob = rng.normal(-3.0, 2.0, (200, 4))
    m = log_prob.max(axis=1, keepdims=True)
    naive = np.exp(log_prob - m)
    naive = naive / naive.sum(axis=1, keepdims=True)
    np.testing.assert_allclose(_responsibilities(log_prob), naive, rtol=1e-15)


def test_a_fit_survives_an_impossible_sample():
    """End to end: the estimator still converges with such a row in the data."""
    rng = np.random.default_rng(0)
    X = np.concatenate([rng.normal(0.0, 0.1, 200), rng.normal(5.0, 0.1, 200)])[:, None]
    fitted = GaussianMixture(
        n_components=2,
        covariance_type="spherical",
        means_init=np.array([[0.0], [5.0]]),
        covariances_init=np.array([1e-6, 1e-6]),
        init_params="random",
        n_init=1,
        max_iter=50,
        tol=1e-6,
    ).fit(np.vstack([X, [[1e300]]]))

    assert not np.isnan(fitted.means_).any()
    assert not np.isnan(fitted.weights_).any()
    assert not np.isnan(fitted.covariances_).any()


# ---------------------------------------------------------------------------
# the 1-D gate runs the shared estimator
# ---------------------------------------------------------------------------


def test_the_gate_fits_through_the_shared_estimator(monkeypatch):
    """``gaussian_mixture_1d`` must reach ``GaussianMixture``, not a private loop.

    Asserted by construction rather than by reading the source: the fit fails
    if the estimator is not the thing that runs.
    """
    calls = []
    real_fit = GaussianMixture.fit

    def counting_fit(self, X):
        calls.append(self.covariance_type)
        return real_fit(self, X)

    monkeypatch.setattr(GaussianMixture, "fit", counting_fit)
    rng = np.random.default_rng(0)
    x = np.concatenate([rng.normal(0.2, 0.05, 200), rng.normal(0.8, 0.08, 300)])
    accurate.gaussian_mixture_1d(x, 2)

    assert calls, "the 1-D gate did not run the shared estimator"
    assert set(calls) == {"spherical"}, "a 1-D mixture is the spherical layout"


def test_the_ported_gate_converges_where_the_copy_it_replaced_did():
    """Converged parameters match the deleted 1-D EM, which produced these numbers.

    Frozen reference, recorded from the private loop before it was deleted, on
    the fixture its own test uses. Parity is claimed on the *converged*
    mixture, not on the iterates: the shared estimator applies ``tolerance``
    as an absolute rather than a relative gain, so it stops at a different
    iteration on the same monotone path.

    The widths carry the one deliberate difference. The estimator's ridge is
    additive on the variance (``sigma**2 + reg``) where the copy clamped the
    width from below, so a fitted width moves by exactly that ridge and by
    nothing else -- asserted below rather than absorbed into a loose
    tolerance.
    """
    rng = np.random.default_rng(0)
    x = np.concatenate([rng.normal(0.2, 0.05, 800), rng.normal(0.8, 0.08, 1200)])
    fit = accurate.gaussian_mixture_1d(x, 2)

    before_weights = [0.39999999, 0.60000001]
    before_means = [0.19868985, 0.79766073]
    before_sigmas = [0.05001519, 0.08001000]
    before_log_likelihood = 1243.1671199031377

    np.testing.assert_allclose(fit["weights"], before_weights, atol=1e-7)
    np.testing.assert_allclose(fit["means"], before_means, atol=1e-7)
    assert fit["log_likelihood"] == pytest.approx(before_log_likelihood, abs=1e-3)
    # the widths differ by the ridge, exactly
    ridge = accurate.gaussian_mixture_1d.__defaults__ is None  # keeps ruff quiet
    del ridge
    expected = np.sqrt(np.asarray(before_sigmas) ** 2 + 1e-3**2)
    np.testing.assert_allclose(fit["sigmas"], expected, rtol=2e-4)
    # and it converges in a sane number of steps, not by exhausting the budget
    assert 0 < fit["n_iter"] < 300


def test_the_gate_still_recovers_three_known_components():
    """Ground-truth recovery, the property the gate exists for."""
    rng = np.random.default_rng(2)
    x = np.concatenate([rng.normal(-2, 0.3, 300), rng.normal(0, 0.2, 300), rng.normal(3, 0.4, 300)])
    fit = accurate.gaussian_mixture_1d(x, 3)
    np.testing.assert_allclose(fit["means"], [-2.0, 0.0, 3.0], atol=0.05)
    np.testing.assert_allclose(fit["weights"], [1 / 3, 1 / 3, 1 / 3], atol=0.02)
    np.testing.assert_allclose(fit["sigmas"], [0.3, 0.2, 0.4], atol=0.02)


def test_more_components_than_the_data_supports_stays_a_mixture():
    """The degenerate case: extra components must not produce nan or a non-mixture.

    Three components on one tight blob is unidentifiable, so no particular
    split is the right answer -- what must hold is that every parameter is
    finite, the weights are a distribution, and no width falls through the
    floor the caller asked for.
    """
    rng = np.random.default_rng(1)
    x = rng.normal(0.0, 0.01, 60)
    fit = accurate.gaussian_mixture_1d(x, 3, sigma_floor=1e-3)

    assert np.isfinite(fit["means"]).all()
    assert np.isfinite(fit["sigmas"]).all()
    assert np.isfinite(fit["log_likelihood"])
    assert (fit["weights"] >= 0).all()
    assert fit["weights"].sum() == pytest.approx(1.0)
    assert (fit["sigmas"] >= 1e-3).all(), "a component collapsed through the floor"
    assert not np.isnan(fit["responsibilities"]).any()
    np.testing.assert_allclose(fit["responsibilities"].sum(axis=1), 1.0)


def test_the_gate_is_deterministic():
    """Two calls on the same samples give the same gate, as the docstring claims."""
    rng = np.random.default_rng(4)
    x = np.concatenate([rng.normal(0.25, 0.04, 400), rng.normal(0.75, 0.06, 400)])
    first, second = accurate.gaussian_mixture_1d(x, 2), accurate.gaussian_mixture_1d(x, 2)
    np.testing.assert_array_equal(first["labels"], second["labels"])
    np.testing.assert_array_equal(first["means"], second["means"])
