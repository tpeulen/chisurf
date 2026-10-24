"""detect -> analyse -> qc on synthetic photons and, when present, tttr-data."""
import pathlib

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.plugins.burst.fret_check.detect import detect_experiment, load, open_measurement, with_phase  # noqa: E402
from chisurf.plugins.burst.fret_check.pipeline import BurstSettings, _merge, analyse  # noqa: E402
from chisurf.plugins.burst.fret_check.qc import FLAG_BRIGHT, _lambda_for, _p_multi, run_qc  # noqa: E402

DATA = pathlib.Path(__file__).resolve().parents[5].parent / "tttr-data"
RES = 12.5e-9


def synthetic(alternating: bool, n_bursts=1000, seed=1, donor=0, acceptor=1, donor_only=0.0,
              macro_period=0):
    """Poisson background plus bursts of a single E=0.5 species (S=0.5 with ALEX)."""
    rng = np.random.default_rng(seed)
    t, ch, micro = [], [], []
    duration = 20.0
    # Background 0.5 kHz per channel.
    for c in (donor, acceptor):
        n = rng.poisson(5e2 * duration)
        t.append(rng.uniform(0, duration, n)); ch.append(np.full(n, c))
        micro.append(np.zeros(n, int) if macro_period else rng.integers(0, 4096, n))
    starts = np.sort(rng.uniform(0, duration - 0.01, n_bursts))
    for s in starts:
        n = rng.poisson(150)
        tb = s + rng.uniform(0, 1e-3, n)
        e = 0.03 if rng.random() < donor_only else 0.5
        if alternating:
            aex = rng.random(n) < 0.5
            c = np.where(aex, acceptor, np.where(rng.random(n) < e, acceptor, donor))
            m = np.where(aex, rng.integers(2048, 4096, n), rng.integers(0, 2048, n))
        else:
            aex = np.zeros(n, bool)
            c = np.where(rng.random(n) < e, acceptor, donor)
            m = rng.integers(0, 4096, n)
        if macro_period:
            # µsALEX in the macro time: place each photon in its half period.
            ticks = (tb / RES).astype(np.int64)
            half = macro_period // 2
            ticks = ticks - ticks % macro_period + np.where(aex, half, 0) + rng.integers(0, half, n)
            tb = ticks * RES
            m = np.zeros(n, int)
        t.append(tb); ch.append(c); micro.append(m)
    t = np.concatenate(t); order = np.argsort(t)
    macro = (t[order] / RES).astype(np.uint64)
    routing = np.concatenate(ch)[order].astype(np.int8)
    micro = np.concatenate(micro)[order].astype(np.uint16)
    d = tttrlib.TTTR(macro, micro, routing, np.zeros(macro.size, np.int8))
    d.header.set_macro_time_resolution(RES)
    return d


def test_merge_overlapping():
    iv = np.array([[25, 144], [137, 208], [213, 543], [500, 600]])
    assert _merge(iv).tolist() == [[25, 208], [213, 600]]


def test_p_multi_limits():
    assert _p_multi(0.0) == 0.0
    assert _p_multi(1e-3) == pytest.approx(5e-4, rel=1e-2)


@pytest.mark.parametrize("alternating", [False, True])
def test_synthetic_es(alternating):
    d = synthetic(alternating)
    e = detect_experiment(d)
    assert e.excitation == ("alternating" if alternating else "cw")
    if alternating:
        assert e.donor_channels == [0] and e.acceptor_channels == [1]
    b = analyse(d, e, BurstSettings(min_photons=50, m=10, T=200e-6))
    assert b.n > 300
    assert np.median(b.E) == pytest.approx(0.5, abs=0.05)
    if alternating:
        assert np.median(b.S) == pytest.approx(0.5, abs=0.05)
    q = run_qc(d, e, b)
    assert q.p_multi < 0.1
    assert {c.name for c in q.checks} >= {"multi-molecule events", "signal stability"}


def test_bright_outlier_flagged():
    d = synthetic(False)
    e = detect_experiment(d)
    b = analyse(d, e, BurstSettings(min_photons=50, m=10, T=200e-6))
    b.counts["DD"][0] *= 50
    b.duration[0] = np.median(b.duration)
    q = run_qc(d, e, b)
    assert q.flags[0] & FLAG_BRIGHT


@pytest.mark.skipif(not (DATA / "sm/cal1").is_dir(), reason="tttr-data not present")
def test_cal1_alex_pto():
    d = load(DATA / "sm/cal1/001_60g_25r_cal1_cy3b_8_18_33bp_atto647n_alex.pto")
    e = detect_experiment(d)
    assert e.kind == "2c µsALEX"
    assert e.donor_channels == [1] and e.acceptor_channels == [0]


def test_cw_donor_from_donor_only_bursts():
    """cw: the donor is the colour with single-colour bursts, whatever its number."""
    d = synthetic(False, donor=1, acceptor=0, donor_only=0.3)
    e = detect_experiment(d)
    assert e.excitation == "cw"
    assert e.donor_channels == [1] and e.acceptor_channels == [0]


def test_usalex_in_macro_time():
    """µsALEX with no micro time: the period is found and folded into the micro time."""
    d = synthetic(True, macro_period=8000)  # 100 µs at 12.5 ns
    e = detect_experiment(d)
    assert e.alex_period == 8000
    assert e.excitation == "alternating"
    assert e.donor_channels == [0] and e.acceptor_channels == [1]
    b = analyse(with_phase(d, e.alex_period), e, BurstSettings(min_photons=50, m=10, T=200e-6))
    assert np.median(b.S) == pytest.approx(0.5, abs=0.05)


def test_dilution_target():
    lam = _lambda_for(0.02)
    assert _p_multi(lam) == pytest.approx(0.02, rel=1e-3)


@pytest.mark.skipif(not (DATA / "sm/cal1").is_dir(), reason="tttr-data not present")
def test_cal1_sm_is_usalex():
    _, e = open_measurement(DATA / "sm/cal1/001_60g_25r_cal1_cy3b_8_18_33bp_atto647n.sm")
    assert e.alex_period == 8000
    assert e.donor_channels == [1] and e.acceptor_channels == [0]


def test_no_background_time_gives_no_signal_to_background_verdict():
    """Bulk-like data: nothing outside bursts -- S/B is n/a, not an OK 'inf'."""
    import dataclasses

    from chisurf.plugins.burst.fret_check.qc import INFO

    d = synthetic(False)
    e = detect_experiment(d)
    b = analyse(d, e, BurstSettings(min_photons=50, m=10, T=200e-6))
    b = dataclasses.replace(b, background={k: 0.0 for k in b.background})
    q = run_qc(d, e, b)
    sb = next(c for c in q.checks if c.name == "signal / background")
    assert (sb.level, sb.value) == (INFO, "n/a")
