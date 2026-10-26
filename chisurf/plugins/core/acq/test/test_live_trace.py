"""The running smFRET trace: a ring buffer of the last T seconds in bins of width dt -- donor up,
acceptor (FRET and directly excited) down -- equal to a direct histogram of those photons."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.core.acq.live.setups import default_setup
from chisurf.plugins.core.acq.live.sources import Population, SimulatedPieSource
from chisurf.plugins.core.acq.live.trace import LiveTrace, trace_streams

CLOCK = None


def _pie_photons(seconds: float = 3.0):
    src = SimulatedPieSource(
        (Population(0.2), Population(0.8)), duration_s=seconds, seed=3, realtime=False
    )
    src.start()
    parts = []
    while True:
        b = src.read(timeout=2.0)
        if b is None:
            if src.finished:
                break
            continue
        parts.append(b)
    return src.info, parts


def test_the_trace_is_the_last_window_binned_and_mirrored():
    info, batches = _pie_photons()
    setup = default_setup("pie", info.n_micro)
    streams = trace_streams(setup, "pie")
    assert [s.sign for s in streams] == [1, -1, -1]
    window_s, bin_s = 1.0, 1e-3
    trace = LiveTrace(streams, macro_clock_s=info.macro_clock_s, window_s=window_s, bin_s=bin_s)
    for b in batches:  # fed in the source's own batches, as the session does
        trace.push(b.macro, b.micro, b.channel)
    snap = trace.snapshot()
    assert snap["window_s"] == pytest.approx(window_s) and snap["bin_s"] == pytest.approx(bin_s)
    assert len(snap["t"]) == 1000 and snap["t"][-1] == 0.0
    assert snap["t"][-1] - snap["t"][0] == pytest.approx(window_s - bin_s)
    by_name = {s["name"]: np.asarray(s["counts"]) for s in snap["streams"]}
    dd, da, aa = (by_name[s.name] for s in streams)
    assert (dd >= 0).all() and (da <= 0).all() and (aa <= 0).all()
    assert dd.sum() > 0 and da.sum() < 0 and aa.sum() < 0
    # the same bins, histogrammed directly from the last window of photons
    macro = np.concatenate([b.macro for b in batches]).astype(np.int64)
    micro = np.concatenate([b.micro for b in batches]).astype(np.int64)
    ch = np.concatenate([b.channel for b in batches]).astype(np.int64)
    t = (macro - macro[0]) * info.macro_clock_s
    b_abs = np.floor(t / bin_s).astype(np.int64)
    head = int(b_abs[-1])
    for stream, got in zip(streams, (dd, da, aa)):
        sel = (
            np.isin(ch, stream.channels)
            & (micro >= stream.window[0])
            & (micro < stream.window[1])
            & (b_abs > head - 1000)
        )
        expected = np.bincount(b_abs[sel] - (head - 999), minlength=1000)[:1000]
        assert np.array_equal(stream.sign * got, expected), stream.name


def test_two_colour_and_single_colour_traces():
    two = trace_streams({"detectors": {"green": {"chs": [0]}, "red": {"chs": [1]}}}, "two_color")
    assert [(s.sign, s.channels) for s in two] == [(1, (0,)), (-1, (1,))]
    one = trace_streams({"detectors": {"green": {"chs": [0]}}}, "single_color")
    assert len(one) == 1 and one[0].sign == 1


def test_a_reconfigured_trace_starts_over_and_bins_are_cheap():
    streams = trace_streams(
        {"detectors": {"green": {"chs": [0]}, "red": {"chs": [1]}}}, "two_color"
    )
    trace = LiveTrace(streams, macro_clock_s=1e-8, window_s=1.0, bin_s=1e-3)
    macro = np.arange(0, 3e8, 1000, dtype=np.int64)  # 3 s, one photon per 10 us
    ch = (np.arange(macro.size) % 2).astype(np.int64)
    trace.push(macro, np.zeros(macro.size, np.int64), ch)
    assert trace.counts.shape == (2, 1000)  # a window of bins, never the run's photons
    assert int(trace.counts.sum()) == 100_000  # the last second only
    trace.configure(0.5, 5e-3)
    assert trace.counts.shape == (2, 100) and int(trace.counts.sum()) == 0
