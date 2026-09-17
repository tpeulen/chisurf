"""Headless tests for Recurrence Analysis of Single Particles (RASP).

Cover the core estimators (same-molecule probability, recurrence histograms)
and the ``Bursts.recurrence`` workflow handle.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from chisurf.core.fluorescence.burst import recurrence as rec


def test_same_molecule_probability_poisson_is_flat():
    """A Poisson burst stream is uncorrelated: P_same ~ 0 (G ~ 1)."""
    rng = np.random.default_rng(0)
    t = np.sort(rng.uniform(0.0, 600.0, size=5000))  # 5000 bursts over 10 min
    tau, p_same, g = rec.same_molecule_probability(t, 1e-3, 1.0, n_bins=40)
    assert np.nanmean(p_same) < 0.15
    assert abs(np.nanmedian(g) - 1.0) < 0.3


def test_same_molecule_probability_detects_recurrence():
    """Clustered re-appearances enrich short lags: P_same > 0 at small tau."""
    rng = np.random.default_rng(1)
    # 400 molecules, each emitting 2-4 bursts within a 50 ms recurrence window,
    # the molecules themselves spread over 10 min (well separated).
    times = []
    for t0 in np.sort(rng.uniform(0.0, 600.0, size=400)):
        k = rng.integers(2, 5)
        times.extend(t0 + rng.uniform(0.0, 0.05, size=k))
    t = np.sort(np.asarray(times))
    tau, p_same, g = rec.same_molecule_probability(t, 1e-3, 1.0, n_bins=40)
    short = tau < 0.05
    long = tau > 0.3
    assert np.nanmean(p_same[short]) > 0.3  # same molecule likely at short lag
    assert np.nanmean(p_same[short]) > np.nanmean(p_same[long])  # decays with lag


def test_recurrence_histogram_recovers_interconverting_state():
    """Initial low-E bursts that recur as high-E show a high-E recurrence peak."""
    rng = np.random.default_rng(2)
    times, eff = [], []
    t = 0.0
    for _ in range(500):
        t += rng.exponential(0.5)  # initial low-E burst
        times.append(t)
        eff.append(rng.normal(0.2, 0.03))
        t += rng.uniform(0.005, 0.03)  # recurs quickly as high-E
        times.append(t)
        eff.append(rng.normal(0.8, 0.03))
    times = np.asarray(times)
    eff = np.asarray(eff)

    centers, rec_h, all_h = rec.recurrence_histogram(
        times,
        eff,
        e_range=(0.0, 0.4),
        dt_range_s=(1e-3, 0.05),
        bins=40,
    )
    # The recurrence histogram (initial low-E) is dominated by the high-E state.
    assert centers[np.argmax(rec_h)] > 0.6
    # The overall histogram is bimodal (both states present).
    assert all_h[centers < 0.4].sum() > 0


def test_recurrence_efficiencies_respects_time_window():
    """No recurring bursts when the recurrence window excludes all pairs."""
    times = np.array([0.0, 0.01, 1.0, 1.01])
    eff = np.array([0.2, 0.8, 0.2, 0.8])
    got = rec.recurrence_efficiencies(times, eff, e_range=(0.0, 0.4), dt_range_s=(0.005, 0.05))
    assert np.allclose(np.sort(got), [0.8, 0.8])  # each low-E burst -> its high-E partner
    none = rec.recurrence_efficiencies(times, eff, e_range=(0.0, 0.4), dt_range_s=(5.0, 10.0))
    assert none.size == 0


def test_bursts_recurrence_workflow_handle():
    """Bursts.recurrence resolves E + arrival time and returns a Recurrence."""
    from chisurf.plugins.burst.burst_analysis.api.workflow import Bursts, Recurrence, Setup

    rng = np.random.default_rng(3)
    n = 400
    t_ms = np.sort(rng.uniform(0.0, 60_000.0, size=n))  # ms
    pr = rng.uniform(0.0, 1.0, size=n)
    table = pd.DataFrame(
        {
            "First File": ["f0"] * n,
            "Mean Macro Time (ms)": t_ms,
            "Proximity Ratio": pr,
        }
    )
    bursts = Bursts(
        names=["f0"],
        dataset_uuids=[],
        table=table,
        setup=Setup.from_channels(green=(0, 8), red=(1, 9)),
    )
    r = bursts.recurrence()
    assert isinstance(r, Recurrence)
    assert r.times_s.shape == (n,)
    np.testing.assert_allclose(r.times_s, t_ms / 1e3)
    tau, p_same = r.same_molecule_probability()
    assert tau.shape == p_same.shape
    assert 0.0 <= r.recurrence_time() or np.isnan(r.recurrence_time())
    centers, rec_h, all_h = r.histogram(e_range=(0.0, 0.4), dt_range_s=(1e-3, 0.1))
    assert centers.size == 50
