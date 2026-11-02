"""CUSUM/SPRT's "background 0 = estimate": a time-binned median, not tttrlib's photon-binned one."""

import numpy as np

from chisurf.core.fluorescence.burst.tttrlib_search import estimate_background_cps


class _Header:
    macro_time_resolution = 1e-8


class _TTTR:
    header = _Header()

    def __init__(self, seconds):
        self.macro_times = np.round(np.sort(seconds) / 1e-8).astype(np.int64)


def test_the_estimate_is_the_background_between_many_bursts():
    rng = np.random.default_rng(0)
    background = np.cumsum(rng.exponential(1 / 3000.0, 30_000))  # 3 kcps for ~10 s
    starts = rng.uniform(0, background[-1] - 0.002, 600)  # 600 bursts of 1 ms at 200 kcps
    bursts = np.concatenate([s + np.sort(rng.uniform(0, 1e-3, 200)) for s in starts])
    tttr = _TTTR(np.concatenate([background, bursts]))
    estimate = estimate_background_cps(tttr)
    assert abs(estimate - 3000.0) < 0.15 * 3000.0, estimate
    # the photon-binned median tttrlib uses drifts up toward the burst rate
    t = tttr.macro_times * 1e-8
    dt = np.diff(t)
    n = (dt.size // 100) * 100
    photon_binned = np.median(100 / dt[:n].reshape(-1, 100).sum(1))
    assert photon_binned > 1.5 * estimate


def test_a_sparse_stream_widens_the_bin():
    rng = np.random.default_rng(1)
    tttr = _TTTR(np.cumsum(rng.exponential(1 / 200.0, 4000)))  # 200 cps: 1 ms bins are mostly empty
    assert abs(estimate_background_cps(tttr) - 200.0) < 40.0
