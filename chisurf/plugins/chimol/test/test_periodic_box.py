"""A periodic box, where a trajectory carries one.

What was missing
----------------
chimol did not handle periodic boundaries at all, and the box was discarded one
line after being read: ``load_trajectory_frames`` ends
``xyz, _, _ = read_dcd(path)``. The DCD reader parses the per-frame unit cell
perfectly well; nothing downstream ever saw it. There is still no ``pbc``,
``wrap`` or ``unwrap`` command among the 180 -- the only ``cell`` is
*crystallographic*, for CRYST1 symmetry mates, which is a different thing.

What is fixed here is the case that visibly breaks a picture, and it is the one
VMD images for too: **trajectory averaging across a box wall**. An atom that
steps over the wall reappears a whole cell away, so a plain mean of "this side,
this side, the other side" places it in the *middle of the box*. One frame in
which part of the molecule explodes across the cell, with nothing raised.

What is covered
---------------
Orthorhombic **and** triclinic. The shift is taken in *fractional* coordinates,
so a sheared cell images as correctly as a rectangular one -- and the
orthorhombic case is not special-cased, since for a 90-degree cell the matrix is
diagonal and the general path reduces to dividing by the edge lengths.

The window is also **clamped rather than shrunk** at the ends of a trajectory,
so smoothing strength stays constant there, and the box is published as the
object's unit cell so ``cell`` draws it -- republished per frame, because an NPT
box breathes.

Unwrapping is covered too: ``pbc unwrap`` makes each molecule whole across a
wall and ``pbc wrap`` puts it back **as a unit**, both over fragments of the
bond graph -- wrapping atom by atom is what splits a molecule across the picture
in the first place. And ``zoom`` includes a *shown* cell in its fit, so a box
much larger than its contents no longer runs off the viewport.

What is deliberately not covered
--------------------------------
``pbc unwrap`` seeds each fragment from its first atom rather than walking the
bond graph, so a fragment spanning more than half the cell -- a polymer threaded
through the whole box -- is not unwrapped correctly. Such a fragment has no
unambiguous unwrapping anyway.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chimol.io.structure import load_trajectory_cell
from chimol.core.services.trajectory import _minimum_image, _smooth_frame

DCD = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "trajectory" / "dcd"
)
WITH_CELL = DCD / "triclinic_cell.dcd"
WITHOUT_CELL = DCD / "hgbp1_transition.dcd"


def test_a_trajectory_with_a_box_reports_one():
    """The reader has always parsed it; now something asks."""
    if not WITH_CELL.is_file():
        pytest.skip("the triclinic fixture is not present")
    cell = load_trajectory_cell(WITH_CELL)
    assert cell is not None, "the unit cell was dropped again"
    lengths, angles = cell
    assert lengths.shape[1] == 3 and angles.shape[1] == 3
    assert np.allclose(lengths[0], [30.0, 40.0, 50.0])


def test_a_trajectory_without_a_box_reports_none():
    """Most trajectories have none, and that must not look like a failure."""
    if not WITHOUT_CELL.is_file():
        pytest.skip("the fixture is not present")
    assert load_trajectory_cell(WITHOUT_CELL) is None


def _wobble_across_the_wall():
    """One atom stepping back and forth over the x wall of a 30 A box."""
    frames = np.zeros((5, 1, 3))
    frames[:, 0, 0] = [29.5, 0.5, 29.6, 0.4, 29.7]
    box = np.tile([30.0, 40.0, 50.0], (5, 1))
    angles = np.full((5, 3), 90.0)
    return frames, (box, angles)


def test_averaging_across_a_wall_lands_in_the_box_centre_without_a_box():
    """The bug, stated as the number it produces.

    Kept as a test rather than a comment because it is the whole justification
    for the imaging below: 16.6 is not a rounding error, it is the middle of the
    cell and nowhere near the atom.
    """
    frames, _ = _wobble_across_the_wall()
    naive = _smooth_frame(frames, 2, frames[2], 5, None)
    assert 10.0 < float(naive[0, 0]) < 20.0, (
        "expected the naive mean to land near the box centre"
    )


def test_averaging_across_a_wall_stays_with_the_atom_when_imaged():
    """With the box, the average sits where the atom actually is."""
    frames, cell = _wobble_across_the_wall()
    imaged = _smooth_frame(frames, 2, frames[2], 5, cell)
    x = float(imaged[0, 0]) % 30.0
    assert min(x, 30.0 - x) < 1.0, (
        f"the averaged atom is at x={x:.2f}; it should sit near the wall at ~29.6"
    )


def test_a_frame_that_did_not_move_is_untouched():
    """Imaging must be a no-op for a molecule that never crosses a wall."""
    frames = np.zeros((3, 4, 3))
    frames[:, :, 0] = [[10.0, 11.0, 12.0, 13.0]] * 3
    box = (np.tile([30.0, 40.0, 50.0], (3, 1)), np.full((3, 3), 90.0))
    assert np.array_equal(_minimum_image(frames, 1, box), frames)


def test_a_triclinic_cell_images_along_its_own_vectors():
    """A sheared box images too, and this is the test that proves it.

    Three atoms displaced by exactly one cell *vector* each must all collapse
    onto the reference. Doing this in Cartesian space instead -- rounding
    against the edge lengths -- moves them somewhere else entirely, and for a
    90-degree box the two agree, which is how a wrong transpose survives.
    """
    from chimol.core.services.trajectory import _cell_matrix

    lengths = np.array([30.0, 40.0, 50.0])
    angles = np.array([70.0, 80.0, 110.0])
    matrix = _cell_matrix(lengths, angles)
    assert matrix is not None

    base = np.array([1.0, 2.0, 3.0])
    frames = np.zeros((4, 1, 3))
    frames[0, 0] = base
    for axis in range(3):
        frames[axis + 1, 0] = base + matrix[axis]

    imaged = _minimum_image(
        frames, 0, (np.tile(lengths, (4, 1)), np.tile(angles, (4, 1)))
    )
    assert np.allclose(imaged[:, 0, :], base), (
        f"cell-vector displacements did not image back: {imaged[:, 0, :]}"
    )


def test_the_cell_matrix_has_the_right_volume():
    """A sanity check on the six-numbers-to-three-vectors construction."""
    from chimol.core.services.trajectory import _cell_matrix

    matrix = _cell_matrix(np.array([10.0, 10.0, 10.0]), np.full(3, 90.0))
    assert np.isclose(abs(np.linalg.det(matrix)), 1000.0)
    skewed = _cell_matrix(np.array([30.0, 40.0, 50.0]), np.array([70.0, 80.0, 110.0]))
    # Strictly less than the rectangular box of the same edges: shearing a cell
    # cannot add volume.
    assert 0.0 < abs(np.linalg.det(skewed)) < 30.0 * 40.0 * 50.0


def test_a_degenerate_cell_is_refused_rather_than_producing_nonsense():
    """Zero edges and flat angles have no inverse to image with."""
    from chimol.core.services.trajectory import _cell_matrix

    assert _cell_matrix(np.array([0.0, 10.0, 10.0]), np.full(3, 90.0)) is None
    assert _cell_matrix(np.array([10.0, 10.0, 10.0]), np.array([90.0, 90.0, 0.0])) is None
    assert _cell_matrix(np.array([10.0, 10.0, 10.0]), np.array([170.0, 170.0, 170.0])) is None


def test_the_averaging_window_is_clamped_rather_than_shrunk():
    """Smoothing strength must not weaken at the ends of a trajectory.

    Taking ``frames[max(0, i-half) : min(n, i+half+1)]`` narrows the window near
    either end, so the first and last frames come out jitterier than the middle
    -- which reads as the setting not working there. Repeating the end frame
    keeps the window the width it was asked for, as VMD does.
    """
    # A ramp: frame k sits at x = k. At frame 0 with a five-frame window, a
    # clamped window averages [0,0,0,1,2] = 0.6 under a flat mean, while a
    # shrunk one averages [0,1,2] = 1.0.
    frames = np.zeros((10, 1, 3))
    frames[:, 0, 0] = np.arange(10.0)
    smoothed = _smooth_frame(frames, 0, frames[0], 5, None)
    assert float(smoothed[0, 0]) < 0.8, (
        f"the window shrank at the start: x={float(smoothed[0, 0]):.2f}"
    )


@pytest.mark.parametrize("cell", [None, ("nonsense",), (np.zeros((5, 3)), None)])
def test_an_unusable_box_is_ignored_rather_than_raising(cell):
    """A missing or malformed box must degrade to the plain mean.

    A zero-length box is in this list on purpose: dividing by it would give
    infinities, and a viewer that shows nothing is worse than one that shows an
    unimaged average.
    """
    frames, _ = _wobble_across_the_wall()
    assert np.array_equal(_minimum_image(frames, 2, cell), frames)


# --------------------------------------------------------------------------- #
# Unwrapping
# --------------------------------------------------------------------------- #
def _split_chain():
    """A four-atom chain straddling the x wall of a 30 A box, 0.8 A bonds."""
    coords = np.array(
        [[29.0, 5.0, 5.0], [29.8, 5.0, 5.0], [0.6, 5.0, 5.0], [1.4, 5.0, 5.0]]
    )
    bonds = np.array([[0, 1], [1, 2], [2, 3]])
    return coords, bonds


def test_a_molecule_on_a_wall_arrives_split():
    """The premise, stated as a number: two of the bonds look 29 A long."""
    coords, _ = _split_chain()
    steps = np.abs(np.diff(coords[:, 0]))
    assert steps.max() > 25.0, "the fixture is supposed to straddle the wall"


def test_unwrap_makes_the_molecule_whole():
    from chimol.analysis.periodic import (
        cell_matrix, fragments, unwrap_coordinates,
    )

    coords, bonds = _split_chain()
    matrix = cell_matrix([30.0, 40.0, 50.0], [90.0, 90.0, 90.0])
    groups = fragments(4, bonds=bonds)
    assert len(groups) == 1, "the bond graph is one fragment"

    whole = unwrap_coordinates(coords, matrix, groups)
    steps = np.abs(np.diff(whole[:, 0]))
    assert np.allclose(steps, 0.8), f"bonds are still broken: {steps}"


def test_wrap_moves_a_molecule_as_a_unit():
    """Back inside the box, and still in one piece.

    The second half is the point. Wrapping atom by atom puts every atom inside
    the box and tears the molecule in half doing it, which is the state the
    files arrive in.
    """
    from chimol.analysis.periodic import (
        cell_matrix, fragments, unwrap_coordinates, wrap_coordinates,
    )

    coords, bonds = _split_chain()
    matrix = cell_matrix([30.0, 40.0, 50.0], [90.0, 90.0, 90.0])
    groups = fragments(4, bonds=bonds)
    whole = unwrap_coordinates(coords, matrix, groups)
    back = wrap_coordinates(whole, matrix, groups)

    assert np.abs(np.diff(back[:, 0])).max() < 5.0, "wrapping tore the molecule"
    centre = back.mean(axis=0) @ np.linalg.inv(matrix)
    assert np.all((centre >= -1e-9) & (centre < 1.0 + 1e-9)), (
        f"the fragment centre is outside the box: {centre}"
    )


def test_unwrap_works_in_a_sheared_cell():
    """Two atoms one cell vector apart come back together, triclinic or not."""
    from chimol.analysis.periodic import (
        cell_matrix, unwrap_coordinates,
    )

    matrix = cell_matrix([30.0, 40.0, 50.0], [70.0, 80.0, 110.0])
    base = np.array([1.0, 2.0, 3.0])
    pair = np.vstack((base, base + matrix[1]))
    whole = unwrap_coordinates(pair, matrix, [np.array([0, 1])])
    assert np.allclose(whole[0], whole[1])


def test_fragments_fall_back_when_there_are_no_bonds():
    """A bead model has no bonds, and must still move in sensible pieces.

    Chains before residues: a residue-wise wrap would tear a polymer at every
    peptide bond, which is worse than not wrapping at all.
    """
    from chimol.analysis.periodic import fragments

    chains = np.array(["A", "A", "B", "B", "B"])
    residues = np.array([1, 2, 3, 4, 5])
    grouped = fragments(5, bonds=None, chains=chains, res_ids=residues)
    assert [list(g) for g in grouped] == [[0, 1], [2, 3, 4]]

    grouped = fragments(5, bonds=None, chains=None, res_ids=residues)
    assert len(grouped) == 5

    assert [list(g) for g in fragments(3)] == [[0, 1, 2]]
