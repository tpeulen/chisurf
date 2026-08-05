"""The BVH must change *which* primitives a ray tests, and nothing else.

An acceleration structure is the one kind of optimisation that fails silently:
a ray that never visits the box holding the triangle it should have hit does not
crash, it draws the thing behind it. So the property pinned here is not speed
but agreement -- the tree must return exactly what testing every primitive
returns, for every ray.

The exhaustive search below is deliberately a *second* implementation, which is
normally this codebase's dominant failure mode. In a test it is the point: it is
the oracle, it is three lines long, and it has no way to learn the tree's
mistakes. It reuses only the primitive intersection itself, which is what both
paths are supposed to share.

The last test is the guard that the tree is still wired into the tracer at all.
Deleting it would leave every test above passing -- an exhaustive search returns
the same answers, just 150 times slower -- so cost is asserted separately.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.renderer.bvh import (
    _MAX_LEAF,
    STACK_SIZE,
    _moller_trumbore,
    build_bvh,
    closest_hit,
    primitive_bounds,
)


def _stack() -> np.ndarray:
    return np.empty(STACK_SIZE, dtype=np.int32)


def _tree(centers, radii, tris):
    return build_bvh(*primitive_bounds(centers, radii, tris), _MAX_LEAF)


def _exhaustive(ro, d, t_min, centers, radii, tris):
    """Nearest hit by testing every primitive: the oracle the tree must match."""
    best_t, best_prim = np.inf, -1
    for i in range(centers.shape[0]):
        r = radii[i]
        if r <= 0.0:
            continue
        oc = ro - centers[i]
        b = 2.0 * oc @ d
        c = oc @ oc - r * r
        disc = b * b - 4.0 * c
        if disc < 0.0:
            continue
        sq = np.sqrt(disc)
        t = (-b - sq) * 0.5
        if t <= t_min:
            t = (-b + sq) * 0.5
        if t_min < t < best_t:
            best_t, best_prim = t, i
    for j in range(tris.shape[0]):
        t = _moller_trumbore(
            ro[0], ro[1], ro[2], d[0], d[1], d[2],
            tris[j, 0, 0], tris[j, 0, 1], tris[j, 0, 2],
            tris[j, 1, 0], tris[j, 1, 1], tris[j, 1, 2],
            tris[j, 2, 0], tris[j, 2, 1], tris[j, 2, 2],
        )
        if t > t_min and t < best_t:
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
    tree = _tree(centers, radii, tris)
    stack = _stack()

    mismatches = []
    for _ in range(400):
        ro = rng.uniform(-30, 30, 3)
        d = rng.normal(size=3)
        d /= np.linalg.norm(d)
        want_t, want_prim = _exhaustive(ro, d, 1e-6, centers, radii, tris)
        got_t, got_prim = closest_hit(
            ro[0], ro[1], ro[2], d[0], d[1], d[2], 1e-6, np.inf,
            *tree, n_spheres, centers, radii, tris, -1, stack,
        )
        if got_prim != want_prim or not np.isclose(got_t, want_t, atol=1e-9, equal_nan=True):
            mismatches.append((want_prim, got_prim, want_t, got_t))

    assert not mismatches, f"{len(mismatches)} rays disagreed, e.g. {mismatches[:3]}"


def test_a_ray_that_meets_nothing_reports_nothing():
    centers = np.zeros((1, 3))
    radii = np.array([1.0])
    tris = np.zeros((0, 3, 3))
    t, prim = closest_hit(
        0.0, 0.0, 50.0, 0.0, 1.0, 0.0, 1e-6, np.inf,
        *_tree(centers, radii, tris), 1, centers, radii, tris, -1, _stack(),
    )
    assert prim == -1
    assert np.isinf(t)


def test_an_axis_aligned_triangle_is_not_lost():
    """A flat box and a ray in its plane is where a slab test produces a NaN.

    A cartoon is full of exactly axis-aligned triangles, so the bounds are
    padded at build time; without that padding ``0 * inf`` makes the comparison
    false and the triangle silently leaves the picture.
    """
    tris = np.array([[[-1.0, 0.0, -1.0], [1.0, 0.0, -1.0], [0.0, 0.0, 1.0]]])
    centers = np.zeros((0, 3))
    radii = np.zeros(0)
    tree = _tree(centers, radii, tris)
    # Straight down onto the y = 0 plane the triangle lies in.
    t, prim = closest_hit(
        0.0, 5.0, 0.0, 0.0, -1.0, 0.0, 1e-6, np.inf,
        *tree, 0, centers, radii, tris, -1, _stack(),
    )
    assert prim == 0
    assert t == pytest.approx(5.0)


def test_skip_excludes_exactly_one_primitive():
    """The shadow query leaves the surface it starts from out of the search."""
    centers = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, -4.0]])
    radii = np.array([1.0, 1.0])
    tris = np.zeros((0, 3, 3))
    tree = _tree(centers, radii, tris)
    args = (0.0, 0.0, 10.0, 0.0, 0.0, -1.0, 1e-6, np.inf)
    _, near = closest_hit(*args, *tree, 2, centers, radii, tris, -1, _stack())
    _, far = closest_hit(*args, *tree, 2, centers, radii, tris, 0, _stack())
    assert near == 0
    assert far == 1


# --------------------------------------------------------------------------- #
# Tree invariants
# --------------------------------------------------------------------------- #
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


def test_an_empty_scene_builds_a_usable_tree():
    empty_c, empty_r = np.zeros((0, 3)), np.zeros(0)
    empty_t = np.zeros((0, 3, 3))
    tree = _tree(empty_c, empty_r, empty_t)
    _, prim = closest_hit(
        0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1e-6, np.inf,
        *tree, 0, empty_c, empty_r, empty_t, -1, _stack(),
    )
    assert prim == -1


# --------------------------------------------------------------------------- #
# The tree is actually in the tracer's path
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_cost_grows_far_slower_than_the_triangle_count():
    """Thirty-two times the triangles must not cost thirty-two times the time.

    Every test above passes just as well against an exhaustive search, so this
    is the one that fails if the tree is removed from the tracer. The margin is
    deliberately loose -- a factor of 8 against a linear factor of 32 -- so a
    loaded machine cannot make it flake while a lost BVH still cannot slip
    through.

    Measured at a resolution a render actually uses. Building the tree *is*
    linear in the primitive count, so on a thumbnail the build dominates and the
    ratio approaches the linear one for reasons that have nothing to do with
    traversal -- at 96x96 this same comparison reads 8.6x.
    """
    from chisurf.plugins.chimol.chimol.renderer.raytracer import (
        RayCamera,
        Sphere,
        trace,
    )

    def render(n_tris: int) -> float:
        rng = np.random.default_rng(3)
        anchors = rng.uniform(-8, 8, (n_tris, 1, 3))
        tris = anchors + rng.uniform(-0.4, 0.4, (n_tris, 3, 3))
        camera = RayCamera(
            origin=np.array([0.0, 0.0, 40.0]),
            forward=np.array([0.0, 0.0, -1.0]),
            up=np.array([0.0, 1.0, 0.0]),
            far_clip=80.0,
        )
        kw = dict(
            spheres=[], camera=camera,
            light_directions=np.array([[0.0, 0.0, 1.0]]),
            width=320, height=240, ssaa=1, shadow=False,
            tri_vertices=tris,
            tri_vnormals=np.tile(np.array([0.0, 0.0, 1.0]), (n_tris, 3, 1)),
            tri_colors=np.full((n_tris, 3), 0.7),
        )
        trace(**kw)  # warm the JIT; the first call compiles
        t0 = time.perf_counter()
        trace(**kw)
        return time.perf_counter() - t0

    small = render(1_000)
    large = render(32_000)
    assert large < small * 8.0, (
        f"32x the triangles cost {large / max(small, 1e-9):.1f}x the time "
        f"({small:.3f}s -> {large:.3f}s); the ray tracer looks like it is "
        "testing every primitive again"
    )
