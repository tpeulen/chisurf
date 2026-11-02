"""The live burst analyzer: batch-equal per preset, tttrlib's contract, the known answer comes back.

`make_analyzer` is tttrlib's StreamingBurstAnalyzer.from_setup; the batch reference
`analyze_offline` holds its tables.
"""

from __future__ import annotations

import numpy as np
import pytest
import tttrlib

from chisurf.plugins.core.acq.live.analyzer import (
    PRESETS,
    analyze_offline,
    make_analyzer,
)
from chisurf.plugins.core.acq.live.setups import default_setup, infer_preset
from chisurf.plugins.core.acq.live.sources import SimulatedPieSource

N_MICRO = 4000
PIE = default_setup("pie", N_MICRO)
TWO = default_setup("two_color", N_MICRO)


def _simulate(scheme, seconds=6.0, seed=3):
    src = SimulatedPieSource(duration_s=seconds, realtime=False, seed=seed, scheme=scheme)
    src.start()
    parts = []
    while not src.finished:
        b = src.read(1.0)
        if b is not None and len(b):
            parts.append(b)
    assert not src.error, src.error
    cat = [np.concatenate([getattr(p, k) for p in parts]) for k in ("macro", "micro", "channel")]
    return src, cat


@pytest.fixture(scope="module")
def pie_run():
    return _simulate("pie")


@pytest.fixture(scope="module")
def two_run():
    return _simulate("two_color")


def _tttr(src, macro, micro, channel):
    t = tttrlib.TTTR()
    t.append_events(macro, micro, channel, np.zeros(len(macro), np.int8))
    t.header.set_tag("MeasDesc_GlobalResolution", src.info.macro_clock_s, 0x20000008)
    return t


def _live(src, data, setup, preset, chunk, **kw):
    macro, micro, channel = data
    a = make_analyzer(
        setup,
        preset,
        min_photons=30,
        window_photons=10,
        window_time=1e-3,
        macro_time_resolution=src.info.macro_clock_s,
        micro_time_resolution=src.info.micro_res_s,
        **kw,
    )
    for k in range(0, len(macro), chunk):
        a.push_np(
            macro[k : k + chunk], micro[k : k + chunk], channel[k : k + chunk].astype(np.int32)
        )
    a.flush()
    return a


@pytest.mark.parametrize("chunk", [1, 37, 5000, 10**9])
@pytest.mark.parametrize("preset", ["pie", "two_color"])
def test_live_equals_the_batch_for_any_chunking(pie_run, two_run, preset, chunk):
    src, data = pie_run if preset == "pie" else two_run
    setup = PIE if preset == "pie" else TWO
    table = _live(src, data, setup, preset, chunk).table()
    off = analyze_offline(
        _tttr(src, *data), setup, preset, min_photons=30, window_photons=10, window_time=1e-3
    )
    assert len(off["First Photon"]) > 50
    for col, ref in off.items():
        if ref.dtype.kind == "f":
            assert np.allclose(table[col], ref, equal_nan=True), col
        else:
            assert np.array_equal(table[col], ref), col


def test_the_contract_columns_snapshot_and_histograms(pie_run):
    src, data = pie_run
    a = _live(src, data, PIE, "pie", 5000, trace=(0.1, 600), decays=(400, N_MICRO, False))
    table = a.table()
    names = list(table)
    assert names[:6] == [
        "First Photon", "Last Photon", "Duration (ms)", "Mean Macro Time (ms)",
        "Number of Photons", "Count Rate (KHz)",
    ]  # fmt: skip
    assert "S prompt G|G (photons) | 0-2000" in names and names[-2:] == [
        "Proximity Ratio",
        "Stoichiometry",
    ]
    assert (
        table["First Photon"].dtype == np.int64
        and table["S prompt G|G (photons) | 0-2000"].dtype == np.int64
    )
    snap = a.snapshot()
    for key in ("revision", "bursts", "photons", "elapsed_s", "burst_rate_hz", "background_cps",
                "histograms", "trace", "decays", "burst_decays"):  # fmt: skip
        assert key in snap, key
    assert set(snap["background_cps"]) == {
        "prompt G|G",
        "prompt R|G",
        "delayed G|G",
        "delayed R|G",
        "G|G",
        "R|G",
    }
    es = snap["histograms"]["Proximity Ratio vs Stoichiometry"]
    assert es["counts"].shape == (50, 50) and len(es["x_edges"]) == 51
    inside = (table["Proximity Ratio"] >= -0.1) & (table["Proximity Ratio"] < 1.1)
    inside &= (table["Stoichiometry"] >= -0.1) & (table["Stoichiometry"] < 1.1)
    assert es["counts"].sum() == inside.sum()
    assert snap["bursts"] == len(table["First Photon"])


def test_correction_factors_add_the_corrected_columns(pie_run):
    src, data = pie_run
    a = _live(
        src, data, PIE, "pie", 5000, factors={"gamma": 1.0, "beta": 1.0, "alpha": 0.0, "delta": 0.0}
    )
    t = a.table()
    # with unit factors and no background, accurate FRET reduces to the raw ratios
    assert np.allclose(t["FRET Efficiency"], t["Proximity Ratio"])
    assert np.allclose(t["Stoichiometry (corrected)"], t["Stoichiometry"])
    assert "FRET Efficiency vs Stoichiometry (corrected)" in a.histograms()


@pytest.mark.parametrize("preset", ["pie", "two_color"])
def test_the_known_answer_comes_back(pie_run, two_run, preset):
    src, data = pie_run if preset == "pie" else two_run
    t = _live(src, data, PIE if preset == "pie" else TWO, preset, 10**9).table()
    ok = t["Number of Photons"] >= 40
    pr = t["Proximity Ratio"][ok]
    assert np.median(pr[pr < 0.5]) == pytest.approx(0.2, abs=0.06)
    assert np.median(pr[pr >= 0.5]) == pytest.approx(0.8, abs=0.06)
    if preset == "pie":
        assert np.median(t["Stoichiometry"][ok]) == pytest.approx(0.5, abs=0.08)


def test_the_presets_infer_from_their_setups():
    assert infer_preset(PIE) == "pie" and infer_preset(TWO) == "two_color"
    assert infer_preset(default_setup("single_color", N_MICRO)) == "single_color"
    assert infer_preset({"detectors": {"green_par": {}, "green_perp": {}}}) == "mfd"
    assert set(PRESETS) == set(tttrlib.StreamingBurstAnalyzer.PRESETS)
