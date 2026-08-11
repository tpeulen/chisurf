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
expressed the way NumPy is fast at -- a counting sort into a cell table, then
one ``(block, 27)`` add to reach every neighbouring cell of every query point at
once. No Python loop over points, and no compiler.

What it costs, measured against the tree it replaced
----------------------------------------------------
Pair sets are **identical** to ``cKDTree``'s at every size tested, and the
timings are on random points, interleaved A/B/A/B, best of five:

===========  =========  ==========  =========
points       pairs      this        cKDTree
===========  =========  ==========  =========
1,363        8,209      2.8 ms      1.3 ms
20,000       122,094    58 ms       25 ms
50,000       131,774    72 ms       68 ms
200,000      522,558    365 ms      287 ms
===========  =========  ==========  =========

Within a factor of two of compiled C, in NumPy. Three things got it there, and
each is worth keeping:

* **an indexed cell table, not a searched one.** The first version sorted the
  cell keys and found each cell with ``searchsorted``; a profile put **57 % of
  the query in those two binary searches**, because there are twenty-seven of
  them per query point. :func:`_cell_table` is a counting sort, so a cell's
  range is a direct index.
* **a padded grid**, one cell on every side, so all 27 neighbours exist and the
  per-offset bounds test disappears.
* **scalar key offsets**: with the grid padded, a neighbour's linear key is the
  point's own key plus a constant, so the whole stencil is one add rather than
  27 passes of cell arithmetic.

Two further ideas were tried and are *not* here, because they measured slower:
a float32 sieve before the exact test (123 ms against 117 at 20k -- the work is
memory-bound, so an extra pass over the candidates costs more than the narrower
gather saves), and pruning whole cells by their box distance (helped at 20k,
2.5x worse at 200k, where the ``(block, 27, 3)`` temporaries stop fitting).

What remains is inherent: a 3x3x3 stencil covers 27 r^3 where the sphere is
4.19 r^3, so about six candidates are examined per pair returned, and a grid
degenerates when the density varies far more than the query radius -- the
coarse-grained-bead-beside-an-all-atom-chain case. :func:`grid_occupancy`
reports the fullest cell, which is how that is seen rather than guessed at.
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


def _cell_table(keys: np.ndarray, cell_count: int):
    """Return ``(order, start)`` -- the points grouped by cell, CSR style.

    Parameters
    ----------
    keys : numpy.ndarray
        ``(m,)`` linear cell index per point.
    cell_count : int
        Number of cells in the grid.

    Returns
    -------
    tuple of numpy.ndarray
        ``order`` lists the point indices cell by cell; ``start`` has
        ``cell_count + 1`` entries, so cell *k*'s points are
        ``order[start[k]:start[k + 1]]``.

    Notes
    -----
    A counting sort, and the reason it is worth writing out: the obvious form
    is to sort the keys and find each cell with ``searchsorted``, which is what
    this module did first -- and a profile put **57 % of the query time** in
    those two binary searches. A cell's range is a *direct index* here, which
    is the difference between O(log m) per lookup and O(1), and there are
    twenty-seven lookups per query point.
    """
    counts = np.bincount(keys, minlength=cell_count)
    start = np.zeros(cell_count + 1, dtype=np.intp)
    np.cumsum(counts, out=start[1:])
    order = np.argsort(keys, kind="stable")
    return order, start


#: The 3x3x3 stencil, as offsets in cells.
_OFFSETS = np.array(
    [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)],
    dtype=np.intp,
)

#: Query points per block. Bounds the ``(block, 27)`` candidate bookkeeping at
#: a few megabytes, so a million-point query costs the same memory as a
#: hundred-thousand-point one and only more time.
_QUERY_BLOCK = 1 << 17


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

    Notes
    -----
    Three things make this fast enough to have replaced a compiled k-d tree,
    and each was measured rather than assumed:

    * the cell table is **indexed**, not searched (:func:`_cell_table`);
    * the grid is **padded** by one cell on every side, so every one of the 27
      neighbours exists and there is no bounds test at all;
    * a neighbour's linear key is therefore the point's own key plus a
      **scalar**, so the whole stencil is one ``(block, 27)`` add rather than
      27 passes of cell arithmetic.

    What remains is inherent to a grid: a 3x3x3 stencil covers 27 r^3 where the
    sphere is 4.19 r^3, so about six candidates are examined per pair returned.
    The distance test itself is under 2 % of the time.
    """
    a = np.ascontiguousarray(query, dtype=np.float64).reshape(-1, 3)
    b = np.ascontiguousarray(other, dtype=np.float64).reshape(-1, 3)
    empty = (np.zeros(0, dtype=np.intp), np.zeros(0, dtype=np.intp))
    if a.shape[0] == 0 or b.shape[0] == 0:
        return empty
    if not np.isfinite(radius) or radius <= 0.0:
        return empty

    origin = np.minimum(a.min(axis=0), b.min(axis=0))
    size = _cell_size(np.vstack((a, b)), float(radius))
    extent = np.maximum(
        np.maximum(a.max(axis=0), b.max(axis=0)) - origin, 1e-9
    )
    # One cell of padding on each side, and the cell index shifted by one to
    # match: a point's 27 neighbours are then always inside the grid, which is
    # what removes the per-offset bounds test.
    inner = np.ceil(extent / size).astype(np.intp) + 1
    shape = tuple((inner + 2).tolist())
    cell_count = int(np.prod(shape))
    # ``intp``, not ``int64``. On a 64-bit desktop they are the same type; in
    # WebAssembly ``intp`` is **32-bit**, and ``np.bincount`` accepts only
    # ``intp`` -- an int64 key array makes it raise "cannot cast ... according
    # to the rule 'safe'" from inside the cell table, which reaches the user as
    # a file that would not load. Only the browser finds this.
    strides = np.array([shape[1] * shape[2], shape[2], 1], dtype=np.intp)

    def _keys(points: np.ndarray) -> np.ndarray:
        cells = np.floor((points - origin) / size).astype(np.intp)
        np.clip(cells, 0, inner - 1, out=cells)
        return (cells + 1) @ strides

    order_b, start_b = _cell_table(_keys(b), cell_count)
    # The other points in cell order, so a candidate run is a *contiguous*
    # slice rather than a gather through a permutation.
    # float64 throughout, and that is a decision rather than an inherited
    # dtype. A float32 test misclassifies pairs within an epsilon of the cutoff
    # -- two of 522,558 at 200k points, against the k-d tree this replaced --
    # and a neighbour query whose answer depends on the precision of its own
    # arithmetic differs quietly from every reference. A float32 *sieve* with
    # an exact second pass was tried and is slower than the exact test alone
    # (123 ms against 117 at 20k): the work is memory-bound, so the extra pass
    # over the candidates costs more than the narrower gather saves.
    b_sorted = np.ascontiguousarray(b[order_b], dtype=np.float64)
    deltas = _OFFSETS @ strides

    r2 = float(radius) * float(radius)
    found_i: list[np.ndarray] = []
    found_j: list[np.ndarray] = []
    for begin in range(0, a.shape[0], _QUERY_BLOCK):
        stop_block = min(begin + _QUERY_BLOCK, a.shape[0])
        keys = _keys(a[begin:stop_block])[:, None] + deltas[None, :]
        first = start_b[keys]
        counts = (start_b[keys + 1] - first).reshape(-1)
        total = int(counts.sum())
        if total == 0:
            continue

        # Expand every (point, neighbour cell) run at once: repeat each run's
        # query row by its length, then walk the run with an arange offset.
        rows = np.repeat(
            np.repeat(np.arange(begin, stop_block), _OFFSETS.shape[0]), counts
        )
        within_run = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
        slots = np.repeat(first.reshape(-1), counts) + within_run

        delta = a[rows] - b_sorted[slots]
        d2 = np.einsum("ij,ij->i", delta, delta)
        keep = d2 < r2 if strict else d2 <= r2
        if not keep.any():
            continue
        found_i.append(rows[keep])
        # Back through the permutation only for the pairs that survived.
        found_j.append(order_b[slots[keep]])

    if not found_i:
        return empty
    if len(found_i) == 1:
        return found_i[0], found_j[0]
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
    out = np.empty((int(keep.sum()), 2), dtype=np.intp)
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
    inner = np.ceil(extent / size).astype(np.intp) + 1
    cells = np.clip(np.floor((pts - origin) / size).astype(np.intp), 0, inner - 1)
    strides = np.array([inner[1] * inner[2], inner[2], 1], dtype=np.intp)
    counts = np.bincount(cells @ strides, minlength=int(np.prod(inner)))
    return int(np.prod(inner)), int(counts.max())
