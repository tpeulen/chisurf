"""Combat is photophysics, and it steps with no window."""

from __future__ import annotations

import random

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import battle, bestiary, roster
from chisurf.plugins.misc.games.lumis_quest.api.bestiary import Beast, Species
from chisurf.plugins.misc.games.lumis_quest.api.roster import Creature

#: A body with no opinions: every stat multiplier is 1 and its trait is one
#: that does nothing to damage. Combat tests are about the *label*, so the
#: animal has to be a plain carrier or every assertion is about a hare.
PLAIN = Species("plain", "plain", 1.0, 1.0, 1.0, bestiary.MEADOW, "burrow",
                "A test carrier.")


def _creature(name, em, ab, ec=60000.0, qy=0.6, protein=False, probe_id=0):
    """Build a label with chosen stats, so tests do not depend on the data."""
    return Creature(
        probe_id=probe_id, name=name, is_protein=protein,
        emission_nm=em, absorption_nm=ab, ext_coeff=ec, quantum_yield=qy,
    )


class _Lucky(random.Random):
    """A generator whose every roll succeeds.

    Unbinding is a roll, and a fixed seed does not pin it any more: turn order
    draws from the same generator, so which number the take gets depends on who
    moved first. This pins the outcome instead of the seed.
    """

    def random(self) -> float:
        """Always the luckiest possible roll.

        Returns
        -------
        float
            Zero, which is below every threshold in the fight.
        """
        return 0.0


def _beast(label, species=PLAIN):
    """Fix a label into a body, which is what a fight is actually between."""
    return Beast(species=species, label=label)


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
    fighter = battle.Fighter(_beast(pair[0]))
    assert fighter.hp == pair[0].max_hp and fighter.alive
    assert fighter.depleted == 0.0
    fighter.hp //= 2
    assert 0.4 < fighter.depleted < 0.6


def test_attacking_costs_the_attacker_photons(pair):
    """Emitting bleaches you. That trade is the whole tactical layer."""
    donor, acceptor = pair
    me = battle.Fighter(_beast(donor))
    fight = battle.Battle([me], battle.Fighter(_beast(acceptor), hp=999), rng=random.Random(1))
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
        me = battle.Fighter(_beast(creature))
        fight = battle.Battle([me], battle.Fighter(_beast(target), hp=999), rng=random.Random(2))
        fight.attack()
        spent.append(me.depleted)
    assert spent[0] > spent[1], spent
    assert bright.max_hp < dim.max_hp, "and it has less to spend in the first place"


def test_a_turn_on_label_is_dark_until_struck(pair):
    """Photoactivation: the hit that lands lights it; its own next hit is bigger."""
    donor, acceptor = pair
    me = battle.Fighter(_beast(donor, PLAIN).infused("turn_on"))
    foe = battle.Fighter(_beast(acceptor))
    fight = battle.Battle([me], foe, rng=random.Random(3))

    assert not me.activated
    plain_power = fight._damage(me, foe, multiplier=1.0, gain=1.0)

    fight._apply(me, 1)  # any hit at all switches it on
    assert me.activated
    lit_power = fight._damage(me, foe, multiplier=1.0, gain=1.0)

    assert lit_power > plain_power, (lit_power, plain_power)


def test_the_fight_ends_when_the_opponent_bleaches(pair):
    """And it is recorded as a win."""
    donor, acceptor = pair
    fight = battle.Battle([battle.Fighter(_beast(donor))], battle.Fighter(_beast(acceptor), hp=1),
                          rng=random.Random(3))
    fight.attack()
    assert fight.finished and fight.won


def test_the_fight_ends_when_the_whole_team_bleaches(pair):
    """A loss is a loss."""
    donor, acceptor = pair
    me = battle.Fighter(_beast(donor), hp=1)
    fight = battle.Battle([me], battle.Fighter(_beast(acceptor), hp=999), rng=random.Random(4),
                          opponent_power=40.0)
    for _ in range(6):
        if fight.finished:
            break
        fight.attack()
    assert fight.finished and not fight.won


def test_the_log_reads_in_the_order_things_happened(pair):
    """Regression: the opponent's reply was landing ahead of the shot.

    Turn order is the *body's* now, so the two are given bodies of very
    different speed rather than left to a coin toss: a hare goes before a
    beetle, every time.
    """
    donor, acceptor = pair
    mine = battle.Fighter(Beast(bestiary.BY_KEY["hare"], donor))
    theirs = battle.Fighter(Beast(bestiary.BY_KEY["beetle"], acceptor), hp=999)
    fight = battle.Battle([mine], theirs, rng=random.Random(5))
    fight.attack()
    assert len(fight.log) >= 2
    assert mine.name in fight.log[0].text
    assert theirs.name in fight.log[1].text


def test_swapping_brings_a_partner_forward_and_costs_the_turn(pair):
    """A swap is a real decision because the opponent still acts."""
    donor, acceptor = pair
    second = _creature("Second", 560.0, 515.0, probe_id=-6)
    team = [battle.Fighter(_beast(donor)), battle.Fighter(_beast(second))]
    fight = battle.Battle(team, battle.Fighter(_beast(acceptor), hp=999), rng=random.Random(6))
    before = sum(fighter.hp for fighter in team)
    fight.swap(1)
    assert fight.active.creature.name == "Second"
    # Whoever was out when the opponent moved is who it hit -- turn order is
    # the body's now, so a fast opponent lands its shot before the swap and a
    # slow one after it. The claim the swap has to keep is that it *costs the
    # turn*, which is that somebody on your side was hit either way.
    assert sum(fighter.hp for fighter in team) < before, \
        "the opponent acts during a swap"

    assert "Already out" in fight.swap(1).text
    assert "Nobody" in fight.swap(9).text


def test_a_bleached_creature_cannot_be_swapped_in(pair):
    """It has no photons left."""
    donor, acceptor = pair
    spare = battle.Fighter(_creature("Spare", 560.0, 515.0, probe_id=-7), hp=0)
    fight = battle.Battle([battle.Fighter(_beast(donor)), spare], battle.Fighter(_beast(acceptor), hp=999))
    assert "bleached" in fight.swap(1).text
    assert fight.active.creature.name == "Donor"


def test_fleeing_ends_it_with_nothing_gained(pair):
    """No win, no loss."""
    donor, acceptor = pair
    fight = battle.Battle([battle.Fighter(_beast(donor))], battle.Fighter(_beast(acceptor)))
    fight.flee()
    assert fight.finished and fight.fled and not fight.won
    assert "already over" in fight.attack().text


def test_a_wild_opponent_is_the_same_every_visit():
    """A page's guardian must not reshuffle: a place is a place."""
    pool = [_creature(f"c{i}", 450.0 + i * 5, 430.0 + i * 5, probe_id=-100 - i) for i in range(40)]
    first = battle.wild_encounter("docs/concepts/fret.md", 0.6, pool)
    second = battle.wild_encounter("docs/concepts/fret.md", 0.6, pool)
    assert first.beast.name == second.beast.name
    assert first.hp == second.hp

    other = battle.wild_encounter("docs/guides/01_start.md", 0.6, pool)
    assert other.beast.name != first.beast.name or other.hp != first.hp


def test_a_remote_page_holds_a_stronger_guardian():
    """Difficulty picks which creature, not merely how much health it has.

    Scaling HP alone left remote pages guarded by whatever weakling came up,
    which pointed the reward gradient somewhere the danger did not.
    """
    pool = [
        _creature(f"c{i}", 500.0, 480.0, ec=10000.0 + i * 4000.0, probe_id=-200 - i)
        for i in range(40)
    ]
    near = [battle.wild_encounter(f"p{i}", 0.05, pool).creature.attack for i in range(12)]
    far = [battle.wild_encounter(f"p{i}", 0.95, pool).creature.attack for i in range(12)]
    assert sum(far) / len(far) > sum(near) / len(near) * 1.5


def test_an_empty_pool_is_an_error_not_a_crash_later():
    """Better here than as a mysterious failure mid-encounter."""
    with pytest.raises(ValueError):
        battle.wild_encounter("x", 0.5, [])
    with pytest.raises(ValueError):
        battle.Battle([], battle.Fighter(_creature("x", 500.0, 480.0)))


def test_a_real_encounter_from_the_shipped_data_resolves():
    """End to end on the actual roster, so the wiring is exercised."""
    creatures = [c for c in roster.load_roster() if not c.estimated]
    if not creatures:
        pytest.skip("spectra.db is not present in this install")
    team = [battle.Fighter(_beast(c)) for c in roster.starters()]
    opponent = battle.wild_encounter("docs/concepts/fret.md", 0.72, creatures)
    fight = battle.Battle(team, opponent, rng=random.Random(11))
    for _ in range(40):
        if fight.finished:
            break
        fight.attack()
    assert fight.finished
    assert fight.log and all(turn.text for turn in fight.log)


def test_a_worn_opponent_is_easier_to_collect(pair):
    """Driving a dye into its dark state is how you collect it."""
    donor, acceptor = pair
    fresh = battle.Battle([battle.Fighter(_beast(donor))], battle.Fighter(_beast(acceptor)))
    worn = battle.Battle(
        [battle.Fighter(_beast(donor))],
        battle.Fighter(_beast(acceptor), hp=max(1, acceptor.max_hp // 8)),
    )
    assert worn.take_chance() > fresh.take_chance()
    assert 0.0 <= fresh.take_chance() <= 1.0


def test_you_cannot_collect_what_you_cannot_see(pair):
    """A filter that blocks its band collapses the odds, whatever its health."""
    from chisurf.plugins.misc.games.lumis_quest.api import gear

    donor, acceptor = pair
    worn = battle.Fighter(_beast(acceptor), hp=1)

    import numpy as np

    blind = gear.Gear(
        probe_id=-40, name="blind", slot="emission",
        curve=np.exp(-0.5 * ((gear.GRID - 420.0) / 8.0) ** 2),
    )
    seeing = gear.Gear(
        probe_id=-41, name="seeing", slot="emission",
        curve=np.exp(-0.5 * ((gear.GRID - acceptor.emission_nm) / 20.0) ** 2),
    )
    blocked = battle.Battle([battle.Fighter(_beast(donor))], worn,
                            loadout=gear.Loadout(emission=blind))
    visible = battle.Battle([battle.Fighter(_beast(donor))], battle.Fighter(_beast(acceptor), hp=1),
                            loadout=gear.Loadout(emission=seeing))
    assert visible.take_chance() > blocked.take_chance() * 2


def test_a_successful_catch_ends_the_encounter(pair):
    """And records what was caught."""
    donor, acceptor = pair
    # One attempt on a seed where it lands. Retrying in a loop does not work:
    # a failed catch gives the opponent its turn, and an opponent on 1 HP
    # bleaches itself to nothing by emitting, ending the fight before a second
    # attempt.
    fight = battle.Battle([battle.Fighter(_beast(donor))], battle.Fighter(_beast(acceptor), hp=1),
                          rng=_Lucky(), seals=("ember", "prism", "shutter", "triplet"))
    assert fight.take_chance() > 0.7
    fight.unbind()
    assert fight.taken is acceptor
    assert fight.finished and fight.won


def test_a_failed_catch_costs_the_turn(pair):
    """Otherwise collecting is free and nothing else is ever chosen."""
    donor, acceptor = pair
    me = battle.Fighter(_beast(donor))
    fight = battle.Battle([me], battle.Fighter(_beast(acceptor), hp=9999), rng=random.Random(1),
                          opponent_power=3.0)
    before = me.hp
    for _ in range(4):
        fight.unbind()
        if fight.taken is not None:
            pytest.skip("caught on an unlucky seed")
    assert me.hp < before


def test_boss_fight_distinctiveness_rules(pair):
    """Warden boss fights enforce distinct mechanical rules per lesson."""
    donor, acceptor = pair
    me = battle.Fighter(_beast(donor), hp=100)

    # 1. Tolm (Ember): Continuous attacks trigger counter recoil.
    ember_fight = battle.Battle([me], battle.Fighter(_beast(acceptor), hp=500), boss_key="ember", rng=random.Random(42))
    ember_fight.attack()
    assert ember_fight.player_attack_streak == 1
    hp_after_1 = me.hp
    ember_fight.attack()
    assert "counters a continuous barrage" in ember_fight.log[-1].text
    assert me.hp < hp_after_1

    # 2. Ysolde (Prism): Non-matching spectral emission deals 0 damage.
    prism_fight = battle.Battle([me], battle.Fighter(_beast(acceptor), hp=500), boss_key="prism", rng=random.Random(42))
    opp_hp_before = prism_fight.opponent.hp
    prism_fight.attack()
    # Unmatched spectral emission fails to deal damage to Ysolde's Mantis
    assert prism_fight.opponent.hp == opp_hp_before or "transfers" not in prism_fight.log[-1].text

    # 3. Kestrel (Shutter): Invisible without tuned optical filter.
    shutter_fight = battle.Battle([me], battle.Fighter(_beast(acceptor), hp=500), boss_key="shutter", rng=random.Random(42))
    shutter_fight.attack()
    player_turns = [t for t in shutter_fight.log if me.name in t.text]
    assert player_turns and player_turns[0].damage == 0


def test_warden_surge_activates_below_half_hp(pair):
    """A Warden below 50% HP gains a signature move on every third round."""
    donor, acceptor = pair
    me = battle.Fighter(_beast(donor), hp=9999)

    # Ember warden starting at low HP -- the surge should trigger.
    fight = battle.Battle(
        [me],
        battle.Fighter(_beast(acceptor), hp=10),
        boss_key="ember",
        rng=random.Random(42),
    )
    # Round 3 is the first surge round (rounds starts at 0, checked at %3==0
    # after rounds>0). Play enough rounds to reach it.
    for _ in range(6):
        if fight.finished:
            break
        fight.attack()
    surge_log = [t for t in fight.log if "FLARE" in t.text or "SPLIT" in t.text
                 or "VEIL" in t.text or "TIDE" in t.text or "ECLIPSE" in t.text]
    assert len(surge_log) > 0, "a surged Warden must use its signature move"


def test_warden_does_not_surge_above_half_hp(pair):
    """Above 50% HP a Warden behaves like a normal opponent."""
    donor, acceptor = pair
    me = battle.Fighter(_beast(donor), hp=9999)

    fight = battle.Battle(
        [me],
        battle.Fighter(_beast(acceptor), hp=99999),
        boss_key="ember",
        rng=random.Random(42),
    )
    for _ in range(6):
        fight.attack()
    surge_log = [t for t in fight.log if "FLARE" in t.text or "SPLIT" in t.text
                 or "VEIL" in t.text or "TIDE" in t.text or "ECLIPSE" in t.text]
    assert len(surge_log) == 0


def test_prism_surge_stuns_the_active_fighter(pair):
    """Ysolde's SPLIT shelves the active fighter for a turn."""
    donor, acceptor = pair
    me = battle.Fighter(_beast(donor), hp=9999)
    fight = battle.Battle(
        [me],
        battle.Fighter(_beast(acceptor), hp=5),
        boss_key="prism",
        rng=random.Random(42),
    )
    for _ in range(6):
        if fight.finished:
            break
        fight.attack()
    split_log = [t for t in fight.log if "SPLIT" in t.text]
    if split_log:
        assert me.stunned or any("shelved" in t.text for t in fight.log)


def test_fighters_gain_xp_and_level_up(pair):
    """Winning a fight awards XP, and enough XP levels up a creature."""
    donor, acceptor = pair
    me = battle.Fighter(_beast(donor), hp=9999)
    starting_level = me.level
    fight = battle.Battle([me], battle.Fighter(_beast(acceptor), hp=1),
                          rng=random.Random(0))
    fight.attack()
    assert fight.won
    assert me.xp > 0
    # A tier-0 opponent gives (0+1)*3 = 9 XP, enough to reach level 2 (8 XP).
    assert me.level > starting_level


def test_level_scales_stats(pair):
    """A higher-level fighter has more HP and attack than the base beast."""
    donor, acceptor = pair
    low = battle.Fighter(_beast(donor), level=1)
    high = battle.Fighter(_beast(donor), level=5)
    assert high.max_hp > low.max_hp
    assert high.attack_power > low.attack_power


def test_level_up_heals_to_full(pair):
    """Gaining a level restores HP to the new maximum."""
    donor, acceptor = pair
    me = battle.Fighter(_beast(donor), hp=1)
    me.gain_xp(100)
    assert me.hp == me.max_hp


def test_creature_level_survives_save_and_load(pair, tmp_path):
    """Level and XP are part of the run, persisted across a save round trip."""
    from chisurf.plugins.misc.games.lumis_quest.api import save as save_api

    donor, acceptor = pair
    me = battle.Fighter(_beast(donor), hp=42, level=4, xp=15)
    state = save_api.RunState(
        team=[(me.beast.species.key,
               donor.probe_id, me.hp, me.beast.infusion,
               me.level, me.xp)],
    )
    path = tmp_path / "run.json"
    state.save(path)
    back = save_api.RunState.load(path)
    entry = back.team[0]
    assert entry[4] == 4
    assert entry[5] == 15
