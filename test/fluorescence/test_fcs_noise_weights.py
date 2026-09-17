"""Headless tests for the FCS noise-weight model (``core.fluorescence.fcs.noise``).

The correlation amplitude that drives every weight is a difference of two
windows: the short-lag plateau ``correlation[lb:ub]`` minus the long-lag
baseline. Pin the baseline on a synthetic curve ``G = 1 + A / (1 + t / tau)``,
where both windows are known exactly (RF-045).
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence import fcs

AMPLITUDE = 0.5
DIFFUSION_TIME = 1.0  # ms


def synthetic_curve(n: int = 200):
    """Return lag times and a single-component 3D-diffusion correlation curve.

    Parameters
    ----------
    n : int, optional
        Number of logarithmically spaced lag times. Default is 200.

    Returns
    -------
    tuple of np.ndarray
        The lag times in milliseconds and ``G = 1 + A / (1 + t / tau)``.
    """
    times = np.logspace(-4, 3, n)
    correlation = 1.0 + AMPLITUDE / (1.0 + times / DIFFUSION_TIME)
    return times, correlation


def measured_amplitude(times, correlation, **kwargs):
    """Return the amplitude ``noise`` derives, recovered from the uniform branch.

    ``noise`` does not expose the amplitude, so reconstruct it from the
    Starchev variance, which depends on it only through ``N = 1 / A``.

    Parameters
    ----------
    times : np.ndarray
        Lag times in milliseconds.
    correlation : np.ndarray
        Correlation amplitudes.
    **kwargs
        Forwarded to :func:`chisurf.core.fluorescence.fcs.noise`.

    Returns
    -------
    float
        The mean correlation amplitude used internally.
    """
    sd = fcs.noise(
        times,
        correlation,
        measurement_duration=10.0,
        mean_count_rate=50.0,
        weight_type="starchev",
        diffusion_time=DIFFUSION_TIME,
        starchev_a1=1.0,
        starchev_a2=0.0,
        starchev_c1=0.0,
        z0_w0=0.0,
        **kwargs,
    )
    # With a2 = c1 = 0, p = 0 and a1 = 1: var = A**3 / i, so A = (var * i)**(1/3).
    return float((sd[0] ** 2 * 50.0) ** (1.0 / 3.0))


def test_the_offset_is_the_long_lag_baseline_not_the_whole_curve():
    """The default window must average the last 16 points, not all but 16."""
    times, correlation = synthetic_curve()
    a = measured_amplitude(times, correlation)
    # Baseline ~ 1.0 at the longest lags, so A ~ the true amplitude. The old
    # slice averaged 184 of the 200 points into the baseline and gave ~0.19.
    assert a == pytest.approx(AMPLITUDE, abs=2e-3)


def test_a_non_zero_lower_bound_mirrors_the_window_at_the_tail():
    """``(lb, ub)`` selects ``[lb:ub]`` at the front and its mirror at the back."""
    times, correlation = synthetic_curve()
    n = len(correlation)
    expected = np.mean(correlation[2:16]) - np.mean(correlation[n - 16 : n - 2])
    a = measured_amplitude(times, correlation, correlation_amplitude_range=(2, 16))
    assert a == pytest.approx(expected, rel=1e-6)


def test_the_baseline_window_never_swallows_the_amplitude_window():
    """Head and tail windows stay disjoint, so the amplitude cannot self-cancel."""
    times, correlation = synthetic_curve()
    for lb, ub in [(0, 16), (0, 32), (4, 20)]:
        a = measured_amplitude(times, correlation, correlation_amplitude_range=(lb, ub))
        assert a > 0.3, f"amplitude collapsed for range ({lb}, {ub})"


def test_the_estimated_diffusion_time_follows_the_corrected_amplitude():
    """Half-amplitude crossing lands near tau once the baseline is right."""
    times, correlation = synthetic_curve(n=2000)
    sd_estimated = fcs.noise(
        times, correlation, measurement_duration=10.0, mean_count_rate=50.0, weight_type="starchev"
    )
    sd_exact = fcs.noise(
        times,
        correlation,
        measurement_duration=10.0,
        mean_count_rate=50.0,
        weight_type="starchev",
        diffusion_time=DIFFUSION_TIME,
    )
    # A biased offset shifts the crossing to a much shorter lag; the weights
    # then differ from the exact-tau ones by far more than the sampling grid.
    assert sd_estimated == pytest.approx(sd_exact, rel=2e-2)


def test_suren_weights_stay_finite_and_positive():
    """The suren branch is a live path for every ALV/Kristine import."""
    times, correlation = synthetic_curve()
    sd = fcs.noise(
        times, correlation, measurement_duration=10.0, mean_count_rate=50.0, weight_type="suren"
    )
    assert sd.shape == correlation.shape
    assert np.all(np.isfinite(sd))
    assert np.all(sd > 0.0)
