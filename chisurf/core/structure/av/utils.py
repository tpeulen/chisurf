import numpy as np


def atoms_in_reach(xyz, vdw, dmaxsq, atom_i):
    """Return the xyz coordinates of atoms within reach (defined by dmaxsq) of a list of atoms

    Parameters
    ----------
    xyz : ndarray
        Coordinates of atoms
    vdw : ndarray
        Van der Waals radii of atoms
    dmaxsq : float
        Maximum squared distance
    atom_i : int
        Attachment atom index

    Returns
    -------
    ra : ndarray
        Coordinates of atoms within reach
    vdwr : ndarray
        Van der Waals radii of atoms within reach

    Notes
    -----
    The squared distance is summed over the coordinate axis rather than
    accumulated in a scalar, so the comparison against ``dmaxsq`` is the same
    arithmetic in the same order as the per-atom loop this replaces. Boolean
    indexing keeps the atoms in index order, which the callers rely on.
    """
    xyz = np.asarray(xyz, dtype=np.float64)
    dsq = ((xyz - xyz[atom_i]) ** 2.0).sum(axis=1)
    in_reach = dsq < dmaxsq
    in_reach[atom_i] = False
    return xyz[in_reach], np.asarray(vdw, dtype=np.float64)[in_reach]
