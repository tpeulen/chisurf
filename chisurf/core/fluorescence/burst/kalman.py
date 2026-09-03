"""Kalman-filtered count-rate burst search.

The stream is binned, its count rate is tracked by a Kalman filter whose
measurement noise comes from Poisson statistics, and a burst is a run of bins
whose innovation is large compared with the filter's own uncertainty
(a Mahalanobis distance). Because it responds to a *change* in rate rather than
to an absolute level, a slow drift in background is tracked and ignored rather
than detected.

:func:`kalman_filter` and :func:`kalman_burst_search` are the entry points, and
they run ``tttrlib``'s ``burst_search_kalman`` -- the same shape as
:mod:`~chisurf.core.fluorescence.burst.bocpd` and
:mod:`~chisurf.core.fluorescence.burst.cusum`.

The in-tree Python recursion (``KalmanBurstDetector``, ``kalman_burst_detection``
and the binning helpers) was kept as a fallback for a build whose ``tttrlib``
predates ``burst_search_kalman``.  The tree pins its engines, so that fallback
was dead code; it was deleted in the fallback audit.  The parity test
that exercised the fallback path (``test_kalman_engine_parity.py``) was updated
to cover only the engine path.
"""

from __future__ import annotations

import numpy as np
import tttrlib

from chisurf.core.fluorescence.burst.utils import create_array_with_ones

__all__ = [
    "kalman_filter",
    "kalman_burst_search",
]


def kalman_burst_search(
    tttr: tttrlib.TTTR,
    min_ph: int = 20,
    dt: float = 1e-3,
    q: float = 20.0,
    r_scale: float = 1.0,
    z_thresh: float = 3.0,
    min_len: int = 2,
    merge_gap: int = 20,
    per_channel: bool = True,
) -> np.ndarray:
    """Run the Kalman burst search and return inclusive photon index ranges.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        TTTR object containing the photon data.
    min_ph : int
        Minimum photons per burst (``L``), applied last.
    dt : float
        Bin width in seconds. Sets the time resolution of the method.
    q : float
        Process-noise variance in ``(counts/s)^2``; how fast the filter believes
        the underlying rate itself changes. Not dimensionless -- it has to be
        commensurate with the count rates in the data.
    r_scale : float
        Scale on the Poisson measurement variance ``rate / dt``.
    z_thresh : float
        Mahalanobis distance above which a bin counts as part of a burst.
    min_len : int
        Minimum number of consecutive bins over threshold.
    merge_gap : int
        Merge bursts separated by at most this many bins.
    per_channel : bool
        Track one state dimension per used routing channel rather than pooling
        every photon into a single rate.

    Returns
    -------
    np.ndarray
        ``(n_bursts, 2)`` array of **inclusive** ``[start, stop]`` photon
        indices, the layout every ``TTTR.burst_search*`` returns.
    """
    start_stop = tttr.burst_search_kalman(
        L=int(min_ph),
        dt=float(dt),
        q=float(q),
        r_scale=float(r_scale),
        z_thresh=float(z_thresh),
        min_len=int(min_len),
        merge_gap=int(merge_gap),
        per_channel=bool(per_channel),
    )
    return np.asarray(start_stop, dtype=np.int64).reshape((-1, 2))


def kalman_filter(
    tttr: tttrlib.TTTR,
    min_ph: int = 20,
    dt: float = 1e-3,
    q: float = 20.0,
    r_scale: float = 1.0,
    z_thresh: float = 3.0,
    min_len: int = 2,
    merge_gap: int = 20,
    per_channel: bool = True,
) -> np.ndarray:
    """Filter photons by Kalman burst search, returning a per-photon mask.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        TTTR object containing the photon data.
    min_ph, dt, q, r_scale, z_thresh, min_len, merge_gap, per_channel
        See :func:`kalman_burst_search`.

    Returns
    -------
    np.ndarray
        Boolean mask of selected photons, of length ``len(tttr)``.
    """
    n = len(tttr)
    start_stop = kalman_burst_search(
        tttr, min_ph=min_ph, dt=dt, q=q, r_scale=r_scale, z_thresh=z_thresh,
        min_len=min_len, merge_gap=merge_gap, per_channel=per_channel,
    )
    if len(start_stop) == 0:
        return np.zeros(n, dtype=bool)
    # The engine reports inclusive stops; create_array_with_ones wants half-open.
    half_open = np.asarray(start_stop, dtype=np.int64).copy()
    half_open[:, 1] += 1
    return np.asarray(create_array_with_ones(half_open, n), dtype=bool)
