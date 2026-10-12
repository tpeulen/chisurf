from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

# Ensure quest is importable
ROOT = Path(__file__).resolve().parents[1]

from chisurf.plugins.quenching_estimator.api.local import DecaySimulationResult, simulate_project

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


def test_mc4r_simulation() -> None:
    cif_path = ROOT / "test" / "data" / "mc4r_dimer.cif"
    assert cif_path.exists(), f"Test CIF file not found at {cif_path}"

    project: dict[str, Any] = {
        "pdb": str(cif_path),
        "attachment": {
            "chain": "A",
            # Re-picked with the move to IMP radii: A1 and A2 no longer have an
            # accessible volume at this grid resolution. (A1 still does at
            # dg = 1.0 — burial is resolution-dependent, since a coarser grid
            # cannot resolve the atoms that close the pocket.)
            "residue": 3,
            "atom": "CB",
        },
        "av_parameter": {
            "linker_length": 21.5,
            "linker_width": 0.5,
            "radius1": 3.5,
        },
        "dg": 0.5,
        "slow_radius": 8.5,
        "t_max": 200.0,
        "t_step": 0.02,
        "n_photons": 1000,
        "n_bins": 512,
        "tau0": 4.0,
        "critical_distance": 5.0,
        "amino_acid_interactions": _aa_interactions(
            HIS={"slow_factor": 0.05, "kQ": 2.0},
            TRP={"slow_factor": 0.05, "kQ": 2.0},
            TYR={"slow_factor": 0.05, "kQ": 2.0},
        ),
        "output_file": "out_test",
        "save_avs": False,
        "fret": {"enabled": False, "dyes": [{"D": 40.0}], "R0_matrix": []},
    }

    result = simulate_project(project)

    assert isinstance(result, DecaySimulationResult)
    assert result.time.ndim == 1
    assert result.donor_counts.ndim == 1
    assert result.time.shape == result.donor_counts.shape
    assert result.fret_counts is None
    assert 0.0 < result.quantum_yield_donor <= 1.0
    assert 0.0 <= result.collisions_fraction <= 1.0
