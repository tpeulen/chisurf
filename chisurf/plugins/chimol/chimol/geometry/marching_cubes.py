"""Self-contained marching cubes (NumPy + optional numba).

ChiMOL's surface/metaball/AV representations need to extract an isosurface mesh
from a scalar grid. The scientific stack normally supplies this
(``skimage.measure.marching_cubes``), but this codebase is being narrowed to
depend only on IMP (plus NumPy/numba) — scipy and scikit-image are not permitted
runtime dependencies. IMP *can* produce an isosurface
(``IMP.display.IsosurfaceGeometry``) but its CGAL mesher is ~2 s for a 60³ grid,
far too slow for interactive rendering.

This module is the standard Lorensen–Cline marching cubes with the canonical
edge/triangle tables. The per-cell work is a numba kernel; a NumPy fallback keeps
it importable without numba. Vertex normals are taken from the trilinearly
interpolated grid gradient (as ``skimage`` does), so the output is a drop-in for
the ``(verts, faces, normals)`` the renderer expects.

Corner / edge numbering (Lorensen–Cline):

    corners: 0:(0,0,0) 1:(1,0,0) 2:(1,1,0) 3:(0,1,0)
             4:(0,0,1) 5:(1,0,1) 6:(1,1,1) 7:(0,1,1)
    edges:   0:0-1 1:1-2 2:2-3 3:3-0 4:4-5 5:5-6 6:6-7 7:7-4
             8:0-4 9:1-5 10:2-6 11:3-7
"""

from __future__ import annotations

# Numba is required. The `_HAVE_NUMBA` guard it replaces made every kernel
# here optional and every fallback beside it unexercised -- which is how the
# ray tracer's pure-NumPy twin came to be silently broken while every test
# passed.
import numba as _nb
import numpy as np

# Corner offsets in (x, y, z).
_CORNERS = np.array(
    [
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ],
    dtype=np.int64,
)

# The two corners joined by each of the 12 edges.
_EDGE_CORNERS = np.array(
    [
        [0, 1], [1, 2], [2, 3], [3, 0],
        [4, 5], [5, 6], [6, 7], [7, 4],
        [0, 4], [1, 5], [2, 6], [3, 7],
    ],
    dtype=np.int64,
)

# For welding: each cube edge maps to a unique grid edge identified by an axis
# (0=x,1=y,2=z) and the offset of its lower corner within the cell. Two adjacent
# cells sharing an edge therefore share the same vertex.
_EDGE_MAP = np.array(
    [
        [0, 0, 0, 0], [1, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0],
        [0, 0, 0, 1], [1, 1, 0, 1], [0, 0, 1, 1], [1, 0, 0, 1],
        [2, 0, 0, 0], [2, 1, 0, 0], [2, 1, 1, 0], [2, 0, 1, 0],
    ],
    dtype=np.int64,
)

# 256-entry edge table: bitmask of edges intersected for each corner-sign case.
_EDGE_TABLE = np.array([
    0x0, 0x109, 0x203, 0x30a, 0x406, 0x50f, 0x605, 0x70c,
    0x80c, 0x905, 0xa0f, 0xb06, 0xc0a, 0xd03, 0xe09, 0xf00,
    0x190, 0x99, 0x393, 0x29a, 0x596, 0x49f, 0x795, 0x69c,
    0x99c, 0x895, 0xb9f, 0xa96, 0xd9a, 0xc93, 0xf99, 0xe90,
    0x230, 0x339, 0x33, 0x13a, 0x636, 0x73f, 0x435, 0x53c,
    0xa3c, 0xb35, 0x83f, 0x936, 0xe3a, 0xf33, 0xc39, 0xd30,
    0x3a0, 0x2a9, 0x1a3, 0xaa, 0x7a6, 0x6af, 0x5a5, 0x4ac,
    0xbac, 0xaa5, 0x9af, 0x8a6, 0xfaa, 0xea3, 0xda9, 0xca0,
    0x460, 0x569, 0x663, 0x76a, 0x66, 0x16f, 0x265, 0x36c,
    0xc6c, 0xd65, 0xe6f, 0xf66, 0x86a, 0x963, 0xa69, 0xb60,
    0x5f0, 0x4f9, 0x7f3, 0x6fa, 0x1f6, 0xff, 0x3f5, 0x2fc,
    0xdfc, 0xcf5, 0xfff, 0xef6, 0x9fa, 0x8f3, 0xbf9, 0xaf0,
    0x650, 0x759, 0x453, 0x55a, 0x256, 0x35f, 0x55, 0x15c,
    0xe5c, 0xf55, 0xc5f, 0xd56, 0xa5a, 0xb53, 0x859, 0x950,
    0x7c0, 0x6c9, 0x5c3, 0x4ca, 0x3c6, 0x2cf, 0x1c5, 0xcc,
    0xfcc, 0xec5, 0xdcf, 0xcc6, 0xbca, 0xac3, 0x9c9, 0x8c0,
    0x8c0, 0x9c9, 0xac3, 0xbca, 0xcc6, 0xdcf, 0xec5, 0xfcc,
    0xcc, 0x1c5, 0x2cf, 0x3c6, 0x4ca, 0x5c3, 0x6c9, 0x7c0,
    0x950, 0x859, 0xb53, 0xa5a, 0xd56, 0xc5f, 0xf55, 0xe5c,
    0x15c, 0x55, 0x35f, 0x256, 0x55a, 0x453, 0x759, 0x650,
    0xaf0, 0xbf9, 0x8f3, 0x9fa, 0xef6, 0xfff, 0xcf5, 0xdfc,
    0x2fc, 0x3f5, 0xff, 0x1f6, 0x6fa, 0x7f3, 0x4f9, 0x5f0,
    0xb60, 0xa69, 0x963, 0x86a, 0xf66, 0xe6f, 0xd65, 0xc6c,
    0x36c, 0x265, 0x16f, 0x66, 0x76a, 0x663, 0x569, 0x460,
    0xca0, 0xda9, 0xea3, 0xfaa, 0x8a6, 0x9af, 0xaa5, 0xbac,
    0x4ac, 0x5a5, 0x6af, 0x7a6, 0xaa, 0x1a3, 0x2a9, 0x3a0,
    0xd30, 0xc39, 0xf33, 0xe3a, 0x936, 0x83f, 0xb35, 0xa3c,
    0x53c, 0x435, 0x73f, 0x636, 0x13a, 0x33, 0x339, 0x230,
    0xe90, 0xf99, 0xc93, 0xd9a, 0xa96, 0xb9f, 0x895, 0x99c,
    0x69c, 0x795, 0x49f, 0x596, 0x29a, 0x393, 0x99, 0x190,
    0xf00, 0xe09, 0xd03, 0xc0a, 0xb06, 0xa0f, 0x905, 0x80c,
    0x70c, 0x605, 0x50f, 0x406, 0x30a, 0x203, 0x109, 0x0,
], dtype=np.int64)


def _load_tri_table() -> np.ndarray:
    """Return the 256x16 triangle table (edge indices, -1 padded)."""
    # Packed as one flat sequence of 256 rows, each row a list of edge triples
    # terminated by -1 and padded to length 16. Kept in a module-level string to
    # avoid a 4096-line literal; parsed once at import.
    from ._mc_tri_table import TRI_TABLE  # noqa: PLC0415

    table = np.full((256, 16), -1, dtype=np.int64)
    for i, row in enumerate(TRI_TABLE):
        table[i, : len(row)] = row
    return table


_TRI_TABLE = _load_tri_table()


@_nb.njit(cache=True)  # type: ignore[misc]
def _mc_count(grid, level, corners, tri_table):
    nx, ny, nz = grid.shape
    n_tri = 0
    for ci in range(nx - 1):
        for cj in range(ny - 1):
            for ck in range(nz - 1):
                idx = 0
                for c in range(8):
                    if grid[ci + corners[c, 0], cj + corners[c, 1], ck + corners[c, 2]] < level:
                        idx |= 1 << c
                if idx == 0 or idx == 255:
                    continue
                t = 0
                while tri_table[idx, t] != -1:
                    n_tri += 1
                    t += 3
    return n_tri

@_nb.njit(cache=True)  # type: ignore[misc]
def _mc_fill(grid, level, corners, edge_corners, edge_map, tri_table, n_tri):
    # Exact allocation from the counting pass avoids the huge worst-case
    # (n_cells * 5) buffer that dominated runtime for large grids.
    verts = np.empty((n_tri * 3, 3), dtype=np.float64)
    faces = np.empty((n_tri, 3), dtype=np.int64)
    nx, ny, nz = grid.shape
    # Weld vertices via a per-grid-edge index so adjacent cells share the
    # vertex on their common edge (matches skimage's vertex count and gives
    # a connected mesh rather than 3 loose verts per triangle).
    edge_vid = np.full(3 * nx * ny * nz, -1, dtype=np.int64)
    nv = 0
    nf = 0
    cv = np.empty(8, dtype=np.float64)
    for ci in range(nx - 1):
        for cj in range(ny - 1):
            for ck in range(nz - 1):
                idx = 0
                for c in range(8):
                    vx = grid[ci + corners[c, 0], cj + corners[c, 1], ck + corners[c, 2]]
                    cv[c] = vx
                    if vx < level:
                        idx |= 1 << c
                if idx == 0 or idx == 255:
                    continue
                t = 0
                while tri_table[idx, t] != -1:
                    for kk in range(3):
                        e = tri_table[idx, t + kk]
                        axis = edge_map[e, 0]
                        ei = ci + edge_map[e, 1]
                        ej = cj + edge_map[e, 2]
                        ek = ck + edge_map[e, 3]
                        gid = ((axis * nx + ei) * ny + ej) * nz + ek
                        vid = edge_vid[gid]
                        if vid == -1:
                            a = edge_corners[e, 0]
                            b = edge_corners[e, 1]
                            va = cv[a]
                            vb = cv[b]
                            denom = vb - va
                            if denom < 1e-12 and denom > -1e-12:
                                mu = 0.5
                            else:
                                mu = (level - va) / denom
                            verts[nv, 0] = ci + corners[a, 0] + mu * (corners[b, 0] - corners[a, 0])
                            verts[nv, 1] = cj + corners[a, 1] + mu * (corners[b, 1] - corners[a, 1])
                            verts[nv, 2] = ck + corners[a, 2] + mu * (corners[b, 2] - corners[a, 2])
                            vid = nv
                            edge_vid[gid] = vid
                            nv += 1
                        faces[nf, kk] = vid
                    nf += 1
                    t += 3
    return verts[:nv], faces[:nf]

def _mc_kernel(grid, level, corners, edge_corners, edge_map, tri_table):
    n_tri = _mc_count(grid, level, corners, tri_table)
    if n_tri == 0:
        return np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.int64)
    return _mc_fill(grid, level, corners, edge_corners, edge_map, tri_table, n_tri)


def marching_cubes(grid, level, spacing=(1.0, 1.0, 1.0)):
    """Extract an isosurface mesh from a scalar grid.

    Parameters
    ----------
    grid : numpy.ndarray
        Scalar field of shape ``(nx, ny, nz)``.
    level : float
        Iso value; a corner is "inside" when its value is ``< level``.
    spacing : tuple of float
        Physical size of a voxel along each axis.

    Returns
    -------
    tuple
        ``(verts, faces, normals)``. ``verts`` are in grid-index units scaled by
        ``spacing`` (add the grid origin afterwards). Normals come from the
        trilinearly interpolated grid gradient and point toward increasing value.
        Empty arrays are returned when the surface does not cross the grid.
    """
    g = np.ascontiguousarray(grid, dtype=np.float64)
    level = float(level)
    if g.ndim != 3 or min(g.shape) < 2:
        return (
            np.zeros((0, 3), dtype=np.float64),
            np.zeros((0, 3), dtype=np.int64),
            np.zeros((0, 3), dtype=np.float64),
        )

    verts, faces = _mc_kernel(g, level, _CORNERS, _EDGE_CORNERS, _EDGE_MAP, _TRI_TABLE)

    if verts.shape[0] == 0:
        return (
            np.zeros((0, 3), dtype=np.float64),
            np.zeros((0, 3), dtype=np.int64),
            np.zeros((0, 3), dtype=np.float64),
        )

    # Vertex normals from the interpolated grid gradient (points up-gradient).
    gx, gy, gz = np.gradient(g)
    normals = _sample_gradient(gx, gy, gz, verts)

    sp = np.asarray(spacing, dtype=np.float64)
    verts = verts * sp
    # Rescale gradient normals by 1/spacing so anisotropic voxels stay correct.
    normals = normals / np.where(sp > 0, sp, 1.0)
    ln = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.divide(normals, np.where(ln > 1e-12, ln, 1.0))
    # Match skimage.measure.marching_cubes' output convention (outward normals,
    # matching triangle winding) so this is a drop-in replacement: callers that
    # post-process skimage output keep working unchanged.
    normals = -normals
    faces = faces[:, [0, 2, 1]]
    return verts, faces.astype(np.int64), normals


def _sample_gradient(gx, gy, gz, verts):
    """Trilinearly sample a gradient field at fractional vertex positions."""
    shape = np.array(gx.shape) - 1
    p = np.clip(verts, 0.0, shape.astype(float))
    i0 = np.floor(p).astype(np.int64)
    i0 = np.minimum(i0, shape - 1)
    frac = p - i0
    out = np.empty_like(verts)
    for axis, gfield in enumerate((gx, gy, gz)):
        acc = np.zeros(verts.shape[0], dtype=np.float64)
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    w = (
                        (frac[:, 0] if dx else 1 - frac[:, 0])
                        * (frac[:, 1] if dy else 1 - frac[:, 1])
                        * (frac[:, 2] if dz else 1 - frac[:, 2])
                    )
                    acc += w * gfield[i0[:, 0] + dx, i0[:, 1] + dy, i0[:, 2] + dz]
        out[:, axis] = acc
    return out


__all__ = ["marching_cubes"]
