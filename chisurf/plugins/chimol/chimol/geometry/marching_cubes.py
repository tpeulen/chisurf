"""Self-contained marching cubes, vectorised over cells.

ChiMOL's surface/metaball/AV representations need to extract an isosurface mesh
from a scalar grid. The scientific stack normally supplies this
(``skimage.measure.marching_cubes``), which is a large dependency for one
function; IMP *can* produce an isosurface (``IMP.display.IsosurfaceGeometry``)
but its CGAL mesher is ~2 s for a 60³ grid, far too slow for interactive
rendering.

This module is the standard Lorensen–Cline marching cubes with the canonical
edge/triangle tables. Every cell is processed at once with array operations
rather than in a per-cell loop, which is what lets it be plain NumPy: the case
index is a bit-packed comparison over eight shifted views of the grid, and the
triangle table is applied by fancy indexing. Vertex normals are taken from the
trilinearly interpolated grid gradient (as ``skimage`` does), so the output is a
drop-in for the ``(verts, faces, normals)`` the renderer expects.

Two habits here are taken from the reference viewer's contour code
(``_map/contour.cpp`` in the ChimeraX checkout), which is the authority on
doing this fast:

* **The grid is read in its own precision.** A ``float32`` map stays
  ``float32`` end to end; promoting a 180³ map to ``float64`` before looking
  at it doubles the memory traffic of every full-grid pass and was costing
  more than the triangulation itself. The corner cases are packed into
  ``uint8`` for the same reason — a case is 0–255, and an ``int64`` temporary
  per corner bit is eight times the traffic for no information.
* **The gradient is sampled only at surface vertices.** Every welded vertex
  sits on one grid edge, so its trilinear gradient reduces to the symmetric
  difference at the edge's two end nodes, lerped by the crossing fraction —
  exactly the reference's per-vertex normal. Building three full-grid
  ``np.gradient`` fields first (as this module once did) allocated 3×N
  doubles to read back a few thousand values, and dominated the profile.

Corner / edge numbering (Lorensen–Cline):

    corners: 0:(0,0,0) 1:(1,0,0) 2:(1,1,0) 3:(0,1,0)
             4:(0,0,1) 5:(1,0,1) 6:(1,1,1) 7:(0,1,1)
    edges:   0:0-1 1:1-2 2:2-3 3:3-0 4:4-5 5:5-6 6:6-7 7:7-4
             8:0-4 9:1-5 10:2-6 11:3-7
"""

from __future__ import annotations

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


#: Unit step along each grid axis, for turning an edge id back into the pair of
#: corners it joins.
_AXIS_STEP = np.eye(3, dtype=np.int64)


def _triangle_edges(active, case_of_active, cell_shape, dims, edge_map, tri_table):
    """Grid-edge ids per triangle corner, welded, plus the face list.

    Parameters
    ----------
    active : numpy.ndarray
        Flat indices of the cells the surface crosses, ascending.
    case_of_active : numpy.ndarray
        Corner-sign case of each.
    cell_shape : tuple of int
        ``(nx-1, ny-1, nz-1)``.
    dims : tuple of int
        ``(nx, ny, nz)``.
    edge_map : numpy.ndarray
        ``(12, 4)`` axis and lower-corner offset of each cube edge.
    tri_table : numpy.ndarray
        ``(256, 16)`` edge triples per case, ``-1`` padded.

    Returns
    -------
    tuple
        ``(unique_edge_ids, faces)``.

    Notes
    -----
    Vertices are welded by *grid* edge, not by cube edge, so two cells sharing an
    edge share the vertex on it — that is what makes the output a connected mesh
    with skimage's vertex count rather than three loose vertices per triangle.
    Identifying the edge globally also removes the interpolation's dependence on
    which cell reached it first, which is what lets the placement happen
    somewhere else entirely: on the GPU, from a volume the host never sees.
    """
    nx, ny, nz = dims
    rows = tri_table[case_of_active]
    cells = []
    triangles = []
    # Five triangle slots per case, terminated by -1; a whole slot at a time is
    # five array operations instead of a loop over cells.
    for slot in range(tri_table.shape[1] // 3):
        column = slot * 3
        used = rows[:, column] != -1
        if not used.any():
            continue
        cells.append(active[used])
        triangles.append(rows[used, column:column + 3])
    if not cells:
        return np.zeros(0, dtype=np.int64), np.zeros((0, 3), dtype=np.int64)

    cell_index = np.concatenate(cells)
    edge_index = np.concatenate(triangles)

    ci, cj, ck = np.unravel_index(cell_index, cell_shape)
    corner = np.repeat(np.stack((ci, cj, ck), axis=1), 3, axis=0)
    edge = edge_index.reshape(-1)
    axis = edge_map[edge, 0]
    corner = corner + edge_map[edge, 1:]

    identifier = ((axis * nx + corner[:, 0]) * ny + corner[:, 1]) * nz + corner[:, 2]

    # `np.unique(..., return_inverse=True)` would sort 330k ids to find 55k
    # distinct ones. The ids are dense and bounded -- three per grid node -- so a
    # mark-and-number pass over that range is cheaper: `flatnonzero` returns them
    # already ascending, which is the order `unique` would have given, so the
    # vertex numbering is unchanged.
    marked = np.zeros(3 * nx * ny * nz, dtype=bool)
    marked[identifier] = True
    unique = np.flatnonzero(marked)
    slot = np.zeros(marked.size, dtype=np.int32)
    slot[unique] = np.arange(unique.size, dtype=np.int32)
    return unique, slot[identifier].reshape(-1, 3).astype(np.int64)


def _place_vertices(grid, level, unique, dims):
    """Interpolate each welded vertex onto its grid edge, on the host.

    Parameters
    ----------
    grid : numpy.ndarray
        ``(nx, ny, nz)`` scalar field.
    level : float
        Iso value.
    unique : numpy.ndarray
        Grid-edge ids.
    dims : tuple of int
        ``(nx, ny, nz)``.

    Returns
    -------
    tuple
        ``(verts, lower, vaxis, mu)`` — the ``(m, 3)`` positions in grid-index
        units, plus the edge each vertex sits on (its lower grid node, its
        axis, and the crossing fraction along it), which is what the normal
        sampling needs to avoid a full-grid gradient.
    """
    nx, ny, nz = dims
    volume = nx * ny * nz
    vaxis = unique // volume
    rest = unique % volume
    vi = rest // (ny * nz)
    rest = rest % (ny * nz)
    vj = rest // nz
    vk = rest % nz
    lower = np.stack((vi, vj, vk), axis=1)
    upper = lower + _AXIS_STEP[vaxis]

    below = grid[lower[:, 0], lower[:, 1], lower[:, 2]].astype(np.float64)
    above = grid[upper[:, 0], upper[:, 1], upper[:, 2]].astype(np.float64)
    span = above - below
    # A flat edge has no crossing to locate; the midpoint is what the tables
    # assume, and dividing by the span would be a division by zero.
    mu = np.where(
        np.abs(span) < 1e-12, 0.5,
        (level - below) / np.where(span == 0.0, 1.0, span),
    )
    verts = lower.astype(np.float64) + mu[:, None] * _AXIS_STEP[vaxis]
    return verts, lower, vaxis, mu


def _cell_cases(grid, level, corners):
    """Every cell's corner-sign case, and the ones the surface crosses.

    Parameters
    ----------
    grid : numpy.ndarray
        ``(nx, ny, nz)`` scalar field.
    level : float
        Iso value.
    corners : numpy.ndarray
        ``(8, 3)`` cube-corner offsets.

    Returns
    -------
    tuple
        ``(active, case_of_active)``.
    """
    nx, ny, nz = grid.shape
    inside = grid < level
    # A case is 0–255: packing it into uint8 instead of int64 cuts the memory
    # traffic of this (full-grid) phase eightfold, and the one reused scratch
    # buffer keeps the eight corner passes from allocating eight temporaries.
    bits = inside.view(np.uint8)
    case = np.zeros((nx - 1, ny - 1, nz - 1), dtype=np.uint8)
    scratch = np.empty_like(case)
    for bit in range(8):
        ox, oy, oz = corners[bit]
        np.multiply(
            bits[ox:ox + nx - 1, oy:oy + ny - 1, oz:oz + nz - 1],
            np.uint8(1 << bit), out=scratch,
        )
        np.bitwise_or(case, scratch, out=case)
    flat = case.ravel()
    active = np.flatnonzero((flat != 0) & (flat != 255))
    return active, flat[active]


def marching_cubes(grid, level, spacing=(1.0, 1.0, 1.0), volume=None):
    """Extract an isosurface mesh from a scalar grid.

    Parameters
    ----------
    grid : numpy.ndarray
        Scalar field of shape ``(nx, ny, nz)``. May be ``None`` when ``volume``
        is given and the host has no copy.
    level : float
        Iso value; a corner is "inside" when its value is ``< level``.
    spacing : tuple of float
        Physical size of a voxel along each axis.
    volume : chimol.renderer.compute.GpuVolume, optional
        The same field, already on the device. When present the grid is never
        touched by the host: the crossings, the interpolation and the normals all
        read it where it is.

    Returns
    -------
    tuple
        ``(verts, faces, normals)``. ``verts`` are in grid-index units scaled by
        ``spacing`` (add the grid origin afterwards). Normals come from the
        trilinearly interpolated grid gradient and point toward increasing value.
        Empty arrays are returned when the surface does not cross the grid.
    """
    empty = (
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 3), dtype=np.int64),
        np.zeros((0, 3), dtype=np.float64),
    )
    dims = tuple(volume.shape) if volume is not None else np.asarray(grid).shape
    if len(dims) != 3 or min(dims) < 2:
        return empty
    level = float(level)

    verts = None
    normals = None
    if volume is not None:
        from ..renderer import compute  # noqa: PLC0415

        scan = compute.marching_cubes_active(volume, level)
        if scan is not None:
            active, case_of_active = scan
            unique, faces = _triangle_edges(
                active, case_of_active,
                tuple(n - 1 for n in dims), dims, _EDGE_MAP, _TRI_TABLE,
            )
            if unique.size == 0:
                return empty
            placed = compute.isosurface_vertices(volume, unique, level)
            if placed is not None:
                verts, normals = placed

    if verts is None:
        # A device route that declined mid-chain leaves the host without a grid,
        # so read the volume back rather than crash on `None`. It is the slow
        # path twice over and it is also the only correct thing to do.
        if grid is None:
            grid = volume.read()
        # The grid is read in its own precision (the reference viewer's habit):
        # promoting a float32 map to float64 here doubled the memory traffic of
        # every full-grid pass. Only non-float grids are converted.
        g = np.asarray(grid)
        if g.dtype not in (np.float32, np.float64):
            g = g.astype(np.float32)
        g = np.ascontiguousarray(g)
        active, case_of_active = _cell_cases(g, level, _CORNERS)
        if active.size == 0:
            return empty
        unique, faces = _triangle_edges(
            active, case_of_active,
            tuple(n - 1 for n in dims), dims, _EDGE_MAP, _TRI_TABLE,
        )
        if unique.size == 0:
            return empty
        verts, lower, vaxis, mu = _place_vertices(g, level, unique, dims)
        # Vertex normals from the interpolated grid gradient (points
        # up-gradient), sampled only at the vertices rather than built as three
        # full-grid fields first. Each vertex lies on one grid edge, so the
        # trilinear sample reduces to the two end-node gradients lerped by mu.
        normals = _edge_normals(g, lower, vaxis, mu)

    if verts.shape[0] == 0:
        return empty

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


def _gradient_at_nodes(grid, nodes):
    """Sample the grid gradient at a set of grid nodes, by symmetric differences.

    Central differences over two steps at interior nodes, one-sided at the
    boundary — exactly what :func:`numpy.gradient` computes, evaluated only at
    the ``(m, 3)`` ``nodes`` instead of over the whole grid.
    """
    out = np.empty((nodes.shape[0], 3), dtype=np.float64)
    index = [nodes[:, 0], nodes[:, 1], nodes[:, 2]]
    for axis, limit in enumerate(grid.shape):
        hi = np.minimum(index[axis] + 1, limit - 1)
        lo = np.maximum(index[axis] - 1, 0)
        pick_hi = list(index)
        pick_lo = list(index)
        pick_hi[axis] = hi
        pick_lo[axis] = lo
        span = np.maximum(hi - lo, 1)
        out[:, axis] = (
            grid[tuple(pick_hi)].astype(np.float64) - grid[tuple(pick_lo)]
        ) / span
    return out


def _edge_normals(grid, lower, vaxis, mu):
    """Sample the grid gradient at each welded vertex, where the vertex is.

    A welded vertex sits on one grid edge, at fraction ``mu`` between the edge's
    two end nodes, with its other two coordinates integral — so the trilinear
    gradient sample the renderer needs reduces to the end-node gradients lerped
    along that one axis. This is the reference viewer's per-vertex normal, and
    it touches ~6 values per vertex where building full-grid gradient fields
    first touched every voxel three times.
    """
    upper = lower + _AXIS_STEP[vaxis]
    at_lower = _gradient_at_nodes(grid, lower)
    at_upper = _gradient_at_nodes(grid, upper)
    weight = mu[:, None]
    return at_lower * (1.0 - weight) + at_upper * weight


__all__ = ["marching_cubes"]
