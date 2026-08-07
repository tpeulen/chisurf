"""Bond orders for the standard residues, from residue nomenclature.

A PDB file records no bond orders, so a viewer that wants to draw a double bond
has to know which bonds are double. PyMOL solves this the same way it solves
formal charge: a hard-coded table applied while it connects the molecule
(``assign_pdb_known_residue``, ``layer2/ObjectMolecule2.cpp``), keyed on the
residue name and the two atom names. That table is transcribed here.

What it covers, and what it cannot
----------------------------------
Every standard amino acid and nucleotide, which is what a PDB structure is made
of, plus the backbone carbonyl of any known protein residue. It says nothing
about a **ligand**: an untemplated residue has no entry and its bonds stay
single. PyMOL is in the same position -- for a ligand it has bond orders only
from a format that carries them (mol2, sdf, mmCIF's ``chem_comp_bond``) -- so
this is a property of the input rather than a gap between the two.

The asymmetries are deliberate and are PyMOL's:

* a carboxylate has **one** double bond (``CG=OD1``, ``CD=OE1``) with the other
  oxygen single and formally charged, which is the same bookkeeping choice
  :data:`~chimol.analysis.interactions.PDB_FORMAL_CHARGES` makes;
* a guanidinium is ``CZ=NH1``, and PyMOL forces ``CZ-NH2`` back to **single**
  in case something else set it -- the pair is a resonance hybrid and the
  bookkeeping has to pick one;
* the aromatic rings are drawn Kekulé, alternating, not as a delocalised
  circle. Which alternation matters: taking the wrong three bonds of a
  phenylalanine gives a ring where two double bonds meet at one carbon.
* histidine's second double bond depends on the tautomer, and the residue name
  is what says which: ``CE1=ND1`` for the default and for the protonated forms,
  ``CE1=NE2`` for the ND1-protonated ones (``HID``, ``HISA``, ``HISD``).
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "DOUBLE_BONDS",
    "PROTEIN_RESIDUES",
    "assign_bond_orders",
]

#: Residues PyMOL's ``AtomInfoKnownProteinResName`` accepts, which is what
#: decides whether the backbone ``C=O`` rule applies.
PROTEIN_RESIDUES = frozenset({
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "CYX", "HID", "HIE", "HIP", "HISA", "HISB", "HISD", "HISE", "HISH",
    "HISP", "ARGP", "ASPM", "GLUM", "LYSP", "MSE", "SEC", "PYL",
})

_PURINE = (("C8", "N7"), ("C4", "C5"), ("C6", "N1"), ("C2", "N3"))
_GUANINE = (("C6", "O6"), ("C2", "N3"), ("C8", "N7"), ("C4", "C5"))
_CYTOSINE = (("C2", "O2"), ("C4", "N3"), ("C5", "C6"))
_URACIL = (("C2", "O2"), ("C4", "O4"), ("C5", "C6"))
#: Both spellings of the phosphate oxygen, as PyMOL accepts both.
_PHOSPHATE = (("P", "O1P"), ("P", "OP1"))
_BENZENE = (("CG", "CD1"), ("CZ", "CE1"), ("CE2", "CD2"))

#: ``residue -> pairs of atom names joined by a double bond``. The empty
#: residue key holds the rule that applies to every protein residue.
DOUBLE_BONDS: dict[str, tuple[tuple[str, str], ...]] = {
    "ARG": (("CZ", "NH1"),),
    "ARGP": (("CZ", "NH1"),),
    "ASP": (("CG", "OD1"),),
    "ASPM": (("CG", "OD1"),),
    "ASN": (("CG", "OD1"),),
    "GLU": (("CD", "OE1"),),
    "GLUM": (("CD", "OE1"),),
    "GLN": (("CD", "OE1"),),
    # Histidine, by tautomer. The imidazole always has CG=CD2; the other double
    # bond moves with the proton.
    "HIS": (("CG", "CD2"), ("CE1", "ND1")),
    "HIP": (("CG", "CD2"), ("CE1", "ND1")),
    "HISH": (("CG", "CD2"), ("CE1", "ND1")),
    "HISP": (("CG", "CD2"), ("CE1", "ND1")),
    "HISB": (("CG", "CD2"), ("CE1", "ND1")),
    "HISE": (("CG", "CD2"), ("CE1", "ND1")),
    "HIE": (("CG", "CD2"), ("CE1", "ND1")),
    "HISA": (("CG", "CD2"), ("CE1", "NE2")),
    "HISD": (("CG", "CD2"), ("CE1", "NE2")),
    "HID": (("CG", "CD2"), ("CE1", "NE2")),
    "PHE": _BENZENE,
    "TYR": _BENZENE,
    "TRP": (("CG", "CD1"), ("CZ3", "CE3"), ("CZ2", "CH2"), ("CE2", "CD2")),
    # Nucleotides, ribo and deoxy under the same rules.
    "A": _PURINE + _PHOSPHATE,
    "DA": _PURINE + _PHOSPHATE,
    "I": _PURINE + _PHOSPHATE,
    "DI": _PURINE + _PHOSPHATE,
    "G": _GUANINE + _PHOSPHATE,
    "DG": _GUANINE + _PHOSPHATE,
    "C": _CYTOSINE + _PHOSPHATE,
    "DC": _CYTOSINE + _PHOSPHATE,
    "T": _URACIL + _PHOSPHATE,
    "DT": _URACIL + _PHOSPHATE,
    "U": _URACIL + _PHOSPHATE,
    "DU": _URACIL + _PHOSPHATE,
}

#: PyMOL forces these back to single after setting the partner double, because
#: the pair is one resonance hybrid and only one of them may be drawn double.
FORCED_SINGLE: dict[str, tuple[tuple[str, str], ...]] = {
    "ARG": (("CZ", "NH2"),),
    "ARGP": (("CZ", "NH2"),),
}


def _pair_key(first: str, second: str) -> tuple[str, str]:
    """Atom-name pair in a fixed order, so a bond matches either way round."""
    return (first, second) if first <= second else (second, first)


def assign_bond_orders(atoms: np.ndarray, bond_pairs) -> np.ndarray:
    """Order for every bond: 2 where the table says double, else 1.

    Parameters
    ----------
    atoms : numpy.ndarray
        Structured atom array with ``atom_name``, ``res_name`` and, when
        present, ``res_id`` and ``chain`` -- which are what stop the rule from
        matching two atoms of the *same names* in neighbouring residues.
    bond_pairs : array-like or None
        ``(B, 2)`` bonds.

    Returns
    -------
    numpy.ndarray
        ``(B,)`` of ``int``. All ones when there is nothing to say.

    Notes
    -----
    Both atoms must be in the same residue, except that nothing in the table
    spans residues -- the peptide ``C-N`` bond is single and stays single.
    """
    pairs = np.asarray(bond_pairs, dtype=int) if bond_pairs is not None else None
    if pairs is None or pairs.ndim != 2 or pairs.shape[0] == 0:
        return np.ones(0, dtype=int)

    orders = np.ones(pairs.shape[0], dtype=int)
    names = atoms.dtype.names or ()
    if "atom_name" not in names or "res_name" not in names:
        return orders

    atom_names = np.char.upper(
        np.char.strip(np.asarray(atoms["atom_name"]).astype(str))
    )
    res_names = np.char.upper(
        np.char.strip(np.asarray(atoms["res_name"]).astype(str))
    )
    res_ids = (
        np.asarray(atoms["res_id"]) if "res_id" in names
        else np.zeros(len(atoms), dtype=int)
    )
    chains = (
        np.asarray(atoms["chain"]).astype(str) if "chain" in names
        else np.zeros(len(atoms), dtype=str)
    )

    for index, (i, j) in enumerate(pairs[:, :2]):
        i, j = int(i), int(j)
        if not (0 <= i < len(atoms) and 0 <= j < len(atoms)):
            continue
        # Same residue only. Two neighbouring glutamates both have a `CD` and
        # an `OE1`, and a table keyed on names alone would happily double the
        # bond between them if the connectivity ever put one there.
        if res_ids[i] != res_ids[j] or chains[i] != chains[j]:
            continue
        residue = str(res_names[i])
        if residue != str(res_names[j]):
            continue
        key = _pair_key(str(atom_names[i]), str(atom_names[j]))

        # The backbone carbonyl, for any residue PyMOL calls a protein.
        if key == ("C", "O") and residue in PROTEIN_RESIDUES:
            orders[index] = 2
            continue

        table = DOUBLE_BONDS.get(residue)
        if table and any(_pair_key(*pair) == key for pair in table):
            orders[index] = 2
        forced = FORCED_SINGLE.get(residue)
        if forced and any(_pair_key(*pair) == key for pair in forced):
            orders[index] = 1

    return orders
