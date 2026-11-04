"""2CDE takes its burst run from the Datasets workspace: a click on the Input section's row runs it,
and its table is a companion of that run in the container. No input dialog, no drop hook."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from chisurf.plugins.burst.burst_2cde.gui.app import create_app
from test.gui.burst_workspace import (
    burst_run_in_workspace,
    draw,
    no_input_dialog,
    pick_row,
    restore_workspace,
    save_png,
    settle,
)

SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    with restore_workspace():
        yield


def test_a_burst_run_picked_in_the_input_section_runs_and_registers_its_table(
    tmp_path, monkeypatch
):
    from chisurf.core.api import dataset_objects

    run = burst_run_in_workspace(tmp_path)
    no_input_dialog(monkeypatch)
    app = create_app()
    app.model.donor_channels_text, app.model.acceptor_channels_text = "0", "1"
    try:
        assert not hasattr(app, "files_dropped")
        strings = draw(app).strings
        assert "runBursts#1" in strings and "m000.spc" not in strings  # burst runs only
        pick_row(app, "runBursts#1")
        assert app.model.folder == run.address
        assert app.source_uid == run.unique_identifier
        settle(app)
        assert app.model.df is not None, app.model.status_text
        # the 2CDE table is a companion of the run in its container, read with the run by ndX's
        # reader -- not a workspace row of its own
        assert not [d for d in dataset_objects() if getattr(d, "result_of", "") == run.unique_identifier]
        from chisurf.plugins.burst.burst_2cde.core.computation import COLUMN_FRET_2CDE
        from test.gui.burst_workspace import run_columns

        assert COLUMN_FRET_2CDE in run_columns(run.address)
        save_png(app, SHOTS / "burst_2cde_workspace.png")
    finally:
        app.close()


def test_old_result_is_flagged_and_new_result_records_stream_version(tmp_path):
    from chisurf.core.fio.analysis_path import split_container_path
    from chisurf.core.fio.fluorescence.burst_container import burst_table_name
    from chisurf.core.fio.pto import Measurement
    from chisurf.plugins.burst.burst_2cde.backend.services import stale_results
    from chisurf.plugins.burst.burst_2cde.core.computation import STREAM_ALGORITHM_VERSION

    run = burst_run_in_workspace(tmp_path)
    container, run_name = split_container_path(run.address)
    with Measurement.open(container, writable=True) as measurement:
        name = burst_table_name(measurement, run_name)
        parent = measurement._f.find(name)
        measurement.put_table(
            "old 2cde", {"FRET-2CDE": [1.0]}, artifact_kind="burst_table",
            operation_type="burst_2cde", row_grain="burst", parameters={"variant": "fret"},
            derived_from=parent,
        )
        measurement.put_table(
            "new 2cde", {"ALEX-2CDE": [1.0]}, artifact_kind="burst_table",
            operation_type="burst_2cde", row_grain="burst",
            parameters={"variant": "alex", "stream_algorithm_version": STREAM_ALGORITHM_VERSION},
            derived_from=parent,
        )
    assert stale_results(run.address) == ["fret"]
    app = create_app()
    try:
        assert app.controller.adopt_folder(run.address)
        strings = draw(app).strings
        assert any("unrecorded excitation streams" in text for text in strings)
        save_png(app, SHOTS / "burst_2cde_stale.png")
    finally:
        app.close()
