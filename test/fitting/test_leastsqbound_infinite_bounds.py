"""Regression tests for infinite bounds in :mod:`leastsqbound`.

``leastsqbound`` optimises in an internal, unconstrained coordinate system and
maps back through a sin/arcsin transform. It used to detect "this parameter is
unconstrained" by testing ``bound is None`` only — but ``Model.parameter_bounds``
reports an absent bound as ``+/-inf``, not ``None``.

An ``(-inf, inf)`` parameter therefore fell through to the *bounded* branch:

    arcsin((2 * (x - lower) / (upper - lower)) - 1)
      = arcsin((x + inf) / inf - 1)
      = arcsin(inf/inf - 1)
      = arcsin(nan) = nan

so every unbounded parameter was silently NaN in the optimiser's internal
vector. The visible symptom was a fit that *destroyed* a good solution: started
at the true parameters with chi2r 1.55, it walked away to NaN.
"""
import numpy as np
import pytest

from chisurf.core.math.optimization.leastsqbound import (
    _external2internal_lambda,
    _internal2external_lambda,
    leastsqbound,
)


@pytest.mark.parametrize(
    "bound",
    [
        (-np.inf, np.inf),      # fully free, as parameter_bounds reports it
        (None, None),           # fully free, spelled with None
        (0.0, np.inf),          # lower bound only, inf spelling
        (0.0, None),            # lower bound only, None spelling
        (-np.inf, 10.0),        # upper bound only, inf spelling
        (None, 10.0),           # upper bound only, None spelling
    ],
)
def test_transforms_are_finite(bound):
    """No bound spelling may produce a non-finite internal coordinate."""
    e2i = _external2internal_lambda(bound)
    i2e = _internal2external_lambda(bound)
    for x in (0.5, 1.0, 2.5, 7.0):
        xi = e2i(x)
        assert np.isfinite(xi), f"external->internal produced {xi} for {bound}"
        assert np.isfinite(i2e(xi)), f"internal->external non-finite for {bound}"


@pytest.mark.parametrize("bound", [(-np.inf, np.inf), (None, None)])
def test_free_parameter_round_trips_exactly(bound):
    """An unconstrained parameter must map through as the identity."""
    e2i = _external2internal_lambda(bound)
    i2e = _internal2external_lambda(bound)
    for x in (-3.0, 0.0, 0.7, 42.0):
        assert i2e(e2i(x)) == pytest.approx(x, rel=0, abs=1e-12)


def test_infinite_bounds_do_not_poison_a_fit():
    """A least-squares fit with (-inf, inf) bounds must actually converge.

    Before the fix the internal parameter vector was NaN and the optimiser
    returned its starting point (or worse).
    """
    x = np.linspace(0.0, 10.0, 200)
    truth = np.array([2.5, -1.3])
    y = truth[0] * x + truth[1]

    def residual(p, *args):
        return p[0] * x + p[1] - y

    p0 = np.array([0.1, 0.1])
    out = leastsqbound(residual, p0, bounds=[(-np.inf, np.inf), (-np.inf, np.inf)])
    fitted = np.asarray(out[0], dtype=float)

    assert np.all(np.isfinite(fitted))
    np.testing.assert_allclose(fitted, truth, rtol=1e-6, atol=1e-6)


def test_mixed_finite_and_infinite_bounds():
    """The common real case: some parameters bounded, others free."""
    x = np.linspace(0.0, 10.0, 200)
    truth = np.array([2.5, -1.3])
    y = truth[0] * x + truth[1]

    def residual(p, *args):
        return p[0] * x + p[1] - y

    out = leastsqbound(
        residual, np.array([0.1, 0.1]),
        bounds=[(0.0, 100.0), (-np.inf, np.inf)],   # slope bounded, offset free
    )
    fitted = np.asarray(out[0], dtype=float)
    assert np.all(np.isfinite(fitted))
    np.testing.assert_allclose(fitted, truth, rtol=1e-6, atol=1e-6)
