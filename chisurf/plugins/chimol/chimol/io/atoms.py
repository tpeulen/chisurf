"""What an atom row is -- and what a *bead* is, which is a row too.

Every reader here produces the same structured array, and that array's shape is
**not defined here**: it is `chisurf.core.fio.structure.coordinates.keys_formats`,
the one chisurf's own structure readers fill. Importing it rather than
transcribing it is the whole point. There were three transcriptions in chimol
alone -- a six-field one for the PDB/mmCIF/RMF readers, a twelve-field one for
MDTraj topologies, and a third for pseudoatoms -- each claiming in a comment to
be "the atom dtype every reader produces", and no two of them the same. A
structured array does not complain when the shapes disagree; consumers just
grew ``dtype.fields`` guards, and the fields nobody guarded went missing.

A coarse-grained model has no atoms. It has **beads**: spheres that each stand
for a stretch of sequence, with a radius that says how much of it. Two readers
produce them -- the integrative-mmCIF reader from ``_ihm_sphere_obj_site``, and
the RMF reader from IMP's particles -- and everything downstream has to tell a
bead from an atom, because a bead model must never be splined into a cartoon
and a 200,000-bead model must never be drawn as 200,000 meshes. That test is a
string comparison against one residue name, which was itself written out in
four places and not at all by the RMF reader. It lives here now, once.

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

from chisurf.core.fio.structure.coordinates import atom_dtype as ATOM_DTYPE

__all__ = [
    "ATOM_DTYPE",
    "BEAD_ATOM_NAME",
    "BEAD_ELEMENT",
    "BEAD_RES_NAME",
    "atom_row",
    "bead_mask",
    "bead_row",
    "empty_atoms",
    "make_bead_rows",
]

#: Named so the trace and cartoon machinery can follow a chain of beads.
BEAD_ATOM_NAME = "CA"
#: The residue name that marks a row as a bead rather than an atom. This single
#: string is the whole classification; see :func:`bead_mask`.
BEAD_RES_NAME = "BEA"
#: Beads have no element. Carbon is the harmless answer for the colour-by-element
#: and radius tables, which would otherwise fall through to an unknown-element
#: default that differs between them.
BEAD_ELEMENT = "C"


def empty_atoms(n: int) -> np.ndarray:
    """Return an all-zero atom array of ``n`` rows, for a reader to fill by name.

    Parameters
    ----------
    n : int
        Number of rows.

    Returns
    -------
    numpy.ndarray
        Structured array of :data:`ATOM_DTYPE`.
    """
    return np.zeros(int(n), dtype=ATOM_DTYPE)


def atom_row(**fields) -> tuple:
    """Build one row **by field name**, for a reader that appends as it parses.

    The row is a tuple in dtype order, and that order is now twelve fields long
    -- which is more than anyone should be asked to keep in their head while
    reading a PDB line. Passing the fields by name means adding a field to the
    dtype cannot silently shift a reader's values into the wrong columns; an
    unknown name is refused rather than dropped.

    Parameters
    ----------
    **fields
        Any subset of :data:`ATOM_DTYPE`'s field names. Anything not given keeps
        the type's zero.

    Returns
    -------
    tuple
        A row in :data:`ATOM_DTYPE` order.

    Raises
    ------
    KeyError
        If a name is not a field of the dtype.
    """
    unknown = set(fields) - set(ATOM_DTYPE.names)
    if unknown:
        raise KeyError(f"not atom fields: {', '.join(sorted(unknown))}")
    row = np.zeros(1, dtype=ATOM_DTYPE)
    for name, value in fields.items():
        row[name] = value
    return tuple(row[0])


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
    return atom_row(
        atom_name=BEAD_ATOM_NAME,
        res_name=BEAD_RES_NAME,
        chain=str(chain),
        res_id=int(res_id),
        element=BEAD_ELEMENT,
        xyz=xyz,
    )


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

    rows = empty_atoms(n)
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
