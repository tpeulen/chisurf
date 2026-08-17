"""An RMF is read into the same shape as every other structure, and drawn like one.

RMF used to have its own route into the viewer -- its own loader branch in the
window, its own ``set_rmf_data`` filling a parallel set of state fields. The
result was not that it looked slightly different but that it received *nothing*
the common path knew:

* 60,000 beads came back with one global radius, because the radii were stored
  where nothing that draws reads them;
* they were drawn as a merged mesh and decimated to a fraction of themselves,
  never as the sphere impostors an integrative model needs;
* the hierarchy panel built its tree and ticked its check boxes, and hiding a
  molecule removed not one bead from the picture.

None of that raised anything. These tests pin the unified path: read once, into
one payload, drawn by one set of rules -- plus the resolution chooser that
becomes possible once the reader knows a model can be depicted more than one
way.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from rmf_fixture import COARSE_RESOLUTION, FINE_RESOLUTION, write_multiresolution_rmf

from chimol.io.atoms import bead_mask
from chimol.io.structure import load_structure_payload
from chimol.core.viewer import MolView, _is_bead_model

RMF = pytest.importorskip("RMF", reason="reading an RMF needs the RMF package")


@pytest.fixture
def _qt_app():
    """Ensure a QApplication exists for MolView construction."""
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


#: Force the impostor branch, whose geometry carries one position per bead --
#: which is what lets a test count what is *drawn* rather than inspect a mesh.
_POINTS = {"impostor_min_atoms": 1}


@pytest.fixture(scope="module")
def multires(tmp_path_factory):
    """Write a two-resolution RMF and return it with what went into it."""
    path = tmp_path_factory.mktemp("rmf") / "multires.rmf3"
    info = write_multiresolution_rmf(path)
    return path, info


@pytest.fixture(scope="module")
def single(tmp_path_factory):
    """Write an ordinary RMF: one representation, no alternatives."""
    path = tmp_path_factory.mktemp("rmf") / "single.rmf3"
    info = write_multiresolution_rmf(path, n_coarse=0)
    return path, info


def _load(path, qt_app=None):
    """Load a file the way the window does and return the viewer."""
    _structure, payload = load_structure_payload(Path(path))
    view = MolView()
    view.add_payload(payload, name="model", source_path=str(path))
    return view, payload


def _drawn(view) -> int:
    """How many beads the viewer would actually draw."""
    scene = view._bead_scene_object(_POINTS, None)
    if scene is None:
        return 0
    return int(np.asarray(scene.geometry.positions).shape[0])


# --------------------------------------------------------------------------- #
# Read as one payload
# --------------------------------------------------------------------------- #
def test_an_rmf_arrives_as_beads_with_their_own_radii(_qt_app, multires):
    """The thing the parallel path never delivered: bead rows and real sizes."""
    path, info = multires
    view, payload = _load(path)

    assert payload.reader == "rmf"
    assert bead_mask(payload.atoms["res_name"]).all()
    assert _is_bead_model(view._atoms)

    # Beads differ in size within a representation, and the sizes survive all
    # the way to what is traced. A *single* distinct radius here is the old bug
    # exactly: `get_atom_sphere_data` fell back to one global size, because the
    # per-bead radii were stored where nothing that draws looks.
    _pts, _colors, drawn_radii = view.get_atom_sphere_data(visible_only=True)
    assert len(np.unique(np.round(drawn_radii, 9))) > 1

    # And the two representations really are drawn at different scales.
    fine = view._resolutions == FINE_RESOLUTION
    coarse = view._resolutions == COARSE_RESOLUTION
    assert view._all_atom_radii[coarse].min() > view._all_atom_radii[fine].max()


def test_the_trajectory_and_the_hierarchy_both_arrive(_qt_app, multires):
    """One call carries the frames and the tree, not just coordinates."""
    path, info = multires
    view, payload = _load(path)

    state = view._get_active_state()
    assert state.frames is not None
    assert np.asarray(state.frames).shape[0] == info["n_frames"]
    assert view._rmf_hierarchy is not None
    # Every particle is attributed to some node of the tree.
    assert len(view._rmf_hierarchy.atom_indices) == info["n_particles"]


def test_measurements_follow_playback(_qt_app, multires):
    """``atoms["xyz"]`` tracks the frame, so distances are not frozen at frame 0.

    This is what ``zoom``, ``distance`` and ``select ... within`` read. It used
    to be kept in sync only for objects that also had residue ids, which is
    incidental to the question -- an object with atoms and no residues had every
    measurement silently stuck at the first frame while the picture moved.
    """
    path, _info = multires
    view, _payload = _load(path)

    first = np.asarray(view._atoms["xyz"], dtype=float).copy()
    view.set_current_frame(2)
    later = np.asarray(view._atoms["xyz"], dtype=float)

    assert not np.allclose(first, later)


# --------------------------------------------------------------------------- #
# Resolutions
# --------------------------------------------------------------------------- #
def test_an_ordinary_rmf_offers_no_choice(_qt_app, single):
    """One representation means no resolution dimension and no chooser.

    A chooser offering a single option is worse than none, and an array of one
    repeated value costs every consumer a mask it does not need.
    """
    path, info = single
    view, payload = _load(path)

    assert payload.resolutions is None
    assert view.available_resolutions() == []
    assert view.visible_row_mask(info["n_particles"]) is None
    assert _drawn(view) == info["n_fine_total"]


def test_a_multiresolution_file_opens_on_the_trees_own_representation(
    _qt_app, multires
):
    """Both depictions are loaded; only the file's own one is drawn."""
    path, info = multires
    view, _payload = _load(path)

    assert view.available_resolutions() == [FINE_RESOLUTION, COARSE_RESOLUTION]
    # Every particle is present...
    assert view._all_atom_coords.shape[0] == info["n_particles"]
    # ...and only the fine ones are drawn, so the file opens as it always did
    # rather than with two depictions superimposed.
    assert _drawn(view) == info["n_fine_total"]


def test_switching_resolution_changes_what_is_drawn(_qt_app, multires):
    """The chooser swaps the depiction without reloading anything."""
    path, info = multires
    view, _payload = _load(path)

    assert view.set_visible_resolutions([COARSE_RESOLUTION]) == info["n_coarse_total"]
    assert _drawn(view) == info["n_coarse_total"]

    assert view.set_visible_resolutions(None) == info["n_particles"]
    assert _drawn(view) == info["n_particles"]

    assert view.set_visible_resolutions([FINE_RESOLUTION]) == info["n_fine_total"]
    assert _drawn(view) == info["n_fine_total"]


def test_an_unmatched_resolution_keeps_the_current_one(_qt_app, multires):
    """A request that matches nothing is refused, not obeyed into an empty view."""
    path, info = multires
    view, _payload = _load(path)

    assert view.set_visible_resolutions([3.7]) == 0
    assert _drawn(view) == info["n_fine_total"]


# --------------------------------------------------------------------------- #
# The two masks are independent
# --------------------------------------------------------------------------- #
def _first_molecule_rows(view) -> list[int]:
    """Rows belonging to the first chain of the hierarchy."""
    for node in view._rmf_hierarchy.descendants():
        if node.node_type == "CHAIN" and node.atom_indices:
            return list(node.atom_indices)
    raise AssertionError("the fixture has chains")


def test_hiding_a_molecule_removes_its_beads(_qt_app, multires):
    """The hierarchy check boxes move the picture for an RMF, at last."""
    path, info = multires
    view, _payload = _load(path)

    rows = _first_molecule_rows(view)
    before = _drawn(view)
    view.set_rows_hidden(rows, True)
    after = _drawn(view)

    assert after < before
    # Only the *drawn* (fine) rows of that chain can go, since the coarse ones
    # were not being drawn to begin with.
    assert before - after == sum(1 for row in rows if view._resolutions[row] == FINE_RESOLUTION)


def test_choosing_a_resolution_does_not_unhide_what_you_hid(_qt_app, multires):
    """The two masks answer different questions and are composed, not shared.

    Sharing one mask is the tempting simplification, and it means picking a
    coarser depiction silently brings back the molecule you switched off.
    """
    path, info = multires
    view, _payload = _load(path)

    rows = _first_molecule_rows(view)
    view.set_rows_hidden(rows, True)
    view.set_visible_resolutions([COARSE_RESOLUTION])

    hidden_coarse = sum(
        1 for row in rows if view._resolutions[row] == COARSE_RESOLUTION
    )
    assert hidden_coarse > 0, "the fixture's chains have coarse beads too"
    assert _drawn(view) == info["n_coarse_total"] - hidden_coarse

    # And unhiding restores them, still within the chosen resolution.
    view.set_rows_hidden(rows, False)
    assert _drawn(view) == info["n_coarse_total"]


# --------------------------------------------------------------------------- #
# Coordinates and connectivity
# --------------------------------------------------------------------------- #
def test_the_coordinate_permutation_is_right(multires, monkeypatch):
    """RMF's own particle order is mapped onto the loader's, not assumed equal.

    ``get_all_global_coordinates`` fills its buffer in a plain depth-first order
    and is the only reader that applies ancestors' reference frames, so it is
    worth keeping -- but the loader visits an alternative representation through
    the node that owns it, which is a *different* order. Getting the mapping
    wrong scrambles every coordinate against its own radius and hierarchy entry,
    and looks like a corrupt file rather than a reader bug.

    Both paths are exercised and compared: the buffered one, and the per-node
    fallback that reads each particle by hand in loader order.
    """
    import chimol.io.rmf as rmf_module

    path, _info = multires
    buffered = rmf_module.load_rmf_full(path)["frames"]

    def refuse(*args, **kwargs):
        raise RuntimeError("forced onto the per-node path")

    monkeypatch.setattr(rmf_module.RMF, "get_all_global_coordinates", refuse)
    per_node = rmf_module.load_rmf_full(path)["frames"]

    np.testing.assert_allclose(buffered, per_node, atol=1e-5)


def test_stated_bonds_survive_a_bead_model(_qt_app, multires):
    """A reader that knows the connectivity outranks the all-beads rule.

    A bead model has no bonds to *infer* -- no interatomic distance means
    anything on a sphere covering ten residues -- so the bead path zeroes them.
    That must not also discard the bonds an RMF states, which are often the
    restraint topology someone opened the file to look at.
    """
    path, _info = multires
    _structure, payload = load_structure_payload(Path(path))

    stated = np.array([[0, 1], [1, 2]], dtype=int)
    payload.bonds = stated

    view = MolView()
    view.add_payload(payload, name="bonded")

    assert view._bond_pairs is not None
    np.testing.assert_array_equal(np.asarray(view._bond_pairs), stated)
