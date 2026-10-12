from __future__ import annotations

import json
import sys
from pathlib import Path

from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]

from chisurf.plugins.quenching_estimator.cli.cli import cli  # type: ignore[import]


AMINO_ACIDS = [
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
]


def _aa_interactions(**overrides: dict[str, float]) -> dict[str, dict[str, float]]:
    interactions = {aa: {"slow_factor": 1.0, "kQ": 0.0} for aa in AMINO_ACIDS}
    for aa, values in overrides.items():
        interactions[aa].update(values)
    return interactions


def _make_minimal_project() -> dict:
    project: dict = {}
    project["pdb"] = str(Path(__file__).resolve().parent / "148l.pdb")
    project["attachment"] = {"chain": "E", "residue": 10, "atom": "CB"}
    project["av_parameter"] = {"linker_length": 21.5, "linker_width": 0.5, "radius1": 3.5}
    project["dg"] = 0.5
    project["slow_radius"] = 8.5
    project["t_max"] = 200.0
    project["t_step"] = 0.02
    project["n_photons"] = 5_000  # small to keep simulations light if invoked
    project["n_bins"] = 128
    project["skip_frame"] = 5
    project["tau0"] = 4.2
    project["critical_distance"] = 6.5
    project["amino_acid_interactions"] = _aa_interactions(TYR={"slow_factor": 0.1, "kQ": 2.0})
    project["output_file"] = "test_out"
    project["save_avs"] = False
    project["fret"] = {"enabled": False, "dyes": [
        {
            "name": "D0",
            "role": "donor",
            "attachment": project["attachment"],
            "av_parameter": project["av_parameter"],
            "D": 7.0,
        }
    ], "R0_matrix": []}
    return project


def test_cli_template_and_validate(tmp_path: Path) -> None:
    runner = CliRunner()

    # Template (no-fret) should succeed
    result_template = runner.invoke(cli, ["template", "--no-fret"], catch_exceptions=False)
    assert result_template.exit_code == 0
    assert "fret" in result_template.output

    # Write a minimal project and validate it via CLI
    project = _make_minimal_project()
    project_path = tmp_path / "proj.quest.json"
    project_path.write_text(json.dumps(project), encoding="utf8")

    result_validate = runner.invoke(cli, ["validate", "-p", str(project_path)], catch_exceptions=False)
    assert result_validate.exit_code == 0
    assert "valid" in result_validate.output.lower()
