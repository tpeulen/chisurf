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

__all__ = [
    "valence_offsets","bond_line_segments", "nonbonded_crosses", "unbonded_mask"]


def valence_offsets(
    coords: np.ndarray,
    bonds: np.ndarray,
    orders: np.ndarray,
    *,
    size: float = 0.06,
) -> np.ndarray | None:
    """Where the second line of a double bond goes, per bond.

    PyMOL's ``valence_mode 1``: the extra line sits **beside** the bond rather
    than replacing it, offset perpendicular to it and *towards the rest of the
    molecule* -- which puts it inside a ring, where it reads as a Kekule
    structure rather than as two parallel rails. ``valence_size`` (0.06) scales
    the offset with the bond, so it is the same fraction of every bond's length
    however long it is.

    The direction comes from the two atoms' other neighbours: their mean, made
    perpendicular to the bond. A bond whose atoms have no other neighbour --
    a diatomic, or a fragment -- has no plane to choose, and any perpendicular
    is as good as another; one is picked from whichever axis is least aligned
    with the bond, so the line is never drawn on top of the bond it doubles.

    Parameters
    ----------
    coords : numpy.ndarray
        ``(N, 3)`` atom positions.
    bonds : numpy.ndarray
        ``(B, 2)`` atom index pairs.
    orders : numpy.ndarray
        ``(B,)`` bond orders; only ``>= 2`` is offset.
    size : float, optional
        ``valence_size``, as a fraction of the bond length.

    Returns
    -------
    numpy.ndarray or None
        ``(B, 3)`` offsets, zero where the bond is single. ``None`` when no
        bond is double, so a caller can skip the work entirely.
    """
    pts = np.asarray(coords, dtype=float)
    pairs = np.asarray(bonds, dtype=int)
    order_arr = np.asarray(orders, dtype=int).reshape(-1)
    if pairs.ndim != 2 or pairs.shape[0] == 0 or order_arr.shape[0] != pairs.shape[0]:
        return None
    double = order_arr >= 2
    if not double.any():
        return None

    # Mean position of everything each atom is bonded to, which is the cheapest
    # stand-in for "the side the rest of the molecule is on".
    sums = np.zeros_like(pts)
    counts = np.zeros(pts.shape[0], dtype=float)
    np.add.at(sums, pairs[:, 0], pts[pairs[:, 1]])
    np.add.at(sums, pairs[:, 1], pts[pairs[:, 0]])
    np.add.at(counts, pairs[:, 0], 1.0)
    np.add.at(counts, pairs[:, 1], 1.0)
    neighbourhood = np.divide(
        sums, np.maximum(counts, 1.0)[:, None],
        out=np.zeros_like(sums), where=counts[:, None] > 0,
    )

    a = pts[pairs[:, 0]]
    b = pts[pairs[:, 1]]
    axis = b - a
    length = np.linalg.norm(axis, axis=1)
    unit = np.divide(
        axis, np.maximum(length, 1e-9)[:, None],
        out=np.zeros_like(axis), where=length[:, None] > 1e-9,
    )

    towards = 0.5 * (
        neighbourhood[pairs[:, 0]] + neighbourhood[pairs[:, 1]]
    ) - 0.5 * (a + b)
    # Perpendicular component only; the parallel part would slide the line
    # along the bond instead of beside it.
    towards = towards - unit * np.sum(towards * unit, axis=1)[:, None]

    norm = np.linalg.norm(towards, axis=1)
    weak = norm < 1e-6
    if weak.any():
        # No plane to choose from. Any perpendicular will do, so take the axis
        # the bond is least aligned with and remove the parallel part of it.
        fallback = np.zeros((int(weak.sum()), 3))
        fallback[np.arange(len(fallback)), np.argmin(np.abs(unit[weak]), axis=1)] = 1.0
        fallback = fallback - unit[weak] * np.sum(
            fallback * unit[weak], axis=1
        )[:, None]
        towards[weak] = fallback
        norm = np.linalg.norm(towards, axis=1)

    direction = np.divide(
        towards, np.maximum(norm, 1e-9)[:, None],
        out=np.zeros_like(towards), where=norm[:, None] > 1e-9,
    )
    offsets = direction * (float(size) * length)[:, None]
    offsets[~double] = 0.0
    return offsets


def bond_line_segments(
    coords: np.ndarray,
    bonds: np.ndarray,
    colors: np.ndarray | None = None,
    *,
    split_at_midpoint: bool = True,
    orders: np.ndarray | None = None,
    valence_size: float = 0.06,
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
    orders : numpy.ndarray, optional
        ``(B,)`` bond orders. When given, every bond of order 2 or more gets a
        second line beside it -- PyMOL's ``valence``. Omit it (the default) and
        the wireframe is drawn single-bonded, which is what PyMOL does with
        ``valence`` off.
    valence_size : float, optional
        How far beside, as a fraction of the bond length. PyMOL's
        ``valence_size``.

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

    offsets = None
    if orders is not None:
        kept = np.asarray(orders, dtype=int).reshape(-1)
        if kept.shape[0] == valid.shape[0]:
            kept = kept[valid]
        if kept.shape[0] == pairs.shape[0]:
            offsets = valence_offsets(pts, pairs, kept, size=valence_size)

    if not split_at_midpoint:
        vertices = np.empty((pairs.shape[0] * 2, 3), dtype=float)
        vertices[0::2] = a
        vertices[1::2] = b
        out = None
        if col is not None:
            out = np.empty((pairs.shape[0] * 2, col.shape[1]), dtype=float)
            out[0::2] = col[pairs[:, 0]]
            out[1::2] = col[pairs[:, 1]]
        return _with_valence(vertices, out, a, b, offsets, split=False)

    mid = 0.5 * (a + b)
    # Two segments per bond: a->mid and mid->b, so each half is one atom's colour.
    vertices = np.empty((pairs.shape[0] * 4, 3), dtype=float)
    vertices[0::4] = a
    vertices[1::4] = mid
    vertices[2::4] = mid
    vertices[3::4] = b
    if col is None:
        return _with_valence(vertices, None, a, b, offsets, split=True)

    out = np.empty((pairs.shape[0] * 4, col.shape[1]), dtype=float)
    first = col[pairs[:, 0]]
    second = col[pairs[:, 1]]
    out[0::4] = first
    out[1::4] = first
    out[2::4] = second
    out[3::4] = second
    return _with_valence(vertices, out, a, b, offsets, split=True)


def _with_valence(vertices, colours, a, b, offsets, *, split: bool):
    """Append the second line of every double bond to a finished wireframe.

    Appended rather than interleaved: the extra lines are a *subset* of the
    bonds, so they cannot share the regular stride, and a GL_LINES draw does
    not care what order its segments arrive in.
    """
    if offsets is None:
        return vertices, colours
    double = np.any(np.abs(offsets) > 1e-12, axis=1)
    if not double.any():
        return vertices, colours

    off = offsets[double]
    start = a[double] + off
    end = b[double] + off
    if split:
        mid = 0.5 * (start + end)
        extra = np.empty((int(double.sum()) * 4, 3), dtype=float)
        extra[0::4] = start
        extra[1::4] = mid
        extra[2::4] = mid
        extra[3::4] = end
    else:
        extra = np.empty((int(double.sum()) * 2, 3), dtype=float)
        extra[0::2] = start
        extra[1::2] = end

    vertices = np.concatenate([vertices, extra])
    if colours is None:
        return vertices, None

    stride = 4 if split else 2
    repeat = np.repeat(np.nonzero(double)[0], stride)
    per_vertex = colours.reshape(-1, stride, colours.shape[1])[repeat[::stride]]
    return vertices, np.concatenate([colours, per_vertex.reshape(-1, colours.shape[1])])


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
