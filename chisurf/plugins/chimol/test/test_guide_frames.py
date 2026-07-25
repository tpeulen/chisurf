"""The per-residue guide frame, against PyMOL's algorithm.

chimol used to take the ribbon's tangents from the finished spline, which leaves
nowhere to put the two conditioning steps PyMOL runs per residue — and both are
on by default and visible. These tests pin each pass separately, because the
whole reason the stage exists is that the passes cannot be expressed downstream.

Reference: ``layer2/RepCartoon.cpp``, functions
``RepCartoonComputeDifferencesAndNormals``, ``RepCartoonComputeTangents``,
``RepCartoonRefineNormals`` and ``RepCartoonFlattenSheetsRefineTips``.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.geometry.guide_frames import (
    build_guide_frames,
    differences_and_normals,
    refine_normals,
    refine_sheet_tips,
    tangents_from_normals,
)


def _chain(n: int = 8, rise: float = 3.3) -> np.ndarray:
    pts = np.zeros((n, 3))
    pts[:, 0] = rise * np.arange(n)
    return pts


# --------------------------------------------------------------------------- #
# Differences and normals
# --------------------------------------------------------------------------- #
def test_normals_point_from_each_residue_to_the_next():
    pts = _chain(5)
    _, normals, lengths = differences_and_normals(pts, np.zeros(5, int))
    assert np.allclose(normals[:-1], [1.0, 0.0, 0.0])
    assert np.allclose(lengths[:-1], 3.3)
    # The last entry has no successor, so it stays zero.
    assert np.allclose(normals[-1], 0.0)
    assert lengths[-1] == 0.0


def test_a_segment_break_zeroes_the_direction_across_it():
    """Two chains must not be joined by a direction that spans the gap."""
    pts = _chain(6)
    segments = np.array([0, 0, 0, 1, 1, 1])
    _, normals, lengths = differences_and_normals(pts, segments)
    assert np.allclose(normals[2], 0.0)
    assert lengths[2] == 0.0
    assert np.allclose(normals[1], [1.0, 0.0, 0.0])


def test_a_degenerate_step_copies_the_previous_direction():
    """PyMOL copies rather than leaving a zero vector mid-chain."""
    pts = _chain(5)
    pts[3] = pts[2]  # two residues on top of each other
    _, normals, _ = differences_and_normals(pts, np.zeros(5, int))
    assert np.allclose(normals[2], normals[1])


# --------------------------------------------------------------------------- #
# Tangents
# --------------------------------------------------------------------------- #
def test_an_interior_tangent_is_the_sum_of_both_directions():
    """``add3f(nv[a], nv[a-1])`` then normalise -- a head-to-tail sum."""
    pts = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [1.0, 2.0, 0.0]]
    )
    _, normals, _ = differences_and_normals(pts, np.zeros(4, int))
    tangents = tangents_from_normals(normals, np.zeros(4, int))
    expected = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
    assert np.allclose(tangents[1], expected)


def test_the_ends_take_the_one_direction_they_have():
    pts = _chain(4)
    _, normals, _ = differences_and_normals(pts, np.zeros(4, int))
    tangents = tangents_from_normals(normals, np.zeros(4, int))
    assert np.allclose(tangents[0], [1.0, 0.0, 0.0])
    assert np.allclose(tangents[-1], [1.0, 0.0, 0.0])


def test_tangents_are_unit_length():
    pts = np.cumsum(np.random.default_rng(0).normal(size=(10, 3)), axis=0)
    _, normals, _ = differences_and_normals(pts, np.zeros(10, int))
    tangents = tangents_from_normals(normals, np.zeros(10, int))
    assert np.allclose(np.linalg.norm(tangents, axis=1), 1.0)


# --------------------------------------------------------------------------- #
# Refine normals: the ribbon must not flip face
# --------------------------------------------------------------------------- #
def test_alternating_up_vectors_are_made_consistent():
    """This is what stops the ribbon flipping between consecutive residues."""
    n = 9
    pts = _chain(n)
    ups = np.zeros((n, 3))
    ups[:, 2] = (-1.0) ** np.arange(n)   # every neighbour opposed

    frames = build_guide_frames(pts, ups)
    dots = np.einsum(
        "ij,ij->i", frames.orientations[1:-2], frames.orientations[2:-1]
    )
    assert dots.min() > 0.9


def test_a_helix_is_not_offered_the_inverted_candidate():
    """Inverting inside a helix would confuse its inside and outside."""
    n = 9
    pts = _chain(n)
    ups = np.zeros((n, 3))
    ups[:, 2] = (-1.0) ** np.arange(n)
    helix = np.ones(n, dtype=bool)

    frames = build_guide_frames(pts, ups, is_helix=helix)
    # With no inversion available the alternation survives, which is correct:
    # the helix's own twist is the signal, not noise to be flattened.
    dots = np.einsum(
        "ij,ij->i", frames.orientations[1:-2], frames.orientations[2:-1]
    )
    assert dots.min() < 0.0


def test_orientations_come_out_perpendicular_to_the_tangent():
    n = 8
    pts = np.cumsum(np.random.default_rng(1).normal(size=(n, 3)), axis=0)
    ups = np.tile([0.3, 0.5, 0.8], (n, 1))
    frames = build_guide_frames(pts, ups)
    along = np.einsum(
        "ij,ij->i", frames.orientations[1:-1], frames.tangents[1:-1]
    )
    assert np.abs(along).max() < 1e-9


def test_refine_normals_leaves_a_short_chain_alone():
    ups = np.tile([0.0, 0.0, 1.0], (2, 1))
    out = refine_normals(
        ups, np.zeros((2, 3)), np.zeros((2, 3)), np.zeros(2, int),
        np.zeros(2, bool),
    )
    assert np.allclose(out, ups)


# --------------------------------------------------------------------------- #
# Refine tips: the arrowhead must point along the strand
# --------------------------------------------------------------------------- #
def _strand_into_a_loop() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return a strand along +x whose flanking loop peels away in +y."""
    n = 9
    pts = np.zeros((n, 3))
    pts[:, 0] = np.arange(n) * 3.3
    pts[6:, 1] = np.arange(1, n - 5) * 3.0
    sheet = np.zeros(n, dtype=bool)
    sheet[2:6] = True
    return pts, sheet, np.zeros(n, dtype=int)


def test_a_strand_tip_is_aimed_along_the_strand():
    """Without this the tip takes its direction from the loop it joins."""
    pts, sheet, segments = _strand_into_a_loop()
    _, normals, _ = differences_and_normals(pts, segments)
    tangents = tangents_from_normals(normals, segments)

    before = tangents[5].copy()
    after = refine_sheet_tips(tangents, sheet, segments, weight=10.0)[5]
    # The strand runs along +x; the loop pulls +y into the tangent.
    assert abs(before[1]) > 0.3
    assert abs(after[1]) < 0.05
    assert after[0] > 0.99


def test_the_weight_controls_how_hard_the_tip_is_pulled():
    pts, sheet, segments = _strand_into_a_loop()
    _, normals, _ = differences_and_normals(pts, segments)
    tangents = tangents_from_normals(normals, segments)

    gentle = refine_sheet_tips(tangents, sheet, segments, weight=1.0)[5]
    firm = refine_sheet_tips(tangents, sheet, segments, weight=10.0)[5]
    assert abs(firm[1]) < abs(gentle[1])


def test_zero_weight_changes_nothing():
    pts, sheet, segments = _strand_into_a_loop()
    _, normals, _ = differences_and_normals(pts, segments)
    tangents = tangents_from_normals(normals, segments)
    assert np.allclose(
        refine_sheet_tips(tangents, sheet, segments, weight=0.0), tangents
    )


def test_only_strand_tips_move():
    """A residue in the middle of a strand keeps its tangent."""
    pts, sheet, segments = _strand_into_a_loop()
    _, normals, _ = differences_and_normals(pts, segments)
    tangents = tangents_from_normals(normals, segments)
    after = refine_sheet_tips(tangents, sheet, segments, weight=10.0)
    # Residue 3 and 4 are interior to the strand and unchanged.
    assert np.allclose(after[3], tangents[3])
    assert np.allclose(after[4], tangents[4])
    assert not np.allclose(after[5], tangents[5])


def test_tips_are_not_refined_across_a_chain_break():
    pts, sheet, _ = _strand_into_a_loop()
    segments = np.zeros(pts.shape[0], dtype=int)
    segments[5:] = 1
    _, normals, _ = differences_and_normals(pts, segments)
    tangents = tangents_from_normals(normals, segments)
    after = refine_sheet_tips(tangents, sheet, segments, weight=10.0)
    assert np.allclose(after[5], tangents[5])


# --------------------------------------------------------------------------- #
# The whole stage
# --------------------------------------------------------------------------- #
def test_the_frame_is_orthonormal_where_it_is_defined():
    pts, sheet, _ = _strand_into_a_loop()
    ups = np.tile([0.0, 0.0, 1.0], (pts.shape[0], 1))
    frames = build_guide_frames(pts, ups, is_sheet=sheet)

    interior = slice(1, -1)
    assert np.allclose(
        np.linalg.norm(frames.tangents[interior], axis=1), 1.0
    )
    assert np.allclose(
        np.linalg.norm(frames.orientations[interior], axis=1), 1.0
    )
    assert np.abs(
        np.einsum(
            "ij,ij->i", frames.tangents[interior], frames.orientations[interior]
        )
    ).max() < 1e-9


def test_lengths_are_the_residue_spacing():
    pts = _chain(6, rise=3.8)
    ups = np.tile([0.0, 0.0, 1.0], (6, 1))
    frames = build_guide_frames(pts, ups)
    assert np.allclose(frames.lengths[:-1], 3.8)


@pytest.mark.parametrize("n", [0, 1, 2])
def test_a_chain_too_short_to_have_an_interior_is_handled(n):
    pts = _chain(n) if n else np.zeros((0, 3))
    ups = np.zeros((n, 3))
    frames = build_guide_frames(pts, ups)
    assert frames.positions.shape[0] == n
    assert frames.tangents.shape == (n, 3)
