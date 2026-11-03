"""A burst run is a child of its photons in Datasets; deleting it removes it from the .pto.

The run row's record is the project's analysis container, so removing it only from the workspace
would bring it back at the next restore. Delete asks first, names the analyses computed from the
run (a fusion of its bursts), and then removes the run and those analyses from the container and
from the workspace; the photons stay. Delete on a run row used to remove its *parent*, the photons.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import Driver

from chisurf.core.datastore import store_from_arrays
from chisurf.core.fio.analysis_path import list_runs
from chisurf.core.project import analysis
from test.native_emtk.test_emtk_shell_fits import DATASETS_KEY, SHOTS, _settle

PTU = Path(__file__).resolve().parents[1] / "data" / "clsm" / "Leica_SP5.ptu"
RUN = "cusum_sprt_All 0.1500#30"
FUSED = f"{RUN} fused p0.50"

pytestmark = pytest.mark.skipif(not PTU.exists(), reason="no instrument test data")


@pytest.fixture(autouse=True)
def _private(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_ANALYSIS_DIR", str(tmp_path / "analysis"))
    monkeypatch.setenv("CHISURF_PROJECT_TEMP_DIR", str(tmp_path / "temp-projects"))
    monkeypatch.setattr(analysis, "_SESSION", None)


@pytest.fixture
def shell():
    """A shell whose session shares the process's datasets, as the app's does: a run reaches the
    workspace through that (``register_result``), not through the shell."""
    import chisurf
    from chisurf.emtk.main_app import EmtkShellApp
    from chisurf.emtk.session import start_session

    before = list(chisurf.imported_datasets)
    session = start_session()
    app = EmtkShellApp({}, loader=lambda plugin_id: None)
    app.data.adopt(session)
    yield app
    app.close()
    chisurf.imported_datasets[:] = before


def _bur(n: int, name: str):
    first = np.zeros(2 * n + 1)
    first[1::2] = np.arange(n) * 100.0
    last = first + 50.0 * (first > 0)
    files = np.array(["0"] * (2 * n + 1), dtype=object)
    files[1::2] = name
    return store_from_arrays(
        {"First Photon": first, "Last Photon": last, "Number of Photons": last - first, "First File": files}
    )


def _runs_of(raw: Path, uid: str) -> Path:
    """A burst search of *raw* in *uid*'s analysis container, and a fusion of it."""
    from chisurf.core.fio.fluorescence.burst_container import container_for, write_burst_artifact

    out = analysis.container_dir(uid)
    for run, parents in ((RUN, ()), (FUSED, [f"{RUN}/bi4_bur/{raw.stem}.bur"])):
        write_burst_artifact(
            raw,
            _bur(4, raw.name),
            name=f"{run}/bi4_bur/{raw.stem}.bur",
            deinterleave=False,
            artifact_kind="burst_table",
            operation_type="burst_selection",
            parameters={"run": run},
            derived_from=parents,
            out_dir=out,
            raw_data="sidecar",
        )
    return container_for(raw, out)


def _rows(shell, kind):
    return [r for r in shell.data.datasets.datasets if r.get("kind") == kind]


def test_a_run_is_a_child_and_delete_removes_it_with_its_fusion_from_the_pto(shell, tmp_path):
    from chisurf.core.plugin.workspace_input import register_result

    raw = tmp_path / "DNA13bp_3.ptu"
    shutil.copy(PTU, raw)
    driver = Driver(shell, (1400, 900))
    driver.frame(4)
    photons = register_result(str(raw), kind="photons", name=raw.name)
    uid = str(photons.unique_identifier)
    container = _runs_of(raw, uid)
    analysis.container_changed(container)

    def nested():
        rows = {r["name"]: r for r in _rows(shell, "bursts")}
        run, fused = rows.get(RUN), rows.get(FUSED)
        # a tree: the search under its photons, the fusion under the search
        return bool(run and fused) and str(run["parent"]) == uid and fused["parent"] == run["uid"]

    _settle(driver, nested, "both runs under their photons")
    shell.docks.focus(DATASETS_KEY)
    driver.frame(4)
    driver.screenshot(SHOTS / "datasets_runs_nested.png")

    run_row = next(r for r in _rows(shell, "bursts") if r["name"].startswith(RUN) and "fused" not in r["name"])
    shell.data.datasets.remove_dataset(run_row)  # the Delete key on the run row
    dialogs = shell.project.dialogs
    question = dialogs.current
    assert question is not None and question.kind == "confirm"
    assert FUSED in question.message  # the dependent analysis is named
    assert list_runs(container) == [RUN, FUSED]  # nothing removed before the answer
    driver.frame(4)
    driver.screenshot(SHOTS / "datasets_remove_run_warning.png")
    dialogs.answer(key="yes")

    _settle(driver, lambda: not _rows(shell, "bursts") and not shell.data.busy, "the runs removed")
    assert list_runs(container) == []
    assert [r["uid"] for r in _rows(shell, "photons")] == [uid]  # the photons stay
    analysis.sync_runs()  # nothing comes back from the container
    driver.frame(6)
    assert not _rows(shell, "bursts")


def test_cancel_removes_nothing(shell, tmp_path):
    from chisurf.core.plugin.workspace_input import register_result

    raw = tmp_path / "m.ptu"
    shutil.copy(PTU, raw)
    driver = Driver(shell, (1400, 900))
    driver.frame(4)
    uid = str(register_result(str(raw), kind="photons", name=raw.name).unique_identifier)
    container = _runs_of(raw, uid)
    analysis.container_changed(container)
    _settle(driver, lambda: len(_rows(shell, "bursts")) == 2, "the runs")
    assert {uid} | {str(r["uid"]) for r in _rows(shell, "bursts")} >= {
        str(r["parent"]) for r in _rows(shell, "bursts")
    }
    shell.data.datasets.selection = [r for r in _rows(shell, "bursts") if "fused" in r["name"]]
    shell.data.datasets.selected = shell.data.datasets.selection[0]
    shell.data.datasets.remove_selected()
    assert "computed from it" not in shell.project.dialogs.current.message  # a leaf: nothing else goes
    shell.project.dialogs.answer(key="no")
    driver.frame(10)
    assert list_runs(container) == [RUN, FUSED] and len(_rows(shell, "bursts")) == 2
