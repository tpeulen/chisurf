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

from chimol.geometry.ambient import occlusion_from_spheres

_ORIGIN = np.array([[0.0, 0.0, 0.0]])
_UP = np.array([[0.0, 0.0, 1.0]])
_DOWN = np.array([[0.0, 0.0, -1.0]])


def _brute_force_occlusion(points, normals, centers, radii, max_distance, strength):
    """The whole ``(N, M)`` distance matrix, with no spatial index at all.

    Parameters
    ----------
    points, normals : numpy.ndarray
        ``(N, 3)`` vertices and unit normals.
    centers : numpy.ndarray
        ``(M, 3)`` occluder centres.
    radii : numpy.ndarray
        ``(M,)`` occluder radii.
    max_distance, strength : float
        As :func:`occlusion_from_spheres`.

    Returns
    -------
    numpy.ndarray
        ``(N,)`` occlusion in ``[0, 1]``.

    Notes
    -----
    This lives in the test rather than beside the implementation on purpose. It
    used to be a second production code path, which meant the thing that was
    supposed to check the fast route was itself unexercised outside this file —
    the same shape of mistake as a fallback that is never taken. Here it is
    unambiguously a reference: quadratic, obvious, and impossible to reach by
    accident.
    """
    v = centers[None, :, :] - points[:, None, :]
    d2 = np.einsum("ijk,ijk->ij", v, v)
    with np.errstate(invalid="ignore", divide="ignore"):
        d = np.sqrt(d2)
        cos_theta = np.einsum("ijk,ik->ij", v, normals) / d
        sin_a = np.minimum(radii[None, :] / d, 1.0)
        cov = 1.0 - np.sqrt(np.maximum(1.0 - sin_a * sin_a, 0.0))
    valid = (d2 < max_distance ** 2) & (d2 > 1e-12) & (d > radii[None, :]) & (cos_theta > 0.0)
    contrib = np.where(valid, cos_theta * cov, 0.0)
    return np.clip(1.0 - np.exp(-strength * contrib.sum(axis=1)), 0.0, 1.0)


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
# The indexed route must agree with the unindexed one
# --------------------------------------------------------------------------- #
def test_the_indexed_and_brute_force_paths_agree():
    rng = np.random.default_rng(0)
    points = rng.normal(size=(500, 3)) * 5.0
    normals = rng.normal(size=(500, 3))
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    centers = rng.normal(size=(300, 3)) * 5.0
    radii = rng.uniform(1.0, 2.0, 300)

    fast = occlusion_from_spheres(
        points, normals, centers, radii, max_distance=8.0, strength=1.3
    )
    reference = _brute_force_occlusion(
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
    from chimol.io.structure import _read_full_model
    from chimol.core.viewer import MolView

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
    from chimol.core.settings.config import _DISPLAY_CONFIG

    cfg = _DISPLAY_CONFIG.setdefault("occlusion", {})
    previous = cfg.get("enabled", True)
    try:
        cfg["enabled"] = False
        view.update_view()
        flat = _cartoon_colors(view)

        cfg["enabled"] = True
        view.update_view()
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
    from chimol.core.settings.config import _DISPLAY_CONFIG

    cfg = _DISPLAY_CONFIG.setdefault("occlusion", {})
    previous = cfg.get("darkness", 0.7)
    try:
        cfg["darkness"] = 0.0
        view.update_view()
        untouched = _cartoon_colors(view)
        cfg["darkness"] = previous
        view.update_view()
        shaded = _cartoon_colors(view)
    finally:
        cfg["darkness"] = previous
    assert shaded[:, :3].min() < untouched[:, :3].min()


# --------------------------------------------------------------------------- #
# The backend needs the occlusion, not only the darkened colour
# --------------------------------------------------------------------------- #
def test_occlusion_is_attached_to_the_geometry(view):
    """The GL shader damps ambient, rim and reflection with it.

    Those terms do not come from the surface colour, so baking the occlusion
    into the colour alone leaves them free to light a crevice from directions it
    cannot see -- which made the occlusion read as an overall dimming instead of
    as shape.
    """
    scene = view.get_current_scene()
    meshes = [o for o in scene.objects if o.geometry.kind == "mesh"]
    assert meshes
    for obj in meshes:
        occ = obj.geometry.occlusion
        assert occ is not None, f"{obj.id} carries no occlusion"
        assert occ.shape[0] == obj.geometry.positions.shape[0]
        assert occ.min() >= 0.0 and occ.max() <= 1.0
        assert occ.max() > 0.0, f"{obj.id} occlusion is uniformly zero"


def test_the_occlusion_matches_the_darkening_in_the_colours(view):
    """The two channels must describe the same shading, not drift apart."""
    scene = view.get_current_scene()
    obj = next(o for o in scene.objects if o.id.endswith("cartoon"))
    occ = obj.geometry.occlusion
    brightness = obj.geometry.colors[:, :3].sum(axis=1)
    # Rank correlation is enough and is robust to the per-residue base colour.
    order_occ = np.argsort(np.argsort(occ))
    order_bright = np.argsort(np.argsort(-brightness))
    assert np.corrcoef(order_occ, order_bright)[0, 1] > 0.5


def test_geometry_without_occlusion_is_still_valid():
    """Overlays and grids carry no occlusion; the backend must accept that."""
    from chimol.render.scene import Geometry

    geom = Geometry(kind="mesh", positions=np.zeros((3, 3)))
    assert geom.occlusion is None


# --------------------------------------------------------------------------- #
# Cast shadows: a different cue from occlusion
# --------------------------------------------------------------------------- #
# Ambient occlusion says how *enclosed* a point is; this says whether anything
# stands between it and the light. PyMOL casts shadows only when raytracing, so
# having them in the interactive view is chimol going further rather than
# matching.

from chimol.geometry.ambient import (  # noqa: E402
    directional_occlusion,
)

_LIGHT = np.array([0.0, 0.0, 1.0])


def _shadow(normals, centers, radii, **kw) -> float:
    result = directional_occlusion(
        _ORIGIN, normals, np.atleast_2d(centers), np.atleast_1d(radii),
        _LIGHT, **kw
    )
    assert result is not None
    return float(result[0])


def test_an_open_sky_casts_no_shadow():
    assert _shadow(_UP, [0.0, 0.0, -5.0], 2.0, max_distance=20.0) == 0.0


def test_an_occluder_on_the_light_ray_shadows():
    """One occluder squarely on the ray blocks exactly once.

    A sphere the ray passes through the centre of contributes ``blocked = 1``,
    so the shadow is ``1 - exp(-strength)``. The threshold here used to be
    ``> 0.8``, which no single contribution can reach at ``strength = 1`` — it
    was calibrated against a cell list that stepped along the ray in strides of
    ``max_distance`` and searched overlapping 3×3×3 neighbourhoods, counting the
    same occluder two or three times. Pinning the exact value is what stops that
    from being re-introduced as "the shadows look stronger".
    """
    lit = _shadow(_UP, [0.0, 0.0, 5.0], 2.0, max_distance=20.0)
    assert lit == pytest.approx(1.0 - math.exp(-1.0))


def test_an_occluder_beside_the_ray_does_not():
    assert _shadow(_UP, [9.0, 0.0, 5.0], 2.0, max_distance=20.0) == 0.0


def test_a_graze_gives_a_soft_edge():
    """A hard in/out test would stair-step at this scale."""
    full = _shadow(_UP, [0.0, 0.0, 5.0], 2.0, max_distance=20.0)
    graze = _shadow(_UP, [2.6, 0.0, 5.0], 2.0, max_distance=20.0)
    assert 0.0 < graze < full


def test_softness_widens_the_penumbra():
    tight = _shadow(_UP, [2.6, 0.0, 5.0], 2.0, max_distance=20.0, softness=1.2)
    wide = _shadow(_UP, [2.6, 0.0, 5.0], 2.0, max_distance=20.0, softness=2.5)
    assert wide > tight


def test_a_surface_facing_away_is_left_to_the_diffuse_term():
    assert _shadow(_DOWN, [0.0, 0.0, 5.0], 2.0, max_distance=20.0) == 0.0


def test_a_shadow_ray_does_not_start_inside_its_own_occluder():
    assert _shadow(_UP, [0.0, 0.0, 1.0], 2.0, max_distance=20.0) == 0.0


def test_occluders_beyond_the_reach_are_ignored():
    assert _shadow(_UP, [0.0, 0.0, 30.0], 2.0, max_distance=20.0) == 0.0


def test_a_degenerate_light_direction_is_rejected():
    assert directional_occlusion(
        _ORIGIN, _UP, np.array([[0.0, 0.0, 5.0]]), 2.0, np.zeros(3)
    ) is None


def test_shadowing_reaches_the_mesh_colours(view):
    """Off vs on must actually change what is drawn."""
    from chimol.core.settings.config import _DISPLAY_CONFIG

    cfg = _DISPLAY_CONFIG.setdefault("occlusion", {})
    previous = cfg.get("shadows", True)
    try:
        cfg["shadows"] = False
        view.update_view()
        unshadowed = _cartoon_colors(view)
        cfg["shadows"] = True
        view.update_view()
        shadowed = _cartoon_colors(view)
    finally:
        cfg["shadows"] = previous

    assert shadowed.shape == unshadowed.shape
    assert (shadowed[:, :3] <= unshadowed[:, :3] + 1e-9).all()
    assert shadowed[:, :3].min() < unshadowed[:, :3].min()
