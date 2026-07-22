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


if _HAVE_NUMBA and nb is not None:

    @nb.jit(nopython=True, nogil=True, cache=True)  # type: ignore[misc]
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

    @nb.jit(nopython=True, nogil=True, cache=True)  # type: ignore[misc]
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


__all__ = ["_estimate_ambient_occlusion"]

