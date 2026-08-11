"""Radius pair queries on a uniform grid, in NumPy and nothing else.

Why this replaces ``scipy.spatial.cKDTree``
------------------------------------------
Every "what is near what" question in chimol routes through
:mod:`chimol.geometry.neighbors`, and that module was four calls into scipy's
compiled k-d tree. The tree is good and the reasoning that chose it was sound
at the time -- Pyodide ships scipy, so it looked free.

It is not free: **importing** it is a ~14 MB download before a page can draw a
molecule, and ``geometry/__init__`` imports it at module scope, so the browser
paid it to *import the viewer at all* -- for a query it might never make. The
instruction was to move that compute onto the GPU; this is the half that has to
exist first either way, because a GPU path needs a CPU twin to be checked
against and a fallback for small inputs, where a dispatch costs more than the
work.

The grid, and why it is not the cell lists that were deleted
------------------------------------------------------------
Those were **numba** kernels: a Python loop per point, fast only because it was
compiled, and 300-680x slower with the JIT off. This is the same data structure
expressed the way NumPy is fast at -- sort the points by cell once, then answer
all queries against all 27 neighbouring cells with `searchsorted`, one
vectorised pass per offset. No Python loop over points, and no compiler.

The one real weakness of a grid is inherited honestly: it degenerates when the
density varies far more than the query radius, because a cell then holds most of
the points. That is the coarse-grained-bead-beside-an-all-atom-chain case, and
it is bounded here by capping the number of cells rather than the number of
points per cell -- an occupancy the caller can measure with
:func:`grid_occupancy` if a scene ever gets slow.
"""
from __future__ import annotations

import numpy as np

__all__ = ["grid_occupancy", "pairs_within", "self_pairs_within_grid"]

#: The most cells a grid may have, whatever the radius asks for. A 1 A radius
#: over a virus capsid would otherwise ask for billions of cells and allocate
#: them; above this the cell size grows instead, which costs candidate pairs
#: rather than memory.
_MAX_CELLS = 1 << 22


def _cell_size(points: np.ndarray, radius: float) -> float:
    """Return the cell edge to use: the radius, or larger if that is too fine.

    Parameters
    ----------
    points : numpy.ndarray
        ``(n, 3)`` positions.
    radius : float
        The query radius.

    Returns
    -------
    float
    """
    span = np.maximum(points.max(axis=0) - points.min(axis=0), 1e-9)
    size = float(radius)
    # ``ceil(span / size) + 1`` cells per axis; grow the cell until the product
    # is under the cap. Doubling converges in a handful of steps and keeps the
    # cell an exact multiple of the radius, which keeps the 27-cell stencil
    # sufficient.
    for _ in range(64):
        counts = np.ceil(span / size) + 1.0
        if float(np.prod(counts)) <= _MAX_CELLS:
            return size
        size *= 2.0
    return size


def _binned(points: np.ndarray, origin: np.ndarray, size: float, shape):
    """Return ``(order, sorted_keys, cell_index)`` for *points*.

    Parameters
    ----------
    points : numpy.ndarray
        ``(n, 3)`` positions.
    origin : numpy.ndarray
        Grid origin, i.e. the minimum corner.
    size : float
        Cell edge.
    shape : tuple of int
        Cells per axis.

    Returns
    -------
    tuple
        The permutation that sorts the points by cell, the sorted cell keys,
        and each point's ``(n, 3)`` integer cell coordinates.
    """
    cells = np.floor((points - origin) / size).astype(np.int64)
    np.clip(cells, 0, np.asarray(shape, dtype=np.int64) - 1, out=cells)
    keys = np.ravel_multi_index((cells[:, 0], cells[:, 1], cells[:, 2]), shape)
    order = np.argsort(keys, kind="stable")
    return order, keys[order], cells


#: The 27 cell offsets of the stencil, as one array.
_OFFSETS = np.array(
    [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)],
    dtype=np.int64,
)


def pairs_within(
    query,
    other,
    radius: float,
    *,
    strict: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Every ``(query, other)`` pair within *radius*.

    Parameters
    ----------
    query : array_like
        ``(n, 3)`` positions to search from.
    other : array_like
        ``(m, 3)`` positions to search among.
    radius : float
        Cutoff.
    strict : bool, optional
        Compare ``<`` rather than ``<=``. The boundary conventions differ
        between callers -- ``count_within_radius`` is strict and
        ``within_distance_mask`` is inclusive -- and they are what the callers
        were calibrated against, so the choice is the caller's.

    Returns
    -------
    tuple of numpy.ndarray
        ``(i, j)`` index arrays, unordered. Pairs at zero distance are
        included, which is what a caller counting self-neighbours subtracts.
    """
    a = np.ascontiguousarray(query, dtype=np.float64).reshape(-1, 3)
    b = np.ascontiguousarray(other, dtype=np.float64).reshape(-1, 3)
    empty = (np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64))
    if a.shape[0] == 0 or b.shape[0] == 0:
        return empty
    if not np.isfinite(radius) or radius <= 0.0:
        return empty

    origin = np.minimum(a.min(axis=0), b.min(axis=0))
    size = _cell_size(np.vstack((a, b)), float(radius))
    extent = np.maximum(
        np.maximum(a.max(axis=0), b.max(axis=0)) - origin, 1e-9
    )
    shape = tuple((np.ceil(extent / size).astype(np.int64) + 1).tolist())

    order_b, keys_b, _ = _binned(b, origin, size, shape)
    # The other points in cell order, so a candidate range is a *contiguous*
    # slice rather than a gather through a permutation. Measured at a third of
    # the query time on 20k points: the fancy-index gather was the single
    # largest cost, because a grid inspects several times more candidates than
    # it returns pairs.
    b_sorted = np.ascontiguousarray(b[order_b], dtype=np.float32)
    a32 = np.ascontiguousarray(a, dtype=np.float32)
    cells_a = np.floor((a - origin) / size).astype(np.int64)
    np.clip(cells_a, 0, np.asarray(shape, dtype=np.int64) - 1, out=cells_a)

    r2 = np.float32(float(radius) * float(radius))
    found_i: list[np.ndarray] = []
    found_j: list[np.ndarray] = []
    for offset in _OFFSETS:
        neighbour = cells_a + offset
        inside = np.all(
            (neighbour >= 0) & (neighbour < np.asarray(shape, dtype=np.int64)), axis=1
        )
        if not inside.any():
            continue
        rows = np.flatnonzero(inside)
        keys = np.ravel_multi_index(
            (neighbour[rows, 0], neighbour[rows, 1], neighbour[rows, 2]), shape
        )
        # Where each query's neighbour cell sits in the sorted other-points:
        # one contiguous run per cell, so the candidates are a range each.
        start = np.searchsorted(keys_b, keys, side="left")
        stop = np.searchsorted(keys_b, keys, side="right")
        counts = stop - start
        total = int(counts.sum())
        if total == 0:
            continue
        # Expand the ranges without a Python loop: repeat each query row by its
        # candidate count, then walk each run with an arange offset.
        repeat_i = np.repeat(rows, counts)
        offsets_within = np.arange(total) - np.repeat(
            np.cumsum(counts) - counts, counts
        )
        slots = np.repeat(start, counts) + offsets_within

        delta = a32[repeat_i] - b_sorted[slots]
        d2 = np.einsum("ij,ij->i", delta, delta)
        keep = d2 < r2 if strict else d2 <= r2
        if not keep.any():
            continue
        found_i.append(repeat_i[keep])
        # Back through the permutation only for the pairs that survived.
        found_j.append(order_b[slots[keep]])

    if not found_i:
        return empty
    return np.concatenate(found_i), np.concatenate(found_j)


def self_pairs_within_grid(points, radius: float) -> np.ndarray:
    """Unordered pairs of *points* within *radius*, as ``(k, 2)`` with ``i < j``.

    Parameters
    ----------
    points : array_like
        ``(n, 3)`` positions.
    radius : float
        Cutoff, inclusive.

    Returns
    -------
    numpy.ndarray
        ``(k, 2)`` int64, ordered by ``i`` then ``j``.
    """
    first, second = pairs_within(points, points, radius)
    keep = first < second
    out = np.empty((int(keep.sum()), 2), dtype=np.int64)
    out[:, 0] = first[keep]
    out[:, 1] = second[keep]
    order = np.lexsort((out[:, 1], out[:, 0]))
    return out[order]


def grid_occupancy(points, radius: float) -> tuple[int, int]:
    """Return ``(cells, the fullest cell's count)`` for a would-be grid.

    Parameters
    ----------
    points : array_like
        ``(n, 3)`` positions.
    radius : float
        The query radius the grid would be built for.

    Returns
    -------
    tuple of int

    Notes
    -----
    Diagnostic. A grid degenerates when one cell holds most of the points, and
    that is invisible from the outside -- the query is merely slow. This is how
    to see it rather than guess.
    """
    pts = np.ascontiguousarray(points, dtype=np.float64).reshape(-1, 3)
    if pts.shape[0] == 0 or not np.isfinite(radius) or radius <= 0.0:
        return 0, 0
    origin = pts.min(axis=0)
    size = _cell_size(pts, float(radius))
    extent = np.maximum(pts.max(axis=0) - origin, 1e-9)
    shape = tuple((np.ceil(extent / size).astype(np.int64) + 1).tolist())
    _order, keys, _cells = _binned(pts, origin, size, shape)
    if not keys.size:
        return int(np.prod(shape)), 0
    counts = np.diff(np.flatnonzero(np.r_[True, keys[1:] != keys[:-1], True]))
    return int(np.prod(shape)), int(counts.max())
