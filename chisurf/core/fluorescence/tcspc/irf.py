"""General instrument-response-function (IRF) helpers for TCSPC.

These are deliberately lightweight and dependency-free (NumPy only) so they can be reused
across the lifetime models, the FCS/2D-FLC plugins and any tool that needs an IRF when a
measured one is unavailable:

* :func:`synthetic_irf` -- build a (possibly skewed) Gaussian IRF on a time axis, reusing
  :func:`chisurf.core.math.functions.distributions.generalized_normal_distribution`.
* :func:`detect_rising_edge` -- locate the prompt/rise position of a measured decay or IRF.
* :func:`estimate_irf_from_decay` -- detect the rise of a measured decay and return a
  synthetic IRF centred there (a quick "synthetic IRF" when no measured IRF exists).
* :func:`scatter_irf` -- a measured scatter (water, Ludox) decay, background-corrected.
* :func:`irf_from_reference_decay` -- the IRF recovered from a reference dye of known lifetime
  (Rh110, ...) when no scatter was measured.
* :func:`reference_tail_lifetime` -- the lifetime of a mono-exponential reference, from its tail.

For full IRF extraction by Richardson-Lucy deconvolution see
:class:`chisurf.core.fluorescence.tcspc.irf_estimation.IRFEstimator`.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.math.functions.distributions import generalized_normal_distribution

__all__ = [
    "synthetic_irf",
    "detect_rising_edge",
    "estimate_irf_from_decay",
    "scatter_irf",
    "irf_from_reference_decay",
    "reference_tail_lifetime",
    "FWHM_TO_SIGMA",
]

# FWHM = 2*sqrt(2*ln2) * sigma  for a Gaussian
FWHM_TO_SIGMA = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))


def synthetic_irf(
    time_ns: np.ndarray,
    center_ns: float,
    fwhm_ns: float,
    *,
    shape: float = 0.0,
    norm: bool = True,
) -> np.ndarray:
    """Return a synthetic IRF sampled on ``time_ns``.

    A (generalized) normal pulse centred at ``center_ns`` with full-width-half-maximum
    ``fwhm_ns``. ``shape`` adds skewness (0 = symmetric Gaussian), which captures the
    asymmetric tail of a real detector response.

    Parameters
    ----------
    time_ns
        Time axis (ns).
    center_ns
        Pulse centre (ns).
    fwhm_ns
        Full width at half maximum (ns).
    shape
        Skewness parameter passed through to
        :func:`~chisurf.core.math.functions.distributions.generalized_normal_distribution`.
    norm
        Normalize the IRF to unit sum (default).
    """
    time_ns = np.asarray(time_ns, dtype=float)
    scale = max(float(fwhm_ns), 1e-12) * FWHM_TO_SIGMA
    return generalized_normal_distribution(
        time_ns, loc=float(center_ns), scale=scale, shape=float(shape), norm=norm
    )


def detect_rising_edge(decay: np.ndarray, *, smooth: int = 5) -> int:
    """Return the index of the steepest rising edge of a decay/IRF (the prompt position).

    The rise is the global maximum of the (optionally smoothed) first difference. This is a
    fast, robust estimate of the time-zero / prompt channel without any model fitting.

    Parameters
    ----------
    decay
        Measured decay or IRF histogram.
    smooth
        Box-smoothing width (samples) applied before differencing (default 5).
    """
    y = np.asarray(decay, dtype=float)
    if y.size < 3:
        return 0
    if smooth and smooth > 1:
        k = np.ones(int(smooth)) / float(smooth)
        y = np.convolve(y, k, mode="same")
    return int(np.argmax(np.diff(y)))


def estimate_irf_from_decay(
    decay: np.ndarray,
    time_ns: np.ndarray,
    *,
    fwhm_ns: float | None = None,
    shape: float = 0.0,
    smooth: int = 5,
) -> np.ndarray:
    """Detect the prompt position of a measured decay and return a matching synthetic IRF.

    Useful when no measured IRF is available: the rising edge of the decay marks the
    excitation pulse, so a synthetic pulse placed there is a serviceable IRF for
    deconvolution. ``fwhm_ns`` defaults to a few time-axis steps.

    Parameters
    ----------
    decay
        Measured decay histogram.
    time_ns
        Its time axis (ns).
    fwhm_ns
        IRF width (ns); defaults to ~4 time-axis bins.
    shape
        Skewness of the synthetic pulse.
    smooth
        Smoothing width for the rising-edge detection.
    """
    time_ns = np.asarray(time_ns, dtype=float)
    idx = detect_rising_edge(decay, smooth=smooth)
    center = float(time_ns[idx])
    if fwhm_ns is None:
        dt = float(np.median(np.diff(time_ns))) if time_ns.size > 1 else 1.0
        fwhm_ns = 4.0 * dt
    return synthetic_irf(time_ns, center, fwhm_ns, shape=shape)



def _window(n: int, window) -> tuple[int, int]:
    lo, hi = (0, n) if window is None else (max(0, int(window[0])), min(n, int(window[1])))
    return (lo, hi) if hi > lo else (0, n)


def _peak_support(signal: np.ndarray, noise: np.ndarray, lo: int, hi: int, n_sigma: float):
    """The contiguous bins around the strongest peak in ``[lo, hi)`` that stand above
    *n_sigma* times the noise (both smoothed over three bins)."""
    box = np.ones(3) / 3.0
    sm = np.convolve(signal, box, "same")
    sn = np.convolve(noise, box, "same") / np.sqrt(3.0)
    peak = lo + int(np.argmax(sm[lo:hi]))
    i = j = peak
    while i > lo and sm[i - 1] > n_sigma * sn[i - 1]:
        i -= 1
    while j < hi - 1 and sm[j + 1] > n_sigma * sn[j + 1]:
        j += 1
    return i, j + 1


def scatter_irf(
    counts: np.ndarray,
    *,
    buffer: np.ndarray | None = None,
    window: tuple[int, int] | None = None,
    floor_quantile: float = 0.1,
    n_sigma: float = 2.0,
) -> np.ndarray:
    """The IRF of a measured scatter decay (water, Ludox), corrected for its background.

    The buffer measurement (*buffer*, its counts scaled to the scatter's acquisition time), when
    there is one, is subtracted first: it carries the Raman line and the afterpulsing of the
    instrument, which are not the response. The flat floor left (dark counts) is the
    *floor_quantile* of the bins in *window*. The IRF is the contiguous peak standing above
    *n_sigma* times the Poisson noise; everything else is zero. Unnormalised counts.

    Parameters
    ----------
    counts : numpy.ndarray
        Micro-time histogram (counts) of the scatter measurement, one polarisation.
    buffer : numpy.ndarray, optional
        Histogram of the buffer measurement on the same bins, already scaled to *counts*' time.
    window : tuple of int, optional
        ``[start, stop)`` bins of the detector's gate (PIE): the peak searched there.
    floor_quantile : float
        Quantile of the gated bins taken as the flat background.
    n_sigma : float
        Noise multiple a bin must exceed to belong to the IRF.
    """
    raw = np.asarray(counts, dtype=float)
    lo, hi = _window(raw.size, window)
    d = raw - (np.asarray(buffer, dtype=float) if buffer is not None else 0.0)
    d = d - float(np.quantile(d[lo:hi], floor_quantile))
    noise = np.sqrt(np.clip(raw, 1.0, None))
    i, j = _peak_support(d, noise, lo, hi, n_sigma)
    out = np.zeros_like(d)
    out[i:j] = np.clip(d[i:j], 0.0, None)
    return out


def irf_from_reference_decay(
    counts: np.ndarray,
    tau_ns: float,
    dt_ns: float,
    *,
    window: tuple[int, int] | None = None,
    floor_quantile: float = 0.1,
    n_sigma: float = 2.0,
) -> np.ndarray:
    """The IRF recovered from the decay of a reference dye with a known single lifetime.

    A reference decay is the IRF convolved with ``exp(-t / tau)`` on top of a flat floor. On bins
    of width *dt_ns* that convolution is the recursion ``D[i] = IRF[i] + a D[i-1]`` with
    ``a = exp(-dt / tau)``, so after the floor is removed the IRF is ``D[i] - a D[i-1]``
    (periodically: the decay of the last pulse wraps into the first bins) -- exact for a
    mono-exponential dye, no iterative deconvolution. The difference is noisy where the decay is
    flat, so only the contiguous peak standing above *n_sigma* times its noise is kept.

    Parameters
    ----------
    counts : numpy.ndarray
        Micro-time histogram (counts) of the reference measurement, one polarisation, one period.
    tau_ns : float
        Fluorescence lifetime of the reference dye (Rh110 in water: 4.0 ns).
    dt_ns : float
        Width of one bin.
    window, floor_quantile, n_sigma
        As in :func:`scatter_irf`.

    Returns
    -------
    numpy.ndarray
        The IRF in counts (unnormalised), zero outside its peak.
    """
    raw = np.asarray(counts, dtype=float)
    lo, hi = _window(raw.size, window)
    d = raw - float(np.quantile(raw[lo:hi], floor_quantile))
    a = float(np.exp(-float(dt_ns) / float(tau_ns)))
    irf = d - a * np.roll(d, 1)
    var = np.clip(raw, 1.0, None)
    noise = np.sqrt(var + a * a * np.roll(var, 1))
    i, j = _peak_support(irf, noise, lo, hi, n_sigma)
    out = np.zeros_like(irf)
    out[i:j] = np.clip(irf[i:j], 0.0, None)
    return out


def reference_tail_lifetime(
    counts: np.ndarray,
    dt_ns: float,
    *,
    window: tuple[int, int] | None = None,
    skip_ns: float = 1.5,
    floor_quantile: float = 0.1,
) -> float | None:
    """The lifetime of a mono-exponential reference decay, from the slope of its tail.

    The tail starts *skip_ns* after the peak (past the IRF) and ends where the decay sinks into
    its floor (ten times the floor's noise, or 1 % of the peak); a straight line is fitted to the
    logarithm of the floor-free counts there, weighted by the counts. Use the magic-angle sum
    ``VV + 2 VH`` so the rotation of the dye does not bend the tail. The floor is taken as flat,
    which holds when the decay has died before the next pulse (a period of five lifetimes or
    more); a shorter period lifts the floor and shortens the result. ``None`` when the tail is
    shorter than five bins.
    """
    raw = np.asarray(counts, dtype=float)
    lo, hi = _window(raw.size, window)
    w = raw[lo:hi]
    floor = float(np.quantile(w, floor_quantile))
    d = w - floor
    peak = int(np.argmax(d))
    start = peak + max(1, int(round(float(skip_ns) / float(dt_ns))))
    limit = max(10.0 * np.sqrt(max(floor, 1.0)), 0.01 * d[peak])
    stop = start
    while stop < d.size and d[stop] > limit:
        stop += 1
    if stop - start < 5:
        return None
    x = np.arange(start, stop) * float(dt_ns)
    y = d[start:stop]
    slope = np.polyfit(x, np.log(y), 1, w=np.sqrt(y))[0]
    return float(-1.0 / slope) if slope < 0 else None
