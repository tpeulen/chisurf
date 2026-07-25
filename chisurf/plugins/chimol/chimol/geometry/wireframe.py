"""PyMOL's ``lines`` and ``nonbonded`` representations.

These are the two PyMOL shows by **default** on load (``auto_show_lines`` and
``auto_show_nonbonded``), and chimol had neither. What it called ``lines`` was the
alpha-carbon trace, which is a different thing entirely — a PyMOL user typing
``show lines`` expects to see every bond, not a smoothed backbone.

Both are cheap, flat-shaded primitives rather than meshes, which is the point of
them: they are what you turn on when a surface or a cartoon is too heavy to
rotate, and they show the actual atoms rather than an interpretation of them.

* ``lines`` (``RepWireBond``) draws one segment per bond, **split at the
  midpoint** so each half takes its own atom's colour. A bond between a red and a
  blue atom is half red and half blue, which is how you read element identity off
  a wireframe at a glance.
* ``nonbonded`` (``RepNonbonded``) marks atoms that have no bonds at all — waters,
  ions, unlinked ligands — with a small three-axis cross, since a lone atom draws
  no line and would otherwise be invisible.
"""

from __future__ import annotations

import numpy as np

__all__ = ["bond_line_segments", "nonbonded_crosses", "unbonded_mask"]


def bond_line_segments(
    coords: np.ndarray,
    bonds: np.ndarray,
    colors: np.ndarray | None = None,
    *,
    split_at_midpoint: bool = True,
) -> tuple[np.ndarray, np.ndarray | None]:
    """Line segments for a wireframe over ``bonds``.

    Parameters
    ----------
    coords : numpy.ndarray
        ``(N, 3)`` atom positions.
    bonds : numpy.ndarray
        ``(B, 2)`` atom index pairs.
    colors : numpy.ndarray, optional
        ``(N, 4)`` per-atom RGBA.
    split_at_midpoint : bool, optional
        Draw each bond as two half-segments so both atoms contribute their own
        colour, as PyMOL does. With one colour per bond the wireframe reads much
        less clearly, so this is on by default.

    Returns
    -------
    tuple
        ``(vertices, colors)`` laid out as consecutive segment endpoint pairs,
        ready for a ``GL_LINES`` draw. Empty arrays when there is nothing to draw.
    """
    pts = np.asarray(coords, dtype=float)
    pairs = np.asarray(bonds, dtype=int)
    if pts.ndim != 2 or pts.shape[1] != 3 or pairs.ndim != 2 or pairs.shape[1] != 2:
        return np.zeros((0, 3)), None
    if pairs.shape[0] == 0:
        return np.zeros((0, 3)), None

    valid = (
        (pairs[:, 0] >= 0)
        & (pairs[:, 1] >= 0)
        & (pairs[:, 0] < pts.shape[0])
        & (pairs[:, 1] < pts.shape[0])
        & (pairs[:, 0] != pairs[:, 1])
    )
    pairs = pairs[valid]
    if pairs.shape[0] == 0:
        return np.zeros((0, 3)), None

    a = pts[pairs[:, 0]]
    b = pts[pairs[:, 1]]

    col = None
    if colors is not None:
        col_arr = np.asarray(colors, dtype=float)
        if col_arr.ndim == 2 and col_arr.shape[0] == pts.shape[0]:
            col = col_arr

    if not split_at_midpoint:
        vertices = np.empty((pairs.shape[0] * 2, 3), dtype=float)
        vertices[0::2] = a
        vertices[1::2] = b
        if col is None:
            return vertices, None
        out = np.empty((pairs.shape[0] * 2, col.shape[1]), dtype=float)
        out[0::2] = col[pairs[:, 0]]
        out[1::2] = col[pairs[:, 1]]
        return vertices, out

    mid = 0.5 * (a + b)
    # Two segments per bond: a->mid and mid->b, so each half is one atom's colour.
    vertices = np.empty((pairs.shape[0] * 4, 3), dtype=float)
    vertices[0::4] = a
    vertices[1::4] = mid
    vertices[2::4] = mid
    vertices[3::4] = b
    if col is None:
        return vertices, None

    out = np.empty((pairs.shape[0] * 4, col.shape[1]), dtype=float)
    first = col[pairs[:, 0]]
    second = col[pairs[:, 1]]
    out[0::4] = first
    out[1::4] = first
    out[2::4] = second
    out[3::4] = second
    return vertices, out


def unbonded_mask(n_atoms: int, bonds: np.ndarray | None) -> np.ndarray:
    """Atoms that appear in no bond, which is PyMOL's ``nonbonded`` set.

    Parameters
    ----------
    n_atoms : int
        Total atom count.
    bonds : numpy.ndarray or None
        ``(B, 2)`` bond pairs; ``None`` means nothing is bonded.

    Returns
    -------
    numpy.ndarray
        Boolean mask of length ``n_atoms``.
    """
    mask = np.ones(max(int(n_atoms), 0), dtype=bool)
    if mask.size == 0 or bonds is None:
        return mask
    pairs = np.asarray(bonds, dtype=int).reshape(-1)
    pairs = pairs[(pairs >= 0) & (pairs < mask.size)]
    mask[pairs] = False
    return mask


def nonbonded_crosses(
    coords: np.ndarray,
    colors: np.ndarray | None = None,
    *,
    size: float = 0.25,
) -> tuple[np.ndarray, np.ndarray | None]:
    """Three-axis crosses marking atoms that draw no bond line.

    A lone atom contributes no wireframe segment, so without this waters and ions
    vanish from a ``lines`` view entirely — which is why PyMOL turns
    ``auto_show_nonbonded`` on alongside ``auto_show_lines``.

    Parameters
    ----------
    coords : numpy.ndarray
        ``(M, 3)`` positions of the unbonded atoms.
    colors : numpy.ndarray, optional
        ``(M, 4)`` RGBA per atom.
    size : float, optional
        Half-length of each arm, in the same units as ``coords``
        (``nonbonded_size``).

    Returns
    -------
    tuple
        ``(vertices, colors)`` as consecutive endpoint pairs for ``GL_LINES``:
        three segments per atom.
    """
    pts = np.asarray(coords, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 3 or pts.shape[0] == 0 or size <= 0.0:
        return np.zeros((0, 3)), None

    m = pts.shape[0]
    offsets = np.array(
        [
            [-size, 0.0, 0.0], [size, 0.0, 0.0],
            [0.0, -size, 0.0], [0.0, size, 0.0],
            [0.0, 0.0, -size], [0.0, 0.0, size],
        ]
    )
    vertices = (pts[:, None, :] + offsets[None, :, :]).reshape(-1, 3)

    if colors is None:
        return vertices, None
    col = np.asarray(colors, dtype=float)
    if col.ndim != 2 or col.shape[0] != m:
        return vertices, None
    return vertices, np.repeat(col, 6, axis=0)
