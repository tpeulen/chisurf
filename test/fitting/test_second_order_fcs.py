"""Tests for the three-point (second-order) intensity correlation g^(3)."""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.fcs.correlate import second_order_correlation


def test_poisson_trace_is_flat_at_one():
    rng = np.random.default_rng(0)
    trace = rng.poisson(5.0, size=200_000).astype(float)
    tau1 = np.array([1, 3, 10])
    tau2 = np.array([1, 3, 10])
    g3 = second_order_correlation(trace, tau1, tau2)
    assert g3.shape == (3, 3)
    assert np.nanmax(np.abs(g3 - 1.0)) < 0.05        # uncorrelated -> ~1


def test_correlated_bunches_raise_g3():
    """A trace with coincident bright bursts shows g^(3) > 1 at short lags."""
    rng = np.random.default_rng(1)
    n = 100_000
    trace = rng.poisson(1.0, size=n).astype(float)
    # Inject correlated 3-bin-wide bursts.
    for t in rng.integers(0, n - 3, size=2000):
        trace[t:t + 3] += 15.0
    tau1 = np.array([1, 2])
    tau2 = np.array([1, 2])
    g3_short = second_order_correlation(trace, tau1, tau2)
    g3_long = second_order_correlation(trace, np.array([500]), np.array([500]))
    assert np.nanmean(g3_short) > 1.2                # bunched at short lag
    assert np.nanmean(g3_short) > g3_long[0, 0]      # decays to ~1 at long lag


def test_length_mismatch_raises():
    import pytest
    with pytest.raises(ValueError):
        second_order_correlation(np.ones(10), np.array([1]), np.array([1]),
                                 trace2=np.ones(9))
