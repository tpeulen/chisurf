"""Radius neighbour queries — the one spatial primitive chimol builds on.

Every "what is near what" question in the renderer routes through this module:
ambient occlusion counts neighbours, bond inference enumerates close pairs,
surface colouring gathers atoms around a mesh vertex, and distance selections
mask coordinates against a target set. They were four hand-written uniform-grid
cell lists in four files; they are now four calls to :mod:`scipy.spatial`'s
compiled k-d tree.

Why a grid, and not scipy
-------------------------
These were numba cell lists, then ``scipy.spatial.cKDTree``, and are now a
vectorised uniform grid — :mod:`chimol.geometry.grid_pairs`. Each move was for a
reason and the last one is the browser: scipy *runs* in Pyodide, but importing
it is a ~14 MB download, ``geometry/__init__`` imports this module at module
scope, and the page therefore paid for scipy in order to *import the viewer* —
before any query was made. The instruction was to move this compute to the GPU,
and a CPU twin is what a GPU kernel is checked against, so it had to exist
first.

The grid is not the numba cell list returning. Those were Python loops made fast
by a compiler that does not exist in a browser (a no-op ``njit`` shim runs
300–680× slower). This is the same structure expressed as sorting and
``searchsorted``, which is what NumPy is fast at, with no loop over points.

Boundary conventions are preserved from the kernels they replace and differ
between queries — :func:`count_within_radius` is strict, :func:`within_distance_mask`
is inclusive. That is not tidy, but it is what the callers were calibrated
against, and ``nextafter`` makes strictness exact rather than approximate.
"""

from __future__ import annotations

import numpy as np

from .grid_pairs import pairs_within, self_pairs_within_grid


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
    first, _second = pairs_within(pts, pts, float(radius), strict=True)
    counts = np.bincount(first, minlength=n)[:n].astype(np.int64)
    # Minus one: the query point is inside its own radius.
    return counts - 1


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
    # Any target within the cutoff answers the question; the *nearest* one is
    # more than was asked, and finding it costs a second structure.
    first, _second = pairs_within(pts, tgt, float(dist))
    mask = np.zeros(n, dtype=bool)
    mask[first] = True
    return mask


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
    return pairs_within(pts, oth, float(radius))


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
    reduces to one number per vertex. **So the block size is estimated from a
    sample, not from the exact counts.** Counting exactly used to be free -- the
    k-d tree could return lengths without building the pairs -- and when the
    tree went, the same code started materialising every pair *in order to
    decide how to avoid materialising every pair*, then querying each block a
    second time. That is the opposite of what this function is for, and it is
    invisible until the input is large enough to run out of memory.

    A few hundred query points give the mean pairs per point to well within the
    factor of two that choosing a block size needs.
    """
    pts = _as_points(points)
    oth = _as_points(others)
    n = pts.shape[0]
    if n == 0 or oth.shape[0] == 0 or not np.isfinite(radius) or radius <= 0.0:
        return

    budget = max(1, int(budget))
    sample_size = min(n, 512)
    step = max(1, n // sample_size)
    sample = pts[::step][:sample_size]
    sampled_i, _sampled_j = pairs_within(sample, oth, float(radius))
    if sampled_i.size == 0:
        # The sample found nothing, which does not prove the rest is empty --
        # it proves only that the density is low, so one generous block is the
        # right guess rather than an early return.
        chunk = n
    else:
        per_point = max(sampled_i.size / float(len(sample)), 1e-9)
        chunk = int(min(max(budget / per_point, 1.0), float(n)))

    for start in range(0, n, chunk):
        stop = min(start + chunk, n)
        block_i, block_j = pairs_within(pts[start:stop], oth, float(radius))
        if block_i.size == 0:
            continue
        yield int(start), int(stop), block_i, block_j


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
    return self_pairs_within_grid(pts, radius)


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
    ``nearest`` is filled **only where ``wsum`` is zero** and is ``-1``
    elsewhere, because that is the only place any caller reads it — and finding
    the globally nearest atom for every vertex cost more than the whole gather
    once the gather moved to the GPU. Where it is filled it is the true global
    nearest: the cell list this replaces searched only the query cell and its 26
    neighbours and returned ``-1`` when all of them were empty, which the caller
    then used as an index, painting such vertices with the **last** atom's
    colour.
    """
    v = _as_points(verts)
    a = _as_points(atoms)
    nv = v.shape[0]
    col = np.ascontiguousarray(atom_colors, dtype=np.float64).reshape(-1, 4)
    sig = np.ascontiguousarray(sigmas, dtype=np.float64).reshape(-1)

    out_col = np.zeros((nv, 4), dtype=np.float64)
    grad = np.zeros((nv, 3), dtype=np.float64)
    wsum = np.zeros(nv, dtype=np.float64)
    if nv == 0 or a.shape[0] == 0 or not np.isfinite(cutoff) or cutoff <= 0.0:
        return out_col, wsum, grad, np.full(nv, -1, dtype=np.int64)

    # The gather is per-vertex and independent, which is the one shape a GPU is
    # unambiguously better at.
    from ..renderer.compute import shade_from_atoms as _shade_on_gpu  # noqa: PLC0415

    accelerated = _shade_on_gpu(v, a, col, sig, float(cutoff))
    if accelerated is not None:
        out_col, wsum, grad = accelerated
        return out_col, wsum, grad, _nearest_where_starved(v, a, wsum)

    vi, ai = pairs_within(v, a, float(cutoff), strict=True)
    if vi.size == 0:
        return out_col, wsum, grad, _nearest_where_starved(v, a, wsum)

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
    return out_col, wsum, grad, _nearest_where_starved(v, a, wsum)


def _nearest_where_starved(verts, atoms, wsum) -> np.ndarray:
    """Closest atom to each vertex that no atom reached, ``-1`` for the rest.

    Parameters
    ----------
    verts : numpy.ndarray
        ``(n, 3)`` mesh vertices.
    atoms : numpy.ndarray
        ``(m, 3)`` atom positions.
    wsum : numpy.ndarray
        ``(n,)`` accumulated Gaussian weight per vertex.

    Returns
    -------
    numpy.ndarray
        ``(n,)`` int64 atom indices.

    Notes
    -----
    Restricting the query to the starved rows is not a micro-optimisation: on a
    surface where every vertex has atoms inside the cutoff — the normal case —
    it does no work at all, where querying every vertex cost more than the
    weighted sum itself once that moved to the GPU.
    """
    nearest = np.full(verts.shape[0], -1, dtype=np.int64)
    starved = np.flatnonzero(wsum <= 0.0)
    if starved.size and len(atoms):
        # Brute force over the starved rows only. There are none on an ordinary
        # surface -- every vertex has atoms inside the cutoff -- and where there
        # are any it is a handful, so a spatial structure costs more than the
        # distances do.
        delta = np.asarray(verts)[starved][:, None, :] - np.asarray(atoms)[None, :, :]
        nearest[starved] = np.argmin(
            np.einsum("ijk,ijk->ij", delta, delta), axis=1
        ).astype(np.int64)
    return nearest


__all__ = [
    "blocked_cross_pairs",
    "count_within_radius",
    "cross_pairs_within",
    "self_pairs_within",
    "shade_from_atoms",
    "within_distance_mask",
]
