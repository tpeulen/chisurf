"""The selection keyword table, against PyMOL's ``Keyword[]``.

This table exists because the parser used to carry its own hand-maintained tuple
of property names, which had drifted from the evaluator: ``resn`` was implemented
and evaluated correctly but never *parsed*, so ``resn NAG`` fell through to an
implicit ``AND`` of two bare identifiers and matched nothing at all. The tests
here pin the vocabulary and the arities so that cannot recur.
"""

from __future__ import annotations

import pytest
from chimol.core.selection.keywords import (
    CANONICAL,
    KEYWORDS,
    Arity,
    lookup,
    split_keyword,
)


# --------------------------------------------------------------------------- #
# The vocabulary
# --------------------------------------------------------------------------- #
def test_the_keyword_that_started_this_is_present():
    """`resn` is the regression: parsed, not merely evaluated."""
    keyword = lookup("resn")
    assert keyword is not None
    assert keyword.canonical == "resn"
    assert keyword.arity is Arity.STRING


@pytest.mark.parametrize(
    "alias, canonical",
    [
        # PyMOL's own spellings, from Keyword[] in layer3/Selector.cpp.
        ("resname", "resn"),
        ("r.", "resn"),
        ("r;", "resn"),
        ("residue", "resi"),
        ("resid", "resi"),
        ("i.", "resi"),
        ("symbol", "elem"),
        ("element", "elem"),
        ("e.", "elem"),
        ("n.", "name"),
        ("c.", "chain"),
        ("segment", "segi"),
        ("segid", "segi"),
        ("s.", "segi"),
        ("model", "object"),
        ("o.", "object"),
        ("m.", "object"),
        ("het", "hetatm"),
        ("hydrogens", "hydro"),
        ("h.", "hydro"),
        ("byresidue", "byres"),
        ("br.", "byres"),
        ("bymol", "bymolecule"),
        ("bm.", "bymolecule"),
        ("bc.", "bychain"),
        ("byobj", "byobject"),
        ("w.", "within"),
        ("a.", "around"),
        ("x.", "expand"),
        ("nto.", "near_to"),
        ("be.", "beyond"),
        ("bb.", "backbone"),
        ("sc.", "sidechain"),
        ("sol.", "solvent"),
        ("org.", "organic"),
        ("pol.", "polymer"),
        ("ps.", "pepseq"),
        ("*", "all"),
    ],
)
def test_pymol_aliases_resolve(alias, canonical):
    keyword = lookup(alias)
    assert keyword is not None, f"{alias!r} is in PyMOL's table but not ours"
    assert keyword.canonical == canonical


def test_lookup_ignores_case():
    assert lookup("ResN").canonical == "resn"
    assert lookup("BYRES").canonical == "byres"


def test_a_name_that_is_not_a_keyword_returns_none():
    """Object names must not be mistaken for keywords."""
    assert lookup("1dg3") is None
    assert lookup("my_selection") is None


# --------------------------------------------------------------------------- #
# Arity -- the STYP_ suffix of each SELE_ code
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "keyword, arity",
    [
        # 's' -- one value list
        ("name", Arity.STRING),
        ("resn", Arity.STRING),
        ("ss", Arity.STRING),
        # 'z' -- no argument
        ("hetatm", Arity.FLAG),
        ("solvent", Arity.FLAG),
        ("backbone", Arity.FLAG),
        ("metals", Arity.FLAG),
        # 'x' -- compared against a number
        ("b", Arity.NUMERIC),
        ("q", Arity.NUMERIC),
        ("x", Arity.NUMERIC),
        ("partial_charge", Arity.NUMERIC),
        # '1' -- one selection
        ("byres", Arity.UNARY),
        ("bychain", Arity.UNARY),
        ("first", Arity.UNARY),
        ("last", Arity.UNARY),
        # '2' -- infix
        ("and", Arity.BINARY),
        ("or", Arity.BINARY),
        ("in", Arity.BINARY),
        # STYP_PRP1 -- postfix with a value
        ("around", Arity.DIST),
        ("expand", Arity.DIST),
        ("gap", Arity.DIST),
        ("extend", Arity.DIST),
        # STYP_OP22 -- infix with a distance and 'of'
        ("within", Arity.DIST_OF),
        ("near_to", Arity.DIST_OF),
        ("beyond", Arity.DIST_OF),
    ],
)
def test_arity_matches_the_styp_code(keyword, arity):
    assert lookup(keyword).arity is arity


def test_around_and_within_have_different_fixity():
    """The distinction the old parser got wrong.

    ``STYP_PRP1`` reduces ``LIST PRP1 PVAL`` and ``STYP_OP22`` reduces
    ``LIST OP22 VALU VALU LIST``, so ``around`` is postfix and ``within`` infix.
    Treating both as prefix made ``name CA around 5`` a parse error.
    """
    assert lookup("around").arity is Arity.DIST
    assert lookup("within").arity is Arity.DIST_OF


# --------------------------------------------------------------------------- #
# Glued abbreviations
# --------------------------------------------------------------------------- #
def test_a_value_glued_to_an_abbreviation_splits():
    """`c.A` and `c. A` mean the same thing in PyMOL."""
    keyword, remainder = split_keyword("c.A")
    assert (keyword.canonical, remainder) == ("chain", "A")


def test_a_bare_abbreviation_leaves_no_remainder():
    keyword, remainder = split_keyword("c.")
    assert (keyword.canonical, remainder) == ("chain", "")


def test_the_longest_abbreviation_wins():
    """`nt.` is numeric_type, not `n.` followed by `t.`."""
    keyword, remainder = split_keyword("nt.foo")
    assert (keyword.canonical, remainder) == ("numeric_type", "foo")


def test_a_dotted_keyword_is_not_split_as_an_abbreviation():
    keyword, remainder = split_keyword("polymer.protein")
    assert (keyword.canonical, remainder) == ("polymer.protein", "")


def test_splitting_a_plain_name_gives_nothing():
    assert split_keyword("1dg3") is None
    assert split_keyword("") is None


# --------------------------------------------------------------------------- #
# Table integrity
# --------------------------------------------------------------------------- #
#: Canonical names that are internal labels rather than something a user types.
#: PyMOL spells these only as a symbol or only as an abbreviation, so the
#: canonical name is ours: `-` for subtract, `%` for a named selection, `p.` for
#: a custom property, `hba.`/`hbd.` for the hydrogen-bond classes.
_INTERNAL_LABELS = {"subtract", "selection", "p", "hba", "hbd"}


def test_every_canonical_name_is_its_own_alias():
    """Otherwise the canonical spelling would not parse."""
    for canonical, (_, aliases) in CANONICAL.items():
        assert canonical in aliases or canonical in _INTERNAL_LABELS, (
            f"{canonical!r} cannot be written"
        )


def test_no_alias_means_two_things():
    seen: dict[str, str] = {}
    for canonical, (_, aliases) in CANONICAL.items():
        for alias in aliases:
            assert alias not in seen, f"{alias!r} maps to both {seen[alias]!r} and {canonical!r}"
            seen[alias] = canonical


def test_aliases_are_lower_case():
    """Lookup lower-cases its argument, so an upper-case key is unreachable."""
    assert all(alias == alias.lower() for alias in KEYWORDS)
