"""What a *bead* is, in one place.

A coarse-grained model does not have atoms. It has beads: spheres that each
stand for a stretch of sequence, with a radius that says how much of it. Two
readers produce them -- the integrative-mmCIF reader from
``_ihm_sphere_obj_site``, and the RMF reader from IMP's particles -- and
everything downstream has to be able to tell a bead from an atom, because a
bead model must never be splined into a cartoon and a 200,000-bead model must
never be drawn as 200,000 meshes.

That test is a string comparison against one residue name, which is a fragile
thing to have written down in four places. It *was* written down in four
places: twice in the mmCIF reader's row construction and twice in the renderer.
The RMF reader, which had its own private route into the viewer, did not write
it down at all -- and so an RMF model was never recognised as beads, drew every
particle at one default radius, ignored the hierarchy's visibility check boxes,
and got silently decimated to a fraction of its particles.

So the definition lives here, once, and both readers call it.

Notes
-----
Beads are given the atom name ``CA`` deliberately. Every per-atom path
downstream wants a row per coordinate, and the trace/cartoon machinery looks
for alpha carbons to follow a chain -- naming them ``CA`` is what lets a chain
of beads be followed at all, while the ``BEA`` residue name is what stops it
being mistaken for real backbone and given secondary structure.
"""
from __future__ import annotations

import numpy as np

__all__ = [
    "ATOM_DTYPE",
    "BEAD_ATOM_NAME",
    "BEAD_ELEMENT",
    "BEAD_RES_NAME",
    "bead_mask",
    "bead_row",
    "make_bead_rows",
]

#: The structured per-atom array every non-trajectory reader produces. Note
#: that :mod:`chimol.io.structure` also defines a wider MDTraj-specific dtype
#: for trajectory topologies; the two have never been reconciled, and consumers
#: guard on ``atoms.dtype.fields`` rather than assuming either.
ATOM_DTYPE = np.dtype([
    ("atom_name", "U4"),
    ("res_name", "U4"),
    ("chain", "U2"),
    ("res_id", np.int64),
    ("element", "U2"),
    ("xyz", float, (3,)),
])

#: Named so the trace and cartoon machinery can follow a chain of beads.
BEAD_ATOM_NAME = "CA"
#: The residue name that marks a row as a bead rather than an atom. This single
#: string is the whole classification; see :func:`bead_mask`.
BEAD_RES_NAME = "BEA"
#: Beads have no element. Carbon is the harmless answer for the colour-by-element
#: and radius tables, which would otherwise fall through to an unknown-element
#: default that differs between them.
BEAD_ELEMENT = "C"


def bead_row(chain: str, res_id: int, xyz) -> tuple:
    """Build one bead row, for a reader that appends rows as it walks a file.

    Parameters
    ----------
    chain : str
        Chain (or asym-unit) identifier the bead belongs to.
    res_id : int
        Residue number. For a bead spanning a range, the first residue of it --
        the range's start is what identifies the bead in the file.
    xyz : tuple of float
        Cartesian coordinates.

    Returns
    -------
    tuple
        A row in :data:`ATOM_DTYPE` order.
    """
    return (BEAD_ATOM_NAME, BEAD_RES_NAME, str(chain), int(res_id), BEAD_ELEMENT, xyz)


def make_bead_rows(xyz, *, chain_ids=None, res_ids=None) -> np.ndarray:
    """Build a whole structured array of beads at once.

    The vectorised counterpart of :func:`bead_row`, for a reader that already
    has its particles in arrays. An integrative model has hundreds of thousands
    of beads, and building that row by row in Python costs more than reading the
    file did.

    Parameters
    ----------
    xyz : array_like
        ``(N, 3)`` coordinates.
    chain_ids : sequence of str, optional
        Per-bead chain identifier. Empty strings when not given, which leaves
        the whole model in one unnamed chain.
    res_ids : sequence of int, optional
        Per-bead residue number. ``1..N`` when not given, so that every bead
        still has a distinct residue identity -- the trace breaks on repeated
        ``(chain, res_id)`` pairs, and giving every bead the same one collapses
        the model to a single point.

    Returns
    -------
    numpy.ndarray
        Structured array of :data:`ATOM_DTYPE`, length ``N``.

    Raises
    ------
    ValueError
        If ``xyz`` is not ``(N, 3)``, or a supplied metadata array does not
        match its length.
    """
    coords = np.asarray(xyz, dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 3:
        raise ValueError("xyz must have shape (N, 3)")
    n = int(coords.shape[0])

    rows = np.zeros(n, dtype=ATOM_DTYPE)
    rows["atom_name"] = BEAD_ATOM_NAME
    rows["res_name"] = BEAD_RES_NAME
    rows["element"] = BEAD_ELEMENT
    rows["xyz"] = coords

    if chain_ids is not None:
        chains = np.asarray(chain_ids, dtype=str)
        if chains.shape[0] != n:
            raise ValueError(
                f"chain_ids has {chains.shape[0]} entries for {n} beads"
            )
        rows["chain"] = chains

    if res_ids is None:
        rows["res_id"] = np.arange(1, n + 1, dtype=np.int64)
    else:
        numbers = np.asarray(res_ids, dtype=np.int64)
        if numbers.shape[0] != n:
            raise ValueError(
                f"res_ids has {numbers.shape[0]} entries for {n} beads"
            )
        rows["res_id"] = numbers

    return rows


def bead_mask(res_names) -> np.ndarray | None:
    """Which of these rows are beads.

    Classification is **per row over the whole array**, never a sample of it: a
    reader writes every atomic row before every sphere, so looking at the first
    row (or the last) answers for one end of a hybrid model and is wrong about
    the other. A model can legitimately be part atomic and part coarse-grained,
    and both halves have to be drawn as what they are.

    Parameters
    ----------
    res_names : array_like or None
        The ``res_name`` column, or anything array-like of names.

    Returns
    -------
    numpy.ndarray or None
        Boolean mask of the same length, or ``None`` when there is nothing to
        classify.
    """
    if res_names is None:
        return None
    names = np.asarray(res_names)
    if names.size == 0:
        return None
    return np.char.strip(names.astype(str)) == BEAD_RES_NAME
