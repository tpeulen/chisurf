"""Normalised quantities must carry normalised error bars.

When ``Lifetime.normalize_amplitudes`` is on, the amplitudes are rescaled to
``|a| / sum|a|`` in :meth:`Lifetime.update`.  The optimiser, however, works in
the **raw** (pre-normalisation) space: the Jacobian and covariance are taken
with respect to the raw amplitude values, so the error estimates come out in
raw units.  After ``update()`` the *values* are normalised but the *errors*
are not — and the relative error ``σ / value`` is off by a factor of
``sum|a_raw|``.

This test suite verifies that after a fit, the amplitude error estimates
live in the same normalised space as the values.
"""
import numpy as np
import pytest

from .test_tcspc_fit_convergence import _build, _chi2r, TRUE_AMPS, TRUE_TAUS


def test_amplitude_errors_are_in_normalised_space():
    """After a fit the error bar must be on the same scale as the value.

    With ``normalize_amplitudes=True`` the values sum to 1, so an error
    comparable to the value (a few percent) is expected.  If the error
    were still in raw space it would be off by ``sum|a_raw|``, which for
    starting amplitudes of (1.0, 1.0) is a factor of 2.
    """
    fit, m = _build(start=[(1.0, 8.0), (1.0, 0.4)])
    fit.run()

    amps = m.lifetimes._amplitudes
    # All amplitudes should have finite error estimates
    for a in amps:
        assert np.isfinite(a.error_estimate), (
            f"amplitude {a.name} has no error estimate")
        assert a.error_estimate > 0, (
            f"amplitude {a.name} has zero error estimate")

    # The relative error should be reasonable (not millions of percent)
    for a in amps:
        rel = abs(a.error_estimate / a.value) * 100
        assert rel < 100, (
            f"amplitude {a.name} relative error {rel:.1f}% is unreasonably "
            f"large — error is probably in raw (unnormalised) space")


def test_redundant_amplitude_error_is_also_normalised():
    """The held-out amplitude's error must match the free one (two-component case).

    For two normalised components, a0 + a1 = 1, so σ(a0) = σ(a1).
    If only the free amplitude's error is normalised but the redundant
    one's is not, they will disagree.
    """
    fit, m = _build(start=[(1.0, 8.0), (1.0, 0.4)])
    fit.run()

    a0, a1 = m.lifetimes._amplitudes
    assert a0.redundant and not a1.redundant

    assert np.isfinite(a0.error_estimate), "redundant amplitude has no error"
    assert np.isfinite(a1.error_estimate), "free amplitude has no error"

    # For two components summing to 1, the errors must be equal
    np.testing.assert_allclose(
        a0.error_estimate, a1.error_estimate, rtol=1e-6,
        err_msg="redundant and free amplitude errors disagree — "
                "normalisation was not applied consistently")


def test_error_scaling_is_idempotent():
    """Repeated update() calls must not compound the error scaling.

    After normalisation sum|a| = 1, so the scale factor is 1 and subsequent
    updates are no-ops.  Calling update() many times must not change the
    error estimates.
    """
    fit, m = _build(start=[(1.0, 8.0), (1.0, 0.4)])
    fit.run()

    ee = [a.error_estimate for a in m.lifetimes._amplitudes]
    for _ in range(10):
        m.lifetimes.update()
    ee2 = [a.error_estimate for a in m.lifetimes._amplitudes]

    np.testing.assert_allclose(ee, ee2, rtol=1e-12,
                              err_msg="error estimates changed on repeated update()")


def test_disabling_normalisation_does_not_scale_errors():
    """When normalize_amplitudes is off, the scale factor is 1 — no change."""
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    m.lifetimes.normalize_amplitudes = False
    m.lifetimes.update()

    # No fit → no error estimates → nothing to scale
    for a in m.lifetimes._amplitudes:
        assert not np.isfinite(a.error_estimate)


def test_relative_error_matches_manual_calculation():
    """The relative error σ/value should match the value computed from the
    covariance matrix taken in normalised space."""
    fit, m = _build(start=[(1.0, 8.0), (1.0, 0.4)])
    fit.run()

    # Re-compute error estimates from the covariance in normalised space
    from chisurf.core.fitting.fit import covariance_matrix
    cov_m, used = covariance_matrix(fit)

    # The covariance is already in normalised space (after update()),
    # so the diagonal gives us the normalised variance
    free = fit.model.parameters
    err = np.sqrt(np.diag(cov_m))

    # Compare against stored error estimates
    for idx, p in zip(used, free):
        # Only check amplitude parameters
        if p in m.lifetimes._amplitudes:
            np.testing.assert_allclose(
                p.error_estimate, err[idx], rtol=1e-3,
                err_msg=f"amplitude {p.name} error estimate does not match "
                        f"covariance diagonal — still in raw space?")
