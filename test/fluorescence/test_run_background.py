"""A run's background: per-detector rates from the strict selection, stored with the run.

``chisurf.core.fio.fluorescence.run_background`` computes each detector's background rate from
the strict selection of background photons around a run's bursts and stores it as
``<run>/background`` (``Detector``, ``Rate`` kHz, ``Source``, ``Seconds``), derived from the
run's burst table. ndX reads it back as ``Bg_<detector>`` -- what it opens a run with.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

RUN = "sliding_window_All 0.1500#60"
RES_S = 1e-7


def _photons(seed=2, seconds=200.0, rates=(1.2, 0.8)):
    """A flat background on two detectors (channels 0, 1) and bright bursts on both."""
    rng = np.random.default_rng(seed)
    times, channels, bursts = [], [], []
    for ch, khz in enumerate(rates):
        t = rng.random(rng.poisson(khz * 1e3 * seconds)) * seconds
        times.append(t)
        channels.append(np.full(t.size, ch))
    for start in rng.random(int(0.5 * seconds)) * seconds:
        n = rng.poisson(120)
        t = start + rng.random(n) * 2e-3
        times.append(t)
        channels.append(rng.integers(0, 2, n))
        bursts.append((start, start + 2e-3))
    t = np.concatenate(times)
    ch = np.concatenate(channels)
    order = np.argsort(t, kind="stable")
    t, ch = t[order], ch[order]
    in_burst = np.zeros(t.size, bool)
    for lo, hi in bursts:
        in_burst[np.searchsorted(t, lo):np.searchsorted(t, hi)] = True
    tttr = SimpleNamespace(
        macro_times=np.round(t / RES_S).astype(np.int64),
        routing_channel=ch.astype(np.int16),
        micro_times=np.zeros(t.size, dtype=np.int32),
        header=SimpleNamespace(macro_time_resolution=RES_S),
    )
    return tttr, in_burst


DETECTORS = {"G|G": {"chs": [0]}, "R|G": {"chs": [1]}}


def test_each_detector_gets_its_own_rate():
    from chisurf.core.fio.fluorescence.run_background import strict_selection_rates

    tttr, in_burst = _photons()
    rates, info = strict_selection_rates(tttr, in_burst, DETECTORS)
    assert rates["G|G"] == pytest.approx(1.2, rel=0.08)
    assert rates["R|G"] == pytest.approx(0.8, rel=0.08)
    assert info["seconds"] > 0.5 * info["total_seconds"]


def _container(tmp_path):
    from chisurf.core.fio.fluorescence.burst_tree import OPERATION
    from chisurf.core.fio.pto import Measurement

    path = tmp_path / "m000.pto"
    with Measurement.create_empty(path, title="test") as m:
        m.put_table(
            f"{RUN}/bi4_bur/m000.bur",
            {"First Photon": np.arange(0, 100, 10, dtype=np.int64),
             "Last Photon": np.arange(5, 105, 10, dtype=np.int64),
             "Duration (ms)": np.full(10, 2.0)},
            artifact_kind="burst_table", operation_type=OPERATION, row_grain="burst",
            parameters={"min_photons": 60},
        )
    return path


def test_the_record_is_the_runs_and_ndx_reads_it(tmp_path):
    from chisurf.core.fio.fluorescence.run_background import (
        read_run_background,
        write_run_background,
    )
    from chisurf.core.fio.pto import Measurement

    path = _container(tmp_path)
    with Measurement.open(path, writable=True) as m:
        uid = write_run_background(m, RUN, {"G|G": 1.9, "R|G": 0.67, "R|R": float("nan")},
                                   "strict selection", seconds=120.0)
        parents = m.parents(uid)
        assert m._f.find(f"{RUN}/bi4_bur/m000.bur") in parents  # linked to the run's bursts
    # writing again replaces it
    with Measurement.open(path, writable=True) as m:
        write_run_background(m, RUN, {"G|G": 2.0, "R|G": 0.7}, {"G|G": "buffer", "R|G": "model"})
        assert [str(o.name) for o in m._f.objects()].count(f"{RUN}/background") == 1
    back = read_run_background(path, RUN)
    assert back["G|G"] == {"rate_khz": 2.0, "source": "buffer", "seconds": pytest.approx(np.nan, nan_ok=True)}
    assert set(back) == {"G|G", "R|G"}

    ndx = pytest.importorskip("ndxplorer.analysis.fret_background")
    found = ndx.stored_background(str(path), RUN)
    assert found["G|G"]["rate"] == 2.0 and found["R|G"]["source"] == "model"
    assert ndx.stored_background_constants(str(path), RUN) == {"Bg_G|G": 2.0, "Bg_R|G": 0.7}
