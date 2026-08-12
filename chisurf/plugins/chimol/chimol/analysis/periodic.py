"""Making a molecule whole across a periodic wall, and putting it back.

A simulation writes coordinates *wrapped* into the box: an atom that leaves one
face re-enters the opposite one. That is correct bookkeeping and a broken
picture -- a protein sitting on a wall is drawn in two pieces at opposite edges
of the scene, and its radius of gyration, its centre and every distance measured
across the seam are wrong by a box length.

Two operations fix it, and they are opposites:

**unwrap** makes each molecule whole. Bonded neighbours are placed at the image
nearest each other, so a fragment straddling a wall is pulled back together --
and may then stick out of the box, which is the point.

**wrap** puts each molecule back inside, moving it *as a unit* so it stays
whole. Wrapping per atom is what produced the split picture in the first place.

Both work on **fragments**, not atoms: connected components of the bond graph,
falling back to chains and then to residues where a structure has no bonds. That
is the whole reason this is not two lines -- a molecule is only whole if every
atom in it is imaged against its own neighbours rather than against the origin.
"""
from __future__ import annotations

import numpy as np

__all__ = ["cell_matrix", "fragments", "unwrap_coordinates", "wrap_coordinates"]


def cell_matrix(lengths, angles):
    """The 3x3 cell matrix, rows being the cell vectors ``a``, ``b``, ``c``.

    The conventional crystallographic setting: ``a`` along x, ``b`` in the xy
    plane, ``c`` completing it.

    Returns
    -------
    numpy.ndarray or None
        ``None`` for a degenerate cell -- zero edges, or angles that describe
        no volume -- which must not raise from a render path.
    """
    try:
        a, b, c = (float(x) for x in np.asarray(lengths, dtype=float).reshape(3))
        alpha, beta, gamma = (
            np.radians(float(x)) for x in np.asarray(angles, dtype=float).reshape(3)
        )
    except Exception:  # noqa: BLE001
        return None
    if not (a > 0.0 and b > 0.0 and c > 0.0):
        return None

    cos_a, cos_b, cos_g = np.cos(alpha), np.cos(beta), np.cos(gamma)
    sin_g = np.sin(gamma)
    if abs(sin_g) < 1e-9:
        return None
    cx = c * cos_b
    cy = c * (cos_a - cos_b * cos_g) / sin_g
    squared = c * c - cx * cx - cy * cy
    if squared <= 0.0:
        return None
    return np.array(
        [
            [a, 0.0, 0.0],
            [b * cos_g, b * sin_g, 0.0],
            [cx, cy, float(np.sqrt(squared))],
        ],
        dtype=float,
    )


def fragments(n_atoms: int, bonds=None, chains=None, res_ids=None) -> list[np.ndarray]:
    """Group atom indices into the pieces that must move together.

    Parameters
    ----------
    n_atoms : int
    bonds : array_like, optional
        ``(k, 2)`` bonded pairs. The best answer when present.
    chains, res_ids : array_like, optional
        Fallbacks, in that order, for a structure with no bonds -- a bead model,
        a coarse-grained trace. A chain is a better guess than a residue because
        a residue-wise wrap would tear a polymer at every peptide bond.

    Returns
    -------
    list of numpy.ndarray
        Index arrays covering every atom exactly once.
    """
    if n_atoms <= 0:
        return []

    if bonds is not None and len(bonds):
        pairs = np.asarray(bonds, dtype=np.int64).reshape(-1, 2)
        pairs = pairs[
            (pairs[:, 0] >= 0) & (pairs[:, 1] >= 0)
            & (pairs[:, 0] < n_atoms) & (pairs[:, 1] < n_atoms)
        ]
        if len(pairs):
            # Union-find, iterative: a recursive flood fill over a protein's
            # bond graph is deep enough to hit the recursion limit.
            parent = np.arange(n_atoms, dtype=np.int64)

            def find(index: int) -> int:
                root = index
                while parent[root] != root:
                    root = parent[root]
                while parent[index] != root:  # path compression
                    parent[index], index = root, parent[index]
                return root

            for left, right in pairs:
                a, b = find(int(left)), find(int(right))
                if a != b:
                    parent[a] = b
            roots = np.array([find(i) for i in range(n_atoms)], dtype=np.int64)
            order = np.argsort(roots, kind="stable")
            grouped = np.split(order, np.flatnonzero(np.diff(roots[order])) + 1)
            return [np.sort(g) for g in grouped if g.size]

    for labels in (chains, res_ids):
        if labels is None:
            continue
        values = np.asarray(labels)
        if values.shape[0] != n_atoms:
            continue
        order = np.argsort(values, kind="stable")
        cuts = np.flatnonzero(values[order][1:] != values[order][:-1]) + 1
        grouped = np.split(order, cuts)
        return [np.sort(g) for g in grouped if g.size]

    return [np.arange(n_atoms, dtype=np.int64)]


def unwrap_coordinates(coords, matrix, groups) -> np.ndarray:
    """Make each fragment whole, imaging every atom against its own group.

    Parameters
    ----------
    coords : array_like
        ``(n, 3)``.
    matrix : array_like
        The cell matrix from :func:`cell_matrix`.
    groups : sequence of array_like
        Fragments from :func:`fragments`.

    Returns
    -------
    numpy.ndarray
        A new array; *coords* is not modified.

    Notes
    -----
    Each fragment is imaged against **its own first atom**, not against the
    box centre or the origin. That is what makes a molecule sitting on a wall
    come back whole rather than being folded to wherever the origin happens to
    be: the seed is inside one piece, and every other atom follows it.

    This is an approximation, and a good one for the case that matters. A truly
    correct unwrap walks the bond graph so each atom is imaged against a
    *bonded* neighbour, which also handles a fragment longer than half the box.
    Seeding from one atom fails only for a fragment that spans more than half
    the cell -- a polymer threaded through the whole box -- and such a fragment
    has no unambiguous unwrapping anyway.
    """
    points = np.array(coords, dtype=float, copy=True)
    if points.ndim != 2 or points.shape[1] != 3:
        return points
    cell = np.asarray(matrix, dtype=float)
    try:
        inverse = np.linalg.inv(cell)
    except np.linalg.LinAlgError:
        return points

    for group in groups:
        index = np.asarray(group, dtype=np.int64)
        if index.size < 2:
            continue
        block = points[index]
        delta = block - block[0]
        shift = np.round(delta @ inverse) @ cell
        points[index] = block - shift
    return points


def wrap_coordinates(coords, matrix, groups) -> np.ndarray:
    """Move each fragment, as a unit, so its centre lies inside the box.

    The counterpart of :func:`unwrap_coordinates`. Moving *whole fragments* is
    the point: wrapping atom by atom is what splits a molecule across the
    picture in the first place.
    """
    points = np.array(coords, dtype=float, copy=True)
    if points.ndim != 2 or points.shape[1] != 3:
        return points
    cell = np.asarray(matrix, dtype=float)
    try:
        inverse = np.linalg.inv(cell)
    except np.linalg.LinAlgError:
        return points

    for group in groups:
        index = np.asarray(group, dtype=np.int64)
        if index.size == 0:
            continue
        block = points[index]
        centre_fractional = (block.mean(axis=0)) @ inverse
        shift = np.floor(centre_fractional) @ cell
        points[index] = block - shift
    return points
