"""How an integrative (bead) model is read and drawn.

A bead stands for a *range* of residues. It has no backbone, no secondary
structure and no bonds, so the depictions that assume one are not merely
expensive on a model of this size -- they are wrong. These tests pin the three
rules that follow:

* a bead model loads in the sphere representation, not as a cartoon;
* every bead is drawn, at its own radius -- past a budget as sphere impostors,
  which is one vertex each instead of ~160;
* an impostor's radius is a distance in the model, so it has to be projected to
  pixels rather than used as one.

The eight-spoke nuclear pore (`PDBDEV_00000012`, 234,184 beads) is the case that
forced all three: it took 430 s and ~11 GB to open as a cartoon splined through
beads, against 1.6 s and 0.7 GB as spheres.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.renderer.view import (
    MolView,
    _bead_mask,
    _is_bead_model,
)


# --------------------------------------------------------------------------- #
# A synthetic bead model, shaped like the real thing
# --------------------------------------------------------------------------- #
def _bead_atoms(n: int = 64, seed: int = 0):
    """Build the atom array ``_parse_mmcif_backbone`` produces for beads."""
    rng = np.random.default_rng(seed)
    xyz = rng.normal(scale=40.0, size=(n, 3))
    radii = rng.uniform(6.0, 30.0, size=n)
    dtype = np.dtype(
        [
            ("atom_name", "U4"),
            ("res_name", "U4"),
            ("chain", "U4"),
            ("res_id", "i4"),
            ("element", "U2"),
            ("xyz", "f8", 3),
        ]
    )
    atoms = np.zeros(n, dtype=dtype)
    atoms["atom_name"] = "CA"
    atoms["res_name"] = "BEA"
    atoms["chain"] = "A"
    atoms["res_id"] = np.arange(1, n + 1)
    atoms["element"] = "C"
    atoms["xyz"] = xyz
    return atoms, xyz, radii


@pytest.fixture
def bead_view(qapp_chimol):
    """Return a MolView holding a 64-bead model with per-bead radii."""
    atoms, xyz, radii = _bead_atoms()
    view = MolView()
    view.set_coordinates(
        xyz,
        trace_coords=xyz,
        res_ids=atoms["res_id"],
        res_names=atoms["res_name"],
        chain_ids=atoms["chain"],
        atoms=atoms,
        atom_radii=radii,
    )
    return view, radii


@pytest.fixture(scope="session")
def qapp_chimol():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


# --------------------------------------------------------------------------- #
# Recognising one
# --------------------------------------------------------------------------- #
def test_all_bea_residues_are_a_bead_model():
    atoms, _xyz, _r = _bead_atoms()
    assert _is_bead_model(atoms)


def test_a_protein_is_not_a_bead_model():
    atoms, _xyz, _r = _bead_atoms(n=8)
    atoms["res_name"] = "ALA"
    assert not _is_bead_model(atoms)


# --------------------------------------------------------------------------- #
# Drawing one
# --------------------------------------------------------------------------- #
def test_a_bead_model_loads_as_spheres_not_a_cartoon(bead_view):
    """The rule `set_rmf_data` already applied, now applied by every reader."""
    view, _radii = bead_view
    assert view._show_atoms is True
    assert view._show_cartoon is False
    assert view._show_trace is False
    assert view._ball_mask is not None and view._ball_mask.all()
    assert view._cartoon_mask is not None and not view._cartoon_mask.any()


def test_every_bead_is_drawn(bead_view):
    """Not a sample of them.

    The generic ball path subsamples to ``balls.max_atoms``; on the nuclear pore
    that is 8,000 of 234,184 beads, which is a different molecule.
    """
    view, radii = bead_view
    obj = view._bead_scene_object({"impostor_min_atoms": 1}, None)
    assert obj is not None
    assert obj.geometry.positions.shape[0] == radii.shape[0]


def test_bead_radii_are_kept_and_scaled(bead_view):
    """The sizes are the shape of the thing; one default radius is a lie."""
    view, radii = bead_view
    scale = float(view._scale_factor)
    assert view._all_atom_radii == pytest.approx(radii * scale)
    obj = view._bead_scene_object({"impostor_min_atoms": 1}, None)
    assert obj.geometry.radii == pytest.approx(radii * scale)


def test_a_bead_model_has_no_bonds(bead_view):
    """A distance cutoff between beads means nothing, and costs 0.7 s a spoke."""
    view, _radii = bead_view
    assert view._bond_pairs is None or len(view._bond_pairs) == 0


def test_the_masks_survive_the_scene_build(bead_view):
    """`_update_view` runs inside `set_coordinates`; the defaults must not win."""
    view, radii = bead_view
    objects = view._build_scene_for_current_object()
    ids = {o.id.split(":")[-1] for o in objects}
    assert "atoms_points" in ids or "atoms_mesh" in ids
    assert not any(i.startswith("cartoon") for i in ids)


# --------------------------------------------------------------------------- #
# Which depiction, and how much it costs
# --------------------------------------------------------------------------- #
def test_a_small_bead_model_gets_the_merged_mesh(bead_view):
    view, radii = bead_view
    obj = view._bead_scene_object({"impostor_min_atoms": 10_000}, None)
    assert obj.geometry.kind == "mesh"
    # ~160 vertices a sphere: the mesh is what the impostor budget exists for.
    assert obj.geometry.positions.shape[0] > 20 * radii.shape[0]


def test_a_large_bead_model_gets_impostors(bead_view):
    view, radii = bead_view
    obj = view._bead_scene_object({"impostor_min_atoms": 1}, None)
    assert obj.geometry.kind == "points"
    assert obj.geometry.meta["glyph"] == "sphere"
    assert obj.geometry.meta["world_radius"] is True
    assert obj.geometry.positions.shape[0] == radii.shape[0]


def test_per_bead_colours_need_no_residue_lookup(bead_view):
    """One bead is one residue, so the per-residue colours are already per-bead."""
    view, radii = bead_view
    n = radii.shape[0]
    colors = np.zeros((n, 4), dtype=float)
    colors[:, 0] = np.linspace(0.0, 1.0, n)
    colors[:, 3] = 1.0
    obj = view._bead_scene_object({"impostor_min_atoms": 1}, colors)
    assert obj.geometry.colors[:, 0] == pytest.approx(colors[:, 0])


def test_a_protein_does_not_take_the_bead_path(qapp_chimol):
    atoms, xyz, radii = _bead_atoms(n=16)
    atoms["res_name"] = "ALA"
    view = MolView()
    view.set_coordinates(xyz, trace_coords=xyz, res_ids=atoms["res_id"],
                         res_names=atoms["res_name"], chain_ids=atoms["chain"],
                         atoms=atoms)
    assert view._bead_scene_object({"impostor_min_atoms": 1}, None) is None


# --------------------------------------------------------------------------- #
# A model that is part atoms and part beads -- the normal shape of one
# --------------------------------------------------------------------------- #
def _hybrid(n_atomic: int = 8, n_beads: int = 40):
    """One resolved residue's atoms first, then beads, as the mmCIF reader writes them."""
    atoms, xyz, radii = _bead_atoms(n=n_atomic + n_beads, seed=3)
    atoms["res_name"][:n_atomic] = "ALA"
    atoms["atom_name"][:n_atomic] = ["N", "CA", "C", "O"] * (n_atomic // 4)
    atoms["res_id"][:n_atomic] = np.repeat(np.arange(1, n_atomic // 4 + 1), 4)
    radii[:n_atomic] = 1.7
    # Real backbone spacing, or nothing is within a bonding cutoff and the
    # "bonded over its atoms" check would pass for the wrong reason.
    backbone = np.array(
        [[0.0, 0.0, 0.0], [1.46, 0.0, 0.0], [2.01, 1.42, 0.0], [1.25, 2.39, 0.0]]
    )
    for res in range(n_atomic // 4):
        xyz[res * 4 : res * 4 + 4] = backbone + np.array([res * 3.3, 0.0, 0.0])
    atoms["xyz"][:n_atomic] = xyz[:n_atomic]
    # The trace: one point per resolved residue, then one per bead.
    n_res = n_atomic // 4 + n_beads
    res_names = np.array(["ALA"] * (n_atomic // 4) + ["BEA"] * n_beads)
    res_ids = np.arange(1, n_res + 1)
    trace = np.vstack([xyz[1:n_atomic:4], xyz[n_atomic:]])
    return atoms, xyz, radii, trace, res_ids, res_names


@pytest.fixture
def hybrid_view(qapp_chimol):
    atoms, xyz, radii, trace, res_ids, res_names = _hybrid()
    view = MolView()
    view.set_coordinates(
        xyz,
        trace_coords=trace,
        res_ids=res_ids,
        res_names=res_names,
        chain_ids=np.array(["A"] * len(res_ids)),
        atoms=atoms,
        atom_radii=radii,
    )
    return view, atoms, res_names


def test_one_atom_ahead_of_the_beads_does_not_make_it_a_protein(hybrid_view):
    """The recogniser sampled the first 256 rows, and the atoms come first.

    A single resolved residue at the head of a 200k-bead entry restored the
    whole cartoon-through-beads pathology the sphere depiction exists to remove.
    """
    _view, atoms, _res_names = hybrid_view
    mask = _bead_mask(atoms)
    assert mask is not None
    assert mask.any() and not mask.all()
    assert not _is_bead_model(atoms), "it is not *wholly* beads"


def test_a_bead_first_array_does_not_swallow_its_atoms(qapp_chimol):
    """The converse: beads at the head used to strip the atomic part's cartoon."""
    atoms, _xyz, _r = _bead_atoms(n=1000)
    atoms["res_name"][900:] = "ALA"
    mask = _bead_mask(atoms)
    assert mask[:900].all() and not mask[900:].any()
    assert not _is_bead_model(atoms)


def test_the_beads_are_spheres_and_the_atoms_keep_their_cartoon(hybrid_view):
    view, atoms, _res_names = hybrid_view
    beads = _bead_mask(atoms)
    assert view._show_atoms is True
    assert view._show_cartoon is True, "the resolved residues still have one"
    assert np.array_equal(view._ball_mask, beads)
    # The cartoon covers exactly the residues that are not beads.
    res_beads = np.char.strip(_res_names.astype(str)) == "BEA"
    assert np.array_equal(view._cartoon_mask, ~res_beads)


def test_only_the_beads_go_down_the_bead_path(hybrid_view):
    view, atoms, _res_names = hybrid_view
    beads = _bead_mask(atoms)
    obj = view._bead_scene_object({"impostor_min_atoms": 1}, None)
    assert obj is not None
    assert obj.geometry.positions.shape[0] == int(beads.sum())


def test_a_hybrid_is_bonded_over_its_atoms_only(hybrid_view):
    """A distance cutoff between beads means nothing; between atoms it does."""
    view, atoms, _res_names = hybrid_view
    beads = _bead_mask(atoms)
    pairs = np.asarray(view._bond_pairs).reshape(-1, 2)
    assert pairs.size, "the resolved residues should still be bonded"
    assert not beads[pairs].any(), "no bond may touch a bead"


def test_the_atomic_balls_are_still_drawn(hybrid_view):
    """`_bead_scene_object` must not short-circuit the generic ball path."""
    view, atoms, _res_names = hybrid_view
    beads = _bead_mask(atoms)
    view._ball_mask = np.ones(len(atoms), dtype=bool)
    view._show_atoms = True
    objects = view._update_atoms(
        view._coords, view._coords.shape[0], {"impostor_min_atoms": 1}, None
    )
    ids = [o.id for o in objects]
    assert "atoms_points" in ids, "the beads"
    assert "atoms_mesh" in ids, "and the resolved atoms, drawn as themselves"


def test_a_bead_is_not_drawn_twice(hybrid_view):
    """Falling through to the generic path must not re-draw the beads as a mesh.

    The generic path builds a merged sphere mesh from the ball mask. With the
    beads still in that mask they came out a second time, on top of their own
    impostors and at whatever size the generic path chose.
    """
    view, atoms, _res_names = hybrid_view
    beads = _bead_mask(atoms)
    n_atomic = int((~beads).sum())
    view._ball_mask = np.ones(len(atoms), dtype=bool)
    view._show_atoms = True
    objects = view._update_atoms(
        view._coords, view._coords.shape[0], {"impostor_min_atoms": 1}, None
    )
    points = [o for o in objects if o.id == "atoms_points"]
    meshes = [o for o in objects if o.id == "atoms_mesh"]
    assert len(points) == 1
    assert points[0].geometry.positions.shape[0] == int(beads.sum())
    # A merged sphere mesh has a fixed vertex count per sphere, so the mesh must
    # account for the atomic rows and no more.
    assert meshes, "the atomic rows still need drawing"
    from chisurf.plugins.chimol.chimol.renderer.view import _build_sphere_mesh

    lat, lon = MolView._balls_sphere_segments()
    per_sphere = _build_sphere_mesh(1.0, lat, lon)["vertices"].shape[0]
    assert meshes[0].geometry.positions.shape[0] == n_atomic * per_sphere, (
        "the merged mesh must cover the atomic rows and nothing else"
    )


# --------------------------------------------------------------------------- #
# An impostor is a sphere, so it has to be the size of one
# --------------------------------------------------------------------------- #
def test_impostor_point_scale_matches_the_ray_tracer(qapp_chimol):
    """Both project a vertical field of view onto the frame height.

    ``_point_scale`` is what the vertex shader divides by camera-space depth.
    A sphere of radius ``r`` at depth ``d`` covers ``2 r H / (2 d tan(fov/2))``
    pixels, which is the same projection the ray tracer builds its ray grid
    from -- so a GL impostor and a ray-traced sphere are the same size.
    """
    from chisurf.plugins.chimol.chimol.renderer.qtgl import QtGLRenderer

    renderer = QtGLRenderer(controller=None)
    renderer.resize(800, 600)
    renderer._fov = 45.0

    scale = renderer._point_scale()
    ratio = float(renderer.devicePixelRatioF())
    height = 600.0 * ratio
    assert scale == pytest.approx(0.5 * height / math.tan(math.radians(22.5)))

    r, d = 12.0, 300.0
    diameter_px = 2.0 * r * scale / d
    expected = 2.0 * r * height / (2.0 * d * math.tan(math.radians(22.5)))
    assert diameter_px == pytest.approx(expected)
    renderer.deleteLater()


def test_world_radius_reaches_the_draw_call(qapp_chimol):
    """The flag is what tells the shader the radius is not a pixel count."""
    from chisurf.plugins.chimol.chimol.renderer.qtgl import QtGLRenderer
    from chisurf.plugins.chimol.chimol.renderer.scene import Geometry, SceneObject

    renderer = QtGLRenderer(controller=None)
    pts = np.zeros((3, 3), dtype=float)
    geom = Geometry(
        kind="points",
        positions=pts,
        colors=np.ones((3, 4)),
        radii=np.full(3, 5.0),
        meta={"glyph": "sphere", "world_radius": True},
    )
    draw = renderer._geometry_to_draw_data(SceneObject(id="beads", geometry=geom))
    assert draw is not None and draw.world_radius is True

    plain = renderer._geometry_to_draw_data(
        SceneObject(
            id="dots",
            geometry=Geometry(kind="points", positions=pts, colors=np.ones((3, 4)),
                              meta={"glyph": "sphere"}),
        )
    )
    assert plain is not None and plain.world_radius is False
    renderer.deleteLater()


# --------------------------------------------------------------------------- #
# The numba cache must not be poisoned by a by-path load
# --------------------------------------------------------------------------- #
def test_numba_cache_is_only_written_under_a_real_package_name():
    """A cache entry keyed to a name nothing can import breaks the *next* run.

    `test_nucleic_cartoon_render` loads these two modules by file path, where
    the module name is synthetic. Numba records that name in the entry it
    writes and re-imports it when it loads the entry back -- so the by-path
    load's cache made an ordinary ``add_structure`` die inside numba with
    ``ModuleNotFoundError: No module named '<dynamic>'``.
    """
    import importlib.util
    import pathlib

    from chisurf.plugins.chimol.chimol.geometry import ambient, cartoon

    assert cartoon._NB_CACHE is True
    assert ambient._NB_CACHE is True

    geom_dir = pathlib.Path(cartoon.__file__).parent
    for name, path in (
        ("_chimol_cartoon_standalone", geom_dir / "cartoon.py"),
        ("_chimol_ambient_standalone", geom_dir / "ambient.py"),
    ):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod._NB_CACHE is False, f"{name} would write a poisoned cache"
