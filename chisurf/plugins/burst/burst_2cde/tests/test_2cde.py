"""Headless tests for the FRET-2CDE / ALEX-2CDE burst feature.

Validate that the ChiSurf compute path (tttrlib ``TwoCDE`` fast path) reproduces
the pure-NumPy FRETBursts reference, that the result dataclass summarises the
feature, and that the workflow-prepare RPC resolves settings from context.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import tttrlib

from chisurf.plugins.burst.burst_2cde.core import computation as core


def _build(chan_per_burst, gap=1_000_000):
    """In-memory TTTR (macro time +1 per photon) + a burst dataframe."""
    macro, chan, rows = [], [], []
    t = 0
    for ch in chan_per_burst:
        start = len(macro)
        for c in ch:
            t += 1
            macro.append(t)
            chan.append(int(c))
        t += gap
        rows.append(("f0", start, len(macro) - 1))  # inclusive stop
    d = tttrlib.TTTR()
    d.append_events(
        np.asarray(macro, dtype=np.uint64),
        np.zeros(len(macro), dtype=np.uint16),
        np.asarray(chan, dtype=np.int8),
        np.zeros(len(macro), dtype=np.int8),
        False, 0,
    )
    d.header.set_macro_time_resolution(1.0)  # tau in "seconds" == ticks
    df = pd.DataFrame(rows, columns=["First File", "First Photon", "Last Photon"])
    return {"f0": d}, df, np.asarray(macro, np.float64), np.asarray(chan)


@pytest.mark.parametrize("kernel", ["laplace", "gaussian"])
def test_fret_2cde_matches_reference(kernel):
    rng = np.random.default_rng(7)
    bursts = [(rng.random(300) < p).astype(int) for p in rng.uniform(0.1, 0.9, 30)]
    tttrs, df, macro, chan = _build(bursts)
    out = core.compute_2cde(
        df, tttrs, donor_channels=[0], acceptor_channels=[1],
        donor_micro_time_ranges=[], acceptor_micro_time_ranges=[],
        tau=30.0, kernel=kernel, variant="fret",
    )
    got = out[core.COLUMN_FRET_2CDE].to_numpy()
    ref = core._fret_2cde_numpy(
        macro, np.isin(chan, [0]), np.isin(chan, [1]),
        df[["First Photon", "Last Photon"]].to_numpy(), 30.0, kernel,
    )
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-7)


def test_alex_2cde_matches_reference():
    rng = np.random.default_rng(8)
    bursts = []
    for _ in range(30):
        r = rng.random(300)
        bursts.append(np.where(r < 0.45, 0, np.where(r < 0.75, 1, 2)))
    tttrs, df, macro, chan = _build(bursts)
    out = core.compute_2cde(
        df, tttrs, donor_channels=[0, 1], acceptor_channels=[2],
        donor_micro_time_ranges=[], acceptor_micro_time_ranges=[],
        tau=30.0, variant="alex",
    )
    got = out[core.COLUMN_ALEX_2CDE].to_numpy()
    ref = core._alex_2cde_numpy(
        macro, np.isin(chan, [0, 1]), np.isin(chan, [2]),
        df[["First Photon", "Last Photon"]].to_numpy(), 30.0,
    )
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-7)


def test_static_bursts_near_ten():
    """FRET-2CDE ~10 for static bursts (no within-burst dynamics)."""
    rng = np.random.default_rng(9)
    static = [(rng.random(400) < 0.5).astype(int) for _ in range(30)]
    tttrs, df, _, _ = _build(static)
    out = core.compute_2cde(
        df, tttrs, donor_channels=[0], acceptor_channels=[1],
        donor_micro_time_ranges=[], acceptor_micro_time_ranges=[],
        tau=40.0, variant="fret",
    )
    assert abs(np.nanmean(out[core.COLUMN_FRET_2CDE]) - 10.0) < 3.0


def test_result_dataclass_and_plot(tmp_path):
    from chisurf.plugins.burst.burst_analysis.api.workflow import TwoCde

    rng = np.random.default_rng(10)
    bursts = [(rng.random(200) < p).astype(int) for p in rng.uniform(0.2, 0.8, 20)]
    tttrs, df, _, _ = _build(bursts)
    out = core.compute_2cde(
        df, tttrs, donor_channels=[0], acceptor_channels=[1],
        donor_micro_time_ranges=[], acceptor_micro_time_ranges=[],
        tau=30.0, variant="fret",
    )
    res = TwoCde(table=out, variant="fret")
    assert res.column == "FRET-2CDE"
    assert np.isfinite(res.mean_2cde)
    assert 0.0 <= res.dynamic_fraction(threshold=12.0) <= 1.0


def test_read_burst_analysis_skips_json_sidecar_and_isolates_bi4_bur(tmp_path, monkeypatch):
    """Reading a folder that also holds ``bv4/bva_settings.json`` must not crash.

    Regression: 2CDE read the folder with the default ``b*4*`` glob, which also
    matched ``bv4/`` and read BVA's ``bva_settings.json`` inside it — corrupting
    the ``First File`` column so a later ``data_path / ff`` raised
    ``PosixPath / float``. 2CDE now reads only ``bi4_bur``; the reader also skips
    JSON/YAML sidecars and coerces the filename to ``str``.
    """
    import json

    from chisurf.plugins.burst.burst_bva.core import computation as bva_core

    # Stub TTTR loading — we are testing the table read, not real photon files.
    monkeypatch.setattr(bva_core.tttrlib, "TTTR", lambda *a, **k: object())

    (tmp_path / "bi4_bur").mkdir()
    (tmp_path / "bv4").mkdir()
    rows = ["First Photon\tLast Photon\tFirst File"]
    for i in range(4):
        rows.append("0\t0\t")
        rows.append(f"{i}\t{i + 1}\tm000.spc")
    (tmp_path / "bi4_bur" / "m000.bur").write_text("\n".join(rows))
    (tmp_path / "bv4" / "bva_settings.json").write_text(json.dumps({"min_window": 0.01}))

    # 2CDE's path: only the burst tables, never the bv4 sidecars.
    df, tttrs = bva_core.read_burst_analysis(tmp_path, "SPC-130", pattern="bi4_bur")
    assert "First File" in df.columns
    assert list(df["First File"]) == ["m000.spc"] * 4
    assert list(tttrs) == ["m000.spc"]


def test_write_sidecars(tmp_path):
    rng = np.random.default_rng(11)
    bursts = [(rng.random(150) < 0.5).astype(int) for _ in range(5)]
    tttrs, df, _, _ = _build(bursts)
    out = core.compute_2cde(
        df, tttrs, donor_channels=[0], acceptor_channels=[1],
        donor_micro_time_ranges=[], acceptor_micro_time_ranges=[],
        tau=30.0, variant="fret",
    )
    core.write_2cde_analysis(out, str(tmp_path), variant="fret")
    files = list((tmp_path / "2c4").glob("*.2c4"))
    assert len(files) == 1


def test_workflow_prepare_resolves_context(tmp_path):
    from chisurf.plugins.burst.burst_2cde.backend.services import prepare_workflow_handler

    folder = tmp_path / "burstwise"
    folder.mkdir()
    resp = prepare_workflow_handler(
        workflow_context={
            "burst_folder": str(folder),
            "channel_settings": {
                "detectors": {
                    "green": {"chs": [8, 0], "micro_time_ranges": [[0, 100]]},
                    "red": {"chs": [9, 1], "micro_time_ranges": [[100, 200]]},
                },
                "tttr_reading": {"file_type": "SPC-130"},
            },
        }
    )
    assert resp["ok"] is True
    s = resp["result"]["settings"]
    assert s["donor_channels"] == [8, 0]
    assert s["acceptor_channels"] == [9, 1]


def test_services_register_workflow_prepare():
    from chisurf.plugins.burst.burst_2cde.backend.services import (
        METHOD_PREPARE_WORKFLOW,
        register_services,
    )

    calls: dict[str, object] = {}

    class Dispatcher:
        def register(self, name, handler):
            calls[name] = handler

    register_services(Dispatcher())
    assert METHOD_PREPARE_WORKFLOW in calls
