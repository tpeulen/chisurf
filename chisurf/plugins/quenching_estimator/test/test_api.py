"""Tests for the high-level quest.api module.

These tests exercise the public API functions that are intended to be
used from scripts or Jupyter notebooks:

- quest.api.load_project
- quest.api.simulate_project

The tests construct a small in-memory project dictionary and use a
bundled PDB file so they do not depend on the GUI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

from chisurf.plugins.quenching_estimator.api.local import (
    DecaySimulationResult,
    load_project,
    simulate_project,
)

PDB_PATH = Path(__file__).resolve().parent / "148l.pdb"
AAS = [
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
    interactions = {aa: {"slow_factor": 1.0, "kQ": 0.0} for aa in AAS}
    for aa, values in overrides.items():
        interactions[aa].update(values)
    return interactions


def _make_minimal_project(with_fret: bool) -> dict[str, Any]:
    """Return a small but complete QuEst project dictionary for testing.

    The parameters are chosen so that simulations run quickly while still
    exercising the core diffusion and decay logic. Attachment and
    quencher positions are selected from the bundled 148l.pdb file.
    """

    project: dict[str, Any] = {}

    project["pdb"] = str(PDB_PATH)
    project["attachment"] = {
        "chain": "E",
        # This project switches every quencher off except TYR, so
        # `quenching_grid.max() >= 2.0` really asserts "a tyrosine is within
        # critical_distance of the accessible volume". Which sites satisfy that
        # is sensitive to the AV, so it has been re-measured twice rather than
        # relaxed:
        #
        #   2026-07-27, move to IMP radii — larger atoms shrank every volume,
        #               leaving only 36 and 82 on this chain.
        #   2026-07-28, one grid-offset convention — the quenching grid had been
        #               stamped up to one voxel per axis from where the walk read
        #               it, so *which* residues were in reach changed wholesale.
        #               Re-scanned residues 2..164 under both backends:
        #                 imp_bff  : 80 86 97 103 117 127 129 131 132 135 136
        #                            137 139 141 143 144 145 149 150 151 152
        #                            154 157 160
        #                 labellib : 2 74 92 95 96 97 130 134 138 160
        #               The intersection is {97, 160}; 36 is in neither.
        #   2026-08-18, IMP.bff's global absolute lattice — the volume moved
        #               again and **97 fell out**: no TYR within
        #               critical_distance, so the written grid is all zeros.
        #               Re-scanned the previously documented candidates; 16 now
        #               satisfy both this assertion and 0 < QY < 1:
        #                 117 127 129 130 131 132 135 139 141 143 144 150 152
        #                 154 157 160
        #               Nearly all sit at QY 0.997-0.999, i.e. barely quenched
        #               and one AV change away from failing again. **117 is the
        #               only one with real margin (QY 0.957)**, so it is the
        #               pick — not merely a site that passes today.
        #
        # LabelLib is gone since the quenching model moved into IMP.bff, so the both-backends constraint that
        # produced the 2026-07-28 intersection no longer applies.
        #
        # **The FRET variant keeps 97, and that is a symptom, not a taste.**
        # `fret_rate_pair_trace` requires the donor and acceptor trajectories to
        # have the same number of frames: donor 117 gives 50 000 against the
        # acceptor's 80 000 and the pairing raises.
        #
        # The acceptor is a *different dye at a different site*, quenched by its
        # own local residues, so it needs a different number of excitations to
        # collect the same photons. **Unequal lengths are the normal case, not an
        # error case**, and the refusal to truncate is right (a trajectory
        # concatenates one walk per excitation, so an arbitrary cut splits one).
        # The defect is that QuEst never matches the two dyes' *walk counts* --
        # which is the lever, not t_max or t_step, both already shared and named
        # by the old error message. Filed rather than papered over; until the
        # counts are matched this fixture uses an unquenched donor for the FRET
        # case, where the grid assertion below does not apply anyway.
        "residue": 97 if with_fret else 117,
        "atom": "CB",
    }

    project["av_parameter"] = {
        "linker_length": 21.5,
        "linker_width": 0.5,
        "radius1": 3.5,
    }

    project["dg"] = 0.5
    project["slow_radius"] = 8.5

    project["t_max"] = 200.0
    project["t_step"] = 0.02
    project["n_photons"] = 10_000
    project["n_bins"] = 512
    project["skip_frame"] = 10

    project["tau0"] = 4.2
    project["critical_distance"] = 6.5
    project["amino_acid_interactions"] = _aa_interactions(TYR={"kQ": 2.0})

    project["output_file"] = "test_out"
    project["save_avs"] = False

    # Dyes and per-dye diffusion coefficients
    dyes = []

    donor = {
        "name": "D0",
        "role": "donor",
        "attachment": project["attachment"],
        "av_parameter": project["av_parameter"],
        "D": 7.0,
    }
    dyes.append(donor)

    if with_fret:
        acceptor = {
            "name": "A0",
            "role": "acceptor",
            "attachment": {
                "chain": "E",
                "residue": 18,
                "atom": "CB",
            },
            "av_parameter": project["av_parameter"],
            "D": 7.0,
        }
        dyes.append(acceptor)

        project["fret"] = {
            "enabled": True,
            "dyes": dyes,
            "R0_matrix": [
                [None, 52.0],
                [52.0, None],
            ],
        }
    else:
        project["fret"] = {
            "enabled": False,
            "dyes": dyes,
            "R0_matrix": [],
        }

    return project


def test_simulate_project_donor_only() -> None:
    """Simulate a donor-only decay and validate basic properties.

    This test checks that the API returns arrays of matching length,
    a reasonable quantum yield in the (0, 1] range, and a valid
    collision fraction.
    """

    project = _make_minimal_project(with_fret=False)
    result = simulate_project(project)

    assert isinstance(result, DecaySimulationResult)

    assert result.time.ndim == 1
    assert result.donor_counts.ndim == 1
    assert result.time.shape == result.donor_counts.shape

    assert result.fret_counts is None
    assert 0.0 < result.quantum_yield_donor <= 1.0

    assert 0.0 <= result.collisions_fraction <= 1.0


def test_load_project_roundtrip(tmp_path: Path) -> None:
    """Write a minimal project to disk and load it via load_project.

    This test ensures that the JSON loader returns a dictionary with the
    expected keys and values, and that it can be passed directly into
    :func:`simulate_project`.
    """

    project = _make_minimal_project(with_fret=False)
    target = tmp_path / "proj.quest.json"
    target.write_text(json.dumps(project), encoding="utf8")

    loaded = load_project(target)

    assert loaded["pdb"] == project["pdb"]
    assert loaded["attachment"]["residue"] == project["attachment"]["residue"]

    result = simulate_project(loaded)
    assert isinstance(result, DecaySimulationResult)


def test_simulate_project_with_fret() -> None:
    """Simulate a donor+FRET decay and validate FRET-specific outputs.

    The test enables FRET, runs the simulation, and verifies that a
    second decay curve is produced together with a FRET quantum yield
    and efficiency estimate.
    """

    project = _make_minimal_project(with_fret=True)
    result = simulate_project(project)

    assert isinstance(result, DecaySimulationResult)

    assert result.fret_counts is not None
    assert result.fret_counts.shape == result.donor_counts.shape

    assert result.quantum_yield_fret is not None
    assert 0.0 <= result.quantum_yield_fret <= 1.0

    if result.fret_efficiency is not None:
        assert 0.0 <= result.fret_efficiency <= 1.0


def test_simulate_project_with_custom_amino_acid_kq() -> None:
    """Verify that per-AA kQ values drive the additive quenching-rate grid."""
    project = _make_minimal_project(with_fret=False)
    project["amino_acid_interactions"] = _aa_interactions(
        TYR={"kQ": 3.0},
        MET={"kQ": 1.5},
    )
    result = simulate_project(project)
    assert isinstance(result, DecaySimulationResult)
    assert 0.0 < result.quantum_yield_donor <= 1.0


def test_simulate_project_job_dir(tmp_path: Path) -> None:
    """Verify that running a simulation writes files to a unique folder under project_dir."""
    project = _make_minimal_project(with_fret=False)
    # `save_outputs` is opt-in since 2026-07-28; this test is about *where* the
    # artefacts land once a caller has asked for them.
    result = simulate_project(project, project_dir=tmp_path, save_outputs=True)
    assert isinstance(result, DecaySimulationResult)
    assert result.job_id is not None

    jobs_dir = tmp_path / "jobs"
    assert jobs_dir.is_dir()

    job_folders = [p for p in jobs_dir.iterdir() if p.is_dir()]
    assert len(job_folders) == 1
    job_folder = job_folders[0]
    assert job_folder.name == result.job_id

    # Verify uuid format
    import uuid

    uuid.UUID(job_folder.name)

    out_xyz = job_folder / "out.xyz"
    out_slow_xyz = job_folder / "out_slow.xyz"
    result_json = job_folder / "result.json"
    sampled_density_mrc = job_folder / "sampled_dye_density.mrc"
    diffusion_coefficients_mrc = job_folder / "diffusion_coefficients.mrc"
    quenching_rates_mrc = job_folder / "quenching_rates.mrc"
    aa_residence_csv = job_folder / "aa_residence.csv"

    assert out_xyz.is_file()
    assert out_slow_xyz.is_file()
    assert result_json.is_file()
    assert sampled_density_mrc.is_file()
    assert diffusion_coefficients_mrc.is_file()
    assert quenching_rates_mrc.is_file()
    assert aa_residence_csv.is_file()
    assert sampled_density_mrc.stat().st_size > 1024
    with sampled_density_mrc.open("rb") as f:
        header = f.read(212)
    assert header[208:212] == b"MAP "
    with diffusion_coefficients_mrc.open("rb") as f:
        header = f.read(1024)
        diffusion_grid = np.frombuffer(f.read(), dtype=np.float32)
    assert header[208:212] == b"MAP "
    assert diffusion_grid.max() <= project["fret"]["dyes"][0]["D"]
    assert diffusion_grid.max() > 0.0
    with quenching_rates_mrc.open("rb") as f:
        header = f.read(1024)
        quenching_grid = np.frombuffer(f.read(), dtype=np.float32)
    assert header[208:212] == b"MAP "
    assert quenching_grid.max() >= 2.0

    with result_json.open("r", encoding="utf8") as f:
        data = json.load(f)
    assert data["job_id"] == result.job_id
    assert "time_ns" in data
    assert "donor_counts" in data
    assert result.trajectory_points is not None
    assert result.trajectory_points.ndim == 2
    assert result.trajectory_points.shape[1] == 3
    assert len(result.trajectory_points) <= 2000
    assert data["trajectory_points"] == result.trajectory_points.tolist()
    assert isinstance(result.aa_residence, list)
    assert data["aa_residence"] == result.aa_residence
    assert aa_residence_csv.read_text(encoding="utf-8").startswith("residue_name,center_count")
