"""Tests for the normal-aware ambient occlusion baked into mesh colours.

The estimator that came before this one counted neighbours inside a radius,
which measures *crowding*, not *concavity*: a bulge in the middle of a crowd
came out as dark as the pit beside it. These tests pin the difference, because
it is the whole reason the new one exists.
"""

from __future__ import annotations

import math
import pathlib

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.geometry.ambient import (
    _occlusion_from_spheres_numpy,
    occlusion_from_spheres,
)

_ORIGIN = np.array([[0.0, 0.0, 0.0]])
_UP = np.array([[0.0, 0.0, 1.0]])
_DOWN = np.array([[0.0, 0.0, -1.0]])


def _occ(normals, centers, radii, **kw) -> float:
    result = occlusion_from_spheres(
        _ORIGIN, normals, np.atleast_2d(centers), np.atleast_1d(radii), **kw
    )
    assert result is not None
    return float(result[0])


# --------------------------------------------------------------------------- #
# The geometry it is supposed to model
# --------------------------------------------------------------------------- #
def test_open_space_is_not_occluded():
    assert _occ(_UP, [0.0, 0.0, 100.0], 1.0, max_distance=12.0) == 0.0


def test_an_occluder_overhead_darkens():
    assert _occ(_UP, [0.0, 0.0, 3.0], 2.0, max_distance=12.0) > 0.2


def test_an_occluder_behind_the_surface_does_not():
    """Only the hemisphere the surface faces can occlude it."""
    assert _occ(_DOWN, [0.0, 0.0, 3.0], 2.0, max_distance=12.0) == 0.0


def test_an_occluder_on_the_horizon_barely_counts():
    """cos(theta) -> 0 exactly in the surface plane."""
    assert _occ(_UP, [3.0, 0.0, 0.0], 1.0, max_distance=12.0) == pytest.approx(0.0)


def test_a_pit_is_darker_than_a_single_overhang():
    """Concavity is the signal; this is what the neighbour count could not see."""
    ring = np.array(
        [[math.cos(t) * 3, math.sin(t) * 3, 2.0]
         for t in np.linspace(0, 2 * math.pi, 8, endpoint=False)]
    )
    pit = _occ(_UP, ring, np.full(8, 1.5), max_distance=12.0)
    one = _occ(_UP, ring[:1], np.full(1, 1.5), max_distance=12.0)
    assert pit > one


def test_closer_occluders_darken_more():
    near = _occ(_UP, [0.0, 0.0, 2.5], 1.0, max_distance=12.0)
    far = _occ(_UP, [0.0, 0.0, 8.0], 1.0, max_distance=12.0)
    assert near > far > 0.0


def test_bigger_occluders_darken_more():
    big = _occ(_UP, [0.0, 0.0, 4.0], 2.0, max_distance=12.0)
    small = _occ(_UP, [0.0, 0.0, 4.0], 0.5, max_distance=12.0)
    assert big > small > 0.0


def test_a_vertex_inside_an_occluder_is_not_self_shadowed():
    """A mesh sits on its own atoms; those are its surface, not a blocker."""
    assert _occ(_UP, [0.0, 0.0, 0.5], 2.0, max_distance=12.0) == 0.0


def test_the_solid_angle_is_the_analytic_one():
    """One occluder straight overhead reduces to ``1 - exp(-(1 - cos alpha))``."""
    d, r = 3.0, 2.0
    coverage = 1.0 - math.sqrt(1.0 - (r / d) ** 2)
    assert _occ(_UP, [0.0, 0.0, d], r, max_distance=12.0) == pytest.approx(
        1.0 - math.exp(-coverage)
    )


# --------------------------------------------------------------------------- #
# Bounds and knobs
# --------------------------------------------------------------------------- #
def test_occlusion_never_saturates_to_black():
    """Combining as 1 - exp(-sum) keeps a dense shell inside [0, 1)."""
    rng = np.random.default_rng(0)
    shell = rng.normal(size=(400, 3))
    shell /= np.linalg.norm(shell, axis=1)[:, None]
    value = _occ(_UP, shell * 3.0, np.full(400, 1.0), max_distance=12.0)
    assert 0.9 < value < 1.0


def test_strength_deepens_without_exceeding_one():
    weak = _occ(_UP, [0.0, 0.0, 3.0], 2.0, max_distance=12.0, strength=1.0)
    strong = _occ(_UP, [0.0, 0.0, 3.0], 2.0, max_distance=12.0, strength=4.0)
    assert weak < strong < 1.0


def test_max_distance_bounds_what_is_considered():
    assert _occ(_UP, [0.0, 0.0, 9.0], 1.0, max_distance=5.0) == 0.0
    assert _occ(_UP, [0.0, 0.0, 9.0], 1.0, max_distance=20.0) > 0.0


# --------------------------------------------------------------------------- #
# The two implementations must agree
# --------------------------------------------------------------------------- #
def test_the_numba_and_numpy_paths_agree():
    rng = np.random.default_rng(0)
    points = rng.normal(size=(500, 3)) * 5.0
    normals = rng.normal(size=(500, 3))
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    centers = rng.normal(size=(300, 3)) * 5.0
    radii = rng.uniform(1.0, 2.0, 300)

    fast = occlusion_from_spheres(
        points, normals, centers, radii, max_distance=8.0, strength=1.3
    )
    reference = _occlusion_from_spheres_numpy(
        points, normals, centers, radii, 8.0, 1.3
    )
    assert np.allclose(fast, reference, atol=1e-12)


def test_a_scalar_radius_applies_to_every_occluder():
    rng = np.random.default_rng(1)
    centers = rng.normal(size=(20, 3)) * 4.0
    per_occluder = occlusion_from_spheres(
        _ORIGIN, _UP, centers, np.full(20, 1.5), max_distance=12.0
    )
    scalar = occlusion_from_spheres(
        _ORIGIN, _UP, centers, 1.5, max_distance=12.0
    )
    assert np.allclose(per_occluder, scalar)


# --------------------------------------------------------------------------- #
# Degenerate input
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "points, normals, centers",
    [
        (np.zeros((0, 3)), np.zeros((0, 3)), _ORIGIN),      # no vertices
        (_ORIGIN, _UP, np.zeros((0, 3))),                    # no occluders
        (_ORIGIN, np.zeros((2, 3)), _ORIGIN),                # mismatched normals
        (np.zeros((1, 2)), np.zeros((1, 2)), _ORIGIN),       # not 3D
    ],
)
def test_malformed_input_returns_none(points, normals, centers):
    assert occlusion_from_spheres(
        points, normals, centers, 1.0, max_distance=12.0
    ) is None


def test_mismatched_radii_are_rejected():
    assert occlusion_from_spheres(
        _ORIGIN, _UP, np.zeros((3, 3)), np.ones(2), max_distance=12.0
    ) is None


def test_a_zero_normal_does_not_produce_nan():
    """Degenerate normals happen at mesh seams; they must not poison a colour."""
    value = occlusion_from_spheres(
        _ORIGIN, np.zeros((1, 3)), np.array([[0.0, 0.0, 3.0]]), 2.0,
        max_distance=12.0,
    )
    assert value is not None
    assert np.isfinite(value).all()


def test_normals_need_not_be_unit_length():
    long_normal = _UP * 17.0
    assert _occ(long_normal, [0.0, 0.0, 3.0], 2.0, max_distance=12.0) == pytest.approx(
        _occ(_UP, [0.0, 0.0, 3.0], 2.0, max_distance=12.0)
    )


# --------------------------------------------------------------------------- #
# It has to reach the mesh the viewport draws
# --------------------------------------------------------------------------- #
_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def view(qapp):
    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.io.structure import _read_full_model
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    v = MolView()
    v.resize(400, 300)
    v.add_structure(
        _read_full_model(cs_struct.Structure, _PDB_148L),
        name="148l",
        source_path=str(_PDB_148L),
    )
    v.set_color_mode("by_secondary_structure")
    v.set_cartoon_visible(True)
    return v


def _cartoon_colors(view) -> np.ndarray:
    scene = view.get_current_scene()
    assert scene is not None
    parts = [
        np.asarray(o.geometry.colors)
        for o in scene.objects
        if o.id.endswith("cartoon") and o.geometry.colors is not None
    ]
    assert parts, "no cartoon geometry in the scene"
    return np.concatenate(parts)


def test_occlusion_varies_the_cartoon_colours(view):
    """Baked into vertex colours, so the live viewport gets it without `ray`."""
    from chisurf.plugins.chimol.chimol.config import _DISPLAY_CONFIG

    cfg = _DISPLAY_CONFIG.setdefault("occlusion", {})
    previous = cfg.get("enabled", True)
    try:
        cfg["enabled"] = False
        view._update_view()
        flat = _cartoon_colors(view)

        cfg["enabled"] = True
        view._update_view()
        shaded = _cartoon_colors(view)
    finally:
        cfg["enabled"] = previous

    assert flat.shape == shaded.shape
    # Shading only ever darkens, and it must actually vary across the mesh --
    # a constant factor would just be a dimmer switch.
    assert (shaded[:, :3] <= flat[:, :3] + 1e-9).all()
    assert shaded[:, :3].min() < flat[:, :3].min()
    ratio = shaded[:, :3].sum(axis=1) / np.maximum(flat[:, :3].sum(axis=1), 1e-9)
    assert ratio.std() > 0.05


def test_occlusion_leaves_alpha_alone(view):
    colors = _cartoon_colors(view)
    assert np.allclose(colors[:, 3], 1.0)


def test_disabling_occlusion_is_honoured(view):
    from chisurf.plugins.chimol.chimol.config import _DISPLAY_CONFIG

    cfg = _DISPLAY_CONFIG.setdefault("occlusion", {})
    previous = cfg.get("darkness", 0.7)
    try:
        cfg["darkness"] = 0.0
        view._update_view()
        untouched = _cartoon_colors(view)
        cfg["darkness"] = previous
        view._update_view()
        shaded = _cartoon_colors(view)
    finally:
        cfg["darkness"] = previous
    assert shaded[:, :3].min() < untouched[:, :3].min()
