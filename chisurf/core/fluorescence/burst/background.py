"""Background estimation for TTTR burst experiments.

This module implements an exponential tail fit to the interphoton time
histogram to estimate background count rates, following the approach used
in PAM's `Estimate_Background_From_Burst.m` and the methodology
of Ingargiola et al., PLoS ONE (2016).

The main public entry point is :func:`estimate_background_from_bursts`,
which is also re-exported via :mod:`chisurf.core.fluorescence.burst`.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import tttrlib

try:  # SciPy is a core dependency of ChiSurf, but fail clearly if missing
    from scipy.optimize import minimize
except Exception as exc:  # pragma: no cover - defensive guard
    raise ImportError(
        "chisurf.core.fluorescence.burst.background requires SciPy. "
        "Please ensure that the 'scipy' package is installed."
    ) from exc


@dataclass
class BackgroundDiagnostics:
    """Inter-photon-time histogram and exponential tail fit for one detector.

    Everything a diagnostic plot needs: the histogram, the fitted background
    model, the tail region used, and the resulting rate.  See
    :func:`interphoton_time_diagnostics`.

    Attributes
    ----------
    centers : numpy.ndarray
        Inter-photon-time histogram bin centres (ms).
    counts : numpy.ndarray
        Histogram counts per bin.
    tail_mask : numpy.ndarray
        Boolean mask of the bins used for the tail fit.
    model : numpy.ndarray
        Fitted background model ``A·exp(-rate·centers)`` over every bin (counts).
    rate_khz : float
        Estimated background rate (kHz == 1/ms).
    amplitude : float
        Fitted pre-exponential amplitude ``A``.
    """

    centers: np.ndarray = field(default_factory=lambda: np.empty(0))
    counts: np.ndarray = field(default_factory=lambda: np.empty(0))
    tail_mask: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=bool))
    model: np.ndarray = field(default_factory=lambda: np.empty(0))
    rate_khz: float = 0.0
    amplitude: float = 0.0


#: Lower bound used in place of zero for strictly positive fit parameters. Small
#: enough to be no constraint on any physical amplitude or rate, large enough that
#: the objective stays finite on the boundary the optimiser is allowed to visit.
_POSITIVE = 1e-12


def _fit_exponential_tail(centers, counts, max_dt, tail_fraction, min_counts,
                          tail_range_ms=None):
    """Poisson-MLE exponential fit of the inter-photon-time tail.

    Returns ``(amplitude, rate, tail_mask, success)``; ``rate`` falls back to the
    inverse mean tail interval if the optimiser fails.  Shared by
    :func:`estimate_background_from_interphoton_times` and
    :func:`interphoton_time_diagnostics` so both give identical rates.

    ``tail_range_ms`` is an explicit ``(low, high)`` window in milliseconds and
    replaces the ``tail_fraction`` rule when given. It exists because the
    fraction rule has no *upper* edge: the far tail of a real measurement is a
    handful of bins holding one count each, and an unbounded window lets that
    sparse end pull the fitted rate while contributing almost no information.
    """
    if tail_range_ms is not None:
        low, high = float(tail_range_ms[0]), float(tail_range_ms[1])
        valid = (centers >= low) & (centers <= high) & (counts >= min_counts)
    else:
        tail_threshold = tail_fraction * float(centers.max())
        valid = (centers > tail_threshold) & (counts >= min_counts)
    if not np.any(valid):
        return 0.0, 0.0, valid, False

    xdata = centers[valid]
    ydata = counts[valid].astype(np.float64)

    def neg_log_likelihood(params: np.ndarray) -> float:
        A, lam = params
        if A <= 0.0 or lam <= 0.0:
            return np.inf
        model = A * np.exp(-lam * xdata)
        eps = 1e-12
        model_safe = model + eps
        ratio = ydata / model_safe
        term = ydata * np.log(np.maximum(ratio, eps)) - ydata + model_safe
        return float(np.sum(term))

    A0 = float(counts[0]) if counts[0] > 0 else float(ydata.max())
    lam0 = 3.0 / max_dt
    # The bounds must exclude zero. The objective is ``+inf`` at ``A == 0`` or
    # ``lam == 0``, and L-BFGS-B evaluates *on* its bounds while building the
    # finite-difference gradient — so a closed bound at zero yields ``inf - inf``,
    # a NaN gradient, and an early stop reported as failure. The fallback then
    # returns the inverse mean tail interval instead of the fitted rate, which is
    # a different (and biased) estimator arriving with no error at all.
    result = minimize(
        neg_log_likelihood,
        np.array([A0, lam0], dtype=float),
        method="L-BFGS-B",
        bounds=((_POSITIVE, None), (_POSITIVE, None)),
    )
    if not result.success:
        mean_dt = float(np.mean(xdata))
        lam = 1.0 / mean_dt if mean_dt > 0.0 else 0.0
        return A0, max(lam, 0.0), valid, False
    A, lam = float(result.x[0]), float(result.x[1])
    return A, max(lam, 0.0), valid, True


def _histogram_interphoton(dt_ms, binsize_ms):
    """Return ``(centers, counts, max_dt)`` of the inter-photon-time histogram."""
    dt_ms = np.asarray(dt_ms, dtype=np.float64)
    dt_ms = dt_ms[dt_ms > 0.0]
    if dt_ms.size == 0:
        return None
    max_dt = float(dt_ms.max())
    if max_dt <= 0.0:
        return None
    edges = np.arange(0.0, max_dt + binsize_ms, binsize_ms, dtype=np.float64)
    if edges.size < 2:
        return None
    counts, edges = np.histogram(dt_ms, bins=edges)
    centers = 0.5 * (edges[:-1] + edges[1:])
    if centers.size == 0:
        return None
    return centers, counts, max_dt


def interphoton_time_diagnostics(
    dt_ms: np.ndarray,
    *,
    binsize_ms: float = 0.1,
    tail_fraction: float = 0.2,
    min_counts: int = 1,
    tail_range_ms=None,
) -> BackgroundDiagnostics:
    """Inter-photon-time histogram + tail fit for plotting (same rate as the estimator).

    Parameters mirror :func:`estimate_background_from_interphoton_times`.
    """
    hist = _histogram_interphoton(dt_ms, binsize_ms)
    if hist is None:
        return BackgroundDiagnostics()
    centers, counts, max_dt = hist
    A, lam, tail_mask, _ = _fit_exponential_tail(
        centers, counts, max_dt, tail_fraction, min_counts,
        tail_range_ms=tail_range_ms)
    model = A * np.exp(-lam * centers) if A > 0 and lam > 0 else np.zeros_like(centers)
    return BackgroundDiagnostics(
        centers=centers, counts=counts, tail_mask=tail_mask,
        model=model, rate_khz=lam, amplitude=A)


def estimate_background_from_interphoton_times(
    dt_ms: np.ndarray,
    *,
    binsize_ms: float = 0.1,
    tail_fraction: float = 0.2,
    min_counts: int = 1,
    tail_range_ms=None,
) -> float:
    """Estimate a background count rate (in kHz) from interphoton times.

    Parameters
    ----------
    dt_ms : np.ndarray
        One-dimensional array of interphoton times in **milliseconds**.
    binsize_ms : float, optional
        Histogram bin width in milliseconds. Default is 0.1 ms, matching
        the PAM implementation (``0:.1:max(MT)``).
    tail_fraction : float, optional
        Fraction of the histogram range used for the tail fit. Bins with
        centers strictly greater than ``tail_fraction * max(center)`` and
        at least ``min_counts`` counts are considered. A value of 0.2
        reproduces the PAM criterion ``dt > max(dt)/5`` (i.e. use the
        last ~80% of the range).
    min_counts : int, optional
        Minimum number of counts per histogram bin for inclusion in the
        fit. Default is 1.
    tail_range_ms : tuple of float, optional
        Explicit ``(low, high)`` fit window in milliseconds. Given, it replaces
        ``tail_fraction`` — which has no upper edge, so the sparse far tail is
        always in the fit whether or not it carries information.

    Returns
    -------
    float
        Estimated background count rate in **kHz**. Returns 0.0 if the
        estimate cannot be obtained (e.g. too few photons).
    """
    hist = _histogram_interphoton(dt_ms, binsize_ms)
    if hist is None:
        return 0.0
    centers, counts, max_dt = hist
    # lambda has units 1/ms, treated as kHz (1/ms == kHz).
    _, lam, _, _ = _fit_exponential_tail(
        centers, counts, max_dt, tail_fraction, min_counts,
        tail_range_ms=tail_range_ms)
    return float(lam)


def estimate_background_from_bursts(
    tttr: tttrlib.TTTR,
    detectors: Mapping[str, Mapping[str, Any]],
    *,
    binsize_ms: float = 0.1,
    tail_fraction: float = 0.8,
    min_counts: int = 1,
) -> dict[str, float]:
    """Estimate background count rates (kHz) for multiple detector definitions.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        TTTR object containing the photon data. The object must provide
        ``macro_times``, ``micro_times``, ``routing_channel``, and a
        ``header.macro_time_resolution`` attribute (in seconds).
    detectors : Mapping[str, Mapping[str, Any]]
        Detector definitions, typically obtained from
        :meth:`DetectorWizardPage.get_settings` as
        ``settings["detectors"]``. Each detector configuration should
        contain at least:

        - ``"chs"``: list of routing-channel integers.
        - ``"micro_time_ranges"``: list of ``(start_bin, stop_bin)``
          micro-time ranges. If omitted or empty, all micro-times are used.

    binsize_ms : float, optional
        Histogram bin width in milliseconds. Default is 0.1 ms.
    tail_fraction : float, optional
        Fraction of the histogram range used for the tail fit.
    min_counts : int, optional
        Minimum number of counts per histogram bin for inclusion in the
        fit.

    Returns
    -------
    Dict[str, float]
        Mapping from detector name to estimated background rate in kHz.
        Detectors for which no estimate can be obtained are assigned 0.0.
    """
    macro = np.asarray(tttr.macro_times, dtype=np.int64)
    if macro.size < 2:
        return {name: 0.0 for name in detectors.keys()}

    rout = np.asarray(tttr.routing_channel)
    micro = np.asarray(tttr.micro_times)

    header = tttr.header
    # macro_time_resolution is in seconds; convert dt to milliseconds
    dt_scale = float(getattr(header, "macro_time_resolution", 1.0)) * 1000.0

    results: dict[str, float] = {}

    for det_name, det_info in detectors.items():
        chs = np.asarray(det_info.get("chs", []), dtype=int)
        if chs.size == 0:
            results[det_name] = 0.0
            continue

        # Channel selection
        mask = np.isin(rout, chs)

        # Optional micro-time windowing
        mt_ranges = det_info.get("micro_time_ranges", []) or []
        if mt_ranges:
            mt_mask = np.zeros_like(mask, dtype=bool)
            for start, stop in mt_ranges:
                start_i = int(start)
                stop_i = int(stop)
                mt_mask |= (micro >= start_i) & (micro < stop_i)
            mask &= mt_mask

        times = macro[mask]
        if times.size < 2:
            results[det_name] = 0.0
            continue

        dt_ms = np.diff(times.astype(np.float64)) * dt_scale
        bg_khz = estimate_background_from_interphoton_times(
            dt_ms,
            binsize_ms=binsize_ms,
            tail_fraction=tail_fraction,
            min_counts=min_counts,
        )
        results[det_name] = float(bg_khz)

    return results


def _detector_interphoton_times(tttr, det_info, dt_scale):
    """Return the inter-photon times (ms) of one detector's photon stream."""
    rout = np.asarray(tttr.routing_channel)
    micro = np.asarray(tttr.micro_times)
    macro = np.asarray(tttr.macro_times, dtype=np.int64)
    chs = np.asarray(det_info.get("chs", []), dtype=int)
    if chs.size == 0:
        return np.empty(0)
    mask = np.isin(rout, chs)
    mt_ranges = det_info.get("micro_time_ranges", []) or []
    if mt_ranges:
        mt_mask = np.zeros_like(mask, dtype=bool)
        for start, stop in mt_ranges:
            mt_mask |= (micro >= int(start)) & (micro < int(stop))
        mask &= mt_mask
    times = macro[mask]
    if times.size < 2:
        return np.empty(0)
    return np.diff(times.astype(np.float64)) * dt_scale


def background_diagnostics_from_bursts(
    tttr: tttrlib.TTTR,
    detectors: Mapping[str, Mapping[str, Any]],
    *,
    binsize_ms: float = 0.1,
    tail_fraction: float = 0.8,
    min_counts: int = 1,
) -> dict[str, BackgroundDiagnostics]:
    """Per-detector inter-photon-time histogram + tail fit for diagnostic plots.

    The plotting companion of :func:`estimate_background_from_bursts`: returns a
    :class:`BackgroundDiagnostics` per detector (identical rate), carrying the
    histogram, the fitted model and the tail region.
    """
    header = tttr.header
    dt_scale = float(getattr(header, "macro_time_resolution", 1.0)) * 1000.0
    out: dict[str, BackgroundDiagnostics] = {}
    for det_name, det_info in detectors.items():
        dt_ms = _detector_interphoton_times(tttr, det_info, dt_scale)
        out[det_name] = interphoton_time_diagnostics(
            dt_ms, binsize_ms=binsize_ms, tail_fraction=tail_fraction,
            min_counts=min_counts)
    return out
