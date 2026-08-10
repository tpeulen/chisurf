"""The creature roster is read from real measurements, and degrades honestly."""

from __future__ import annotations

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import roster


@pytest.fixture(scope="module")
def creatures():
    """The roster from the shipped database.

    Returns
    -------
    tuple of Creature
        Skips the module when the database is not installed.
    """
    loaded = roster.load_roster()
    if not loaded:
        pytest.skip("spectra.db is not present in this install")
    return loaded


def test_the_roster_is_large_and_real(creatures):
    """A bestiary of hundreds, straight out of the shipped database."""
    assert len(creatures) > 300
    assert all(350.0 <= c.emission_nm <= 800.0 for c in creatures)
    assert all(c.ext_coeff > 0 and 0.0 < c.quantum_yield <= 1.0 for c in creatures)


def test_it_reads_as_a_spectrum(creatures):
    """Sorted by emission, so the roster is ordered by colour."""
    assert [c.emission_nm for c in creatures] == sorted(c.emission_nm for c in creatures)


def test_missing_stats_are_flagged_not_invented(creatures):
    """A creature without a measured value says so.

    Only a third of the database carries a complete stat set. Filling the gaps
    silently would have the game teach numbers nobody measured.
    """
    estimated = [c for c in creatures if c.estimated]
    assert estimated, "some entries really are incomplete; this should catch them"
    for creature in estimated:
        assert creature.estimated <= {"ext_coeff", "quantum_yield", "absorption_nm"}
        assert "~" in creature.summary, "an estimated stat must be visible to the player"
    assert any(not c.estimated for c in creatures), "and some are fully measured"


def test_non_numeric_properties_do_not_break_the_read():
    """The property table is EAV text and holds `Origin` and `Material Name`.

    A float cast over the column raises; every read goes through the parser.
    """
    assert roster._number("45000") == 45000.0
    assert roster._number("Atto Organic Dye") is None
    assert roster._number(None) is None
    assert roster._number("nan") is None


def test_brightness_drives_attack_and_quantum_yield_costs_stamina(creatures):
    """The trade every fluorophore makes, as a game stat."""
    brightest = max(creatures, key=lambda c: c.brightness)
    dimmest = min(creatures, key=lambda c: c.brightness)
    assert brightest.attack > dimmest.attack

    # Two dyes of the same class: the higher quantum yield bleaches sooner.
    dyes = [c for c in creatures if not c.is_protein]
    high = max(dyes, key=lambda c: c.quantum_yield)
    low = min(dyes, key=lambda c: c.quantum_yield)
    assert high.max_hp < low.max_hp


def test_the_type_chart_is_the_real_overlap_integral(creatures):
    """A donor is strong against what absorbs where it emits, and weak elsewhere.

    This is the claim that makes the roster worth using at all, so it is
    asserted against the shipped spectra rather than trusted.
    """
    measured = [c for c in creatures if not c.estimated]
    donor = min(measured, key=lambda c: abs(c.emission_nm - 520.0))

    matched = min(measured, key=lambda c: abs(c.absorption_nm - donor.emission_nm))
    mismatched = min(measured, key=lambda c: abs(c.absorption_nm - 380.0))

    assert roster.effectiveness(donor, matched) > roster.effectiveness(donor, mismatched)
    assert roster.effectiveness(donor, matched) > 1.2


def test_effectiveness_never_reaches_zero(creatures):
    """A move that can do nothing is a move nobody ever picks."""
    a, b = creatures[0], creatures[-1]
    assert roster.effectiveness(a, b) >= 0.5
    assert roster.effectiveness(a, a) <= 2.0


def test_starters_span_the_spectrum(creatures):
    """A starting team has to be able to answer more than one colour."""
    chosen = roster.starters(3)
    assert len(chosen) == 3
    assert all(not c.estimated for c in chosen), "starters must be fully measured"
    wavelengths = sorted(c.emission_nm for c in chosen)
    assert wavelengths[-1] - wavelengths[0] > 120.0
