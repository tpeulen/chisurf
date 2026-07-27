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

import math

import numpy as np

try:  # Optional acceleration via numba
    import numba as nb  # type: ignore
    _HAVE_NUMBA = True
except Exception:  # pragma: no cover - run-time availability
    nb = None  # type: ignore
    _HAVE_NUMBA = False


#: Whether it is safe to write numba's on-disk cache from this module. See the
#: same constant in ``cartoon.py`` for what goes wrong when it is not: this file
#: is loaded by path as well, and a cache entry keyed to a name nothing can
#: import breaks the *next ordinary run*, not the one that wrote it.
_NB_CACHE = bool(__package__)


if _HAVE_NUMBA and nb is not None:

    @nb.jit(nopython=True, nogil=True, cache=_NB_CACHE)  # type: ignore[misc]
    def _estimate_ambient_occlusion_nb(
        pts: np.ndarray,
        radius: float,
        max_neighbors: int,
    ) -> np.ndarray:
        """Brute-force O(n^2) reference occlusion count (exact).

        Retained as the correctness reference and as a fallback; production uses
        the O(n) cell-list variant below.
        """
        n = pts.shape[0]
        occ = np.zeros(n, dtype=np.float64)
        r2 = radius * radius
        if n <= 1 or r2 <= 0.0:
            return occ

        for i in range(n):
            count = 0
            x0 = pts[i, 0]
            y0 = pts[i, 1]
            z0 = pts[i, 2]
            for j in range(n):
                if i == j:
                    continue
                dx = pts[j, 0] - x0
                dy = pts[j, 1] - y0
                dz = pts[j, 2] - z0
                if dx * dx + dy * dy + dz * dz < r2:
                    count += 1
                    if max_neighbors > 0 and count >= max_neighbors:
                        break

            if max_neighbors > 0:
                if count > max_neighbors:
                    count = max_neighbors
                occ[i] = float(count) / float(max_neighbors)

        return occ

    @nb.jit(nopython=True, nogil=True, cache=_NB_CACHE)  # type: ignore[misc]
    def _estimate_ambient_occlusion_grid_nb(
        pts: np.ndarray,
        radius: float,
        max_neighbors: int,
    ) -> np.ndarray:
        """O(n) occlusion count via a uniform cell list (cell size = radius).

        Exact — every point within ``radius`` falls in the query point's cell or
        one of the 26 adjacent cells — but linear in the number of points for the
        near-uniform density of a marching-cubes surface, versus the O(n^2)
        double loop that dominated metaball/surface builds. Bit-identical to
        :func:`_estimate_ambient_occlusion_nb`.
        """
        n = pts.shape[0]
        occ = np.zeros(n, dtype=np.float64)
        r2 = radius * radius
        if n <= 1 or r2 <= 0.0 or max_neighbors <= 0:
            return occ

        minx = miny = minz = 1.0e30
        maxx = maxy = maxz = -1.0e30
        for i in range(n):
            x = pts[i, 0]
            y = pts[i, 1]
            z = pts[i, 2]
            if x < minx:
                minx = x
            if x > maxx:
                maxx = x
            if y < miny:
                miny = y
            if y > maxy:
                maxy = y
            if z < minz:
                minz = z
            if z > maxz:
                maxz = z

        inv = 1.0 / radius
        nx = int((maxx - minx) * inv) + 1
        ny = int((maxy - miny) * inv) + 1
        nz = int((maxz - minz) * inv) + 1
        ncells = nx * ny * nz

        # Linked-list buckets: head[cell] -> point, nxt[point] -> next point.
        head = np.full(ncells, -1, dtype=np.int64)
        nxt = np.empty(n, dtype=np.int64)
        cix = np.empty(n, dtype=np.int64)
        ciy = np.empty(n, dtype=np.int64)
        ciz = np.empty(n, dtype=np.int64)
        for i in range(n):
            ix = int((pts[i, 0] - minx) * inv)
            iy = int((pts[i, 1] - miny) * inv)
            iz = int((pts[i, 2] - minz) * inv)
            cix[i] = ix
            ciy[i] = iy
            ciz[i] = iz
            c = (ix * ny + iy) * nz + iz
            nxt[i] = head[c]
            head[c] = i

        for i in range(n):
            ix = cix[i]
            iy = ciy[i]
            iz = ciz[i]
            x0 = pts[i, 0]
            y0 = pts[i, 1]
            z0 = pts[i, 2]
            count = 0
            for dx in range(-1, 2):
                jx = ix + dx
                if jx < 0 or jx >= nx:
                    continue
                for dy in range(-1, 2):
                    jy = iy + dy
                    if jy < 0 or jy >= ny:
                        continue
                    for dz in range(-1, 2):
                        jz = iz + dz
                        if jz < 0 or jz >= nz:
                            continue
                        j = head[(jx * ny + jy) * nz + jz]
                        while j != -1:
                            if j != i:
                                ddx = pts[j, 0] - x0
                                ddy = pts[j, 1] - y0
                                ddz = pts[j, 2] - z0
                                if ddx * ddx + ddy * ddy + ddz * ddz < r2:
                                    count += 1
                            j = nxt[j]
            if count > max_neighbors:
                count = max_neighbors
            occ[i] = float(count) / float(max_neighbors)

        return occ


    @nb.jit(nopython=True, nogil=True, cache=_NB_CACHE)  # type: ignore[misc]
    def _occlusion_from_spheres_nb(
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
        combined as ``1 - exp(-strength * sum)`` rather than added, which keeps
        the result in [0, 1) and stops a dense neighbourhood from saturating to
        pure black the way a plain sum would.

        Occluders are bucketed into a uniform cell list of side
        ``max_distance``, so the cost is linear in the number of vertices rather
        than quadratic against the atom count.
        """
        n = points.shape[0]
        occ = np.zeros(n, dtype=np.float64)
        m = centers.shape[0]
        if n == 0 or m == 0 or max_distance <= 0.0:
            return occ

        minx = miny = minz = 1.0e30
        maxx = maxy = maxz = -1.0e30
        for j in range(m):
            x = centers[j, 0]
            y = centers[j, 1]
            z = centers[j, 2]
            if x < minx:
                minx = x
            if x > maxx:
                maxx = x
            if y < miny:
                miny = y
            if y > maxy:
                maxy = y
            if z < minz:
                minz = z
            if z > maxz:
                maxz = z

        inv = 1.0 / max_distance
        nx = int((maxx - minx) * inv) + 1
        ny = int((maxy - miny) * inv) + 1
        nz = int((maxz - minz) * inv) + 1

        head = np.full(nx * ny * nz, -1, dtype=np.int64)
        nxt = np.empty(m, dtype=np.int64)
        for j in range(m):
            jx = int((centers[j, 0] - minx) * inv)
            jy = int((centers[j, 1] - miny) * inv)
            jz = int((centers[j, 2] - minz) * inv)
            c = (jx * ny + jy) * nz + jz
            nxt[j] = head[c]
            head[c] = j

        d_max2 = max_distance * max_distance
        for i in range(n):
            px = points[i, 0]
            py = points[i, 1]
            pz = points[i, 2]
            nx_i = normals[i, 0]
            ny_i = normals[i, 1]
            nz_i = normals[i, 2]

            ix = int((px - minx) * inv)
            iy = int((py - miny) * inv)
            iz = int((pz - minz) * inv)

            total = 0.0
            for dx in range(-1, 2):
                jx = ix + dx
                if jx < 0 or jx >= nx:
                    continue
                for dy in range(-1, 2):
                    jy = iy + dy
                    if jy < 0 or jy >= ny:
                        continue
                    for dz in range(-1, 2):
                        jz = iz + dz
                        if jz < 0 or jz >= nz:
                            continue
                        j = head[(jx * ny + jy) * nz + jz]
                        while j != -1:
                            vx = centers[j, 0] - px
                            vy = centers[j, 1] - py
                            vz = centers[j, 2] - pz
                            d2 = vx * vx + vy * vy + vz * vz
                            if d2 < d_max2 and d2 > 1.0e-12:
                                d = math.sqrt(d2)
                                r = radii[j]
                                # A vertex sitting inside an occluder is its own
                                # surface, not something blocking it.
                                if d > r:
                                    cos_theta = (
                                        vx * nx_i + vy * ny_i + vz * nz_i
                                    ) / d
                                    if cos_theta > 0.0:
                                        sin_a = r / d
                                        cov = 1.0 - math.sqrt(
                                            1.0 - sin_a * sin_a
                                        )
                                        total += cos_theta * cov
                            j = nxt[j]

            occ[i] = 1.0 - math.exp(-strength * total)

        return occ


    @nb.jit(nopython=True, nogil=True, cache=_NB_CACHE)  # type: ignore[misc]
    def _directional_occlusion_nb(
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
        """
        n = points.shape[0]
        shadow = np.zeros(n, dtype=np.float64)
        m = centers.shape[0]
        if n == 0 or m == 0 or max_distance <= 0.0:
            return shadow

        lx, ly, lz = direction[0], direction[1], direction[2]

        minx = miny = minz = 1.0e30
        maxx = maxy = maxz = -1.0e30
        for j in range(m):
            if centers[j, 0] < minx:
                minx = centers[j, 0]
            if centers[j, 0] > maxx:
                maxx = centers[j, 0]
            if centers[j, 1] < miny:
                miny = centers[j, 1]
            if centers[j, 1] > maxy:
                maxy = centers[j, 1]
            if centers[j, 2] < minz:
                minz = centers[j, 2]
            if centers[j, 2] > maxz:
                maxz = centers[j, 2]

        inv = 1.0 / max_distance
        nx = int((maxx - minx) * inv) + 1
        ny = int((maxy - miny) * inv) + 1
        nz = int((maxz - minz) * inv) + 1
        head = np.full(nx * ny * nz, -1, dtype=np.int64)
        nxt = np.empty(m, dtype=np.int64)
        for j in range(m):
            jx = int((centers[j, 0] - minx) * inv)
            jy = int((centers[j, 1] - miny) * inv)
            jz = int((centers[j, 2] - minz) * inv)
            c = (jx * ny + jy) * nz + jz
            nxt[j] = head[c]
            head[c] = j

        # The ray only ever moves toward the light, so walking cells along it
        # visits far fewer than a full neighbourhood search would.
        steps = int(max_distance / max_distance) + 2
        for i in range(n):
            px = points[i, 0]
            py = points[i, 1]
            pz = points[i, 2]
            if normals[i, 0] * lx + normals[i, 1] * ly + normals[i, 2] * lz <= 0.0:
                # Facing away: the diffuse term already darkens this.
                continue

            total = 0.0
            for s in range(steps):
                cx = px + lx * max_distance * s
                cy = py + ly * max_distance * s
                cz = pz + lz * max_distance * s
                ix = int((cx - minx) * inv)
                iy = int((cy - miny) * inv)
                iz = int((cz - minz) * inv)
                for dx in range(-1, 2):
                    jx = ix + dx
                    if jx < 0 or jx >= nx:
                        continue
                    for dy in range(-1, 2):
                        jy = iy + dy
                        if jy < 0 or jy >= ny:
                            continue
                        for dz in range(-1, 2):
                            jz = iz + dz
                            if jz < 0 or jz >= nz:
                                continue
                            j = head[(jx * ny + jy) * nz + jz]
                            while j != -1:
                                vx = centers[j, 0] - px
                                vy = centers[j, 1] - py
                                vz = centers[j, 2] - pz
                                along = vx * lx + vy * ly + vz * lz
                                if along > 0.0 and along < max_distance:
                                    r = radii[j]
                                    ox = vx - along * lx
                                    oy = vy - along * ly
                                    oz = vz - along * lz
                                    perp2 = ox * ox + oy * oy + oz * oz
                                    reach = r * softness
                                    if perp2 < reach * reach:
                                        d2 = vx * vx + vy * vy + vz * vz
                                        if d2 > r * r:
                                            blocked = 1.0 - math.sqrt(perp2) / reach
                                            total += blocked * blocked
                                j = nxt[j]
            shadow[i] = 1.0 - math.exp(-strength * total)

        return shadow


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

    if _HAVE_NUMBA and nb is not None:
        try:
            occ = _occlusion_from_spheres_nb(  # type: ignore[name-defined]
                pts, nrm, ctr, rad, float(max_distance), float(strength)
            )
            return np.clip(occ, 0.0, 1.0)
        except Exception:
            pass

    return _occlusion_from_spheres_numpy(
        pts, nrm, ctr, rad, float(max_distance), float(strength)
    )


def _occlusion_from_spheres_numpy(
    points: np.ndarray,
    normals: np.ndarray,
    centers: np.ndarray,
    radii: np.ndarray,
    max_distance: float,
    strength: float,
) -> np.ndarray:
    """Numba-free fallback for :func:`occlusion_from_spheres`.

    Chunked over vertices so the ``(chunk, M)`` distance matrix stays bounded
    regardless of how many vertices the mesh has.
    """
    n = points.shape[0]
    occ = np.zeros(n, dtype=float)
    chunk = max(1, int(4_000_000 // max(centers.shape[0], 1)))
    d_max2 = max_distance * max_distance

    for start in range(0, n, chunk):
        stop = min(start + chunk, n)
        v = centers[None, :, :] - points[start:stop, None, :]
        d2 = np.einsum("ijk,ijk->ij", v, v)
        with np.errstate(invalid="ignore", divide="ignore"):
            d = np.sqrt(d2)
            cos_theta = np.einsum("ijk,ik->ij", v, normals[start:stop]) / d
            sin_a = np.minimum(radii[None, :] / d, 1.0)
            cov = 1.0 - np.sqrt(np.maximum(1.0 - sin_a * sin_a, 0.0))
        valid = (d2 < d_max2) & (d2 > 1e-12) & (d > radii[None, :]) & (cos_theta > 0.0)
        contrib = np.where(valid, cos_theta * cov, 0.0)
        occ[start:stop] = 1.0 - np.exp(-strength * contrib.sum(axis=1))

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

    if not (_HAVE_NUMBA and nb is not None):
        # No numba: the ambient term alone still gives depth, and a pure-NumPy
        # ray march over every vertex would cost more than it is worth here.
        return None

    try:
        shadow = _directional_occlusion_nb(  # type: ignore[name-defined]
            pts, nrm, ctr, rad, light,
            float(max_distance), float(softness), float(strength),
        )
    except Exception:
        return None
    return np.clip(shadow, 0.0, 1.0)


def _estimate_ambient_occlusion(
    points: np.ndarray,
    radius: float = 4.0,
    max_neighbors: int = 32,
) -> Optional[np.ndarray]:
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[0] == 0:
        return None

    n = pts.shape[0]
    if n == 1:
        return np.zeros(1, dtype=float)

    r = float(radius)
    if not np.isfinite(r) or r <= 0.0:
        return None

    # Preferred: the O(n) numba cell list. This replaces a former numba O(n^2)
    # double loop that was the single dominant cost of the metaball/surface
    # representations on the tens of thousands of vertices a marching-cubes
    # surface produces. (IMP's ``NearestNeighbor3D.get_in_ball`` was evaluated
    # and rejected: it silently drops interior neighbours -- an approximate
    # search -- and ``GridClosePairsFinder`` materialises every close pair, which
    # blows up on dense meshes. scipy is deliberately not used: it is not a
    # dependency here.) The pure-NumPy grid hash below is the numba-free
    # fallback.
    if _HAVE_NUMBA and nb is not None:
        try:
            occ_grid = _estimate_ambient_occlusion_grid_nb(  # type: ignore[name-defined]
                pts, r, int(max_neighbors)
            )
            return np.clip(occ_grid, 0.0, 1.0)
        except Exception:
            pass

    cell = r
    inv_cell = 1.0 / cell

    centered = pts - pts.mean(axis=0)
    ijk = np.floor(centered * inv_cell).astype(np.int32)

    grid: dict[tuple[int, int, int], list[int]] = {}
    for idx, key in enumerate(map(tuple, ijk)):
        grid.setdefault(key, []).append(idx)

    neighbor_offsets = [
        (dx, dy, dz)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        for dz in (-1, 0, 1)
    ]

    occ = np.zeros(n, dtype=float)
    r2 = r * r

    for idx, key in enumerate(map(tuple, ijk)):
        ix, iy, iz = key
        cand_idx: list[int] = []
        for dx, dy, dz in neighbor_offsets:
            cand_idx.extend(grid.get((ix + dx, iy + dy, iz + dz), []))

        if not cand_idx:
            continue

        if len(cand_idx) > max_neighbors * 4:
            cand_idx = cand_idx[: max_neighbors * 4]

        cand = np.asarray(cand_idx, dtype=int)
        diffs = pts[cand] - pts[idx]
        dist2 = np.einsum("ij,ij->i", diffs, diffs)
        within = dist2 < r2
        count = int(np.count_nonzero(within))
        if count <= 0:
            continue

        if count > max_neighbors:
            count = max_neighbors
        occ[idx] = float(count)

    if max_neighbors > 0:
        occ /= float(max_neighbors)

    return np.clip(occ, 0.0, 1.0)


__all__ = [
    "_estimate_ambient_occlusion",
    "occlusion_from_spheres",
    "directional_occlusion",
]

