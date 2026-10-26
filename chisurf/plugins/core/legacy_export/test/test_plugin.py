"""The legacy-export plugin: plan preview, burst-folder writer, ALEX CSVs, model, CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner

from chisurf.core.datastore import store_from_arrays
from chisurf.core.fio.fluorescence.burst_container import (
    container_for,
    write_burst_artifact,
)

PTU = Path(__file__).resolve().parents[5] / "test" / "data" / "clsm" / "Leica_SP5.ptu"
N = 12


@pytest.fixture
def container(tmp_path: Path) -> Path:
    if not PTU.exists():
        pytest.skip("no instrument test data")
    raw = tmp_path / "m000.ptu"
    shutil.copy(PTU, raw)
    interleaved = np.zeros(2 * N + 1)
    interleaved[1::2] = np.arange(N) + 60
    write_burst_artifact(
        raw,
        store_from_arrays({"Number of Photons": interleaved}),
        name="run/bi4_bur/m000.bur",
        deinterleave=False,
        artifact_kind="burst_table",
        operation_type="burst_selection",
        parameters={"min_photons": 60},
        derived_from=(),
    )
    write_burst_artifact(
        raw,
        store_from_arrays({"Proximity Ratio Mean": np.linspace(0, 1, N)}),
        name="bva",
        artifact_kind="burst_table",
        operation_type="burst_variance_analysis",
        parameters={"window": 5},
        derived_from=(),
    )
    return container_for(raw)


def test_the_plan_names_run_operation_and_ending(container: Path):
    from chisurf.plugins.core.legacy_export import core

    rows = core.export_plan(container)
    by_op = {row["operation"]: row for row in rows}
    assert by_op["burst_selection"]["ending"] == "bur"
    assert by_op["burst_variance_analysis"]["ending"] == "bv4"
    # The run is reported beside the table: ``m000.pto/<run>`` opens the run, not the table.
    assert by_op["burst_selection"]["run"] == "bi4_bur/m000.bur"
    assert by_op["burst_selection"]["container_run"] == "run"
    assert by_op["burst_variance_analysis"]["container_run"] == ""
    assert core.export_plan(container.parent / "nowhere.pto") == []


def test_the_model_offers_burst_search_runs_for_the_alex_csvs(container: Path):
    """The Run choice lists run names of burst tables, and picks one by default."""
    from chisurf.plugins.core.legacy_export.gui.app import LegacyExportModel

    model = LegacyExportModel()
    assert "burst-search run" in model.export_alex_csvs()
    model.set_file(str(container))
    assert model.alex_runs() == ["run"]
    assert model.alex_run == "run"


def test_burst_folder_export_writes_bur_and_companions(container: Path, tmp_path: Path):
    from chisurf.plugins.core.legacy_export import core

    written = core.export_burst_folder(container, tmp_path / "legacy")
    names = sorted(p.name for p in written)
    assert "m000.bur" in names
    suffixes = {p.suffix for p in written}
    assert ".bv4" in suffixes
    # The companion carries the analysis, one row per burst -- read it back.
    from chisurf.core.fio.fluorescence.burst_companion import read_companion

    bv4 = next(p for p in written if p.suffix == ".bv4")
    _columns, rows = read_companion(bv4)
    assert len(rows) == N


def test_the_model_exports_and_reports(container: Path, tmp_path: Path):
    from chisurf.plugins.core.legacy_export.gui.app import LegacyExportModel

    model = LegacyExportModel()
    assert "container" in model.export_burst_folder().lower()
    model.set_file(str(container))
    assert model.plan and model.out_folder == str(container.parent)
    verdict = model.export_burst_folder(str(tmp_path / "out"))
    assert "wrote" in verdict.lower()
    assert any(p.endswith(".bur") for p in model.written)


def test_the_cli_plans_and_exports(container: Path, tmp_path: Path):
    from chisurf.plugins.core.legacy_export.cli.main import cli

    runner = CliRunner()
    plan = runner.invoke(cli, ["plan", str(container)])
    assert plan.exit_code == 0 and "burst_selection" in plan.output
    out = runner.invoke(cli, ["burst-folder", str(container), str(tmp_path / "legacy")])
    assert out.exit_code == 0 and "m000.bur" in out.output


def test_the_manifest_loads():
    from chisurf.core.plugin import load_manifest

    m = load_manifest(Path(__file__).resolve().parents[1] / "manifest.json")
    assert m is not None and m.entrypoints.emtk and m.entrypoints.cli


# -- the demo container: a real burst search + BVA of the Burst Selection demo stream -- #


@pytest.fixture(scope="module")
def demo_container(tmp_path_factory) -> Path:
    pytest.importorskip("tttrlib")
    from chisurf.plugins.core.legacy_export import demo

    return demo.make_demo(tmp_path_factory.mktemp("legacy_demo"))


def test_the_demo_is_cached_and_holds_a_burst_search_and_a_companion(demo_container: Path):
    from chisurf.plugins.core.legacy_export import core, demo

    stamp = demo_container.stat().st_mtime_ns
    assert demo.make_demo(demo_container.parent) == demo_container
    assert demo_container.stat().st_mtime_ns == stamp  # reused, not rewritten
    by_op = {row["operation"]: row for row in core.export_plan(demo_container)}
    assert by_op["burst_selection"]["container_run"] == "burstwise"
    assert by_op["burst_variance_analysis"]["ending"] == "bv4"


def test_the_cli_writes_the_alex_csvs_from_a_container_run(demo_container: Path, tmp_path: Path):
    """``alex-csvs m000.pto/<run>``: the container form the docstring promises."""
    from chisurf.plugins.core.legacy_export.cli.main import cli

    out = CliRunner().invoke(
        cli, ["alex-csvs", f"{demo_container}/burstwise", str(tmp_path / "csv" / "bs_demo")]
    )
    assert out.exit_code == 0, out.output
    written = sorted(p.name for p in (tmp_path / "csv").iterdir())
    assert len(written) == 4 and all(name.endswith(".csv") for name in written), written


def _window(tmp_path: Path, demo_container: Path, monkeypatch):
    from emtk.testing import Driver

    from chisurf.plugins.core.legacy_export import demo
    from chisurf.plugins.core.legacy_export.gui.app import make_app

    monkeypatch.setattr(demo, "demo_folder", lambda: demo_container.parent)
    app = make_app()
    driver = Driver(app, (1000, 900))
    driver.frame(2)
    return app, driver


def test_the_window_exports_the_folder_and_the_alex_csvs(
    demo_container: Path, tmp_path: Path, monkeypatch
):
    """Load example -> Export burst folder -> Write ALEX-Suite CSVs, all by their ids."""
    app, driver = _window(tmp_path, demo_container, monkeypatch)
    driver.click("load_example")
    driver.frame(2)
    assert app.model.filename == str(demo_container)
    assert app.model.alex_run == "burstwise"
    app.model.out_folder = str(tmp_path / "legacy")
    driver.frame(1)
    driver.click("export")
    driver.frame(2)
    assert any(p.endswith("bs_demo.bur") for p in app.model.written), app.model.status
    assert any(p.endswith(".bv4") for p in app.model.written), app.model.status
    driver.click("write_alex")
    driver.frame(2)
    assert "Wrote 4 ALEX-Suite CSV(s)" in app.model.status, app.model.status
    assert all(Path(p).exists() for p in app.model.written)


def test_every_tour_target_is_drawn_and_the_awaits_wait_for_real_clicks(
    demo_container: Path, tmp_path: Path, monkeypatch
):
    app, driver = _window(tmp_path, demo_container, monkeypatch)
    tour = app.tour
    assert tour.steps and tour.wait_for_controls
    awaited = [tour._target_key(s["target"]) for s in tour.steps if s.get("await")]
    assert awaited == ["load_example", "export", "write_alex"]
    driver.click("guide")
    driver.frame(1)
    assert tour.active and tour.step_idx == 0
    tour.next()
    assert tour.awaiting  # Load example: the card waits, Next does nothing
    tour.next()
    assert tour.step_idx == 1
    driver.click("load_example")
    driver.frame(2)
    assert not tour.awaiting
    app.model.out_folder = str(tmp_path / "legacy")
    driver.frame(2)
    drawn = set(driver.ids())
    targets = {tour._target_key(s.get("target")) for s in tour.steps} - {""}
    assert targets <= drawn, sorted(targets - drawn)
    for key in ("export", "write_alex"):
        tour.step_idx = next(
            i for i, s in enumerate(tour.steps) if tour._target_key(s.get("target")) == key
        )
        tour._step_used = False
        assert tour.awaiting
        driver.click(key)
        driver.frame(2)
        assert not tour.awaiting, key
