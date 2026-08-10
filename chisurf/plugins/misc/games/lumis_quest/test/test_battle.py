"""Combat is photophysics, and it steps with no window."""

from __future__ import annotations

import random

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import battle, roster
from chisurf.plugins.misc.games.lumis_quest.api.roster import Creature


def _creature(name, em, ab, ec=60000.0, qy=0.6, protein=False, probe_id=0):
    """Build a creature with chosen stats, so tests do not depend on the data."""
    return Creature(
        probe_id=probe_id, name=name, is_protein=protein,
        emission_nm=em, absorption_nm=ab, ext_coeff=ec, quantum_yield=qy,
    )


@pytest.fixture
def pair():
    """A donor and an acceptor that genuinely couple.

    Returns
    -------
    tuple of Creature
        Donor emitting at 520, acceptor absorbing at 525.
    """
    return _creature("Donor", 520.0, 480.0, probe_id=-1), _creature(
        "Acceptor", 600.0, 525.0, probe_id=-2
    )


def test_a_fighter_starts_at_full_health(pair):
    """And knows how far through its photon budget it is."""
    fighter = battle.Fighter(pair[0])
    assert fighter.hp == pair[0].max_hp and fighter.alive
    assert fighter.bleached == 0.0
    fighter.hp //= 2
    assert 0.4 < fighter.bleached < 0.6


def test_attacking_costs_the_attacker_photons(pair):
    """Emitting bleaches you. That trade is the whole tactical layer."""
    donor, acceptor = pair
    me = battle.Fighter(donor)
    fight = battle.Battle([me], battle.Fighter(acceptor, hp=999), rng=random.Random(1))
    before = me.hp
    fight.attack()
    assert me.hp < before


def test_a_brighter_dye_bleaches_faster():
    """Quantum yield is both the damage and the cost."""
    bright = _creature("Bright", 520.0, 480.0, qy=0.95, probe_id=-3)
    dim = _creature("Dim", 520.0, 480.0, qy=0.15, probe_id=-4)
    target = _creature("Target", 600.0, 525.0, probe_id=-5)

    # Measured as a fraction of each dye's own photon budget, which is the
    # claim: a bright dye has both a smaller budget and a faster burn, and the
    # absolute loss per shot can come out equal while the fraction does not.
    spent = []
    for creature in (bright, dim):
        me = battle.Fighter(creature)
        fight = battle.Battle([me], battle.Fighter(target, hp=999), rng=random.Random(2))
        fight.attack()
        spent.append(me.bleached)
    assert spent[0] > spent[1], spent
    assert bright.max_hp < dim.max_hp, "and it has less to spend in the first place"


def test_the_fight_ends_when_the_opponent_bleaches(pair):
    """And it is recorded as a win."""
    donor, acceptor = pair
    fight = battle.Battle([battle.Fighter(donor)], battle.Fighter(acceptor, hp=1),
                          rng=random.Random(3))
    fight.attack()
    assert fight.finished and fight.won


def test_the_fight_ends_when_the_whole_team_bleaches(pair):
    """A loss is a loss."""
    donor, acceptor = pair
    me = battle.Fighter(donor, hp=1)
    fight = battle.Battle([me], battle.Fighter(acceptor, hp=999), rng=random.Random(4),
                          opponent_power=40.0)
    for _ in range(6):
        if fight.finished:
            break
        fight.attack()
    assert fight.finished and not fight.won


def test_the_log_reads_in_the_order_things_happened(pair):
    """Regression: the opponent's reply was landing ahead of the shot."""
    donor, acceptor = pair
    fight = battle.Battle([battle.Fighter(donor)], battle.Fighter(acceptor, hp=999),
                          rng=random.Random(5))
    fight.attack()
    assert len(fight.log) >= 2
    assert "Donor" in fight.log[0].text
    assert "Acceptor" in fight.log[1].text


def test_swapping_brings_a_partner_forward_and_costs_the_turn(pair):
    """A swap is a real decision because the opponent still acts."""
    donor, acceptor = pair
    second = _creature("Second", 560.0, 515.0, probe_id=-6)
    team = [battle.Fighter(donor), battle.Fighter(second)]
    fight = battle.Battle(team, battle.Fighter(acceptor, hp=999), rng=random.Random(6))
    before = team[1].hp
    fight.swap(1)
    assert fight.active.creature.name == "Second"
    assert team[1].hp < before, "the opponent acts during a swap"

    assert "Already out" in fight.swap(1).text
    assert "Nobody" in fight.swap(9).text


def test_a_bleached_creature_cannot_be_swapped_in(pair):
    """It has no photons left."""
    donor, acceptor = pair
    spare = battle.Fighter(_creature("Spare", 560.0, 515.0, probe_id=-7), hp=0)
    fight = battle.Battle([battle.Fighter(donor), spare], battle.Fighter(acceptor, hp=999))
    assert "bleached" in fight.swap(1).text
    assert fight.active.creature.name == "Donor"


def test_fleeing_ends_it_with_nothing_gained(pair):
    """No win, no loss."""
    donor, acceptor = pair
    fight = battle.Battle([battle.Fighter(donor)], battle.Fighter(acceptor))
    fight.flee()
    assert fight.finished and fight.fled and not fight.won
    assert "already over" in fight.attack().text


def test_a_wild_opponent_is_the_same_every_visit():
    """A page's guardian must not reshuffle: a place is a place."""
    pool = [_creature(f"c{i}", 450.0 + i * 5, 430.0 + i * 5, probe_id=-100 - i) for i in range(40)]
    first = battle.wild_opponent("docs/concepts/fret.md", 0.6, pool)
    second = battle.wild_opponent("docs/concepts/fret.md", 0.6, pool)
    assert first.creature.name == second.creature.name
    assert first.hp == second.hp

    other = battle.wild_opponent("docs/guides/01_start.md", 0.6, pool)
    assert other.creature.name != first.creature.name or other.hp != first.hp


def test_a_remote_page_holds_a_stronger_guardian():
    """Difficulty picks which creature, not merely how much health it has.

    Scaling HP alone left remote pages guarded by whatever weakling came up,
    which pointed the reward gradient somewhere the danger did not.
    """
    pool = [
        _creature(f"c{i}", 500.0, 480.0, ec=10000.0 + i * 4000.0, probe_id=-200 - i)
        for i in range(40)
    ]
    near = [battle.wild_opponent(f"p{i}", 0.05, pool).creature.attack for i in range(12)]
    far = [battle.wild_opponent(f"p{i}", 0.95, pool).creature.attack for i in range(12)]
    assert sum(far) / len(far) > sum(near) / len(near) * 1.5


def test_an_empty_pool_is_an_error_not_a_crash_later():
    """Better here than as a mysterious failure mid-encounter."""
    with pytest.raises(ValueError):
        battle.wild_opponent("x", 0.5, [])
    with pytest.raises(ValueError):
        battle.Battle([], battle.Fighter(_creature("x", 500.0, 480.0)))


def test_a_real_encounter_from_the_shipped_data_resolves():
    """End to end on the actual roster, so the wiring is exercised."""
    creatures = [c for c in roster.load_roster() if not c.estimated]
    if not creatures:
        pytest.skip("spectra.db is not present in this install")
    team = [battle.Fighter(c) for c in roster.starters()]
    opponent = battle.wild_opponent("docs/concepts/fret.md", 0.72, creatures)
    fight = battle.Battle(team, opponent, rng=random.Random(11))
    for _ in range(40):
        if fight.finished:
            break
        fight.attack()
    assert fight.finished
    assert fight.log and all(turn.text for turn in fight.log)
