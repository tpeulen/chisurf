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


class _FullTTTR(_TTTR):
    """With micro times and indexing, as the detector search needs."""

    def __init__(self, seconds, channels):
        super().__init__(seconds, channels)
        self.micro_times = np.zeros(self.macro_times.size, dtype=np.uint16)

    def __len__(self):
        return int(self.macro_times.size)

    @property
    def routing_channel(self):  # tttrlib's other spelling, which the Background tool reads
        return self.routing_channels

    def __getitem__(self, index):
        sub = object.__new__(_FullTTTR)
        sub.macro_times = self.macro_times[index]
        sub.routing_channels = self.routing_channels[index]
        sub.micro_times = self.micro_times[index]
        return sub

    def burst_search_by_name(self, algorithm, **parameters):
        self.searched_with = dict(parameters)
        _FullTTTR.last = self
        # two "bursts": the first and the last ten photons of what it was given
        n = len(self)
        return np.array([0, 9, n - 10, n - 1], dtype=np.int64)


def _three_channels(rng):
    green = _stream(rng, 1600.0, 20.0, n_bursts=300)
    red = _stream(rng, 700.0, 20.0, n_bursts=300, per_burst=80)
    other = _stream(rng, 3000.0, 20.0)  # a channel no detector reads
    t = np.concatenate([green, red, other])
    chs = np.r_[np.zeros(green.size), np.ones(red.size), np.full(other.size, 5)].astype(np.int8)
    return _FullTTTR(t, chs)


def test_the_background_tool_estimate_per_detector():
    from chisurf.core.fluorescence.burst.tttrlib_search import detector_backgrounds_cps

    tttr = _three_channels(np.random.default_rng(4))
    found = detector_backgrounds_cps(tttr, {"green": {"chs": [0]}, "red": {"chs": [1]}})
    assert abs(found["green"] - 1600.0) < 0.06 * 1600.0, found
    assert abs(found["red"] - 700.0) < 0.06 * 700.0, found


def test_cusum_reads_the_selecting_detectors_and_their_background(monkeypatch):
    """The CUSUM tests against the background of the photons it reads -- the detectors the
    bursts are selected on -- and its bursts are indices of the whole stream."""
    from chisurf.core.fluorescence.burst import tttrlib_search as ts

    monkeypatch.setattr(ts, "describe", lambda name: {})
    tttr = _three_channels(np.random.default_rng(5))
    detectors = {"green": {"chs": [0]}, "red": {"chs": [1]}}
    found = np.asarray(ts.search(tttr, "cusum_sprt", {"background_cps": 0.0, ts.SEARCH_DETECTORS: detectors}))
    searched = _FullTTTR.last
    assert set(np.unique(searched.routing_channels).tolist()) == {0, 1}  # channel 5 is not read
    assert ts.SEARCH_DETECTORS not in searched.searched_with
    assert abs(searched.searched_with["background_cps"] - 2300.0) < 0.06 * 2300.0
    assert set(tttr.routing_channels[found].tolist()) <= {0, 1}  # full-stream indices of detector photons
    assert found.max() < len(tttr)
