"""PyMOL's ``cartoon_side_chain_helper``, transcribed from ``SideChainHelper.cpp``.

The commonest figure in structural biology is a cartoon with sticks on a handful
of residues. Drawn naively it is a mess: every stick residue also draws its
backbone N, C and O, which run *inside* the cartoon and poke out of it, so the
side chain does not read as growing out of the ribbon. PyMOL's answer is this
setting, on in its ``pretty`` and ``ligand_cartoon`` presets, and it is why those
presets look the way they do.

The rule is a **bond filter, not an atom filter**, which is the thing to get
right: the backbone atoms stay in the model and stay pickable, and it is the
*bonds between them* that are dropped from the stick and line representations
where a cartoon already covers them. ``SideChainHelperFilterBond`` suppresses

* ``CA-C`` and ``N-CA`` (the latter except in proline, whose ring needs it),
* ``N-C``,
* ``C-O`` and ``C-OXT``,
* every hydrogen on ``CA`` and on ``N``,

and leaves ``CA-CB`` alone -- that is the bond the side chain hangs from, and
where the cartoon's colour is handed over to the sticks.

The exception that makes it work at the edges is ``marked``: an atom whose
cartoon is drawn but whose bonded neighbour's is *not* keeps its backbone bonds,
so sticks at the end of a cartoon segment still connect to something rather than
floating.

Nucleic acids have their own branch in PyMOL (``na_mode``, the ``C[45][*']``
bonds); it is not transcribed here, so the helper only ever hides protein
backbone bonds.
"""

from __future__ import annotations

import numpy as np

__all__ = ["mark_cartoon_boundary_atoms", "hidden_backbone_bonds"]


def _field(atoms, name: str) -> np.ndarray | None:
    """One atom field as stripped upper-case strings, or ``None`` if absent."""
    if atoms is None or name not in (atoms.dtype.names or ()):
        return None
    return np.char.upper(np.char.strip(np.asarray(atoms[name]).astype(str)))


def mark_cartoon_boundary_atoms(
    bonds: np.ndarray, cartoon: np.ndarray, polymer: np.ndarray
) -> np.ndarray:
    """Atoms whose cartoon is drawn but whose bonded neighbour's is not.

    PyMOL's ``SideChainHelperMarkNonCartoonBonded``. These atoms keep their
    backbone bonds, because they are where the cartoon stops and the sticks have
    to reach it.

    Parameters
    ----------
    bonds : ndarray of int, shape (M, 2)
        Bonded atom index pairs.
    cartoon : ndarray of bool
        Whether a cartoon is drawn over each atom.
    polymer : ndarray of bool
        Whether each atom belongs to the polymer.

    Returns
    -------
    ndarray of bool
        One flag per atom.
    """
    marked = np.zeros(cartoon.shape[0], dtype=bool)
    if bonds.size == 0:
        return marked
    i, j = bonds[:, 0], bonds[:, 1]
    both_polymer = polymer[i] & polymer[j]
    np.logical_or.at(marked, i[both_polymer & cartoon[i] & ~cartoon[j]], True)
    np.logical_or.at(marked, j[both_polymer & cartoon[j] & ~cartoon[i]], True)
    return marked


def hidden_backbone_bonds(
    atoms,
    bonds: np.ndarray,
    cartoon: np.ndarray,
    polymer: np.ndarray,
) -> np.ndarray:
    """Which bonds ``cartoon_side_chain_helper`` hides.

    Transcribed from ``SideChainHelperFilterBond``. Only bonds whose *both*
    atoms are polymer and carry a cartoon are considered, matching the
    ``cRepCartoonBit & ati1->visRep & ati2->visRep`` guard in ``RepCylBond``.

    Parameters
    ----------
    atoms : numpy structured array
        Needs ``atom_name`` and ``element``; ``res_name`` is used for the
        proline exception.
    bonds : ndarray of int, shape (M, 2)
        Bonded atom index pairs.
    cartoon : ndarray of bool
        Whether a cartoon is drawn over each atom.
    polymer : ndarray of bool
        Whether each atom belongs to the polymer.

    Returns
    -------
    ndarray of bool
        One flag per bond; True means "do not draw this stick or line".
    """
    hidden = np.zeros(bonds.shape[0], dtype=bool)
    names = _field(atoms, "atom_name")
    elements = _field(atoms, "element")
    if names is None or elements is None or bonds.size == 0:
        return hidden
    res_names = _field(atoms, "res_name")
    marked = mark_cartoon_boundary_atoms(bonds, cartoon, polymer)

    i, j = bonds[:, 0], bonds[:, 1]
    # Only bonds whose *both* atoms are polymer and carry a cartoon, matching
    # the `cRepCartoonBit & ati1->visRep & ati2->visRep` guard in RepCylBond.
    eligible = polymer[i] & polymer[j] & cartoon[i] & cartoon[j]
    if not eligible.any():
        return hidden

    # PyMOL orders the pair before testing so each rule is written once; the
    # swap is transcribed rather than reasoned about, since it is what makes
    # `a` the backbone anchor (CA, N or O) in every rule below. Vectorised
    # because this runs on every scene rebuild: a per-bond Python loop cost
    # 1.3 s on 500 000 bonds, which a large assembly reaches easily.
    swap = (
        (elements[i] == "H")
        | (elements[j] == "N")
        | (elements[j] == "O")
        | ((elements[i] == "C") & (elements[j] == "C") & (names[j] == "CA"))
    )
    a = np.where(swap, j, i)
    b = np.where(swap, i, j)

    el_a, el_b = elements[a], elements[b]
    nm_a, nm_b = names[a], names[b]
    marked_a, marked_b = marked[a], marked[b]

    is_ca = (el_a == "C") & (nm_a == "CA")
    hidden |= is_ca & (el_b == "C") & (nm_b == "C") & ~marked_b   # CA-C
    hidden |= is_ca & (el_b == "H")                               # CA-hydrogens

    is_n = (el_a == "N") & (nm_a == "N")
    not_pro = (
        np.ones(bonds.shape[0], dtype=bool) if res_names is None
        else res_names[b] != "PRO"
    )
    # Proline's N-CA closes its ring: PyMOL keeps it and hands the colour over.
    hidden |= is_n & (el_b == "C") & (nm_b == "CA") & ~marked_a & not_pro
    hidden |= is_n & (el_b == "C") & (nm_b == "C") & ~marked_a    # N-C
    hidden |= is_n & (el_b == "H")                                # N-hydrogens

    is_o = el_a == "O"
    hidden |= (
        is_o & (el_b == "C") & (nm_b == "C")
        & ((nm_a == "O") | (nm_a == "OXT")) & ~marked_b           # C-O, C-OXT
    )

    return hidden & eligible
