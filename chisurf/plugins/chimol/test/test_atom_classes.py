"""Atom classification, against ``SelectorClassifyAtoms``.

``polymer``, ``organic``, ``solvent``, ``backbone`` and ``guide`` are derived per
residue from which atoms are present, not from a table of residue names. Pinning
that here is what stops the classification quietly regressing to a name lookup,
which would mis-file every modified residue and every unusual ligand.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.analysis.atom_classes import (
    BACKBONE_NAMES,
    classify_atoms,
    is_metal,
    residue_runs,
)

_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)

_DTYPE = [
    ("atom_name", "U5"), ("res_name", "U4"), ("chain", "U2"),
    ("res_id", np.int64), ("element", "U2"),
]


def _residue(names, resn="ALA", chain="A", res_id=1, elements=None):
    """One residue's worth of atoms."""
    elements = elements or [n[:1] for n in names]
    return [
        (n, resn, chain, res_id, e) for n, e in zip(names, elements)
    ]


def _atoms(*residues) -> np.ndarray:
    rows = [row for residue in residues for row in residue]
    return np.array(rows, dtype=_DTYPE)


# --------------------------------------------------------------------------- #
# The rule, transcribed
# --------------------------------------------------------------------------- #
def test_a_backbone_makes_a_residue_protein():
    """CA + N + C + O, per SelectorClassifyAtoms."""
    classes = classify_atoms(_atoms(_residue(["N", "CA", "C", "O", "CB"])))
    assert classes.protein.all()
    assert classes.polymer.all()
    assert not classes.organic.any()


def test_a_missing_backbone_atom_is_not_protein():
    """A residue named ALA without its CA is not polymer, whatever it is called.

    This is the point of classifying by content: the name lies, the atoms do not.
    """
    classes = classify_atoms(_atoms(_residue(["N", "C", "O", "CB"])))
    assert not classes.protein.any()
    assert classes.organic.all()   # it still has carbon


def test_a_nucleotide_is_nucleic():
    names = ["P", "O5'", "C5'", "C4'", "O4'", "C3'", "O3'", "C1'", "N1"]
    classes = classify_atoms(_atoms(_residue(names, resn="DA")))
    assert classes.nucleic.all()
    assert classes.polymer.all()
    assert not classes.protein.any()


def test_a_star_primed_nucleotide_is_nucleic_too():
    """Files written before the mmCIF era spell C4' as C4*."""
    names = ["P", "O5*", "C5*", "C4*", "O4*", "C3*", "O3*", "C1*"]
    classes = classify_atoms(_atoms(_residue(names, resn="DA")))
    assert classes.nucleic.all()


def test_a_carbon_bearing_residue_is_organic():
    classes = classify_atoms(
        _atoms(_residue(["C1", "C2", "O1"], resn="LIG"))
    )
    assert classes.organic.all()


def test_a_lone_oxygen_is_solvent():
    """PyMOL's rule: (O or OH2) *and* a single-atom residue."""
    classes = classify_atoms(_atoms(_residue(["O"], resn="HOH")))
    assert classes.solvent.all()
    assert not classes.organic.any()


def test_a_backbone_oxygen_is_not_solvent():
    """The single-atom condition is what keeps every backbone O out of solvent."""
    classes = classify_atoms(_atoms(_residue(["N", "CA", "C", "O"])))
    assert not classes.solvent.any()


def test_a_lone_metal_is_inorganic():
    classes = classify_atoms(
        _atoms(_residue(["ZN"], resn="ZN", elements=["ZN"]))
    )
    assert classes.inorganic.all()
    assert classes.metal.all()


def test_a_hydrogen_only_residue_is_nothing():
    """PyMOL excludes them explicitly, or unsorted hydrogens read as inorganic."""
    classes = classify_atoms(
        _atoms(_residue(["H1", "H2"], resn="UNK", elements=["H", "H"]))
    )
    assert not classes.inorganic.any()
    assert not classes.organic.any()
    assert classes.hydrogen.all()


# --------------------------------------------------------------------------- #
# Guide atoms
# --------------------------------------------------------------------------- #
def test_the_guide_atom_of_a_protein_residue_is_ca():
    atoms = _atoms(_residue(["N", "CA", "C", "O", "CB"]))
    guide = classify_atoms(atoms).guide
    assert atoms["atom_name"][guide].tolist() == ["CA"]


def test_the_guide_atom_of_a_nucleotide_is_c4_prime():
    names = ["P", "O5'", "C5'", "C4'", "O4'", "C3'", "O3'", "C1'"]
    atoms = _atoms(_residue(names, resn="DA"))
    guide = classify_atoms(atoms).guide
    assert atoms["atom_name"][guide].tolist() == ["C4'"]


def test_a_ligand_has_no_guide_atom():
    classes = classify_atoms(_atoms(_residue(["C1", "C2"], resn="LIG")))
    assert not classes.guide.any()


def test_one_guide_atom_per_residue():
    atoms = _atoms(
        _residue(["N", "CA", "C", "O"], res_id=1),
        _residue(["N", "CA", "C", "O"], res_id=2),
    )
    assert int(classify_atoms(atoms).guide.sum()) == 2


# --------------------------------------------------------------------------- #
# Backbone / sidechain
# --------------------------------------------------------------------------- #
def test_backbone_and_sidechain_partition_the_polymer():
    atoms = _atoms(_residue(["N", "CA", "C", "O", "CB", "CG"]))
    classes = classify_atoms(atoms)
    assert (classes.backbone | classes.sidechain).tolist() == classes.polymer.tolist()
    assert not (classes.backbone & classes.sidechain).any()


def test_a_ligand_is_neither_backbone_nor_sidechain():
    """Both are gated on cAtomFlag_polymer in PyMOL."""
    classes = classify_atoms(_atoms(_residue(["C1", "C2"], resn="LIG")))
    assert not classes.backbone.any()
    assert not classes.sidechain.any()


def test_backbone_names_are_pymols_list():
    """Spot-checks against backbone_names[] in layer3/Selector.cpp."""
    for name in ("CA", "C", "O", "N", "OXT", "H", "P", "OP1", "C4'", "O3'"):
        assert name in BACKBONE_NAMES


# --------------------------------------------------------------------------- #
# Metals, by proton count
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("symbol", ["LI", "NA", "MG", "AL", "K", "CA", "FE", "ZN", "AU", "U"])
def test_metals_are_metals(symbol):
    assert is_metal(np.array([symbol]))[0]


@pytest.mark.parametrize("symbol", ["H", "HE", "C", "N", "O", "F", "P", "S", "CL", "BR", "I", "XE"])
def test_non_metals_are_not(symbol):
    assert not is_metal(np.array([symbol]))[0]


def test_an_unknown_symbol_is_not_a_metal():
    """A blank or junk element must not be guessed into a class."""
    assert not is_metal(np.array(["", "??"])).any()


# --------------------------------------------------------------------------- #
# Residue runs
# --------------------------------------------------------------------------- #
def test_runs_split_on_a_change_of_residue():
    atoms = _atoms(
        _residue(["N", "CA"], res_id=1),
        _residue(["N", "CA"], res_id=2),
    )
    assert residue_runs(atoms) == [(0, 2), (2, 4)]


def test_runs_split_on_a_change_of_chain():
    """Two chains numbered the same are two residues, not one."""
    atoms = _atoms(
        _residue(["N", "CA"], chain="A", res_id=1),
        _residue(["N", "CA"], chain="B", res_id=1),
    )
    assert residue_runs(atoms) == [(0, 2), (2, 4)]


def test_runs_are_by_contiguity_not_by_sorting():
    """The same residue appearing twice yields two runs."""
    atoms = _atoms(
        _residue(["N"], res_id=1),
        _residue(["N"], res_id=2),
        _residue(["N"], res_id=1),
    )
    assert residue_runs(atoms) == [(0, 1), (1, 2), (2, 3)]


def test_no_atoms_gives_no_runs():
    assert residue_runs(np.array([], dtype=_DTYPE)) == []


# --------------------------------------------------------------------------- #
# A deposited entry
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def lysozyme_atoms():
    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.io.structure import _read_full_model

    return _read_full_model(cs_struct.Structure, _PDB_148L).atoms


def test_the_protein_chain_classifies_as_protein(lysozyme_atoms):
    classes = classify_atoms(lysozyme_atoms)
    chains = np.char.strip(lysozyme_atoms["chain"].astype(str))
    # Chain E is T4 lysozyme itself; all but the terminal residue lacking a CA.
    assert classes.protein[chains == "E"].mean() > 0.99


def test_the_sugars_of_the_ligand_are_organic(lysozyme_atoms):
    """NAG and MUB carry carbon and no peptide backbone."""
    classes = classify_atoms(lysozyme_atoms)
    names = np.char.strip(lysozyme_atoms["res_name"].astype(str))
    assert classes.organic[np.isin(names, ("NAG", "MUB"))].all()


def test_the_stem_peptide_of_the_ligand_is_polymer(lysozyme_atoms):
    """DAL and FGA are amino acids with full backbones, so they are polymer.

    Only reachable because the reader keeps ligand atom names: IMP prefixes the
    type of any atom it cannot classify with ``HET:``, which used to truncate to
    ``HET:`` and leave every ligand atom sharing one name.
    """
    classes = classify_atoms(lysozyme_atoms)
    names = np.char.strip(lysozyme_atoms["res_name"].astype(str))
    assert classes.polymer[np.isin(names, ("DAL", "FGA"))].all()


def test_every_atom_lands_in_at_most_one_class(lysozyme_atoms):
    classes = classify_atoms(lysozyme_atoms)
    total = (
        classes.protein.astype(int)
        + classes.nucleic.astype(int)
        + classes.organic.astype(int)
        + classes.solvent.astype(int)
        + classes.inorganic.astype(int)
    )
    assert total.max() <= 1


def test_one_guide_atom_per_traced_residue(lysozyme_atoms):
    """As many guide atoms as there are polymer residues."""
    classes = classify_atoms(lysozyme_atoms)
    runs = residue_runs(lysozyme_atoms)
    polymer_residues = sum(1 for a, b in runs if classes.polymer[a:b].any())
    assert int(classes.guide.sum()) == polymer_residues
