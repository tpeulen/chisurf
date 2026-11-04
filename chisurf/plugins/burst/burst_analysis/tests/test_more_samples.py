"""Step 4, *More samples*: further measurements processed with the recipe tuned on the first.

Real paths throughout: the demo session (measurement, buffer, water IRF, Rh110) is walked through
the hub to fitted lifetimes, the recipe is captured from the steps, and two further simulated
measurements of the same sample (:func:`..demo.make_more_samples`) are processed -- headless
(``BurstWorkflow.process_more``) and from the step itself. Their results equal the pipeline run
by hand on the same measurement with the same settings.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.emtk_test_input import Driver


@pytest.fixture(scope="module")
def first(tmp_path_factory):
    """The hub with the demo's first measurement fitted (Simple: BVA and 2CDE ran unseen)."""
    from chisurf.core.fluorescence import dyes
    from chisurf.plugins.burst.burst_analysis import demo
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app
    from chisurf.plugins.burst.burst_analysis.tests.test_emtk_native_hub import settle

    root = tmp_path_factory.mktemp("more_samples")
    patch = pytest.MonkeyPatch()
    for key, folder in (("CHISURF_SETTINGS_DIR", "s"), ("MMFDB_SETTINGS_DIR", "m")):
        (root / folder).mkdir()
        patch.setenv(key, str(root / folder))
    patch.setenv("MMFDB_DATABASE_PATH", str(root / "m.sqlite"))
    # the dye database as ChiSurf ships it (an empty configured MMFDB would be read instead)
    patch.setattr(dyes, "_entries_from_database", lambda: None)
    dyes.reference_dyes(refresh=True)
    files = demo.make_demo(root / "demo")
    more = demo.make_more_samples(root / "demo")
    hub = create_app()
    try:
        drv = Driver(hub, (1200, 800))
        drv.draw(2)
        assert not hub.panel_enabled("more")  # the steps open in order
        hub.setup_model.data = copy.deepcopy(demo.SETUP)
        hub.setup_model.changed()
        hub.context.channel_settings = hub.setup_model.get_settings()
        data = hub.ensure_child("data")
        data.source.auto_import = False
        data.source.add_paths([files[k] for k in ("measurement", "buffer", "irf", "reference")])
        end = time.monotonic() + 120
        while (data.job.busy or not hub.context.calibration) and time.monotonic() < end:
            time.sleep(0.1)
            data.poll_calibration()
        hub.select("selection")
        drv.draw(2)
        drv.click(hub.item_rects["fast_forward"])
        end = time.monotonic() + 240
        while time.monotonic() < end and not all(hub.step_done(r) for r in ("mle", "bva", "two_cde")):
            drv.draw(1)
            time.sleep(0.02)
        settle(drv)
        assert hub.step_done("mle"), hub.children["mle"].model.status_text
        yield {"hub": hub, "drv": drv, "files": files, "more": more, "root": root}
    finally:
        hub.close()
        patch.undo()
        try:
            dyes.reference_dyes(refresh=True)
        except Exception:  # noqa: BLE001 - the next user reloads it
            dyes._CACHE = None


def _mle_window(hub) -> dict:
    session = hub.children["mle"].model.session
    return {d: (st.micro_time_start, st.micro_time_stop) for d, st in session.det_settings.items()}


def test_the_recipe_is_the_tuned_pipeline_and_round_trips(first):
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app
    from chisurf.plugins.burst.burst_analysis.more_samples import Recipe

    hub = first["hub"]
    recipe = hub.capture_recipe()
    assert recipe.ready and recipe.steps() == ["bva", "two_cde"]  # what ran on the first data
    assert {Path(p).name: row for p, row in recipe.workflow["samples"].items()} == {
        "buffer.ptu": "buffer", "water_irf.ptu": "irf", "Rh110_ref.ptu": "reference"
    }
    assert recipe.setup["detectors"]["G|G"]["g_factor"] == pytest.approx(
        hub.context.channel_settings["detectors"]["G|G"]["g_factor"]
    )
    assert recipe.fit_window() == _mle_window(hub)
    assert recipe.selection == hub.children["selection"].model.export_settings()
    assert recipe.calibration_report_id
    assert Recipe.from_payload(json.loads(json.dumps(recipe.to_payload()))) == recipe
    # the hub's settings keep it (the step shows what it would run)
    hub.select("more")
    first["drv"].draw(2)
    state = json.loads(json.dumps(hub.export_settings()))
    assert Recipe.from_payload(state["children"]["more"]["recipe"]) == recipe
    again = create_app()
    try:
        again.restore_settings(state)
        assert again.ensure_child("more").recipe == recipe
    finally:
        again.close()
    rows = recipe.detail_rows()
    assert [r["part"] for r in rows][:4] == ["Setup", "Calibration", "Report", "Search"]
    assert all(len(r["value"]) < 30 for r in rows)  # short cells, details in the tips


def test_two_more_samples_equal_the_pipeline_run_by_hand(first):
    from chisurf.plugins.burst.burst_analysis.api import BurstWorkflow
    from chisurf.plugins.burst.burst_analysis.calibration_report import read_report
    from chisurf.plugins.burst.burst_analysis.more_samples import read_recipe
    from chisurf.plugins.burst.burst_analysis.tests.test_emtk_native_hub import settle
    from chisurf.plugins.burst.burst_mle_analysis.gui.fit_view import burst_lifetimes

    hub, drv, more = first["hub"], first["drv"], first["more"]
    recipe = hub.capture_recipe()
    rows = BurstWorkflow.offline().process_more(more, recipe.to_payload())
    assert [r["status"] for r in rows] == ["done", "done"], [r["error"] for r in rows]
    for row in rows:
        assert row["bursts"] > 100 and 2.5 < row["tau"]["G|G"] < 3.5  # the simulated 3 ns
        assert row["E"] is None  # one colour
        stored = read_recipe(row["container"])
        assert stored["recipe_id"] == recipe.recipe_id == row["recipe_id"]
        assert stored["calibration_report_id"] == recipe.calibration_report_id
        assert stored["runs"] == [row["run"]] and Path(row["run"]).parent == Path(row["container"])
        assert read_report(row["container"]) == recipe.workflow["calibration_report"]
    assert rows[0]["bursts"] != rows[1]["bursts"]  # two measurements, not one twice

    # by hand: the second sample as the measurement of step 1, the same steps, the same settings
    tuned = copy.deepcopy(hub.children["mle"].model.session.det_settings)
    data = hub.children["data"]
    data.source.remove_paths([first["files"]["measurement"]])
    data.source.add_paths([more[0]], "measurement")
    drv.draw(2)
    hub.select("selection")
    drv.draw(2)
    drv.click(hub.item_rects["next"])
    settle(drv)
    hub.select("mle")
    settle(drv)
    mle = hub.children["mle"]
    mle.model.session.det_settings.update(copy.deepcopy(tuned))  # the fit window as tuned
    mle.fit_bursts(force=True)
    settle(drv)
    by_hand = burst_lifetimes(mle.model.burst_results)["G|G"]
    assert mle.model.n_bursts == rows[0]["bursts"]
    assert float(np.mean(by_hand)) == pytest.approx(rows[0]["tau"]["G|G"], rel=1e-12)
    # back to the first measurement for the tests after this one
    data.source.remove_paths([more[0]])
    data.source.add_paths([first["files"]["measurement"]], "measurement")


def test_a_failing_sample_does_not_stop_the_others(first, tmp_path):
    from chisurf.plugins.burst.burst_analysis.more_samples import process_more

    broken = tmp_path / "broken.ptu"
    broken.write_bytes(b"not a photon stream")
    recipe = first["hub"].capture_recipe()
    # two at once (threads), the broken one first
    rows = process_more(recipe, [broken, first["more"][1]], workers=2)
    status = {r["name"]: r for r in rows}
    assert status["broken"]["status"] == "failed" and status["broken"]["error"]
    assert status["sample_dsDNA_3"]["status"] == "done", status["sample_dsDNA_3"]["error"]


def test_the_step_takes_dropped_samples_and_runs_them(first):
    from chisurf.plugins.burst.burst_analysis.gui.native import receive_photons
    from chisurf.plugins.burst.burst_analysis.tests.test_emtk_native_hub import settle

    hub, drv = first["hub"], first["drv"]
    assert hub.panel_enabled("more")
    hub.select("more")
    drv.draw(2)
    step = hub.children["more"]
    # Simple: the drop target, the table and Run; Advanced: the recipe and Re-run too
    assert len(step.spec["sections"]) == 1
    assert [m["label"] for m in step.spec["sections"][0]["options"]["context_menu"]] == ["Remove"]
    hub.set_advanced(True)
    assert len(step.spec["sections"]) == 2
    assert [m["label"] for m in step.spec["sections"][0]["options"]["context_menu"]] == ["Re-run", "Remove"]
    hub.set_advanced(False)
    # a drop while step 4 is open (the workspace hands photons over) is a sample, not step 1's data
    measurements = list(hub.context.raw_files)
    receive_photons(hub, {"files": [str(p) for p in first["more"]]})
    assert hub.selected == "more" and hub.context.raw_files == measurements
    assert [r["status"] for r in step.sample_rows()] == ["queued", "queued"]
    assert step.run_step()  # Next runs it
    seen_running = False
    end = time.monotonic() + 240
    while step.running and time.monotonic() < end:
        seen_running = seen_running or any(r["status"] == "running" for r in step.sample_rows())
        drv.draw(1)
        time.sleep(0.05)
    settle(drv)
    assert seen_running
    rows = step.sample_rows()
    assert [r["status"] for r in rows] == ["done", "done"], [r["tip"] for r in rows]
    assert all(r["bursts"] and r["tau"] for r in rows)
    assert "recipe" in rows[0]["tip"] and "mean τ G|G" in rows[0]["tip"]
    assert hub.step_done("more") and hub.badge("more") == "✓ (2)"
    # every control of the step says what it does, in both modes
    import sys

    sys.modules.pop("test", None)
    from test.gui.emtk_port_parity import emtk_inventory

    for advanced in (False, True):
        hub.set_advanced(advanced)
        assert emtk_inventory(step)["controls_without_tooltip"] == [], advanced
    hub.set_advanced(False)


def test_a_parallel_batch_equals_the_serial_one_and_stays_within_the_cores(first, tmp_path):
    """Several samples in flight (their stages in one shared pool) give exactly what one after
    the other gives; the batch never runs more worker processes than the core budget, and that
    budget never exceeds the physical cores."""
    import shutil
    import threading

    import psutil

    from chisurf.plugins.burst.burst_analysis import more_samples as ms

    recipe = first["hub"].capture_recipe()
    paths = []
    for index, source in enumerate(first["more"] * 2):  # four samples, two of each measurement
        target = tmp_path / f"s{index}_{Path(source).name}"
        shutil.copy(source, target)
        paths.append(target)
    budget = ms.core_budget()
    assert 1 <= budget <= ms.physical_cores()
    serial = ms.process_more(recipe, paths, workers=1, register=False)

    me = psutil.Process()
    before = {c.pid for c in me.children(recursive=True)}
    seen: set = set()
    stop = threading.Event()

    def watch() -> None:
        while not stop.is_set():
            seen.update(c.pid for c in me.children(recursive=True))
            time.sleep(0.02)

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        parallel = ms.process_more(recipe, paths, register=False)
    finally:
        stop.set()
        watcher.join()
    pool = ms.batch_pool(budget)
    assert pool._max_workers == budget
    pool_pids = set(getattr(pool, "_processes", {}) or {})
    assert len(pool_pids) <= budget
    # nothing but the one pool's processes appeared for the batch (no pool per sample or stage)
    assert seen - before <= pool_pids, (seen - before, pool_pids)
    key = lambda rows: [(Path(r["path"]).name, r["status"], r["bursts"], r["tau"]) for r in rows]  # noqa: E731
    assert key(parallel) == key(serial)
    assert all(r["status"] == "done" for r in parallel)
    assert ms.concurrent_samples(paths, budget) == min(len(paths), budget)


def test_the_batch_admits_samples_by_memory():
    from chisurf.plugins.burst.burst_analysis import more_samples as ms

    one = ms.MEMORY_PER_SAMPLE
    # no room for two: one at a time, but always one
    assert ms.concurrent_samples(["a", "b", "c"], budget=7, memory=one) == 1
    assert ms.concurrent_samples(["a", "b", "c"], budget=7, memory=10 * one) == 3
    assert ms.concurrent_samples(["a", "b", "c"], budget=2, memory=10 * one) == 2


def test_the_calibration_is_computed_once_per_batch_not_per_sample(first, tmp_path, monkeypatch):
    """Spies on every calibration-related computation: a batch of three samples makes exactly the
    calls a batch of one makes (the buffer read once, the dye lookups and the calibration files
    once, no IRF derived or shift calibrated per sample), and its results are unchanged."""
    import collections
    import shutil

    from chisurf.core.fluorescence import dyes
    from chisurf.plugins.burst.burst_analysis import more_samples as ms
    from chisurf.plugins.burst.burst_analysis import workflow_context
    from chisurf.plugins.burst.burst_mle_analysis import engine

    calls: collections.Counter = collections.Counter()

    def spy(owner, name):
        original = getattr(owner, name)

        def counted(*args, **kwargs):
            calls[name] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(owner, name, counted)

    for name in ("pattern_histogram", "irf_pattern", "calibrate_shift", "recalibrate_shifts",
                 "extract_irf_background", "set_pattern_files", "auto_extract"):
        spy(engine.MleSession, name)
    spy(dyes, "get_dye")
    spy(workflow_context.BurstWorkflowContext, "references")
    spy(ms, "prepare_calibration")

    recipe = first["hub"].capture_recipe()
    paths = []
    for index in range(3):
        target = tmp_path / f"c{index}_{Path(first['more'][index % 2]).name}"
        shutil.copy(first["more"][index % 2], target)
        paths.append(target)
    reference = ms.process_more(recipe, paths[:1], workers=1, register=False)  # fit fanned out here
    once = dict(calls)
    calls.clear()
    rows = ms.process_more(recipe, paths, workers=1, register=False)
    # three samples cost no calibration call more than one (a lookup the window makes meanwhile
    # may add to the first count, never to the second)
    assert all(calls[name] <= once.get(name, 0) for name in calls), (once, dict(calls))
    assert calls["prepare_calibration"] == 1 and calls["references"] == 1
    assert once["prepare_calibration"] == 1 and once["references"] == 1
    assert once["pattern_histogram"] == once["set_pattern_files"] == 1  # the buffer, read once
    for name in ("irf_pattern", "calibrate_shift", "recalibrate_shifts", "extract_irf_background",
                 "auto_extract"):
        assert once.get(name, 0) == 0, name
    assert all(r["status"] == "done" for r in rows)
    assert (rows[0]["bursts"], rows[0]["tau"]) == (reference[0]["bursts"], reference[0]["tau"])
    # the arrays every sample gets are the batch's, read-only
    calibration = ms.prepare_calibration(recipe)
    assert all(not a.flags.writeable for a in (*calibration.irf.values(), *calibration.buffer.values()))
    handle, block = ms.publish_calibration(calibration)
    try:
        assert ms.calibration_of(handle) is calibration
        ms._SHARED.clear()
        again = ms.calibration_of(handle)  # as a worker reads it: once, from the shared block
        assert again.recipe_id == calibration.recipe_id and again.key == calibration.key
    finally:
        block.close()
        block.unlink()
