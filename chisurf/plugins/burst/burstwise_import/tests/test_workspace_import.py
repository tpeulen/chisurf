"""A legacy burstwise folder handed over by the drop is imported into the project: its runs
become children of their photon streams in the Datasets workspace, the containers live in those
streams' analysis containers, and nothing is written beside the legacy folder."""

from __future__ import annotations

import time
from pathlib import Path

from chisurf.plugins.burst.burstwise_import.gui.app import (
    adopt_into_project,
    create_app,
    receive_folder,
)
from test.gui.burst_workspace import restore_workspace


def _converted(app, timeout=60.0):
    app.convert()
    end = time.monotonic() + timeout
    while app.future is not None:
        assert time.monotonic() < end, "the conversion did not finish"
        time.sleep(0.05)
        app.poll()


def test_a_dropped_legacy_folder_is_scanned_and_converted_without_writing_beside_it():
    from chisurf.core.api import dataset_objects
    from chisurf.plugins.burst.burstwise_import.demo import make_demo

    folder = make_demo()
    before = {p for p in folder.parent.rglob("*.pto")}
    app = create_app()
    try:
        with restore_workspace():
            receive_folder(app, {"folder": str(folder)})  # what the shell's drop hands over
            assert app.model.inventory
            app.model.resolver_mode = "beside"
            _converted(app)
            # The shipped sample has no raw photons: nothing is converted, which the log says,
            # and the workspace gains no rows.
            assert app.model.report is not None and not app.model.report.containers
            assert "0 burst run(s) added to the Datasets workspace." in app.model.messages
            assert not [d for d in dataset_objects() if getattr(d, "data_kind", "") == "bursts"]
        assert {p for p in folder.parent.rglob("*.pto")} == before  # nothing beside the folder
    finally:
        app.close()


def test_the_window_offers_no_input_dialog_or_drop_hook():
    app = create_app()
    try:
        assert not hasattr(app, "browse") and not hasattr(app, "on_paths_dropped")
    finally:
        app.close()


def test_a_container_with_its_photons_becomes_the_runs_parent(tmp_path):
    """With the photon file found, it becomes the photon dataset and the runs its children."""
    from chisurf.core.api import dataset_objects
    from chisurf.core.fio.fluorescence.burst import read_bur_file
    from chisurf.core.fio.fluorescence.burst_container import deinterleave_bursts
    from chisurf.core.project.analysis import container_dir
    from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    measurement = build(tmp_path / "measurement")
    photons = measurement.parent / "m000.spc"
    bur = sorted((measurement / "bi4_bur").glob("*.bur"))[0]
    staged = write_container(
        photons,
        deinterleave_bursts(read_bur_file(bur)),
        parameters={"run": 1},
        out_dir=tmp_path / "staging",
        run="runBursts#1",
        raw_data="sidecar",
    )
    with restore_workspace():
        assert adopt_into_project([staged]) == 1
        datasets = list(dataset_objects())
        (stream,) = [d for d in datasets if getattr(d, "data_kind", "") == "photons"]
        (run,) = [d for d in datasets if getattr(d, "data_kind", "") == "bursts"]
        assert run.result_of == stream.unique_identifier
        assert list(container_dir(stream.unique_identifier).glob("*.pto"))
        assert not Path(staged).exists()
