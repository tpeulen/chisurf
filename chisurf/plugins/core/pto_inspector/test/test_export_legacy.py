"""The inspector's one explicit export: the Seidel/Margarita folder, from the GUI model and the CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner

from chisurf.core.datastore import store_from_arrays
from chisurf.core.fio.fluorescence.burst_companion import read_companion
from chisurf.core.fio.fluorescence.burst_container import container_for, write_burst_artifact

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


def test_the_model_exports_and_says_so(container, tmp_path):
    from chisurf.plugins.core.pto_inspector.gui.view_model import PtoInspectorViewModel

    model = PtoInspectorViewModel()
    assert "No container open" in model.export_legacy()
    model.set_filename(str(container))
    assert "Choose the legacy folder" in model.export_legacy()  # nothing chosen yet
    verdict = model.export_legacy(str(tmp_path / "legacy"))
    assert verdict.startswith("Exported") and "bi4_bur" in verdict
    bv4 = tmp_path / "legacy" / "run" / "bv4" / "m000.bv4"
    assert read_companion(bv4)[1].shape == (N, 1)
    assert model.status == verdict
    model.close()


def test_the_cli_subcommand_writes_the_same_folder(container, tmp_path):
    from chisurf.plugins.core.pto_inspector.cli.main import cli

    out = tmp_path / "cli"
    result = CliRunner().invoke(cli, ["export-legacy", str(container), str(out)])
    assert result.exit_code == 0, result.output
    assert (out / "run" / "bi4_bur" / "m000.bur").is_file()
    assert (out / "run" / "bv4" / "m000.bv4").is_file()
    assert "wrote" in result.output
