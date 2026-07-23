"""Backend/service and photon-extraction tests for the H2MM plugin."""

from __future__ import annotations

import types
from pathlib import Path

import numpy as np
import pandas as pd

from chisurf.plugins.burst.burst_h2mm.core import analysis, h2mm
from chisurf.plugins.burst.burst_h2mm.core.photons import (
    StreamDef,
    bursts_from_dataframe,
)


def _fake_tttr(macro, chan, micro, resolution=1e-6):
    """Build a duck-typed TTTR object for tests (no disk IO)."""
    header = types.SimpleNamespace()
    header.tag = lambda key: {"value": resolution}
    header.macro_time_resolution = resolution
    return types.SimpleNamespace(
        macro_times=np.asarray(macro),
        routing_channels=np.asarray(chan),
        micro_times=np.asarray(micro),
        header=header,
    )


def _synthetic_dataset(n_bursts=250, burst_len=80, seed=7):
    """Simulate a 2-state dataset laid out as one TTTR file + burst table."""
    gt = h2mm.H2mmModel(
        np.array([0.5, 0.5]),
        np.array([[0.99, 0.01], [0.02, 0.98]]),
        np.array([[0.85, 0.15], [0.20, 0.80]]),
    )
    rng = np.random.default_rng(seed)
    times = [
        np.concatenate([[0], np.cumsum(rng.poisson(4, size=burst_len - 1) + 1)]).astype(np.int64)
        for _ in range(n_bursts)
    ]
    streams = h2mm.simulate_bursts(gt, times, seed=seed + 1)

    macro, chan, micro, rows = [], [], [], []
    offset = 0
    base = 0
    for t, s in zip(times, streams):
        macro.append(t + base)
        chan.append(s.astype(np.int64))  # stream 0 -> ch 0, stream 1 -> ch 1
        micro.append(np.zeros_like(s))
        rows.append(("f.spc", offset, offset + t.shape[0]))
        offset += t.shape[0]
        base += int(t[-1]) + 1000
    tttr = _fake_tttr(np.concatenate(macro), np.concatenate(chan), np.concatenate(micro))
    df = pd.DataFrame(rows, columns=["First File", "First Photon", "Last Photon"])
    return df, {"f.spc": tttr}


def test_bursts_from_dataframe_and_analyze():
    df, tttrs = _synthetic_dataset()
    streams = [StreamDef("green", [0], []), StreamDef("red", [1], [])]
    data = bursts_from_dataframe(df, tttrs, streams, min_photons=5)
    assert data.n_bursts == 250
    assert data.n_streams == 2

    ana = analysis.analyze(
        data, state_counts=(1, 2, 3), criterion="bic",
        base_time_s=1e-6, n_restarts=1, max_iter=200,
    )
    assert ana.best.n_states == 2
    order = np.argsort(-ana.best.model.obs[:, 0])
    fret = ana.fret[order]
    assert fret[0] < 0.35 and fret[1] > 0.65
    assert len(ana.transitions) > 0


def test_analyze_populates_dwells_path_and_measured_es():
    """analyze() exposes a Viterbi path and per-dwell measured E aligned to states."""
    df, tttrs = _synthetic_dataset()
    streams = [StreamDef("green", [0], []), StreamDef("red", [1], [])]
    data = bursts_from_dataframe(df, tttrs, streams, min_photons=5)
    ana = analysis.analyze(
        data, state_counts=(1, 2, 3), base_time_s=1e-6, n_restarts=1, max_iter=200,
    )
    # Viterbi path covers every analysed photon.
    assert ana.path.shape[0] == data.n_photons
    assert int(ana.path.max()) < ana.best.n_states
    # No acceptor-excitation stream → stoichiometry is all-NaN.
    assert not np.isfinite(ana.stoichiometry).any()
    # Every dwell is accounted for and the legacy duration mapping matches.
    assert len(ana.dwells) == sum(len(v) for v in ana.dwell_times.values())
    # Measured dwell E tracks the model per-state E: the low-E state's dwells have
    # a lower mean measured E than the high-E state's.
    low = int(np.argmin(ana.fret))
    high = int(np.argmax(ana.fret))
    e_low = np.array([d.e for d in ana.dwells if d.state == low and np.isfinite(d.e)])
    e_high = np.array([d.e for d in ana.dwells if d.state == high and np.isfinite(d.e)])
    assert e_low.mean() < e_high.mean()


def test_analyze_stoichiometry_with_alex_stream():
    """A 3rd acceptor-excitation stream yields finite per-state stoichiometry."""
    gt = h2mm.H2mmModel(
        np.array([0.5, 0.5]),
        np.array([[0.98, 0.02], [0.03, 0.97]]),
        # [DexDem, DexAem, AexAem]; both states S ~ 0.5, E low/high.
        np.array([[0.45, 0.10, 0.45], [0.10, 0.45, 0.45]]),
    )
    rng = np.random.default_rng(3)
    times = [
        np.concatenate([[0], np.cumsum(rng.poisson(4, size=79) + 1)]).astype(np.int64)
        for _ in range(200)
    ]
    sim = h2mm.simulate_bursts(gt, times, seed=4)
    macro, chan, micro, rows = [], [], [], []
    offset = base = 0
    for t, s in zip(times, sim):
        macro.append(t + base)
        chan.append(s.astype(np.int64))
        micro.append(np.zeros_like(s))
        rows.append(("f.spc", offset, offset + t.shape[0]))
        offset += t.shape[0]
        base += int(t[-1]) + 1000
    tttr = _fake_tttr(np.concatenate(macro), np.concatenate(chan), np.concatenate(micro))
    df = pd.DataFrame(rows, columns=["First File", "First Photon", "Last Photon"])
    streams = [StreamDef("green", [0]), StreamDef("red", [1]), StreamDef("yellow", [2])]
    data = bursts_from_dataframe(df, {"f.spc": tttr}, streams, min_photons=8)
    assert data.n_streams == 3
    ana = analysis.analyze(data, state_counts=(1, 2), base_time_s=1e-6, n_restarts=2, max_iter=200)
    assert np.isfinite(ana.stoichiometry).all()
    assert np.allclose(ana.stoichiometry, 0.5, atol=0.15)
    # Measured per-dwell S is populated (finite for multi-photon dwells).
    s_vals = np.array([d.s for d in ana.dwells if np.isfinite(d.s)])
    assert s_vals.size > 0


def test_stream_microtime_gating():
    macro = np.array([0, 1, 2, 3])
    chan = np.array([0, 0, 1, 1])
    micro = np.array([100, 5000, 100, 5000])
    tttr = _fake_tttr(macro, chan, micro)
    df = pd.DataFrame([("f", 0, 4)], columns=["First File", "First Photon", "Last Photon"])
    # Green accepts ch0 with micro<=1000; red accepts ch1 any micro.
    streams = [StreamDef("green", [0], [(0, 1000)]), StreamDef("red", [1], [])]
    from chisurf.plugins.burst.burst_h2mm.core.photons import extract_burst_photons

    times, sidx = extract_burst_photons(df, {"f": tttr}, streams, min_photons=1)
    # Photon 1 (ch0, micro 5000) is dropped by the micro-time gate.
    assert len(times) == 1
    assert list(sidx[0]) == [0, 1, 1]


def test_contract_describe_rpc():
    from chisurf.core.plugin.client import InProcessClient
    from chisurf.plugins.burst.burst_h2mm.backend.services import register_services
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    state = SessionState()
    dispatcher = ServiceDispatcher(state)
    dispatcher._build_default_registry()
    register_services(dispatcher)
    client = InProcessClient(dispatcher)

    res = client.call("burst_h2mm.contract.describe", {})
    assert res.get("ok") is True
    assert res["result"]["plugin_id"] == "burst_h2mm"


def test_load_tttrs_resolves_legacy_burst_folder_parent(tmp_path, monkeypatch):
    """CUSUM/burstwise .bur folders reference TTTR files in the dataset root."""
    import tttrlib

    from chisurf.plugins.burst.burst_h2mm.backend import services

    data_root = tmp_path / "bh_spc132_sm_dna"
    burst_dir = data_root / "cusum_All 0.2000#30" / "bi4_bur"
    burst_dir.mkdir(parents=True)
    tttr_path = data_root / "m000.spc"
    tttr_path.write_bytes(b"dummy")

    loaded: list[tuple[str, str]] = []

    def fake_tttr(path: str, file_type: str):
        loaded.append((path, file_type))
        return types.SimpleNamespace(path=Path(path), file_type=file_type)

    monkeypatch.setattr(tttrlib, "TTTR", fake_tttr)
    df = pd.DataFrame(
        [("0", 0, 0), ("m000.spc", 1, 10)],
        columns=["First File", "First Photon", "Last Photon"],
    )

    tttrs = services._load_tttrs(df, burst_dir, "SPC-130")

    assert tttrs["m000.spc"].path == tttr_path
    assert loaded == [(str(tttr_path), "SPC-130")]
