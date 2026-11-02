"""A photon dataset's analysis container lives in the project: written while the session runs,
embedded as ``project.cs.pto/<name>.pto`` at save, restored on open, its runs derived as rows."""

from __future__ import annotations

from pathlib import Path

import pytest

from chisurf.core.project import analysis


@pytest.fixture(autouse=True)
def fresh_session(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_ANALYSIS_DIR", str(tmp_path / "analysis"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setattr(analysis, "_SESSION", None)


def _search(tmp_path, uid: str) -> Path:
    """A burst run of the demo measurement, written into *uid*'s analysis container."""
    from chisurf.core.fio.fluorescence.burst import read_bur_file
    from chisurf.core.fio.fluorescence.burst_container import deinterleave_bursts
    from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    measurement = build(tmp_path / "measurement")
    bur = sorted((measurement / "bi4_bur").glob("*.bur"))[0]
    return Path(
        write_container(
            measurement.parent / "m000.spc",
            deinterleave_bursts(read_bur_file(bur)),
            parameters={"run": 1},
            out_dir=analysis.container_dir(uid),
            run="runBursts#1",
            raw_data="sidecar",
        )
    )


def test_a_run_goes_into_the_projects_container_not_beside_the_vendor_file(tmp_path):
    container = _search(tmp_path, "photons-1")
    assert container.parent == analysis.container_dir("photons-1")
    assert not (tmp_path / "measurement" / "m000.pto").exists()
    rows = analysis.derived_datasets()
    assert [(Path(r.address).name, r.result_of) for r in rows] == [("runBursts#1", "photons-1")]
    assert analysis.is_derived(rows[0].address)


def test_the_container_is_embedded_on_save_and_restored_on_open(tmp_path, monkeypatch):
    from chisurf.core.project.project import Project

    _search(tmp_path, "photons-1")
    saved = Project(name="p").save(tmp_path / "p.cs.pto")
    reopened_session = tmp_path / "other-session"
    monkeypatch.setenv("CHISURF_ANALYSIS_DIR", str(reopened_session))
    monkeypatch.setattr(analysis, "_SESSION", None)
    project = Project.load(saved)
    assert project.extra[analysis.EXTRA_KEY] == {"photons-1": ["m000.pto"]}
    restored = analysis.containers()["photons-1"]
    assert restored[0].is_relative_to(reopened_session)
    rows = analysis.derived_datasets()
    assert [Path(r.address).name for r in rows] == ["runBursts#1"]


def test_ndx_reads_the_run_out_of_the_container(tmp_path):
    """The container is in exactly the format ndX reads (its own reader, no ChiSurf code)."""
    from ndxplorer.io.pto_reader import list_tables, read_container

    container = _search(tmp_path, "photons-1")
    tables = list_tables(container)
    assert [t["run"] for t in tables] == ["runBursts#1"]
    assert read_container(container).size == tables[0]["rows"]


def test_a_search_with_other_settings_is_a_new_run_the_same_settings_replace_it(tmp_path):
    """The run name (``sliding_window_All 0.1500#60``) does not carry every setting: a second
    search with other settings is a new analysis (``... (2)``), not hidden under the first."""
    from chisurf.core.fio.fluorescence.burst import read_bur_file
    from chisurf.core.fio.fluorescence.burst_container import deinterleave_bursts, new_run_name
    from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    measurement = build(tmp_path / "measurement")
    source = measurement.parent / "m000.spc"
    table = deinterleave_bursts(read_bur_file(sorted((measurement / "bi4_bur").glob("*.bur"))[0]))
    out = analysis.container_dir("photons-1")

    def search(settings):
        run = new_run_name(source, "runBursts#1", settings, out)
        write_container(source, table, parameters=settings, out_dir=out, run=run, raw_data="sidecar")
        return run

    assert search({"T": 0.5}) == "runBursts#1"
    assert search({"T": 0.5}) == "runBursts#1"  # the same settings: replaced
    assert search({"T": 0.6}) == "runBursts#1 (2)"  # other settings: a new analysis
    assert search({"T": 0.7}) == "runBursts#1 (3)"
    assert search({"T": 0.6}) == "runBursts#1 (2)"
    names = sorted(Path(r.address).name for r in analysis.derived_datasets())
    assert names == ["runBursts#1", "runBursts#1 (2)", "runBursts#1 (3)"]
