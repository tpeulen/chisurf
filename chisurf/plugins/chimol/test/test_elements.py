"""The transcribed atomic-mass table, checked the way carried data has to be.

Transcribed from PyMOL's ``chempy.atomic_mass`` by ``analysis/make_elements.py``.
A carried table is verified through **its own properties plus its size**: a
*truncated* extraction is self-consistent and passes every spot check that
happens to fall inside it, which is exactly how a half-copied table survives
review. So the count is asserted alongside the values -- the same rule the 547
space groups are held to.
"""

from __future__ import annotations

import pytest
from chimol.analysis.elements import (
    ATOMIC_MASS,
    mass_of,
    masses_for,
)


def test_the_table_is_not_truncated():
    """PyMOL lists ~109 distinct symbols once the case duplicates are folded."""
    assert len(ATOMIC_MASS) > 100, len(ATOMIC_MASS)


def test_the_light_elements_are_the_iupac_values():
    """The ones that decide a protein's weight, so they are worth pinning."""
    assert mass_of("H") == pytest.approx(1.00794)
    assert mass_of("C") == pytest.approx(12.0107)
    assert mass_of("N") == pytest.approx(14.0067)
    assert mass_of("O") == pytest.approx(15.9994)
    assert mass_of("S") == pytest.approx(32.065)
    assert mass_of("P") == pytest.approx(30.973762)


def test_lookup_is_case_insensitive():
    """A PDB element column is written both `Fe` and `FE`.

    A table that knows only one spelling silently drops every metal in half the
    files in the world -- and drops them to *nothing*, not to an error.
    """
    assert mass_of("Fe") == mass_of("FE") == mass_of("fe") == pytest.approx(55.845)
    assert mass_of(" se ") == pytest.approx(78.96)


def test_masses_rise_with_the_elements_in_a_period():
    """A structural check rather than a value one: it fails on a shifted table.

    An extraction that dropped a row would leave the symbols paired with their
    neighbours' masses, which every individual spot check above could still
    pass.
    """
    period = ["LI", "BE", "B", "C", "N", "O", "F", "NE"]
    values = [mass_of(symbol) for symbol in period]
    assert all(a < b for a, b in zip(values, values[1:])), values


def test_an_unknown_symbol_is_none_rather_than_a_guess():
    """Reported, never defaulted: a weight is wrong in a way nobody can see if
    an unrecognised atom is quietly counted as carbon -- or as zero.
    """
    assert mass_of("XX") is None
    assert mass_of("") is None


def test_masses_for_reports_how_many_it_did_not_know():
    values, unknown = masses_for(["C", "O", "ZZ"])
    assert unknown == 1
    assert values[0] == pytest.approx(12.0107)
    assert values[2] == 0.0
