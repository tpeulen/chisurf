"""The BVH must change *which* primitives a ray tests, and nothing else.

An acceleration structure is the one kind of optimisation that fails silently: a
ray that never visits the box holding the triangle it should have hit does not
crash, it draws the thing behind it. So the property pinned here is not speed but
agreement -- the tree must return exactly what testing every primitive returns,
for every ray.

The exhaustive search below is deliberately a *second* implementation, which is
normally this codebase's dominant failure mode. In a test it is the point: it is
the oracle, it is short, and it has no way to learn the tree's mistakes. It
shares nothing with the tree, not even the intersection code, because the
traversal now lives in WGSL and the oracle has to stay readable in Python.

Traversal is reached through ``compute.closest_hit``, which runs the *same*
``closest_hit`` function the tracer runs -- both shaders are the BVH prelude plus
an entry point -- so what this exercises is the real thing rather than a copy.
"""

from __future__ import annotations

import numpy as np
import pytest

from chimol.renderer import compute
from chimol.renderer import bvh as bvh_module
from chimol.renderer.bvh import (
    _MAX_LEAF,
    build_bvh,
    build_bvh_cached,
    primitive_bounds,
)

pytestmark = pytest.mark.skipif(
    not compute.available(), reason="no WebGPU adapter on this machine"
)


def _tree(centers, radii, tris):
    return build_bvh(*primitive_bounds(centers, radii, tris), _MAX_LEAF)


def _scene(centers, radii, tris):
    return compute.RayScene(centers, radii, tris, _tree(centers, radii, tris))


def _exhaustive(ro, d, t_min, centers, radii, tris):
    """Nearest hit by testing every primitive: the oracle the tree must match."""
    best_t, best_prim = np.inf, -1
    for i in range(centers.shape[0]):
        r = radii[i]
        if r <= 0.0:
            continue
        oc = ro - centers[i]
        half_b = oc @ d
        c = oc @ oc - r * r
        disc = half_b * half_b - c
        if disc < 0.0:
            continue
        root = np.sqrt(disc)
        t = -half_b - root
        if t <= t_min:
            t = -half_b + root
        if t_min < t < best_t:
            best_t, best_prim = t, i
    for j in range(tris.shape[0]):
        v0, v1, v2 = tris[j]
        e1, e2 = v1 - v0, v2 - v0
        pvec = np.cross(d, e2)
        det = e1 @ pvec
        if abs(det) < 1e-12:
            continue
        inv = 1.0 / det
        tvec = ro - v0
        u = (tvec @ pvec) * inv
        if u < 0.0 or u > 1.0:
            continue
        qvec = np.cross(tvec, e1)
        v = (d @ qvec) * inv
        if v < 0.0 or u + v > 1.0:
            continue
        t = (e2 @ qvec) * inv
        if t >= 1e-6 and t_min < t < best_t:
            best_t, best_prim = t, centers.shape[0] + j
    return best_t, best_prim


def _random_scene(rng, n_spheres, n_tris):
    centers = rng.uniform(-10, 10, (n_spheres, 3))
    radii = rng.uniform(0.2, 1.5, n_spheres)
    # Triangles of a realistic size relative to the scene, not random points in
    # the whole box: a mesh's triangles are small and clustered, which is the
    # case the tree has to be good at.
    anchors = rng.uniform(-10, 10, (n_tris, 1, 3))
    tris = anchors + rng.uniform(-0.8, 0.8, (n_tris, 3, 3))
    return centers, radii, tris


# --------------------------------------------------------------------------- #
# The tree returns what an exhaustive search returns
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "n_spheres, n_tris",
    [(200, 0), (0, 200), (120, 120), (1, 1), (0, 1), (1, 0)],
)
def test_tree_agrees_with_exhaustive_search(n_spheres, n_tris):
    rng = np.random.default_rng(20260805)
    centers, radii, tris = _random_scene(rng, n_spheres, n_tris)
    scene = _scene(centers, radii, tris)

    origins = rng.uniform(-30, 30, (400, 3))
    directions = rng.normal(size=(400, 3))
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    got_t, got_prim = compute.closest_hit(scene, origins, directions, 1e-6)

    mismatches = []
    for k in range(origins.shape[0]):
        want_t, want_prim = _exhaustive(
            origins[k], directions[k], 1e-6, centers, radii, tris
        )
        # f32 in the shader against f64 here, so the distance is compared with a
        # tolerance; the *primitive* must match exactly, since picking a
        # different surface is the failure this test exists for.
        agree = want_prim == got_prim[k] and (
            want_prim < 0 or np.isclose(want_t, got_t[k], rtol=2e-5, atol=2e-4)
        )
        if not agree:
            mismatches.append((want_prim, int(got_prim[k]), want_t, float(got_t[k])))

    assert not mismatches, f"{len(mismatches)} rays disagreed, e.g. {mismatches[:3]}"


def test_a_ray_that_meets_nothing_reports_nothing():
    centers = np.zeros((1, 3))
    radii = np.array([1.0])
    tris = np.zeros((0, 3, 3))
    t, prim = compute.closest_hit(
        _scene(centers, radii, tris),
        np.array([[0.0, 0.0, 50.0]]), np.array([[0.0, 1.0, 0.0]]),
    )
    assert prim[0] == -1
    assert np.isinf(t[0])


def test_an_axis_aligned_triangle_is_not_lost():
    """A flat box and a ray in its plane is where a slab test produces a NaN.

    A cartoon is full of exactly axis-aligned triangles, so the bounds are padded
    at build time; without that padding ``0 * inf`` makes the comparison false
    and the triangle silently leaves the picture.
    """
    tris = np.array([[[-1.0, 0.0, -1.0], [1.0, 0.0, -1.0], [0.0, 0.0, 1.0]]])
    centers = np.zeros((0, 3))
    radii = np.zeros(0)
    t, prim = compute.closest_hit(
        _scene(centers, radii, tris),
        np.array([[0.0, 5.0, 0.0]]), np.array([[0.0, -1.0, 0.0]]),
    )
    assert prim[0] == 0
    assert t[0] == pytest.approx(5.0, abs=1e-4)


def test_skip_excludes_exactly_one_primitive():
    """The shadow query leaves the surface it starts from out of the search."""
    centers = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, -4.0]])
    radii = np.array([1.0, 1.0])
    tris = np.zeros((0, 3, 3))
    scene = _scene(centers, radii, tris)
    origin = np.array([[0.0, 0.0, 10.0]])
    direction = np.array([[0.0, 0.0, -1.0]])
    _, near = compute.closest_hit(scene, origin, direction, skip=-1)
    _, far = compute.closest_hit(scene, origin, direction, skip=0)
    assert near[0] == 0
    assert far[0] == 1


# --------------------------------------------------------------------------- #
# Tree invariants -- these need no device
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(False, reason="pure CPU")
def test_every_primitive_is_owned_by_exactly_one_leaf():
    rng = np.random.default_rng(7)
    centers, radii, tris = _random_scene(rng, 150, 150)
    node_min, node_max, node_left, node_start, node_count, prim_index = _tree(
        centers, radii, tris
    )
    n_prims = centers.shape[0] + tris.shape[0]

    assert sorted(prim_index.tolist()) == list(range(n_prims)), (
        "prim_index must be a permutation -- a duplicate draws a primitive twice "
        "and an omission drops it from the picture"
    )
    owned: list[int] = []
    for node in range(node_left.shape[0]):
        if node_left[node] < 0:
            s = node_start[node]
            owned.extend(prim_index[s : s + node_count[node]].tolist())
    assert sorted(owned) == list(range(n_prims))


def test_a_node_encloses_both_of_its_children():
    rng = np.random.default_rng(11)
    centers, radii, tris = _random_scene(rng, 100, 100)
    node_min, node_max, node_left, _, _, _ = _tree(centers, radii, tris)
    for node in range(node_left.shape[0]):
        left = node_left[node]
        if left < 0:
            continue
        for child in (left, left + 1):
            assert np.all(node_min[node] <= node_min[child] + 1e-9)
            assert np.all(node_max[node] >= node_max[child] - 1e-9)


def test_a_leaf_is_never_larger_than_the_cap_unless_it_has_to_be():
    """Median splitting must actually reduce the leaves it can reduce.

    A build that stopped splitting early would still pass every agreement test
    above -- an exhaustive search returns the same answers -- so the shape of the
    tree is asserted separately from what it finds.
    """
    rng = np.random.default_rng(13)
    centers, radii, tris = _random_scene(rng, 500, 500)
    _, _, node_left, _, node_count, _ = _tree(centers, radii, tris)
    leaves = node_count[node_left < 0]
    assert leaves.max() <= _MAX_LEAF
    assert leaves.sum() == 1000


def test_an_empty_scene_builds_a_usable_tree():
    empty_c, empty_r = np.zeros((0, 3)), np.zeros(0)
    empty_t = np.zeros((0, 3, 3))
    _, prim = compute.closest_hit(
        _scene(empty_c, empty_r, empty_t),
        np.zeros((1, 3)), np.array([[0.0, 0.0, 1.0]]),
    )
    assert prim[0] == -1


# --------------------------------------------------------------------------- #
# The cache returns the same tree, and only when it should
# --------------------------------------------------------------------------- #
def test_the_cache_is_hit_for_an_identical_scene():
    """A second render of unchanged geometry must not rebuild the tree.

    On a traced solvent surface the build is 70 % of the render, and `ray` is a
    command people run again after changing a light or a colour. A cached tree
    and a rebuilt one are indistinguishable from the outside, so the build
    counter is the only way to see this working.
    """
    rng = np.random.default_rng(21)
    centers, radii, tris = _random_scene(rng, 200, 200)
    lower, upper = primitive_bounds(centers, radii, tris)

    before = bvh_module.build_count
    first = build_bvh_cached(lower, upper, _MAX_LEAF)
    assert bvh_module.build_count == before + 1
    again = build_bvh_cached(lower.copy(), upper.copy(), _MAX_LEAF)
    assert bvh_module.build_count == before + 1, "a rebuilt tree, not a cached one"
    # The same arrays, not merely equal ones -- a copy would defeat the point.
    for a, b in zip(first, again):
        assert a is b


def test_the_cache_notices_a_moved_molecule():
    """Identity would never match and a shape check would match too often."""
    rng = np.random.default_rng(22)
    centers, radii, tris = _random_scene(rng, 200, 200)
    lower, upper = primitive_bounds(centers, radii, tris)
    build_bvh_cached(lower, upper, _MAX_LEAF)

    moved_lower, moved_upper = primitive_bounds(centers + 3.0, radii, tris + 3.0)
    before = bvh_module.build_count
    build_bvh_cached(moved_lower, moved_upper, _MAX_LEAF)
    assert bvh_module.build_count == before + 1

    # Same geometry, different leaf size, is a different tree.
    before = bvh_module.build_count
    build_bvh_cached(lower, upper, _MAX_LEAF * 2)
    assert bvh_module.build_count == before + 1


def test_a_cached_tree_is_the_tree_build_bvh_would_have_made():
    rng = np.random.default_rng(23)
    centers, radii, tris = _random_scene(rng, 300, 300)
    lower, upper = primitive_bounds(centers, radii, tris)
    for cached, direct in zip(
        build_bvh_cached(lower, upper, _MAX_LEAF), build_bvh(lower, upper, _MAX_LEAF)
    ):
        assert np.array_equal(cached, direct)


# --------------------------------------------------------------------------- #
# The tree is actually in the tracer's path
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_cost_grows_far_slower_than_the_triangle_count():
    """Thirty-two times the triangles must not cost thirty-two times the time.

    Every test above passes just as well against an exhaustive search, so this is
    the one that fails if the tree is removed from the tracer. The margin is
    deliberately loose so a loaded machine cannot make it flake while a lost BVH
    still cannot slip through.

    The first call of the process compiles the shader, which costs far more than
    either render, so both sizes are rendered once before either is timed.

    Measured at a resolution where *tracing* dominates. At 320x240 it no longer
    does: the traversal is on the GPU and the tree build is NumPy on the host, so
    at 32k triangles the build is 80 ms against a 20 ms trace and the ratio
    hovers on the threshold -- the test failed one run in three while the tree
    was perfectly good. What it is for is the tree, so it has to be measured
    where the tree is what costs.
    """
    import time

    from chimol.renderer.raytracer import (
        RayCamera,
        Sphere,
        trace,
    )

    def scene_kwargs(n_tris: int) -> dict:
        rng = np.random.default_rng(3)
        anchors = rng.uniform(-8, 8, (n_tris, 1, 3))
        tris = anchors + rng.uniform(-0.4, 0.4, (n_tris, 3, 3))
        camera = RayCamera(
            origin=np.array([0.0, 0.0, 40.0]),
            forward=np.array([0.0, 0.0, -1.0]),
            up=np.array([0.0, 1.0, 0.0]),
            far_clip=80.0,
        )
        return dict(
            spheres=[], camera=camera,
            light_directions=np.array([[0.0, 0.0, 1.0]]),
            width=960, height=720, ssaa=1, shadow=False,
            tri_vertices=tris,
            tri_vnormals=np.tile(np.array([0.0, 0.0, 1.0]), (n_tris, 3, 1)),
            tri_colors=np.full((n_tris, 3), 0.7),
        )

    small_kw, large_kw = scene_kwargs(1_000), scene_kwargs(32_000)
    trace(**small_kw)
    trace(**large_kw)

    t0 = time.perf_counter()
    trace(**small_kw)
    small = time.perf_counter() - t0
    t0 = time.perf_counter()
    trace(**large_kw)
    large = time.perf_counter() - t0

    assert large < small * 8.0, (
        f"32x the triangles cost {large / max(small, 1e-9):.1f}x the time "
        f"({small:.3f}s -> {large:.3f}s); the ray tracer looks like it is "
        "testing every primitive again"
    )


def test_the_tracer_says_so_when_there_is_no_device(monkeypatch):
    """No adapter is an error with a name, not a silent CPU path.

    There is deliberately no CPU tracer: chimol's renderer is WebGPU, so a
    session that can display a molecule can trace one, and a second shading
    implementation would be a large body of code nothing ever runs.
    """
    from chimol.renderer import raytracer

    monkeypatch.setattr(compute, "raytrace", lambda *a, **k: None)
    with pytest.raises(raytracer.NoComputeDevice):
        raytracer.trace(
            spheres=[raytracer.Sphere(center=np.zeros(3), radius=1.0,
                                      color=np.ones(3))],
            camera=raytracer.RayCamera(
                origin=np.array([0.0, 0.0, 10.0]),
                forward=np.array([0.0, 0.0, -1.0]),
                up=np.array([0.0, 1.0, 0.0]),
            ),
            light_directions=np.array([[0.0, 0.0, 1.0]]),
            width=8, height=8, ssaa=1,
        )
