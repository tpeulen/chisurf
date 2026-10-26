"""The live PIE analysis: setup reading, photon classes, and live == offline for any batching."""

from __future__ import annotations

import numpy as np
import pytest
import tttrlib

from chisurf.plugins.core.acq.live.pie import (
    AA,
    DA,
    DD,
    OTHER,
    BurstParameters,
    PieBurstAnalyzer,
    PieSetup,
    analyze_offline,
    classify,
    fret,
)
from chisurf.plugins.core.acq.live.sources import Population, SimulatedPieSource


def _simulate(seconds=6.0, seed=3, pops=(Population(0.2), Population(0.8))):
    src = SimulatedPieSource(pops, duration_s=seconds, realtime=False, seed=seed)
    src.start()
    parts = []
    while not src.finished:
        batch = src.read(1.0)
        if batch is not None and len(batch):
            parts.append(batch)
    assert not src.error, src.error
    cat = [
        np.concatenate([getattr(p, k) for p in parts])
        for k in ("macro", "micro", "channel", "truth")
    ]
    return src, cat


@pytest.fixture(scope="module")
def run():
    return _simulate()


def _tttr(src, macro, micro, channel):
    t = tttrlib.TTTR()
    t.append_events(macro, micro, channel, np.zeros(len(macro), np.int8))
    t.header.set_tag("MeasDesc_GlobalResolution", src.info.macro_clock_s, 0x20000008)
    return t


def test_the_shared_channel_definition_is_read():
    setup = PieSetup.from_setup(
        {
            "data": {
                "windows": {"prompt": [0, 2048], "delayed": [2048, 4095]},
                "detectors": {"green": {"chs": [8, 0]}, "red": {"chs": [9, 1]}},
                "corrections": {"gamma": 0.9, "beta": 1.1, "alpha": 0.05, "delta": 0.07},
            }
        },
        name="lab",
    )
    assert setup.donor_channels == (8, 0) and setup.acceptor_channels == (9, 1)
    assert setup.prompt == (0, 2048) and setup.delay == (2048, 4095)
    assert setup.corrected and setup.alpha == 0.05


def test_a_setup_without_detectors_is_refused():
    with pytest.raises(ValueError):
        PieSetup.from_setup({"windows": {"prompt": [0, 1], "delayed": [1, 2]}, "detectors": {}})


def test_photons_are_classed_by_detector_and_window():
    setup = PieSetup(prompt=(0, 10), delay=(10, 20))
    codes = classify(setup, np.array([1, 1, 15, 15, 25]), np.array([0, 1, 1, 0, 1]))
    assert codes.tolist() == [DD, DA, AA, OTHER, OTHER]


def test_corrections_follow_lee_2005():
    raw = PieSetup()
    e, s = fret(raw, [60.0], [40.0], [100.0])
    assert e[0] == pytest.approx(0.4) and s[0] == pytest.approx(0.5)
    corr = PieSetup(gamma=2.0, beta=1.0, alpha=0.0, delta=0.0)
    e, s = fret(corr, [60.0], [40.0], [100.0])
    assert e[0] == pytest.approx(40.0 / (120.0 + 40.0))


def test_the_simulator_places_red_laser_photons_in_the_delay_window(run):
    src, (macro, micro, channel, truth) = run
    donor_delay = (channel == 0) & (micro >= src.info.n_micro // 2)
    # the donor is never excited by the red laser: only background lands there
    assert set(np.unique(truth[donor_delay]).tolist()) <= {len(src.populations)}


@pytest.mark.parametrize("chunk", [1, 37, 5000, 10**9])
def test_live_equals_offline_for_any_batching(run, chunk):
    src, (macro, micro, channel, _truth) = run
    setup = PieSetup.default_for(src.info.n_micro)
    an = PieBurstAnalyzer(setup, src.info.macro_clock_s, src.info.n_micro, BurstParameters())
    for a in range(0, len(macro), chunk):
        an.push(macro[a : a + chunk], micro[a : a + chunk], channel[a : a + chunk])
    an.finish()
    live = an.results()
    off = analyze_offline(_tttr(src, macro, micro, channel), setup)
    assert an.burst_count > 50
    for col in (
        "First Photon",
        "Last Photon",
        "Number of Photons (DD)",
        "Number of Photons (DA)",
        "Number of Photons (AA)",
    ):
        assert np.array_equal(live[col], off[col]), col
    assert np.allclose(live["E"], off["E"], equal_nan=True)
    assert np.allclose(live["S"], off["S"], equal_nan=True)


def test_the_known_answer_comes_back(run):
    src, (macro, micro, channel, _truth) = run
    an = PieBurstAnalyzer(
        PieSetup.default_for(src.info.n_micro), src.info.macro_clock_s, src.info.n_micro
    )
    an.push(macro, micro, channel)
    an.finish()
    t = an.results()
    ok = np.isfinite(t["E"]) & np.isfinite(t["S"]) & (t["Number of Photons"] >= 40)
    e, s = t["E"][ok], t["S"][ok]
    assert np.median(e[e < 0.5]) == pytest.approx(0.2, abs=0.05)
    assert np.median(e[e >= 0.5]) == pytest.approx(0.8, abs=0.05)
    assert np.median(s) == pytest.approx(0.5, abs=0.08)
    snap = an.snapshot()
    shown = np.asarray(an.live_es)
    in_range = (
        np.isfinite(shown).all(axis=1) & (shown >= -0.1).all(axis=1) & (shown < 1.1).all(axis=1)
    )
    assert snap["es"].sum() == in_range.sum()  # every burst in range lands in the histogram


def test_memory_is_bounded_by_the_open_burst(run):
    src, (macro, micro, channel, _truth) = run
    an = PieBurstAnalyzer(
        PieSetup.default_for(src.info.n_micro), src.info.macro_clock_s, src.info.n_micro
    )
    for a in range(0, len(macro), 2000):
        an.push(macro[a : a + 2000], micro[a : a + 2000], channel[a : a + 2000])
    assert len(an._codes) < len(macro) // 10
