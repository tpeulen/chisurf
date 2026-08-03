"""Recurrence Analysis of Single Particles (RASP).

RASP (Hoffmann et al., Phys. Chem. Chem. Phys. 2011) extracts slow (ms..s)
conformational dynamics and sub-population kinetics from freely-diffusing
single-molecule FRET data — timescales far longer than a single burst.  A
molecule that diffuses out of the confocal spot and returns produces a second
burst; within the *recurrence time* it is likely the **same** molecule, so
correlating an initially-selected FRET sub-population with the bursts that
recur shortly after reveals inter-conversion between states.

Two quantities:

* :func:`same_molecule_probability` — the probability that a burst recurring a
  time ``tau`` after an initial burst is the same molecule, ``P_same(tau) =
  1 - 1/G(tau)`` where ``G`` is the burst-arrival-time autocorrelation.  It sets
  the recurrence-time window in which recurrence histograms are meaningful.
* :func:`recurrence_efficiencies` / :func:`recurrence_histogram` — the FRET
  efficiencies of bursts that recur within a chosen time window after an
  initial sub-population, compared with the overall histogram.

These operate purely on the per-burst table (arrival time + efficiency); no
photon-level access is needed.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


def pair_statistics(
    burst_times_s: np.ndarray,
    edges: np.ndarray,
    edge_correction: bool = True,
) -> Tuple[np.ndarray, np.ndarray]:
    r"""Counted and expected burst pairs per lag bin, for one measurement.

    The estimator behind :func:`same_molecule_probability`, split out because a
    single measurement rarely carries enough burst pairs to resolve
    ``P_same(tau)``: counts and expectations are *additive*, so several
    measurements are pooled by summing both and dividing once
    (``G = sum(counts) / sum(expected)``) rather than averaging per-file ``G``
    estimates, which double-weights a short file.

    Parameters
    ----------
    burst_times_s : numpy.ndarray
        Burst arrival times in seconds (any order; NaNs ignored).
    edges : numpy.ndarray
        Lag-bin edges in seconds, ascending, length ``n_bins + 1``.
    edge_correction : bool
        Correct the expected pair count for the finite acquisition time
        (``T - tau``); negligible for ``tau << T`` but keeps large lags sane.

    Returns
    -------
    counts : numpy.ndarray
        Ordered pairs ``(i, j > i)`` whose separation falls in each bin.
    expected : numpy.ndarray
        Pairs a Poisson (uncorrelated) burst stream of the same rate and
        duration would put in each bin. Zero where the measurement is too short
        or too empty to expect any.
    """
    n_bins = len(edges) - 1
    counts = np.zeros(n_bins)
    expected = np.zeros(n_bins)

    t = np.sort(np.asarray(burst_times_s, dtype=float))
    t = t[np.isfinite(t)]
    n = t.size
    if n < 2:
        return counts, expected

    total_time = t[-1] - t[0]
    if total_time <= 0:
        return counts, expected
    rate = n / total_time

    for k in range(n_bins):
        a, b = edges[k], edges[k + 1]
        # Ordered pairs (i, j>i) with separation t_j - t_i in [a, b).
        counts[k] = float(
            (np.searchsorted(t, t + b, side="left")
             - np.searchsorted(t, t + a, side="left")).sum()
        )
        d_tau = b - a
        span = total_time - 0.5 * (a + b) if edge_correction else total_time
        expected[k] = rate * rate * d_tau * max(span, 0.0)
    return counts, expected


def same_molecule_probability(
    burst_times_s: np.ndarray,
    tau_min_s: float = 1e-3,
    tau_max_s: float = 1.0,
    n_bins: int = 50,
    edge_correction: bool = True,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    r"""Same-molecule probability ``P_same(tau) = 1 - 1/G(tau)``.

    ``G(tau)`` is the normalised autocorrelation of the burst arrival times: for
    a Poisson (uncorrelated) burst stream ``G = 1`` and ``P_same = 0``; when a
    molecule recurs, short-lag pairs are enriched, ``G > 1`` and ``P_same > 0``.

    Parameters
    ----------
    burst_times_s : numpy.ndarray
        Burst arrival times in **seconds** (any order; NaNs ignored).
    tau_min_s, tau_max_s : float
        Log-spaced lag range in seconds.
    n_bins : int
        Number of logarithmic lag bins.
    edge_correction : bool
        Correct the expected pair count for the finite acquisition time
        (``T - tau``); negligible for ``tau << T`` but keeps large lags sane.

    Returns
    -------
    tau : numpy.ndarray
        Lag-bin centres (geometric mean), seconds.
    p_same : numpy.ndarray
        Same-molecule probability per lag bin (clipped to ``[0, 1]``).
    g : numpy.ndarray
        The underlying autocorrelation ``G(tau)``.
    """
    edges = np.logspace(np.log10(tau_min_s), np.log10(tau_max_s), n_bins + 1)
    tau = np.sqrt(edges[:-1] * edges[1:])
    counts, expected = pair_statistics(burst_times_s, edges, edge_correction)
    g = np.full(n_bins, np.nan)
    if not expected.any():
        return tau, np.zeros(n_bins), g

    with np.errstate(divide="ignore", invalid="ignore"):
        g = np.where(expected > 0, counts / np.where(expected > 0, expected, 1.0), np.nan)
        p_same = 1.0 - 1.0 / g  # empty bins (g == 0) -> -inf -> clipped to 0
    p_same = np.clip(p_same, 0.0, 1.0)
    return tau, p_same, g


def recurrence_efficiencies(
    burst_times_s: np.ndarray,
    efficiency: np.ndarray,
    e_range: Tuple[float, float],
    dt_range_s: Tuple[float, float],
) -> np.ndarray:
    """FRET efficiencies of bursts recurring after an initial sub-population.

    For every *initial* burst whose efficiency lies in ``e_range``, collect the
    efficiencies of all bursts that arrive within ``dt_range_s`` after it (the
    recurrence window).  The distribution of these recurring efficiencies,
    contrasted with the overall one, exposes state inter-conversion.

    Parameters
    ----------
    burst_times_s : numpy.ndarray
        Burst arrival times in seconds.
    efficiency : numpy.ndarray
        Per-burst FRET efficiency / proximity ratio (same order as the times).
    e_range : (float, float)
        Efficiency window selecting the initial sub-population.
    dt_range_s : (float, float)
        Recurrence-time window ``(t1, t2)`` in seconds after an initial burst.

    Returns
    -------
    numpy.ndarray
        Efficiencies of the recurring bursts (one entry per recurrence event).
    """
    t = np.asarray(burst_times_s, dtype=float)
    e = np.asarray(efficiency, dtype=float)
    order = np.argsort(t)
    t, e = t[order], e[order]

    e1, e2 = e_range
    dt1, dt2 = dt_range_s
    init = np.where(np.isfinite(e) & (e >= e1) & (e <= e2))[0]
    lo = np.searchsorted(t, t + dt1, side="left")
    hi = np.searchsorted(t, t + dt2, side="right")

    out: list[float] = []
    for i in init:
        for j in range(lo[i], hi[i]):
            if j != i and np.isfinite(e[j]):
                out.append(e[j])
    return np.asarray(out, dtype=float)


def recurrence_histogram(
    burst_times_s: np.ndarray,
    efficiency: np.ndarray,
    e_range: Tuple[float, float],
    dt_range_s: Tuple[float, float],
    bins: int = 50,
    e_limits: Tuple[float, float] = (-0.1, 1.1),
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Recurrence FRET histogram alongside the overall histogram.

    Returns
    -------
    centers : numpy.ndarray
        Histogram bin centres.
    recurrence : numpy.ndarray
        Normalised histogram (unit area) of the recurring efficiencies.
    overall : numpy.ndarray
        Normalised histogram of every burst efficiency (for comparison).
    """
    rec = recurrence_efficiencies(burst_times_s, efficiency, e_range, dt_range_s)
    e_all = np.asarray(efficiency, dtype=float)
    e_all = e_all[np.isfinite(e_all)]

    edges = np.linspace(e_limits[0], e_limits[1], bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    rec_h, _ = np.histogram(rec, bins=edges, density=True)
    all_h, _ = np.histogram(e_all, bins=edges, density=True)
    return centers, rec_h, all_h
