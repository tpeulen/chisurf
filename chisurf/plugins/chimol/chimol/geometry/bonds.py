from __future__ import annotations

import numpy as np

from .neighbors import self_pairs_within


def _build_bond_pairs(coords: np.ndarray, max_length: float) -> np.ndarray:
    """Return an array of (i, j) index pairs for simple covalent bonds.

    Bonds are inferred purely from distance using a cutoff ``max_length`` in
    the *raw* coordinate frame.

    Parameters
    ----------
    coords : numpy.ndarray
        ``(n, 3)`` positions.
    max_length : float
        Inclusive distance cutoff.

    Returns
    -------
    numpy.ndarray
        ``(m, 2)`` index pairs with ``i < j``, ordered by ``i`` then ``j``.

    Notes
    -----
    This used to be an O(n²) numba double loop that ran *twice* — once to count
    the pairs and once to fill them. The neighbour query behind it is a k-d
    tree, so the cost is now output-sensitive: a 100k-atom structure no longer
    evaluates 5×10⁹ distances to find its ~10⁵ bonds.
    """
    pts = np.asarray(coords, dtype=float)
    if pts.ndim != 2 or pts.shape[0] < 2:
        return np.zeros((0, 2), dtype=int)

    r = float(max_length)
    if not np.isfinite(r) or r <= 0.0:
        return np.zeros((0, 2), dtype=int)

    return self_pairs_within(pts, r)


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

