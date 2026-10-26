"""A recording lands in the project: a photons row with its burst run, its photons inside the .cs.pto.

The Record tool measures the simulated MultiHarp in a shell whose session has its temporary
project; at stop the run must show in Datasets at once (photons row, burst run as its child), its
photons must be embedded in the ``.cs.pto`` -- not only a path -- and a saved project must reopen
with the row and its photons readable after the original recording file is gone.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from emtk.testing import Driver

from chisurf.plugins.core.acq.gui.record_app import RecordModel
from test.native_emtk.test_emtk_shell_fits import (  # noqa: F401  (the fixture and the helpers)
    DATASETS_KEY,
    SHOTS,
    _settle,
    shell,
)


@pytest.fixture(autouse=True)
def _temp_dir(tmp_path, monkeypatch):
    root = tmp_path / "temp-projects"
    monkeypatch.setenv("CHISURF_PROJECT_TEMP_DIR", str(root))
    return root


def _rows(shell, kind):  # noqa: F811
    return [r for r in shell.data.datasets.datasets if r.get("kind") == kind]


def test_a_recording_is_embedded_in_the_project_and_reopens(shell, tmp_path):  # noqa: F811
    from chisurf.core.fio.staging import open_tttr

    driver = Driver(shell, (1400, 900))
    driver.frame(4)
    _settle(
        driver, lambda: shell.project.temporary and not shell.project.busy, "the temporary project"
    )
    temp = Path(shell.project.document.path)

    model = RecordModel(output_dir=tmp_path / "unused", realtime=False)
    model.load_example()
    model.duration_s = 4.0
    model.run_name = "first_run"
    assert model.recording_store == "embed"  # a fresh recording is stored in the project
    assert model.start()
    end = time.monotonic() + 120
    while model.running:
        assert time.monotonic() < end, "the run did not end"
        driver.frame(1)
        time.sleep(0.02)
    model.poll(force=True)  # registers the run
    ptu = model.saved_path
    assert ptu.parent.name.endswith(" recordings") and ptu.parent.parent == temp.parent

    def listed():
        photons = [r for r in _rows(shell, "photons") if r.get("name") == ptu.name]
        if not photons:
            return False
        uid = str(photons[0].get("uid"))
        return any(str(r.get("parent")) == uid for r in _rows(shell, "bursts"))

    _settle(driver, listed, "the photons row and its burst run")
    row = next(r for r in _rows(shell, "photons") if r.get("name") == ptu.name)
    assert row["embedded"] is True and row["experiment"] == "Single photon counting"
    _settle(driver, lambda: not shell.project.busy, "the autosave")
    assert temp.stat().st_size >= ptu.stat().st_size  # the photons are inside the temporary project
    shell.docks.focus(DATASETS_KEY)
    driver.frame(4)
    driver.screenshot(SHOTS / "record_in_datasets.png")

    # save it somewhere, lose the original file, reopen: the photons come from the project itself
    project = shell.project
    project.save()
    driver.frame(2)
    saved = tmp_path / "kept.cs.pto"
    project.choose_file(saved)
    _settle(driver, lambda: not project.busy and saved.is_file(), "the save")
    photons = int(model.session.result.photons)
    ptu.unlink()
    assert project.open_path(saved)
    _settle(
        driver, lambda: not project.busy and bool(_rows(shell, "photons")), "the reopened project"
    )
    reopened = [r for r in _rows(shell, "photons") if r.get("name") == ptu.name]
    assert reopened, "the recording's row is restored"
    assert str(saved) in reopened[0]["address"]  # read from the project itself
    uid = str(reopened[0]["uid"])
    assert any(str(r.get("parent")) == uid for r in _rows(shell, "bursts"))  # and its burst run
    tttr = open_tttr(str(reopened[0]["address"]))
    assert len(tttr) == photons
