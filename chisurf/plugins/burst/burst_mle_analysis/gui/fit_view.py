"""What the emtk burst-MLE windows show of the per-burst lifetimes, read from the rows the batch computed.

The engine owns the fit. This module turns the rows of the last batch run (``MleViewModel.burst_results``) into the
lifetime series and their common-grid histograms. With no batch run each function returns an empty result and the
windows draw an empty-state message: nothing is ever invented.

Qt-free and engine-free: plain rows in, arrays out, so the tests can feed literal rows.
"""

from __future__ import annotations

import re

import numpy as np

#: Bins of the lifetime histogram.
LIFETIME_BINS = 30

_TAU_COLUMN = re.compile(r"^Tau(?: S(?P<state>\d+))? \((?P<colour>.+)\)$")


def burst_lifetimes(rows: list[dict] | None) -> dict[str, np.ndarray]:
    """Per-burst lifetimes by series from the rows of the last batch run.

    The key is the detection colour (``"green"``) or, in the segment-level analysis, ``"S0 green"``. Only finite
    values are kept; a column nobody filled is left out.
    """
    series: dict[str, list[float]] = {}
    for row in rows or []:
        for column, value in row.items():
            match = _TAU_COLUMN.match(str(column))
            if match is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(number):
                continue
            key = (
                match["colour"]
                if match["state"] is None
                else f"S{match['state']} {match['colour']}"
            )
            series.setdefault(key, []).append(number)
    # Sorted by series: the batch rows arrive in worker order; the plot must not depend on it.
    return {
        key: np.asarray(values, dtype=np.float64)
        for key, values in sorted(series.items())
        if values
    }


def lifetime_histograms(
    lifetimes: dict[str, np.ndarray], bins: int = LIFETIME_BINS
) -> list[tuple[str, np.ndarray, np.ndarray, float]]:
    """``(label, bin centres, counts, bar width)`` per series, on one common bin grid."""
    if not lifetimes:
        return []
    everything = np.concatenate(list(lifetimes.values()))
    lo, hi = float(everything.min()), float(everything.max())
    if hi <= lo:
        hi = lo + 1.0
    edges = np.linspace(lo, hi, bins + 1)
    centres = (edges[:-1] + edges[1:]) / 2.0
    width = float(edges[1] - edges[0])
    return [
        (key, centres, np.histogram(values, bins=edges)[0].astype(np.float64), width)
        for key, values in lifetimes.items()
    ]
