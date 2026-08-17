"""PyMOL's ``lines`` and ``nonbonded``, the two it shows by default.

chimol had neither. What it called ``lines`` was the alpha-carbon trace, which is
a different thing: a PyMOL user typing ``show lines`` expects every bond, not a
smoothed backbone. These are also the representations you fall back to when a
surface or cartoon is too heavy to rotate, so their absence was felt.
"""

from __future__ import annotations

import numpy as np
import pytest

from chimol.geometry.wireframe import (
    bond_line_segments,
    nonbonded_crosses,
    unbonded_mask,
)

_COORDS = np.array(
    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [9.0, 9.0, 9.0]]
)
_BONDS = np.array([[0, 1], [1, 2]])


# --------------------------------------------------------------------------- #
# Bond lines
# --------------------------------------------------------------------------- #
def test_each_bond_becomes_two_half_segments():
    """Split at the midpoint so each half carries its own atom's colour."""
    verts, _ = bond_line_segments(_COORDS, _BONDS)
    assert verts.shape == (2 * 4, 3)
    # First bond: 0 -> mid -> mid -> 1
    assert np.allclose(verts[0], _COORDS[0])
    assert np.allclose(verts[1], [0.5, 0.0, 0.0])
    assert np.allclose(verts[2], [0.5, 0.0, 0.0])
    assert np.allclose(verts[3], _COORDS[1])


def test_each_half_takes_its_own_atoms_colour():
    """A red-to-blue bond is half red and half blue, as in PyMOL."""
    colors = np.array(
        [[1.0, 0.0, 0.0, 1.0], [0.0, 0.0, 1.0, 1.0],
         [0.0, 1.0, 0.0, 1.0], [1.0, 1.0, 1.0, 1.0]]
    )
    _, cols = bond_line_segments(_COORDS, _BONDS, colors)
    assert cols is not None
    assert np.allclose(cols[0], colors[0]) and np.allclose(cols[1], colors[0])
    assert np.allclose(cols[2], colors[1]) and np.allclose(cols[3], colors[1])


def test_unsplit_mode_gives_one_segment_per_bond():
    verts, _ = bond_line_segments(_COORDS, _BONDS, split_at_midpoint=False)
    assert verts.shape == (2 * 2, 3)


def test_out_of_range_and_self_bonds_are_dropped():
    bonds = np.array([[0, 1], [0, 0], [0, 99], [-1, 2]])
    verts, _ = bond_line_segments(_COORDS, bonds)
    assert verts.shape[0] == 4      # only the first bond survives


def test_no_bonds_draws_nothing():
    verts, cols = bond_line_segments(_COORDS, np.zeros((0, 2), dtype=int))
    assert verts.shape == (0, 3)
    assert cols is None


def test_mismatched_colours_are_ignored_rather_than_crashing():
    verts, cols = bond_line_segments(_COORDS, _BONDS, np.zeros((2, 4)))
    assert verts.shape[0] == 8
    assert cols is None


# --------------------------------------------------------------------------- #
# Nonbonded
# --------------------------------------------------------------------------- #
def test_atoms_in_no_bond_are_the_nonbonded_set():
    mask = unbonded_mask(4, _BONDS)
    assert mask.tolist() == [False, False, False, True]


def test_everything_is_nonbonded_without_bonds():
    assert unbonded_mask(3, None).all()


def test_a_cross_is_three_segments():
    verts, _ = nonbonded_crosses(np.zeros((1, 3)), size=0.5)
    assert verts.shape == (6, 3)
    # One segment per axis, centred on the atom.
    assert np.allclose(verts[0], [-0.5, 0.0, 0.0])
    assert np.allclose(verts[1], [0.5, 0.0, 0.0])
    assert np.allclose(verts[3], [0.0, 0.5, 0.0])
    assert np.allclose(verts[5], [0.0, 0.0, 0.5])


def test_cross_colours_repeat_per_atom():
    colors = np.array([[1.0, 0.0, 0.0, 1.0], [0.0, 1.0, 0.0, 1.0]])
    _, cols = nonbonded_crosses(np.zeros((2, 3)), colors, size=0.25)
    assert cols is not None
    assert cols.shape == (12, 4)
    assert np.allclose(cols[:6], colors[0])
    assert np.allclose(cols[6:], colors[1])


def test_a_zero_size_cross_draws_nothing():
    verts, _ = nonbonded_crosses(np.zeros((3, 3)), size=0.0)
    assert verts.shape == (0, 3)


# --------------------------------------------------------------------------- #
# In the viewer
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def view(qapp):
    import pathlib

    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chimol.io.structure import _read_full_model
    from chimol.core.viewer import Viewer

    pdb = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )
    v = Viewer()
    v.add_structure(
        _read_full_model(cs_struct.Structure, pdb), name="148l",
        source_path=str(pdb),
    )
    return v


def _ids(view) -> list[str]:
    scene = view.get_current_scene()
    return [] if scene is None else [o.id.split(":")[-1] for o in scene.objects]


def test_show_lines_draws_a_wireframe_not_a_trace(view):
    """The bug this closes: `lines` used to mean the CA trace."""
    view.set_cartoon_visible(False)
    view.set_lines_visible(True)
    ids = _ids(view)
    assert "lines" in ids
    assert "trace" not in ids

    scene = view.get_current_scene()
    lines = next(o for o in scene.objects if o.id.endswith("lines"))
    assert lines.geometry.kind == "line"
    # Four vertices per bond, and a protein has far more bonds than residues.
    assert lines.geometry.positions.shape[0] > 4 * view._coords.shape[0]


def test_as_lines_replaces_the_other_representations(view):
    """PyMOL's `as` replaces rather than adds."""
    view.set_representation("lines")
    ids = _ids(view)
    assert "lines" in ids
    assert "cartoon" not in ids

    view.set_representation("cartoon")
    ids = _ids(view)
    assert "cartoon" in ids
    assert "lines" not in ids


def test_lines_are_coloured_per_atom(view):
    """Element colours are what make a wireframe readable."""
    view.set_cartoon_visible(False)
    view.set_lines_visible(True)
    lines = next(
        o for o in view.get_current_scene().objects if o.id.endswith("lines")
    )
    colors = lines.geometry.colors
    assert colors is not None
    assert colors.shape[0] == lines.geometry.positions.shape[0]
    # More than one colour present, or it is not per-atom at all.
    assert np.unique(colors, axis=0).shape[0] > 1
