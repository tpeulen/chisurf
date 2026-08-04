"""A dwell that ends with its burst did not end — the burst did.

The first and last dwell of every burst are **censored**: the molecule was
already in that state when the burst began, or still in it when the burst ended,
so the measured duration is a lower bound set by the photon selection rather
than the time the state lasted. A state slower than a burst produces *nothing
else*, and histogramming those numbers draws the burst-duration distribution
under the name "dwell time". These pin that they are identified once and left
out of the distribution.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_h2mm.core import h2mm
from chisurf.plugins.burst.burst_h2mm.core.analysis import analyze
from chisurf.plugins.burst.burst_h2mm.core.h2mm import prepare_bursts


def _dataset(n_bursts=40, burst_len=60, seed=5):
    """Two states with a real chance of transitioning inside a burst."""
    gt = h2mm.H2mmModel(
        np.array([0.5, 0.5]),
        np.array([[0.97, 0.03], [0.04, 0.96]]),
        np.array([[0.85, 0.15], [0.20, 0.80]]),
    )
    rng = np.random.default_rng(seed)
    times = [
        np.concatenate([[0], np.cumsum(rng.poisson(4, burst_len - 1) + 1)]).astype(np.int64)
        for _ in range(n_bursts)
    ]
    streams = h2mm.simulate_bursts(gt, times, seed=seed + 1)
    return prepare_bursts(times, streams, n_streams=2)


@pytest.fixture(scope="module")
def analysis():
    return analyze(_dataset(), state_counts=(2,), base_time_s=1e-6,
                   n_restarts=1, max_iter=200)


def test_every_burst_contributes_two_censored_dwells(analysis):
    """The first and last dwell of a burst touch its edge, by construction.

    (One dwell when the whole burst is a single state — it touches both.)
    """
    per_burst = {}
    for d in analysis.dwells:
        per_burst.setdefault(d.burst, []).append(d)
    for burst, dwells in per_burst.items():
        dwells.sort(key=lambda d: d.start)
        assert dwells[0].is_edge, burst
        assert dwells[-1].is_edge, burst
        # ...and nothing in between is, because both its ends are transitions.
        assert not any(d.is_edge for d in dwells[1:-1]), burst


def test_the_dwell_time_distribution_drops_the_censored_ones(analysis):
    """The histogram's input is complete dwells, not every dwell."""
    complete = analysis.dwell_time_arrays()
    everything = analysis.dwell_time_arrays(include_edges=True)

    n_complete = sum(a.size for a in complete.values())
    n_all = sum(a.size for a in everything.values())
    assert n_complete < n_all, "nothing was censored — the fixture has no edges?"
    assert n_all == len(analysis.dwells)
    assert n_all - n_complete == sum(d.is_edge for d in analysis.dwells)

    # The legacy mapping is still every dwell, so a reader of it is unchanged.
    assert sum(a.size for a in analysis.dwell_times.values()) == n_all


def test_a_censored_dwell_reports_the_burst_not_the_state():
    """Why it matters: a state slower than a burst has only censored dwells.

    With no transitions at all, every dwell spans a whole burst — so the
    "dwell times" are burst durations, and the complete-dwell view is correctly
    empty rather than confidently wrong.
    """
    rng = np.random.default_rng(11)
    n_bursts, burst_len = 25, 40
    times = [
        np.concatenate([[0], np.cumsum(rng.poisson(4, burst_len - 1) + 1)]).astype(np.int64)
        for _ in range(n_bursts)
    ]
    # One state only: the Viterbi path cannot transition, so every dwell is an
    # edge dwell spanning its whole burst.
    streams = [rng.integers(0, 2, burst_len).astype(np.int64) for _ in times]
    data = prepare_bursts(times, streams, n_streams=2)
    ana = analyze(data, state_counts=(1,), base_time_s=1e-6, n_restarts=1, max_iter=100)

    assert all(d.is_edge for d in ana.dwells)
    assert len(ana.dwells) == n_bursts
    complete = ana.dwell_time_arrays()
    assert all(a.size == 0 for a in complete.values()), "no dwell was observed to end"

    # The censored durations are the burst durations, which is exactly the
    # number that must not be plotted as a dwell time.
    censored = ana.dwell_time_arrays(include_edges=True)[0]
    burst_durations = np.array([int(t[-1] - t[0]) for t in times])
    assert np.array_equal(np.sort(censored), np.sort(burst_durations))


def test_the_exported_edge_flag_is_the_records_flag(analysis):
    """One definition of "edge": the table reports what the histogram filters on."""
    from chisurf.plugins.burst.burst_h2mm.core import export as X
    from chisurf.plugins.burst.burst_h2mm.core.photons import PhotonMeta

    data = _dataset()
    n = int(data.n_photons)
    burst_id = np.zeros(n, dtype=np.int64)
    offsets = np.asarray(data.burst_offsets)
    for b in range(len(offsets) - 1):
        burst_id[offsets[b]:offsets[b + 1]] = b
    meta = PhotonMeta(
        macro_time=np.arange(n, dtype=np.int64),
        micro_time=np.zeros(n, dtype=np.int64),
        channel=np.asarray(data.streams, dtype=np.int64),
        burst_id=burst_id,
    )
    table = X.build_dwell_table(data, meta, analysis.dwells, analysis.base_time_s)
    assert (table["Is Edge"].to_numpy() ==
            np.array([int(d.is_edge) for d in analysis.dwells])).all()


def test_the_dwell_table_has_a_one_click_route_out_of_the_window(qapp):
    """The dwell grain now has an automated consumer, not a CSV to open by hand.

    ``open_dwells_in_ndx`` builds the *same* table the exporter writes and hands
    it to ndX, so what a user gates on is what a later reader gets.
    """
    import types

    import pandas as pd

    from chisurf.plugins.burst.burst_h2mm.api.models import H2mmSettings
    from chisurf.plugins.burst.burst_h2mm.backend.services import H2mmAnalysisBundle
    from chisurf.plugins.burst.burst_h2mm.core.photons import (
        StreamDef,
        bursts_from_dataframe,
    )
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    rng = np.random.default_rng(4)
    times = [
        np.concatenate([[0], np.cumsum(rng.poisson(4, 49) + 1)]).astype(np.int64)
        for _ in range(30)
    ]
    gt = h2mm.H2mmModel(
        np.array([0.5, 0.5]),
        np.array([[0.97, 0.03], [0.04, 0.96]]),
        np.array([[0.85, 0.15], [0.20, 0.80]]),
    )
    streams = h2mm.simulate_bursts(gt, times, seed=9)
    macro, chan, micro, rows = [], [], [], []
    off = base = 0
    for t, s in zip(times, streams):
        macro.append(t + base)
        chan.append(s.astype(np.int64))
        micro.append(np.zeros_like(s))
        # ``Last Photon`` is inclusive: the reader slices to ``last + 1``, so
        # ``off + len(t)`` hands the burst the *next* burst's first photon.
        rows.append(("f.spc", off, off + len(t) - 1))
        off += len(t)
        base += int(t[-1]) + 1000
    hdr = types.SimpleNamespace(tag=lambda k: {"value": 1e-6}, macro_time_resolution=1e-6)
    tttr = types.SimpleNamespace(
        macro_times=np.concatenate(macro), routing_channels=np.concatenate(chan),
        micro_times=np.concatenate(micro), header=hdr,
    )
    df = pd.DataFrame(rows, columns=["First File", "First Photon", "Last Photon"])
    data = bursts_from_dataframe(
        df, {"f.spc": tttr}, [StreamDef("green", [0]), StreamDef("red", [1])],
        min_photons=5,
    )
    ana = analyze(data, state_counts=(2,), base_time_s=1e-6, n_restarts=1, max_iter=150)

    w = H2mmTool(embedded=True)
    try:
        # No fit loaded: the button says so instead of raising.
        assert w.dwell_table() is None
        assert w.open_dwells_in_ndx() is False

        bundle = H2mmAnalysisBundle(ana, data, H2mmSettings())
        bundle.meta = _meta_for(data)
        w._bundle = bundle
        table = w.dwell_table()
        assert table is not None and len(table) == len(ana.dwells)
        assert "Is Edge" in table.columns
    finally:
        w.close()


def _meta_for(data):
    """Minimal per-photon metadata for the table builder."""
    from chisurf.plugins.burst.burst_h2mm.core.photons import PhotonMeta

    n = int(data.n_photons)
    burst_id = np.zeros(n, dtype=np.int64)
    offsets = np.asarray(data.burst_offsets)
    for b in range(len(offsets) - 1):
        burst_id[offsets[b]:offsets[b + 1]] = b
    return PhotonMeta(
        macro_time=np.arange(n, dtype=np.int64),
        micro_time=np.zeros(n, dtype=np.int64),
        channel=np.asarray(data.streams, dtype=np.int64),
        burst_id=burst_id,
    )
