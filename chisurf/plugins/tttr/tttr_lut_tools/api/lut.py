"""Pure TAC linearization LUT algorithms (no Qt, no tttrlib, no CLI).

A **LUT** (look-up table) linearizes the TCSPC / TAC (time-to-amplitude
converter) micro-time axis: real TAC hardware has *differential non-linearity*
(DNL) — bins are not exactly equal in width — so a uniform-illumination
(uncorrelated-light) measurement, which *should* be flat, is not. The Felekyan
et al. (Rev. Sci. Instrum. 2005) construction turns that flat-light histogram
into a cumulative table ``NTAC_fract`` that remaps every photon's raw micro-time
onto a corrected, equal-width axis.

These functions are the shared computational core used by the api/cli/rpc/gui
layers. File and tttrlib IO lives in :mod:`..api.io`; correction application and
``settings.tttr.json`` handling live in :mod:`..api.settings`.
"""

from __future__ import annotations

import numpy as np

#: TAC bin counts that raw micro-time maxima are snapped to when auto-inferring.
NICE_BIN_COUNTS = (4096, 8192, 16384, 32768, 65536)


def infer_n_bins(micro: np.ndarray, n_bins_opt: int | None = None) -> int:
    """Infer a TAC histogram bin count from microtime data.

    Parameters
    ----------
    micro : numpy.ndarray
        Raw microtime values.
    n_bins_opt : int or None
        User-specified bin count. If positive it is returned directly.

    Returns
    -------
    int
        Histogram bin count (snapped to a nearby power-of-two-ish value).
    """
    if n_bins_opt and n_bins_opt > 0:
        return int(n_bins_opt)
    n_bins = int(np.max(micro)) + 1
    for nice_bins in NICE_BIN_COUNTS:
        if abs(n_bins - nice_bins) <= max(8, int(0.002 * nice_bins)):
            return nice_bins
    return n_bins


def histogram_micro(micro: np.ndarray, n_bins: int) -> np.ndarray:
    """Build a TAC histogram from microtime values.

    Parameters
    ----------
    micro : numpy.ndarray
        Raw microtime values.
    n_bins : int
        Number of histogram bins.

    Returns
    -------
    numpy.ndarray
        Histogram counts.
    """
    counts, _ = np.histogram(micro, bins=n_bins, range=(0, n_bins))
    return counts


def rolling_mean(x: np.ndarray, win: int) -> np.ndarray:
    """Return a padded rolling mean for a 1D array.

    Parameters
    ----------
    x : numpy.ndarray
        Input values.
    win : int
        Rolling window size.

    Returns
    -------
    numpy.ndarray
        Rolling mean with edge padding.
    """
    if win <= 1:
        return x.astype(float)
    cumulative = np.cumsum(np.insert(x, 0, 0))
    out = (cumulative[win:] - cumulative[:-win]) / float(win)
    pad_left = win // 2
    pad_right = len(x) - len(out) - pad_left
    return np.pad(out, (pad_left, pad_right), mode="edge")


def find_longest_true_run(mask: np.ndarray) -> tuple[int, int] | None:
    """Find the longest contiguous run of True values.

    Parameters
    ----------
    mask : numpy.ndarray
        Boolean mask.

    Returns
    -------
    tuple of int or None
        Half-open ``(start, stop)`` interval, or ``None`` when no True run exists.
    """
    best_len = 0
    best_start = -1
    cur_len = 0
    cur_start = -1
    for index, value in enumerate(mask):
        if value:
            if cur_len == 0:
                cur_start = index
            cur_len += 1
            if cur_len > best_len:
                best_len = cur_len
                best_start = cur_start
        else:
            cur_len = 0
    if best_len == 0:
        return None
    return best_start, best_start + best_len


def autodetect_linear_region(
    counts: np.ndarray,
    noffset_guess: int = 0,
    tail_exclude_frac: float = 0.0,
    win: int = 31,
    rel_dev_thresh: float = 0.10,
    slope_thresh: float = 0.02,
    min_width: int = 32,
) -> tuple[int, int]:
    """Detect a stable TAC plateau (the linear region) for LUT linearization.

    Parameters
    ----------
    counts : numpy.ndarray
        TAC histogram counts of a uniform-illumination measurement.
    noffset_guess : int, default=0
        Initial offset guess used to skip early bins.
    tail_exclude_frac : float, default=0.0
        Fraction of the tail to exclude.
    win : int, default=31
        Rolling-window size for stability estimates.
    rel_dev_thresh : float, default=0.10
        Maximum relative deviation from the rolling mean.
    slope_thresh : float, default=0.02
        Maximum relative rolling-mean slope.
    min_width : int, default=32
        Minimum plateau width.

    Returns
    -------
    tuple of int
        Half-open ``(linear_start, linear_stop)`` plateau interval.

    Raises
    ------
    ValueError
        If no sufficiently stable plateau is found.
    """
    n_bins = len(counts)
    lo = int(np.clip(noffset_guess, 0, n_bins - 2))
    hi = int(np.clip(n_bins - int(n_bins * tail_exclude_frac), lo + 1, n_bins))
    region_counts = counts[lo:hi].astype(float)
    mean = rolling_mean(region_counts, win=win)
    mean = np.where(mean <= 0, 1.0, mean)
    rel_dev = np.abs(region_counts / mean - 1.0)
    rel_slope = np.abs(np.gradient(mean) / np.maximum(mean, 1.0))
    stable = (rel_dev <= rel_dev_thresh) & (rel_slope <= slope_thresh)
    run = find_longest_true_run(stable)
    if run is None:
        raise ValueError("no plateau")
    start_rel, stop_rel = run
    if (stop_rel - start_rel) < min_width:
        raise ValueError(f"plateau too short ({stop_rel - start_rel} < {min_width})")
    return lo + start_rel, lo + stop_rel


def build_linearization_table(
    counts: np.ndarray,
    linear_start: int,
    linear_stop: int,
    ntac_required: int,
    noffset: int,
) -> dict[str, int | float | np.ndarray]:
    """Build the Felekyan-style TAC linearization table.

    Parameters
    ----------
    counts : numpy.ndarray
        Effective TAC histogram counts (uniform-illumination measurement).
    linear_start : int
        First bin of the selected linear region.
    linear_stop : int
        First bin after the selected linear region.
    ntac_required : int
        Desired number of NTAC bins.
    noffset : int
        Offset subtracted from corrected NTAC indices.

    Returns
    -------
    dict
        LUT table with the cumulative ``NTAC_fract`` array and metadata.
    """
    region = counts[linear_start:linear_stop]
    if region.sum() == 0:
        raise ValueError("Chosen linear region has zero counts.")
    mean = float(region.mean())
    widths = counts.astype(np.float64) / (mean if mean != 0 else 1.0)
    cumulative = np.cumsum(widths)
    total = cumulative[-1]
    if total <= 0:
        raise ValueError("Cumulative width is zero.")
    scale = float(ntac_required) / float(total)
    ntac_fract = scale * cumulative
    return {
        "NTAC_fract": ntac_fract,
        "w": widths,
        "f": scale,
        "n_bins": int(len(counts)),
        "linear_start": int(linear_start),
        "linear_stop": int(linear_stop),
        "ntac_required": int(ntac_required),
        "noffset": int(noffset),
        "n_mean": float(mean),
        "total_counts": int(counts.sum()),
    }


def stochastic_rebin_ntac(
    raw_micro: np.ndarray,
    ntac_fract: np.ndarray,
    noffset: int,
    seed: int | None = None,
    max_photons: int | None = None,
    rounding: str = "ceil",
    eps: float = 0.0,
) -> np.ndarray:
    """Apply a LUT to raw microtimes and return corrected NTAC indices.

    Parameters
    ----------
    raw_micro : numpy.ndarray
        Raw microtime values.
    ntac_fract : numpy.ndarray
        Cumulative NTAC fractions (the LUT).
    noffset : int
        Offset subtracted from corrected indices.
    seed : int or None, optional
        Random seed for the stochastic correction.
    max_photons : int or None, optional
        Cap on the number of photons processed (previews).
    rounding : {"ceil", "floor", "stochastic"}, default="ceil"
        Rounding mode.
    eps : float, default=0.0
        Small epsilon to avoid mapping exactly onto the last boundary.

    Returns
    -------
    numpy.ndarray
        Corrected integer NTAC indices.
    """
    rng = np.random.default_rng(seed)
    if eps and eps > 0:
        ntac_fract = np.array(ntac_fract, copy=True)
        ntac_fract[-1] = np.nextafter(ntac_fract[-1] - float(eps), -np.inf)
    n_bins = ntac_fract.shape[0]
    raw = raw_micro.astype(np.int64)
    if max_photons is not None and max_photons > 0:
        raw = raw[:max_photons]
    raw = np.clip(raw, 0, n_bins - 1)
    left = np.zeros_like(raw, dtype=np.float64)
    right = ntac_fract[raw].astype(np.float64)
    mask = raw > 0
    left[mask] = ntac_fract[raw[mask] - 1]
    span = right - left
    span = np.where(span > 0, span, 0.0)
    u = rng.random(raw.shape[0])
    frac_pos = left + u * span
    if rounding == "floor":
        ntac_int = np.floor(frac_pos).astype(np.int64)
    elif rounding == "stochastic":
        ntac_int = np.floor(frac_pos + rng.random(frac_pos.shape)).astype(np.int64)
    else:
        ntac_int = np.ceil(frac_pos).astype(np.int64)
    return ntac_int - noffset
