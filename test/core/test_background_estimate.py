"""CUSUM/SPRT's "background 0 = estimate": the exponential tail of the inter-photon times.

The estimate before (the median of counts in 1 ms bins) took integer values at ~4 counts a bin:
a measurement of 3.6 kcps read "4.00 kcps", and a user who typed the background of one detector
(0.7 kcps) into a search over every channel got no proper bursts at all.
"""

import numpy as np

from chisurf.core.fluorescence.burst.tttrlib_search import estimate_background_cps


class _Header:
    macro_time_resolution = 1e-8


class _TTTR:
    header = _Header()

    def __init__(self, seconds, channels=None):
        order = np.argsort(seconds)
        self.macro_times = np.round(np.asarray(seconds)[order] / 1e-8).astype(np.int64)
        chs = np.zeros(len(seconds), dtype=np.int8) if channels is None else np.asarray(channels)
        self.routing_channels = chs[order]


def _stream(rng, rate, seconds, n_bursts=0, per_burst=200):
    background = np.cumsum(rng.exponential(1 / rate, int(rate * seconds * 1.1)))
    background = background[background < seconds]
    starts = rng.uniform(0, seconds - 0.002, n_bursts)
    bursts = [s + np.sort(rng.uniform(0, 1e-3, per_burst)) for s in starts]
    return np.concatenate([background, *bursts]) if bursts else background


def test_the_background_between_many_bursts():
    rng = np.random.default_rng(0)
    t = _stream(rng, 3000.0, 10.0, n_bursts=600)  # 600 bursts of 1 ms at 200 kcps: 80 % of photons
    estimate = estimate_background_cps(_TTTR(t))
    assert abs(estimate - 3000.0) < 0.03 * 3000.0, estimate


def test_no_integer_steps_at_a_few_counts_per_millisecond():
    """3.6 kcps is 3.6 counts per ms: the binned median said 4.00 kcps."""
    rng = np.random.default_rng(2)
    estimate = estimate_background_cps(_TTTR(_stream(rng, 3600.0, 20.0, n_bursts=200)))
    assert abs(estimate - 3600.0) < 0.03 * 3600.0, estimate


def test_a_sparse_stream():
    rng = np.random.default_rng(1)
    estimate = estimate_background_cps(_TTTR(_stream(rng, 200.0, 20.0)))
    assert abs(estimate - 200.0) < 0.08 * 200.0, estimate


def test_the_channels_add_up_to_the_whole_stream():
    """Per detector and over every channel: what the search sees is the sum."""
    rng = np.random.default_rng(3)
    green = _stream(rng, 1600.0, 20.0, n_bursts=300)
    red = _stream(rng, 700.0, 20.0, n_bursts=300, per_burst=80)
    tttr = _TTTR(np.concatenate([green, red]), np.r_[np.zeros(green.size), np.ones(red.size)].astype(np.int8))
    g = estimate_background_cps(tttr, channels=[0])
    r = estimate_background_cps(tttr, channels=[1])
    total = estimate_background_cps(tttr)
    assert abs(g - 1600.0) < 0.04 * 1600.0 and abs(r - 700.0) < 0.04 * 700.0, (g, r)
    assert abs(total - (g + r)) < 0.04 * total, (total, g, r)
