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

The tree is built **breadth-first with a median split on the widest centroid
axis**, entirely in array operations: one sort per level over the whole
primitive array, with the nodes of that level as the primary sort key. That is
what lets the build be NumPy rather than a compiled per-node loop -- a binned
surface-area heuristic evaluates candidate planes *per node*, which is a loop
over nodes and exactly what could not be written this way.

The cost of that choice is real but small: a median split balances the counts
and can leave two children overlapping where SAH would have separated them.
Measured on the scenes chimol renders it costs a few per cent of traversal, and
the traversal now runs on the GPU, where it is not the bottleneck.

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
    Built one *level* at a time, and with no Python loop over nodes at all. The
    nodes of a level always partition ``prim_index`` into contiguous runs, so the
    bounds for the whole level are one ``reduceat`` and the partition is one
    ``lexsort`` keyed by (node, centroid along that node's widest axis).

    The per-node loop is what had to go, not just the per-primitive one. A
    32k-triangle mesh has 8k leaves, so iterating the frontier in Python cost
    more than the sorts did -- and it showed up as the tracer's cost growing
    9.5x for 32x the triangles, which reads as a broken tree and was a slow
    build.
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

    centroid = 0.5 * (lower + upper)
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

        ordered_min = lower[order]
        ordered_max = upper[order]
        ordered_centroid = centroid[order]
        node_min[frontier] = np.minimum.reduceat(ordered_min, starts, axis=0)
        node_max[frontier] = np.maximum.reduceat(ordered_max, starts, axis=0)
        centre_lo = np.minimum.reduceat(ordered_centroid, starts, axis=0)
        centre_hi = np.maximum.reduceat(ordered_centroid, starts, axis=0)

        extent = centre_hi - centre_lo
        axis = np.argmax(extent, axis=1)
        widest = extent[np.arange(extent.shape[0]), axis]
        # A node whose centroids coincide has no plane that separates them, and
        # the depth cap turns the last level into leaves however full they are.
        splittable = (counts > leaf_size) & (widest > 1e-12) & (depth < _MAX_DEPTH)
        if not splittable.any():
            break

        # One sort for the whole level: primary key the node, secondary key the
        # centroid along that node's own widest axis. Nodes that are not being
        # split keep their order, because their key is constant within the run.
        segment = np.repeat(np.arange(counts.size, dtype=np.int64), counts)
        key = np.where(
            splittable[segment],
            ordered_centroid[np.arange(n), axis[segment]],
            0.0,
        )
        order = order[np.lexsort((key, segment))]

        parents = frontier[splittable]
        parent_start = starts[splittable]
        parent_count = counts[splittable]
        half = parent_count // 2
        left = n_nodes + 2 * np.arange(parents.size, dtype=np.int64)
        node_left[parents] = left.astype(np.int32)
        node_start[left] = parent_start
        node_count[left] = half
        node_start[left + 1] = parent_start + half
        node_count[left + 1] = parent_count - half
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
