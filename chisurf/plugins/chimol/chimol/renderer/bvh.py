"""A bounding-volume hierarchy, so a ray stops testing every primitive.

The tracer beside this module was exhaustive: each ray intersected every sphere
and every triangle in the scene, for every sample, for every transparency layer.
That is ``O(primitives)`` per ray, and a molecule is not a handful of primitives
-- 148L's cartoon is 39 252 triangles, its solvent surface 51 748 -- so a
640x480 render spent its time on the ~99.9 % of the scene each ray misses.

A BVH sorts the primitives into a tree of nested boxes once, before the first
ray. A ray then descends only the boxes it actually pierces, which turns the
per-ray cost into ``O(log primitives)``. Building the tree costs a fraction of a
single row of pixels, so there is no scene small enough for it not to pay.

The tree is built **breadth-first with a spatial-midpoint split on the widest
centroid axis**, entirely in array operations and with no sort at all: a level
is one ``reduceat`` for its bounds and one stable partition, and a stable
partition of contiguous runs is a ``cumsum``. That is what lets the build be
NumPy rather than a compiled per-node loop -- a binned surface-area heuristic
evaluates candidate planes *per node*, which is a loop over nodes and exactly
what could not be written this way.

A midpoint split can put every primitive of a node on one side, which a median
split cannot; when that happens the node falls back to halving its primitives in
their current order, which is arbitrary but always makes progress. It can also
leave two children overlapping where SAH would have separated them. Both cost a
little traversal and neither is where the time goes: the traversal runs on the
GPU and the *build* was the bottleneck -- 80-110 ms for 32k triangles against a
20-90 ms trace, almost all of it in the per-level sort this replaces.

Primitives are addressed by one index space so a scene of mixed kinds is one
tree: ``prim < n_spheres`` is a sphere, and anything above it is triangle
``prim - n_spheres``. A wireframe -- round caps as spheres, shafts as triangles
-- is the case that made a unified tree worth having over one tree per kind.
"""

from __future__ import annotations

import numpy as np

#: Primitives a leaf may hold. Small leaves mean a deeper tree and more box
#: tests; large ones mean more primitive tests. Four is the usual sweet spot for
#: triangles and measured no worse than two or eight here.
_MAX_LEAF = 4

#: How deep the tree may go before a node is forced to be a leaf. A pathological
#: split sequence could otherwise grow a tree deeper than the traversal stack,
#: and a stack that overflows silently drops geometry out of the picture. An
#: over-full leaf is merely slow, which is the right way for this to fail.
_MAX_DEPTH = 60

#: Traversal stack depth, matching the fixed-size stack in ``wgsl/bvh.wgsl``.
#: Bounded by :data:`_MAX_DEPTH` plus room for the root.
STACK_SIZE = _MAX_DEPTH + 4



def build_bvh(prim_min, prim_max, max_leaf):
    """Build a BVH over axis-aligned primitive bounds.

    Parameters
    ----------
    prim_min, prim_max : numpy.ndarray
        Per-primitive bounding box, shape ``(P, 3)``. A primitive's box must
        enclose it completely; :func:`primitive_bounds` pads flat boxes so a
        ray parallel to a degenerate slab cannot produce a NaN.
    max_leaf : int
        Primitives a leaf may hold before the node is split.

    Returns
    -------
    tuple of numpy.ndarray
        ``(node_min, node_max, node_left, node_start, node_count, prim_index)``.
        ``node_left`` is the index of a node's left child, with the right child
        always at ``left + 1``, and ``-1`` marking a leaf. A leaf owns
        ``prim_index[node_start : node_start + node_count]``, so ``prim_index``
        is a permutation of the primitives and the primitives themselves are
        never moved.

    Notes
    -----
    Built one *level* at a time, with no Python loop over nodes and no sort. The
    nodes of a level always partition ``prim_index`` into contiguous runs, so the
    bounds for the whole level are one ``reduceat``, and splitting them is a
    stable partition about each node's midpoint -- which for contiguous runs is
    two running counts and a scatter.

    Both of those were arrived at the hard way. The per-node Python loop went
    first: a 32k-triangle mesh has 8k leaves, and iterating the frontier cost
    more than the array work did. What was left was a `lexsort` per level, and
    that was still 80-110 ms for 32k triangles -- more than the trace it was
    accelerating.
    """
    lower = np.ascontiguousarray(prim_min, dtype=np.float64).reshape(-1, 3)
    upper = np.ascontiguousarray(prim_max, dtype=np.float64).reshape(-1, 3)
    n = lower.shape[0]
    leaf_size = max(1, int(max_leaf))

    if n == 0:
        return (
            np.zeros((1, 3), dtype=np.float64), np.zeros((1, 3), dtype=np.float64),
            np.full(1, -1, dtype=np.int32), np.zeros(1, dtype=np.int32),
            np.zeros(1, dtype=np.int32), np.zeros(0, dtype=np.int32),
        )

    # One packed array, gathered once per level instead of three, in f32
    # instead of f64. Both matter and neither is cosmetic: the three separate
    # `(n, 3)` float64 gathers were 21 ms of a 52 ms build, and the node bounds
    # are handed to the shader as f32 anyway, so the wider type bought nothing.
    #
    # The upper bound and the upper centroid are stored **negated**, so a single
    # `minimum.reduceat` over the twelve columns yields all four bounds -- min of
    # the lows, and minus the max of the highs.
    centroid = 0.5 * (lower + upper)
    packed = np.empty((n, 12), dtype=np.float32)
    packed[:, 0:3] = lower
    packed[:, 3:6] = -upper
    packed[:, 6:9] = centroid
    packed[:, 9:12] = -centroid
    order = np.arange(n, dtype=np.int64)

    capacity = 2 * n + 1
    node_min = np.zeros((capacity, 3), dtype=np.float64)
    node_max = np.zeros((capacity, 3), dtype=np.float64)
    node_left = np.full(capacity, -1, dtype=np.int32)
    node_start = np.zeros(capacity, dtype=np.int64)
    node_count = np.zeros(capacity, dtype=np.int64)
    node_start[0] = 0
    node_count[0] = n
    n_nodes = 1

    # The frontier is every current leaf, in ascending `start` order, so it
    # always tiles [0, n) -- which is what lets `reduceat` read the whole level
    # in one call. Nodes that stop splitting stay in it; they simply never
    # satisfy the split test again.
    frontier = np.zeros(1, dtype=np.int64)

    for depth in range(_MAX_DEPTH + 1):
        starts = node_start[frontier]
        counts = node_count[frontier]

        ordered = packed[order]
        bounds = np.minimum.reduceat(ordered, starts, axis=0)
        node_min[frontier] = bounds[:, 0:3]
        node_max[frontier] = -bounds[:, 3:6]
        centre_lo = bounds[:, 6:9]
        centre_hi = -bounds[:, 9:12]

        extent = centre_hi - centre_lo
        axis = np.argmax(extent, axis=1)
        widest = extent[np.arange(extent.shape[0]), axis]
        # A node whose centroids coincide has no plane that separates them, and
        # the depth cap turns the last level into leaves however full they are.
        splittable = (counts > leaf_size) & (widest > 1e-12) & (depth < _MAX_DEPTH)
        if not splittable.any():
            break

        # Partition, not sort. Within each node's contiguous run the
        # primitives below the midpoint keep their order and move to the front,
        # the rest follow -- and a stable partition of runs is just two running
        # counts, so the whole level is a handful of O(n) passes instead of an
        # O(n log n) `lexsort`. That sort was the build's entire cost.
        # int32 throughout: a scene with more than two billion primitives is not
        # a scene, and the wider type doubles the memory this walks per level.
        segment = np.repeat(np.arange(counts.size, dtype=np.int32), counts)
        midpoint = 0.5 * (centre_lo + centre_hi)
        own_axis = axis[segment]
        coordinate = ordered[np.arange(n), 6 + own_axis]
        goes_left = coordinate < midpoint[segment, own_axis]
        # A node that is not being split must not be reshuffled.
        goes_left |= ~splittable[segment]

        left_running = np.cumsum(goes_left, dtype=np.int32)
        right_running = np.arange(1, n + 1, dtype=np.int32) - left_running
        before = np.zeros(counts.size + 1, dtype=np.int64)
        before[1:] = np.cumsum(counts)
        zero = np.zeros(1, dtype=np.int32)
        left_before = np.concatenate((zero, left_running))[before[:-1]]
        right_before = np.concatenate((zero, right_running))[before[:-1]]
        left_total = np.add.reduceat(goes_left.astype(np.int32), starts)

        rank_left = left_running - 1 - left_before[segment]
        rank_right = right_running - 1 - right_before[segment]
        destination = starts[segment].astype(np.int64) + np.where(
            goes_left, rank_left, left_total[segment] + rank_right
        )
        partitioned = np.empty_like(order)
        partitioned[destination] = order
        order = partitioned

        # An empty side means the midpoint separated nothing, which a median
        # never does. Halving in the current order is arbitrary and always makes
        # progress; without it the node would be rebuilt identically for ever.
        half = np.where(
            (left_total == 0) | (left_total == counts), counts // 2, left_total
        )

        parents = frontier[splittable]
        parent_start = starts[splittable]
        parent_count = counts[splittable]
        parent_half = half[splittable]
        left = n_nodes + 2 * np.arange(parents.size, dtype=np.int64)
        node_left[parents] = left.astype(np.int32)
        node_start[left] = parent_start
        node_count[left] = parent_half
        node_start[left + 1] = parent_start + parent_half
        node_count[left + 1] = parent_count - parent_half
        n_nodes += 2 * parents.size

        # The next frontier is the unsplit leaves plus the new children, back in
        # ascending `start` order so it keeps tiling [0, n).
        following = np.concatenate((frontier[~splittable], left, left + 1))
        frontier = following[np.argsort(node_start[following], kind="stable")]

    return (
        node_min[:n_nodes],
        node_max[:n_nodes],
        node_left[:n_nodes],
        node_start[:n_nodes].astype(np.int32),
        node_count[:n_nodes].astype(np.int32),
        order.astype(np.int32),
    )


def primitive_bounds(centers, radii, tri_vertices):
    """Axis-aligned bounds for spheres then triangles, in one index space.

    Parameters
    ----------
    centers, radii : numpy.ndarray
        Sphere data, shapes ``(S, 3)`` and ``(S,)``.
    tri_vertices : numpy.ndarray
        Triangle corners, shape ``(T, 3, 3)``.

    Returns
    -------
    tuple of numpy.ndarray
        ``(prim_min, prim_max)``, shape ``(S + T, 3)``. Boxes are padded
        outwards: a cartoon has triangles that are exactly axis-aligned and
        therefore exactly flat in one dimension, and a ray travelling in that
        plane would otherwise compute ``0 * inf`` and drop the triangle out of
        the picture on a NaN comparison.
    """
    centers = np.asarray(centers, dtype=np.float64).reshape(-1, 3)
    radii = np.asarray(radii, dtype=np.float64).reshape(-1)
    tri_vertices = np.asarray(tri_vertices, dtype=np.float64).reshape(-1, 3, 3)

    r = np.maximum(radii, 0.0)[:, None]
    mins = [centers - r]
    maxs = [centers + r]
    if tri_vertices.shape[0]:
        mins.append(tri_vertices.min(axis=1))
        maxs.append(tri_vertices.max(axis=1))

    prim_min = np.concatenate(mins, axis=0) if len(mins) > 1 else mins[0]
    prim_max = np.concatenate(maxs, axis=0) if len(maxs) > 1 else maxs[0]

    pad = 1e-6 * np.maximum(np.abs(prim_max - prim_min).max(initial=1.0), 1.0)
    return prim_min - pad, prim_max + pad
