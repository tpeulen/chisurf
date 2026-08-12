"""Surface refinement for map contours: subdivision and smoothing.

A marching-cubes isosurface of a real map is exact but not pretty: the
triangulation carries the grid's staircase, and on a noisy reconstruction the
per-vertex normals glitter. The reference viewer's answer is a pair of
rendering options applied to the contour after it is cut — ``subdivide_surface``
(each triangle into four, edge midpoints welded) and ``surface_smoothing``
(each vertex pulled toward the mean of its neighbours) — with defaults
``smoothing_factor 0.3``, ``smoothing_iterations 2``, ``subdivision_levels 1``.
Both are ported here as plain NumPy over ``(verts, faces, normals)``; the
algorithms are transcriptions of the reference's ``subdivide.cpp`` and
``smooth.cpp``, and the caller applies them in the reference's order:
subdivide, then any edge masking, then smoothing.
"""

from __future__ import annotations

import numpy as np

__all__ = ["smooth_vertex_positions", "subdivide_triangles"]


def subdivide_triangles(verts, faces, normals):
    """Divide each triangle into four by its welded edge midpoints.

    The reference's ``subdivide_triangles``: one new vertex per unique edge,
    so neighbouring triangles share their midpoint and the surface stays
    closed. Midpoint normals are the normalised average of the endpoints'.

    Returns
    -------
    tuple
        ``(verts, faces, normals)`` with ``len(faces)`` quadrupled.
    """
    verts = np.asarray(verts)
    faces = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    normals = np.asarray(normals)
    if faces.size == 0:
        return verts, faces, normals

    edges = np.sort(
        np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]),
        axis=1,
    )
    unique, inverse = np.unique(edges, axis=0, return_inverse=True)
    n_verts = verts.shape[0]

    midpoints = 0.5 * (verts[unique[:, 0]] + verts[unique[:, 1]])
    mid_normals = normals[unique[:, 0]] + normals[unique[:, 1]]
    length = np.linalg.norm(mid_normals, axis=1, keepdims=True)
    mid_normals = mid_normals / np.where(length > 1e-12, length, 1.0)

    n_faces = faces.shape[0]
    mid01 = n_verts + inverse[:n_faces]
    mid12 = n_verts + inverse[n_faces:2 * n_faces]
    mid20 = n_verts + inverse[2 * n_faces:]
    quarter = np.concatenate([
        np.stack([faces[:, 0], mid01, mid20], axis=1),
        np.stack([mid01, faces[:, 1], mid12], axis=1),
        np.stack([mid20, mid12, faces[:, 2]], axis=1),
        np.stack([mid01, mid12, mid20], axis=1),
    ])
    return (
        np.concatenate([verts, midpoints.astype(verts.dtype)]),
        quarter,
        np.concatenate([normals, mid_normals.astype(normals.dtype)]),
    )


def smooth_vertex_positions(verts, faces, factor: float = 0.3,
                            iterations: int = 2):
    """Pull each vertex toward the mean of its neighbours, ``iterations`` times.

    The reference's ``smooth_vertices``: per iteration every triangle adds
    each corner's two partners into that corner's neighbour sum (a vertex in
    ``k`` triangles therefore averages over ``2k`` entries, repeats included),
    and the vertex moves ``factor`` of the way to the average. It smooths the
    marching-cubes staircase and the noise-floor glitter without changing the
    triangulation; the same call smooths a normal array, which the caller
    should renormalise.

    Returns
    -------
    numpy.ndarray
        The smoothed copy; the input is not written.
    """
    moved = np.asarray(verts, dtype=np.float64).copy()
    faces = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if faces.size == 0 or iterations <= 0:
        return moved.astype(np.asarray(verts).dtype)

    n = moved.shape[0]
    i0, i1, i2 = faces[:, 0], faces[:, 1], faces[:, 2]
    counts = np.bincount(faces.reshape(-1), minlength=n) * 2
    safe = np.maximum(counts, 1).astype(np.float64)
    keep = 1.0 - float(factor)
    pull = float(factor)

    for _ in range(int(iterations)):
        total = np.zeros_like(moved)
        for axis in range(moved.shape[1]):
            component = moved[:, axis]
            total[:, axis] = (
                np.bincount(i0, weights=component[i1] + component[i2], minlength=n)
                + np.bincount(i1, weights=component[i0] + component[i2], minlength=n)
                + np.bincount(i2, weights=component[i0] + component[i1], minlength=n)
            )
        averaged = total / safe[:, None]
        touched = counts > 0
        moved[touched] = keep * moved[touched] + pull * averaged[touched]

    return moved.astype(np.asarray(verts).dtype)
