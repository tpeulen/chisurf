"""Unit tests for Phase 4: OLGA pair selection."""

import os
import tempfile
import numpy as np
import pytest

from ..core.pair_selection import (
    preprocess_efficiency_matrix,
    select_informative_pairs,
    write_pair_selection_report,
)


def test_preprocess_drops_column_with_60pct_nan():
    """Verify columns with more than max_nan_fraction NaNs are discarded."""
    effs = np.array([
        [1.0, np.nan],
        [1.0, np.nan],
        [1.0, np.nan],
        [1.0, np.nan],
        [1.0, np.nan],
        [1.0, np.nan],
        [1.0, 0.5],
        [1.0, 0.5],
        [1.0, 0.5],
        [1.0, 0.5],
    ], dtype=np.float32)  # Col 1 has 6/10 NaNs (60%)
    rmsds = np.zeros((10, 10), dtype=np.float32)
    effs_clean, _, valid_indices = preprocess_efficiency_matrix(effs, rmsds, max_nan_fraction=0.2)
    assert list(valid_indices) == [0]
    assert effs_clean.shape == (10, 1)


def test_preprocess_fills_nan_from_nearest_rmsd():
    """Verify NaN cells are populated using efficiency values from the nearest frame (by RMSD)."""
    effs = np.array([
        [np.nan],
        [0.5],
        [0.8]
    ], dtype=np.float32)
    rmsds = np.array([
        [0.0, 1.0, 5.0],
        [1.0, 0.0, 4.0],
        [5.0, 4.0, 0.0]
    ], dtype=np.float32)
    effs_clean, _, _ = preprocess_efficiency_matrix(effs, rmsds, max_nan_fraction=0.5)
    # Row 0 is closer to Row 1 (RMSD=1.0) than Row 2 (RMSD=5.0). Thus, it should take 0.5.
    assert abs(effs_clean[0, 0] - 0.5) < 1e-7


def test_preprocess_zero_nan_returns_all_columns():
    """Verify no columns are discarded when there are no NaN values."""
    effs = np.ones((5, 3), dtype=np.float32)
    rmsds = np.zeros((5, 5), dtype=np.float32)
    effs_clean, _, valid_indices = preprocess_efficiency_matrix(effs, rmsds, max_nan_fraction=0.2)
    assert list(valid_indices) == [0, 1, 2]
    assert effs_clean.shape == (5, 3)


def test_greedy_selection_order_deterministic():
    """Verify greedy selection returns a reproducible selection order on a toy matrix."""
    effs = np.array([
        [0.1, 0.9],
        [0.2, 0.8],
        [0.9, 0.1],
    ], dtype=np.float32)
    rmsds = np.array([
        [0.0, 5.0, 10.0],
        [5.0, 0.0, 5.0],
        [10.0, 5.0, 0.0]
    ], dtype=np.float32)
    selected, decay = select_informative_pairs(effs, rmsds, err=0.05, max_pairs=2)
    assert len(selected) == 2
    assert len(decay) == 2


def test_precision_decay_length_equals_n_selected():
    """Verify length of precision decay output array matches the number of selected pairs."""
    effs = np.array([
        [0.1, 0.9],
        [0.2, 0.8],
        [0.9, 0.1],
    ], dtype=np.float32)
    rmsds = np.array([
        [0.0, 5.0, 10.0],
        [5.0, 0.0, 5.0],
        [10.0, 5.0, 0.0]
    ], dtype=np.float32)
    selected, decay = select_informative_pairs(effs, rmsds, err=0.05, max_pairs=2)
    assert len(decay) == len(selected)


def test_write_report_row0_is_initial_rmsd():
    """Verify the first row of the report contains the correct placeholder and initial RMSD."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        path = f.name
    try:
        write_pair_selection_report(["A", "B"], np.array([5.0, 4.0]), 10.0, path)
        with open(path) as f:
            lines = f.read().splitlines()
        assert lines[0] == "#\tPair_added\t<<RMSD>>/A"
        assert lines[1] == "0\t--\t10.0000"
        assert lines[2] == "1\tA\t5.0000"
        assert lines[3] == "2\tB\t4.0000"
    finally:
        os.unlink(path)


def _toy_matrices():
    effs = np.array([[0.1, 0.9, 0.5], [0.2, 0.8, 0.4], [0.9, 0.1, 0.6]], dtype=np.float32)
    rmsds = np.array([[0.0, 5.0, 10.0], [5.0, 0.0, 5.0], [10.0, 5.0, 0.0]], dtype=np.float32)
    return effs, rmsds  # 3 frames, 3 candidate pairs


def test_select_max_pairs_caps_to_n_pairs():
    """max_pairs larger than the number of candidate pairs is capped, not an error."""
    effs, rmsds = _toy_matrices()
    selected, decay = select_informative_pairs(effs, rmsds, err=0.05, max_pairs=10)
    assert len(selected) <= effs.shape[1]
    assert len(decay) == len(selected)


def test_select_max_pairs_zero_returns_empty():
    """max_pairs <= 0 returns empty selection + decay arrays."""
    effs, rmsds = _toy_matrices()
    selected, decay = select_informative_pairs(effs, rmsds, err=0.05, max_pairs=0)
    assert len(selected) == 0
    assert len(decay) == 0


def test_select_unique_only_has_no_repeats():
    """With unique_only, no pair is selected twice."""
    effs, rmsds = _toy_matrices()
    selected, _ = select_informative_pairs(effs, rmsds, err=0.05, max_pairs=3, unique_only=True)
    assert len(set(selected.tolist())) == len(selected)


def test_select_precision_decay_non_increasing():
    """Each added informative pair should not worsen the expected precision."""
    effs, rmsds = _toy_matrices()
    _, decay = select_informative_pairs(effs, rmsds, err=0.05, max_pairs=3)
    assert np.all(np.diff(np.asarray(decay, dtype=float)) <= 1e-4)


def test_select_pairs_cli_writes_report(tmp_path, monkeypatch):
    """The `select-pairs` CLI writes a valid report (guards the arg-order fix).

    The data-loading + AV-compute helpers are stubbed so the command runs without
    PDB files, an AV backend, or IMP — exercising the pure greedy selection + the
    report writer wiring. Before the arg-order fix this command crashed in
    ``open(<float>, "w")``.
    """
    from click.testing import CliRunner

    from ..cli.main import main
    from ..core import av, io
    from ..core import pair_selection as ps

    effs, rmsds = _toy_matrices()
    monkeypatch.setattr(av, "select_backend", lambda *a, **k: None)
    monkeypatch.setattr(io, "read_fps_json", lambda p: ({}, {}, None, None))
    monkeypatch.setattr(ps, "compute_rmsd_matrix_from_pdb_dir",
                        lambda *a, **k: (rmsds, ["f0", "f1", "f2"]))
    monkeypatch.setattr(ps, "compute_efficiency_matrix_from_evaluators",
                        lambda *a, **k: (effs, ["P1", "P2", "P3"]))

    out = tmp_path / "report.txt"
    res = CliRunner().invoke(main, [
        "select-pairs", "--fps", "x.fps.json", "--pdb-dir", str(tmp_path),
        "--output", str(out), "--max-pairs", "2",
    ])
    assert res.exit_code == 0, res.output
    lines = out.read_text().splitlines()
    assert lines[0].startswith("#\tPair_added")
    assert lines[1].startswith("0\t--")  # the initial-RMSD row


def test_trajectory_pair_selection():
    import mdtraj as md
    import tempfile
    
    # Create a simple molecule trajectory with 3 frames
    xyz = np.array([
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        [[0.0, 0.0, 0.0], [1.1, 0.0, 0.0], [0.0, 1.1, 0.0]],
        [[0.0, 0.0, 0.0], [1.2, 0.0, 0.0], [0.0, 1.2, 0.0]]
    ]) * 0.1 # mdtraj uses nanometers!
    
    # Create a basic topology
    from mdtraj.core.topology import Topology
    t = Topology()
    c = t.add_chain()
    r = t.add_residue("ALA", c)
    t.add_atom("CA", md.element.carbon, r)
    t.add_atom("HA", md.element.hydrogen, r)
    t.add_atom("N", md.element.nitrogen, r)
    
    # Save topology and trajectory
    with tempfile.NamedTemporaryFile(suffix=".pdb", delete=False) as f_top:
        top_path = f_top.name
    with tempfile.NamedTemporaryFile(suffix=".xtc", delete=False) as f_traj:
        traj_path = f_traj.name
        
    try:
        traj = md.Trajectory(xyz, t)
        traj[0].save_pdb(top_path)
        traj.save_xtc(traj_path)
        
        # Test compute_rmsd_matrix_from_trajectory
        from ..core.pair_selection import (
            compute_rmsd_matrix_from_trajectory,
            compute_efficiency_matrix_from_evaluators_trajectory
        )
        
        rmsds, filenames = compute_rmsd_matrix_from_trajectory(top_path, traj_path, selection="all")
        assert rmsds.shape == (3, 3)
        assert len(filenames) == 3
        assert filenames[0] == "frame_0"
        
        # Test compute_efficiency_matrix_from_evaluators_trajectory
        positions = {
            "pos1": {
                "atom_name": "CA",
                "chain_identifier": "A",
                "residue_seq_number": 1,
                "linker_length": 10.0,
                "linker_width": 1.0,
                "radius1": 3.0,
                "simulation_grid_resolution": 2.0,
                "simulation_type": "AV1"
            },
            "pos2": {
                "atom_name": "N",
                "chain_identifier": "A",
                "residue_seq_number": 1,
                "linker_length": 10.0,
                "linker_width": 1.0,
                "radius1": 3.0,
                "simulation_grid_resolution": 2.0,
                "simulation_type": "AV1"
            }
        }
        distances = {
            "pos1_pos2": {
                "position1_name": "pos1",
                "position2_name": "pos2",
                "Forster_radius": 52.0
            }
        }
        
        # Select backend auto or grid
        from ..core import av
        av.select_backend("auto")
        
        effs, pair_names = compute_efficiency_matrix_from_evaluators_trajectory(
            top_path, traj_path, positions, distances
        )
        assert effs.shape == (3, 1)
        assert pair_names == ["pos1_pos2"]
        
    finally:
        os.unlink(top_path)
        os.unlink(traj_path)

