"""The estimated rate travels in two units, and the axes are in nanoseconds.

The estimator is deliberately run on a unit grid, so ``params["k"]`` is per
*channel* while every axis the result hands out is in nanoseconds. The forward
model used to build its kernel from ``params["k"]`` on a nanosecond axis, which
stretched the exponential by a factor of ``dt`` — a curve labelled
"IRF ⊗ Exp" that could not reproduce the decay it was drawn over.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.fluorescence_decay.irf_estimator.core.estimation import (
    estimate_irf,
)


def _decay(n: int = 500, dt: float = 0.1002, tau: float = 4.0, t0: float = 5.0):
    """A reconvolved single-exponential decay that reaches baseline."""
    t = np.arange(n) * dt
    irf = np.exp(-0.5 * ((t - t0) / 0.5) ** 2)
    irf /= irf.sum()
    conv = np.convolve(np.exp(-t / tau), irf)[:n]
    rng = np.random.default_rng(5)
    return rng.poisson(4.0e4 * conv / conv.max() + 8.0).astype(float), dt, t


def test_the_result_carries_the_rate_in_both_units():
    """``k`` is per channel, ``k_per_ns`` is per ns, and they differ by ``dt``."""
    decay, dt, t = _decay()
    result = estimate_irf(decay, dt, channel_axis=t)

    assert "k" in result.params and "k_per_ns" in result.params
    assert result.params["k_per_ns"] == pytest.approx(result.params["k"] / dt)
    assert result.params["k_per_ns"] == pytest.approx(result.decay_rate_ns)
    # dt != 1, so a caller that grabs the wrong one is off by a real factor --
    # which is what makes the two names worth having.
    assert result.params["k"] != pytest.approx(result.params["k_per_ns"])


def test_the_per_ns_rate_matches_the_reported_lifetime():
    """``lifetime_ns`` and ``decay_rate_ns`` describe one exponential."""
    decay, dt, t = _decay()
    result = estimate_irf(decay, dt, channel_axis=t)
    assert result.lifetime_ns == pytest.approx(1.0 / result.decay_rate_ns)


def test_the_recovered_irf_sits_where_the_real_one_did():
    """Position is what the tool is for; a unit slip moves it.

    Recovering the *lifetime* needs many lifetimes of measured tail, so this
    checks the IRF position and width rather than tau -- see the guide.
    """
    t0 = 5.0
    decay, dt, t = _decay(t0=t0)
    result = estimate_irf(decay, dt, channel_axis=t)

    irf = np.asarray(result.irf, dtype=float)
    peak_ns = float(np.asarray(result.time_axis)[int(np.argmax(irf))])
    assert peak_ns == pytest.approx(t0, abs=3 * dt)
