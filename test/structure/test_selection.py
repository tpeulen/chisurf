"""Atom-selection expressions (:mod:`chisurf.core.structure.selection`).

This parser replaces an external one, and selection strings live in saved
projects and in users' fingers — so the test that matters is not "does it
parse" but "does it select the same atoms as the language it replaces". The
answer for 45 expressions is recorded in
``test/data/atomic_coordinates/selection/``, generated from the reference
implementation on a real 5235-atom structure and committed, so the comparison
survives that implementation's removal.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from chisurf.core.structure.selection import SelectionError, select, selection_mask

DATA = pathlib.Path(__file__).resolve().parents[1] / "data/atomic_coordinates"
PDB = DATA / "trajectory/hgbp1/topol.pdb"
EXPRESSIONS = json.loads((DATA / "selection/expressions.json").read_text())
EXPECTED = np.load(DATA / "selection/topol_expected.npz")


@pytest.fixture(scope="module")
def atoms():
    from chisurf.core.structure import Structure

    return Structure(str(PDB)).atoms


@pytest.mark.parametrize(
    "index, expression",
    list(enumerate(EXPRESSIONS)),
    ids=[e.replace(" ", "_") for e in EXPRESSIONS],
)
def test_matches_the_language_it_replaces(atoms, index, expression):
    np.testing.assert_array_equal(
        np.asarray(select(atoms, expression), dtype=np.int32), EXPECTED[f"s{index}"]
    )


def test_the_fixture_is_not_vacuous():
    """Guard against the comparison passing because everything is empty."""
    sizes = [len(EXPECTED[f"s{i}"]) for i in range(len(EXPRESSIONS))]
    assert sum(1 for n in sizes if n) >= len(EXPRESSIONS) - 4
    assert max(sizes) == 5235


def test_resid_and_resseq_are_not_the_same_thing(atoms):
    # The classic trap: a structure that does not start at residue 1 makes
    # these differ, and picking the wrong one silently selects a different
    # residue rather than failing.
    by_index = select(atoms, "resid 0")
    by_number = select(atoms, "resSeq 0")
    assert len(by_index) > 0
    assert not np.array_equal(by_index, by_number)


def test_a_range_includes_both_ends(atoms):
    assert len(select(atoms, "index 0 to 4")) == 5


def test_masks_and_indices_agree(atoms):
    mask = selection_mask(atoms, "name CA")
    np.testing.assert_array_equal(np.flatnonzero(mask), select(atoms, "name CA"))


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "   ",
        "name",
        "nosuchfield CA",
        "name CA and",
        "(name CA",
        "name CA)",
        "resSeq > ",
        "resSeq > CA",
        "name CA $ CB",
    ],
)
def test_a_bad_expression_raises_rather_than_selecting_nothing(atoms, expression):
    # Returning an empty selection for a typo is the dangerous failure: an
    # analysis then runs on no atoms and reports a result.
    with pytest.raises(SelectionError):
        select(atoms, expression)
