"""What the emtk H2MM windows draw, derived from a finished fit and from nothing else.

Every function takes the :class:`~chisurf.plugins.burst.burst_h2mm.core.analysis.H2mmAnalysis` that
:func:`~chisurf.plugins.burst.burst_h2mm.core.analysis.analyze` / ``run_analysis`` returned and gives back the
arrays the plots and tables show. With no analysis they return ``None`` (or an empty list): the windows then draw
an empty-state message, never a placeholder curve (PRD-153 rule 8a: no invented data).

The module is Qt-free and emtk-free so the parity tests can compare its output with the backend directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

#: Bins of a per-state dwell-time histogram (the Qt tool's ``_plot_dwell_times`` uses 30 as well).
DWELL_BINS = 30


@dataclass(frozen=True)
class DwellHistogram:
    """The histogram of one state's complete dwells, in milliseconds."""

    state: int
    centers_ms: np.ndarray
    counts: np.ndarray
    n_dwells: int


def n_states(ana: Any) -> int | None:
    """Number of states of the selected model (``None`` without a fit)."""
    if ana is None:
        return None
    return int(ana.best.n_states)


def rate_matrix(ana: Any) -> np.ndarray | None:
    """Transition rates in 1/s, row = from state, column = to state; ``None`` without a fit or a matrix."""
    if ana is None:
        return None
    rates = np.asarray(getattr(ana, "trans_rates", np.empty((0, 0))), dtype=np.float64)
    if rates.ndim != 2 or rates.shape[0] == 0:
        return None
    return rates


def transition_points(ana: Any) -> tuple[np.ndarray, np.ndarray] | None:
    """FRET efficiency before and after every decoded within-burst transition (finite pairs only)."""
    if ana is None or not ana.transitions:
        return None
    before = np.array([t.e_from for t in ana.transitions], dtype=np.float64)
    after = np.array([t.e_to for t in ana.transitions], dtype=np.float64)
    good = np.isfinite(before) & np.isfinite(after)
    if not good.any():
        return None
    return before[good], after[good]


def transitions_in_gate(
    points: tuple[np.ndarray, np.ndarray] | None, x_range: tuple[float, float], y_range: tuple[float, float]
) -> tuple[int, int]:
    """How many of the *points* fall in the gate, and how many there are."""
    if points is None:
        return 0, 0
    x, y = points
    inside = (x >= x_range[0]) & (x <= x_range[1]) & (y >= y_range[0]) & (y <= y_range[1])
    return int(inside.sum()), int(x.size)


def dwell_histograms(ana: Any, bins: int = DWELL_BINS) -> tuple[list[DwellHistogram], list[int]]:
    """Per-state histograms of the dwells that ended inside their burst, and the states that have none.

    Dwells touching a burst edge are censored (the burst ended them, not the state) and are left out, exactly as in
    the Qt tool; a state with no complete dwell is returned in the second list so the window can name it.
    """
    if ana is None:
        return [], []
    base_ms = float(ana.base_time_s) * 1e3
    out: list[DwellHistogram] = []
    censored: list[int] = []
    for state, arr in sorted(ana.dwell_time_arrays().items()):
        if arr.size == 0:
            censored.append(int(state))
            continue
        counts, edges = np.histogram(arr * base_ms, bins=bins)
        out.append(DwellHistogram(int(state), (edges[:-1] + edges[1:]) / 2.0, counts.astype(np.float64), int(arr.size)))
    return out, censored
