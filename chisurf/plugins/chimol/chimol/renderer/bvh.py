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

The tree is built with a **binned surface-area heuristic**, the standard
quality/build-time compromise: candidate split planes are evaluated by the
expected cost of the two children (their surface area times their primitive
count) rather than by simply halving the primitives, because a split that
balances the *counts* can still produce two deeply overlapping boxes that every
ray has to enter.

Primitives are addressed by one index space so a scene of mixed kinds is one
tree: ``prim < n_spheres`` is a sphere, and anything above it is triangle
``prim - n_spheres``. A wireframe -- round caps as spheres, shafts as triangles
-- is the case that made a unified tree worth having over one tree per kind.
"""

from __future__ import annotations

import numba as _nb
import numpy as np

#: Primitives a leaf may hold. Small leaves mean a deeper tree and more box
#: tests; large ones mean more primitive tests. Four is the usual sweet spot for
#: triangles and measured no worse than two or eight here.
_MAX_LEAF = 4

#: Candidate split planes evaluated per node. Twelve is what a binned SAH build
#: normally uses: enough that the chosen plane is close to the exhaustive
#: optimum, few enough that binning stays a single pass over the node.
_BINS = 12

#: How deep the tree may go before a node is forced to be a leaf. A pathological
#: split sequence could otherwise grow a tree deeper than the traversal stack,
#: and a stack that overflows silently drops geometry out of the picture. An
#: over-full leaf is merely slow, which is the right way for this to fail.
_MAX_DEPTH = 60

#: Traversal stack depth. Bounded by :data:`_MAX_DEPTH` plus room for the root.
STACK_SIZE = _MAX_DEPTH + 4


@_nb.njit(cache=True, fastmath=True)
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
    """
    n = prim_min.shape[0]
    max_nodes = 2 * n + 1
    node_min = np.zeros((max_nodes, 3), dtype=np.float64)
    node_max = np.zeros((max_nodes, 3), dtype=np.float64)
    node_left = np.full(max_nodes, -1, dtype=np.int32)
    node_start = np.zeros(max_nodes, dtype=np.int32)
    node_count = np.zeros(max_nodes, dtype=np.int32)
    node_depth = np.zeros(max_nodes, dtype=np.int32)
    prim_index = np.arange(n).astype(np.int32)

    if n == 0:
        return (
            node_min[:1], node_max[:1], node_left[:1],
            node_start[:1], node_count[:1], prim_index,
        )

    centroid = np.empty((n, 3), dtype=np.float64)
    for i in range(n):
        centroid[i, 0] = 0.5 * (prim_min[i, 0] + prim_max[i, 0])
        centroid[i, 1] = 0.5 * (prim_min[i, 1] + prim_max[i, 1])
        centroid[i, 2] = 0.5 * (prim_min[i, 2] + prim_max[i, 2])

    node_start[0] = 0
    node_count[0] = n
    node_depth[0] = 0
    n_nodes = 1

    stack = np.empty(max_nodes, dtype=np.int32)
    sp = 0
    stack[sp] = 0
    sp += 1

    scratch = np.empty(n, dtype=np.int32)
    bin_count = np.empty(_BINS, dtype=np.int64)
    bin_min = np.empty((_BINS, 3), dtype=np.float64)
    bin_max = np.empty((_BINS, 3), dtype=np.float64)
    left_area = np.empty(_BINS, dtype=np.float64)
    left_count = np.empty(_BINS, dtype=np.int64)

    while sp > 0:
        sp -= 1
        node = stack[sp]
        start = node_start[node]
        count = node_count[node]

        # ---- this node's bounds, and its centroid bounds ----
        bmn0 = 1e300; bmn1 = 1e300; bmn2 = 1e300
        bmx0 = -1e300; bmx1 = -1e300; bmx2 = -1e300
        cmn0 = 1e300; cmn1 = 1e300; cmn2 = 1e300
        cmx0 = -1e300; cmx1 = -1e300; cmx2 = -1e300
        for i in range(start, start + count):
            p = prim_index[i]
            if prim_min[p, 0] < bmn0: bmn0 = prim_min[p, 0]
            if prim_min[p, 1] < bmn1: bmn1 = prim_min[p, 1]
            if prim_min[p, 2] < bmn2: bmn2 = prim_min[p, 2]
            if prim_max[p, 0] > bmx0: bmx0 = prim_max[p, 0]
            if prim_max[p, 1] > bmx1: bmx1 = prim_max[p, 1]
            if prim_max[p, 2] > bmx2: bmx2 = prim_max[p, 2]
            if centroid[p, 0] < cmn0: cmn0 = centroid[p, 0]
            if centroid[p, 1] < cmn1: cmn1 = centroid[p, 1]
            if centroid[p, 2] < cmn2: cmn2 = centroid[p, 2]
            if centroid[p, 0] > cmx0: cmx0 = centroid[p, 0]
            if centroid[p, 1] > cmx1: cmx1 = centroid[p, 1]
            if centroid[p, 2] > cmx2: cmx2 = centroid[p, 2]

        node_min[node, 0] = bmn0
        node_min[node, 1] = bmn1
        node_min[node, 2] = bmn2
        node_max[node, 0] = bmx0
        node_max[node, 1] = bmx1
        node_max[node, 2] = bmx2

        if count <= max_leaf or node_depth[node] >= _MAX_DEPTH:
            continue

        # ---- widest centroid axis ----
        ext0 = cmx0 - cmn0
        ext1 = cmx1 - cmn1
        ext2 = cmx2 - cmn2
        axis = 0
        extent = ext0
        c_lo = cmn0
        if ext1 > extent:
            axis = 1
            extent = ext1
            c_lo = cmn1
        if ext2 > extent:
            axis = 2
            extent = ext2
            c_lo = cmn2
        if extent < 1e-12:
            # Every centroid coincides; no plane separates them. A leaf here is
            # correct, and the depth cap above keeps it from being reached by a
            # runaway recursion instead.
            continue

        # ---- bin the primitives along that axis ----
        scale = float(_BINS) / extent
        for b in range(_BINS):
            bin_count[b] = 0
            bin_min[b, 0] = 1e300; bin_min[b, 1] = 1e300; bin_min[b, 2] = 1e300
            bin_max[b, 0] = -1e300; bin_max[b, 1] = -1e300; bin_max[b, 2] = -1e300
        for i in range(start, start + count):
            p = prim_index[i]
            b = int((centroid[p, axis] - c_lo) * scale)
            if b < 0:
                b = 0
            if b >= _BINS:
                b = _BINS - 1
            bin_count[b] += 1
            for k in range(3):
                if prim_min[p, k] < bin_min[b, k]:
                    bin_min[b, k] = prim_min[p, k]
                if prim_max[p, k] > bin_max[b, k]:
                    bin_max[b, k] = prim_max[p, k]

        # ---- sweep left, then right, costing each of the 11 planes ----
        amn0 = 1e300; amn1 = 1e300; amn2 = 1e300
        amx0 = -1e300; amx1 = -1e300; amx2 = -1e300
        running = 0
        for b in range(_BINS):
            if bin_count[b] > 0:
                if bin_min[b, 0] < amn0: amn0 = bin_min[b, 0]
                if bin_min[b, 1] < amn1: amn1 = bin_min[b, 1]
                if bin_min[b, 2] < amn2: amn2 = bin_min[b, 2]
                if bin_max[b, 0] > amx0: amx0 = bin_max[b, 0]
                if bin_max[b, 1] > amx1: amx1 = bin_max[b, 1]
                if bin_max[b, 2] > amx2: amx2 = bin_max[b, 2]
                running += bin_count[b]
            left_area[b] = _box_area(amn0, amn1, amn2, amx0, amx1, amx2)
            left_count[b] = running

        best_cost = 1e300
        best_split = -1
        amn0 = 1e300; amn1 = 1e300; amn2 = 1e300
        amx0 = -1e300; amx1 = -1e300; amx2 = -1e300
        running = 0
        for b in range(_BINS - 1, 0, -1):
            if bin_count[b] > 0:
                if bin_min[b, 0] < amn0: amn0 = bin_min[b, 0]
                if bin_min[b, 1] < amn1: amn1 = bin_min[b, 1]
                if bin_min[b, 2] < amn2: amn2 = bin_min[b, 2]
                if bin_max[b, 0] > amx0: amx0 = bin_max[b, 0]
                if bin_max[b, 1] > amx1: amx1 = bin_max[b, 1]
                if bin_max[b, 2] > amx2: amx2 = bin_max[b, 2]
                running += bin_count[b]
            n_left = left_count[b - 1]
            n_right = running
            if n_left == 0 or n_right == 0:
                continue
            right_area = _box_area(amn0, amn1, amn2, amx0, amx1, amx2)
            cost = left_area[b - 1] * float(n_left) + right_area * float(n_right)
            if cost < best_cost:
                best_cost = cost
                best_split = b

        # ---- partition prim_index in place around the chosen plane ----
        n_left = 0
        if best_split > 0:
            n_right = 0
            for i in range(start, start + count):
                p = prim_index[i]
                b = int((centroid[p, axis] - c_lo) * scale)
                if b < 0:
                    b = 0
                if b >= _BINS:
                    b = _BINS - 1
                if b < best_split:
                    prim_index[start + n_left] = p
                    n_left += 1
                else:
                    scratch[n_right] = p
                    n_right += 1
            for j in range(n_right):
                prim_index[start + n_left + j] = scratch[j]

        if n_left == 0 or n_left == count:
            # No usable plane -- fall back to halving the primitives so the tree
            # keeps making progress. Without this a node whose SAH split is
            # degenerate would be rebuilt identically forever.
            n_left = count // 2

        left_node = n_nodes
        n_nodes += 1
        right_node = n_nodes
        n_nodes += 1
        node_left[node] = left_node
        node_start[left_node] = start
        node_count[left_node] = n_left
        node_depth[left_node] = node_depth[node] + 1
        node_start[right_node] = start + n_left
        node_count[right_node] = count - n_left
        node_depth[right_node] = node_depth[node] + 1
        stack[sp] = left_node
        sp += 1
        stack[sp] = right_node
        sp += 1

    return (
        node_min[:n_nodes], node_max[:n_nodes], node_left[:n_nodes],
        node_start[:n_nodes], node_count[:n_nodes], prim_index,
    )


@_nb.njit(cache=True, fastmath=True)
def _box_area(mn0, mn1, mn2, mx0, mx1, mx2):
    """Surface area of an axis-aligned box; zero if it encloses nothing."""
    d0 = mx0 - mn0
    d1 = mx1 - mn1
    d2 = mx2 - mn2
    if d0 < 0.0 or d1 < 0.0 or d2 < 0.0:
        return 0.0
    return 2.0 * (d0 * d1 + d1 * d2 + d2 * d0)


@_nb.njit(cache=True, fastmath=True)
def closest_hit(
    rox, roy, roz,
    dx, dy, dz,
    t_min, t_limit,
    node_min, node_max, node_left, node_start, node_count, prim_index,
    n_spheres,
    centers, radii,
    tri_vertices,
    skip_prim,
    stack,
):
    """Nearest primitive a ray meets beyond ``t_min``.

    Both primitive kinds are intersected exactly -- a sphere analytically, a
    triangle by Moller-Trumbore -- so the tree changes only *which* primitives
    are tested, never the geometry of a hit.

    Parameters
    ----------
    rox, roy, roz : float
        Ray origin.
    dx, dy, dz : float
        Ray direction; must be unit length, since ``t`` is read as a distance.
    t_min : float
        Hits at or before this are ignored, which is how the transparency walk
        steps past the surface it just shaded.
    t_limit : float
        Search is abandoned beyond this. ``np.inf`` for an unbounded search.
    node_min, node_max, node_left, node_start, node_count, prim_index
        The tree, as returned by :func:`build_bvh`.
    n_spheres : int
        Where the index space changes kind: ``prim < n_spheres`` is a sphere,
        and above it triangle ``prim - n_spheres``.
    centers, radii : numpy.ndarray
        Sphere data, shapes ``(S, 3)`` and ``(S,)``.
    tri_vertices : numpy.ndarray
        Triangle corners, shape ``(T, 3, 3)``.
    skip_prim : int
        One primitive to ignore, or ``-1``. Used by the shadow query to skip the
        surface the shadow ray leaves from.
    stack : numpy.ndarray
        Scratch traversal stack of at least :data:`STACK_SIZE` int32 entries.
        Passed in rather than allocated so a per-pixel query does not allocate.

    Returns
    -------
    tuple
        ``(t, prim)`` -- distance and primitive index, or ``(inf, -1)`` when the
        ray meets nothing.
    """
    best_t = t_limit
    best_prim = -1
    if node_count.shape[0] == 0:
        return best_t, best_prim

    # A zero component gives an infinite slope, which the slab test handles: the
    # ray is parallel to that pair of planes and either always or never inside
    # them, and the min/max below resolves to the correct one. The bounds are
    # padded at build time so `0 * inf` -- the one case that would give a NaN --
    # cannot arise.
    inv_x = 1.0 / dx if dx != 0.0 else 1e300
    inv_y = 1.0 / dy if dy != 0.0 else 1e300
    inv_z = 1.0 / dz if dz != 0.0 else 1e300

    sp = 0
    stack[sp] = 0
    sp += 1

    while sp > 0:
        sp -= 1
        node = stack[sp]

        # ---- does the ray enter this box at all, and before the best hit? ----
        t0 = (node_min[node, 0] - rox) * inv_x
        t1 = (node_max[node, 0] - rox) * inv_x
        tnear = min(t0, t1)
        tfar = max(t0, t1)
        t0 = (node_min[node, 1] - roy) * inv_y
        t1 = (node_max[node, 1] - roy) * inv_y
        tnear = max(tnear, min(t0, t1))
        tfar = min(tfar, max(t0, t1))
        t0 = (node_min[node, 2] - roz) * inv_z
        t1 = (node_max[node, 2] - roz) * inv_z
        tnear = max(tnear, min(t0, t1))
        tfar = min(tfar, max(t0, t1))
        if tfar < tnear or tfar < t_min or tnear > best_t:
            continue

        left = node_left[node]
        if left >= 0:
            stack[sp] = left
            sp += 1
            stack[sp] = left + 1
            sp += 1
            continue

        start = node_start[node]
        for i in range(start, start + node_count[node]):
            p = prim_index[i]
            if p == skip_prim:
                continue

            if p < n_spheres:
                r = radii[p]
                if r <= 0.0:
                    continue
                ocx = rox - centers[p, 0]
                ocy = roy - centers[p, 1]
                ocz = roz - centers[p, 2]
                b = 2.0 * (ocx * dx + ocy * dy + ocz * dz)
                c = ocx * ocx + ocy * ocy + ocz * ocz - r * r
                disc = b * b - 4.0 * c
                if disc < 0.0:
                    continue
                sqrt_d = np.sqrt(disc)
                th = (-b - sqrt_d) * 0.5
                if th <= t_min:
                    th = (-b + sqrt_d) * 0.5
                    if th <= t_min:
                        continue
                if th < best_t:
                    best_t = th
                    best_prim = p
            else:
                ti = p - n_spheres
                t = _moller_trumbore(
                    rox, roy, roz, dx, dy, dz,
                    tri_vertices[ti, 0, 0], tri_vertices[ti, 0, 1], tri_vertices[ti, 0, 2],
                    tri_vertices[ti, 1, 0], tri_vertices[ti, 1, 1], tri_vertices[ti, 1, 2],
                    tri_vertices[ti, 2, 0], tri_vertices[ti, 2, 1], tri_vertices[ti, 2, 2],
                )
                if t > t_min and t < best_t:
                    best_t = t
                    best_prim = p

    return best_t, best_prim


@_nb.njit(fastmath=True, cache=True)
def _moller_trumbore(
    rox, roy, roz,
    dx, dy, dz,
    v0x, v0y, v0z,
    v1x, v1y, v1z,
    v2x, v2y, v2z,
):
    """Moller-Trumbore ray-triangle intersection; returns ``t``, or ``-1``."""
    e1x = v1x - v0x
    e1y = v1y - v0y
    e1z = v1z - v0z
    e2x = v2x - v0x
    e2y = v2y - v0y
    e2z = v2z - v0z

    pvecx = dy * e2z - dz * e2y
    pvecy = dz * e2x - dx * e2z
    pvecz = dx * e2y - dy * e2x

    det = e1x * pvecx + e1y * pvecy + e1z * pvecz
    if abs(det) < 1e-12:
        return -1.0
    inv_det = 1.0 / det

    tx = rox - v0x
    ty = roy - v0y
    tz = roz - v0z

    u = (tx * pvecx + ty * pvecy + tz * pvecz) * inv_det
    if u < 0.0 or u > 1.0:
        return -1.0

    qvecx = ty * e1z - tz * e1y
    qvecy = tz * e1x - tx * e1z
    qvecz = tx * e1y - ty * e1x

    v = (dx * qvecx + dy * qvecy + dz * qvecz) * inv_det
    if v < 0.0 or u + v > 1.0:
        return -1.0

    t = (e2x * qvecx + e2y * qvecy + e2z * qvecz) * inv_det
    if t < 1e-6:
        return -1.0
    return t


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
