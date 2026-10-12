from __future__ import annotations

import sys
import json
import numpy as np
import pytest
from pathlib import Path
from click.testing import CliRunner

# Ensure quest is importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chisurf.plugins.quenching_estimator.api.local import simulate_project, DecaySimulationResult
from chisurf.plugins.quenching_estimator.cli.cli import cli

PDB_PATH = Path(__file__).resolve().parent / "148l.pdb"

AMINO_ACIDS = [
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
]


def _aa_interactions(**overrides: dict[str, float]) -> dict[str, dict[str, float]]:
    interactions = {aa: {"slow_factor": 1.0, "kQ": 0.0} for aa in AMINO_ACIDS}
    for aa, values in overrides.items():
        interactions[aa].update(values)
    return interactions


def _make_project(with_fret: bool) -> dict:
    project = {
        "pdb": str(PDB_PATH),
        "attachment": {"chain": "E", "residue": 10, "atom": "CB"},
        "av_parameter": {"linker_length": 21.5, "linker_width": 0.5, "radius1": 3.5},
        "dg": 0.5,
        "slow_radius": 8.5,
        "t_max": 100.0,
        "t_step": 0.05,
        "n_photons": 5_000,
        "n_bins": 256,
        "skip_frame": 10,
        "tau0": 4.2,
        "critical_distance": 6.5,
        "amino_acid_interactions": _aa_interactions(TYR={"slow_factor": 0.1, "kQ": 2.0}),
        "output_file": "test_out",
        "save_avs": False,
    }
    
    dyes = [
        {
            "name": "D0",
            "role": "donor",
            "attachment": project["attachment"],
            "av_parameter": project["av_parameter"],
            "D": 7.0,
        }
    ]

    if with_fret:
        dyes.append(
            {
                "name": "A0",
                "role": "acceptor",
                "attachment": {"chain": "E", "residue": 18, "atom": "CB"},
                "av_parameter": project["av_parameter"],
                "D": 7.0,
            }
        )
        project["fret"] = {"enabled": True, "dyes": dyes, "R0_matrix": [[None, 52.0], [52.0, None]]}
    else:
        project["fret"] = {"enabled": False, "dyes": dyes, "R0_matrix": []}

    return project


def test_use_case_donor_only() -> None:
    """Test standard donor-only simulation on 148l.pdb."""
    project = _make_project(with_fret=False)
    result = simulate_project(project)
    
    assert isinstance(result, DecaySimulationResult)
    assert result.time.ndim == 1
    assert result.donor_counts.ndim == 1
    assert len(result.time) == project["n_bins"]
    assert 0.0 < result.quantum_yield_donor <= 1.0
    assert 0.0 <= result.collisions_fraction <= 1.0


def test_use_case_fret() -> None:
    """Test FRET simulation on 148l.pdb."""
    project = _make_project(with_fret=True)
    result = simulate_project(project)
    
    assert isinstance(result, DecaySimulationResult)
    assert result.fret_counts is not None
    assert len(result.fret_counts) == project["n_bins"]
    assert 0.0 <= result.quantum_yield_fret <= 1.0
    assert 0.0 <= result.fret_efficiency <= 1.0


def test_cli_validate_use_case(tmp_path: Path) -> None:
    """Test CLI validate command with a valid project file."""
    runner = CliRunner()
    project = _make_project(with_fret=False)
    project_path = tmp_path / "project.json"
    project_path.write_text(json.dumps(project), encoding="utf8")
    
    result = runner.invoke(cli, ["validate", "-p", str(project_path)])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


@pytest.mark.needs_av
def test_cli_simulate_use_case(tmp_path: Path) -> None:
    """Test CLI simulate command with output csv/json generation."""
    runner = CliRunner()
    project = _make_project(with_fret=False)
    project_path = tmp_path / "project.json"
    project_path.write_text(json.dumps(project), encoding="utf8")
    
    out_csv = tmp_path / "out.csv"
    result = runner.invoke(cli, ["simulate", "-p", str(project_path), "-o", str(out_csv)])
    assert result.exit_code == 0
    assert out_csv.exists()
    
    # Check that CSV has headers
    lines = out_csv.read_text(encoding="utf8").splitlines()
    assert len(lines) > 1
    assert "time" in lines[0]
    assert "donor" in lines[0]


@pytest.mark.needs_av
def test_cli_simulate_grid_sweep_use_case(tmp_path: Path) -> None:
    """Test CLI simulate command doing a grid parameter sweep."""
    runner = CliRunner()
    project = _make_project(with_fret=False)
    project_path = tmp_path / "project.json"
    project_path.write_text(json.dumps(project), encoding="utf8")
    
    out_json = tmp_path / "out.json"
    result = runner.invoke(cli, [
        "simulate",
        "-p", str(project_path),
        # 10 and 15 lost their accessible volume when radii moved to IMP's.
        "--grid", "attachment.residue=18,36",
        "-o", str(out_json)
    ])
    assert result.exit_code == 0
    
    # Grid sweeps output multiple files matching format: out_param-val.json
    out_files = list(tmp_path.glob("out_attachment.residue-*.json"))
    assert len(out_files) == 2
    
    # Read one file to verify it's valid JSON result
    with out_files[0].open("r", encoding="utf8") as f:
        data = json.load(f)
    assert "quantum_yield_donor" in data
