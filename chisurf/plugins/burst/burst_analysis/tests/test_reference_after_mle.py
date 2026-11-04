"""The owner's order: the bursts searched, Burst MLE open, the reference dye added afterwards.

On DNA13bp_3 (RVZMT150) Data Selection computed G|G 1.436 from Rh110_thick_1 and wrote it into
the setup, but Burst MLE's session kept G 1.0 for good: the hand-over to the step on screen was
deferred while its preparation ran (``_resync``) and only ever taken up for a step *not* on
screen. The shifts stayed calibrated with G 1 (reference fit chi2_r 309 instead of 1.4).

Here the same order on the simulated session of :mod:`..demo` (a G|G detector, G 1.15, Rh110 at
4 ns): the G reaches the MLE session, the shifts are calibrated again with it and the reference
fit is about 1. Data Selection's proposals are off so the reference really comes late, as the
owner's did; and every product stays in the one container of the measurement's dataset.
"""

from __future__ import annotations

import copy
import shutil
import time

import pytest

from chisurf.plugins.burst.burst_analysis import demo
from chisurf.plugins.emtk_test_input import Driver


@pytest.fixture
def session_files(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "settings").mkdir()
    (tmp_path / "mmfdb").mkdir()
    from chisurf.core.fluorescence import dyes

    monkeypatch.setattr(dyes, "_entries_from_database", lambda: None)
    dyes.reference_dyes(refresh=True)
    files = demo.make_demo(tmp_path / "demo")
    from chisurf.plugins.burst.burst_selection.gui.model import save_setup

    save_setup("demo", copy.deepcopy(demo.SETUP))
    return files


def _wait(drv, until, what, timeout=300.0):
    end = time.monotonic() + timeout
    while not until():
        assert time.monotonic() < end, what
        drv.draw(1)
        time.sleep(0.05)
    drv.draw(2)


def test_a_reference_added_after_burst_mle_opened_brings_its_g_and_new_shifts(session_files):
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app, receive_photons

    hub = create_app()
    try:
        drv = Driver(hub, (1200, 800))
        hub.set_advanced(False)
        drv.draw(3)
        hub.children["setup"].select_setup("demo")
        drv.draw(2)
        hub.select("data")
        drv.draw(2)
        data = hub.children["data"]
        data.source.propose = False  # the reference arrives later, by hand, as the owner's did
        data.source.auto_import = False
        receive_photons(hub, {"files": [str(session_files["measurement"])], "datasets": []})
        drv.draw(2)
        hub.select("selection")
        drv.draw(2)
        selection = hub.children["selection"]
        selection.run()
        _wait(drv, lambda: not selection.running and hub.context.bur_files, "the burst search")
        hub.select("mle")
        mle = hub.children["mle"]
        _wait(drv, lambda: not mle.pending and mle.model.session.irf_np.get("G|G") is not None, "MLE ready")
        # the step's jobs run on a snapshot whose session comes back: always read it anew
        assert mle.model.session.detectors["G|G"]["g_factor"] == 1.0
        assert "G|G" not in mle.model.session.shift_calibration  # no reference yet

        # the reference dye, added to Data Selection while Burst MLE is open
        receive_photons(hub, {"files": [str(session_files["reference"])], "datasets": []})
        assert hub.context.references()["reference"]["G|G"]
        _wait(drv, lambda: (data.source.calibration or {}).get("colours"), "Data Selection's calibration")
        g = hub.setup_model.data["detectors"]["G|G"]["g_factor"]
        assert g == pytest.approx(demo.TRUTH["g_factor"], rel=0.02)
        hub.select("mle")  # the owner's next click
        _wait(
            drv,
            lambda: not mle.pending and mle.model.session.detectors["G|G"]["g_factor"] == pytest.approx(g)
            and "G|G" in mle.model.session.shift_calibration,
            "the G and the shift calibration in Burst MLE",
        )
        shift = mle.model.session.shift_calibration["G|G"]
        assert shift["dye"] == "Rh110"
        assert shift["fit_g"] == pytest.approx(g)  # calibrated with the G Data Selection computed
        assert shift["fit_chi2r"] < 1.6, shift["fit_text"]
        assert abs(shift["fit_g_fitted"] - g) < 0.03
        assert not hub.errors, hub.errors
    finally:
        hub.close()


def test_a_measurement_from_a_dataset_has_one_container(session_files, tmp_path):
    """The dataset a file came from is recorded before the file is added: the workflow makes its
    container at once, and in the dataset's folder -- never a second one under ``_``."""
    from chisurf.core.project.analysis import container_dir
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    hub = create_app()
    try:
        drv = Driver(hub, (1200, 800))
        drv.draw(3)
        hub.children["setup"].select_setup("demo")
        hub.select("data")
        drv.draw(2)
        data = hub.children["data"]
        data.source.auto_import = False
        data.source.propose = False
        measurement = tmp_path / "copy" / "sample.ptu"
        measurement.parent.mkdir()
        shutil.copy(session_files["measurement"], measurement)
        data.take_photons([measurement], ["dataset-uid-1"])
        end = time.monotonic() + 30
        while time.monotonic() < end and not list(container_dir("dataset-uid-1").glob("*.pto")):
            time.sleep(0.1)
        assert [p.name for p in container_dir("dataset-uid-1").glob("*.pto")] == ["sample.pto"]
        assert not list(container_dir("").glob("sample.pto"))
    finally:
        hub.close()


def test_one_pipeline_leaves_one_container_with_one_linked_run(session_files):
    """Setup, Data Selection (the references beside the measurement proposed), >>: one container
    for the measurement's dataset, and in it the run of the search with everything the pipeline
    made of it -- the bursts, the MLE lifetimes and the calibration report -- linked to the run's
    burst table; ndX opens the run with the lifetimes merged."""
    from ndxplorer.io.pto_reader import read_run

    from chisurf.core.datastore import column_names
    from chisurf.core.fio.analysis_path import split_container_path
    from chisurf.core.fio.pto import Measurement
    from chisurf.core.project.analysis import container_dir

    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    hub = create_app()
    try:
        drv = Driver(hub, (1200, 800))
        hub.set_advanced(False)
        drv.draw(3)
        hub.children["setup"].select_setup("demo")
        hub.select("data")
        drv.draw(2)
        data = hub.children["data"]
        data.source.auto_import = False
        data.take_photons([session_files["measurement"]], ["dataset-one"])
        assert hub.context.references()["reference"]["G|G"]  # Rh110 proposed from beside it
        _wait(drv, lambda: (data.source.calibration or {}).get("colours"), "Data Selection's calibration")
        drv.click(hub.item_rects["fast_forward"])
        mle = None
        end = time.monotonic() + 300
        while time.monotonic() < end and not (hub.step_done("mle") and not hub.children["mle"].pending):
            drv.draw(1)
            time.sleep(0.05)
        mle = hub.children["mle"]
        assert hub.step_done("mle"), (hub.status, mle.model.status_text)
        _wait(drv, lambda: "Written into" in mle.model.status_text, "the lifetimes written", 60)
        time.sleep(1.0)  # the report is written on a thread
        drv.draw(3)

        containers = sorted(container_dir("dataset-one").glob("*.pto"))
        assert [p.name for p in containers] == ["sample_dsDNA.pto"]
        assert not list(container_dir("").glob("sample_dsDNA.pto"))
        run = split_container_path(hub.context.burst_folder)[1]
        with Measurement.open(containers[0], writable=False) as m:
            names = {o.uid: str(o.name) for o in m._f.objects()}
            bursts = next(n for n in names.values() if n.startswith(f"{run}/") and n.endswith(".bur"))
            members = {n for n in names.values() if n.startswith(f"{run}/")}
            assert f"{run}/mle G|G" in members and f"{run}/burst_calibration" in members, sorted(names.values())
            for obj in m._f.objects():
                if str(obj.name) in (f"{run}/mle G|G", f"{run}/burst_calibration"):
                    assert [names[u] for u in m.parents(obj.uid)] == [bursts]
        store, _ = read_run(containers[0], table=bursts)
        assert "Tau (G|G)" in column_names(store)
        assert not hub.errors, hub.errors
    finally:
        hub.close()
