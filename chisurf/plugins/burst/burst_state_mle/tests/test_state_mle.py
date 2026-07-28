"""A burst with dynamics has one lifetime per state, not one per burst.

These drive the post-H2MM step end to end on synthetic photons whose per-state
lifetimes are known, and pin the folder contract the results are written in.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from chisurf.plugins.burst.burst_state_mle.core import state_mle as sm

pytest.importorskip("tttrlib")

N_BINS = 128
BINNING = 32
PERIOD = 13.5
DT = PERIOD / N_BINS
GREEN = [0, 1]          # vv = [0], vh = [1]


def _irf(n=N_BINS, centre=8, width=1.5):
    x = np.arange(n)
    g = np.exp(-0.5 * ((x - centre) / width) ** 2)
    g /= g.sum()
    return np.concatenate([g, g])


def _emit(tau_ns, n, rng, *, offset=8):
    """Micro-time *raw* channels for ``n`` photons of lifetime ``tau_ns``."""
    t = rng.exponential(tau_ns / DT, n) + offset
    return np.clip(t, 0, N_BINS - 1).astype(int) * BINNING


def _photons(rng, *, n_bursts=40, tau_by_state=(3.6, 1.0), per_state=260):
    """Two states per burst, each with its own lifetime, on both polarisations."""
    import pandas as pd

    rows = []
    for b in range(n_bursts):
        for s, tau in enumerate(tau_by_state):
            raw = _emit(tau, per_state, rng)
            chan = rng.integers(0, 2, raw.size)  # split over vv (0) and vh (1)
            rows.append(pd.DataFrame({
                "Burst": b, "State": s, "Channel": chan, "Micro Time": raw,
            }))
    return pd.concat(rows, ignore_index=True)


def _detector(name="green", channels=GREEN, min_photons=10):
    return sm.DetectorFit(
        name=name, channels=list(channels), n_bins=N_BINS, binning=BINNING,
        sb=0, eb=N_BINS, dt=DT, period=PERIOD,
        irf=_irf(), background=np.zeros(2 * N_BINS),
        x0=[2.0, 0.0, 0.38, 1.22], fixed=[0, 1, 1, 1], min_photons=min_photons,
    )


def test_each_state_recovers_its_own_lifetime():
    """The point of the step: one lifetime per state, not one per burst."""
    rng = np.random.default_rng(0)
    photons = _photons(rng)
    out = sm.fit_state_wise(photons, [_detector()])

    fitted = out[out["Fitted"] == 1]
    tau0 = fitted[fitted["State"] == 0]["Tau"].median()
    tau1 = fitted[fitted["State"] == 1]["Tau"].median()
    assert tau0 > tau1, "the long-lifetime state must fit longer than the short one"
    assert 2.5 < tau0 < 5.0, tau0
    assert 0.5 < tau1 < 1.8, tau1

    # …and a burst-wise fit of the same photons lands between the two, which is
    # the number this step exists to stop being reported.
    mixed = photons.assign(State=0)
    both = sm.fit_state_wise(mixed, [_detector()])
    tau_mixed = both[both["Fitted"] == 1]["Tau"].median()
    assert tau1 < tau_mixed < tau0, (
        "a mixed burst fit is neither state's lifetime — that is the defect"
    )


def test_every_burst_and_state_is_reported_even_when_not_fitted():
    """Too few photons must read as 'not fitted', never as a missing row."""
    rng = np.random.default_rng(1)
    photons = _photons(rng, n_bursts=4, per_state=3)
    out = sm.fit_state_wise(photons, [_detector(min_photons=50)])
    assert len(out) == 4 * 2, "one row per (burst, state) regardless of photon count"
    assert (out["Fitted"] == 0).all()
    assert out["Tau"].isna().all()
    assert (out["Ng-p-all"] + out["Ng-s-all"] > 0).all(), "counts are still reported"


def test_the_polarisations_are_split_by_the_alternating_channel_rule():
    det = _detector(channels=[8, 0, 3, 1])
    assert det.vv_channels == [8, 3]
    assert det.vh_channels == [0, 1]
    assert det.letter == "g"


def test_results_are_written_as_one_b4_folder_per_state(tmp_path):
    """Per-state folders reuse the .b?4 format so existing readers just work."""
    rng = np.random.default_rng(2)
    photons = _photons(rng, n_bursts=6)
    det = _detector()
    out = sm.fit_state_wise(photons, [det])
    written = sm.write_state_results(out, tmp_path, [det], file_stem="m000")

    for state in (0, 1):
        f = tmp_path / f"bg4_s{state}" / "m000.bg4"
        assert f in written and f.is_file()
        header = f.read_text().splitlines()[0]
        assert header.startswith("Ng-p-all\tNg-s-all\t")
        assert "Tau (green)" in header
        body = np.loadtxt(f, skiprows=1, delimiter="\t")
        # zero-interleaved: 2N+1 rows for N bursts, data on the odd rows
        assert body.shape[0] == 6 * 2 + 1
        assert np.allclose(body[0::2], 0.0), "the interleaved zero rows must stay zero"

    # The row grid is the burst grid in every state folder, so states join row-wise.
    a = np.loadtxt(tmp_path / "bg4_s0" / "m000.bg4", skiprows=1, delimiter="\t")[1::2]
    b = np.loadtxt(tmp_path / "bg4_s1" / "m000.bg4", skiprows=1, delimiter="\t")[1::2]
    assert a.shape == b.shape == (6, 12)

    tidy = tmp_path / "Info" / "state_mle.csv"
    assert tidy in written and tidy.is_file()


def test_a_folder_without_an_h2mm_run_says_so(tmp_path):
    with pytest.raises(FileNotFoundError, match="run H2MM first"):
        sm.read_photon_table(tmp_path)

    with pytest.raises(FileNotFoundError, match="burst-wise MLE"):
        sm.detectors_from_analysis(tmp_path)


def test_the_experiment_record_carries_the_irf_not_the_channel_settings(tmp_path):
    """IRF/background are sample-dependent, so they are not a channel setting."""
    (tmp_path / "bg4").mkdir()
    (tmp_path / "bg4" / "channel_settings.json").write_text(json.dumps({
        "green": {"micro_time_binning": BINNING, "micro_time_start": 0,
                  "micro_time_stop": N_BINS * BINNING, "dt": DT,
                  "excitation_period": PERIOD, "min_photons": 10,
                  "initial_x0": [2.0, 0.0, 0.38, 1.22], "fixed_flags": [0, 1, 1, 1]},
    }))
    (tmp_path / "h2mm_result.json").write_text(json.dumps({
        "settings_applied": {"streams": [{"name": "green", "channels": GREEN}]}
    }))

    # Without the experiment record there is no IRF, so nothing can be fitted…
    assert sm.detectors_from_analysis(tmp_path) == []

    info = tmp_path / "Info"
    info.mkdir()
    (info / "experiment_settings.json").write_text(json.dumps({
        "format": "chisurf-burst-experiment", "version": 1,
        "detectors": {"green": {"irf": _irf().tolist(),
                                "background": np.zeros(2 * N_BINS).tolist()}},
    }))
    dets = sm.detectors_from_analysis(tmp_path)
    assert [d.name for d in dets] == ["green"]
    d = dets[0]
    assert d.n_bins == N_BINS and d.channels == GREEN
    assert d.irf.size == 2 * N_BINS
    assert pytest.approx(d.dt) == DT


def test_stream_channels_come_from_the_h2mm_result(tmp_path):
    (tmp_path / "h2mm_result.json").write_text(json.dumps({
        "settings_applied": {"streams": [
            {"name": "green", "channels": [0, 8]},
            {"name": "red", "channels": [1, 9]},
            {"name": "yellow", "channels": [1, 9]},
        ]}
    }))
    assert sm.read_stream_channels(tmp_path) == {
        "green": [0, 8], "red": [1, 9], "yellow": [1, 9],
    }
    assert sm.read_stream_channels(pathlib.Path(tmp_path) / "nope") == {}


def test_the_panel_is_step_7_and_receives_the_folder(qapp, tmp_path):
    """Wired into the workflow after H2MM, and handed the folder like every step."""
    from chisurf.plugins.burst.burst_analysis.gui.tool import BURST_PANELS
    from chisurf.plugins.burst.burst_state_mle.gui.tool import BurstStateMleTool

    names = [p["name"] for p in BURST_PANELS]
    assert names.index("7. MLE-Statewise") == names.index("6. H2MM") + 1
    panel = next(p for p in BURST_PANELS if p.get("role") == "state_mle")
    assert panel["factory"].__name__ == "_burst_state_mle"

    tool = BurstStateMleTool(embedded=True)
    try:
        tool.set_folder(tmp_path)
        assert tool._folder_edit.text() == str(tmp_path)
        # An empty folder must say which step to run, not fail silently.
        assert "run H2MM first" in tool._lbl_photons.text()
        assert "MLE-Burstwise" in tool._lbl_detectors.text()
        # Nothing starts by itself: refitting every state is the workflow's most
        # expensive step, so arriving describes the folder and waits.
        tool.run()
        assert tool._results is None
    finally:
        tool.close()
