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
import tttrlib

from chisurf.core.fluorescence.burst.background import (
    estimate_background_from_interphoton_times,
)
from chisurf.core.fluorescence.burst.burst import burst_filter
from chisurf.core.fluorescence.tcspc.irf import detect_rising_edge

__all__ = [
    "DetectorIrfBackground",
    "non_burst_mask",
    "extract_irf_background",
    "extract_mle_irf_background",
]


def _micro_time_channels_per_period(tttr: tttrlib.TTTR) -> int:
    """Return the number of micro-time channels in one laser period.

    The header's ``number_of_micro_time_channels`` is the TAC/ADC range, usually
    larger than one laser period; the physically meaningful length is
    ``macro_time_resolution / micro_time_resolution`` (macro ticks are the laser
    sync), capped at the ADC range. Falls back to the ADC range.
    """
    header = tttr.header
    adc = int(getattr(header, "number_of_micro_time_channels", 0) or 0)
    micro_res = float(getattr(header, "micro_time_resolution", 0.0) or 0.0)
    macro_res = float(getattr(header, "macro_time_resolution", 0.0) or 0.0)
    if micro_res > 0.0 and macro_res > 0.0:
        n = int(round(macro_res / micro_res))
        if adc > 0:
            n = min(n, adc)
        return max(1, n)
    return max(1, adc or 1)


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
            raise ValueError(
                f"mask length {keep.shape[0]} != photon count {rout.shape[0]}"
            )

    header = tttr.header
    dt_scale_ms = float(getattr(header, "macro_time_resolution", 1.0)) * 1000.0
    micro_res_ns = float(getattr(header, "micro_time_resolution", 0.0) or 0.0) * 1e9
    n_bins = _micro_time_channels_per_period(tttr)
    if micro_res_ns <= 0.0:
        micro_res_ns = 1.0
    time_ns = np.arange(n_bins, dtype=float) * micro_res_ns

    q = float(np.clip(baseline_quantile, 0.0, 1.0))

    results: dict[str, DetectorIrfBackground] = {}
    for name, det in detectors.items():
        chs = np.asarray(det.get("chs", []), dtype=int)
        ch_mask = np.isin(rout, chs) if chs.size else np.zeros_like(keep)
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
        mt_ranges = det.get("micro_time_ranges", []) or []
        bg_mask = det_bg
        if mt_ranges:
            mt_sel = np.zeros_like(keep)
            for start, stop in mt_ranges:
                mt_sel |= (micro >= int(start)) & (micro < int(stop))
            bg_mask = bg_mask & mt_sel
        times = macro[bg_mask]
        if times.size >= 2:
            dt_ms = np.diff(times.astype(np.float64)) * dt_scale_ms
            bg_khz = estimate_background_from_interphoton_times(
                dt_ms,
                binsize_ms=bg_binsize_ms,
                tail_fraction=bg_tail_fraction,
                min_counts=bg_min_counts,
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
      counts the fit subtracts: flat dark counts plus the scatter prompt).
    * The **IRF** pattern is the same histogram with its flat dark-count floor (a
      low quantile) subtracted, isolating the scatter prompt used for convolution.

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
        Dark-count floor quantile subtracted to form the IRF pattern.

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
    q = float(np.clip(baseline_quantile, 0.0, 1.0))

    def _half(channels: list[int]) -> tuple[np.ndarray, np.ndarray]:
        """Return (irf, bg) micro-time patterns for one polarization sub-channel set."""
        rout = np.asarray(non_burst.routing_channel)
        sel = np.isin(rout, channels)
        sub = non_burst[np.where(sel)[0]]
        hist = np.asarray(sub.get_microtime_histogram(binning)[0], dtype=np.float64)
        bg = hist.copy()
        if hist.sum() > 0:
            irf = np.clip(hist - float(np.quantile(hist, q)), 0.0, None)
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
        irf_p, bg_p = _half(p_chs)
        irf_s, bg_s = _half(s_chs)
        results[name] = {
            "irf": np.hstack([irf_p, irf_s]),
            "bg": np.hstack([bg_p, bg_s]),
        }

    return results
