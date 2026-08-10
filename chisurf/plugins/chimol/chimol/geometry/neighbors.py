"""Radius neighbour queries — the one spatial primitive chimol builds on.

Every "what is near what" question in the renderer routes through this module:
ambient occlusion counts neighbours, bond inference enumerates close pairs,
surface colouring gathers atoms around a mesh vertex, and distance selections
mask coordinates against a target set. They were four hand-written uniform-grid
cell lists in four files; they are now four calls to :mod:`scipy.spatial`'s
compiled k-d tree.

Why not the cell lists
----------------------
They were numba kernels, and numba does not exist in Pyodide — so each one was a
wall between chimol and the browser. The cheap way out is dead: a no-op ``njit``
shim (exactly ``NUMBA_DISABLE_JIT=1``) runs 300–680× slower, and no
whole-program Python→WASM compiler closes that, because it cannot see through a
numpy buffer. ``cKDTree`` is compiled, ships in Pyodide, and lands within a small
factor of the numba cell list — nothing for work done once per scene rebuild.

The k-d tree is also *better* than what it replaces for non-uniform input. A
cell list sized to the query radius degenerates when density varies (one cell
holding most of the points), which is exactly what a coarse-grained bead model
next to an all-atom chain looks like.

Boundary conventions are preserved from the kernels they replace and differ
between queries — :func:`count_within_radius` is strict, :func:`within_distance_mask`
is inclusive. That is not tidy, but it is what the callers were calibrated
against, and ``nextafter`` makes strictness exact rather than approximate.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

#: Pass to every ``cKDTree`` query that accepts it. The tree releases the GIL,
#: so this is a real speedup on the vertex counts a marching-cubes surface
#: produces.
_WORKERS = -1


def _as_points(values) -> np.ndarray:
    """Return ``values`` as a contiguous ``(n, 3)`` float array.

    Parameters
    ----------
    values : array_like
        Anything convertible to coordinates.

    Returns
    -------
    numpy.ndarray
        ``(n, 3)`` float64, empty when the input is not point-shaped.
    """
    arr = np.ascontiguousarray(values, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 3:
        return np.zeros((0, 3), dtype=np.float64)
    return arr


def count_within_radius(points, radius) -> np.ndarray:
    """Return the number of *other* points strictly within ``radius`` of each.

    Parameters
    ----------
    points : array_like
        ``(n, 3)`` positions.
    radius : float
        Query radius; a point at exactly this distance does **not** count.

    Returns
    -------
    numpy.ndarray
        ``(n,)`` int64 counts, excluding the point itself.
    """
    pts = _as_points(points)
    n = pts.shape[0]
    if n == 0 or not np.isfinite(radius) or radius <= 0.0:
        return np.zeros(n, dtype=np.int64)
    # The cell lists this replaces tested `d2 < r2`. The largest float below
    # `radius` turns the tree's inclusive query into that exact test, rather
    # than an approximation of it that differs on grid-aligned input -- which
    # a marching-cubes vertex set is.
    strict = float(np.nextafter(float(radius), 0.0))
    tree = cKDTree(pts)
    counts = tree.query_ball_point(pts, strict, return_length=True, workers=_WORKERS)
    return np.asarray(counts, dtype=np.int64) - 1


def within_distance_mask(coords, targets, dist) -> np.ndarray:
    """Mask of ``coords`` lying within ``dist`` of any point in ``targets``.

    Parameters
    ----------
    coords : array_like
        ``(n, 3)`` positions to test.
    targets : array_like
        ``(m, 3)`` positions to measure against.
    dist : float
        Cutoff, inclusive.

    Returns
    -------
    numpy.ndarray
        ``(n,)`` bool.
    """
    pts = _as_points(coords)
    tgt = _as_points(targets)
    n = pts.shape[0]
    if n == 0 or tgt.shape[0] == 0 or not np.isfinite(dist) or dist <= 0.0:
        return np.zeros(n, dtype=bool)
    # One nearest-target distance per coordinate answers the question directly;
    # enumerating the pairs would build a list only to throw it away.
    nearest, _ = cKDTree(tgt).query(pts, k=1, workers=_WORKERS)
    return np.asarray(nearest) <= float(dist)


def cross_pairs_within(points, others, radius) -> tuple[np.ndarray, np.ndarray]:
    """Enumerate every ``(point, other)`` pair no further apart than ``radius``.

    Parameters
    ----------
    points : array_like
        ``(n, 3)`` positions.
    others : array_like
        ``(m, 3)`` positions.
    radius : float
        Cutoff, inclusive.

    Returns
    -------
    tuple of numpy.ndarray
        ``(i, j)`` index arrays into ``points`` and ``others``. Pairs at zero
        distance are included — a sparse-matrix output type would drop them as
        structural zeros, which is why this uses the record-array form.
    """
    pts = _as_points(points)
    oth = _as_points(others)
    empty = (np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64))
    if pts.shape[0] == 0 or oth.shape[0] == 0:
        return empty
    if not np.isfinite(radius) or radius <= 0.0:
        return empty
    pairs = cKDTree(pts).sparse_distance_matrix(
        cKDTree(oth), float(radius), output_type="ndarray"
    )
    return pairs["i"].astype(np.int64), pairs["j"].astype(np.int64)


def blocked_cross_pairs(points, others, radius, *, budget: int = 4_000_000):
    """Yield ``(start, stop, i, j)`` pair blocks so the pair array stays bounded.

    Parameters
    ----------
    points : array_like
        ``(n, 3)`` query positions.
    others : array_like
        ``(m, 3)`` positions to pair against.
    radius : float
        Cutoff, inclusive.
    budget : int, optional
        Soft ceiling on the number of pairs held at once.

    Yields
    ------
    tuple
        ``(start, stop, i, j)`` — the half-open range of ``points`` this block
        covers, and index arrays into ``points`` and ``others``.

    Notes
    -----
    A 12 Å occlusion radius over a 40k-vertex mesh in an all-atom structure is
    roughly 2.4×10⁷ pairs; materialising them all costs gigabytes for work that
    reduces to one number per vertex. The neighbour counts are queried first —
    cheap, and parallel — so the block sizes follow the actual density rather
    than a guess about it.
    """
    pts = _as_points(points)
    oth = _as_points(others)
    n = pts.shape[0]
    if n == 0 or oth.shape[0] == 0 or not np.isfinite(radius) or radius <= 0.0:
        return
    tree = cKDTree(oth)
    counts = np.asarray(
        tree.query_ball_point(pts, float(radius), return_length=True, workers=_WORKERS),
        dtype=np.int64,
    )
    cumulative = np.cumsum(counts)
    total = int(cumulative[-1])
    if total == 0:
        return
    block_count = max(1, -(-total // max(1, int(budget))))
    targets = np.arange(1, block_count) * max(1, int(budget))
    splits = np.searchsorted(cumulative, targets) + 1
    bounds = np.unique(np.clip(np.concatenate(([0], splits, [n])), 0, n))
    for start, stop in zip(bounds[:-1], bounds[1:]):
        if counts[start:stop].sum() == 0:
            continue
        pairs = cKDTree(pts[start:stop]).sparse_distance_matrix(
            tree, float(radius), output_type="ndarray"
        )
        yield int(start), int(stop), pairs["i"].astype(np.int64), pairs["j"].astype(np.int64)


def self_pairs_within(points, radius) -> np.ndarray:
    """Enumerate every unordered pair of ``points`` no further apart than ``radius``.

    Parameters
    ----------
    points : array_like
        ``(n, 3)`` positions.
    radius : float
        Cutoff, inclusive.

    Returns
    -------
    numpy.ndarray
        ``(k, 2)`` int64 index pairs with ``i < j``, ordered by ``i`` then ``j``.
    """
    pts = _as_points(points)
    if pts.shape[0] < 2 or not np.isfinite(radius) or radius <= 0.0:
        return np.zeros((0, 2), dtype=np.int64)
    first, second = cross_pairs_within(pts, pts, radius)
    keep = first < second
    out = np.empty((int(keep.sum()), 2), dtype=np.int64)
    out[:, 0] = first[keep]
    out[:, 1] = second[keep]
    order = np.lexsort((out[:, 1], out[:, 0]))
    return out[order]


def shade_from_atoms(verts, atoms, atom_colors, sigmas, cutoff):
    """Gaussian-weighted colour and gradient normal at each vertex from atoms.

    Parameters
    ----------
    verts : array_like
        ``(n, 3)`` mesh vertices.
    atoms : array_like
        ``(m, 3)`` atom positions.
    atom_colors : array_like
        ``(m, 4)`` RGBA per atom.
    sigmas : array_like
        ``(m,)`` Gaussian width per atom.
    cutoff : float
        Atoms beyond this contribute nothing.

    Returns
    -------
    tuple
        ``(colors, wsum, grad, nearest)`` — the unnormalised Gaussian-weighted
        RGBA sum, the weight sum, the density gradient, and the index of the
        closest atom. Callers normalise ``colors`` by ``wsum`` and derive the
        shading normal as ``-grad / |grad|``; ``nearest`` is what they fall back
        to where ``wsum`` is zero.

    Notes
    -----
    ``nearest`` is now the *globally* closest atom. The cell list this replaces
    searched only the query cell and its 26 neighbours and returned ``-1`` when
    all of them were empty — and the caller indexes ``atom_colors`` with it, so
    a vertex further than one cell from every atom was painted with the colour
    of the **last** atom in the structure rather than the nearest one.
    """
    v = _as_points(verts)
    a = _as_points(atoms)
    nv = v.shape[0]
    col = np.ascontiguousarray(atom_colors, dtype=np.float64).reshape(-1, 4)
    sig = np.ascontiguousarray(sigmas, dtype=np.float64).reshape(-1)

    out_col = np.zeros((nv, 4), dtype=np.float64)
    grad = np.zeros((nv, 3), dtype=np.float64)
    wsum = np.zeros(nv, dtype=np.float64)
    nearest = np.full(nv, -1, dtype=np.int64)
    if nv == 0 or a.shape[0] == 0 or not np.isfinite(cutoff) or cutoff <= 0.0:
        return out_col, wsum, grad, nearest

    atom_tree = cKDTree(a)
    _, nearest = atom_tree.query(v, k=1, workers=_WORKERS)
    nearest = np.asarray(nearest, dtype=np.int64)

    strict = float(np.nextafter(float(cutoff), 0.0))
    pairs = cKDTree(v).sparse_distance_matrix(
        atom_tree, strict, output_type="ndarray"
    )
    vi = pairs["i"]
    ai = pairs["j"]
    if vi.size == 0:
        return out_col, wsum, grad, nearest

    delta = v[vi] - a[ai]
    d2 = np.einsum("ij,ij->i", delta, delta)
    s2 = sig[ai] * sig[ai]
    weight = np.exp(-d2 / (2.0 * s2))

    # Many pairs share a vertex, so this is a scatter-*add*: fancy-index
    # assignment would keep only the last pair per vertex. `np.bincount` is the
    # fast form of that -- `np.add.at` is the unbuffered ufunc path and runs an
    # order of magnitude slower on the millions of pairs a surface produces.
    def _accumulate(values: np.ndarray) -> np.ndarray:
        return np.bincount(vi, weights=values, minlength=nv)[:nv]

    wsum = _accumulate(weight)
    weighted_colors = weight[:, None] * col[ai]
    weighted_delta = (weight / s2)[:, None] * delta
    for channel in range(4):
        out_col[:, channel] = _accumulate(weighted_colors[:, channel])
    for axis in range(3):
        grad[:, axis] = _accumulate(weighted_delta[:, axis])
    return out_col, wsum, grad, nearest


__all__ = [
    "blocked_cross_pairs",
    "count_within_radius",
    "cross_pairs_within",
    "self_pairs_within",
    "shade_from_atoms",
    "within_distance_mask",
]
