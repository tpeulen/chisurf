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

pytestmark = pytest.mark.skipif(not PTU.exists(), reason="no instrument test data")


@pytest.fixture
def container(tmp_path: Path) -> Path:
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
    assert core.export_plan(container.parent / "nowhere.pto") == []


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
