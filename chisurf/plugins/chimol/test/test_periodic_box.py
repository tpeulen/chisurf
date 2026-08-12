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

What is deliberately not covered
--------------------------------
Only orthorhombic boxes are imaged. A triclinic minimum image needs the full
cell matrix and its inverse per frame, and the case that breaks a picture is
handled by the rectangular one -- so a triclinic box is left alone rather than
imaged wrongly. ``triclinic_cell.dcd`` is used below to pin exactly that.

Nothing here unwraps a molecule for *display*: a protein straddling the wall is
still drawn in two pieces. That wants a connectivity-aware unwrap and a `pbc`
command, and is not done.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.io.structure import load_trajectory_cell
from chisurf.plugins.chimol.chimol.renderer.view import _minimum_image, _smooth_frame

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


def test_a_triclinic_box_is_left_alone_rather_than_imaged_wrongly():
    """Non-orthogonal cells are out of scope, and must not be half-handled."""
    frames, (box, _angles) = _wobble_across_the_wall()
    triclinic = (box, np.tile([70.0, 80.0, 110.0], (5, 1)))
    assert np.array_equal(_minimum_image(frames, 2, triclinic), frames)


@pytest.mark.parametrize("cell", [None, ("nonsense",), (np.zeros((5, 3)), None)])
def test_an_unusable_box_is_ignored_rather_than_raising(cell):
    """A missing or malformed box must degrade to the plain mean.

    A zero-length box is in this list on purpose: dividing by it would give
    infinities, and a viewer that shows nothing is worse than one that shows an
    unimaged average.
    """
    frames, _ = _wobble_across_the_wall()
    assert np.array_equal(_minimum_image(frames, 2, cell), frames)
