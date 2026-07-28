"""A chain identifier is not one character, and the PDB writer has one column.

Two facts that pull against each other, and getting either wrong is silent.

The atom row every chisurf reader fills is defined once, in
``chisurf.core.fio.structure.coordinates``. Its ``chain`` field was ``|U1``,
which is right for a PDB file and wrong for everything else: an mmCIF asym id
runs ``A``..``Z`` and then ``AA``, ``AB``, ..., so on the eight-spoke nuclear
pore (PDBDEV_00000012) 518 of 544 chains needed two characters and every one was
stored as its first letter. 544 chains became 26 -- ``chain AB`` selected the
whole of A, and colouring by chain painted twenty molecules alike. Nothing
raised, because a structured array truncates rather than complains.

Widening the field then made the *writer* the hazard: ``%1s`` is a **minimum**
width in Python and does not truncate, so a two-character id written through it
shifts every following column and produces a file no reader parses. The writer
truncates explicitly and says which chains it flattened.
"""
from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fio.structure.coordinates import atom_dtype, keys, write_pdb


def _atoms(chains) -> np.ndarray:
    """Build an atom array carrying the given chain identifiers."""
    atoms = np.zeros(len(chains), dtype=atom_dtype)
    atoms["atom_id"] = np.arange(1, len(chains) + 1)
    atoms["atom_name"] = "CA"
    atoms["res_name"] = "ALA"
    atoms["chain"] = chains
    atoms["res_id"] = np.arange(1, len(chains) + 1)
    atoms["element"] = "C"
    atoms["xyz"] = np.arange(3 * len(chains), dtype=float).reshape(-1, 3)
    return atoms


def test_the_dtype_is_one_definition():
    """``atom_dtype`` and the ``keys``/``formats`` pair describe the same row."""
    assert atom_dtype.names == tuple(keys)


def test_a_multi_character_chain_id_survives_the_round_trip():
    """The field holds what mmCIF permits, so distinct chains stay distinct."""
    atoms = _atoms(["A", "AA", "AB", "ZZ"])
    assert atoms["chain"].tolist() == ["A", "AA", "AB", "ZZ"]
    assert len(set(atoms["chain"].tolist())) == 4


def test_writing_pdb_keeps_every_column_aligned(tmp_path):
    """A wide chain id must not shift the fields after it.

    ``%1s`` would have written both characters and moved the residue number,
    the coordinates and everything else one column right -- for every atom of
    that chain, in a fixed-column format.
    """
    path = tmp_path / "wide.pdb"
    write_pdb(str(path), atoms=_atoms(["A", "AB", "AC"]))

    lines = [ln for ln in path.read_text().splitlines() if ln.startswith("ATOM")]
    assert len(lines) == 3
    for index, line in enumerate(lines):
        # The columns the PDB format fixes, read back by position.
        assert line[21] == "A", "chain belongs in column 22"
        assert line[22:26] == f"{index + 1:>4}", "residue number moved"
        assert line[30:38].strip() == f"{index * 3:.3f}", "coordinates moved"
        assert line[17:20] == "ALA"


def test_writing_pdb_says_which_chains_it_flattened(tmp_path, caplog):
    """The loss is real and forced by the format, so it is reported, not hidden.

    A PDB file cannot carry these identifiers. Truncating is the only thing to
    do -- but doing it in silence is how a user discovers, later and elsewhere,
    that two chains have become one.
    """
    path = tmp_path / "warned.pdb"
    with caplog.at_level("WARNING"):
        write_pdb(str(path), atoms=_atoms(["A", "AB", "AC"]))

    assert "AB" in caplog.text and "AC" in caplog.text
    assert "mmCIF" in caplog.text


def test_writing_pdb_is_quiet_when_nothing_is_lost(tmp_path, caplog):
    """An ordinary structure must not be warned about."""
    path = tmp_path / "plain.pdb"
    with caplog.at_level("WARNING"):
        write_pdb(str(path), atoms=_atoms(["A", "B", "C"]))

    assert "truncated" not in caplog.text


@pytest.mark.parametrize("chain", ["A", "AB", "ABCD"])
def test_the_structure_repr_uses_the_same_columns(chain):
    """``Structure.__str__`` shares the writer's format string and its hazard."""
    from chisurf.core.structure.structure import Structure

    atoms = _atoms([chain])
    structure = Structure.__new__(Structure)
    structure._atoms = atoms
    structure.filename = None

    line = next(
        ln for ln in str(structure).splitlines() if ln.startswith("ATOM")
    )
    assert line[21] == chain[0]
    assert line[22:26] == "   1", "residue number moved"
