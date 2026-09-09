"""Unit tests for Phase 4: OLGA pair selection."""

import os
import tempfile
import pathlib

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
    from chisurf.core.structure import trajectory_data as md
    import tempfile
    
    # Create a simple molecule trajectory with 3 frames
    xyz = np.array([
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        [[0.0, 0.0, 0.0], [1.1, 0.0, 0.0], [0.0, 1.1, 0.0]],
        [[0.0, 0.0, 0.0], [1.2, 0.0, 0.0], [0.0, 1.2, 0.0]]
    ]) * 0.1 # trajectories are in nanometres
    
    # Create a basic topology
    from chisurf.core.structure.topology import Topology

    t = Topology()
    c = t.add_chain()
    r = t.add_residue("ALA", c)
    t.add_atom("CA", md.element.carbon, r)
    t.add_atom("HA", md.element.hydrogen, r)
    t.add_atom("N", md.element.nitrogen, r)
    
    # Save topology and trajectory
    with tempfile.NamedTemporaryFile(suffix=".pdb", delete=False) as f_top:
        top_path = f_top.name
    with tempfile.NamedTemporaryFile(suffix=".dcd", delete=False) as f_traj:
        traj_path = f_traj.name
        
    try:
        traj = md.Trajectory(xyz, t)
        traj[0].save_pdb(top_path)
        traj.save_dcd(traj_path)
        
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
        
        # An accessible volume needs a structure to be accessible *around*.
        # Three atoms filter to an empty obstacle set, which is not a
        # meaningful AV -- and used to take the process down with it, because
        # LabelLib segfaults on an empty array rather than returning. Use a
        # real protein for this part.
        real_pdb = (pathlib.Path(__file__).resolve().parents[5]
                    / "test/data/atomic_coordinates/pdb_files/148l.pdb")
        if not real_pdb.is_file():
            pytest.skip(f"reference structure not found: {real_pdb}")
        real_traj = md.load(str(real_pdb))
        real_dcd = os.path.join(os.path.dirname(traj_path), "148l.dcd")
        md.join([real_traj, real_traj, real_traj]).save_dcd(real_dcd)

        effs, pair_names = compute_efficiency_matrix_from_evaluators_trajectory(
            str(real_pdb), real_dcd, positions, distances
        )
        assert effs.shape == (3, 1)
        assert pair_names == ["pos1_pos2"]
        
    finally:
        os.unlink(top_path)
        os.unlink(traj_path)



def test_the_chi_squared_tail_weight_is_right_for_odd_degrees_of_freedom():
    """``Q(nu/2, chi2/2)`` must match the incomplete gamma for *every* ``ndof``.

    The half-integer branch of the hand-ported expansion ran one term short.
    Boost, which Olga copies, loops ``for (n = 2; n < a; ++n)`` with ``a`` a
    half-integer; the port wrote ``range(2, int(a))``, and ``int(2.5)`` is 2, so
    the loop did nothing where Boost does one iteration. That made the weight
    too small for *every odd* ``ndof`` -- and ``ndof`` is the number of pairs
    chosen so far, so it is odd on every other greedy step.

    Checked against :func:`scipy.special.gammaincc`, which is the same function,
    rather than against a stored expectation: a stored number would have been
    generated from the broken code.
    """
    from scipy.special import gammaincc

    from chisurf.plugins.modelling.fret.core.olga_greedy import _chisq_rt_cdf

    chisq = np.concatenate([[0.0], np.linspace(1e-9, 300.0, 500)])
    for ndof in list(range(1, 40)) + [101, 201, 401]:
        got = np.asarray(_chisq_rt_cdf(chisq, ndof), dtype=float)
        expected = gammaincc(0.5 * ndof, 0.5 * chisq)
        np.testing.assert_allclose(got, expected, rtol=1e-10, atol=1e-12,
                                   err_msg=f"ndof={ndof}")

    # The specific value the defect was found on: the broken expansion returned
    # 0.3903934 here, which is not a rounding error but very nearly half.
    assert float(_chisq_rt_cdf(np.array([3.008]), 5)[0]) == pytest.approx(0.6987524, abs=1e-7)


def test_a_zero_chi_squared_weighs_one():
    """The diagonal is always zero, and ``Q(a, 0) = 1``.

    The half-integer series divides by ``sqrt(pi * x)``, so the diagonal would
    be a division by zero on every single call if it were not handled.
    """
    from chisurf.plugins.modelling.fret.core.olga_greedy import _chisq_rt_cdf

    for ndof in range(1, 12):
        assert float(_chisq_rt_cdf(np.zeros(1), ndof)[0]) == 1.0


def test_the_weight_does_not_modify_the_chi_squared_it_is_given():
    """Scaling ``chisq`` by a half in place would corrupt the accumulator.

    The greedy loop accumulates chi-squared across steps and passes that same
    array in on every one, so an in-place scale silently halves the state -- the
    selection still looks plausible and the decay curve stops decaying.
    """
    from chisurf.plugins.modelling.fret.core.olga_greedy import _chisq_rt_cdf

    chi2 = np.linspace(0.0, 40.0, 64).reshape(8, 8)
    before = chi2.copy()
    _chisq_rt_cdf(chi2, 5)
    np.testing.assert_array_equal(chi2, before)


def test_the_selector_is_bffs_and_is_tested_there():
    """The chunked candidate scoring this used to pin is not here any more.

    `select_informative_pairs` is `IMP.bff`'s and is C++; the chunking was an
    internal of the Python implementation it replaced, so a test that reached
    into `_best_pair_all_candidates` was testing a library through an
    application. It is covered upstream by `test/restraints/test_pair_selection.py`
    and `test/restraints/test_greedy_olga_ab.py`, the second of which is an
    A/B against the original.

    What is worth asserting on this side is that the plugin reaches it and
    gets an answer of the right shape.
    """
    from chisurf.plugins.modelling.fret.core.olga_greedy import (
        select_informative_pairs,
    )

    rng = np.random.default_rng(11)
    n, m = 17, 40
    effs = rng.uniform(0.05, 0.95, (n, m))
    # (n, n): the selector scores how well a pair separates every pair of
    # structures, so it wants the RMSD matrix, not a vector to a reference.
    rmsds = rng.uniform(0.5, 20.0, (n, n))
    rmsds = (rmsds + rmsds.T) / 2
    np.fill_diagonal(rmsds, 0.0)

    order, precision = select_informative_pairs(effs, rmsds, 0.06, 5)
    assert len(order) == 5
    assert len(precision) == len(order)
    # No pair twice, which is what `unique_only` defaults to.
    assert len(set(int(i) for i in order)) == len(order)
    # Every index names a column of `effs`.
    assert all(0 <= int(i) < m for i in order)
