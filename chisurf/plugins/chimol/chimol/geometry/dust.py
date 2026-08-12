"""Hide Dust: drop the small disconnected crumbs of a map contour.

A contour of a real map is never one surface: around the level worth looking
at, the noise floor crosses the threshold in thousands of places and each
crossing becomes a tiny disconnected blob — *dust*. It hides the structure it
surrounds, and lowering the level to see more of the molecule produces more of
it, which is the trap the tool exists to break.

This is the reference viewer's **Hide Dust** (its ``surface dust``): find the
connected pieces of the triangulation, measure each one, and hide every piece
smaller than a threshold. The default metric is the reference's — ``size``,
the largest extent of the piece's bounding box, in the same units the map is
placed in — because a blob's triangle count depends on the grid step while its
physical size does not.
"""

from __future__ import annotations

import numpy as np

__all__ = ["connected_components", "dust_faces"]


def connected_components(faces, n_vertices: int) -> np.ndarray:
    """Label each vertex with its connected component.

    Plain NumPy (the engine has no graph library): minimum-label propagation
    over the triangle edges with pointer jumping, which converges in a few
    sweeps rather than one per mesh diameter.

    Returns
    -------
    numpy.ndarray
        ``(n_vertices,)`` labels; vertices in no triangle keep a label of
        their own index.
    """
    labels = np.arange(int(n_vertices), dtype=np.int64)
    faces = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if faces.size == 0:
        return labels
    e0 = np.concatenate([faces[:, 0], faces[:, 1], faces[:, 2]])
    e1 = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 0]])
    while True:
        before = labels
        low = np.minimum(labels[e0], labels[e1])
        labels = labels.copy()
        np.minimum.at(labels, e0, low)
        np.minimum.at(labels, e1, low)
        while True:
            jump = labels[labels]
            if np.array_equal(jump, labels):
                break
            labels = jump
        if np.array_equal(labels, before):
            return labels


def dust_faces(verts, faces, min_size: float) -> tuple[np.ndarray, int]:
    """Return the triangles surviving Hide Dust, and how many pieces hid.

    Parameters
    ----------
    verts : numpy.ndarray
        ``(n, 3)`` vertex positions, in the units ``min_size`` is given in.
    faces : numpy.ndarray
        ``(m, 3)`` triangle indices.
    min_size : float
        A connected piece survives when the largest extent of its bounding
        box is at least this — the reference viewer's default ``size`` metric.

    Returns
    -------
    tuple
        ``(faces_kept, pieces_hidden)``.
    """
    verts = np.asarray(verts)
    faces = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if faces.size == 0 or min_size <= 0:
        return faces, 0

    labels = connected_components(faces, verts.shape[0])
    used = np.zeros(verts.shape[0], dtype=bool)
    used[faces.reshape(-1)] = True

    # Per-component bounding box, taken only over vertices that are in the
    # surface at all -- an orphan vertex would otherwise stretch nothing.
    n = verts.shape[0]
    low = np.full((n, 3), np.inf)
    high = np.full((n, 3), -np.inf)
    for axis in range(3):
        component = labels[used]
        np.minimum.at(low[:, axis], component, verts[used, axis])
        np.maximum.at(high[:, axis], component, verts[used, axis])
    extent = np.where(np.isfinite(high - low), high - low, 0.0).max(axis=1)

    keep_component = extent >= float(min_size)
    keep_face = keep_component[labels[faces[:, 0]]]
    hidden = int(np.unique(labels[used])[
        ~keep_component[np.unique(labels[used])]
    ].size)
    return faces[keep_face], hidden
