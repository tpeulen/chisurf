"""Selection expressions end to end, on a deposited entry.

The unit tests next door pin the vocabulary and the classification; this file
pins what a user actually types. It runs against T4 lysozyme (148L), which is
useful precisely because it is not a clean case: a protein chain, a covalently
bound peptidoglycan ligand made of both sugars and amino acids, and a terminal
residue with no CA.

Three classes of bug are guarded here, each of which was live before:

* a keyword the evaluator implements but the parser cannot reach (``resn``),
* an operator parsed with the wrong fixity (``around`` is postfix, not prefix),
* a distance compared in the wrong units (the viewer holds scene units, a
  selection distance is Angstrom).
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.cmd.sele_parser import (
    Evaluator,
    ParserError,
    UnknownSelectionName,
    UnsupportedSelection,
)

_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def viewer(qapp):
    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.io.structure import _read_full_model
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    view = MolView()
    view.add_structure(
        _read_full_model(cs_struct.Structure, _PDB_148L),
        name="148l",
        source_path=str(_PDB_148L),
    )
    return view


@pytest.fixture
def select(viewer):
    """Evaluate an expression against the loaded entry, returning a mask."""
    object_id = viewer.get_active_object_id()

    def _select(expression: str) -> np.ndarray:
        return np.asarray(
            Evaluator(viewer, object_id).evaluate(expression, object_id),
            dtype=bool,
        )

    return _select


@pytest.fixture
def atoms(viewer):
    return viewer._objects[viewer.get_active_object_id()].state.atoms


def _count(mask) -> int:
    return int(np.count_nonzero(mask))


# --------------------------------------------------------------------------- #
# The regression: a keyword the parser could not reach
# --------------------------------------------------------------------------- #
def test_resn_selects_a_residue_by_name(select, atoms):
    """The bug this work started from: `resn NAG` matched nothing.

    The evaluator read `res_name` correctly, but the parser's hand-maintained
    tuple of property names did not list `resn`, so the expression parsed as an
    implicit AND of two bare identifiers and came out empty. It looked like an
    empty selection, not like a missing feature.
    """
    expected = _count(
        np.char.strip(atoms["res_name"].astype(str)) == "NAG"
    )
    assert expected > 0, "148L should carry NAG"
    assert _count(select("resn NAG")) == expected


def test_resn_ignores_case(select):
    assert _count(select("resn nag")) == _count(select("resn NAG"))


def test_a_value_list_unions(select):
    assert _count(select("resn NAG+MUB")) == _count(
        select("resn NAG or resn MUB")
    )


def test_a_residue_range(select, atoms):
    ids = np.asarray(atoms["res_id"], dtype=int)
    assert _count(select("resi 10-20")) == _count((ids >= 10) & (ids <= 20))


def test_a_wildcard_matches_a_family_of_names(select, atoms):
    """PyMOL matches globs, so `name C*` is every carbon position."""
    names = np.char.strip(atoms["atom_name"].astype(str))
    expected = _count(np.char.startswith(names, "C"))
    assert _count(select("name C*")) == expected


# --------------------------------------------------------------------------- #
# Operator fixity
# --------------------------------------------------------------------------- #
def test_around_is_postfix(select):
    """`sele around d`, per the LIST PRP1 PVAL reduction. Prefix is a parse error."""
    near = select("resn NAG around 4")
    assert _count(near) > 0
    with pytest.raises(ParserError):
        select("around 4 resn NAG")


def test_around_excludes_the_selection_it_grew_from(select):
    """Which is the whole difference between `around` and `expand`."""
    ligand = select("resn NAG")
    assert not (select("resn NAG around 4") & ligand).any()


def test_expand_includes_the_selection(select):
    ligand = select("resn NAG")
    grown = select("resn NAG expand 4")
    assert (grown & ligand).tolist() == ligand.tolist()
    assert _count(grown) == _count(select("resn NAG around 4")) + _count(ligand)


def test_within_is_infix(select):
    """`s1 within d of s2`, per the LIST OP22 VALU VALU LIST reduction."""
    mask = select("name CA within 6 of resn NAG")
    assert _count(mask) > 0
    assert (mask & select("name CA")).tolist() == mask.tolist()


def test_within_needs_its_of(select):
    with pytest.raises(ParserError):
        select("name CA within 6 resn NAG")


def test_beyond_is_the_complement_of_within(select):
    left = select("name CA")
    near = select("name CA within 8 of resn NAG")
    far = select("name CA beyond 8 of resn NAG")
    assert not (near & far).any()
    assert (near | far).tolist() == left.tolist()


def test_near_to_excludes_the_target_itself(select):
    """An atom of the right-hand selection must not select itself."""
    assert not (select("all near_to 5 of resn NAG") & select("resn NAG")).any()


# --------------------------------------------------------------------------- #
# Distances are in Angstrom
# --------------------------------------------------------------------------- #
def test_a_distance_is_angstrom_not_scene_units(select, atoms, viewer):
    """The viewer scales coordinates by ten; a selection distance must not be.

    Comparing an Angstrom distance against scene-unit coordinates silently turns
    `within 5` into `within 0.5` -- invisible on screen, wrong in every count.
    """
    scale = float(getattr(viewer, "_scale_factor", 1.0) or 1.0)
    assert scale != 1.0, "this test is only meaningful when the viewer scales"

    xyz = np.asarray(atoms["xyz"], dtype=float)
    ligand = select("resn NAG")
    distance = np.min(
        np.linalg.norm(xyz[:, None, :] - xyz[None, ligand, :], axis=2), axis=1
    )
    for radius in (3.0, 5.0, 8.0):
        expected = _count((distance <= radius) & ~ligand)
        assert _count(select(f"resn NAG around {radius}")) == expected


def test_a_larger_radius_selects_more(select):
    counts = [_count(select(f"resn NAG around {d}")) for d in (2, 4, 6, 8)]
    assert counts == sorted(counts)
    assert counts[0] < counts[-1]


# --------------------------------------------------------------------------- #
# Atom classes
# --------------------------------------------------------------------------- #
def test_polymer_and_hetatm_are_complementary(select):
    assert (select("polymer") | select("hetatm")).all()
    assert not (select("polymer") & select("hetatm")).any()


def test_backbone_and_sidechain_partition_the_polymer(select):
    assert (select("backbone") | select("sidechain")).tolist() == select(
        "polymer"
    ).tolist()


def test_organic_finds_the_ligand_sugars(select, atoms):
    names = np.char.strip(atoms["res_name"].astype(str))
    organic = select("organic")
    assert organic[np.isin(names, ("NAG", "MUB"))].all()


def test_guide_is_one_atom_per_polymer_residue(select):
    """`guide` is the CA of a protein residue -- what a cartoon is drawn through."""
    assert _count(select("guide")) == _count(select("name CA"))


def test_solvent_is_empty_when_the_entry_has_no_water(select):
    """148L deposits no waters, so this must be empty rather than wrong."""
    assert _count(select("solvent")) == 0


def test_hydro_is_empty_for_an_x_ray_entry(select):
    assert _count(select("hydro")) == 0


# --------------------------------------------------------------------------- #
# Expansion
# --------------------------------------------------------------------------- #
def test_byres_grows_to_whole_residues(select, atoms):
    grown = select("byres name CA")
    assert _count(grown) > _count(select("name CA"))
    # Every atom of every residue that has a CA.
    ids = np.char.add(
        np.char.strip(atoms["chain"].astype(str)),
        np.asarray(atoms["res_id"]).astype(str),
    )
    assert _count(grown) == _count(np.isin(ids, ids[select("name CA")]))


def test_byres_does_not_merge_two_chains_numbered_alike(select, atoms):
    """A residue is chain plus number, not the number alone.

    148L numbers its ligand from 164 upward, so a same-numbered clash needs the
    chain to be part of the key on a dimer; guard the key rather than the entry.
    """
    grown = select("byres chain S and resi 165")
    chains = np.char.strip(atoms["chain"].astype(str))
    assert set(chains[grown].tolist()) == {"S"}


def test_bychain_grows_to_the_chain(select, atoms):
    chains = np.char.strip(atoms["chain"].astype(str))
    assert _count(select("bychain resn NAG")) == _count(chains == "S")


def test_bymol_follows_bonds_not_chains(select, atoms):
    """148L's ligand is covalently bound to Glu26, so it is one molecule with it.

    A 1.51 A Glu26:OE2-MurNAc:C1 bond is the deposited covalent intermediate, so
    a chain-based answer here would be wrong in the other direction.
    """
    chains = np.char.strip(atoms["chain"].astype(str))
    molecule = select("bymol resn NAG")
    assert _count(molecule) > _count(chains == "S")
    assert molecule[chains == "E"].any()


def test_bycalpha_reduces_a_selection_to_its_guide_atoms(select):
    mask = select("bycalpha resi 10-20")
    assert mask.tolist() == (select("byres resi 10-20") & select("guide")).tolist()


def test_first_and_last_pick_one_atom(select):
    assert _count(select("first name CA")) == 1
    assert _count(select("last name CA")) == 1
    assert select("first name CA").tolist() != select("last name CA").tolist()


# --------------------------------------------------------------------------- #
# Logic
# --------------------------------------------------------------------------- #
def test_a_space_means_and(select):
    assert select("polymer name CA").tolist() == select(
        "polymer and name CA"
    ).tolist()


def test_not_inverts(select):
    assert select("not polymer").tolist() == (~select("polymer")).tolist()


def test_minus_subtracts(select):
    """PyMOL added `-` as the complement of `+`: an AND NOT."""
    assert select("polymer - backbone").tolist() == select(
        "polymer and not backbone"
    ).tolist()


def test_a_range_is_not_read_as_a_subtraction(select):
    """`resi 10-20` must stay a range even though `-` also subtracts."""
    assert _count(select("resi 10-20")) == _count(select("resi 10+11+12+13+14+15+16+17+18+19+20"))


def test_parentheses_group(select):
    assert _count(select("polymer and (name CA or name CB)")) == _count(
        select("polymer and name CA")
    ) + _count(select("polymer and name CB"))


def test_all_and_none(select):
    assert select("all").all()
    assert not select("none").any()
    assert select("*").all()


# --------------------------------------------------------------------------- #
# Abbreviations
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "short, long",
    [
        ("c. S", "chain S"),
        ("n. CA", "name CA"),
        ("r. NAG", "resn NAG"),
        ("i. 10-20", "resi 10-20"),
        ("e. C", "elem C"),
        ("bb.", "backbone"),
        ("sc.", "sidechain"),
        ("pol.", "polymer"),
    ],
)
def test_pymol_abbreviations_mean_the_same_thing(select, short, long):
    assert select(short).tolist() == select(long).tolist()


def test_a_value_glued_to_an_abbreviation(select):
    assert select("c.S").tolist() == select("chain S").tolist()


# --------------------------------------------------------------------------- #
# Numeric properties
# --------------------------------------------------------------------------- #
def test_b_factor_comparison(select, atoms):
    b = np.asarray(atoms["bfactor"], dtype=float)
    assert _count(select("b < 20")) == _count(b < 20.0)
    assert _count(select("b > 20")) == _count(b > 20.0)


def test_a_coordinate_comparison_is_in_angstrom(select, atoms):
    """`x < 0` refers to the file's frame, not the viewer's."""
    x = np.asarray(atoms["xyz"], dtype=float)[:, 0]
    assert _count(select("x < 0")) == _count(x < 0.0)


def test_comparison_spellings(select):
    assert select("b <= 20").tolist() == select("b<=20").tolist()
    assert _count(select("b >= 20")) >= _count(select("b > 20"))


# --------------------------------------------------------------------------- #
# Secondary structure
# --------------------------------------------------------------------------- #
def test_ss_selects_helices(select):
    assert _count(select("ss H")) > 0


def test_both_spellings_of_strand_agree(select):
    """PyMOL writes `S`, DSSP-flavoured assigners write `E`."""
    assert select("ss S").tolist() == select("ss E").tolist()


def test_both_spellings_of_loop_agree(select):
    assert select("ss L").tolist() == select("ss C").tolist()


def test_ss_classes_cover_every_atom(select):
    assert (select("ss H") | select("ss S") | select("ss L")).all()


# --------------------------------------------------------------------------- #
# Index and rank
# --------------------------------------------------------------------------- #
def test_index_is_one_based(select):
    assert _count(select("index 1")) == 1
    assert _count(select("index 1-10")) == 10


def test_rank_is_zero_based(select):
    assert np.nonzero(select("rank 0"))[0].tolist() == [0]


# --------------------------------------------------------------------------- #
# pepseq
# --------------------------------------------------------------------------- #
def test_pepseq_finds_a_motif(select):
    """T4 lysozyme begins MNIFEMLR; a motif inside it must match its residues."""
    mask = select("pepseq FEML")
    assert _count(mask) > 0
    assert (mask & select("polymer")).tolist() == mask.tolist()


def test_pepseq_that_matches_nothing_is_empty(select):
    assert _count(select("pepseq WWWWWW")) == 0


# --------------------------------------------------------------------------- #
# Gaps are reported, not hidden
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "expression",
    [
        "masked",          # no picking mask
        "protected",
        "text_type CA",    # no force-field types
        "flag 1",
    ],
)
def test_an_unimplemented_keyword_says_so(select, expression):
    """An empty selection and a missing feature must not look alike.

    Returning nothing is exactly how `resn` hid for so long; anything chimol
    cannot answer names itself instead.
    """
    with pytest.raises(UnsupportedSelection):
        select(expression)


def test_donors_and_acceptors_are_answered_from_the_chemistry(select, atoms):
    """These were refused as "needing assigned chemistry" that already existed.

    `analysis.hbonds.type_atoms` assigns donor and acceptor flags for the
    polar-contact search, from the residue templates and the bond angles. Only
    the keyword was missing -- and its absence took the object menu's
    **hydrogens > add polar** with it, since that entry is
    `h_add (sele) and (donors or acceptors)`.
    """
    donors = select("donors")
    acceptors = select("acceptors")
    assert _count(donors) > 0
    assert _count(acceptors) > 0
    # Every one is a nitrogen, an oxygen or a sulfur; carbon is neither.
    for mask in (donors, acceptors):
        elements = {
            str(e).strip().upper() for e in atoms["element"][mask]
        }
        assert elements <= {"N", "O", "S"}, elements


def test_don_and_acc_are_pymols_spellings(select):
    """`don.` and `acc.`, which is how PyMOL's own menu writes them."""
    assert select("don.").tolist() == select("donors").tolist()
    assert select("acc.").tolist() == select("acceptors").tolist()


def test_byring_grows_to_whole_rings(select):
    """`byring` was refused for want of a ring finder that now exists.

    One atom of each phenylalanine ring comes back as six; a proline's CG comes
    back as five, because `byring` is a question about **connectivity** and a
    proline is as much a ring as a phenylalanine. (The pi finder's planar
    filter is a different question and does exclude proline.)
    """
    assert _count(select("name CZ and resn PHE")) == 5
    assert _count(select("byring (name CZ and resn PHE)")) == 30
    assert _count(select("resn PRO and name CG")) == 3
    assert _count(select("byring (resn PRO and name CG)")) == 15


def test_byring_drops_atoms_that_are_in_no_ring(select):
    """PyMOL clears the mask before its ring finder runs.

    `SELE_RING` does `std::fill_n(base[0].sele_data(), n_atom, 0)` first, so
    `byring (name CA)` answers "the prolines" -- the only CAs inside a ring --
    and not "every CA, plus the prolines' rings", which is what keeping the
    incoming mask would give.
    """
    assert _count(select("name CA")) > 100
    assert _count(select("byring (name CA)")) == 15


def test_an_unknown_name_is_an_error_not_an_empty_answer(select):
    """PyMOL ends the same walk with ``Invalid selection name``.

    This used to assert the opposite -- that a bare word chimol cannot resolve
    "matches nothing here" -- which made a typo indistinguishable from a
    selection that genuinely has no atoms. ``SelectorSelect0`` looks the word up
    as a selection, then as a group, and then errors.
    """
    with pytest.raises(UnknownSelectionName):
        select("some_other_object")


def test_a_question_mark_makes_an_undefined_name_legal(select):
    """PyMOL's ``?sele``: undefined is allowed *here*, and selects nothing."""
    assert _count(select("?some_other_object")) == 0


def test_a_malformed_expression_raises(select):
    for expression in ("name", "resn NAG and", "(name CA", "b <"):
        with pytest.raises((ParserError, UnsupportedSelection)):
            select(expression)
