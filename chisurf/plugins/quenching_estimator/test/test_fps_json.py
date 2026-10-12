import json
import os
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner

from chisurf.plugins.quenching_estimator.api import local as api
from chisurf.plugins.quenching_estimator.cli.cli import cli

# Test with 148l.pdb which is a T4 Lysozyme structure
PDB_PATH = Path(__file__).parent / "148l.pdb"
IMP_BFF_FPS_PATH = "/Users/tpeulen/dev/imp.bff/examples/structure/T4L/fret.fps.json"

AMINO_ACIDS = [
    "ALA",
    "ARG",
    "ASN",
    "ASP",
    "CYS",
    "GLN",
    "GLU",
    "GLY",
    "HIS",
    "ILE",
    "LEU",
    "LYS",
    "MET",
    "PHE",
    "PRO",
    "SER",
    "THR",
    "TRP",
    "TYR",
    "VAL",
]


def _aa_interactions(**overrides: dict[str, float]) -> dict[str, dict[str, float]]:
    interactions = {aa: {"slow_factor": 1.0, "kQ": 0.0} for aa in AMINO_ACIDS}
    for aa, values in overrides.items():
        interactions[aa].update(values)
    return interactions


def _make_project() -> dict:
    project = {
        "pdb": str(PDB_PATH),
        "attachment": {"chain": "E", "residue": 10, "atom": "CB"},
        "av_parameter": {"linker_length": 21.5, "linker_width": 0.5, "radius1": 3.5},
        "dg": 1.5,  # larger spacing for faster tests
        "slow_radius": 8.5,
        "t_max": 10.0,
        "t_step": 0.05,
        "n_photons": 2000,
        "n_bins": 64,
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

    project["fret"] = {"enabled": False, "dyes": dyes, "R0_matrix": []}
    return project


@pytest.fixture
def base_project():
    """Returns a basic QuEst project settings dictionary."""
    return _make_project()


def test_load_fps_json():
    """Verify that we can load and parse an fps.json file."""
    if not os.path.exists(IMP_BFF_FPS_PATH):
        pytest.skip(f"Reference file not found at {IMP_BFF_FPS_PATH}")

    data = api.load_fps_json(IMP_BFF_FPS_PATH)
    assert "Positions" in data
    assert "Distances" in data
    assert "119A" in data["Positions"]
    assert data["Positions"]["119A"]["residue_seq_number"] == 119


def test_normalize_to_fps_positions(base_project):
    """Verify normalization of old list-of-sites to the fps.json schema."""
    sites_list = [
        {"chain": "E", "residue": 10, "atom": "CB", "residue_name": "ASP"},
        {"chain": "E", "residue": 5, "atom": "CB", "residue_name": "GLU", "name": "custom_name_5"},
    ]

    fps_data = api.normalize_to_fps_positions(sites_list, base_project)
    assert "Positions" in fps_data
    positions = fps_data["Positions"]

    assert "10E" in positions
    assert "custom_name_5" in positions

    pos_5 = positions["custom_name_5"]
    assert pos_5["residue_seq_number"] == 5
    assert pos_5["atom_name"] == "CB"
    assert pos_5["linker_length"] == 21.5


def test_run_fps_scan(base_project, tmp_path):
    """Verify that running a scan on a mock/slice fps.json works and returns named results."""
    fps_data = {
        "Positions": {
            "site_10E": {
                "chain_identifier": "E",
                "residue_seq_number": 10,
                "atom_name": "CB",
                "residue_name": "ASP",
                "linker_length": 20.0,
                "linker_width": 0.5,
                "radius1": 3.5,
                "simulation_grid_resolution": 1.5,
                "simulation_type": "AV1",
            }
        }
    }

    generator = api.run_fps_scan(
        fps_data=fps_data,
        pdb_path=PDB_PATH,
        project=base_project,
        nbins=64,
        tac_range=(0.0, 10.0),
        project_dir=tmp_path,
    )

    results = list(generator)
    assert len(results) == 1
    res = results[0]
    assert res["name"] == "site_10E"
    assert res["status"] == "success", f"Scan failed: {res.get('error')}"
    assert "lifetime" in res
    assert res["lifetime"] is not None
    assert "av_volume" in res
    assert res["av_volume"] is not None
    assert "contact_volume" in res
    assert res["contact_volume"] is not None
    assert "contact_to_free_ratio" in res
    assert res["contact_to_free_ratio"] is not None


@pytest.mark.needs_av
def test_cli_scan_command(base_project, tmp_path):
    """Verify that the quest scan command runs headlessly using CliRunner."""
    project_file = tmp_path / "project.json"
    project_file.write_text(json.dumps(base_project, indent=2), encoding="utf-8")

    labeling_file = tmp_path / "labeling.json"
    labeling_data = {
        "Positions": {
            "site_10E": {
                "chain_identifier": "E",
                "residue_seq_number": 10,
                "atom_name": "CB",
                "residue_name": "ASP",
                "linker_length": 20.0,
                "linker_width": 0.5,
                "radius1": 3.5,
                "simulation_grid_resolution": 1.5,
                "simulation_type": "AV1",
            }
        }
    }
    labeling_file.write_text(json.dumps(labeling_data, indent=2), encoding="utf-8")

    output_file = tmp_path / "scan_results.json"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "scan",
            "-p",
            str(project_file),
            "-l",
            str(labeling_file),
            "--pdb",
            str(PDB_PATH),
            "-o",
            str(output_file),
            "--nbins",
            "64",
            "--tac-start",
            "0.0",
            "--tac-stop",
            "10.0",
        ],
    )

    assert result.exit_code == 0, f"CLI command failed: {result.output}"
    assert output_file.exists()

    scan_results = json.loads(output_file.read_text(encoding="utf-8"))
    assert "site_10E" in scan_results
    assert scan_results["site_10E"]["status"] == "success"
    assert "lifetime" in scan_results["site_10E"]
    assert "av_volume" in scan_results["site_10E"]
    assert "contact_volume" in scan_results["site_10E"]
    assert "contact_to_free_ratio" in scan_results["site_10E"]


def test_run_fps_scan_buried_residue(base_project, tmp_path):
    """Verify that running a scan on a buried residue fails gracefully and reports 'failed'."""
    fps_data = {
        "Positions": {
            "site_buried": {
                "chain_identifier": "E",
                "residue_seq_number": 10,
                "atom_name": "CB",
                "residue_name": "ASP",
                "linker_length": 0.1,
                "linker_width": 0.1,
                "radius1": 10.0,
                "simulation_grid_resolution": 1.5,
                "simulation_type": "AV1",
            }
        }
    }

    generator = api.run_fps_scan(
        fps_data=fps_data,
        pdb_path=PDB_PATH,
        project=base_project,
        nbins=64,
        tac_range=(0.0, 10.0),
        project_dir=tmp_path,
    )

    results = list(generator)
    assert len(results) == 1
    res = results[0]
    assert res["name"] == "site_buried"
    assert res["status"] == "failed"
    assert "error" in res
    assert "Accessible Volume is empty" in res["error"]
