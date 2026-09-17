"""Fusing bursts that the same molecule produced.

A molecule diffusing through a confocal spot does not always leave one burst.
It wanders out and back, or dims below the search threshold for a few hundred
microseconds, and the burst search — which knows only about count rate — cuts
the passage into two or three separate bursts.  Downstream every fragment is
counted as its own molecule: the photon-count distribution grows a short tail,
the proximity ratio of each fragment is noisier than the passage as a whole,
and a dynamics analysis sees a transition where there was only a gap.

The question "did these two bursts come from the same molecule?" already has an
answer in this package.  :func:`~.recurrence.same_molecule_probability` computes
``P_same(tau) = 1 - 1/G(tau)`` from the autocorrelation of the burst arrival
times (Hoffmann et al., PCCP 2011): at a lag where recurring bursts outnumber
coincidental ones, ``G > 1`` and ``P_same`` rises towards 1.  This module turns
that curve into a *decision*.

The user picks a probability threshold.  The curve is inverted into the largest
lag at which ``P_same`` still exceeds it (:func:`fusion_window`), and every run
of consecutive bursts separated by less than that lag becomes one burst
(:func:`group_labels`).  Threshold 1 fuses nothing; a low threshold fuses
aggressively and eventually starts merging genuinely different molecules — the
trade-off is the user's to see and make, which is why the plugin plots the
curve, the chosen window, and what fusion does to the burst statistics rather
than only reporting a number.

Two things this module deliberately does *not* decide:

* **What a fused burst is on disk.**  A ``.bur`` row is one
  ``(first photon, last photon)`` interval, so a fused burst is the *span* from
  the first photon of the first fragment to the last photon of the last, and it
  therefore contains the inter-fragment photons (mostly background) as well.
  :func:`fuse_burst_frame` merges the burst *table* without the photons — exact
  for the indices, the span and the signal photon counts, approximate for the
  quantities that depend on what lies in the gaps — and is meant for the fast
  preview.  Writing the fused analysis folder re-derives every column from the
  photons themselves.
* **Which time is the burst's.**  The lag is the difference of burst *mean macro
  times*, the same quantity ``P_same`` is built from, so the threshold means
  exactly what the plotted curve says it means.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np

from .recurrence import pair_statistics

__all__ = [
    "FusionWindow",
    "same_molecule_curve",
    "fusion_window",
    "group_labels",
    "group_slices",
    "fuse_burst_frame",
    "fusion_statistics",
]


@dataclasses.dataclass(frozen=True)
class FusionWindow:
    """The recurrence-time window a same-molecule threshold implies.

    Attributes
    ----------
    tau_s : numpy.ndarray
        Lag-bin centres (seconds).
    p_same : numpy.ndarray
        Same-molecule probability per lag bin. ``NaN`` marks a bin with too few
        counted pairs to judge (see ``min_pairs``), which is not the same as a
        bin that says "different molecule".
    g : numpy.ndarray
        The underlying pooled autocorrelation ``G(tau)``.
    counts, expected : numpy.ndarray
        Pooled counted and Poisson-expected pairs per bin, kept so a caller can
        show how much evidence each point of the curve rests on.
    threshold : float
        The requested same-molecule probability.
    tau_max_s : float
        Largest lag at which ``P_same`` still meets ``threshold``; bursts closer
        together than this are fused. ``0`` means fuse nothing.
    resolved : bool
        Whether the curve actually crossed the threshold inside the lag range.
        ``False`` means ``tau_max_s`` is the end of the range rather than a
        measured crossing — the window is a floor, not a result, and fusing on
        it merges everything the range covers.
    n_bursts : int
        Bursts the curve was estimated from.
    """

    tau_s: np.ndarray
    p_same: np.ndarray
    g: np.ndarray
    counts: np.ndarray
    expected: np.ndarray
    threshold: float
    tau_max_s: float
    resolved: bool
    n_bursts: int


def _as_measurements(times) -> list[np.ndarray]:
    """Normalise one array or a sequence of arrays into a list of arrays."""
    if times is None:
        return []
    if isinstance(times, np.ndarray) and times.ndim == 1:
        return [times.astype(float)]
    if isinstance(times, (list, tuple)) and times and np.isscalar(times[0]):
        return [np.asarray(times, dtype=float)]
    return [np.asarray(t, dtype=float) for t in times]


def same_molecule_curve(
    times_by_measurement,
    tau_min_s: float = 1e-4,
    tau_max_s: float = 1.0,
    n_bins: int = 60,
    min_pairs: int = 3,
    edge_correction: bool = True,
):
    """Pooled ``P_same(tau)`` over several measurements.

    Lags are only ever taken *within* a measurement — two files are separate
    acquisitions and a burst in one cannot recur in the other — but the counted
    and expected pair numbers are summed across files before dividing, so ten
    short measurements resolve the curve that none of them resolves alone.

    Parameters
    ----------
    times_by_measurement : sequence of numpy.ndarray
        Burst times in seconds, one array per measurement. A single array is
        accepted and treated as one measurement.
    tau_min_s, tau_max_s : float
        Log-spaced lag range, seconds.
    n_bins : int
        Number of logarithmic lag bins.
    min_pairs : int
        Bins holding fewer than this many counted pairs are returned as ``NaN``
        rather than as a probability. An empty short-lag bin in sparse data
        would otherwise read as a confident "different molecule" and truncate
        the fusion window at the first hole in the statistics.
    edge_correction : bool
        Finite-acquisition-time correction of the expected pair count.

    Returns
    -------
    tau : numpy.ndarray
        Lag-bin centres (geometric mean), seconds.
    p_same : numpy.ndarray
        Same-molecule probability, clipped to ``[0, 1]``, ``NaN`` where
        undetermined.
    g : numpy.ndarray
        Pooled autocorrelation.
    counts, expected : numpy.ndarray
        Pooled pair statistics.
    """
    edges = np.logspace(np.log10(tau_min_s), np.log10(tau_max_s), int(n_bins) + 1)
    tau = np.sqrt(edges[:-1] * edges[1:])
    counts = np.zeros(int(n_bins))
    expected = np.zeros(int(n_bins))
    for t in _as_measurements(times_by_measurement):
        c, e = pair_statistics(t, edges, edge_correction)
        counts += c
        expected += e

    with np.errstate(divide="ignore", invalid="ignore"):
        g = np.where(expected > 0, counts / np.where(expected > 0, expected, 1.0), np.nan)
        p_same = 1.0 - 1.0 / g
    p_same = np.clip(p_same, 0.0, 1.0)
    p_same[counts < max(int(min_pairs), 0)] = np.nan
    return tau, p_same, g, counts, expected


def _window_from_curve(tau: np.ndarray, p_same: np.ndarray, threshold: float):
    """Return the **largest** lag at which ``p_same`` still meets *threshold*.

    Deliberately read from the long end, not scanned outward from the short one.
    ``P_same`` is not monotonic: it *dips* at the shortest lags, because nothing
    recurs faster than a burst is long, so the shortest bins hold coincidences
    between different molecules and little else. Stopping at the first bin below
    the threshold would read that dip as "different molecule" and collapse the
    window to zero — on exactly the data where fusion is most obviously
    warranted. Taking the last bin above the threshold instead is also the
    convention the recurrence literature states the recurrence time in.

    Undetermined bins (``NaN``) are stepped over; they carry no evidence either
    way. The crossing between the last bin above and the next determined bin
    below is interpolated logarithmically, because the lag axis is logarithmic
    and a linear interpolation would systematically land short.

    Returns
    -------
    tau_max_s : float
        ``0.0`` when no determined bin reaches the threshold — nothing fuses.
    resolved : bool
        ``False`` when the threshold is met out to the end of the scanned range,
        so the window is where the scan stopped rather than a measured crossing.
    """
    determined = np.isfinite(p_same)
    above = np.flatnonzero(determined & (p_same >= threshold))
    if above.size == 0:
        return 0.0, True

    last = int(above[-1])
    beyond = np.flatnonzero(determined[last + 1 :]) + last + 1
    if beyond.size == 0:
        return float(tau[last]), False

    below = int(beyond[0])
    high, low = float(p_same[last]), float(p_same[below])
    if high <= low:  # non-monotonic pair; keep the last lag that qualified
        return float(tau[last]), True
    frac = float(np.clip((high - threshold) / (high - low), 0.0, 1.0))
    log_tau = np.log(float(tau[last])) + frac * (
        np.log(float(tau[below])) - np.log(float(tau[last]))
    )
    return float(np.exp(log_tau)), True


def fusion_window(
    times_by_measurement,
    threshold: float = 0.5,
    tau_min_s: float = 1e-4,
    tau_max_s: float = 1.0,
    n_bins: int = 60,
    min_pairs: int = 3,
    edge_correction: bool = True,
) -> FusionWindow:
    """Turn a same-molecule probability threshold into a recurrence-time window.

    Parameters
    ----------
    times_by_measurement : sequence of numpy.ndarray
        Burst times in seconds, one array per measurement.
    threshold : float
        Fuse two bursts only while the probability that they are the same
        molecule is at least this.
    tau_min_s, tau_max_s, n_bins, min_pairs, edge_correction
        Passed to :func:`same_molecule_curve`.

    Returns
    -------
    FusionWindow
        The curve, the resulting ``tau_max_s``, and whether the threshold was
        actually crossed inside the scanned lag range.
    """
    measurements = _as_measurements(times_by_measurement)
    tau, p_same, g, counts, expected = same_molecule_curve(
        measurements, tau_min_s, tau_max_s, n_bins, min_pairs, edge_correction
    )
    window, resolved = _window_from_curve(tau, p_same, float(threshold))
    return FusionWindow(
        tau_s=tau,
        p_same=p_same,
        g=g,
        counts=counts,
        expected=expected,
        threshold=float(threshold),
        tau_max_s=float(window),
        resolved=bool(resolved),
        n_bursts=int(sum(int(np.isfinite(t).sum()) for t in measurements)),
    )


def group_labels(
    times_s: np.ndarray,
    tau_max_s: float,
    max_group: int = 0,
) -> np.ndarray:
    """Label runs of bursts that fuse into one, within a single measurement.

    Fusion is transitive along the time axis: A fuses with B and B with C, so
    all three become one burst even when A and C are further apart than
    ``tau_max_s``. That is the physically right reading — the molecule was in
    the spot the whole time — but in a dense measurement it is also how a chain
    runs away, so ``max_group`` caps it.

    Parameters
    ----------
    times_s : numpy.ndarray
        Burst times in seconds, **ascending** (the caller sorts; the burst table
        is already in time order).
    tau_max_s : float
        Fuse consecutive bursts closer together than this. ``<= 0`` fuses
        nothing.
    max_group : int
        Largest number of bursts one fused burst may contain (``0`` = no limit).

    Returns
    -------
    numpy.ndarray
        Integer label per burst, ascending and contiguous from 0.
    """
    t = np.asarray(times_s, dtype=float)
    n = t.size
    if tau_max_s <= 0:
        return np.arange(n, dtype=int)
    labels = np.zeros(n, dtype=int)
    if n <= 1:
        return labels

    label = 0
    size = 1
    for i in range(1, n):
        gap = t[i] - t[i - 1]
        joins = np.isfinite(gap) and gap <= tau_max_s
        if joins and (max_group <= 0 or size < max_group):
            size += 1
        else:
            label += 1
            size = 1
        labels[i] = label
    return labels


def group_slices(labels: np.ndarray) -> list[np.ndarray]:
    """Return the row indices of each group, in label order."""
    labels = np.asarray(labels, dtype=int)
    if labels.size == 0:
        return []
    order = np.arange(labels.size)
    boundaries = np.flatnonzero(np.diff(labels)) + 1
    return np.split(order, boundaries)


# ── burst-table merge (no photon access) ────────────────────────────────────


def _burst_edges(frame, index) -> tuple:
    """Start and end time (ms) of one burst row, from its mean time and duration.

    ``Mean Macro Time (ms)`` is the midpoint of a burst's first and last photon
    and ``Duration (ms)`` their separation, so the two together give the burst's
    edges exactly — no photon access needed.
    """
    mean = float(np.asarray(frame["Mean Macro Time (ms)"])[index])
    dur = float(np.asarray(frame["Duration (ms)"])[index])
    return mean - 0.5 * dur, mean + 0.5 * dur


def fuse_burst_frame(frame, labels: np.ndarray):
    """Merge the rows of a burst table according to *labels*.

    A table-only merge, for previewing a threshold without touching the photon
    stream. Exact for the photon indices, the span, and the signal photon counts
    (a fused burst emitted the sum of its fragments' photons); **approximate for
    everything that depends on what lies between the fragments** — the emitted
    ``.bur`` counts the inter-fragment photons too, because a burst on disk is
    one interval. The per-window count rates are duration-weighted averages,
    the mean micro times photon-count-weighted averages (exact over the signal
    photons), and ``Confidence (sigma)`` is the strongest fragment's.

    Parameters
    ----------
    frame : pandas.DataFrame
        Burst rows of **one measurement**, in time order, with the zero rows of
        the interleaved ``.bur`` layout already removed.
    labels : numpy.ndarray
        Group label per row, from :func:`group_labels`.

    Returns
    -------
    pandas.DataFrame
        One row per fused burst, same columns as *frame*, plus ``Fusion Size``
        (fragments merged) and ``Fusion Gap (ms)`` (time inside the fused burst
        that no fragment covered).
    """
    from chisurf.core.datastore import (
        column_names as _column_names,
    )
    from chisurf.core.datastore import (
        numeric_column,
        store_from_rows,
    )

    columns = _column_names(frame)
    groups = group_slices(labels)

    # Coerce each column ONCE, not once per group per column: this loop runs
    # over every fused group, and the coercion does not depend on the group.
    numeric: dict[str, np.ndarray] = {}

    def values_of(name: str) -> np.ndarray:
        """The column as float64, computed on first use and kept."""
        if name not in numeric:
            numeric[name] = numeric_column(frame, name)
        return numeric[name]

    rows: list[dict[str, Any]] = []

    detectors = [
        c[len("Number of Photons (") : -1]
        for c in columns
        if c.startswith("Number of Photons (") and c.endswith(")")
    ]
    window_columns = [c for c in columns if c.startswith("S ") and "(kHz)" in c]

    for rows_of_group in groups:
        first, last = int(rows_of_group[0]), int(rows_of_group[-1])
        out: dict[str, Any] = {}

        start_ms, _ = _burst_edges(frame, first)
        _, stop_ms = _burst_edges(frame, last)
        duration = stop_ms - start_ms
        photons = float(np.nansum(values_of("Number of Photons")[rows_of_group]))

        covered = 0.0
        for i in rows_of_group:
            a, b = _burst_edges(frame, int(i))
            covered += b - a

        out["First Photon"] = int(np.nanmin(values_of("First Photon")[rows_of_group]))
        out["Last Photon"] = int(np.nanmax(values_of("Last Photon")[rows_of_group]))
        out["Duration (ms)"] = duration
        out["Mean Macro Time (ms)"] = 0.5 * (start_ms + stop_ms)
        out["Number of Photons"] = photons
        out["Count Rate (KHz)"] = photons / duration if duration > 0 else np.nan
        if "Confidence (sigma)" in columns:
            out["Confidence (sigma)"] = float(
                np.nanmax(values_of("Confidence (sigma)")[rows_of_group])
            )
        for column in ("First File", "Last File"):
            if column in columns:
                raw = np.asarray(frame[column])
                out[column] = raw[first] if column == "First File" else raw[last]

        for det in detectors:
            counts = values_of(f"Number of Photons ({det})")[rows_of_group]
            total = float(np.nansum(counts))
            out[f"Number of Photons ({det})"] = total

            seen = values_of(f"First Photon ({det})")[rows_of_group]
            has = seen >= 0
            if has.any():
                out[f"First Photon ({det})"] = int(seen[has].min())
                lasts = values_of(f"Last Photon ({det})")[rows_of_group]
                out[f"Last Photon ({det})"] = int(lasts[has].max())
                # The detector's own span: from the earliest to the latest
                # fragment in which it saw anything.
                det_durations = values_of(f"Duration ({det}) (ms)")[rows_of_group]
                det_means = values_of(f"Mean Macrotime ({det}) (ms)")[rows_of_group]
                starts = det_means - 0.5 * det_durations
                stops = det_means + 0.5 * det_durations
                det_start = float(starts[has].min())
                det_stop = float(stops[has].max())
                det_duration = det_stop - det_start
                out[f"Duration ({det}) (ms)"] = det_duration
                out[f"Mean Macrotime ({det}) (ms)"] = 0.5 * (det_start + det_stop)
                out[f"{det.capitalize()} Count Rate (KHz)"] = (
                    total / det_duration if det_duration > 0 else np.nan
                )
            else:
                out[f"First Photon ({det})"] = -1
                out[f"Last Photon ({det})"] = -1
                out[f"Duration ({det}) (ms)"] = -1.0
                out[f"Mean Macrotime ({det}) (ms)"] = -1.0
                out[f"{det.capitalize()} Count Rate (KHz)"] = -1.0

            micro_column = f"Mean Microtime ({det}) (ns)"
            if micro_column in columns:
                micro = values_of(micro_column)[rows_of_group]
                weights = counts
                valid = np.isfinite(micro) & (weights > 0)
                out[micro_column] = (
                    float(np.average(micro[valid], weights=weights[valid])) if valid.any() else 0.0
                )

        for column in window_columns:
            rates = values_of(column)[rows_of_group]
            weights = values_of("Duration (ms)")[rows_of_group]
            valid = np.isfinite(rates) & (rates >= 0) & (weights > 0)
            out[column] = (
                float(np.average(rates[valid], weights=weights[valid])) if valid.any() else -1.0
            )

        for column in columns:
            if column not in out:
                values = values_of(column)[rows_of_group]
                finite = values[np.isfinite(values)]
                out[column] = (
                    float(finite.mean()) if finite.size else np.asarray(frame[column])[first]
                )

        out["Fusion Size"] = int(len(rows_of_group))
        out["Fusion Gap (ms)"] = max(duration - covered, 0.0)
        rows.append(out)

    fused = store_from_rows(rows, columns=columns + ["Fusion Size", "Fusion Gap (ms)"])
    return fused


def fusion_statistics(before, after, labels: np.ndarray) -> dict[str, Any]:
    """How fusion changed the burst set, in the numbers a user judges it by.

    Parameters
    ----------
    before, after : pandas.DataFrame
        The burst table before and after fusion (data rows only).
    labels : numpy.ndarray
        Group label per input burst.

    Returns
    -------
    dict
        Burst counts, the group-size distribution, and mean/median duration and
        photon count on both sides. Proximity-ratio statistics are added by the
        caller, which owns the definition of the ratio.
    """
    from chisurf.core.datastore import (
        column_names as _column_names,
    )
    from chisurf.core.datastore import (
        numeric_column,
        row_count,
    )

    labels = np.asarray(labels, dtype=int)
    sizes = np.bincount(labels) if labels.size else np.zeros(0, dtype=int)
    fused = sizes[sizes > 1] if sizes.size else sizes

    def _stats(frame, column: str) -> dict[str, float]:
        if column not in _column_names(frame):
            return {"mean": float("nan"), "median": float("nan")}
        values = numeric_column(frame, column)
        values = values[np.isfinite(values)]
        if values.size == 0:
            return {"mean": float("nan"), "median": float("nan")}
        return {"mean": float(values.mean()), "median": float(np.median(values))}

    return {
        "n_bursts_before": int(row_count(before)),
        "n_bursts_after": int(row_count(after)),
        "n_fused_groups": int(fused.size),
        "n_bursts_in_fused_groups": int(fused.sum()) if fused.size else 0,
        "fused_fraction": float(fused.sum() / row_count(before)) if row_count(before) else 0.0,
        "largest_group": int(sizes.max()) if sizes.size else 0,
        "mean_group_size": float(sizes.mean()) if sizes.size else 0.0,
        "duration_ms": {
            "before": _stats(before, "Duration (ms)"),
            "after": _stats(after, "Duration (ms)"),
        },
        "photons": {
            "before": _stats(before, "Number of Photons"),
            "after": _stats(after, "Number of Photons"),
        },
        "count_rate_khz": {
            "before": _stats(before, "Count Rate (KHz)"),
            "after": _stats(after, "Count Rate (KHz)"),
        },
    }
