"""Burst MLE ahead of Next: the bursts a search found in memory are prepared and fitted before
they are written; once Next wrote them as a run the state becomes the run's, and what it gives
is what reading that run gives -- the same rows, written into the same container."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from chisurf.plugins.burst.burst_mle_analysis import engine

from .test_mle_restored_inputs import fresh_session, inputs, set_window  # noqa: F401 - fixture


def _photons_and_table(container_run: Path):
    """The demo's photon file and the bursts of its run, as the search ahead hands them over."""
    from chisurf.core.datastore import column_names, concat_stores
    from chisurf.core.fio.analysis_path import split_container_path

    table, container = engine.read_burst_container(container_run)
    keep = [c for c in column_names(table) if not c.startswith("_") and c != "burst_file"]
    ahead = concat_stores([{c: table[c] for c in keep}])
    box, run = split_container_path(container_run)
    photons = Path(box).parent / f"{Path(box).stem}.ptu"
    assert photons.is_file(), photons
    return photons, ahead, Path(box) / (run or "demo")


def _prepare(session, inputs):  # noqa: F811 - the fixture
    session.set_binning(1)
    session.set_pattern_files("irf", "synthetic", [inputs["irf"]])
    session.set_pattern_files("bg", "synthetic", [inputs["bg"]])
    set_window(session)


def _same(a, b):
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return a == b


def test_fitted_ahead_then_attached_is_the_run_read_and_fitted(inputs, tmp_path):  # noqa: F811
    photons, table, run = _photons_and_table(Path(inputs["bur"]))

    from_run = fresh_session(run)
    _prepare(from_run, inputs)
    want = from_run.run_batch(max_workers=2)

    ahead = engine.MleSession(template=engine.MleSettings(gamma=0.0, r0=0.0))
    from chisurf.plugins.burst.burst_mle_analysis import demo

    ahead.set_definition(demo.SETUP)
    ahead.take_ahead({str(photons): table}, key="search-1")
    assert ahead.ahead_key == "search-1" and ahead.bur_files == [photons.resolve()]
    _prepare(ahead, inputs)
    got = ahead.run_batch(max_workers=2)
    with pytest.raises(ValueError, match="searched ahead"):
        ahead.export_results()  # no run to write into yet
    strict = ahead._memo_key()
    assert ahead.attach_run([run])
    assert ahead.burst_results is not got, "the rows fitted ahead are renamed as new rows"
    got = ahead.burst_results
    assert not ahead.ahead_key and ahead.bur_files == [run]
    assert ahead._memo_key() != strict and ahead.__dict__["_memo_cache"]["key"] == ahead._memo_key()
    assert len(got) == len(want) > 0
    for a, b in zip(want, got):
        assert list(a) == list(b)
        assert all(_same(a[k], b[k]) for k in a), {k: (a[k], b[k]) for k in a if not _same(a[k], b[k])}
    assert ahead.measurement_files() == from_run.measurement_files()
    assert ahead.export_results()


def test_runs_of_other_bursts_are_not_attached(inputs):  # noqa: F811
    photons, table, run = _photons_and_table(Path(inputs["bur"]))
    ahead = engine.MleSession()
    ahead.take_ahead({str(photons): table}, key="k")
    assert not ahead.attach_run([Path(str(run).replace("synthetic_mle", "another"))])
    assert ahead.ahead_key == "k"
    session = fresh_session(run)
    assert not session.attach_run([run]), "bursts read from a run are not ahead"


def _run_jobs(app, timeout=120.0):
    import time

    end = time.monotonic() + timeout
    while (app.pending or app.job.busy) and time.monotonic() < end:
        app.job.poll()
        app._fit_if_waiting()
        time.sleep(0.02)
    app.job.poll()
    assert not app.pending, "the jobs did not finish"


def test_the_app_fits_ahead_and_writes_after_next(inputs):  # noqa: F811
    """Through the app's real background jobs: fitted ahead (nothing written), then attached to
    the run Next wrote -- the step is fitted and the lifetimes are in the container."""
    from chisurf.plugins.burst.burst_mle_analysis import demo
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app

    photons, table, run = _photons_and_table(Path(inputs["bur"]))
    app = create_app()
    session = app.model.session
    session.set_definition(demo.SETUP)
    # what the preparation would find (no references in this test), set before the bursts come
    reference = fresh_session(run)
    _prepare(reference, inputs)
    session.set_binning(1)
    session.set_pattern_files("irf", "synthetic", [inputs["irf"]])
    session.set_pattern_files("bg", "synthetic", [inputs["bg"]])
    session.settings.micro_time_start = reference.settings.micro_time_start
    session.settings.micro_time_stop = reference.settings.micro_time_stop
    written = []
    real = engine.MleSession.export_results
    def export(self, tick=None):
        paths = real(self, tick)  # raises when no row names a loaded run
        written.append(len(paths))
        return paths

    engine.MleSession.export_results = export
    try:
        app.take_ahead({str(photons): table}, "search-1")
        assert app.ahead_key == "search-1"
        _run_jobs(app)
        assert app.model.burst_results, (app.job.error, app.model.status_text)
        assert not written, "nothing is written before the run exists"
        held = app.model.burst_results
        named = [row.get("First File") for row in held]
        # a job's copy shares the fitted rows (no copy of 65 k rows on the UI thread) ...
        import copy as _copy

        snapshot = _copy.copy(app.model)
        assert snapshot.burst_results is held and snapshot.session.burst_results is app.model.session.burst_results
        app.model.release_snapshot()
        assert app.attach_ahead([run])
        _run_jobs(app)
        # ... so attaching builds new rows and never renames the held ones
        assert [row.get("First File") for row in held] == named
        assert app.model.burst_results is not held
        assert app.model.burst_results is app.model.session.burst_results
        assert len(app.model.burst_results) == len(held)
        assert [row.get("First File") for row in app.model.burst_results] != named
    finally:
        engine.MleSession.export_results = real
    assert written and written[0] > 0, app.model.status_text
    assert app.model.session.bur_files == [run]
    assert app.model.held_fingerprint == app.model.session.batch_fingerprint()


def test_a_dropped_preparation_merges_nothing(inputs):  # noqa: F811
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app

    photons, table, _run = _photons_and_table(Path(inputs["bur"]))
    app = create_app()
    app._queue_job("load_example")  # a job ahead of it: the preparation is queued
    app.take_ahead({str(photons): table}, "old")
    app.drop_ahead()
    assert app.ahead_key is None
    assert all(job[0] != "take_ahead" for job in app.__dict__.get("_queued_jobs", []))
    _run_jobs(app)
    assert app.model.session.ahead_key == ""
