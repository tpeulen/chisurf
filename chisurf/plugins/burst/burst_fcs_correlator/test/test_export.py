"""Successful native runs preserve real measurements; failed publication preserves prior bytes."""

import json
import shutil
from concurrent.futures import CancelledError
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import numeric_column
from chisurf.core.fio.fluorescence.burst_companion import read_companion
from chisurf.core.fio.pto import Measurement
from chisurf.plugins.burst.burst_fcs_correlator.core.export import write_fcs_results_container
from chisurf.plugins.burst.burst_fcs_correlator.gui.app import create_app

REPO = Path(__file__).resolve().parents[5]


@pytest.fixture
def source(tmp_path):
    raw = tmp_path / "BH_SPC132.spc"
    shutil.copy2(REPO / "test/data/tttr/BH/132/BH_SPC132.spc", raw)
    return raw


def rows(source, value=0.5):
    return [
        {
            "First File": str(source),
            "Burst Folder": str(source.parent),
            "Burst Index": 2,
            "pair_name": "green_ACF",
            "td_mean_ms": value,
            "td_peak_ms": value,
        }
    ]


def test_native_run_writes_the_frozen_real_grid_and_indexed_container(source):
    app = create_app()
    ctrl = app.controller
    from .driving import make_input_container

    source, container = make_input_container(source.parent, [(0, 5000), (6000, 11000), (12000, 17000)])
    ctrl.add_files([container])
    ctrl.apply_pairs('[{"pair_name":"green_ACF","chs_a":[0,1],"chs_b":[0,1]}]')
    ctrl._model.padding_ms = 0
    ctrl._model.n_bins = 3
    ctrl._model.n_casc = 12
    try:
        ctrl._on_run()
        ctrl._future.result(timeout=30)
        ctrl.poll()
        assert ctrl.status == "Computed 3 burst correlation curves."
        assert len(ctrl.output_paths) == 1 and ctrl.output_paths[0].suffix == ".pto"
        selected = ctrl._curves[0]
        assert selected["td_grid"] == [] and selected["p"] == []
        series = ctrl._model.dist_plot_series()
        assert series[0]["x"] == [selected["td_mean"]]
        assert series[0]["y"] == [1.0] and series[0]["marker"]
        assert series[0]["name"] == "Simple fit"
        facts = json.loads(
            (Path(__file__).with_name("data") / "burst-facts.json").read_text()
        )
        expected = next(iter(facts["td4_files"].values()))
        assert not (source.parent / "td4").exists()  # a companion is an explicit export
        # The frozen real grid (what the legacy writer put on disk) is reproduced
        # by the explicit export, not written beside the container.
        frozen = source.parent / "frozen" / "BH_SPC132.td4"
        frozen.parent.mkdir()
        frozen.write_text(expected)
        columns, full = read_companion(frozen)
        with Measurement.open(source.with_suffix(".pto")) as measurement:
            table = measurement.get_store("burst fcs")
            np.testing.assert_array_equal(numeric_column(table, "Burst Index"), [0, 1, 2])
            np.testing.assert_allclose(numeric_column(table, columns[0]), full[:, 0], atol=5e-7)
            uid = measurement._resolve("burst fcs")
            assert measurement.tag(uid, "_mmfdb_edge.source_row_column") == "Burst Index"
            assert measurement.tag(uid, "_mmfdb_artifact.row_grain") == "burst"
            assert measurement.column_units(table, columns[0]) == "milliseconds"
            uid = measurement._resolve("burst fcs")
            assert measurement.tag(uid, "_mmfdb_operation.operation_type") == "burst_correlation"
    finally:
        app.close()


def test_cancellation_during_staging_preserves_existing_outputs(source):
    paths = write_fcs_results_container(rows(source), {(str(source.parent), source.stem): 4})
    before = {p: p.read_bytes() for p in paths}
    count = 0

    def cancel():
        nonlocal count
        count += 1
        if count == 2:
            raise CancelledError()

    with pytest.raises(CancelledError):
        write_fcs_results_container(
            rows(source, 1), {(str(source.parent), source.stem): 4}, cancel_check=cancel
        )
    assert {p: p.read_bytes() for p in paths} == before
    assert not list(source.parent.glob(".burst-fcs-*"))


def test_failed_publication_rolls_back_exact_existing_bytes_and_modes(source, monkeypatch):
    paths = write_fcs_results_container(rows(source), {(str(source.parent), source.stem): 4})
    paths[0].chmod(0o640)
    before = {p: (p.read_bytes(), p.stat().st_mode) for p in paths}
    replace = Path.replace
    failed = False

    def fail_once(self, target):
        nonlocal failed
        if Path(target).suffix == ".pto" and not failed:
            failed = True
            raise OSError("publication failed")
        return replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_once)
    with pytest.raises(OSError, match="publication failed"):
        write_fcs_results_container(rows(source, 1), {(str(source.parent), source.stem): 4})
    assert {p: (p.read_bytes(), p.stat().st_mode) for p in paths} == before


def test_concurrent_output_change_is_preserved_and_rejected(source):
    paths = write_fcs_results_container(rows(source), {(str(source.parent), source.stem): 4})
    original_pto = paths[0].read_bytes()
    count = 0

    def external_write():
        nonlocal count
        count += 1
        if count == 2:
            paths[0].write_text("external analysis")

    with pytest.raises(RuntimeError, match="changed while"):
        write_fcs_results_container(
            rows(source, 1), {(str(source.parent), source.stem): 4}, cancel_check=external_write
        )
    assert paths[0].read_text() == "external analysis"
    assert original_pto != b"external analysis"


def test_two_analysis_folders_of_one_measurement_publish_together(source):
    """The shared measurement container is staged once while both positional grids survive."""
    first = source.parent / "analysis-a"
    second = source.parent / "analysis-b"
    a, b = rows(source, 0.5), rows(source, 0.7)
    a[0]["Burst Folder"], b[0]["Burst Folder"] = str(first), str(second)
    counts = {(str(first), source.stem): 4, (str(second), source.stem): 5}
    paths = write_fcs_results_container(a + b, counts)
    assert len(paths) == 1 and paths[0].suffix == ".pto"
    assert not (first / "td4").exists() and not (second / "td4").exists()
    # The canonical last-run table remains the latest analysis, as before.
    with Measurement.open(source.with_suffix(".pto")) as measurement:
        table = measurement.get_store("burst fcs")
        assert numeric_column(table, "td_mean__green_ACF")[0] == pytest.approx(0.7)


def test_publication_uses_worker_and_gui_frames_remain_responsive_on_cancel(source, monkeypatch):
    """Actual staging IO cannot block the GUI; cancellation before publish leaves no artifacts."""
    import threading
    import time

    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_fcs_correlator.core import export

    app = create_app()
    ctrl = app.controller
    from .driving import make_input_container

    _raw, container = make_input_container(source.parent, [(0, 5000), (6000, 11000)])
    ctrl.add_files([container])
    ctrl._model.padding_ms = 0
    entered, release = threading.Event(), threading.Event()
    worker_ids = []
    original = export.write_fcs_container

    def slow_actual_container(*args, **kwargs):
        worker_ids.append(threading.get_ident())
        entered.set()
        assert release.wait(timeout=5)
        return original(*args, **kwargs)

    monkeypatch.setattr(export, "write_fcs_container", slow_actual_container)
    try:
        ctrl._on_run()
        assert entered.wait(timeout=5)
        assert worker_ids[0] != threading.get_ident()
        # This is the real GUI frame/poll path while the writer is blocked.
        driver = Driver(app, size=(800, 600))
        started = time.monotonic()
        driver.draw(3)
        assert time.monotonic() - started < 2
        ctrl.stop()
        release.set()
        with pytest.raises(CancelledError):
            ctrl._future.result(timeout=10)
        ctrl.poll()
        assert ctrl.status == "Burst FCS cancelled." and not ctrl.running
        assert not source.with_suffix(".pto").exists()
        assert not (source.parent / "td4").exists()
    finally:
        release.set()
        app.close()


def test_stop_after_completed_publication_keeps_successful_output(source):
    """A queued Stop click arriving after the finished worker cannot relabel committed results cancelled."""
    app = create_app()
    ctrl = app.controller
    from .driving import make_input_container

    source, container = make_input_container(source.parent, [(0, 5000)])
    ctrl.add_files([container])
    try:
        ctrl._on_run()
        ctrl._future.result(timeout=30)
        ctrl.stop()
        assert ctrl.status == "Computed 1 burst correlation curves."
        assert source.with_suffix(".pto").exists()
        assert not ctrl._cancel.is_set()
    finally:
        app.close()


def test_cancellation_after_first_publish_rolls_back_previous_outputs(source):
    """Cancellation in the bounded publication phase restores already replaced artifacts."""
    paths = write_fcs_results_container(rows(source), {(str(source.parent), source.stem): 4})
    before = {p: p.read_bytes() for p in paths}
    count = 0

    def cancel_after_container():
        nonlocal count
        count += 1
        if count == 4:
            raise CancelledError()

    with pytest.raises(CancelledError):
        write_fcs_results_container(
            rows(source, 1),
            {(str(source.parent), source.stem): 4},
            cancel_check=cancel_after_container,
        )
    assert {p: p.read_bytes() for p in paths} == before


def test_native_maxent_preset_fields_are_actual_effective_grid_and_auto_is_explicit(
    source, tmp_path
):
    """The GUI exposes the legacy fixed grid while zero remains an explicit automatic API request."""
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_fcs_correlator.core.algorithms import BurstFcsSettings

    app = create_app()
    ctrl = app.controller
    from .driving import make_input_container

    source, container = make_input_container(source.parent, [(0, 5000)])
    ctrl.add_files([container])
    driver = Driver(app, size=(1200, 850))
    try:
        app.select_tab("Settings")
        driver.draw(3)
        driver.click("fit_mode.2")
        assert ctrl._model.fit_mode == "maxent"
        settings = ctrl._model.to_settings()
        assert settings.maxent_td_min == 0.001 and settings.maxent_td_max == 20.0
        driver.click("run")
        ctrl._future.result(timeout=30)
        driver.draw(3)
        assert ctrl.status == "Computed 1 burst correlation curves."
        grid = ctrl._curves[0]["td_grid"]
        assert grid[0] == pytest.approx(0.001) and grid[-1] == pytest.approx(20)
        path = tmp_path / "maxent-settings.json"
        ctrl.save_settings(path)
        saved = json.loads(path.read_text())
        assert saved["maxent_td_min"] == 0.001 and saved["maxent_td_max"] == 20
        assert BurstFcsSettings().maxent_td_min is None
        assert BurstFcsSettings().maxent_td_max is None
        ctrl._model.maxent_td_min = ctrl._model.maxent_td_max = 0
        assert ctrl._model.to_settings().maxent_td_min is None
        assert ctrl._model.to_settings().maxent_td_max is None
    finally:
        app.close()
