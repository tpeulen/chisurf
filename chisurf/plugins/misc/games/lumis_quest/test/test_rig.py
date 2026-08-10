"""A crafted light path, evaluated by the application's own simulator."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.misc.games.lumis_quest.api import gear, rig, roster


def _band(centre, width, slot, probe_id=-1, name="part"):
    """A synthetic part, so tests do not depend on which catalogue ships."""
    return gear.Gear(
        probe_id=probe_id, name=name, slot=slot,
        curve=np.exp(-0.5 * ((gear.GRID - centre) / (width / 2.355)) ** 2),
    )


def test_an_empty_path_passes_everything():
    """A partial rig is a working rig with less selectivity, not a blindfold."""
    empty = rig.Rig()
    assert not empty.complete and empty.parts == []
    assert empty.response(500.0) == 1.0 and empty.sees(700.0)
    assert empty.summary == "bare path"


def test_parts_go_into_their_own_slots():
    """A rig is assembled from what you happen to have."""
    path = rig.Rig()
    path.fit(_band(520.0, 40.0, "emission", -1))
    path.fit(_band(480.0, 30.0, "excitation", -2))
    assert path.emission is not None and path.excitation is not None
    assert not path.complete
    path.fit(_band(500.0, 100.0, "dichroic", -3))
    path.fit(_band(550.0, 200.0, "detector", -4))
    assert path.complete and len(path.parts) == 4


def test_a_longer_path_is_more_selective_not_dimmer():
    """Regression: multiplying four curves made a complete rig blind everywhere.

    Every extra element scaled the whole curve down, so a fully assembled rig
    scored worse than a bare eye at every wavelength -- which reads as a balance
    problem and was arithmetic.
    """
    path = rig.Rig(
        excitation=_band(560.0, 40.0, "excitation", -1),
        emission=_band(560.0, 40.0, "emission", -2),
        detector=_band(560.0, 300.0, "detector", -3),
    )
    assert path.response(560.0) > 1.0, "a matched path must beat a bare eye"
    assert path.response(460.0) < 0.3, "and block what it is not tuned for"
    assert path.sees(560.0) and not path.sees(460.0)


def test_a_dichroic_reflects_what_it_does_not_transmit():
    """It is a beamsplitter, not an absorber.

    Multiplying its transmission in blindly made every rig blind at exactly the
    wavelengths its beamsplitter was chosen to steer.
    """
    edge = gear.Gear(
        probe_id=-9, name="edge", slot="dichroic",
        curve=(gear.GRID > 550.0).astype(float),
    )
    path = rig.Rig(dichroic=edge)
    curve = path.curve()
    # Both arms survive: nothing in the band is thrown away.
    assert curve[gear.GRID > 560.0].min() > 0.9
    assert curve[gear.GRID < 540.0].min() > 0.9


@pytest.fixture(scope="module")
def creatures():
    """Fully measured creatures from the shipped database.

    Returns
    -------
    list of Creature
        Skips the module when the database is absent.
    """
    pool = [c for c in roster.load_roster() if not c.estimated]
    if not pool:
        pytest.skip("spectra.db is not present in this install")
    return pool


def test_collection_is_high_for_what_the_path_is_tuned_for(creatures):
    """And low for what it is not."""
    target = min(creatures, key=lambda c: abs(c.emission_nm - 610.0))
    other = min(creatures, key=lambda c: abs(c.emission_nm - 515.0))
    path = rig.Rig(emission=_band(610.0, 40.0, "emission", -1))
    assert path.collection(target) > path.collection(other) * 3


def test_crosstalk_is_leakage_relative_to_the_wanted_signal(creatures):
    """The number is named for what it measures, not for one of its uses.

    A rig tuned for a 610 nm emitter collects it at full strength -- excellent,
    and not leakage. Crosstalk is that collection *relative to* the channel's
    intended occupant.
    """
    acceptor = min(creatures, key=lambda c: abs(c.emission_nm - 610.0))
    donor = min(creatures, key=lambda c: abs(c.emission_nm - 515.0))
    path = rig.Rig(emission=_band(610.0, 40.0, "emission", -1))

    leak = path.crosstalk(donor, acceptor)
    assert 0.0 <= leak < 0.5, "a well-separated pair should barely bleed through"
    assert path.crosstalk(acceptor, acceptor) == pytest.approx(1.0, abs=1e-6)


def test_crosstalk_against_a_channel_that_collects_nothing_is_zero(creatures):
    """Leakage relative to nothing is not a meaningful number."""
    donor, acceptor = creatures[0], creatures[-1]
    blind = rig.Rig(emission=_band(300.0, 2.0, "emission", -1))
    assert blind.crosstalk(donor, acceptor) == 0.0


def test_the_forster_radius_comes_from_the_simulator(creatures):
    """A crafted rig and a real instrument must not disagree about the physics.

    R0 for a green donor and a red acceptor should land in the tens of
    angstrom, which is what the literature reports for such pairs.
    """
    donor = min(creatures, key=lambda c: abs(c.emission_nm - 519.0))
    acceptor = min(creatures, key=lambda c: abs(c.emission_nm - 610.0))
    radius = rig.Rig().forster_radius(donor, acceptor)
    if radius == 0.0:
        pytest.skip("the spectra needed are not stored for this pair")
    assert 20.0 < radius < 90.0, radius


def test_a_missing_spectrum_degrades_rather_than_raising(creatures):
    """A pair the database cannot describe yields zero, not an exception."""
    from chisurf.plugins.misc.games.lumis_quest.api.roster import Creature

    ghost = Creature(
        probe_id=-12345, name="ghost", is_protein=False,
        emission_nm=520.0, absorption_nm=490.0, ext_coeff=50000.0, quantum_yield=0.5,
    )
    assert rig.Rig().forster_radius(ghost, ghost) == 0.0
    assert 0.0 <= rig.Rig().collection(ghost) <= 1.0
