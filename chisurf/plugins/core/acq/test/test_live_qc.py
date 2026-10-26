"""Live quality lights: the FRET quality checker's verdict on a live run, and where it is kept."""

from __future__ import annotations

import json

import numpy as np
import pytest

from chisurf.plugins.core.acq.live.qc import MIN_BURSTS, live_qc
from chisurf.plugins.core.acq.live.session import RUN_NAME, RecordSession, quality_record
from chisurf.plugins.core.acq.live.setups import Experiment, default_setup
from chisurf.plugins.core.acq.live.sources import Population, SimulatedPieSource


def _run(concentration, seconds=15.0, seed=2, ptu=None):
    src = SimulatedPieSource(
        (Population(0.2, 0.5, concentration), Population(0.8, 0.5, concentration)),
        duration_s=None,
        realtime=False,
        seed=seed,
    )
    session = RecordSession(src, duration_s=seconds, ptu_path=ptu)
    session.start()
    result = session.wait(300)
    assert result is not None and not session.error, session.error
    return session, result


@pytest.fixture(scope="module")
def crowded():
    """Far too concentrated: many molecules in the focus at once."""
    return _run(concentration=25.0)


def test_too_high_occupancy_turns_the_occupancy_light_red_with_the_checkers_text(crowded):
    from chisurf.plugins.burst.fret_check.report import _ISSUE_ACTION

    _session, result = crowded
    qc = result.qc
    assert qc["ready"] and qc["level"] == "red"
    checks = {c["name"]: c for c in qc["checks"]}
    density = checks["burst density"]
    assert density["light"] == "red"
    assert density["action"] == _ISSUE_ACTION["burst density"]
    assert checks["multi-molecule events"]["light"] == "red"
    assert "dilute" in checks["multi-molecule events"]["action"]


def test_the_lights_stay_grey_until_there_is_enough_data(crowded):
    session, result = crowded
    few = {k: v[: MIN_BURSTS - 1] for k, v in result.table.items()}
    qc = live_qc(
        few,
        session.experiment,
        elapsed_s=result.elapsed_s,
        background_cps=session.analyzer.snapshot()["background_cps"],
        trace=session.trace_1s(),
        macro_clock_s=session.source.info.macro_clock_s,
        micro_res_s=session.source.info.micro_res_s,
        n_micro=session.source.info.n_micro,
        n_photons=result.photons,
    )
    assert not qc["ready"] and qc["level"] == "grey" and qc["checks"] == []


def test_without_alternation_stoichiometry_is_not_applicable():
    src = SimulatedPieSource(duration_s=None, realtime=False, seed=5, scheme="two_color")
    exp = Experiment(default_setup("two_color", 4000), "two_color")
    session = RecordSession(src, exp, duration_s=12.0)
    session.start()
    result = session.wait(300)
    checks = {c["name"]: c for c in result.qc["checks"]}
    assert checks["donor-only / acceptor-only"]["light"] == "grey"
    assert checks["donor-only / acceptor-only"]["value"] == "not applicable"
    assert "low-E / donor-only" in checks  # the checker's own two-colour check stands in
    assert checks["ALEX-2CDE > 30"]["value"] == "not computed live"


def test_the_live_snapshot_carries_the_verdict(crowded):
    session, _result = crowded
    assert session.snapshot()["qc"]["level"] == "red"


def test_the_verdict_at_stop_is_stored_with_the_run_and_ndx_reads_it(tmp_path):
    pto_reader = pytest.importorskip("ndxplorer.io.pto_reader")
    from chisurf.core.datastore import store_from_rows
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    _session, result = _run(concentration=25.0, seconds=8.0, seed=4, ptu=tmp_path / "crowded.ptu")
    cols = list(result.table)
    rows = [{c: result.table[c][i].item() for c in cols} for i in range(result.bursts)]
    container = write_container(
        result.ptu,
        store_from_rows(rows, cols),
        parameters={"mode": "live_pie", "quality": quality_record(result.qc)},
        out_dir=tmp_path / "ac",
        raw_data="sidecar",
        run=RUN_NAME,
    )
    store, provenance = pto_reader.read_run(container)
    assert int(np.asarray(store["Proximity Ratio"]).size) == result.bursts
    assert "quality" in json.dumps(provenance, default=str)
    assert '"level": "red"' in json.dumps(provenance, default=str).replace("\\", "")
