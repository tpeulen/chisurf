from __future__ import annotations

from typing import Optional

import numpy as np

try:  # Optional acceleration via numba
    import numba as nb  # type: ignore
    _HAVE_NUMBA = True
except Exception:  # pragma: no cover - run-time availability
    nb = None  # type: ignore
    _HAVE_NUMBA = False


if _HAVE_NUMBA and nb is not None:

    @nb.jit(nopython=True, nogil=True, cache=True)  # type: ignore[misc]
    def _build_bond_pairs_nb(pts: np.ndarray, max_length: float) -> np.ndarray:
        n = pts.shape[0]
        r2 = max_length * max_length
        if n < 2 or r2 <= 0.0:
            return np.zeros((0, 2), dtype=np.int64)

        count = 0
        for i in range(n - 1):
            x0 = pts[i, 0]
            y0 = pts[i, 1]
            z0 = pts[i, 2]
            for j in range(i + 1, n):
                dx = pts[j, 0] - x0
                dy = pts[j, 1] - y0
                dz = pts[j, 2] - z0
                if dx * dx + dy * dy + dz * dz <= r2:
                    count += 1

        if count == 0:
            return np.zeros((0, 2), dtype=np.int64)

        out = np.empty((count, 2), dtype=np.int64)
        k = 0
        for i in range(n - 1):
            x0 = pts[i, 0]
            y0 = pts[i, 1]
            z0 = pts[i, 2]
            for j in range(i + 1, n):
                dx = pts[j, 0] - x0
                dy = pts[j, 1] - y0
                dz = pts[j, 2] - z0
                if dx * dx + dy * dy + dz * dz <= r2:
                    out[k, 0] = i
                    out[k, 1] = j
                    k += 1

        return out


def _build_bond_pairs(coords: np.ndarray, max_length: float) -> np.ndarray:
    """Return an array of (i, j) index pairs for simple covalent bonds.

    Bonds are inferred purely from distance using a cutoff ``max_length`` in
    the *raw* coordinate frame. A simple grid-based neighbor search is used
    so the cost grows roughly linearly with the number of atoms. This is a
    lightweight approximation similar in spirit to pyball's stick geometry.
    """

    pts = np.asarray(coords, dtype=float)
    if pts.ndim != 2 or pts.shape[0] < 2:
        return np.zeros((0, 2), dtype=int)

    r = float(max_length)
    if not np.isfinite(r) or r <= 0.0:
        return np.zeros((0, 2), dtype=int)

    n = pts.shape[0]
    if _HAVE_NUMBA and nb is not None and n > 1:
        try:
            return _build_bond_pairs_nb(pts, r)  # type: ignore[name-defined]
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

    r2 = r * r
    bonds: list[tuple[int, int]] = []

    for i, key in enumerate(map(tuple, ijk)):
        ix, iy, iz = key
        cand_idx: list[int] = []
        for dx, dy, dz in neighbor_offsets:
            cand_idx.extend(grid.get((ix + dx, iy + dy, iz + dz), []))

        if not cand_idx:
            continue

        pi = pts[i]
        for j in cand_idx:
            if j <= i:
                continue
            d = pts[j] - pi
            if float(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]) <= r2:
                bonds.append((i, j))

    if not bonds:
        return np.zeros((0, 2), dtype=int)

    return np.asarray(bonds, dtype=int)


#: ``connect_cutoff`` in ``layer1/SettingInfo.h``: how far *beyond* the mean of two
#: van der Waals radii two atoms may sit and still be called bonded.
CONNECT_CUTOFF = 0.35

#: ``connect_cutoff_adjustment`` in ``layer2/ObjectMolecule2.cpp``. Sulfur reaches
#: further than the vdW mean suggests (a disulfide is 2.05 Å); hydrogen reaches
#: less far.
_SULFUR_ADJUSTMENT = 0.2
_HYDROGEN_ADJUSTMENT = -0.2

#: PyMOL's ``R_SMALL4``: below this two atoms are coincident, not bonded.
_R_SMALL4 = 0.0001


def build_bond_pairs_by_element(
    coords: np.ndarray,
    radii: np.ndarray,
    elements: np.ndarray,
    *,
    cutoff: float = CONNECT_CUTOFF,
) -> np.ndarray:
    """Infer bonds the way PyMOL does: from radii, not from one global distance.

    Transcribed from ``is_distance_bonded`` (``layer2/ObjectMolecule2.cpp``)::

        d = |v1 - v2|
        d -= (vdw1 + vdw2) / 2
        bonded  iff  d <= cutoff + adjustment(a1, a2)

    with ``+0.2`` when either atom is sulfur and ``-0.2`` when either is
    hydrogen, and no bond between two hydrogens.

    Why this matters more than it looks: a single global cutoff has to be wide
    enough for the longest real bond, which makes it wide enough for a *contact*
    between two heavier atoms. That produces bonds that are not there, and every
    bond-based selection inherits them — ``bymol`` merges molecules that merely
    touch, ``bound_to`` and ``extend`` walk across the join, and the wireframe
    draws a stick through empty space.

    Parameters
    ----------
    coords : numpy.ndarray
        ``(n, 3)`` positions in Angstrom.
    radii : numpy.ndarray
        ``(n,)`` van der Waals radii.
    elements : numpy.ndarray
        ``(n,)`` element symbols, for the sulfur and hydrogen adjustments.
    cutoff : float, optional
        PyMOL's ``connect_cutoff``.

    Returns
    -------
    numpy.ndarray
        ``(m, 2)`` index pairs, ``i < j``.
    """
    pts = np.asarray(coords, dtype=float)
    if pts.ndim != 2 or pts.shape[0] < 2:
        return np.zeros((0, 2), dtype=int)

    vdw = np.asarray(radii, dtype=float)
    symbols = np.char.upper(np.char.strip(np.asarray(elements).astype(str)))
    is_hydrogen = np.isin(symbols, ("H", "D"))
    is_sulfur = symbols == "S"

    # The widest any pair may span, used to size the neighbour search.
    reach = float(vdw.max()) + float(cutoff) + _SULFUR_ADJUSTMENT
    candidates = _build_bond_pairs(pts, reach)
    if candidates.shape[0] == 0:
        return candidates

    first, second = candidates[:, 0], candidates[:, 1]
    separation = np.linalg.norm(pts[second] - pts[first], axis=1)
    # `if (dst < R_SMALL4) return false` -- two atoms at the same place are a
    # duplicate record, not a bond, and without this they are the *shortest*
    # distance of all and so always pass.
    coincident = separation < _R_SMALL4
    distance = separation - (vdw[first] + vdw[second]) / 2.0

    limit = np.full(distance.shape, float(cutoff))
    limit[is_sulfur[first] | is_sulfur[second]] += _SULFUR_ADJUSTMENT
    # Hydrogen wins over sulfur, matching the order of the C++ branches.
    hydrogen_pair = is_hydrogen[first] | is_hydrogen[second]
    limit[hydrogen_pair] = float(cutoff) + _HYDROGEN_ADJUSTMENT

    keep = (
        (distance <= limit)
        & ~coincident
        & ~(is_hydrogen[first] & is_hydrogen[second])
    )
    return candidates[keep]


__all__ = ["_build_bond_pairs", "build_bond_pairs_by_element", "CONNECT_CUTOFF"]

