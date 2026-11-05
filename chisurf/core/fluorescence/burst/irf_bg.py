"""Extract an IRF and a background rate from the non-burst part of a single-molecule measurement.

In a confocal single-molecule measurement most of the acquisition time contains
no molecule in the focus. The photons detected during those **non-burst**
periods are not fluorescence from the labelled sample; they are

* uncorrelated dark counts / after-pulses — flat in micro-time, and
* scattered excitation light (Rayleigh/Raman) — a sharp prompt peak whose shape
  *is* the instrument response function (IRF).

So the non-burst stream doubles as a built-in scatter/background measurement: it
yields the per-detector background count rate *and* an IRF, without a separate
scatter or buffer-only acquisition. This module isolates the non-burst photons
(everything a burst search does **not** select), then for every detector

* fits the interphoton-time tail for the background rate (kHz), reusing
  :func:`chisurf.core.fluorescence.burst.background.estimate_background_from_interphoton_times`,
  and
* histograms the non-burst micro-times, subtracts the flat dark-count floor, and
  normalises the remainder to a scatter-derived IRF.

The IRF is deliberately per detector: each detection channel (colour) has its own
response, so a shared IRF must not silently replace distinct detector responses
(see :mod:`chisurf.core.fluorescence` design notes). Qt-free.

The main entry point is :func:`extract_irf_background`, re-exported via
:mod:`chisurf.core.fluorescence.burst`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from chisurf.core.fluorescence.channels import channel_mask
import tttrlib
from tttrlib import micro_time_mask

from chisurf.core.fluorescence.burst.background import (
    estimate_background_from_interphoton_times,
)
from chisurf.core.fluorescence.burst.burst import burst_filter
from chisurf.core.fluorescence.tcspc.irf import detect_rising_edge

__all__ = [
    "DetectorIrfBackground",
    "StrictBackground",
    "flat_scatter_background",
    "non_burst_mask",
    "strict_background_mask",
    "extract_irf_background",
    "extract_mle_irf_background",
]


def _micro_time_channels_per_period(tttr: tttrlib.TTTR) -> int:
    """The micro-time channels of one laser period (:func:`chisurf.core.fio.micro_time.channels_per_period`)."""
    from chisurf.core.fio.micro_time import channels_per_period

    return channels_per_period(tttr)


@dataclass
class DetectorIrfBackground:
    """IRF and background estimated from the non-burst photons of one detector.

    Attributes
    ----------
    name : str
        Detector name.
    background_khz : float
        Background count rate (kHz) from the non-burst interphoton-time tail fit.
    irf : numpy.ndarray
        Scatter-derived IRF: the non-burst micro-time histogram with the flat
        dark-count floor subtracted, clipped at zero and normalised to unit sum.
        One laser period long. All-zero if no scatter prompt is present.
    irf_raw : numpy.ndarray
        Raw (un-subtracted, un-normalised) non-burst micro-time histogram.
    time_ns : numpy.ndarray
        Micro-time axis (ns) for ``irf`` / ``irf_raw``.
    prompt_ns : float
        Rising-edge (prompt) position of the IRF, in ns.
    baseline_per_bin : float
        Flat dark-count level (counts per micro-time bin) subtracted to form ``irf``.
    n_background_photons : int
        Non-burst photons of this detector used for the estimate.
    n_burst_photons : int
        Burst photons of this detector (excluded from the estimate).
    """

    name: str
    background_khz: float
    irf: np.ndarray = field(repr=False)
    irf_raw: np.ndarray = field(repr=False)
    time_ns: np.ndarray = field(repr=False)
    prompt_ns: float
    baseline_per_bin: float
    n_background_photons: int
    n_burst_photons: int


def non_burst_mask(
    tttr: tttrlib.TTTR,
    *,
    min_photons: int = 60,
    photon_window: int = 10,
    time_window: float = 1e-3,
) -> np.ndarray:
    """Return a boolean mask of the photons that are **not** part of any burst.

    Runs the standard sliding-window burst search over all channels and inverts
    it, so the ``True`` photons are the background/scatter between molecules.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        Photon stream.
    min_photons : int
        Minimum photons for a burst (burst-search ``min_ph``).
    photon_window : int
        Photons used to estimate the local count rate (burst-search ``ph_window``).
    time_window : float
        Burst-search time window in **seconds**.

    Returns
    -------
    numpy.ndarray
        Boolean mask, ``True`` for non-burst photons.
    """
    burst = burst_filter(
        tttr,
        min_ph=int(min_photons),
        ph_window=int(photon_window),
        time_window=float(time_window),
    )
    return ~np.asarray(burst, dtype=bool)


@dataclass
class StrictBackground:
    """The photons of a single-molecule measurement that are background, and what is known of it.

    ``mask`` is ``True`` for a background photon. ``seconds`` is the time the kept stretches
    span (what a background *rate* is counted over), ``total_seconds`` the measurement's;
    ``rate_khz`` the background rate of the photons the local rate was judged on (all of them, or
    the channels given), ``threshold_khz`` the local rate above which a stretch was dropped (in
    the last selection),
    ``iterations`` how many re-estimates it took. ``warning`` says when too little is left.
    """

    mask: np.ndarray = field(repr=False)
    seconds: float
    total_seconds: float
    rate_khz: float
    threshold_khz: float
    photons: int
    iterations: int
    warning: str = ""
    #: ``rate_khz`` over the kept photons counted over the kept time: what a histogram of the kept
    #: photons divided by :attr:`seconds` is multiplied by to be a rate (the local-rate cut drops
    #: the background's own fast fluctuations with the molecules, about 5-15 %).
    rate_scale: float = 1.0

    @property
    def fraction(self) -> float:
        """The share of the measurement's time kept as background."""
        return self.seconds / self.total_seconds if self.total_seconds > 0 else 0.0


def _merged(lo: np.ndarray, hi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The union of the intervals ``[lo, hi]`` as sorted, disjoint intervals."""
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    if lo.size == 0:
        return lo, hi
    order = np.argsort(lo, kind="stable")
    lo, hi = lo[order], np.maximum.accumulate(hi[order])
    new = np.r_[True, lo[1:] > hi[:-1]]
    group = np.cumsum(new) - 1
    return lo[new], np.maximum.reduceat(hi, np.flatnonzero(new)) if group.size else hi


def _inside(t: np.ndarray, lo: np.ndarray, hi: np.ndarray, t_sorted: bool = True) -> np.ndarray:
    """Whether each time of *t* lies in one of the disjoint sorted intervals ``[lo, hi]``.

    The intervals are looked up in the photons (``M log N``), not every photon in the intervals
    (``N log M``): a measurement has tens of millions of photons and far fewer intervals, and this
    runs once per threshold the strict background selection tries."""
    if lo.size == 0:
        return np.zeros(t.size, dtype=bool)
    if not t_sorted:
        k = np.searchsorted(lo, t, side="right") - 1
        ok = k >= 0
        out = np.zeros(t.size, dtype=bool)
        out[ok] = t[ok] <= hi[k[ok]]
        return out
    # [first photon >= lo, first photon > hi) per interval: non-decreasing and non-overlapping, as
    # the intervals are disjoint and sorted
    edges = np.empty(2 * lo.size + 2, dtype=np.int64)
    edges[0], edges[-1] = 0, t.size
    edges[1:-1:2] = np.searchsorted(t, lo, side="left")
    edges[2:-1:2] = np.searchsorted(t, hi, side="right")
    flags = np.zeros(2 * lo.size + 1, dtype=bool)
    flags[1::2] = True  # outside, inside, outside, ... between the edges
    return np.repeat(flags, np.diff(edges))


def _merged_windows(lo: np.ndarray, hi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """:func:`_merged` of intervals whose starts *and* ends are both non-decreasing (sliding
    windows over sorted times): one pass, no sort."""
    if lo.size == 0:
        return lo, hi
    new = np.r_[True, lo[1:] > hi[:-1]]
    first = np.flatnonzero(new)
    last = np.r_[first[1:] - 1, lo.size - 1]
    return lo[first], hi[last]


def _poisson_tail_rate(gaps_s: np.ndarray) -> float:
    """The rate [Hz] of the Poisson part of inter-photon times: the slope of the log survival
    function over the long gaps (the 50th to 99.5th percentile). Between molecules the stream is
    background alone, so its long gaps fall as ``exp(-rate t)``; molecules only add short ones."""
    # unsorted: np.quantile selects its order statistics itself (a full sort of millions of gaps
    # cost as much as the rest of the strict selection)
    gaps = np.asarray(gaps_s, dtype=float)
    if gaps.size < 20:
        return 1.0 / max(float(np.mean(gaps)), 1e-12) if gaps.size else 0.0
    q = np.linspace(0.5, 0.995, 40)
    x = np.quantile(gaps, q)
    slope = np.polyfit(x, np.log(1.0 - q), 1)[0]
    return float(-slope) if slope < 0 else 1.0 / max(float(np.mean(gaps)), 1e-12)


def _gamma_quantile(shape: int, q: float) -> float:
    """The *q* quantile of a Gamma(*shape*, 1) variable (integer shape: an Erlang time), by
    bisection on its CDF ``1 - sum_{j<shape} e^-x x^j / j!``."""
    from math import exp, factorial

    def cdf(x: float) -> float:
        return 1.0 - sum(exp(-x) * x**j / factorial(j) for j in range(shape))

    lo, hi = 0.0, float(shape) * 10.0 + 10.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if cdf(mid) < q else (lo, mid)
    return 0.5 * (lo + hi)


def strict_background_mask(
    tttr: tttrlib.TTTR,
    burst_mask: np.ndarray,
    *,
    channels: Any = None,
    margin_ms: float = 2.0,
    margin_fraction: float = 0.5,
    photon_window: int = 10,
    false_alarm: float = 0.01,
    iterations: int = 4,
    min_fraction: float = 0.01,
    min_seconds: float = 1.0,
    rate_khz: float | None = None,
    accept: Any = None,
    tighten: float = 0.7,
    max_tighten: int = 8,
) -> StrictBackground:
    """The background photons of a measurement: stricter than "not in a burst".

    The photons a burst search did not select are not a buffer: molecules below the burst
    threshold pass the focus, and the flanks of every burst (the molecule entering and leaving)
    fall outside it. Their micro-time histogram has a fluorescence decay's shape and their rate is
    several times the background's. Kept here are only the stretches where the photon stream is at
    the background's level:

    1. every burst (*burst_mask*: ``True`` inside a burst) is widened on both sides by
       *margin_ms* plus *margin_fraction* of its duration (a longer burst, a slower molecule, has
       longer flanks), and those photons dropped;
    2. the local count rate is taken as in the burst search -- over *photon_window* consecutive
       photons (of *channels*, or all) -- and every photon inside a window faster than the
       threshold is dropped. The threshold is the rate a Poisson background exceeds in a window
       of that many photons only with probability *false_alarm* (the Erlang distribution of the
       window's duration): about 2.5 times the background rate for ten photons;
    3. the background rate starts as the exponential tail of the inter-photon times outside
       the widened bursts (the Poisson part, :func:`_poisson_tail_rate`; *rate_khz* when given)
       and is re-estimated from the stretches kept -- the exponential tail of their gaps -- and the
       selection repeated, *iterations* times at most or until it holds still.

    4. *accept* (``accept(mask) -> bool``), when given, judges the kept photons -- Burst MLE asks
       whether their histogram is a background's (flat + scatter) or still holds fluorescence.
       Where molecules below the threshold are in the focus nearly all the time, the long gaps
       are theirs and the rate of step 3 is theirs too; then the threshold is lowered by
       *tighten*, at most *max_tighten* times, until the selection is accepted or too little is
       left.

    A warning is set when less than *min_fraction* of the measurement or *min_seconds* is left,
    or when no selection was accepted.
    """
    macro_all = np.asarray(tttr.macro_times, dtype=np.int64)
    res_s = float(getattr(tttr.header, "macro_time_resolution", 1.0) or 1.0)
    n = macro_all.size
    burst = np.asarray(burst_mask, dtype=bool)
    if burst.shape[0] != n:
        raise ValueError(f"burst mask length {burst.shape[0]} != photon count {n}")
    sel = (
        channel_mask(np.asarray(tttr.routing_channel), np.asarray(channels, dtype=int))
        if channels is not None
        else np.ones(n, dtype=bool)
    )
    t = macro_all.astype(np.float64) * res_s  # seconds
    ordered = bool(n < 2 or np.all(macro_all[1:] >= macro_all[:-1]))
    total = float(t[-1] - t[0]) if n > 1 else 0.0

    # 1. bursts and their flanks, as time intervals
    idx = np.flatnonzero(burst)
    if idx.size:
        breaks = np.flatnonzero(np.diff(idx) != 1)
        starts, ends = np.r_[idx[0], idx[breaks + 1]], np.r_[idx[breaks], idx[-1]]
        pad = margin_ms * 1e-3 + margin_fraction * (t[ends] - t[starts])
        flanks = (t[starts] - pad, t[ends] + pad)
    else:
        flanks = (np.zeros(0), np.zeros(0))
    outside_flanks = ~_inside(t, *_merged(*flanks), t_sorted=ordered)

    # 2./3. the local rate at the background's level
    times = t[sel]
    m = max(2, int(photon_window))
    span = times[m - 1 :] - times[: times.size - m + 1] if times.size >= m else np.zeros(0)
    gaps = np.diff(times[outside_flanks[sel]])
    rate = float(rate_khz) if rate_khz else _poisson_tail_rate(gaps) / 1e3  # kHz
    factor = (m - 1) / _gamma_quantile(m - 1, false_alarm)
    # the local rate of every window [kHz], once: each threshold tried only compares against it
    positive = span > 0.0
    local_khz = (m - 1) / np.where(positive, span, np.inf) / 1e3

    def keep_slow(threshold_khz: float):
        fast = positive & (local_khz > threshold_khz)
        k = np.flatnonzero(fast)
        # the fast windows slide over sorted times: merged in one pass before the flanks join them
        fast_lo, fast_hi = _merged_windows(times[k], times[k + m - 1])
        lo, hi = _merged(np.r_[flanks[0], fast_lo], np.r_[flanks[1], fast_hi])
        mask = ~_inside(t, lo, hi, t_sorted=ordered)
        left = max(total - float(np.sum(np.clip(hi, t[0], t[-1]) - np.clip(lo, t[0], t[-1]))), 0.0)
        return mask, left

    def gap_rate(mask, fallback):
        # the rate from the gaps inside the kept stretches (their exponential tail): counting the
        # kept photons over the kept time is biased low, as the fast windows of the background's
        # own fluctuations were dropped with the molecules
        k_sel = mask[sel]
        inner = np.diff(times)[k_sel[1:] & k_sel[:-1]]
        return _poisson_tail_rate(inner) / 1e3 if inner.size >= 20 else fallback

    kept, seconds, done, threshold = outside_flanks, 0.0, 0, factor * rate
    for done in range(1, max(1, int(iterations)) + 1):
        threshold = factor * rate  # kHz
        kept, seconds = keep_slow(threshold)
        new = gap_rate(kept, rate)
        converged = abs(new - rate) <= 0.01 * max(rate, 1e-12)
        rate = new
        if converged:
            break
    accepted = True
    if accept is not None:
        accepted = bool(np.any(kept)) and bool(accept(kept))
        steps = 0
        while not accepted and steps < int(max_tighten) and seconds >= min_seconds:
            steps += 1
            done += 1
            threshold *= float(tighten)
            kept, seconds = keep_slow(threshold)
            if seconds < min_seconds or not np.any(kept):
                break
            accepted = bool(accept(kept))
        if accepted:
            rate = gap_rate(kept, threshold / factor)
    warning = ""
    if not accepted:
        warning = (
            f"no stretch of the measurement is at the background level (still fluorescence at "
            f"a local rate of {threshold:.2g} kHz, {seconds:.2g} s left)"
        )
    elif seconds < min_seconds or (total > 0 and seconds / total < min_fraction):
        warning = (
            f"only {seconds:.2g} s ({seconds / total:.1%} of the measurement) are at the "
            "background level: too little for a background"
            if total > 0
            else "no background time"
        )
    counted = float(np.sum(kept & sel)) / seconds / 1e3 if seconds > 0 else 0.0
    return StrictBackground(
        kept, seconds, total, float(rate), float(threshold), int(np.sum(kept)), done, warning,
        float(rate / counted) if counted > 0 else 1.0,
    )


#: Lifetimes [ns] of the fluorescence the photons outside the bursts carry, as
#: :func:`flat_scatter_background` models it to tell the scatter from it (never kept as background).
_FLUORESCENCE_TAUS = tuple(np.geomspace(0.2, 12.0, 16))


def flat_scatter_background(
    counts: np.ndarray, irf: np.ndarray, dt_ns: float, window: tuple[int, int] | None = None,
    *, margin: int = 2,
) -> tuple[np.ndarray, dict]:
    """The background of a burst decay from the photons outside the bursts: flat + scatter.

    The photons outside the bursts are mostly fluorescence (molecules below the burst threshold),
    so their histogram has a decay's shape; a fit given it as its background takes a second
    lifetime through gamma. A real background is a flat part (dark counts, afterpulsing) and a
    scatter part (Raman, water) with the IRF's shape. Per polarisation of *counts* (``VV | VH``,
    as is: rolled or not as the *irf* is):

    * the **flat** level is the median of the bins before the prompt (the gate's start to
      *margin* bins before the IRF) and of the gate's last tenth, the lower of the two -- the
      late tail still holds fluorescence when the decay has not died before the gate ends;
    * the **scatter** is the IRF's amplitude in a non-negative least-squares fit of the gate by
      the flat level (fixed) + IRF + IRF convolved with exponentials of 0.2-12 ns
      (:data:`_FLUORESCENCE_TAUS`); the fluorescence part of that fit is discarded. The shortest
      lifetime decides how much of a fast prompt is fluorescence: from 0.2 ns a 0.3 ns component
      is not taken for scatter (0.5 ns took a quarter of a FRET sample's non-burst photons for
      scatter) and a scatter on it is found within 15 %.

    Returns the pattern (flat over the gate plus the scatter, in the units of *counts*) and
    ``{"flat": (vv, vh), "scatter": (vv, vh), "fluorescence": (vv, vh)}`` (counts per bin;
    counts in the IRF's shape; counts the fit gave the fluorescence -- what tells a histogram of
    background from one that still holds molecules, :func:`strict_background_mask`).
    """
    from chisurf.core.math.numerics import nnls
    from chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction import polarised_kernels

    counts = np.asarray(counts, dtype=float)
    irf = np.asarray(irf, dtype=float)
    half = counts.size // 2
    lo, hi = (0, half) if window is None else (max(0, int(window[0])), min(half, int(window[1])))
    if hi <= lo:
        lo, hi = 0, half
    kernels = [polarised_kernels(half, dt_ns, tau, None)[0] for tau in _FLUORESCENCE_TAUS]
    parts, flats, scatters, fluorescence = [], [], [], []
    for k in range(2):
        y = counts[k * half : (k + 1) * half]
        shape = np.clip(irf[k * half : (k + 1) * half], 0.0, None) if irf.size == counts.size else np.zeros(half)
        if shape.sum() > 0:
            shape = shape / shape.sum()
        inside = np.flatnonzero(shape[lo:hi] > 1e-3 * shape.max()) if shape.any() else np.zeros(0, int)
        start = lo + int(inside[0]) if inside.size else hi
        regions = [y[lo + 1 : max(lo + 1, start - margin)], y[hi - max(5, (hi - lo) // 10) : hi]]
        levels = [float(np.median(r)) for r in regions if r.size >= 5]
        flat = min(levels) if levels else float(np.quantile(y[lo:hi], 0.05)) if hi > lo else 0.0
        scatter, fluor = 0.0, 0.0
        if shape.any() and hi - lo > len(kernels) + 2:
            columns = [shape] + [np.fft.irfft(np.fft.rfft(shape) * np.fft.rfft(kern, half), half)
                                 for kern in kernels]
            design = np.array(columns).T[lo:hi]
            weight = 1.0 / np.sqrt(np.maximum(y[lo:hi], 1.0))
            coef, _ = nnls(design * weight[:, None], (y[lo:hi] - flat) * weight)
            scatter = float(coef[0])
            fluor = float(np.sum(design[:, 1:] @ coef[1:]))
        part = np.zeros(half)
        part[lo:hi] = max(flat, 0.0)
        part += scatter * shape
        parts.append(part)
        flats.append(max(flat, 0.0))
        scatters.append(scatter)
        fluorescence.append(fluor)
    return np.hstack(parts), {
        "flat": tuple(flats), "scatter": tuple(scatters), "fluorescence": tuple(fluorescence),
    }



def extract_irf_background(
    tttr: tttrlib.TTTR,
    detectors: Mapping[str, Mapping[str, Any]],
    *,
    mask: np.ndarray | None = None,
    min_photons: int = 60,
    photon_window: int = 10,
    time_window: float = 1e-3,
    baseline_quantile: float = 0.2,
    smooth: int = 5,
    bg_binsize_ms: float = 0.1,
    bg_tail_fraction: float = 0.8,
    bg_min_counts: int = 1,
    bg_tail_range_ms=None,
) -> dict[str, DetectorIrfBackground]:
    """Estimate per-detector IRF and background from the non-burst photons.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        Single-molecule photon stream. Must expose ``macro_times``,
        ``micro_times``, ``routing_channel`` and ``header``.
    detectors : Mapping[str, Mapping[str, Any]]
        Detector definitions ``{name: {"chs": [...], "micro_time_ranges": [...]}}``,
        as produced by the shared detector wizard / burst :class:`Setup`. The
        micro-time ranges gate the **background** interphoton times; the **IRF**
        histogram always spans the full laser period for the detector's channels
        (a PIE window would clip the scatter prompt).
    mask : numpy.ndarray, optional
        Precomputed **non-burst** boolean mask (``True`` = keep). When omitted it
        is derived with :func:`non_burst_mask` from the burst-search parameters
        below, so the same burst definition used for selection defines the
        background here.
    min_photons, photon_window, time_window
        Burst-search parameters used only when ``mask`` is not given (see
        :func:`non_burst_mask`).
    baseline_quantile : float
        Quantile of the non-burst micro-time histogram taken as the flat
        dark-count floor per bin. Dark counts are uniform in micro-time while
        scatter is a localised peak, so a low quantile (default 0.2) is a robust
        floor. The floor is subtracted before normalising the IRF.
    smooth : int
        Box-smoothing width for the rising-edge (prompt) detection.
    bg_binsize_ms, bg_tail_fraction, bg_min_counts
        Passed through to
        :func:`~chisurf.core.fluorescence.burst.background.estimate_background_from_interphoton_times`.
    bg_tail_range_ms : tuple of float, optional
        The background fit window in ms. When omitted, one window for all detectors is
        seeded from their non-burst inter-photon times with
        :func:`~chisurf.core.fluorescence.burst.background.seed_tail_window`; only when no
        window can be fitted does ``bg_tail_fraction`` apply. The fraction rule alone put the
        window in the sparse far tail, where empty bins left a two-parameter fit with a few
        one-count bins (0.15 kHz for a 1.9 kHz background).

    Returns
    -------
    Dict[str, DetectorIrfBackground]
        Mapping from detector name to its IRF/background estimate.
    """
    rout = np.asarray(tttr.routing_channel)
    micro = np.asarray(tttr.micro_times)
    macro = np.asarray(tttr.macro_times, dtype=np.int64)

    if mask is None:
        keep = non_burst_mask(
            tttr,
            min_photons=min_photons,
            photon_window=photon_window,
            time_window=time_window,
        )
    else:
        keep = np.asarray(mask, dtype=bool)
        if keep.shape[0] != rout.shape[0]:
            raise ValueError(f"mask length {keep.shape[0]} != photon count {rout.shape[0]}")

    header = tttr.header
    dt_scale_ms = float(getattr(header, "macro_time_resolution", 1.0)) * 1000.0
    micro_res_ns = float(getattr(header, "micro_time_resolution", 0.0) or 0.0) * 1e9
    n_bins = _micro_time_channels_per_period(tttr)
    if micro_res_ns <= 0.0:
        micro_res_ns = 1.0
    time_ns = np.arange(n_bins, dtype=float) * micro_res_ns

    q = float(np.clip(baseline_quantile, 0.0, 1.0))

    # The non-burst inter-photon times of every detector first: one fit window for all.
    gaps: dict[str, np.ndarray] = {}
    for name, det in detectors.items():
        chs = np.asarray(det.get("chs", []), dtype=int)
        ch_mask = channel_mask(rout, chs) if chs.size else np.zeros_like(keep)
        times = macro[ch_mask & keep & micro_time_mask(micro, det.get("micro_time_ranges"))]
        gaps[name] = (
            np.diff(times.astype(np.float64)) * dt_scale_ms if times.size >= 2 else np.empty(0)
        )
    window = bg_tail_range_ms
    if window is None:
        from chisurf.core.fluorescence.burst.background import seed_tail_window

        window = seed_tail_window(gaps.values(), binsize_ms=bg_binsize_ms, min_counts=bg_min_counts)

    results: dict[str, DetectorIrfBackground] = {}
    for name, det in detectors.items():
        chs = np.asarray(det.get("chs", []), dtype=int)
        ch_mask = channel_mask(rout, chs) if chs.size else np.zeros_like(keep)
        det_bg = ch_mask & keep
        det_burst = ch_mask & ~keep

        # --- IRF: full-period micro-time histogram of the non-burst photons ---
        micro_bg = micro[det_bg]
        micro_bg = micro_bg[(micro_bg >= 0) & (micro_bg < n_bins)]
        irf_raw = np.bincount(micro_bg, minlength=n_bins)[:n_bins].astype(float)
        if irf_raw.sum() > 0:
            baseline = float(np.quantile(irf_raw, q))
            irf = np.clip(irf_raw - baseline, 0.0, None)
            total = irf.sum()
            if total > 0:
                irf = irf / total
            prompt_ns = float(time_ns[detect_rising_edge(irf_raw, smooth=smooth)])
        else:
            baseline = 0.0
            irf = np.zeros(n_bins, dtype=float)
            prompt_ns = 0.0

        # --- Background rate from the non-burst interphoton times -------------
        dt_ms = gaps[name]
        if dt_ms.size >= 1:
            bg_khz = estimate_background_from_interphoton_times(
                dt_ms,
                binsize_ms=bg_binsize_ms,
                tail_fraction=bg_tail_fraction,
                min_counts=bg_min_counts,
                tail_range_ms=window,
            )
        else:
            bg_khz = 0.0

        results[name] = DetectorIrfBackground(
            name=name,
            background_khz=float(bg_khz),
            irf=irf,
            irf_raw=irf_raw,
            time_ns=time_ns,
            prompt_ns=prompt_ns,
            baseline_per_bin=baseline,
            n_background_photons=int(det_bg.sum()),
            n_burst_photons=int(det_burst.sum()),
        )

    return results


def extract_mle_irf_background(
    tttr: tttrlib.TTTR,
    detectors: Mapping[str, Mapping[str, Any]],
    *,
    micro_time_binning: int = 1,
    mask: np.ndarray | None = None,
    min_photons: int = 60,
    photon_window: int = 10,
    time_window: float = 1e-3,
    baseline_quantile: float = 0.2,
    irf_model: str = "gaussian",
    irf_shape: float = 0.0,
) -> dict[str, dict[str, np.ndarray]]:
    """Build MLE-ready IRF and background patterns from the non-burst photons.

    Produces, per detector, the "vv_vh"-stacked ``[parallel, perpendicular]``
    micro-time patterns the burst-MLE lifetime fit consumes (its ``irf_np`` and
    ``bg_np`` per detector). The polarization split follows the MLE convention:
    even-indexed routing channels (``chs[::2]``) are parallel, odd-indexed
    (``chs[1::2]``) are perpendicular; a single-channel detector uses that channel
    for both halves. Each half is a micro-time histogram of that detector's
    **non-burst** photons at ``micro_time_binning`` resolution, so the same
    non-burst scatter/background that this module reads also serves the fit —
    no separate scatter or buffer acquisition.

    * The **background** pattern is the raw non-burst histogram (the per-bin
      counts the fit subtracts: flat dark counts plus the scatter prompt). It
      keeps its shape — the scattered-excitation background is not flat.
    * The **IRF** pattern is the scatter prompt used for convolution. By default
      (``irf_model="gaussian"``) it is a Gaussian **fitted to the experimental
      prompt** (a least-squares fit over a window around the peak). This matters:
      the raw non-burst histogram's prompt sits on a *fluorescence tail* (the
      non-burst periods still hold dim / passing molecules), and convolving the
      lifetime model with that tail-carrying "IRF" biases the recovered lifetime
      roughly two-fold short (a genuine ~2.2 ns decay came out ~1.1 ns on real BH
      smFRET data). A Gaussian cannot represent that slow tail, so fitting it to
      the prompt locks onto the sharp scatter peak and leaves the fluorescent
      artifact behind, while still following the measured prompt position/width. ``irf_model="experimental"`` (alias ``"raw"``) keeps
      the baseline-subtracted non-burst histogram (the measured scatter prompt) —
      use it when a genuinely clean scatter prompt is available. ``irf_shape``
      adds skewness (a right tail, as a real detector response has);
      ``irf_model="skewed"`` selects a sensible default skew. The shaping is the
      IRF Estimation tool's (:func:`~chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction.irf_from_prompt`);
      this function only selects, gates and histograms the photons.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        Single-molecule photon stream.
    detectors : Mapping[str, Mapping[str, Any]]
        Detector definitions ``{name: {"chs": [...], ...}}`` (as from the shared
        channel wizard / burst :class:`Setup`).
    micro_time_binning : int
        Micro-time coarsening factor (matches the MLE wizard's binning); each
        vv_vh half has length ``n_micro_channels / micro_time_binning``.
    mask : numpy.ndarray, optional
        Precomputed non-burst boolean mask; derived with :func:`non_burst_mask`
        from the burst-search parameters below when omitted.
    min_photons, photon_window, time_window
        Burst-search parameters used only when ``mask`` is not given.
    baseline_quantile : float
        Dark-count floor quantile subtracted to find the scatter prompt.
    irf_model : {"gaussian", "skewed", "experimental", "raw"}
        ``"gaussian"`` (default) fits a Gaussian to the extracted prompt (sheds
        the fluorescent tail); ``"skewed"`` fits a skew-normal; ``"experimental"``
        (alias ``"raw"``) returns the baseline-subtracted non-burst histogram.
    irf_shape : float
        Skewness of the fitted pulse (0 = symmetric Gaussian). ``irf_model=
        "skewed"`` selects a sensible non-zero default when this is 0.

    Returns
    -------
    dict[str, dict[str, numpy.ndarray]]
        ``{detector_name: {"irf": vv_vh_irf, "bg": vv_vh_bg}}``, each array the
        parallel and perpendicular halves concatenated.
    """
    if mask is None:
        keep = non_burst_mask(
            tttr,
            min_photons=min_photons,
            photon_window=photon_window,
            time_window=time_window,
        )
    else:
        keep = np.asarray(mask, dtype=bool)
    keep_idx = np.where(keep)[0]
    non_burst = tttr[keep_idx] if keep_idx.size else tttr[np.array([], dtype=int)]

    binning = max(1, int(micro_time_binning))
    from chisurf.core.fio.micro_time import channels_per_period, period_histogram

    period = channels_per_period(tttr)
    q = float(np.clip(baseline_quantile, 0.0, 1.0))
    from chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction import irf_from_prompt

    model = str(irf_model).lower()
    # a skewness given overrides the model's (the skewed model's default: 1.5, a mild right
    # tail, the characteristic shape of a real detector response)
    shape = float(irf_shape) if float(irf_shape) != 0.0 else None

    def _half(channels: list[int], gates=None) -> tuple[np.ndarray, np.ndarray]:
        """Return (irf, bg) micro-time patterns for one polarization sub-channel set.

        *gates* (the detector's raw micro-time ranges) restrict both to the detector's own window:
        a gated PIE acceptor would otherwise take the other laser's pulse -- the stronger one in
        its channels -- as its IRF, outside its fit window, and every lifetime ran to the bound.
        """
        rout = np.asarray(non_burst.routing_channel)
        sel = channel_mask(rout, channels)
        sub = non_burst[np.where(sel)[0]]
        # one excitation period of the measurement (not the TDC range its header names)
        hist = period_histogram(sub, binning, period=period)
        ranges = [r for r in (gates or []) if r is not None and len(r) >= 2]
        inside = np.ones(hist.size, dtype=bool)
        if ranges and hist.size:
            inside[:] = False
            for lo, hi in ranges:
                inside[max(0, int(lo) // binning) : max(0, int(np.ceil(int(hi) / binning)))] = True
            hist = np.where(inside, hist, 0.0)
        bg = hist.copy()
        if hist.sum() > 0:
            baseline = float(np.quantile(hist[inside], q)) if inside.any() else 0.0
            prompt = np.where(inside, np.clip(hist - baseline, 0.0, None), 0.0)
            # the IRF's shape is the IRF tool's (one implementation for every consumer)
            irf = irf_from_prompt([prompt], model=model, shape=shape).halves[0] * prompt.sum()
        else:
            irf = np.zeros_like(hist)
        return irf, bg

    results: dict[str, dict[str, np.ndarray]] = {}
    for name, det in detectors.items():
        chs = list(det.get("chs", []))
        if not chs:
            continue
        p_chs = chs[::2]
        s_chs = chs[1::2] if len(chs) > 1 else chs
        gates = det.get("micro_time_ranges")
        irf_p, bg_p = _half(p_chs, gates)
        irf_s, bg_s = _half(s_chs, gates)
        results[name] = {
            "irf": np.hstack([irf_p, irf_s]),
            "bg": np.hstack([bg_p, bg_s]),
        }

    return results
