"""The realistic simulator: the signatures of a real smFRET measurement are there and correct.

Ideal stays the clean stream the exact tests use; Realistic adds donor-only and acceptor-only
molecules, bleaching and blinking, crosstalk, background, scatter, afterpulses, an instrument
response, lifetimes and detector dead time -- each checked against what it was configured to be.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from tttrlib import StreamingBurstAnalyzer

from chisurf.plugins.core.acq.live.qc import live_qc
from chisurf.plugins.core.acq.live.realism import IDEAL, REALISTIC
from chisurf.plugins.core.acq.live.setups import Experiment, default_setup
from chisurf.plugins.core.acq.live.sources import SimulatedPieSource

SECONDS = 20.0
SETUP = default_setup("pie", 4000)


def _photons(realism, seconds=SECONDS, seed=3):
    src = SimulatedPieSource(duration_s=seconds, realtime=False, seed=seed, realism=realism)
    src.start()
    parts = []
    while not src.finished:
        b = src.read(1.0)
        if b is not None and len(b):
            parts.append(b)
    assert not src.error, src.error
    return src, {
        k: np.concatenate([getattr(p, k) for p in parts])
        for k in ("macro", "micro", "channel", "truth")
    }


def _analyse(src, ph, factors=None):
    a = StreamingBurstAnalyzer.from_setup(
        SETUP, "pie", min_photons=30, window_photons=10, window_time=1e-3,
        macro_time_resolution=src.info.macro_clock_s, micro_time_resolution=src.info.micro_res_s,
        factors=factors, decays=(4000, 4000, False), donor="G|G", acceptor="R|G",
    )  # fmt: skip
    a.push_np(ph["macro"], ph["micro"], ph["channel"].astype(np.int32))
    a.flush()
    return a


@pytest.fixture(scope="module")
def realistic():
    src, ph = _photons(REALISTIC)
    return src, ph, _analyse(src, ph, factors=REALISTIC.factors())


def test_ideal_is_the_clean_stream_unchanged():
    a = SimulatedPieSource(duration_s=5.0, realtime=False, seed=2)
    b = SimulatedPieSource(duration_s=5.0, realtime=False, seed=2, realism=IDEAL)
    pa, pb = a.simulate_segment(0), b.simulate_segment(0)
    for k in ("macro", "micro", "channel", "truth"):
        assert np.array_equal(getattr(pa, k), getattr(pb, k)), k


def test_a_realistic_run_is_reproducible():
    a = SimulatedPieSource(
        duration_s=5.0, realtime=False, seed=4, realism=REALISTIC
    ).simulate_segment(0)
    b = SimulatedPieSource(
        duration_s=5.0, realtime=False, seed=4, realism=REALISTIC
    ).simulate_segment(0)
    assert np.array_equal(a.macro, b.macro) and np.array_equal(a.micro, b.micro)


def test_donor_only_and_acceptor_only_islands(realistic):
    _src, _ph, a = realistic
    t = a.table()
    s = t["Stoichiometry"]
    assert 0.06 < np.mean(s > 0.85) < 0.35  # donor-only and acceptor-bleached bursts at S ~ 1
    assert 0.01 < np.mean(s < 0.2) < 0.2  # acceptor-only at S ~ 0


def test_raw_values_are_distorted_and_the_configured_corrections_recover_the_truth(realistic):
    _src, _ph, a = realistic
    t = a.table()
    sc = t["Stoichiometry (corrected)"]
    ok = (sc > 0.3) & (sc < 0.7) & (t["Number of Photons"] >= 40)
    e = t["FRET Efficiency"][ok]
    assert np.median(e[e < 0.5]) == pytest.approx(0.2, abs=0.06)
    assert np.median(e[e >= 0.5]) == pytest.approx(0.8, abs=0.06)
    assert np.median(sc[ok]) == pytest.approx(0.5, abs=0.08)
    raw = t["Proximity Ratio"][ok]
    assert np.median(raw[raw < 0.5]) - 0.2 > 0.03  # leakage and direct excitation raise raw E


def test_bleaching_puts_bursts_between_the_populations():
    def bridge(realism):
        src, ph = _photons(realism, seconds=10.0, seed=5)
        t = _analyse(src, ph).table()
        s = t["Stoichiometry"]
        return np.mean((s > 0.6) & (s < 0.85) & (t["Number of Photons"] >= 40))

    without = replace(
        REALISTIC, acceptor_bleach_per_ms=0.0, donor_bleach_per_ms=0.0, acceptor_blink_per_ms=0.0
    )
    assert bridge(REALISTIC) > bridge(without) + 0.02


def test_the_measured_background_is_the_configured_one(realistic):
    _src, _ph, a = realistic
    bg = a.snapshot()["background_cps"]
    # the donor detector in the delay window: only the flat background (half the period) and
    # afterpulses -- the donor's own photons are in the prompt window
    assert bg["delayed G|G"] == pytest.approx(REALISTIC.background_donor_khz * 1e3 / 2, rel=0.25)


def test_decays_show_the_instrument_response_and_the_lifetimes(realistic):
    src, _ph, a = realistic
    decays = a.snapshot()["decays"]
    res_ns = src.info.micro_res_s * 1e9
    donor = decays["prompt G|G"]
    assert int(np.argmax(donor)) * res_ns == pytest.approx(
        0.5, abs=0.2
    )  # the pulse, through the IRF
    aa = decays["delayed R|G"][2000:]
    peak = int(np.argmax(aa))
    t = np.arange(aa.size) * res_ns
    tail = (t > t[peak] + 1.0) & (t < t[peak] + 8.0) & (aa > 0)
    slope = np.polyfit(t[tail], np.log(aa[tail]), 1)[0]
    assert -1.0 / slope == pytest.approx(REALISTIC.tau_acceptor_ns, rel=0.3)


def test_dead_time_and_realistic_count_rates(realistic):
    src, ph, a = realistic
    for ch in (0, 1):
        gaps = np.diff(ph["macro"][ph["channel"] == ch].astype(np.int64)) * src.info.macro_clock_s
        assert gaps.min() >= REALISTIC.dead_time_ns * 1e-9 - src.info.macro_clock_s
    rate = np.median(a.table()["Count Rate (KHz)"])
    assert 10.0 < rate < 120.0  # tens of kHz in bursts


def test_the_quality_lights_react(realistic):
    src, _ph, a = realistic
    exp = Experiment(SETUP, "pie")
    t = a.table()
    snap = a.snapshot()
    qc = live_qc(
        t, exp, elapsed_s=snap["elapsed_s"], background_cps=snap["background_cps"],
        trace=(np.arange(20) + 0.5, np.full(20, 5.0)), macro_clock_s=src.info.macro_clock_s,
        micro_res_s=src.info.micro_res_s, n_micro=src.info.n_micro, n_photons=snap["photons"],
    )  # fmt: skip
    checks = {c["name"]: c for c in qc["checks"]}
    assert qc["ready"]
    do, ao = checks["donor-only / acceptor-only"]["value"].split(" / ")
    assert int(do.rstrip(" %")) > 3 and int(ao.rstrip(" %")) > 0  # the islands are seen
