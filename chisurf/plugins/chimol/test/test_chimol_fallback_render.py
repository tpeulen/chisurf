"""Rendering-side regression tests for the raw-coordinate (PDB fallback) path.

When the core ``Structure`` reader is unavailable, ChiMOL loads a file through
:func:`_parse_pdb_backbone` and feeds the coordinates to
:meth:`MolView.set_coordinates`. These tests pin the two representations that
regressed when the fallback started carrying a separate CA trace:

* **all atoms** must render (not a sparse ~50-point CA sampling), and
* **sticks** must render (bonds are computed from the raw coordinates).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from qtpy import QtWidgets

from chisurf.plugins.chimol.chimol.io.structure import _parse_pdb_backbone
from chisurf.plugins.chimol.chimol.renderer.view import (
    _DISPLAY_CONFIG,
    MolView,
    _build_sphere_mesh,
)

_PDB = (
    Path(__file__).resolve().parents[4]
    / "test"
    / "data"
    / "atomic_coordinates"
    / "pdb_files"
    / "148l.pdb"
)


@pytest.fixture
def _qt_app():
    """Ensure a QApplication exists for MolView construction."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def _load_fallback(view: MolView) -> int:
    """Load the fixture through the fallback path; return the atom count."""
    backbone = _parse_pdb_backbone(str(_PDB))
    view.add_coordinates(
        backbone.coords,
        name="fallback",
        trace_coords=backbone.trace_coords,
        res_ids=backbone.res_ids,
        res_names=backbone.res_names,
        chain_ids=backbone.chain_ids,
    )
    return int(backbone.coords.shape[0])


def test_fallback_renders_every_atom(_qt_app) -> None:
    """The atoms representation must draw all atoms, not a CA subsample."""
    view = MolView()
    n_atoms = _load_fallback(view)
    view.set_atoms_visible(True)

    balls_cfg = _DISPLAY_CONFIG.get("balls", {})
    objs = view._update_atoms(
        np.asarray(view._coords), view._coords.shape[0], balls_cfg, view._colors_per_ca
    ) or []

    meshes = [o for o in objs if o.id == "atoms_mesh"]
    assert meshes, "the fallback atoms representation produced no mesh"

    verts_per_atom = _build_sphere_mesh(radius=1.0)["vertices"].shape[0]
    drawn = meshes[0].geometry.positions.shape[0] // verts_per_atom
    assert drawn == n_atoms, f"drew {drawn} atoms, expected {n_atoms}"


def test_fallback_computes_bonds_and_renders_sticks(_qt_app) -> None:
    """Bonds are computed from raw coordinates so sticks can render."""
    view = MolView()
    _load_fallback(view)

    assert view._bond_pairs is not None
    assert view._bond_pairs.shape[0] > 0

    view.set_sticks_visible(True)
    sticks_cfg = _DISPLAY_CONFIG.get("sticks", {})
    objs = view._update_sticks(sticks_cfg, view._colors_per_ca) or []
    assert any(o.id == "sticks" for o in objs), "sticks did not render in fallback"


def test_fallback_dots_render_every_atom(_qt_app) -> None:
    """Dots must render all atoms, not crash on a missing per-atom res-id array.

    The fallback populates ``_residue_ids`` (per-CA) but leaves
    ``_all_atom_res_ids`` as ``None``; the per-residue colour path used to build
    ``np.asarray(None)`` and iterate a 0-d array.
    """
    view = MolView()
    n_atoms = _load_fallback(view)
    view.set_dots_visible(True)

    objs = view._update_dots(np.asarray(view._coords), view._colors_per_ca) or []
    dots = [o for o in objs if o.id == "dots"]
    assert dots, "the fallback dots representation produced no geometry"
    assert dots[0].geometry.positions.shape[0] == n_atoms


def test_fallback_scene_builds_with_dots_and_metaballs(_qt_app) -> None:
    """A full scene build must not raise when dots and metaballs are enabled.

    Because ``_update_dots`` runs inside the shared scene builder, its previous
    crash aborted the whole build, so metaballs (and everything else) silently
    disappeared even though their own code was correct.
    """
    view = MolView()
    _load_fallback(view)
    view.set_dots_visible(True)
    view.set_metaballs_visible(True)
    # Must not raise.
    view._update_view()


def test_fallback_metaball_surface_spans_the_molecule(_qt_app) -> None:
    """The metaball isosurface must be a connected envelope, not sub-voxel spikes.

    Density sigmas derive from ``_all_atom_radii`` in the *scaled* coordinate
    frame. A raw-coordinate object carries no radii, so ``set_coordinates`` seeds
    a scaled default; without it the sigma is ~``_scale_factor``x too small and
    marching cubes yields a handful of disconnected specks instead of a surface.
    """
    view = MolView()
    _load_fallback(view)
    view.set_metaballs_visible(True)

    from chisurf.plugins.chimol.chimol.renderer.view import _DISPLAY_CONFIG as _CFG

    objs = view._update_metaballs(
        np.asarray(view._coords), _CFG.get("metaball", {}), view._colors_per_ca
    ) or []
    assert objs, "metaballs produced no mesh"
    verts = objs[0].geometry.positions

    # A real envelope has many vertices and spans the atom cloud; the broken
    # (unscaled-sigma) case collapsed to well under 2000 vertices.
    assert verts.shape[0] > 20_000, f"metaball mesh too sparse: {verts.shape[0]} verts"

    atom_extent = view._all_atom_coords.max(axis=0) - view._all_atom_coords.min(axis=0)
    mesh_extent = verts.max(axis=0) - verts.min(axis=0)
    assert np.all(mesh_extent > 0.5 * atom_extent), (
        f"metaball mesh does not span the molecule: {mesh_extent} vs {atom_extent}"
    )
