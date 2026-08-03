"""The 2D histogram the fit scores against, and the model of it.

**Everything is binned on raw observables.** The proximity ratio ``N_R/(N_G+N_R)``
and the raw mean micro time, never a corrected efficiency or a fitted lifetime. All
the corrections — leakage, direct excitation, ``γ``, the background — live in the
forward model. That is not a stylistic choice: on corrected axes, changing ``γ``
moves the *data* histogram, and a deviance measured against a moving target is not
a fit statistic, because the optimizer can lower it by reshuffling bursts between
bins instead of by explaining them. On raw axes the data histogram is built once
and never moves again.

The model of that histogram is photon-distribution analysis conditioned per burst.
Given a burst's signal ``S`` and its two observation spans, the background counts
are Poisson with known means ``bg_c · t_c`` and the remaining signal partitions
binomially with the state's acceptor probability — the nested sum PDA already
uses, with the fixed time window replaced by the burst's own spans. The lifetime
axis rides on top: given ``N_G`` green photons drawn from a pattern of mean ``μ``
and variance ``v``, the recorded ``⟨t⟩`` has mean ``μ`` and variance ``v / N_G``.

The cost is independent of how many bursts are under the histogram, because the
bursts enter only through the binned nuisance measure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.special import gammaln

from chisurf.core.fluorescence.mfd.moments import mixture_moments
from chisurf.core.fluorescence.mfd.prepare import BurstPreparation, NuisanceMeasure

__all__ = [
    "HistogramAxes",
    "MfdHistogram",
    "acceptor_count_distribution",
    "model_histogram",
    "observed_histogram",
]

#: Green photons below which the Gaussian ``⟨t⟩`` kernel is not trustworthy. The
#: exact self-convolution path exists (``kernel="exact"``) but costs a transform per
#: photon count, so the default is to exclude the low-count wing — and to *report*
#: how much was excluded, never to drop it quietly.
DEFAULT_MIN_GREEN_PHOTONS = 20

#: How many standard deviations of Poisson background to sum over before truncating
#: the nested sum. Six is far past where the terms matter and cheap at these means.
_BACKGROUND_SIGMA = 6.0


@dataclass(frozen=True)
class HistogramAxes:
    """Bin edges of the 2D histogram, in raw observable units.

    Attributes
    ----------
    ratio_edges : numpy.ndarray
        Edges of the proximity-ratio axis, ``N_R / (N_G + N_R)``.
    micro_time_edges : numpy.ndarray
        Edges of the mean-micro-time axis, nanoseconds.
    """

    ratio_edges: np.ndarray
    micro_time_edges: np.ndarray

    @classmethod
    def default(
        cls,
        *,
        n_ratio: int = 41,
        n_micro_time: int = 41,
        micro_time_range: tuple[float, float] = (0.0, 8.0),
    ) -> HistogramAxes:
        """Return evenly spaced axes covering the whole proximity-ratio range.

        Parameters
        ----------
        n_ratio, n_micro_time : int
            Number of bins on each axis.
        micro_time_range : tuple of float
            Mean-micro-time range, ns.

        Returns
        -------
        HistogramAxes
        """
        return cls(
            ratio_edges=np.linspace(0.0, 1.0, int(n_ratio) + 1),
            micro_time_edges=np.linspace(
                float(micro_time_range[0]), float(micro_time_range[1]),
                int(n_micro_time) + 1,
            ),
        )

    @property
    def shape(self) -> tuple[int, int]:
        """Return the histogram shape ``(n_ratio, n_micro_time)``."""
        return self.ratio_edges.size - 1, self.micro_time_edges.size - 1


@dataclass
class MfdHistogram:
    """A 2D MFD histogram and the account of what did not go into it.

    Attributes
    ----------
    counts : numpy.ndarray
        ``(n_ratio, n_micro_time)`` counts.
    axes : HistogramAxes
        The bin edges.
    summary : dict
        What was excluded and why. Never empty: a histogram that quietly dropped a
        third of its bursts looks exactly like one that did not.
    """

    counts: np.ndarray
    axes: HistogramAxes
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def n_used(self) -> int:
        """Return the number of bursts in the histogram."""
        return int(self.counts.sum())


def observed_histogram(
    preparation: BurstPreparation,
    axes: HistogramAxes | None = None,
    *,
    green: str = "green",
    red: str = "red",
    min_green_photons: int = DEFAULT_MIN_GREEN_PHOTONS,
) -> MfdHistogram:
    """Bin the measured bursts onto the raw axes, once and for all.

    Parameters
    ----------
    preparation : BurstPreparation
        From :func:`~chisurf.core.fluorescence.mfd.prepare.prepare_burst_folder`.
    axes : HistogramAxes, optional
        Bin edges; a default covering the full ratio range is used when omitted.
    green, red : str
        Detector names.
    min_green_photons : int
        Bursts with fewer green photons are excluded, because the Gaussian ``⟨t⟩``
        kernel the model uses is not valid there. The **model must apply the same
        cut**, which is why it is stored in the summary rather than left implicit.

    Returns
    -------
    MfdHistogram
    """
    preparation.require_verified([green, red])
    axes = axes or HistogramAxes.default()
    g = preparation.channel_index(green)
    r = preparation.channel_index(red)

    n_g = preparation.counts[:, g]
    n_r = preparation.counts[:, r]
    micro = preparation.mean_micro_time[:, g]

    total = n_g + n_r
    usable = (total > 0) & (n_g >= int(min_green_photons)) & np.isfinite(micro)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(total > 0, n_r / np.maximum(total, 1), 0.0)

    counts, _, _ = np.histogram2d(
        ratio[usable],
        micro[usable],
        bins=(axes.ratio_edges, axes.micro_time_edges),
    )
    n_input = int(preparation.counts.shape[0])
    n_used = int(counts.sum())
    summary = {
        "n_input": n_input,
        "n_used": n_used,
        "min_green_photons": int(min_green_photons),
        "n_excluded_few_green": int((~usable).sum()),
        "n_outside_axes": int(usable.sum()) - n_used,
        "excluded_fraction": 1.0 - n_used / n_input if n_input else 0.0,
    }
    return MfdHistogram(counts=counts, axes=axes, summary=summary)


#: Cached ``log k!``. The nested background sum asks for binomial coefficients tens
#: of thousands of times per model evaluation, for a handful of distinct photon
#: counts; recomputing ``gammaln`` each time was 87% of the evaluation cost.
_LOG_FACTORIAL = gammaln(np.arange(1024, dtype=float) + 1.0)


def _log_factorial(n_max: int) -> np.ndarray:
    """Return ``log k!`` for ``k = 0 … n_max``, growing the cache as needed."""
    global _LOG_FACTORIAL
    if n_max >= _LOG_FACTORIAL.size:
        size = 1 << int(np.ceil(np.log2(n_max + 2)))
        _LOG_FACTORIAL = gammaln(np.arange(size, dtype=float) + 1.0)
    return _LOG_FACTORIAL


def _log_binomial_coefficients(n: int) -> np.ndarray:
    """Return ``log C(n, k)`` for ``k = 0 … n``."""
    table = _log_factorial(n)
    return table[n] - table[: n + 1] - table[n::-1]


def _binomial_pmf(n: int, p: float) -> np.ndarray:
    """Return the binomial pmf over ``k = 0 … n``, in a way that survives p = 0 or 1."""
    if n < 0:
        return np.zeros(0)
    out = np.zeros(n + 1)
    if p <= 0.0:
        out[0] = 1.0
        return out
    if p >= 1.0:
        out[-1] = 1.0
        return out
    k = np.arange(n + 1, dtype=float)
    log_pmf = (
        _log_binomial_coefficients(n) + k * np.log(p) + (n - k) * np.log1p(-p)
    )
    return np.exp(log_pmf)


def _poisson_pmf(mean: float, k_max: int) -> np.ndarray:
    """Return the Poisson pmf over ``k = 0 … k_max``."""
    if mean <= 0.0:
        out = np.zeros(k_max + 1)
        out[0] = 1.0
        return out
    k = np.arange(k_max + 1, dtype=float)
    return np.exp(k * np.log(mean) - mean - _log_factorial(k_max)[: k_max + 1])


def acceptor_count_distribution(
    signal: int,
    p_red: float,
    background_green: float,
    background_red: float,
) -> np.ndarray:
    """Return ``P(N_R | S)`` for one burst, with Poisson background and binomial signal.

    The nested sum of photon-distribution analysis, conditioned on this burst rather
    than on a fixed time window. Of the ``S`` photons the burst holds, ``b_G`` and
    ``b_R`` are uncorrelated background — Poisson with the means the *observation
    spans* imply — and the remaining ``S − b_G − b_R`` are signal, partitioning
    binomially::

        P(N_R | S) = Σ_{b_G, b_R} Pois(b_G) Pois(b_R) Binom(N_R − b_R ; S − b_G − b_R, p)

    Parameters
    ----------
    signal : int
        Total photons in the two channels.
    p_red : float
        Probability that a *signal* photon is detected in the acceptor channel.
    background_green, background_red : float
        Expected background counts in each channel — the rate times that channel's
        observation span for this burst.

    Returns
    -------
    numpy.ndarray
        ``(signal + 1,)``, summing to one.
    """
    s = int(signal)
    if s < 0:
        raise ValueError("the signal must not be negative")
    out = np.zeros(s + 1)
    if s == 0:
        out[0] = 1.0
        return out

    def _cut(mean: float) -> int:
        return int(min(s, np.ceil(mean + _BACKGROUND_SIGMA * np.sqrt(max(mean, 1.0)))))

    green_pmf = _poisson_pmf(background_green, _cut(background_green))
    red_pmf = _poisson_pmf(background_red, _cut(background_red))

    # The binomial depends on the background only through the *total* b_G + b_R, so
    # it is computed once per distinct total rather than once per pair — an order of
    # magnitude fewer exponentials, for identical arithmetic.
    n_max_background = min(s, green_pmf.size + red_pmf.size - 2)
    binomials = [
        _binomial_pmf(s - m, p_red) for m in range(n_max_background + 1)
    ]

    for b_g, w_g in enumerate(green_pmf):
        if w_g <= 0.0 or b_g > s:
            continue
        for b_r, w_r in enumerate(red_pmf):
            if w_r <= 0.0 or b_g + b_r > s:
                continue
            n = s - b_g - b_r
            out[b_r : b_r + n + 1] += (w_g * w_r) * binomials[b_g + b_r]

    total = out.sum()
    return out / total if total > 0 else out


def _gaussian_bin_weights(
    mean: np.ndarray, sigma: np.ndarray, edges: np.ndarray
) -> np.ndarray:
    """Spread unit weight over bins according to a Gaussian, via its CDF.

    Parameters
    ----------
    mean, sigma : numpy.ndarray
        ``(n,)`` kernel parameters.
    edges : numpy.ndarray
        ``(n_bins + 1,)`` bin edges.

    Returns
    -------
    numpy.ndarray
        ``(n, n_bins)``; rows sum to at most one (weight outside the axis is lost,
        which is the same treatment the observed histogram gives it).
    """
    from scipy.special import erf

    safe = np.maximum(sigma, 1e-12)[:, None]
    z = (edges[None, :] - mean[:, None]) / (safe * np.sqrt(2.0))
    cdf = 0.5 * (1.0 + erf(z))
    return np.diff(cdf, axis=1)


def model_histogram(
    nuisance: NuisanceMeasure,
    axes: HistogramAxes,
    *,
    component_weights: np.ndarray,
    p_red: np.ndarray,
    green_mean: np.ndarray,
    green_variance: np.ndarray,
    background_rates: tuple[float, float],
    background_micro_time: tuple[float, float],
    min_green_photons: int = DEFAULT_MIN_GREEN_PHOTONS,
    binned: tuple[np.ndarray, np.ndarray, list[np.ndarray]] | None = None,
) -> np.ndarray:
    """Predict the 2D histogram, given the nuisance measure and a state mixture.

    Deliberately expressed in terms of *components* rather than of states, so that
    kinetics needs no change here: a static model supplies one component per
    nuisance cell, and a kinetic one supplies the occupation-time grid with
    ``P(f | T, K)`` as the weights. What a component is, the histogram does not care.

    Parameters
    ----------
    nuisance : NuisanceMeasure
        The empirical ``P(S, t_G, t_R)``.
    axes : HistogramAxes
        Bin edges, the same ones the observed histogram used.
    component_weights : numpy.ndarray
        ``(n_cells, n_components)`` weights, normalised per cell.
    p_red : numpy.ndarray
        ``(n_cells, n_components)`` acceptor probability of a signal photon.
    green_mean, green_variance : numpy.ndarray
        ``(n_cells, n_components)`` moments of the green channel's *signal* pattern,
        in ns and ns².
    background_rates : tuple of float
        ``(green, red)`` background count rates, s⁻¹.
    background_micro_time : tuple of float
        ``(mean, variance)`` of the flat background's micro time, ns and ns².
    min_green_photons : int
        The same cut the observed histogram applied. Applying a different one here
        is the single easiest way to produce a beautifully fitting wrong answer.
    binned : tuple, optional
        A precomputed :meth:`NuisanceMeasure.binned` result, so a fit loop does not
        rebin every evaluation.

    Returns
    -------
    numpy.ndarray
        ``(n_ratio, n_micro_time)``, summing to the number of bursts the cut keeps.
    """
    weights, signal, spans = binned if binned is not None else nuisance.binned()
    bg_green_rate, bg_red_rate = background_rates
    bg_mean, bg_variance = background_micro_time

    n_ratio, n_micro = axes.shape
    out = np.zeros((n_ratio, n_micro))

    occupied = np.nonzero(weights > 0)[0]
    for cell in occupied:
        s = int(round(float(signal[cell])))
        if s <= 0:
            continue
        b_green = float(bg_green_rate) * float(spans[0][cell])
        b_red = float(bg_red_rate) * float(spans[1][cell])

        n_red = np.arange(s + 1)
        n_green = s - n_red
        keep = n_green >= int(min_green_photons)
        if not keep.any():
            continue

        ratio = n_red / float(s)
        ratio_bin = np.clip(
            np.digitize(ratio, axes.ratio_edges) - 1, 0, n_ratio - 1
        )

        # The background's share of the green channel. Known only in expectation
        # here — the nested sum below knows the actual split, but carrying it
        # through the lifetime axis as well would multiply the cost by the
        # background range for a correction that is second order in b/N.
        with np.errstate(invalid="ignore", divide="ignore"):
            background_fraction = np.clip(
                np.where(n_green > 0, b_green / np.maximum(n_green, 1), 0.0), 0.0, 1.0
            )

        for component in range(component_weights.shape[1]):
            share = float(component_weights[cell, component])
            if share <= 0.0:
                continue
            counts = acceptor_count_distribution(
                s, float(p_red[cell, component]), b_green, b_red
            )
            counts = counts * weights[cell] * share

            mean, variance = mixture_moments(
                np.stack(
                    [1.0 - background_fraction, background_fraction], axis=-1
                ),
                np.broadcast_to(
                    [green_mean[cell, component], bg_mean],
                    background_fraction.shape + (2,),
                ),
                np.broadcast_to(
                    [green_variance[cell, component], bg_variance],
                    background_fraction.shape + (2,),
                ),
            )
            sigma = np.sqrt(variance / np.maximum(n_green, 1))

            rows = _gaussian_bin_weights(
                mean[keep], sigma[keep], axes.micro_time_edges
            )
            np.add.at(
                out,
                ratio_bin[keep],
                rows * counts[keep][:, None],
            )

    return out
