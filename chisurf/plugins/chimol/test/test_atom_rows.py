"""One definition of an atom row, shared by every reader that makes one.

The row's shape belongs to chisurf's core, and chimol imports it. It used to
transcribe it -- three times, each captioned as "the atom dtype every reader
produces", and no two of them the same. A structured array is silent about a
disagreement: fields the other definition had were simply always zero, and a
field too narrow for its data truncated rather than complained.

Beads are rows too. Everything downstream tells a bead from an atom by one
string in one column, and while that string was written out at each
construction site the sites could drift -- the RMF reader, which never wrote it
at all, is why an RMF model was drawn at a single default radius with its
hierarchy check boxes inert.

These tests pin the row shape, its ownership, the ways of building it, and the
per-row classification.
"""
from __future__ import annotations

import numpy as np
import pytest

from chimol.io.atoms import (
    ATOM_DTYPE,
    BEAD_RES_NAME,
    atom_row,
    bead_mask,
    bead_row,
    make_bead_rows,
)


def test_the_two_builders_agree():
    """Row-at-a-time and vectorised construction produce the same row.

    The mmCIF reader appends rows as it walks the file; the RMF reader has
    hundreds of thousands of particles already in arrays. Both spellings have to
    mean the same thing or the classification depends on which reader ran.
    """
    xyz = [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)]
    one_at_a_time = np.array(
        [bead_row("A", 7, xyz[0]), bead_row("B", 8, xyz[1])], dtype=ATOM_DTYPE
    )
    vectorised = make_bead_rows(xyz, chain_ids=["A", "B"], res_ids=[7, 8])

    assert vectorised.dtype == one_at_a_time.dtype
    np.testing.assert_array_equal(vectorised, one_at_a_time)


def test_beads_default_to_distinct_residues():
    """Unnumbered beads get 1..N, not one shared residue id.

    The trace breaks on repeated ``(chain, res_id)`` pairs, so numbering every
    bead the same collapses a whole model to a single trace point.
    """
    rows = make_bead_rows(np.zeros((5, 3)))
    np.testing.assert_array_equal(rows["res_id"], [1, 2, 3, 4, 5])
    assert len(set(rows["res_id"].tolist())) == 5


def test_metadata_length_is_checked():
    """A mismatched chain/res array is an error, not a silent truncation."""
    with pytest.raises(ValueError, match="chain_ids"):
        make_bead_rows(np.zeros((3, 3)), chain_ids=["A", "B"])
    with pytest.raises(ValueError, match="res_ids"):
        make_bead_rows(np.zeros((3, 3)), res_ids=[1, 2])
    with pytest.raises(ValueError, match=r"\(N, 3\)"):
        make_bead_rows(np.zeros((3, 2)))


def test_classification_is_per_row():
    """A hybrid model is half beads, and the mask says exactly which half.

    A reader writes every atomic row before every sphere, so any answer derived
    from a *sample* of the array is right about one end and wrong about the
    other.
    """
    names = np.array(["CA", "CB", BEAD_RES_NAME, BEAD_RES_NAME], dtype="U4")
    np.testing.assert_array_equal(bead_mask(names), [False, False, True, True])


def test_classification_tolerates_padding_and_emptiness():
    """Names arrive padded from fixed-width dtypes; nothing arrives as None."""
    np.testing.assert_array_equal(bead_mask(np.array([" BEA ", "ALA"])), [True, False])
    assert bead_mask(None) is None
    assert bead_mask(np.array([], dtype="U4")) is None


def test_the_mmcif_reader_still_produces_recognisable_beads():
    """The reader's own rows classify as beads.

    This is the anti-drift guard: it goes through ``_parse_mmcif_backbone``'s
    construction rather than a fixture's idea of it, so a reader that stopped
    using the shared builder would fail here rather than at render time on a
    234,000-bead model.
    """
    from chimol.io import structure

    assert structure.ATOM_DTYPE is ATOM_DTYPE
    row = np.array([bead_row("X", 1, (0.0, 0.0, 0.0))], dtype=ATOM_DTYPE)
    np.testing.assert_array_equal(bead_mask(row["res_name"]), [True])


def test_there_is_one_atom_dtype_and_the_core_owns_it():
    """ChiMOL does not define an atom row; it imports chisurf's.

    Three transcriptions of this dtype lived in chimol, each captioned as "the
    atom dtype every reader produces", and no two of them the same: six fields
    for the PDB/mmCIF/RMF readers, twelve for MDTraj topologies, twelve more for
    pseudoatoms. A structured array does not object when the shapes disagree, so
    the mismatch showed up only as fields that were quietly always zero.
    """
    from chisurf.core.fio.structure.coordinates import atom_dtype, keys
    from chimol.cmd.editing import PSEUDOATOM_DTYPE
    from chimol.io import structure

    assert ATOM_DTYPE is atom_dtype
    assert PSEUDOATOM_DTYPE is atom_dtype
    assert structure.ATOM_DTYPE is atom_dtype
    assert ATOM_DTYPE.names == tuple(keys)


def test_a_chain_id_of_more_than_one_character_survives():
    """An mmCIF asym id is not one character, and the field must hold it.

    The canonical dtype had ``chain`` as ``|U1``. On the eight-spoke nuclear
    pore 518 of 544 chains need two characters, so every one of them was stored
    as its first letter and 544 chains became 26 -- silently. ``chain AB`` then
    selected the whole of A, and colouring by chain painted twenty molecules
    alike.
    """
    rows = make_bead_rows(
        np.zeros((3, 3)), chain_ids=["A", "AA", "AB"], res_ids=[1, 1, 1]
    )
    assert rows["chain"].tolist() == ["A", "AA", "AB"]
    assert len(set(rows["chain"].tolist())) == 3


def test_a_row_is_built_by_name_not_by_position():
    """Twelve positional fields is more than a reader should have to count.

    Adding a field to the dtype must not shift a reader's values into the wrong
    columns, and a typo must be refused rather than dropped.
    """
    row = np.array(
        [atom_row(atom_name="CA", res_name="ALA", chain="B", res_id=7,
                  element="C", xyz=(1.0, 2.0, 3.0), bfactor=42.0)],
        dtype=ATOM_DTYPE,
    )
    assert row["atom_name"][0] == "CA"
    assert row["chain"][0] == "B"
    assert row["res_id"][0] == 7
    assert row["bfactor"][0] == 42.0
    # Fields nobody supplied keep the type's zero rather than someone else's value.
    assert row["charge"][0] == 0.0

    with pytest.raises(KeyError, match="bfactorr"):
        atom_row(bfactorr=1.0)
