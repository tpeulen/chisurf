from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np

from .grid_pairs import pairs_within

# Isosurface extraction is chimol's own marching cubes (see marching_cubes.py),
# not scikit-image's -- the tables are small and the alternative is a large
# dependency for one function.
from .marching_cubes import marching_cubes as _marching_cubes

_HAVE_SKIMAGE = True  # retained name: isosurface extraction is always available

#: How many voxel contributions to hold in one array while splatting a field.
#: Chunking is on the *atom* axis, so this bounds memory without changing what
#: is computed.
_SPLAT_BUDGET = 4_000_000



def _splat_field(points, sigmas, grid, origin, spacing, *, reach_of, contribution):
    """Add a per-point radial field into a voxel grid, point box by point box.

    Parameters
    ----------
    points : numpy.ndarray
        ``(n, 3)`` field centres, in the same units as ``origin`` and ``spacing``.
    sigmas : numpy.ndarray
        ``(n,)`` per-point width; its meaning is the caller's, and it is what the
        points are grouped by.
    grid : numpy.ndarray
        ``(nx, ny, nz)`` accumulator, written in place.
    origin : numpy.ndarray
        World position of voxel ``(0, 0, 0)``.
    spacing : float
        Voxel edge length.
    reach_of : callable
        ``sigma -> half-width`` of the box a point writes into.
    contribution : callable
        ``(dist2, sigma) -> value``; ``dist2`` is an array of squared distances
        from the point to each voxel centre in its box.

    Notes
    -----
    Points are grouped by ``sigma`` because that is what fixes the box size, and
    a structure has a handful of distinct radii however many atoms it has — so
    the grouping is nearly free and turns a per-point Python loop into one array
    operation per group. Within a group the box is a fixed stencil offset from
    each point's own lower corner, with a mask for the voxels that fall outside
    the point's true box or off the grid; that keeps it bit-identical to the
    per-point bounds rather than approximately equal to them.
    """
    nx, ny, nz = grid.shape
    shape = np.array([nx, ny, nz], dtype=np.int64)
    usable = np.isfinite(sigmas) & (sigmas > 0.0)
    if not usable.any():
        return
    flat = grid.reshape(-1)

    values, inverse = np.unique(sigmas[usable], return_inverse=True)
    where = np.flatnonzero(usable)
    for group, sigma in enumerate(values):
        reach = float(reach_of(float(sigma)))
        if reach <= 0.0:
            continue
        member = where[inverse == group]
        lower = np.floor((points[member] - origin - reach) / spacing).astype(np.int64)
        upper = np.ceil((points[member] - origin + reach) / spacing).astype(np.int64)
        span = np.maximum((upper - lower + 1).max(axis=0), 0)
        if span.min() <= 0:
            continue
        per_point = int(span.prod())
        step = max(1, _SPLAT_BUDGET // max(per_point, 1))
        for begin in range(0, member.size, step):
            block = slice(begin, begin + step)
            _splat_block(
                points[member][block], lower[block], upper[block], shape,
                origin, spacing, span, float(sigma), contribution, flat,
            )


def _splat_block(centres, lower, upper, shape, origin, spacing, span, sigma,
                 contribution, flat):
    """Splat one block of equally-sized boxes into a flattened grid.

    Parameters
    ----------
    centres : numpy.ndarray
        ``(b, 3)`` field centres.
    lower, upper : numpy.ndarray
        ``(b, 3)`` inclusive voxel-index bounds of each box, unclamped.
    shape : numpy.ndarray
        ``(3,)`` grid dimensions.
    origin : numpy.ndarray
        World position of voxel ``(0, 0, 0)``.
    spacing : float
        Voxel edge length.
    span : numpy.ndarray
        ``(3,)`` stencil size, the largest box in the group.
    sigma : float
        Passed through to ``contribution``.
    contribution : callable
        ``(dist2, sigma) -> value``.
    flat : numpy.ndarray
        The grid, reshaped to one dimension and added to in place.
    """
    axes = []
    for axis in range(3):
        offsets = np.arange(span[axis], dtype=np.int64)
        index = lower[:, axis][:, None] + offsets[None, :]
        inside = (index <= upper[:, axis][:, None]) & (index >= 0) & (index < shape[axis])
        delta = origin[axis] + np.clip(index, 0, shape[axis] - 1) * spacing
        delta = delta - centres[:, axis][:, None]
        axes.append((index, inside, delta * delta))

    (ix, vx, dx2), (iy, vy, dy2), (iz, vz, dz2) = axes
    dist2 = dx2[:, :, None, None] + dy2[:, None, :, None] + dz2[:, None, None, :]
    keep = vx[:, :, None, None] & vy[:, None, :, None] & vz[:, None, None, :]
    value = contribution(dist2, sigma)
    if value is None:
        return
    keep &= np.isfinite(value)
    if not keep.any():
        return
    target = (
        np.clip(ix, 0, shape[0] - 1)[:, :, None, None] * (shape[1] * shape[2])
        + np.clip(iy, 0, shape[1] - 1)[:, None, :, None] * shape[2]
        + np.clip(iz, 0, shape[2] - 1)[:, None, None, :]
    )
    target = np.broadcast_to(target, keep.shape)
    flat += np.bincount(
        target[keep], weights=value[keep], minlength=flat.size
    ).astype(flat.dtype, copy=False)


def _distance_to_spheres(points, radii, grid, origin, spacing):
    """Signed distance from every voxel centre to the nearest sphere surface.

    Parameters
    ----------
    points : numpy.ndarray
        ``(n, 3)`` sphere centres.
    radii : numpy.ndarray
        ``(n,)`` sphere radii.
    grid : numpy.ndarray
        ``(nx, ny, nz)`` output, written in place.
    origin : numpy.ndarray
        World position of voxel ``(0, 0, 0)``.
    spacing : float
        Voxel edge length.

    Notes
    -----
    This is an *additively weighted* nearest-neighbour query — ``min(d_i - r_i)``,
    not ``min(d_i)`` — so the nearest sphere is not necessarily the answer when
    the radii differ. It is still exact, and without a per-voxel Python loop: ask
    for the ``k`` nearest spheres at once, and note that every sphere not in that
    set is at least ``d_k`` away and so cannot score below ``d_k - r_max``. Any
    voxel whose best candidate does not already beat that bound is re-queried
    with a larger ``k``; on real structures almost none are, because vdW radii
    span less than an Angstrom.

    What it replaces was O(voxels × atoms) with no spatial index at all: 8.2×10⁹
    distance evaluations, 35 s, for one 96³ grid on a 11k-atom structure.
    """
    nx, ny, nz = grid.shape
    horizon = max(_DISTANCE_HORIZON, 4.0 * spacing)

    # One dispatch per voxel, each an independent ring scan -- the same
    # arithmetic as below with the search order fixed by the grid instead of by
    # a k-d tree. `None` means no adapter or too small to be worth it.
    from ..renderer.compute import distance_to_spheres  # noqa: PLC0415

    accelerated = distance_to_spheres(
        points, radii, grid.shape, origin, spacing, horizon
    )
    if accelerated is not None:
        grid[...] = accelerated
        return

    radius_max = float(radii.max())
    count = points.shape[0]

    ax = origin[0] + np.arange(nx, dtype=np.float64) * spacing
    ay = origin[1] + np.arange(ny, dtype=np.float64) * spacing
    az = origin[2] + np.arange(nz, dtype=np.float64) * spacing

    # In slabs, so a large grid of voxel coordinates is never held three times
    # over -- but in slabs of several planes, not one. The tree query is
    # threaded, and handing it a few thousand points at a time spends more on
    # starting the threads than on the search: one query over a whole 96³ grid
    # measured 80 ms where the same work plane by plane took 390 ms.
    per_slab = max(1, _SPLAT_BUDGET // max(ny * nz, 1))
    for begin in range(0, nx, per_slab):
        end = min(begin + per_slab, nx)
        block = np.stack(
            np.meshgrid(ax[begin:end], ay, az, indexing="ij"), axis=-1
        ).reshape(-1, 3)
        grid[begin:end] = np.minimum(
            _nearest_sphere_surface(points, radii, radius_max, horizon, block),
            horizon,
        ).reshape(end - begin, ny, nz)


#: Distances beyond this are reported as exactly this, by both routes.
#:
#: The grid is only ever read near the isosurface -- at a level of one probe
#: radius -- so what a voxel 60 A from the nearest atom reports cannot reach the
#: mesh: a cell whose corners are all beyond the horizon does not straddle the
#: level. Clamping is not a shortcut for the CPU route, which is exact either
#: way; it exists because the GPU route's ring scan otherwise needs fifteen
#: rings for such a voxel, which measured *slower than the CPU route*. Applying
#: it on both sides is what keeps them equal.
#:
#: 8 Å with a 6 Å cell was the best of the eight combinations measured, on
#: both a 1.4k-atom protein at 128³ (39.6× the CPU route) and a synthetic
#: 11k-atom cloud at 96³ (33.8×). Doubling it to 16 costs a third of that and
#: buys nothing: no level a probe radius can reach comes near either bound.
_DISTANCE_HORIZON = 8.0

#: How many spheres to consider per voxel before checking whether that was
#: enough. Eight covers every voxel of a protein at vdW radii; the escalation
#: below exists for inputs that mix radii more widely, such as a bead model
#: beside an all-atom chain.
_NEAREST_SPHERES = 8


def _nearest_sphere_surface(points, radii, radius_max, horizon, queries):
    """``min(|q - p_i| - r_i)`` over all spheres, for each query point.

    Parameters
    ----------
    points : numpy.ndarray
        ``(n, 3)`` sphere centres.
    radii : numpy.ndarray
        ``(n,)`` sphere radii.
    radius_max : float
        ``radii.max()``, passed in so it is not recomputed per slab.
    horizon : float
        Distances beyond this are not distinguished -- see
        :data:`_DISTANCE_HORIZON`. It is what bounds the search radius, and
        therefore what makes this a local query rather than a global one.
    queries : numpy.ndarray
        ``(q, 3)`` positions to evaluate.

    Returns
    -------
    numpy.ndarray
        ``(q,)`` signed distance to the nearest sphere *surface*.

    Notes
    -----
    A radius query on the shared grid, not a k-nearest search. The two are not
    interchangeable in general, but they are here because the caller clamps at
    ``horizon``: any voxel with no sphere centre within ``horizon + radius_max``
    is beyond the clamp whatever the true nearest is, so reporting the clamp for
    it is exact rather than approximate. That is also why the k-nearest version
    this replaces needed its escalation loop -- a fixed *k* cannot know it has
    found the nearest surface when the radii differ -- and the radius form has
    no such doubt.
    """
    q = np.ascontiguousarray(queries, dtype=np.float64).reshape(-1, 3)
    best = np.full(q.shape[0], float(horizon), dtype=np.float64)
    if q.shape[0] == 0 or points.shape[0] == 0:
        return best

    reach = float(horizon) + float(radius_max)
    vi, si = pairs_within(q, points, reach)
    if vi.size == 0:
        return best

    delta = q[vi] - points[si]
    scored = np.sqrt(np.einsum("ij,ij->i", delta, delta)) - radii[si]
    # One minimum per query row. `np.minimum.at` is the unbuffered ufunc path
    # and runs an order of magnitude slower on the millions of pairs a grid
    # produces; sorting and taking the first of each run is the fast form.
    order = np.lexsort((scored, vi))
    rows = vi[order]
    firsts = np.flatnonzero(np.r_[True, rows[1:] != rows[:-1]])
    best[rows[firsts]] = np.minimum(best[rows[firsts]], scored[order][firsts])
    return best


def _distance_transform_edt(forbidden: np.ndarray) -> np.ndarray:
    """Euclidean distance, in voxels, to the nearest zero voxel.

    Parameters
    ----------
    forbidden : numpy.ndarray
        Volume whose zeros are the seeds.

    Returns
    -------
    numpy.ndarray
        Distance to the nearest zero, in voxel units.

    Notes
    -----
    Separable and exact either way: scipy's is the same Felzenszwalb transform,
    and the GPU route is the same three passes with one invocation per line.
    """
    mask = np.ascontiguousarray(forbidden).astype(np.uint8)
    from ..renderer.compute import distance_transform_edt as _edt_on_gpu  # noqa: PLC0415

    accelerated = _edt_on_gpu(mask)
    if accelerated is not None:
        return accelerated
    return _edt_numpy(mask)


def _edt_1d(values: np.ndarray) -> np.ndarray:
    """Squared distance transform along the last axis, Felzenszwalb's way.

    Parameters
    ----------
    values : numpy.ndarray
        ``(rows, n)`` float64: the squared distance accumulated so far, or
        ``inf`` where nothing has been found yet.

    Returns
    -------
    numpy.ndarray
        The lower envelope of the parabolas ``(x - i)^2 + values[i]``.

    Notes
    -----
    The parabola-envelope algorithm, which is what scipy's
    ``distance_transform_edt`` runs and what makes the transform *exact* and
    linear rather than an approximation by repeated dilation. Vectorised across
    rows; the scan along the axis stays a loop, because each step depends on the
    intersection computed by the last.
    """
    rows, n = values.shape
    out = np.empty_like(values)
    # `v` holds the index of the k-th parabola in the envelope, `z` its domain
    # boundaries. One set per row, advanced together.
    v = np.zeros((rows, n), dtype=np.int64)
    z = np.empty((rows, n + 1), dtype=np.float64)
    z[:, 0] = -np.inf
    z[:, 1] = np.inf
    k = np.zeros(rows, dtype=np.int64)
    index = np.arange(rows)

    for q in range(1, n):
        fq = values[:, q]
        while True:
            vk = v[index, k]
            # The intersection of parabola `q` with the current top one.
            with np.errstate(invalid="ignore"):
                s = ((fq + q * q) - (values[index, vk] + vk * vk)) / (2.0 * (q - vk))
            pop = (k > 0) & (s <= z[index, k])
            if not pop.any():
                break
            k = np.where(pop, k - 1, k)
        vk = v[index, k]
        with np.errstate(invalid="ignore"):
            s = ((fq + q * q) - (values[index, vk] + vk * vk)) / (2.0 * (q - vk))
        # A row whose f(q) is infinite contributes no parabola at all.
        finite = np.isfinite(fq)
        k = np.where(finite, k + 1, k)
        v[index, k] = np.where(finite, q, v[index, k])
        z[index, k] = np.where(finite, s, z[index, k])
        z[index, k + 1] = np.inf

    k = np.zeros(rows, dtype=np.int64)
    for q in range(n):
        while True:
            ahead = z[index, k + 1] < q
            if not ahead.any():
                break
            k = np.where(ahead, k + 1, k)
        vk = v[index, k]
        out[:, q] = (q - vk) ** 2 + values[index, vk]
    return out


def _edt_numpy(mask: np.ndarray) -> np.ndarray:
    """Exact Euclidean distance to the nearest zero of *mask*, in voxels.

    Parameters
    ----------
    mask : numpy.ndarray
        Non-zero where the distance is measured *from*.

    Returns
    -------
    numpy.ndarray
        float64, the same shape.

    Notes
    -----
    In the tree rather than from scipy, and the reason is the browser: importing
    scipy is a ~14 MB download before a page can draw anything, for a fallback
    that a page with a GPU never takes. Separable, so it is :func:`_edt_1d`
    applied along each axis in turn -- which is exactly what makes the result
    exact and not a chamfer approximation.
    """
    volume = np.ascontiguousarray(mask)
    result = np.where(volume != 0, np.inf, 0.0).astype(np.float64)
    for axis in range(volume.ndim):
        moved = np.moveaxis(result, axis, -1)
        shape = moved.shape
        transformed = _edt_1d(moved.reshape(-1, shape[-1]))
        result = np.moveaxis(transformed.reshape(shape), -1, axis)
    return np.sqrt(result)



def _gaussian_falloff(dist2, sigma):
    """``exp(-d^2 / 2 sigma^2)`` — the density a Gaussian blob puts at a voxel.

    Parameters
    ----------
    dist2 : numpy.ndarray
        Squared distances from the blob centre.
    sigma : float
        Gaussian width.

    Returns
    -------
    numpy.ndarray
        Density, same shape as ``dist2``.
    """
    return np.exp(-dist2 / (2.0 * sigma * sigma))


def _wyvill_falloff(dist2, radius):
    """Wyvill's cubic soft-object falloff, zero at and beyond ``radius``.

    Parameters
    ----------
    dist2 : numpy.ndarray
        Squared distances from the blob centre.
    radius : float
        Radius at which the field reaches zero.

    Returns
    -------
    numpy.ndarray
        Field value, same shape as ``dist2``, zero outside ``radius``.

    Notes
    -----
    Unlike a Gaussian this has compact support, which is what makes a metaball
    merge with its neighbours over a bounded distance instead of everywhere.
    """
    r2 = radius * radius
    u = dist2 / r2
    u2 = u * u
    value = (9.0 - 22.0 * u + 17.0 * u2 - 4.0 * u2 * u) / 9.0
    return np.where(dist2 < r2, value, 0.0)


def _build_density_grid(
    pts: np.ndarray,
    sigmas: np.ndarray,
    *,
    field_function: str = "gaussian",
    grid_spacing: float = 1.0,
    padding: float = 2.5,
    cutoff_factor: float = 2.5,
    max_dim: int = 96,
) -> Optional[Tuple[np.ndarray, np.ndarray, float]]:
    pts_arr = np.asarray(pts, dtype=float)
    if pts_arr.ndim != 2 or pts_arr.shape[0] < 4:
        return None
    sig_arr = np.asarray(sigmas, dtype=float)
    if sig_arr.shape[0] != pts_arr.shape[0]:
        return None

    spacing = max(float(grid_spacing), 0.2)
    max_sigma = float(np.max(sig_arr))
    
    field_function = field_function.lower()
    if field_function == "wyvill":
        pad = max(float(padding), max_sigma + spacing * 2.0)
    else:
        pad = max(float(padding), max_sigma * cutoff_factor + spacing * 2.0)

    max_dim = max(int(max_dim), 16)

    mins = pts_arr.min(axis=0) - pad
    maxs = pts_arr.max(axis=0) + pad
    extent = maxs - mins
    dims_float = np.ceil(extent / spacing).astype(int) + 1
    max_axis = int(np.max(dims_float))
    if max_axis > max_dim:
        scale = max_axis / float(max_dim)
        spacing *= scale
        dims_float = np.ceil(extent / spacing).astype(int) + 1

    dims = np.maximum(dims_float, 3)
    grid = np.zeros(tuple(int(x) for x in dims), dtype=np.float32)

    sig_arr = np.maximum(sig_arr, spacing * 0.1)
    origin = mins.astype(np.float32)

    try:
        from ..renderer import compute
        gpu_grid = compute.density_grid(
            pts_arr,
            sig_arr,
            tuple(int(x) for x in dims),
            origin,
            float(spacing),
            field_function=field_function,
            cutoff_factor=cutoff_factor,
        )
    except Exception:
        gpu_grid = None

    if gpu_grid is not None:
        grid = np.asarray(gpu_grid, dtype=np.float32)
    else:
        grid = np.zeros(tuple(int(x) for x in dims), dtype=np.float32)
        if field_function == "wyvill":
            _splat_field(
                pts_arr.astype(np.float32).astype(np.float64),
                sig_arr.astype(np.float32).astype(np.float64),
                grid,
                origin.astype(np.float64),
                float(spacing),
                reach_of=lambda s: s,
                contribution=_wyvill_falloff,
            )
        else:
            sig_arr_clipped = np.clip(sig_arr, spacing * 0.25, spacing * 5.0)
            factor = float(cutoff_factor)
            _splat_field(
                pts_arr.astype(np.float32).astype(np.float64),
                sig_arr_clipped.astype(np.float32).astype(np.float64),
                grid,
                origin.astype(np.float64),
                float(spacing),
                reach_of=lambda s: factor * s,
                contribution=_gaussian_falloff,
            )

    if not np.isfinite(grid.max()) or grid.max() <= 0.0:
        return None

    return grid, origin, float(spacing)


def _build_gaussian_density_grid(
    pts: np.ndarray,
    sigmas: np.ndarray,
    grid_spacing: float = 1.0,
    padding: float = 2.5,
    cutoff_factor: float = 2.5,
    max_dim: int = 96,
) -> Optional[Tuple[np.ndarray, np.ndarray, float]]:
    return _build_density_grid(
        pts,
        sigmas,
        field_function="gaussian",
        grid_spacing=grid_spacing,
        padding=padding,
        cutoff_factor=cutoff_factor,
        max_dim=max_dim,
    )


def _generate_surface_mesh_from_density(
    pts: np.ndarray,
    sigmas: np.ndarray,
    *,
    field_function: str = "gaussian",
    grid_spacing: float = 1.0,
    padding: float = 2.5,
    cutoff_factor: float = 2.5,
    iso_value: float = 0.2,
    max_dim: int = 96,
) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    if not _HAVE_SKIMAGE:
        return None

    density_data = _build_density_grid(
        pts,
        sigmas,
        field_function=field_function,
        grid_spacing=grid_spacing,
        padding=padding,
        cutoff_factor=cutoff_factor,
        max_dim=max_dim,
    )
    if density_data is None:
        return None

    grid, origin, spacing = density_data
    level = float(iso_value)
    if not np.isfinite(level) or level <= 0.0:
        level = 0.2 * float(grid.max())
    level = min(level, float(grid.max()) * 0.9)
    if level <= 0.0:
        return None

    verts, faces, norms = _marching_cubes(grid, level, (spacing, spacing, spacing))
    if verts.shape[0] == 0:
        return None

    verts = np.asarray(verts, dtype=np.float32)
    verts += origin
    faces = np.asarray(faces, dtype=np.int32)
    # Marching cubes already returns the **outward** face normal here: the
    # field is a density, high inside, so the mesher's normal points out of
    # the matter. Negating it (which this did, under a comment claiming to
    # make it outward) turned every normal inward. Nothing caught it because
    # the `surface` builder replaces these normals with density-gradient ones
    # wholesale; the moment the metaball began using them directly its
    # Fresnel term saturated -- `1 - dot(n, view)` is ~2 for an inward normal
    # -- and the surface could not be made transparent at any alpha.
    # Measured on 148L: 0% of normals faced outward before, 94% after.
    norms = np.asarray(norms, dtype=np.float32)
    faces = faces[:, [0, 2, 1]]
    return verts, faces, norms


def _generate_surface_mesh_from_gaussians(
    pts: np.ndarray,
    sigmas: np.ndarray,
    *,
    grid_spacing: float = 1.0,
    padding: float = 2.5,
    cutoff_factor: float = 2.5,
    iso_value: float = 0.2,
    max_dim: int = 96,
) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    return _generate_surface_mesh_from_density(
        pts,
        sigmas,
        field_function="gaussian",
        grid_spacing=grid_spacing,
        padding=padding,
        cutoff_factor=cutoff_factor,
        iso_value=iso_value,
        max_dim=max_dim,
    )


def _binary_dilate_6(mask: np.ndarray, iterations: int) -> np.ndarray:
    """6-connected 3-D binary dilation (NumPy-only).

    Matches ``scipy.ndimage.binary_dilation`` with its default (face-connected)
    structuring element, but without the scipy dependency: each pass ORs the mask
    with its ±1 shift along every axis.
    """
    out = np.ascontiguousarray(mask, dtype=bool)
    for _ in range(max(int(iterations), 0)):
        d = out.copy()
        d[1:, :, :] |= out[:-1, :, :]
        d[:-1, :, :] |= out[1:, :, :]
        d[:, 1:, :] |= out[:, :-1, :]
        d[:, :-1, :] |= out[:, 1:, :]
        d[:, :, 1:] |= out[:, :, :-1]
        d[:, :, :-1] |= out[:, :, 1:]
        out = d
    return out


def _gaussian_blur_3d(grid: np.ndarray, sigma: float) -> np.ndarray:
    """Separable 3-D Gaussian blur (NumPy-only).

    Replaces ``scipy.ndimage.gaussian_filter`` for the point-cloud surface: a
    normalised 1-D Gaussian is convolved along each axis in turn (reflect
    padding), which is exact and cheap for the small sigmas used here.
    """
    sigma = float(sigma)
    if sigma <= 0.0:
        return grid
    radius = max(1, int(math.ceil(3.0 * sigma)))
    x = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-(x * x) / (2.0 * sigma * sigma))
    kernel /= kernel.sum()
    out = np.asarray(grid, dtype=np.float64)
    for axis in range(out.ndim):
        pad_width = [(0, 0)] * out.ndim
        pad_width[axis] = (radius, radius)
        padded = np.pad(out, pad_width, mode="reflect")
        acc = np.zeros_like(out)
        n = out.shape[axis]
        for i, w in enumerate(kernel):
            sl = [slice(None)] * out.ndim
            sl[axis] = slice(i, i + n)
            acc += w * padded[tuple(sl)]
        out = acc
    return out


def _generate_surface_mesh_from_points(
    pts: np.ndarray,
    *,
    grid_spacing: float = 1.0,
    padding: float = 1.5,
    smoothing_sigma: float = 0.75,
    dilation_iterations: int = 1,
    max_dim: int = 96,
) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Generate a surface mesh around occupied point-cloud voxels.

    Parameters
    ----------
    pts : numpy.ndarray
        Point coordinates with shape ``(N, 3)``.
    grid_spacing : float, optional
        Target voxel spacing in the same coordinate units as ``pts``.
    padding : float, optional
        Empty border around the point cloud.
    smoothing_sigma : float, optional
        Gaussian smoothing sigma in voxel units. Set to ``0`` to disable
        smoothing.
    dilation_iterations : int, optional
        Number of binary dilation passes before smoothing.
    max_dim : int, optional
        Maximum grid dimension. The actual spacing is increased if needed.

    Returns
    -------
    tuple of numpy.ndarray or None
        ``(vertices, faces, normals)`` if marching cubes succeeds, otherwise
        ``None``.
    """
    if not _HAVE_SKIMAGE:
        return None

    points = np.asarray(pts, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] < 4:
        return None
    finite_mask = np.isfinite(points).all(axis=1)
    points = points[finite_mask]
    if points.shape[0] < 4:
        return None

    spacing = max(float(grid_spacing), 1e-3)
    pad = max(float(padding), spacing)
    max_grid_dim = max(int(max_dim), 8)

    xyz_min = points.min(axis=0) - pad
    xyz_max = points.max(axis=0) + pad
    extent = np.maximum(xyz_max - xyz_min, spacing)
    shape = np.ceil(extent / spacing).astype(int) + 1

    largest = int(shape.max())
    if largest > max_grid_dim:
        spacing *= largest / float(max_grid_dim)
        shape = np.ceil(extent / spacing).astype(int) + 1

    shape = np.maximum(shape, 4)
    grid = np.zeros(tuple(int(v) for v in shape), dtype=np.float32)
    indices = np.rint((points - xyz_min) / spacing).astype(int)
    for axis in range(3):
        indices[:, axis] = np.clip(indices[:, axis], 0, shape[axis] - 1)
    grid[indices[:, 0], indices[:, 1], indices[:, 2]] = 1.0

    if dilation_iterations > 0:
        grid = _binary_dilate_6(grid > 0.0, int(dilation_iterations)).astype(np.float32)

    if smoothing_sigma > 0.0:
        grid = _gaussian_blur_3d(grid, float(smoothing_sigma)).astype(np.float32)

    level = 0.5
    grid_max = float(grid.max())
    if grid_max <= 0.0:
        return None
    if level >= grid_max:
        level = grid_max * 0.5

    verts, faces, norms = _marching_cubes(grid, level, (spacing, spacing, spacing))
    if verts.shape[0] == 0:
        return None

    verts = np.asarray(verts, dtype=np.float32)
    verts += xyz_min
    faces = np.asarray(faces, dtype=np.int32)
    norms = -np.asarray(norms, dtype=np.float32)
    faces = faces[:, [0, 2, 1]]
    return verts, faces, norms


def _generate_surface_mesh_edt(
    pts: np.ndarray,
    radii: np.ndarray,
    *,
    method: str = "sas",
    probe_radius: float = 1.4,
    grid_spacing: float = 0.8,
    padding: float = 3.0,
    max_dim: int = 96,
) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Generate a SAS or SES surface mesh using Euclidean Distance Transform (EDT).

    Parameters
    ----------
    pts : np.ndarray
        Coordinates of the atoms, shape (N, 3).
    radii : np.ndarray
        Radii of the atoms, shape (N,).
    method : str, optional
        Either "sas" (Solvent Accessible Surface) or "ses" (Solvent Excluded Surface).
        Default is "sas".
    probe_radius : float, optional
        Radius of the rolling solvent probe. Default is 1.4.
    grid_spacing : float, optional
        Target grid spacing/resolution in Angstroms. Default is 0.8.
    padding : float, optional
        Padding around the bounding box of coordinates in Angstroms. Default is 3.0.
    max_dim : int, optional
        Maximum dimension of the grid to prevent excessive memory/CPU usage.
        Default is 96.

    Returns
    -------
    Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]
        A tuple of (vertices, faces, normals) or None if the calculation failed.
    """
    if not _HAVE_SKIMAGE:
        return None

    method = method.lower()

    pts_arr = np.asarray(pts, dtype=float)
    if pts_arr.ndim != 2 or pts_arr.shape[0] == 0:
        return None
    radii_arr = np.asarray(radii, dtype=float)
    if radii_arr.shape[0] != pts_arr.shape[0]:
        return None

    spacing = max(float(grid_spacing), 0.1)
    max_radius = float(np.max(radii_arr))
    pad = max(float(padding), max_radius + probe_radius + spacing * 2.0)
    max_dim = max(int(max_dim), 16)

    mins = pts_arr.min(axis=0) - pad
    maxs = pts_arr.max(axis=0) + pad
    extent = maxs - mins
    dims_float = np.ceil(extent / spacing).astype(int) + 1
    max_axis = int(np.max(dims_float))
    if max_axis > max_dim:
        scale = max_axis / float(max_dim)
        spacing *= scale
        dims_float = np.ceil(extent / spacing).astype(int) + 1

    if method not in ("sas", "ses"):
        return None

    dims = tuple(int(x) for x in np.maximum(dims_float, 3))
    origin = mins.astype(np.float32)
    points = pts_arr.astype(np.float32).astype(np.float64)
    radii64 = radii_arr.astype(np.float32).astype(np.float64)

    # The whole pipeline -- distance grid, threshold, distance transform,
    # isosurface -- runs on the device with the grid never coming back. Each of
    # those already ran there; what did not was the *grid*, which was copied out
    # and in again between every pair, twice over at 8 MB. See `GpuVolume`.
    resident, level = _resident_field(
        points, radii64, dims, origin, spacing, method, probe_radius
    )
    if resident is not None:
        verts, faces, norms = _marching_cubes(
            None, level, (spacing, spacing, spacing), volume=resident
        )
    else:
        grid = np.zeros(dims, dtype=np.float32)
        _distance_to_spheres(
            points, radii64, grid, origin.astype(np.float64), float(spacing)
        )
        if method == "sas":
            # For SAS: we run on -grid (higher inside) at level -probe_radius.
            grid_to_mesh = -grid
            level = -float(probe_radius)
        else:
            # For SES: B_forbidden = (D < r_p), 1 inside the forbidden region;
            # the distance to the nearest 0 is then in physical units.
            forbidden = (grid < float(probe_radius)).astype(np.uint8)
            grid_to_mesh = _distance_transform_edt(forbidden).astype(np.float32) \
                * float(spacing)
            level = float(probe_radius)
        if level <= grid_to_mesh.min() or level >= grid_to_mesh.max():
            return None
        verts, faces, norms = _marching_cubes(
            grid_to_mesh, level, (spacing, spacing, spacing)
        )
    if verts.shape[0] == 0:
        return None

    verts = np.asarray(verts, dtype=np.float32)
    verts += origin
    faces = np.asarray(faces, dtype=np.int32)
    # Negate normals to point outward
    norms = -np.asarray(norms, dtype=np.float32)
    # Swap winding order to CCW
    faces = faces[:, [0, 2, 1]]
    return verts, faces, norms



def _resident_field(points, radii, dims, origin, spacing, method, probe_radius):
    """Build the field the isosurface is taken from, entirely on the device.

    Parameters
    ----------
    points : numpy.ndarray
        ``(n, 3)`` sphere centres.
    radii : numpy.ndarray
        ``(n,)`` sphere radii.
    dims : tuple of int
        Voxel counts.
    origin : numpy.ndarray
        World position of voxel ``(0, 0, 0)``.
    spacing : float
        Voxel edge length.
    method : str
        ``"sas"`` or ``"ses"``.
    probe_radius : float
        Solvent probe radius.

    Returns
    -------
    tuple
        ``(volume, level)``, or ``(None, 0.0)`` when the device route is
        unavailable — in which case the caller runs the same chain in NumPy.

    Notes
    -----
    The early "does the level even cross this grid" check the NumPy path makes is
    not repeated here, because answering it needs the volume's min and max and
    that is a copy back for one comparison. Marching cubes finds no crossings in
    that case and the caller returns ``None`` just the same.
    """
    from ..renderer import compute  # noqa: PLC0415

    horizon = max(_DISTANCE_HORIZON, 4.0 * spacing)
    field = compute.distance_to_spheres(
        points, radii, dims, origin.astype(np.float64), float(spacing), horizon,
        resident=True,
    )
    if field is None:
        return None, 0.0

    if method == "sas":
        # Higher inside, so the surface sits at minus the probe radius.
        return compute.scale_volume(field, -1.0), -float(probe_radius)

    # SES: seed the transform where the probe cannot reach, and measure out of
    # it. The seed is produced in the form the transform wants -- zero at the
    # seeds, a stand-in for infinity elsewhere -- so no mask ever exists.
    # Note the direction. `forbidden = distance < probe` is where the probe
    # cannot reach, and the transform measures *out of the allowed region* --
    # so the seeds are the voxels the probe can reach and the forbidden ones
    # start at infinity. Getting this backwards does not fail, it grows the
    # surface: 46,558 vertices where there should be 42,562.
    seed = compute.threshold_volume(
        field, float(probe_radius), compute._EDT_BIG, 0.0
    )
    squared = compute.distance_transform_edt(seed, resident=True)
    if squared is None:
        return None, 0.0
    return compute.root_scale_volume(squared, float(spacing)), float(probe_radius)


def _get_surface_atom_mask(
    pts: np.ndarray,
    *,
    radius: float = 5.0,
    max_neighbors: int = 20,
) -> np.ndarray:
    """Return a boolean mask selecting surface-exposed atoms.

    An atom is considered *buried* (not surface) when it has more than
    ``max_neighbors`` other atoms within ``radius`` Angstroms.  This is a
    fast O(N log N) heuristic that avoids a full SASA calculation while
    still removing the vast majority of interior atoms from the density
    field, which dramatically speeds up metaball rendering for large
    structures.

    Parameters
    ----------
    pts : (N, 3) ndarray
        Atom coordinates.
    radius : float
        Search radius for neighbor counting (Angstroms).
    max_neighbors : int
        Atoms with more neighbors than this threshold are classified as
        buried and excluded from the returned mask.

    Returns
    -------
    mask : (N,) ndarray of bool
        ``True`` for surface-exposed atoms.
    """
    arr = np.asarray(pts, dtype=float)
    if arr.ndim != 2 or arr.shape[0] == 0:
        return np.zeros(0, dtype=bool)
    if arr.shape[0] <= max_neighbors:
        return np.ones(arr.shape[0], dtype=bool)

    from .neighbors import count_within_radius

    counts = count_within_radius(arr, float(radius))
    return np.asarray(counts, dtype=int) <= int(max_neighbors)


__all__ = [
    "_build_gaussian_density_grid",
    "_generate_surface_mesh_from_gaussians",
    "_generate_surface_mesh_from_density",
    "_generate_surface_mesh_edt",
    "_get_surface_atom_mask",
]
