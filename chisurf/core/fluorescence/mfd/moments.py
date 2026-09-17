"""The first two moments of a micro-time pattern, which is all the lifetime axis needs.

The mean micro time ``⟨t⟩`` is a *linear* statistic of a burst's photons, so its
sampling distribution is analytic: given ``N`` photons drawn from a pattern with
mean ``μ`` and variance ``v``, ``⟨t⟩`` has mean ``μ`` and variance ``v / N``. A
per-burst maximum-likelihood lifetime is neither analytic nor unbiased at the
50–500 photons a burst carries, and its bias moves with the parameters — which is
why this module exists and a per-burst lifetime fit does not.

A photon's micro time is the instrument-response arrival plus an independent decay
delay, so means and variances **add**::

    μ = μ_IRF + μ_decay        v = v_IRF + v_decay
    μ_decay = Σ xᵢ τᵢ          v_decay = 2 Σ xᵢ τᵢ² − (Σ xᵢ τᵢ)²

**That identity is only true when nothing wraps.** The TAC window is one laser
period long, and a photon emitted late in the period reappears at the start of the
next one, so both the decay and the convolution live on a *circle*. Adding
unwrapped moments biases every long lifetime short, and — this is the dangerous
part — the histogram absorbs the bias into an exchange rate rather than failing.

So this module provides both, and keeps them honest about each other:

* :func:`wrapped_exponential_moments` — the exact closed form on the circle, with
  the series expansions that keep it stable when the lifetime dwarfs the period;
* :func:`pattern_moments` — the moments of a numerically built periodic pattern,
  which is what the fit actually uses, and which needs no assumption at all;
* :func:`mixture_moments` — the law of total variance, for combining the decay with
  background and scatter.

The unwrapped additive identity is then a *test* (it must be recovered when the
period dwarfs the lifetime), never the implementation.

**Bin convention.** A micro time is recorded as an integer TAC channel, and the
mean micro time that reaches the burst tables is
``mean(channel) × ns_per_channel`` — the mean of the *left edges*, not of the bin
centres. Every moment here uses ``t_k = k · dt`` to match, because agreeing with
the measurement matters more than a half-bin of nominal correctness.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "background_moments",
    "mixture_moments",
    "pattern_moments",
    "periodic_pattern",
    "unwrapped_mixture_moments",
    "wrapped_exponential_moments",
    "wrapped_exponential_pattern",
]

#: Below this ``period / lifetime`` ratio the closed forms are evaluated from their
#: series expansions. Both moments are differences of two large, nearly equal terms
#: when the lifetime dwarfs the period, and the direct expressions lose every
#: significant digit there — the mean of a lifetime 10⁶× the period must come out as
#: half the period, not as noise.
_SERIES_THRESHOLD = 1e-2


def _g_series(a: np.ndarray) -> np.ndarray:
    """Return ``1/a − 1/expm1(a)``, the shape factor of the wrapped mean."""
    return 0.5 - a / 12.0 + a**3 / 720.0


def _h_series(a: np.ndarray) -> np.ndarray:
    """Return ``2/a² − (2/a + 1)/expm1(a)``, the shape factor of the wrapped second moment."""
    return 1.0 / 3.0 - a / 12.0 + a**2 / 360.0 + a**3 / 720.0


def wrapped_exponential_moments(
    tau: np.ndarray | float, period: float, channel_width: float | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Return the mean and variance of an exponential decay wrapped onto one period.

    Under repeated excitation the micro time recorded for a photon is its emission
    delay modulo the laser period, so the observed density on ``[0, T)`` is the
    exponential *truncated and renormalised* — photons from earlier pulses fold back
    in. In closed form, with ``a = T / τ``::

        E[Y]  = T · (1/a − 1/(e^a − 1))
        E[Y²] = T² · (2/a² − (2/a + 1)/(e^a − 1))

    The first is the familiar ``τ − T/(e^{T/τ} − 1)``, written so that it stays
    accurate when ``τ ≫ T`` and the two terms nearly cancel.

    Parameters
    ----------
    tau : array_like or float
        Lifetime(s), in the same time unit as *period*. Must be positive.
    period : float
        The laser period — one TAC window.
    channel_width : float, optional
        When given, return the moments of the **recorded** micro time rather than of
        the continuous arrival time: a TAC reports the index of the channel a photon
        fell in, and the burst tables turn that into ``channel × width``, so what is
        measured is the *left edge* of the channel, not the arrival within it.

        The correction is exact rather than a half-channel approximation. An
        exponential is memoryless, so the offset of the arrival from its channel's
        left edge has the same distribution in every channel and is independent of
        which channel it is — and that distribution is itself an exponential wrapped
        onto one *channel*. Its mean and variance therefore subtract::

            μ_recorded = μ − μ_offset        v_recorded = v − v_offset

        with ``(μ_offset, v_offset)`` this function evaluated at a period of one
        channel. For a channel much shorter than the lifetime that reduces to the
        familiar half-channel shift, but it stays right when it does not.

    Returns
    -------
    mean, variance : numpy.ndarray
        Broadcast to the shape of *tau*.

    Notes
    -----
    The limits are the sanity checks worth remembering: as ``τ → 0`` the mean tends
    to ``τ`` and the variance to ``τ²`` (nothing wraps); as ``τ → ∞`` the density
    becomes uniform, so the mean tends to ``T/2`` and the variance to ``T²/12``.
    """
    tau_arr = np.asarray(tau, dtype=float)
    if np.any(tau_arr <= 0.0):
        raise ValueError("lifetimes must be positive")
    period = float(period)
    if period <= 0.0:
        raise ValueError("the period must be positive")

    a = period / tau_arr
    small = a < _SERIES_THRESHOLD
    with np.errstate(over="ignore", invalid="ignore"):
        expm1_a = np.expm1(np.clip(a, None, 700.0))
        g = np.where(small, _g_series(a), 1.0 / a - 1.0 / expm1_a)
        h = np.where(small, _h_series(a), 2.0 / a**2 - (2.0 / a + 1.0) / expm1_a)
    mean = period * g
    second = period * period * h
    variance = np.clip(second - mean * mean, 0.0, None)

    if channel_width is not None:
        offset_mean, offset_variance = wrapped_exponential_moments(tau_arr, float(channel_width))
        mean = mean - offset_mean
        variance = np.clip(variance - offset_variance, 0.0, None)
    return mean, variance


def wrapped_exponential_pattern(tau: float, n_channels: int, dt: float) -> np.ndarray:
    """Return the normalised periodic decay pattern of one lifetime.

    Parameters
    ----------
    tau : float
        Lifetime, in the units of *dt*.
    n_channels : int
        Micro-time channels in one laser period.
    dt : float
        Width of a micro-time channel.

    Returns
    -------
    numpy.ndarray
        ``(n_channels,)``, summing to one. Channel ``k`` holds the probability of a
        photon arriving in ``[k·dt, (k+1)·dt)``.
    """
    if tau <= 0.0:
        raise ValueError("the lifetime must be positive")
    edges = np.arange(int(n_channels) + 1, dtype=float) * float(dt)
    # Integrating the exponential over each channel rather than sampling it keeps
    # the pattern correct when the lifetime is comparable to a channel width, which
    # is where a sampled pattern would put visible weight in the wrong bin.
    survival = np.exp(-edges / float(tau))
    weights = survival[:-1] - survival[1:]
    total = weights.sum()
    return weights / total if total > 0 else np.full(int(n_channels), 1.0 / n_channels)


def periodic_pattern(
    tau: float,
    irf: np.ndarray,
    dt: float,
    *,
    normalize_irf: bool = True,
) -> np.ndarray:
    """Convolve a wrapped decay with the instrument response, on the circle.

    The TAC window *is* one period, so the convolution of the response with the
    decay is **circular**: a photon whose response tail runs past the end of the
    window reappears at its start. Using a linear convolution instead would drop
    that tail and bias the pattern early.

    Parameters
    ----------
    tau : float
        Lifetime, in the units of *dt*.
    irf : numpy.ndarray
        Instrument response over one period, one entry per micro-time channel.
    dt : float
        Width of a micro-time channel.
    normalize_irf : bool
        Normalise the response to unit sum first. Off only when the caller has
        already done it.

    Returns
    -------
    numpy.ndarray
        The normalised pattern, same length as *irf*.
    """
    response = np.asarray(irf, dtype=float)
    if response.ndim != 1 or response.size == 0:
        raise ValueError("the instrument response must be a non-empty 1-D array")
    if normalize_irf:
        total = response.sum()
        if total <= 0.0:
            raise ValueError("the instrument response has no counts")
        response = response / total

    decay = wrapped_exponential_pattern(tau, response.size, dt)
    pattern = np.real(np.fft.irfft(np.fft.rfft(response) * np.fft.rfft(decay), n=response.size))
    pattern = np.clip(pattern, 0.0, None)
    total = pattern.sum()
    return pattern / total if total > 0 else pattern


def pattern_moments(pattern: np.ndarray, dt: float) -> tuple[float, float]:
    """Return the mean and variance of a micro-time pattern, in time units.

    These are *linear* moments of a quantity that lives on a circle, which is
    deliberate: the mean micro time recorded per burst is the arithmetic mean of the
    TAC channels, so the model has to predict the same arithmetic mean.

    Parameters
    ----------
    pattern : numpy.ndarray
        Non-negative weights per micro-time channel; normalised internally.
    dt : float
        Width of a micro-time channel.

    Returns
    -------
    mean, variance : float
    """
    weights = np.asarray(pattern, dtype=float)
    total = weights.sum()
    if total <= 0.0:
        raise ValueError("the pattern has no weight")
    weights = weights / total
    # Left edges, matching how the burst tables compute their mean micro time.
    time = np.arange(weights.size, dtype=float) * float(dt)
    mean = float(weights @ time)
    second = float(weights @ (time * time))
    return mean, max(second - mean * mean, 0.0)


def background_moments(n_channels: int, dt: float) -> tuple[float, float]:
    """Return the moments of an uncorrelated background, flat over the period.

    Dark counts and after-pulses carry no timing information, so their micro times
    are uniform over the window. Left-edge convention as everywhere here, which is
    why the mean is ``(n − 1)·dt / 2`` rather than ``n·dt / 2``.

    Parameters
    ----------
    n_channels : int
        Micro-time channels in one laser period.
    dt : float
        Width of a micro-time channel.

    Returns
    -------
    mean, variance : float
    """
    n = int(n_channels)
    time = np.arange(n, dtype=float) * float(dt)
    mean = float(time.mean())
    return mean, float(((time - mean) ** 2).mean())


def mixture_moments(
    weights: np.ndarray, means: np.ndarray, variances: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Combine component moments into the moments of their mixture.

    The law of total variance: a mixture is wider than its components by the spread
    of the components' own means. Dropping that second term is the classic way to
    make a two-state model look like a one-state model with a slightly wrong
    lifetime.

    ::

        μ = Σ wᵢ μᵢ
        v = Σ wᵢ (vᵢ + μᵢ²) − μ²

    Parameters
    ----------
    weights : array_like
        ``(..., n_components)`` non-negative weights; normalised along the last axis.
    means, variances : array_like
        ``(..., n_components)`` component moments.

    Returns
    -------
    mean, variance : numpy.ndarray
        Shaped like *weights* without its last axis.
    """
    w = np.asarray(weights, dtype=float)
    mu = np.asarray(means, dtype=float)
    v = np.asarray(variances, dtype=float)
    total = w.sum(axis=-1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        w = np.where(total > 0, w / total, 0.0)
    mean = np.sum(w * mu, axis=-1)
    second = np.sum(w * (v + mu * mu), axis=-1)
    return mean, np.clip(second - mean * mean, 0.0, None)


def unwrapped_mixture_moments(
    amplitudes: np.ndarray, lifetimes: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return the moments of a lifetime mixture that never wraps.

    The textbook identity, ``μ = Σ xᵢ τᵢ`` and ``v = 2 Σ xᵢ τᵢ² − μ²``. Kept because
    it is the limit the wrapped machinery must reproduce when the period dwarfs the
    lifetimes, which is the test that catches a wrap-around mistake — **not**
    because it is what the fit uses.

    Parameters
    ----------
    amplitudes : array_like
        ``(..., n)`` species amplitudes; normalised along the last axis.
    lifetimes : array_like
        ``(..., n)`` lifetimes.

    Returns
    -------
    mean, variance : numpy.ndarray
    """
    x = np.asarray(amplitudes, dtype=float)
    tau = np.asarray(lifetimes, dtype=float)
    total = x.sum(axis=-1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        x = np.where(total > 0, x / total, 0.0)
    mean = np.sum(x * tau, axis=-1)
    return mean, np.clip(2.0 * np.sum(x * tau * tau, axis=-1) - mean * mean, 0.0, None)
