"""Ambient occlusion for the mesh builders.

Two estimators live here, and they answer different questions:

* :func:`_estimate_ambient_occlusion` counts neighbours inside a radius. It is
  cheap and normal-agnostic, so it darkens *crowded* regions uniformly rather
  than *concave* ones — a bulge in the middle of a crowd comes out as dark as
  the pit beside it.
* :func:`occlusion_from_spheres` is real ambient occlusion: for each vertex it
  accumulates how much of the hemisphere above its normal is blocked by nearby
  atoms, so crevices, grooves and the undersides of loops darken and exposed
  convex surfaces stay bright. This is what gives the cartoon its depth in the
  interactive viewport, where nothing else casts a shadow.

Both are baked into vertex colours at build time rather than computed per frame,
so they cost nothing while the camera moves and cannot shimmer the way a
screen-space estimate does.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from scipy.spatial import cKDTree

from .neighbors import blocked_cross_pairs, count_within_radius


def _cosine_coverage_occlusion(
    points: np.ndarray,
    normals: np.ndarray,
    centers: np.ndarray,
    radii: np.ndarray,
    max_distance: float,
    strength: float,
) -> np.ndarray:
    """Hemispherical occlusion of ``points`` by a set of spheres.

    Each occluder contributes the fraction of the hemisphere it covers,
    ``1 - cos(alpha)`` with ``sin(alpha) = r / d``, weighted by the cosine
    between the surface normal and the direction to it. Contributions are
    combined as ``1 - exp(-strength * sum)`` rather than added, which keeps the
    result in [0, 1) and stops a dense neighbourhood from saturating to pure
    black the way a plain sum would.

    Parameters
    ----------
    points, normals : numpy.ndarray
        ``(n, 3)`` vertices and unit normals.
    centers : numpy.ndarray
        ``(m, 3)`` occluder centres.
    radii : numpy.ndarray
        ``(m,)`` occluder radii.
    max_distance : float
        Occluders further away than this are ignored.
    strength : float
        Scales the accumulated coverage before the exponential.

    Returns
    -------
    numpy.ndarray
        ``(n,)`` occlusion in ``[0, 1)``.
    """
    n = points.shape[0]
    total = np.zeros(n, dtype=np.float64)
    if n == 0 or centers.shape[0] == 0 or max_distance <= 0.0:
        return total

    # Per-vertex and independent: the pair enumeration the CPU route needs is an
    # artefact of NumPy's shape, not of the problem.
    from ..renderer.compute import occlusion_from_spheres as _occlusion_on_gpu  # noqa: PLC0415

    accelerated = _occlusion_on_gpu(
        points, normals, centers, radii, float(max_distance), float(strength)
    )
    if accelerated is not None:
        return accelerated

    d_max2 = max_distance * max_distance
    for start, stop, vi, ci in blocked_cross_pairs(points, centers, max_distance):
        delta = centers[ci] - points[start:stop][vi]
        d2 = np.einsum("ij,ij->i", delta, delta)
        radius = radii[ci]
        with np.errstate(invalid="ignore", divide="ignore"):
            d = np.sqrt(d2)
            cos_theta = np.einsum("ij,ij->i", delta, normals[start:stop][vi]) / d
            sin_a = radius / d
        # A vertex sitting inside an occluder is its own surface, not something
        # blocking it -- and `d2 > 1e-12` keeps a coincident pair out of the
        # division above.
        keep = (d2 < d_max2) & (d2 > 1.0e-12) & (d > radius) & (cos_theta > 0.0)
        coverage = 1.0 - np.sqrt(np.maximum(1.0 - sin_a * sin_a, 0.0))
        contribution = np.where(keep, cos_theta * coverage, 0.0)
        total[start:stop] += np.bincount(vi, weights=contribution, minlength=stop - start)

    return 1.0 - np.exp(-strength * total)


#: Ray samples are spaced one occluder reach apart, so a sphere near the ray is
#: within ``sqrt(1.25) * reach`` of some sample. Rounded up for float slack.
_RAY_SAMPLE_MARGIN = 1.15


def _ray_blockage(
    points: np.ndarray,
    normals: np.ndarray,
    centers: np.ndarray,
    radii: np.ndarray,
    direction: np.ndarray,
    max_distance: float,
    softness: float,
    strength: float,
) -> np.ndarray:
    """How much of the key light each vertex loses to the geometry.

    A ray is cast from the vertex toward the light and each nearby sphere is
    asked how close it comes to that ray. A sphere the ray passes straight
    through blocks fully; one it grazes blocks partly, which is what gives a
    soft edge rather than the hard stair-step of a shadow map at this scale.

    Occluders behind the vertex, or that the vertex sits inside, are skipped:
    the first are irrelevant and the second is the surface itself.

    Parameters
    ----------
    points, normals : numpy.ndarray
        ``(n, 3)`` vertices and unit normals.
    centers : numpy.ndarray
        ``(m, 3)`` occluder centres.
    radii : numpy.ndarray
        ``(m,)`` occluder radii.
    direction : numpy.ndarray
        Unit vector pointing **toward** the light.
    max_distance : float
        How far along the ray to look.
    softness : float
        Multiplies each occluder radius when deciding how near a graze counts.
    strength : float
        Scales the accumulated blockage before the exponential.

    Returns
    -------
    numpy.ndarray
        ``(n,)`` shadowing in ``[0, 1)``.

    Notes
    -----
    The cell list this replaces stepped along the ray in strides of
    ``max_distance`` and searched a 3×3×3 cell neighbourhood at each stride, and
    those neighbourhoods **overlap** — so an occluder sitting in a shared cell
    was accumulated two or three times and the shadow it cast was that much too
    deep. Sampling at the occluder reach and taking the unique
    ``(vertex, occluder)`` pairs both fixes that and shrinks the candidate set:
    a shadow ray only ever cares about spheres within a couple of Angstrom of
    it, not about everything within ``max_distance``.
    """
    n = points.shape[0]
    total = np.zeros(n, dtype=np.float64)
    m = centers.shape[0]
    if n == 0 or m == 0 or max_distance <= 0.0:
        return total

    reach = radii * softness
    reach_max = float(reach.max())
    if reach_max <= 0.0:
        return total

    # Per-vertex and independent, and the dedup rule the CPU route spends a
    # `np.unique` on is a single comparison in the shader.
    from ..renderer.compute import directional_occlusion as _shadow_on_gpu  # noqa: PLC0415

    accelerated = _shadow_on_gpu(
        points, normals, centers, radii, direction,
        float(max_distance), float(softness), float(strength),
    )
    if accelerated is not None:
        return accelerated

    # Only vertices facing the light can be shadowed; the diffuse term already
    # darkens the rest, and dropping them here shrinks every query below.
    facing = np.flatnonzero(normals @ direction > 0.0)
    if facing.size == 0:
        return total

    tree = cKDTree(centers)
    step = reach_max
    sample_count = int(np.ceil(max_distance / step)) + 1
    query_radius = reach_max * _RAY_SAMPLE_MARGIN

    seen: list[np.ndarray] = []
    origins = points[facing]
    for sample in range(sample_count):
        along = min(sample * step, max_distance)
        probes = origins + direction * along
        found = tree.query_ball_point(probes, query_radius, workers=-1)
        counts = np.fromiter((len(f) for f in found), dtype=np.int64, count=facing.size)
        if counts.sum() == 0:
            continue
        flat = np.concatenate([np.asarray(f, dtype=np.int64) for f in found if f])
        seen.append(np.stack((np.repeat(facing, counts), flat)))
    if not seen:
        return total

    candidates = np.unique(np.concatenate(seen, axis=1).T, axis=0)
    vi = candidates[:, 0]
    ci = candidates[:, 1]

    delta = centers[ci] - points[vi]
    along = delta @ direction
    perpendicular = delta - along[:, None] * direction
    perp2 = np.einsum("ij,ij->i", perpendicular, perpendicular)
    radius = radii[ci]
    span = reach[ci]
    d2 = np.einsum("ij,ij->i", delta, delta)
    keep = (along > 0.0) & (along < max_distance) & (perp2 < span * span) & (d2 > radius * radius)
    if not keep.any():
        return total
    blocked = 1.0 - np.sqrt(perp2[keep]) / span[keep]
    total += np.bincount(vi[keep], weights=blocked * blocked, minlength=n)

    return 1.0 - np.exp(-strength * total)


def occlusion_from_spheres(
    points: np.ndarray,
    normals: np.ndarray,
    centers: np.ndarray,
    radii: np.ndarray | float,
    *,
    max_distance: float = 12.0,
    strength: float = 1.0,
) -> np.ndarray | None:
    """Ambient occlusion of a mesh by the atoms around it.

    Unlike :func:`_estimate_ambient_occlusion`, this is normal-aware: a vertex is
    darkened by what lies in the hemisphere it faces, so concave geometry darkens
    and convex geometry does not. That is the difference between "this region is
    crowded" and "this point is in a pit", and it is what makes a cartoon read as
    a solid object in the interactive viewport.

    Parameters
    ----------
    points : numpy.ndarray
        ``(N, 3)`` vertex positions.
    normals : numpy.ndarray
        ``(N, 3)`` vertex normals; need not be unit length.
    centers : numpy.ndarray
        ``(M, 3)`` occluder centres, normally the atoms.
    radii : numpy.ndarray or float
        Occluder radii, either per-occluder or one value for all.
    max_distance : float, optional
        Occluders further away than this are ignored. Their solid angle already
        falls off as the inverse square, so this mainly bounds the work.
    strength : float, optional
        Scales the accumulated coverage before the exponential. Higher values
        deepen the shading without ever exceeding full occlusion.

    Returns
    -------
    numpy.ndarray or None
        ``(N,)`` occlusion in ``[0, 1)``, 0 being fully exposed. ``None`` when
        the inputs do not describe a mesh and a set of occluders.
    """
    pts = np.ascontiguousarray(points, dtype=np.float64)
    nrm = np.ascontiguousarray(normals, dtype=np.float64)
    ctr = np.ascontiguousarray(centers, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3 or pts.shape[0] == 0:
        return None
    if nrm.shape != pts.shape:
        return None
    if ctr.ndim != 2 or ctr.shape[1] != 3 or ctr.shape[0] == 0:
        return None

    lengths = np.linalg.norm(nrm, axis=1)
    lengths[lengths <= 0.0] = 1.0
    nrm = nrm / lengths[:, None]

    if np.isscalar(radii):
        rad = np.full(ctr.shape[0], float(radii), dtype=np.float64)
    else:
        rad = np.ascontiguousarray(radii, dtype=np.float64).reshape(-1)
        if rad.shape[0] != ctr.shape[0]:
            return None

    if not np.isfinite(max_distance) or max_distance <= 0.0:
        return None

    occ = _cosine_coverage_occlusion(
        pts, nrm, ctr, rad, float(max_distance), float(strength)
    )
    return np.clip(occ, 0.0, 1.0)



def directional_occlusion(
    points: np.ndarray,
    normals: np.ndarray,
    centers: np.ndarray,
    radii: np.ndarray | float,
    direction: np.ndarray,
    *,
    max_distance: float = 20.0,
    softness: float = 1.6,
    strength: float = 1.0,
) -> np.ndarray | None:
    """Shadowing of the key light, baked per vertex.

    Ambient occlusion says how enclosed a point is; this says whether anything
    stands between it and the light, which is a different and complementary cue.
    Together they give the interactive viewport something PyMOL's has no
    equivalent of at all -- PyMOL casts shadows only when raytracing.

    Like the ambient term this is computed once per rebuild and baked into the
    vertex colours, so it costs nothing per frame. The trade is that it is fixed
    to one light direction: moving the camera does not move the shadows, which is
    correct for a headlight and is what a molecular viewer wants anyway, since
    shadows that swim as you orbit are worse than none.

    Parameters
    ----------
    points, normals : numpy.ndarray
        ``(N, 3)`` vertices and their normals.
    centers : numpy.ndarray
        ``(M, 3)`` occluder centres.
    radii : numpy.ndarray or float
        Occluder radii.
    direction : numpy.ndarray
        Unit vector pointing **toward** the light.
    max_distance : float, optional
        How far along the ray to look, in the same units as ``points``.
    softness : float, optional
        Multiplies each occluder's radius when deciding how near a graze counts,
        so values above 1 blur the shadow edge.
    strength : float, optional
        Scales the accumulated blockage before the exponential.

    Returns
    -------
    numpy.ndarray or None
        ``(N,)`` shadowing in ``[0, 1)``, 0 being fully lit.
    """
    pts = np.ascontiguousarray(points, dtype=np.float64)
    nrm = np.ascontiguousarray(normals, dtype=np.float64)
    ctr = np.ascontiguousarray(centers, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3 or pts.shape[0] == 0:
        return None
    if nrm.shape != pts.shape or ctr.ndim != 2 or ctr.shape[0] == 0:
        return None

    lengths = np.linalg.norm(nrm, axis=1)
    lengths[lengths <= 0.0] = 1.0
    nrm = nrm / lengths[:, None]

    light = np.asarray(direction, dtype=np.float64).reshape(3)
    norm = float(np.linalg.norm(light))
    if norm <= 1e-12:
        return None
    light = light / norm

    if np.isscalar(radii):
        rad = np.full(ctr.shape[0], float(radii), dtype=np.float64)
    else:
        rad = np.ascontiguousarray(radii, dtype=np.float64).reshape(-1)
        if rad.shape[0] != ctr.shape[0]:
            return None

    shadow = _ray_blockage(
        pts, nrm, ctr, rad, light,
        float(max_distance), float(softness), float(strength),
    )
    return np.clip(shadow, 0.0, 1.0)


def _estimate_ambient_occlusion(
    points: np.ndarray,
    radius: float = 4.0,
    max_neighbors: int = 32,
) -> Optional[np.ndarray]:
    """Crowding at each point, as a fraction of ``max_neighbors``.

    Parameters
    ----------
    points : numpy.ndarray
        ``(n, 3)`` positions.
    radius : float, optional
        Neighbours strictly inside this radius are counted.
    max_neighbors : int, optional
        The count that reads as fully occluded; larger counts clamp to it.

    Returns
    -------
    numpy.ndarray or None
        ``(n,)`` occlusion in ``[0, 1]``, or ``None`` for non-point input.

    Notes
    -----
    IMP's ``NearestNeighbor3D.get_in_ball`` was evaluated and rejected here: it
    silently drops interior neighbours — it is an approximate search — and
    ``GridClosePairsFinder`` materialises every close pair, which blows up on
    the tens of thousands of vertices a marching-cubes surface produces.
    """
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[0] == 0:
        return None

    n = pts.shape[0]
    if n == 1:
        return np.zeros(1, dtype=float)

    r = float(radius)
    if not np.isfinite(r) or r <= 0.0:
        return None
    if max_neighbors <= 0:
        return np.zeros(n, dtype=float)

    counts = count_within_radius(pts, r)
    return np.clip(counts / float(max_neighbors), 0.0, 1.0)

__all__ = [
    "_estimate_ambient_occlusion",
    "occlusion_from_spheres",
    "directional_occlusion",
]

