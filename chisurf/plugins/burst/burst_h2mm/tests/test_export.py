"""Tests for the ndX-openable H2MM result tables + the full extraction path."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from chisurf.plugins.burst.burst_h2mm.core import export as X
from chisurf.plugins.burst.burst_h2mm.core import h2mm
from chisurf.plugins.burst.burst_h2mm.core.photons import (
    PhotonMeta,
    StreamDef,
    bursts_from_dataframe,
)

tttrlib = pytest.importorskip("tttrlib")


def _two_state_gt():
    return h2mm.H2mmModel(
        np.array([0.5, 0.5]),
        np.array([[0.99, 0.01], [0.02, 0.98]]),
        np.array([[0.85, 0.15], [0.20, 0.80]]),
    )


def _dataset_via_tttrlib(n_bursts=60, burst_len=50, seed=3):
    """Simulate → real tttrlib.TTTR → plugin extraction with per-photon meta."""
    gt = _two_state_gt()
    rng = np.random.default_rng(seed)
    times_local = [
        np.concatenate([[0], np.cumsum(rng.poisson(4, burst_len - 1) + 1)]).astype(np.int64)
        for _ in range(n_bursts)
    ]
    streams_local = h2mm.simulate_bursts(gt, times_local, seed=seed + 7)

    macro, chan, rows = [], [], []
    off, base = 0, 0
    for t, s in zip(times_local, streams_local):
        macro.append((t + base).astype(np.uint64))
        chan.append(s.astype(np.int8))
        rows.append(("sim.spc", off, off + len(t)))
        off += len(t)
        base += int(t[-1]) + 100000

    macro = np.concatenate(macro).astype(np.uint64)
    chan = np.concatenate(chan).astype(np.int8)
    micro = (np.arange(macro.size) % 4096).astype(np.uint16)
    et = np.zeros(macro.size, dtype=np.int8)
    tttr = tttrlib.TTTR()
    tttr.append_events(macro, micro, chan, et, False, 0)

    df = pd.DataFrame(rows, columns=["First File", "First Photon", "Last Photon"])
    defs = [StreamDef("green", [0]), StreamDef("red", [1])]
    return bursts_from_dataframe(df, {"sim.spc": tttr}, defs, min_photons=1, return_meta=True)


def test_meta_aligns_with_streams():
    data, meta = _dataset_via_tttrlib()
    assert isinstance(meta, PhotonMeta)
    n = data.n_photons
    assert meta.macro_time.shape == (n,)
    assert meta.micro_time.shape == (n,)
    assert meta.channel.shape == (n,)
    assert meta.burst_id.shape == (n,)
    # Per-photon channel must be consistent with the stream index it was mapped to
    # (stream 0 = channel 0, stream 1 = channel 1 in this synthetic dataset).
    assert np.array_equal(meta.channel, data.streams.astype(np.int64))
    # burst_id is non-decreasing and covers every burst.
    assert meta.burst_id[0] == 0
    assert meta.burst_id[-1] == data.n_bursts - 1
    assert np.all(np.diff(meta.burst_id) >= 0)


def test_build_tables_schema_and_lengths():
    data, meta = _dataset_via_tttrlib()
    fit = h2mm.fit_states(data, 2, n_restarts=1, max_iter=200, seed=0)
    path, _ = h2mm.viterbi(fit, data)
    fret = np.array([0.15, 0.80])

    tables = X.build_tables(
        data, meta, path, fret, base_time_s=1e-6, micro_time_ns=0.032,
        stream_groups=[("green", (0,)), ("red", (1,))],
    )
    ph, bu = tables.photons, tables.bursts

    assert len(ph) == data.n_photons
    assert len(bu) == data.n_bursts
    for col in ("Mean Macro Time (s)", "Micro Time", "Channel", "Stream", "State", "Burst"):
        assert col in ph.columns
    # ndX FRET-line plot columns (its default Y axis + the per-colour mean micro time).
    for col in ("Mean Microtime (green)", "Mean Microtime (red)",
                "Proximity ratio", "FRET efficiency"):
        assert col in bu.columns
    # Measured proximity ratio is a finite fraction; mean micro time is finite (ns).
    pr = bu["Proximity ratio"].to_numpy()
    assert np.all((pr[np.isfinite(pr)] >= 0) & (pr[np.isfinite(pr)] <= 1))
    assert np.isfinite(bu["Mean Microtime (green)"].to_numpy()).any()
    # Every column ndX imports must be numeric (else it drops them).
    assert all(np.issubdtype(dt, np.number) for dt in ph.dtypes)
    assert all(np.issubdtype(dt, np.number) for dt in bu.dtypes)
    assert set(np.unique(ph["State"])) <= {0, 1}


def test_ndx_hdf5_and_csv_roundtrip(tmp_path):
    data, meta = _dataset_via_tttrlib()
    fit = h2mm.fit_states(data, 2, n_restarts=1, max_iter=200, seed=0)
    path, _ = h2mm.viterbi(fit, data)
    tables = X.build_tables(data, meta, path, np.array([0.15, 0.80]), base_time_s=1e-6)

    pytest.importorskip("tables")  # pandas HDF5 backend
    h5 = X.write_hdf5(tables.photons, tmp_path / "h2mm_photons.h5")
    # ndX opens MFD-HDF5 by reading key "results" first — must round-trip there.
    back = pd.read_hdf(h5, key=X.NDX_HDF5_KEY)
    assert list(back.columns) == list(tables.photons.columns)
    assert len(back) == data.n_photons

    csv = X.write_csv(tables.bursts, tmp_path / "h2mm_bursts.csv")
    back_csv = pd.read_csv(csv)
    assert "Number of Photons" in back_csv.columns
    assert len(back_csv) == data.n_bursts


def test_build_dwell_table_per_dwell_rows_and_edge_flag():
    """The per-dwell table has one row per dwell with an edge flag ndX can filter on."""
    from chisurf.plugins.burst.burst_h2mm.core.analysis import analyze

    data, meta = _dataset_via_tttrlib()
    ana = analyze(data, state_counts=(2,), base_time_s=1e-6, n_restarts=1, max_iter=200)
    dwells = X.build_dwell_table(
        data, meta, ana.dwells, ana.base_time_s,
        stream_groups=[("green", (0,)), ("red", (1,))], micro_time_ns=0.032,
    )
    # One row per analysis dwell.
    assert len(dwells) == len(ana.dwells)
    for col in ("Dwell", "Burst", "State", "Number of Photons", "Dwell Time (ms)",
                "Mean Microtime (green)", "FRET efficiency", "Is Edge"):
        assert col in dwells.columns
    # Edge flag is 0/1 and every burst has at least one edge dwell (its first/last).
    assert set(np.unique(dwells["Is Edge"])) <= {0, 1}
    assert dwells["Is Edge"].sum() >= data.n_bursts
    # States are valid and photon counts positive.
    assert set(np.unique(dwells["State"])) <= {0, 1}
    assert (dwells["Number of Photons"].to_numpy() > 0).all()


def test_write_result_tables_emits_ndx_fret_line_columns(tmp_path):
    """The services table writer wires role groups + micro resolution into ndX columns."""
    from chisurf.plugins.burst.burst_h2mm.api.models import H2mmSettings
    from chisurf.plugins.burst.burst_h2mm.backend.services import (
        H2mmAnalysisBundle,
        _result_from_analysis,
        write_result_tables,
    )
    from chisurf.plugins.burst.burst_h2mm.core.analysis import analyze

    data, meta = _dataset_via_tttrlib()
    ana = analyze(data, state_counts=(2,), base_time_s=1e-6, n_restarts=1, max_iter=150)
    settings = H2mmSettings()
    result = _result_from_analysis(ana, settings)
    bundle = H2mmAnalysisBundle(ana, data, settings)
    bundle.meta = meta
    bundle.micro_time_ns = 0.032  # ns/channel

    write_result_tables(result, bundle, tmp_path)
    csv = result.output_paths.get("bursts_csv")
    assert csv is not None
    df = pd.read_csv(csv)
    for col in ("Mean Microtime (green)", "Proximity ratio", "FRET efficiency",
                "Mean Macro Time (s)", "Dominant State"):
        assert col in df.columns
    assert np.isfinite(df["Mean Microtime (green)"].to_numpy()).any()

    # A per-dwell table is also written for dwell-level filtering in ndX.
    dwells_csv = result.output_paths.get("dwells_csv")
    assert dwells_csv is not None
    ddf = pd.read_csv(dwells_csv)
    for col in ("State", "Number of Photons", "Dwell Time (ms)", "Is Edge",
                "Mean Microtime (green)"):
        assert col in ddf.columns
