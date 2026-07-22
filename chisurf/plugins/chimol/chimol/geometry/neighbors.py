"""Uniform-grid (cell-list) neighbour queries — NumPy/numba, no scipy.

ChiMOL's surface colouring, surface-atom masking and distance-based selection
previously leaned on ``scipy.spatial.cKDTree``. This module provides the same
queries with a numba cell list (cell size = query radius, so every point within
the radius lies in the query cell or one of its 26 neighbours), keeping the
renderer dependent only on IMP / NumPy / numba.
"""

from __future__ import annotations

import numpy as np

try:  # optional numba acceleration
    import numba as _nb  # type: ignore
    _HAVE_NUMBA = True
except Exception:  # pragma: no cover - environment dependent
    _nb = None  # type: ignore
    _HAVE_NUMBA = False


if _HAVE_NUMBA and _nb is not None:

    @_nb.njit(cache=True, nogil=True)  # type: ignore[misc]
    def _build_cells(pts, cell):
        n = pts.shape[0]
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
        inv = 1.0 / cell
        nx = int((maxx - minx) * inv) + 1
        ny = int((maxy - miny) * inv) + 1
        nz = int((maxz - minz) * inv) + 1
        head = np.full(nx * ny * nz, -1, dtype=np.int64)
        nxt = np.empty(n, dtype=np.int64)
        for i in range(n):
            ix = int((pts[i, 0] - minx) * inv)
            iy = int((pts[i, 1] - miny) * inv)
            iz = int((pts[i, 2] - minz) * inv)
            c = (ix * ny + iy) * nz + iz
            nxt[i] = head[c]
            head[c] = i
        return head, nxt, minx, miny, minz, nx, ny, nz, inv

    @_nb.njit(cache=True, nogil=True)  # type: ignore[misc]
    def _count_within_radius_nb(pts, radius):
        n = pts.shape[0]
        counts = np.zeros(n, dtype=np.int64)
        if n <= 1 or radius <= 0.0:
            return counts
        head, nxt, minx, miny, minz, nx, ny, nz, inv = _build_cells(pts, radius)
        r2 = radius * radius
        for i in range(n):
            xi = pts[i, 0]
            yi = pts[i, 1]
            zi = pts[i, 2]
            ix = int((xi - minx) * inv)
            iy = int((yi - miny) * inv)
            iz = int((zi - minz) * inv)
            cnt = 0
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
                                ddx = pts[j, 0] - xi
                                ddy = pts[j, 1] - yi
                                ddz = pts[j, 2] - zi
                                if ddx * ddx + ddy * ddy + ddz * ddz < r2:
                                    cnt += 1
                            j = nxt[j]
            counts[i] = cnt
        return counts

    @_nb.njit(cache=True, nogil=True)  # type: ignore[misc]
    def _within_distance_mask_nb(coords, targets, dist):
        n = coords.shape[0]
        mask = np.zeros(n, dtype=np.bool_)
        m = targets.shape[0]
        if n == 0 or m == 0 or dist <= 0.0:
            return mask
        head, nxt, minx, miny, minz, nx, ny, nz, inv = _build_cells(coords, dist)
        d2 = dist * dist
        for t in range(m):
            tx = targets[t, 0]
            ty = targets[t, 1]
            tz = targets[t, 2]
            ix = int((tx - minx) * inv)
            iy = int((ty - miny) * inv)
            iz = int((tz - minz) * inv)
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
                            ddx = coords[j, 0] - tx
                            ddy = coords[j, 1] - ty
                            ddz = coords[j, 2] - tz
                            if ddx * ddx + ddy * ddy + ddz * ddz <= d2:
                                mask[j] = True
                            j = nxt[j]
        return mask

    @_nb.njit(cache=True, nogil=True)  # type: ignore[misc]
    def _shade_from_atoms_nb(verts, atoms, colors, sigmas, cutoff):
        nv = verts.shape[0]
        out_col = np.zeros((nv, 4), dtype=np.float64)
        grad = np.zeros((nv, 3), dtype=np.float64)
        wsum = np.zeros(nv, dtype=np.float64)
        nearest = np.full(nv, -1, dtype=np.int64)
        na = atoms.shape[0]
        if na == 0 or cutoff <= 0.0:
            return out_col, wsum, grad, nearest
        head, nxt, minx, miny, minz, nx, ny, nz, inv = _build_cells(atoms, cutoff)
        c2 = cutoff * cutoff
        for i in range(nv):
            vx = verts[i, 0]
            vy = verts[i, 1]
            vz = verts[i, 2]
            ix = int((vx - minx) * inv)
            iy = int((vy - miny) * inv)
            iz = int((vz - minz) * inv)
            if ix < 0:
                ix = 0
            elif ix >= nx:
                ix = nx - 1
            if iy < 0:
                iy = 0
            elif iy >= ny:
                iy = ny - 1
            if iz < 0:
                iz = 0
            elif iz >= nz:
                iz = nz - 1
            best = 1.0e30
            bidx = -1
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
                            ddx = vx - atoms[j, 0]
                            ddy = vy - atoms[j, 1]
                            ddz = vz - atoms[j, 2]
                            dd = ddx * ddx + ddy * ddy + ddz * ddz
                            if dd < best:
                                best = dd
                                bidx = j
                            if dd < c2:
                                s = sigmas[j]
                                s2 = s * s
                                w = np.exp(-dd / (2.0 * s2))
                                out_col[i, 0] += w * colors[j, 0]
                                out_col[i, 1] += w * colors[j, 1]
                                out_col[i, 2] += w * colors[j, 2]
                                out_col[i, 3] += w * colors[j, 3]
                                wsum[i] += w
                                inv_s2 = 1.0 / s2
                                grad[i, 0] += ddx * inv_s2 * w
                                grad[i, 1] += ddy * inv_s2 * w
                                grad[i, 2] += ddz * inv_s2 * w
                            j = nxt[j]
            nearest[i] = bidx
        return out_col, wsum, grad, nearest


def count_within_radius(points, radius):
    """Return the number of other points within ``radius`` of each point."""
    pts = np.ascontiguousarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[0] == 0 or radius <= 0.0:
        return np.zeros(pts.shape[0] if pts.ndim == 2 else 0, dtype=np.int64)
    if _HAVE_NUMBA and _nb is not None:
        return _count_within_radius_nb(pts, float(radius))
    # NumPy fallback (O(n^2)) — numba is present in the supported env.
    d2 = np.sum((pts[:, None, :] - pts[None, :, :]) ** 2, axis=2)
    np.fill_diagonal(d2, np.inf)
    return np.count_nonzero(d2 < radius * radius, axis=1).astype(np.int64)


def within_distance_mask(coords, targets, dist):
    """Boolean mask of ``coords`` lying within ``dist`` of any ``targets`` point."""
    c = np.ascontiguousarray(coords, dtype=np.float64)
    t = np.ascontiguousarray(targets, dtype=np.float64)
    if c.ndim != 2 or c.shape[0] == 0 or t.ndim != 2 or t.shape[0] == 0 or dist <= 0.0:
        return np.zeros(c.shape[0] if c.ndim == 2 else 0, dtype=bool)
    if _HAVE_NUMBA and _nb is not None:
        return np.asarray(_within_distance_mask_nb(c, t, float(dist)))
    d2 = np.min(np.sum((c[:, None, :] - t[None, :, :]) ** 2, axis=2), axis=1)
    return d2 <= dist * dist


def shade_from_atoms(verts, atoms, atom_colors, sigmas, cutoff):
    """Gaussian-weighted colour and gradient normal at each vertex from atoms.

    Returns ``(colors, wsum, grad, nearest)`` where ``colors`` is the unnormalised
    Gaussian-weighted RGBA sum, ``wsum`` the weight sum, ``grad`` the density
    gradient, and ``nearest`` the index of the closest atom (for vertices with no
    atom inside ``cutoff``). Callers normalise ``colors`` by ``wsum`` and derive
    the shading normal as ``-grad / |grad|``.
    """
    v = np.ascontiguousarray(verts, dtype=np.float64)
    a = np.ascontiguousarray(atoms, dtype=np.float64)
    col = np.ascontiguousarray(atom_colors, dtype=np.float64)
    sg = np.ascontiguousarray(sigmas, dtype=np.float64)
    if _HAVE_NUMBA and _nb is not None:
        return _shade_from_atoms_nb(v, a, col, sg, float(cutoff))
    # NumPy fallback.
    nv = v.shape[0]
    out_col = np.zeros((nv, 4))
    grad = np.zeros((nv, 3))
    wsum = np.zeros(nv)
    nearest = np.full(nv, -1, dtype=np.int64)
    for i in range(nv):
        diff = v[i] - a
        dd = np.einsum("ij,ij->i", diff, diff)
        nearest[i] = int(np.argmin(dd))
        within = dd < cutoff * cutoff
        if within.any():
            s2 = sg[within] ** 2
            w = np.exp(-dd[within] / (2.0 * s2))
            out_col[i] = (col[within] * w[:, None]).sum(axis=0)
            wsum[i] = w.sum()
            grad[i] = ((diff[within] / s2[:, None]) * w[:, None]).sum(axis=0)
    return out_col, wsum, grad, nearest


__all__ = ["count_within_radius", "within_distance_mask", "shade_from_atoms"]
