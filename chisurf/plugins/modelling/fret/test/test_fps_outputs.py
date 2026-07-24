"""Headless tests for PRD-58 FPS-parity output + geometry helpers.

Covers requirements that were implemented but untested:

* R13 — the ``.pml`` / R-table / chi2-table output writers (``core.results``).
* R14 — ``core.io.compute_rmsd`` including optional Kabsch superposition.
* R15 — a real ``AVSizeEvaluator`` (radius of gyration), previously a bare alias
  of ``PositionEvaluator``.

All pure numpy — no IMP, AV backend, or external data.
"""
from __future__ import annotations

import numpy as np
import pytest

from ..core.av import AccessibleVolume
from ..core.io import compute_rmsd
from ..core.results import (
    SimulationResult,
    write_chi2_table,
    write_pymol_pml,
    write_r_table,
)
from ..evaluators import AVSizeEvaluator, PositionEvaluator


# --------------------------------------------------------------------------------------
# R13 — output writers
# --------------------------------------------------------------------------------------
def _results():
    return [
        SimulationResult(model_distances={"DA1": 45.0, "DA2": 60.0}),
        SimulationResult(model_distances={"DA1": 50.0, "DA2": 55.0}),
    ]


_DISTANCES = {
    "DA1": {"distance": 48.0, "error_neg": 5.0, "error_pos": 5.0},
    "DA2": {"distance": 58.0, "error_neg": 5.0, "error_pos": 5.0},
}


def test_write_r_table(tmp_path):
    out = tmp_path / "r_table.txt"
    write_r_table(_results(), _DISTANCES, str(out))
    lines = out.read_text().strip().splitlines()

    assert lines[0] == "trial\tDA1\tDA2"  # sorted distance keys
    assert len(lines) == 3  # header + 2 trials
    row0 = lines[1].split("\t")
    assert row0[0] == "0"
    assert float(row0[1]) == pytest.approx(45.0)
    assert float(row0[2]) == pytest.approx(60.0)


def test_write_chi2_table(tmp_path):
    out = tmp_path / "chi2_table.txt"
    write_chi2_table(_results(), _DISTANCES, None, str(out))
    lines = out.read_text().strip().splitlines()

    assert lines[0] == "trial\tDA1\tDA2\tchi2_total"
    assert len(lines) == 3
    row0 = [float(x) for x in lines[1].split("\t")[1:]]
    per_distance, total = row0[:-1], row0[-1]
    # the total column is the sum of the per-distance contributions
    assert total == pytest.approx(sum(per_distance))
    assert all(np.isfinite(v) for v in row0)


def test_write_pymol_pml(tmp_path):
    out = tmp_path / "view.pml"
    atoms_per_body = [np.zeros((3, 3)), np.zeros((4, 3))]
    write_pymol_pml(_results(), atoms_per_body, str(out), pdb_prefix="dock")
    text = out.read_text()

    assert "load dock_body_0.pdb, dock_body_0" in text
    assert "load dock_body_1.pdb, dock_body_1" in text
    assert text.strip().endswith("orient")


# --------------------------------------------------------------------------------------
# R14 — compute_rmsd (+ Kabsch)
# --------------------------------------------------------------------------------------
def _cloud(seed=0, n=25):
    rng = np.random.default_rng(seed)
    return rng.normal(size=(n, 3))


def test_compute_rmsd_identical_is_zero():
    a = _cloud()
    assert compute_rmsd(a, a.copy()) == pytest.approx(0.0)


def test_compute_rmsd_superpose_recovers_rigid_transform():
    a = _cloud()
    # a known rotation (90° about z) + translation
    theta = np.pi / 2
    rot = np.array(
        [[np.cos(theta), -np.sin(theta), 0.0],
         [np.sin(theta), np.cos(theta), 0.0],
         [0.0, 0.0, 1.0]]
    )
    b = a @ rot.T + np.array([10.0, -5.0, 3.0])

    assert compute_rmsd(a, b, superpose=False) > 1.0  # large without alignment
    assert compute_rmsd(a, b, superpose=True) == pytest.approx(0.0, abs=1e-9)


def test_compute_rmsd_selection_mask():
    a = _cloud()
    b = a.copy()
    b[0] += 100.0  # corrupt one atom
    mask = np.ones(len(a), dtype=bool)
    mask[0] = False
    assert compute_rmsd(a, b, selection_mask=mask) == pytest.approx(0.0)
    assert compute_rmsd(a, b) > 1.0  # unmasked sees the outlier


def test_compute_rmsd_shape_mismatch_raises():
    with pytest.raises(ValueError):
        compute_rmsd(_cloud(n=5), _cloud(n=6))


# --------------------------------------------------------------------------------------
# R15 — AVSizeEvaluator (radius of gyration), no longer an alias
# --------------------------------------------------------------------------------------
def _make_av(coords, weights=None):
    coords = np.asarray(coords, dtype=np.float64)
    n = len(coords)
    w = np.ones(n) if weights is None else np.asarray(weights, dtype=np.float64)
    points = np.zeros((n, 4), dtype=np.float64)
    points[:, :3] = coords
    points[:, 3] = w
    return AccessibleVolume(
        points=points,
        density=np.ones((1, 1, 1), dtype=np.float32),
        grid_origin=np.zeros(3),
        grid_step=1.0,
        grid_shape=(1, 1, 1),
        attachment_point=coords[0].copy(),
    )


def test_av_size_is_radius_of_gyration():
    # two equal-weight points at x = ±3 → mean 0, Rg = 3
    av = _make_av([[3.0, 0.0, 0.0], [-3.0, 0.0, 0.0]])
    ev = AVSizeEvaluator("size_A", "A")
    res = ev.evaluate({"A": av})
    assert res.value == pytest.approx(3.0)
    assert res.unit == "Å"


def test_av_size_is_not_point_count():
    # AVSizeEvaluator must be a distinct metric, not the old PositionEvaluator alias
    av = _make_av([[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 2.0, 0.0]])
    size = AVSizeEvaluator("s", "A").evaluate({"A": av}).value
    count = PositionEvaluator("c", "A").evaluate({"A": av}).value
    assert count == pytest.approx(3.0)
    assert size != pytest.approx(count)
    assert AVSizeEvaluator is not PositionEvaluator


def test_av_size_empty_is_zero():
    empty = _make_av([[0.0, 0.0, 0.0]])
    empty.points = np.zeros((0, 4))  # no points
    res = AVSizeEvaluator("s", "A").evaluate({"A": empty})
    assert res.value == pytest.approx(0.0)
