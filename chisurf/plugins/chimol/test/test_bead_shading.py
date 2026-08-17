"""Depth and colour on a bead model, which has neither by default.

A cloud of a quarter of a million spheres, drawn flat, is unreadable: no shadow
falls, nothing is out of focus, and at this scale perspective separates nothing,
so the picture carries no cue about which beads are in front. Two things give it
shape:

* **ambient occlusion** — a bead surrounded on all sides is buried and darkens,
  one on the outside stays bright. Every other sphere path in the viewer did
  this; the bead path did not, so an integrative model came out as a flat sheet
  of coloured dots;
* **colour that means something** — ramping over 234,184 beads in file order
  says nothing about the structure, while colouring by *molecule* gives every
  copy of a nucleoporin one colour and makes an assembly's symmetry visible.
"""
from __future__ import annotations

import numpy as np
import pytest

from chimol.io.atoms import make_bead_rows
from chimol.core.hierarchy import HierarchyNode
from chimol.core.viewer import MolView


@pytest.fixture(scope="module")
def _qt_app():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _clustered_beads(n_core: int = 400, n_far: int = 40, seed: int = 0):
    """Build a dense ball of beads plus a few isolated ones far away from it."""
    rng = np.random.default_rng(seed)
    core = rng.normal(scale=6.0, size=(n_core, 3))
    far = rng.normal(scale=6.0, size=(n_far, 3)) + np.array([400.0, 0.0, 0.0])
    return np.vstack([core, far]), n_core


def _viewer(xyz, *, hierarchy=None, radii=None):
    """Return a viewer holding ``xyz`` as beads."""
    view = MolView()
    view.set_coordinates(
        xyz,
        atoms=make_bead_rows(xyz, chain_ids=["A"] * len(xyz)),
        atom_radii=np.full(len(xyz), 2.0) if radii is None else radii,
        hierarchy=hierarchy,
    )
    return view


# --------------------------------------------------------------------------- #
# Ambient occlusion
# --------------------------------------------------------------------------- #
def test_buried_beads_are_darker_than_exposed_ones(_qt_app):
    """The whole point: crowding has to show as shading.

    Without it the two groups come out identical and the picture has no depth
    cue at all.
    """
    xyz, n_core = _clustered_beads()
    view = _viewer(xyz)
    cfg = {"impostor_min_atoms": 1, "ao_strength": 0.6}

    colours = np.asarray(view._bead_scene_object(cfg, None).geometry.colors)[:, :3]
    buried = colours[:n_core].mean()
    exposed = colours[n_core:].mean()

    assert exposed > buried, "the isolated beads must stay brighter"
    assert exposed - buried > 0.05, "the difference must be visible, not nominal"


def test_occlusion_can_be_switched_off(_qt_app):
    """``ao_strength = 0`` leaves every colour exactly as it was."""
    xyz, _ = _clustered_beads()
    view = _viewer(xyz)

    flat = np.asarray(
        view._bead_scene_object(
            {"impostor_min_atoms": 1, "ao_strength": 0.0}, None
        ).geometry.colors
    )[:, :3]

    assert np.allclose(flat.min(axis=0), flat.max(axis=0)), (
        "all beads share one base colour, so with occlusion off they must be equal"
    )


def test_the_occlusion_radius_follows_the_model_scale(_qt_app):
    """A radius in Angstrom is meaningless once the scene has been scaled.

    Coordinates are centred and multiplied by the viewer's scale factor, and a
    bead of the nuclear pore ends up with a *radius* of ~30 scene units — so the
    4 A default neighbourhood contains nothing at all and the shading silently
    does nothing. This is the failure that made the first attempt look like the
    occlusion had not been wired up.
    """
    xyz, n_core = _clustered_beads()
    # Ten times larger, as a real model is after scaling.
    view = _viewer(xyz * 10.0, radii=np.full(len(xyz), 20.0))
    cfg = {"impostor_min_atoms": 1, "ao_strength": 0.6, "ao_radius": 4.0}

    colours = np.asarray(view._bead_scene_object(cfg, None).geometry.colors)[:, :3]
    assert colours[n_core:].mean() - colours[:n_core].mean() > 0.05, (
        "the neighbourhood must scale with the model, not stay at 4 A"
    )


# --------------------------------------------------------------------------- #
# Colour by hierarchy level
# --------------------------------------------------------------------------- #
def _two_molecules(n_each: int = 5):
    """Two molecules of two copies each, as an assembly has."""
    rng = np.random.default_rng(1)
    total = 4 * n_each
    xyz = rng.normal(scale=10.0, size=(total, 3))
    root = HierarchyNode(name="root", node_type="ROOT")
    root.atom_indices = list(range(total))
    row = 0
    for mol in ("Nup84", "Nsp1"):
        node = root.add_child(HierarchyNode(name=mol, node_type="MOLECULE"))
        for copy in range(2):
            chain = node.add_child(
                HierarchyNode(name=f"{mol}.{copy}", node_type="CHAIN")
            )
            chain.atom_indices = list(range(row, row + n_each))
            node.atom_indices.extend(chain.atom_indices)
            row += n_each
    return xyz, root, n_each


def test_rows_can_be_labelled_by_molecule(_qt_app):
    """Copies of one molecule share a label; different molecules do not."""
    xyz, root, n_each = _two_molecules()
    view = _viewer(xyz, hierarchy=root)

    labels = view.hierarchy_labels("MOLECULE")
    assert labels is not None
    assert len(labels) == len(xyz)
    # Both copies of Nup84 first, then both of Nsp1.
    assert set(labels[: 2 * n_each]) == {"Nup84"}
    assert set(labels[2 * n_each:]) == {"Nsp1"}


def test_labelling_by_chain_separates_the_copies(_qt_app):
    """The same machinery at a finer level gives one label per copy."""
    xyz, root, _ = _two_molecules()
    view = _viewer(xyz, hierarchy=root)

    labels = view.hierarchy_labels("CHAIN")
    assert labels is not None
    assert len(set(labels)) == 4


def test_no_hierarchy_means_no_labels(_qt_app):
    """A plain coordinate object says so rather than inventing a level."""
    xyz, _ = _clustered_beads(n_core=10, n_far=2)
    view = _viewer(xyz)

    assert view.hierarchy_labels("MOLECULE") is None
