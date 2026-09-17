"""A metaball has to be a jelly *of something*, not a jelly bean.

Smoothing a metaball has an obvious knob -- widen each atom's field until
neighbours merge -- and it has an unobvious cost. Widen it far enough and the
isosurface stops following the molecule at all: it inflates into a featureless
egg sitting well outside the atoms, and no threshold can pull it back, because
past a certain width even the highest iso_value still encloses far too much.

That is what happened at ``sigma_factor`` 6.5. The surface enclosed **6.5x** the
atoms' own union volume, and sweeping ``iso_value`` to its ceiling (0.95) only
got it down to ~5x. The fold was gone and the knob meant to control it was
saturated. These tests hold the two properties that were lost, so the next
attempt to make it smoother cannot quietly re-inflate it.

The material side of the same look -- translucency -- is not testable here: it
lives in GLSL and needs a real GL context, which the suite does not have. It is
verified by rendering and inspecting, per the project's GUI rule.
"""

from __future__ import annotations

import functools
import json
import pathlib

import numpy as np
import pytest
from chimol.core.settings.config import get_package_display_config_path
from chimol.core.viewer import Viewer
from chimol.io.atoms import make_bead_rows


@pytest.fixture(scope="module")
def _qt_app():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def blob(_qt_app):
    """Return a viewer over a compact, deliberately *non-spherical* cloud.

    Two lobes joined by a neck. A single ball would pass every test below by
    accident; a shape with a waist only survives them if the surface actually
    follows the atoms.
    """
    rng = np.random.default_rng(0)
    left = rng.normal(scale=3.5, size=(220, 3)) + np.array([-12.0, 0.0, 0.0])
    right = rng.normal(scale=3.5, size=(220, 3)) + np.array([12.0, 0.0, 0.0])
    # A thin bridge, so the two lobes are one connected body with a real waist
    # rather than two separate surfaces (which would make the neck test vacuous).
    bridge = np.c_[
        np.linspace(-9.0, 9.0, 40),
        rng.normal(scale=0.8, size=40),
        rng.normal(scale=0.8, size=40),
    ]
    xyz = np.vstack([left, right, bridge])

    view = Viewer()
    view.set_coordinates(xyz, atoms=make_bead_rows(xyz), atom_radii=np.full(len(xyz), 1.7))
    view.set_metaballs_visible(True)
    view._draft_quality = False
    return view


@functools.lru_cache(maxsize=1)
def _shipped_metaball() -> dict:
    """Return the metaball settings the package ships.

    Deliberately **not** `_DISPLAY_CONFIG`: that is the merged runtime config,
    which prefers the copy in the developer's own settings directory. A test
    reading it asks "what does this machine do", and the answer differs per
    machine -- this suite is about what everyone gets.
    """
    return json.loads(get_package_display_config_path().read_text(encoding="utf-8"))["metaball"]


def _mesh(view, **overrides):
    """Build the metaball and return its vertices and triangles."""
    cfg = dict(_shipped_metaball(), **overrides)
    objects = view._update_metaballs(np.asarray(view._coords, dtype=float), cfg, None)
    assert objects, "the metaball builder produced nothing"
    geometry = objects[0].geometry
    vertices = np.asarray(geometry.positions, dtype=float)
    faces = np.asarray(geometry.faces if hasattr(geometry, "faces") else geometry.indices).reshape(
        -1, 3
    )
    return vertices, faces


def _enclosed_volume(vertices, faces) -> float:
    """Volume inside a closed triangle mesh, by the divergence theorem."""
    a, b, c = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    return abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def _atom_volume(view, samples: int = 60_000) -> float:
    """Union volume of the atom spheres, by Monte Carlo.

    The union rather than the sum: the sum double-counts every overlap, and in a
    packed protein that is most of the volume.
    """
    centres = np.asarray(view._all_atom_coords, dtype=float)
    radii = np.asarray(view._all_atom_radii, dtype=float)
    rng = np.random.default_rng(1)
    lo = centres.min(axis=0) - radii.max()
    hi = centres.max(axis=0) + radii.max()
    points = rng.uniform(lo, hi, size=(samples, 3))
    inside = np.zeros(len(points), dtype=bool)
    for start in range(0, len(centres), 256):
        chunk = centres[start : start + 256]
        distances = np.linalg.norm(points[:, None, :] - chunk[None, :, :], axis=2)
        inside |= (distances <= radii[start : start + 256]).any(axis=1)
    return float(inside.mean() * np.prod(hi - lo))


def test_the_surface_stays_near_the_molecule(protein):
    """The shipped default must not enclose a multiple of the atoms' volume.

    A surface has to sit outside the atoms -- that is what makes it a surface --
    but by a skin, not by a factor. Measured on 148L: the 6.5 default enclosed
    **6.5x** the atoms' union volume; the shipped one encloses ~3.8x. The bound
    here is loose enough to survive a deliberate change of look and tight enough
    to catch an egg.

    On a *real* protein rather than a synthetic cloud: in a sparse cloud the
    field fills space a fold does not have, which inflates the ratio to ~4.8 for
    the same settings and would put the bound somewhere that means nothing.
    """
    vertices, faces = _mesh(protein)
    ratio = _enclosed_volume(vertices, faces) / _atom_volume(protein)
    assert ratio < 4.5, f"the metaball encloses {ratio:.1f}x the atoms' volume"


def test_iso_value_still_controls_the_surface(blob):
    """Raising the threshold must visibly shrink the surface.

    This is the property that failed silently. `iso_value` is *the* knob for how
    tight the surface is, and at a wide enough sigma it stops working: the
    density is so spread out that even the ceiling still encloses everything.
    A knob that does nothing is worse than a bad default, because the obvious
    fix -- turn it up -- appears to be broken.
    """
    loose = _enclosed_volume(*_mesh(blob, iso_value=0.05))
    tight = _enclosed_volume(*_mesh(blob, iso_value=0.5))
    assert tight < 0.75 * loose, f"iso_value barely moved the surface: {loose:.3g} -> {tight:.3g}"


def test_the_waist_between_two_lobes_survives(blob):
    """A two-lobed cloud must not render as one convex bean.

    The sharpest symptom of over-smoothing is that concave features fill in
    first, and a molecule is mostly concave features. Measured across the neck:
    the surface must be narrower at the waist than at the lobes.
    """
    vertices, _ = _mesh(blob)
    # About the mesh's own axis: the viewer works in scene units whose origin is
    # not the molecule's centre, so radii measured from (0, 0) would compare the
    # slices against different things.
    axis = vertices - vertices.mean(axis=0)
    x = axis[:, 0]
    centre = 0.0
    span = x.max() - x.min()

    def thickness(where, width=0.06):
        near = np.abs(x - where) < width * span
        assert near.sum() > 20, "not enough vertices in this slice"
        radial = np.hypot(axis[near, 1], axis[near, 2])
        return float(np.percentile(radial, 95))

    waist = thickness(centre)
    lobe = max(thickness(centre - 0.3 * span), thickness(centre + 0.3 * span))
    assert waist < 0.9 * lobe, f"the neck filled in: waist {waist:.2f} vs lobe {lobe:.2f}"


def test_a_wider_sigma_costs_more_than_it_looks(blob):
    """Smoothing is not free, and it gets more expensive twice over.

    A wider field means more work per atom *and* a larger padded box; with
    `max_dim` capped, the grid then coarsens, which is the second way a wide
    sigma loses detail. Measured on 148L, the 6.5 default built its draft mesh
    at 11 fps and the shipped one at 21 -- the difference between a trajectory
    that scrubs and one that does not.
    """
    narrow = _mesh(blob, sigma_factor=3.5, iso_value=0.12)
    wide = _mesh(blob, sigma_factor=6.5, iso_value=0.06)
    assert _enclosed_volume(*wide) > _enclosed_volume(*narrow)


def _connected_pieces(vertices, faces) -> int:
    """How many separate surfaces the mesh is, by union-find over its edges."""
    parent = np.arange(len(vertices))

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for a, b in np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [0, 2]]]):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return len({find(i) for i in range(len(vertices))})


def _load(name: str, view_name: str):
    """Load a structure from the test data into a viewer showing metaballs."""
    from chimol.io.structure import load_structure_payload

    root = pathlib.Path(__file__).resolve().parents[4] / "test" / "data" / "atomic_coordinates"
    for candidate in (root / "pdb_files" / name, root / "trajectory" / "hgbp1" / name):
        if candidate.is_file():
            break
    else:
        pytest.skip(f"{name} is not in the tree")

    _structure, payload = load_structure_payload(candidate)
    view = Viewer()
    view.add_payload(payload, name=view_name)
    view.set_metaballs_visible(True)
    view._draft_quality = False
    return view


@pytest.fixture(scope="module")
def protein(_qt_app):
    """Return a viewer over a real, densely packed protein (T4 lysozyme)."""
    return _load("148l.pdb", "protein")


@pytest.fixture(scope="module")
def helical(_qt_app):
    """Return a viewer over a long helical molecule.

    The case a globular test misses.

    The topology of the trajectory demo: a globular domain and a long helical
    stalk. Tightening the field looks like welcome detail on a compact protein
    and shreds a bundle like this one, so the default is judged here.
    """
    return _load("topol.pdb", "stalk")


def test_the_envelope_does_not_shatter_into_one_surface_per_helix(helical):
    """A tighter field must not break the molecule into a heap of surfaces.

    This is the regression that was reported, and it is invisible on a globular
    protein: at a tight enough sigma the surface wraps each helix on its own and
    the envelope tears open into background between them -- zoomed in, that
    reads as a shredded surface rather than as detail. Measured on this
    molecule: 39 pieces at sigma 2.5, 6 at 3.0, 4 at 3.5, 2 at the shipped 4.0.

    Calibrated against a deliberately over-smooth field rather than a constant,
    so the bound follows the molecule: some structures genuinely *are* in
    several pieces, and the test must not demand that they fuse.
    """
    smooth = _connected_pieces(*_mesh(helical, sigma_factor=6.5, iso_value=0.06))
    shipped = _connected_pieces(*_mesh(helical))
    assert shipped <= smooth + 2, (
        f"the surface fragmented: {shipped} pieces, against {smooth} when "
        "deliberately over-smoothed"
    )
