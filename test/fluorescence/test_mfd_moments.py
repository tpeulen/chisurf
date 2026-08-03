"""The moments the MFD lifetime axis is built on.

Every test here exists because getting the corresponding thing wrong is silent: the
histogram absorbs a biased mean into a rate or a distance and still converges. So
each closed form is checked against a numerically integrated pattern, each limit
against its analytic value, and the wrapped machinery against the unwrapped
identity in the regime where the two must agree.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.mfd.moments import (
    background_moments,
    mixture_moments,
    pattern_moments,
    periodic_pattern,
    unwrapped_mixture_moments,
    wrapped_exponential_moments,
    wrapped_exponential_pattern,
)


def _numeric_wrapped_moments(tau: float, period: float, n: int = 200_000):
    """Return the wrapped moments by brute-force integration, for comparison.

    Uses channel *midpoints*, so this approximates the continuous moments rather
    than the recorded (left-edge) ones — which is what the no-``channel_width``
    closed form claims to be.
    """
    dt = period / n
    edges = np.arange(n + 1) * dt
    survival = np.exp(-edges / tau)
    w = survival[:-1] - survival[1:]
    w = w / w.sum()
    t = edges[:-1] + 0.5 * dt
    mean = float(w @ t)
    return mean, float(w @ (t * t)) - mean * mean


# ──────────────────────────────────────────────────────────────────────────────
# The wrapped exponential
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("tau", [0.05, 0.5, 2.0, 4.0, 13.6, 100.0])
def test_wrapped_moments_match_numeric_integration(tau):
    """The closed form is the integral, not an approximation to it."""
    period = 13.6
    mean, var = wrapped_exponential_moments(tau, period)
    ref_mean, ref_var = _numeric_wrapped_moments(tau, period)
    assert float(mean) == pytest.approx(ref_mean, rel=2e-5)
    assert float(var) == pytest.approx(ref_var, rel=2e-5)


def test_short_lifetime_limit_is_the_unwrapped_exponential():
    """When nothing wraps, the moments are the plain exponential's."""
    tau, period = 0.01, 13.6
    mean, var = wrapped_exponential_moments(tau, period)
    assert float(mean) == pytest.approx(tau, rel=1e-9)
    assert float(var) == pytest.approx(tau * tau, rel=1e-9)


def test_long_lifetime_limit_is_uniform_and_numerically_stable():
    """A lifetime dwarfing the period gives a flat window, not cancellation noise.

    ``mean = τ − T/(e^{T/τ} − 1)`` is a difference of two enormous, nearly equal
    numbers here; evaluated naively it returns garbage rather than ``T/2``.
    """
    period = 13.6
    for tau in (1e4, 1e8, 1e12):
        mean, var = wrapped_exponential_moments(tau, period)
        assert float(mean) == pytest.approx(period / 2.0, rel=1e-3)
        assert float(var) == pytest.approx(period**2 / 12.0, rel=1e-3)


def test_wrapping_biases_a_long_lifetime_short():
    """The whole reason the wrap cannot be ignored, stated as a number.

    A 4 ns lifetime in a 13.6 ns window has a mean micro time ~5% below its
    unwrapped value; treating the two as equal would show up as a lifetime error,
    which the 2D histogram would then absorb as dynamics.
    """
    tau, period = 4.0, 13.6
    mean, _ = wrapped_exponential_moments(tau, period)
    assert float(mean) < tau
    assert 0.02 < (tau - float(mean)) / tau < 0.15


def test_moments_are_vectorised():
    """A grid of lifetimes is evaluated at once, as the fit loop needs."""
    taus = np.array([0.5, 1.0, 4.0])
    mean, var = wrapped_exponential_moments(taus, 13.6)
    assert mean.shape == var.shape == taus.shape
    assert np.all(np.diff(mean) > 0)


def test_negative_or_zero_lifetime_is_refused():
    """A non-positive lifetime is a parameter error, not a NaN downstream."""
    with pytest.raises(ValueError):
        wrapped_exponential_moments(0.0, 13.6)
    with pytest.raises(ValueError):
        wrapped_exponential_moments([1.0, -2.0], 13.6)


# ──────────────────────────────────────────────────────────────────────────────
# Patterns
# ──────────────────────────────────────────────────────────────────────────────
def test_pattern_moments_reproduce_the_closed_form():
    """The numeric route and the closed form describe the same distribution.

    They must be compared like with like: a pattern reports what the TAC *records*,
    the left edge of each channel, so the closed form is asked for the same thing.
    """
    period, n = 13.6, 4096
    dt = period / n
    for tau in (0.2, 1.0, 4.0, 20.0):
        pattern = wrapped_exponential_pattern(tau, n, dt)
        mean, var = pattern_moments(pattern, dt)
        exact_mean, exact_var = wrapped_exponential_moments(tau, period, dt)
        assert mean == pytest.approx(float(exact_mean), rel=1e-9)
        assert var == pytest.approx(float(exact_var), rel=1e-9)


def test_channel_discretization_is_an_exact_correction_not_a_half_bin():
    """The recorded mean is the continuous one minus a computable offset.

    Because an exponential is memoryless the offset is the same in every channel,
    so it subtracts exactly. For a channel far shorter than the lifetime it is the
    familiar half-channel; the point of doing it properly is that it stays right
    when the channel is *not* short — a coarse TAC binning would otherwise bias
    every lifetime by an amount nobody has written down.
    """
    period = 13.6
    for dt in (period / 4096, period / 64, period / 8):
        for tau in (0.3, 2.0, 8.0):
            cont_mean, cont_var = wrapped_exponential_moments(tau, period)
            rec_mean, rec_var = wrapped_exponential_moments(tau, period, dt)
            off_mean, off_var = wrapped_exponential_moments(tau, dt)
            assert float(rec_mean) == pytest.approx(float(cont_mean - off_mean))
            assert float(rec_var) == pytest.approx(float(cont_var - off_var))
            if dt < tau / 10.0:
                assert float(off_mean) == pytest.approx(dt / 2.0, rel=0.05)


def test_irf_convolution_adds_the_response_moments_when_nothing_wraps():
    """The additive identity, recovered in the regime where it is true.

    With a short lifetime and a response far from the end of the window, the
    convolved pattern's moments are the sums of the two components' — which is what
    makes the identity usable, and what makes ignoring the wrap elsewhere wrong.
    """
    n, dt = 4096, 13.6 / 4096
    centre, width = 400, 12.0
    channels = np.arange(n)
    irf = np.exp(-0.5 * ((channels - centre) / width) ** 2)
    irf_mean, irf_var = pattern_moments(irf, dt)

    tau = 0.4
    pattern = periodic_pattern(tau, irf, dt)
    mean, var = pattern_moments(pattern, dt)

    # Both components as the TAC records them, so the sum is like for like.
    decay_mean, decay_var = wrapped_exponential_moments(tau, n * dt, dt)
    assert mean == pytest.approx(irf_mean + float(decay_mean), rel=1e-4)
    assert var == pytest.approx(irf_var + float(decay_var), rel=1e-3)


def test_convolution_is_circular_not_linear():
    """A response near the end of the window wraps; a linear convolution loses it.

    This is the trap the module docstring names. With the response placed close to
    the window's end, a linear convolution would push the pattern's weight off the
    end and report a mean that is far too *late*; the circular one folds it back.
    """
    n, dt = 512, 13.6 / 512
    irf = np.zeros(n)
    irf[n - 4] = 1.0
    tau = 2.0

    pattern = periodic_pattern(tau, irf, dt)
    assert pattern.sum() == pytest.approx(1.0)
    # Almost all of the decay falls after the end of the window and comes back at
    # its start: only the four channels from the response to the window's end do not.
    assert pattern[: n - 4].sum() > 0.9
    # A linear convolution would simply lose that weight — most of the distribution.
    linear = np.convolve(irf, wrapped_exponential_pattern(tau, n, dt))[:n]
    assert linear.sum() < 0.1
    # And so it would report a mean pinned at the response, instead of the early
    # mean the wrapped photons actually produce.
    mean, _ = pattern_moments(pattern, dt)
    assert mean < 0.5 * (n - 4) * dt


def test_pattern_normalisation_and_refusals():
    """A pattern with no counts is an error, not a division by zero."""
    with pytest.raises(ValueError):
        pattern_moments(np.zeros(16), 0.1)
    with pytest.raises(ValueError):
        periodic_pattern(1.0, np.zeros(16), 0.1)
    with pytest.raises(ValueError):
        wrapped_exponential_pattern(-1.0, 16, 0.1)


# ──────────────────────────────────────────────────────────────────────────────
# Mixtures
# ──────────────────────────────────────────────────────────────────────────────
def test_mixture_variance_includes_the_spread_of_the_means():
    """Two components with the same width are wider together than apart.

    Forgetting the between-component term is how a two-state mixture comes to look
    like one state with a slightly wrong lifetime.
    """
    mean, var = mixture_moments([0.5, 0.5], [1.0, 3.0], [0.25, 0.25])
    assert float(mean) == pytest.approx(2.0)
    # within-component 0.25 plus the (±1) spread of the means
    assert float(var) == pytest.approx(0.25 + 1.0)


def test_mixture_of_one_component_is_that_component():
    """The degenerate case must not shift anything."""
    mean, var = mixture_moments([3.0], [4.2], [1.7])
    assert float(mean) == pytest.approx(4.2)
    assert float(var) == pytest.approx(1.7)


def test_unwrapped_identity_matches_the_mixture_law():
    """``v = 2 Σ xᵢ τᵢ² − μ²`` is the law of total variance for exponentials."""
    x = np.array([0.3, 0.7])
    tau = np.array([0.5, 2.0])
    mean_a, var_a = unwrapped_mixture_moments(x, tau)
    mean_b, var_b = mixture_moments(x, tau, tau * tau)
    assert float(mean_a) == pytest.approx(float(mean_b))
    assert float(var_a) == pytest.approx(float(var_b))


def test_wrapped_mixture_tends_to_the_unwrapped_one_for_a_long_period():
    """The wrapped machinery must reproduce the textbook identity in its limit."""
    x = np.array([0.4, 0.6])
    tau = np.array([0.5, 2.0])
    period = 5000.0
    means, variances = wrapped_exponential_moments(tau, period)
    mean, var = mixture_moments(x, means, variances)
    ref_mean, ref_var = unwrapped_mixture_moments(x, tau)
    assert float(mean) == pytest.approx(float(ref_mean), rel=1e-6)
    assert float(var) == pytest.approx(float(ref_var), rel=1e-6)


def test_background_is_flat_over_the_window():
    """An uncorrelated background carries no timing information."""
    n, dt = 4096, 13.6 / 4096
    mean, var = background_moments(n, dt)
    period = n * dt
    assert mean == pytest.approx((period - dt) / 2.0, rel=1e-9)
    assert var == pytest.approx(period**2 / 12.0, rel=1e-3)
