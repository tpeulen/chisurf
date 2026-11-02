"""The guard: a live run equals the offline analysis of its recording, and ndX reads its bursts."""

from __future__ import annotations

import numpy as np
import pytest
import tttrlib

from chisurf.core.fluorescence.burst import burst_filter
from chisurf.plugins.core.acq.live.analyzer import analyze_offline
from chisurf.plugins.core.acq.live.session import RUN_NAME, RecordSession
from chisurf.plugins.core.acq.live.sources import SimulatedPieSource


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    out = tmp_path_factory.mktemp("rec")
    src = SimulatedPieSource(duration_s=None, realtime=False, seed=11)
    session = RecordSession(src, duration_s=6.0, ptu_path=out / "run.ptu", name="run")
    session.start()
    result = session.wait(120)
    assert result is not None and not session.error, session.error
    return session, result, out


def test_the_recording_holds_every_photon_and_stops_at_the_duration(recorded):
    session, result, _out = recorded
    assert result.stop_reason == "duration reached"
    assert result.elapsed_s == pytest.approx(6.0, abs=0.01)
    assert len(tttrlib.TTTR(str(result.ptu))) == result.photons
    assert session.dropped == 0


def test_live_equals_offline_on_the_recorded_file(recorded):
    session, result, _out = recorded
    tttr = tttrlib.TTTR(str(result.ptu))
    exp = session.experiment
    b = exp.burst
    off = analyze_offline(
        tttr,
        exp.setup,
        exp.preset,
        min_photons=b.min_photons,
        window_photons=b.window_photons,
        window_time=b.window_time_s,
    )
    assert result.bursts > 50
    for col in (
        "First Photon",
        "Last Photon",
        "Number of Photons (G|G)",
        "Number of Photons (R|G)",
    ):
        assert np.array_equal(result.table[col], off[col]), col
    assert np.allclose(result.table["Proximity Ratio"], off["Proximity Ratio"])
    assert np.allclose(result.table["Stoichiometry"], off["Stoichiometry"])


def test_burst_selection_finds_the_same_bursts_in_the_recording(recorded):
    session, result, _out = recorded
    tttr = tttrlib.TTTR(str(result.ptu))
    p = session.experiment.burst
    mask = burst_filter(tttr, p.min_photons, p.window_photons, p.window_time_s)
    live = np.zeros(len(tttr), bool)
    for a, b in zip(result.table["First Photon"], result.table["Last Photon"]):
        live[a : b + 1] = True
    assert np.array_equal(mask, live)


def test_the_run_is_written_where_ndx_reads_it(recorded):
    pto_reader = pytest.importorskip("ndxplorer.io.pto_reader")
    from chisurf.core.datastore import store_from_rows
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    _session, result, out = recorded
    cols = list(result.table)
    rows = [{c: result.table[c][i].item() for c in cols} for i in range(result.bursts)]
    container = write_container(
        result.ptu,
        store_from_rows(rows, cols),
        out_dir=out / "ac",
        raw_data="sidecar",
        run=RUN_NAME,
    )
    store, _prov = pto_reader.read_run(container)
    assert int(np.asarray(store["Number of Photons"]).size) == result.bursts
    assert np.allclose(np.asarray(store["Proximity Ratio"]), result.table["Proximity Ratio"])
