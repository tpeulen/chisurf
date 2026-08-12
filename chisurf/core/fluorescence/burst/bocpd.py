"""Bayesian Online Changepoint Detection (BOCPD) for burst detection.

Thin wrapper around tttrlib's C++ BOCPD implementation. The numba-based
Python implementation has been replaced by the native C++ engine in
``tttrlib::burst_search_bocpd`` (see ``BurstSearchBOCPD.h``), which is
~2x faster than the numba version including binning overhead.

The algorithm is Adams & MacKay, *Bayesian Online Changepoint Detection*,
arXiv:0710.3742 (2007).
"""

import numpy as np
import tttrlib
from chisurf.core.fluorescence.burst.utils import create_array_with_ones


def bocpd_filter(
    tttr: tttrlib.TTTR,
    min_ph: int = 20,
    dt: float = 1e-3,
    prior_count: float = 1.0,
    prior_duration: float = 1.0,
    changepoint_prob: float = 0.1,
    max_run: int = 256,
    per_channel: bool = True,
    **deprecated,
) -> np.ndarray:
    """Filter photons using BOCPD burst search via tttrlib's C++ engine.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        TTTR object containing the photon data.
    min_ph : int
        Minimum photons per burst (L).
    dt : float
        Bin width in seconds.
    prior_count : float
        Gamma shape prior (pseudo-count before data).
    prior_duration : float
        Gamma rate prior (prior duration in bins).
    changepoint_prob : float
        Hazard rate — probability of a changepoint in any bin.
    max_run : int
        Maximum run length to track.
    per_channel : bool
        Track one Gamma pair per routing channel.

    Returns
    -------
    np.ndarray
        Boolean mask of selected photons.
    """
    # accept old kwarg names silently
    if 'alpha' in deprecated and deprecated['alpha'] is not None:
        prior_count = deprecated['alpha']
    if 'beta' in deprecated and deprecated['beta'] is not None:
        prior_duration = deprecated['beta']
    if 'hazard' in deprecated and deprecated['hazard'] is not None:
        changepoint_prob = deprecated['hazard']
    if 'L' in deprecated:
        min_ph = deprecated['L']
    if 'min_counts' in deprecated:
        min_ph = deprecated['min_counts']

    start_stop = tttr.burst_search_bocpd(
        L=min_ph,
        dt=dt,
        prior_count=prior_count,
        prior_duration=prior_duration,
        changepoint_prob=changepoint_prob,
        max_run=max_run,
        per_channel=per_channel,
    )
    start_stop = np.asarray(start_stop).reshape((-1, 2))
    # inclusive -> half-open for create_array_with_ones
    start_stop[:, 1] += 1
    n = len(tttr)
    return create_array_with_ones(start_stop, n)


def bocpd_burst_detection(
    donor_timestamps: np.ndarray,
    acceptor_timestamps: np.ndarray,
    dt: float = 1e-3,
    prior_count: float = 1.0,
    prior_duration: float = 1.0,
    changepoint_prob: float = 0.1,
    max_run: int = 256,
    min_counts: int = 20,
    tttr: tttrlib.TTTR = None,
    **deprecated,
) -> tuple:
    """BOCPD burst detection returning burst dicts and diagnostics.

    When *tttr* is provided, delegates to the C++ engine. Otherwise falls
    back to constructing a temporary TTTR from the timestamps.
    """
    if 'alpha' in deprecated and deprecated['alpha'] is not None:
        prior_count = deprecated['alpha']
    if 'beta' in deprecated and deprecated['beta'] is not None:
        prior_duration = deprecated['beta']
    if 'hazard' in deprecated and deprecated['hazard'] is not None:
        changepoint_prob = deprecated['hazard']

    if tttr is None:
        # construct a minimal TTTR from the union of timestamps
        all_ts = np.concatenate([donor_timestamps, acceptor_timestamps])
        idx = np.argsort(all_ts)
        n = len(all_ts)
        macro_times = (all_ts * 1e9).astype(np.uint64)
        micro_times = np.zeros(n, dtype=np.uint16)
        routing = np.zeros(n, dtype=np.int8)
        routing[len(donor_timestamps):] = 1
        routing = routing[idx]
        macro_times = np.sort(macro_times)
        event_types = np.ones(n, dtype=np.int8)
        tttr = tttrlib.TTTR()
        tttr.append_events(macro_times, micro_times, routing, event_types)
        # macro_time_resolution must be set via the reader header normally;
        # for synthetic data we patch it
        try:
            tttr.header.macro_time_resolution = 1e-9
        except AttributeError:
            pass

    start_stop = tttr.burst_search_bocpd(
        L=min_counts,
        dt=dt,
        prior_count=prior_count,
        prior_duration=prior_duration,
        changepoint_prob=changepoint_prob,
        max_run=max_run,
        per_channel=True,
    )
    arr = np.asarray(start_stop).reshape((-1, 2))

    mt_res = tttr.header.macro_time_resolution
    macro_times = np.asarray(tttr.macro_times)

    bursts = []
    for start_idx, stop_idx in arr:
        nd = stop_idx - start_idx + 1
        bursts.append({
            'start_bin': 0,
            'end_bin': 0,
            'start': macro_times[start_idx] * mt_res,
            'end': macro_times[stop_idx] * mt_res,
            'donor': nd,
            'acceptor': 0,
            'FRET': 0.0,
        })

    # bins/counts not needed for the C++ path but returned for API compat
    bins = np.array([])
    D_counts = np.array([])
    A_counts = np.array([])
    return bursts, bins, D_counts, A_counts


def bocpd_burst_detection_multi(
    timestamps_list,
    dt: float = 1e-3,
    prior_count: float = 1.0,
    prior_duration: float = 1.0,
    changepoint_prob: float = 0.1,
    max_run: int = 256,
    min_counts: int = 20,
    tttr: tttrlib.TTTR = None,
    **deprecated,
):
    """Multi-channel BOCPD burst detection.

    When *tttr* is provided, delegates to the C++ engine in one call.
    """
    if 'alpha' in deprecated and deprecated['alpha'] is not None:
        prior_count = deprecated['alpha']
    if 'beta' in deprecated and deprecated['beta'] is not None:
        prior_duration = deprecated['beta']
    if 'hazard' in deprecated and deprecated['hazard'] is not None:
        changepoint_prob = deprecated['hazard']

    if tttr is not None:
        start_stop = tttr.burst_search_bocpd(
            L=min_counts, dt=dt,
            prior_count=prior_count, prior_duration=prior_duration,
            changepoint_prob=changepoint_prob, max_run=max_run,
            per_channel=True,
        )
        arr = np.asarray(start_stop).reshape((-1, 2))
        counts = np.array([])
        bin_edges = np.array([])
        bursts = []
        for s, e in arr:
            bursts.append({
                'start_bin': 0, 'end_bin': 0,
                'counts': [0], 'total_counts': int(e - s + 1),
            })
        return bursts, bin_edges, counts, np.array([]), None

    # fallback: pairwise union (same logic as old Python impl)
    if not timestamps_list:
        return [], np.array([]), np.array([]), np.array([]), None

    n_channels = len(timestamps_list)
    if n_channels == 2:
        bursts, bins, D, A = bocpd_burst_detection(
            timestamps_list[0], timestamps_list[1],
            dt=dt, prior_count=prior_count, prior_duration=prior_duration,
            changepoint_prob=changepoint_prob, max_run=max_run,
            min_counts=min_counts,
        )
        counts = np.stack([D, A], axis=1) if len(D) > 0 else np.array([])
        return bursts, bins, counts, np.array([]), None

    # general case: pool timestamps and run single-channel
    all_ts = np.concatenate(timestamps_list)
    bursts, bins, D, A = bocpd_burst_detection(
        all_ts, np.array([]),
        dt=dt, prior_count=prior_count, prior_duration=prior_duration,
        changepoint_prob=changepoint_prob, max_run=max_run,
        min_counts=min_counts,
    )
    return bursts, bins, np.array([]), np.array([]), None


def convert_bursts_to_start_stop(bursts, tttr: tttrlib.TTTR) -> np.ndarray:
    """Convert burst dicts to (n, 2) start-stop photon indices."""
    if not bursts:
        return np.array([], dtype=np.uint64).reshape(0, 2)
    macro_times = np.asarray(tttr.macro_times)
    time_unit = tttr.header.macro_time_resolution
    starts_time = np.array([b['start'] for b in bursts])
    ends_time = np.array([b['end'] for b in bursts])
    starts_mt = starts_time / time_unit
    ends_mt = ends_time / time_unit
    start_indices = np.searchsorted(macro_times, starts_mt)
    end_indices = np.searchsorted(macro_times, ends_mt, side='right') - 1
    valid = start_indices <= end_indices
    if not np.any(valid):
        return np.array([], dtype=np.uint64).reshape(0, 2)
    return np.stack([start_indices[valid], end_indices[valid]], axis=1).astype(np.uint64)
