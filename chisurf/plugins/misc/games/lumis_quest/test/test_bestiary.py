"""You fight animals with dyes fixed into them, and the dye is what shows."""

from __future__ import annotations

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import bestiary, tiers
from chisurf.plugins.misc.games.lumis_quest.api import tiles as T
from chisurf.plugins.misc.games.lumis_quest.api.roster import Creature


def _label(name="Dye", em=520.0, ab=495.0, ec=60000.0, qy=0.6, protein=False,
           probe_id=1, estimated=frozenset()):
    """A fluorophore with chosen stats, so tests do not depend on the data."""
    return Creature(
        probe_id=probe_id, name=name, is_protein=protein, emission_nm=em,
        absorption_nm=ab, ext_coeff=ec, quantum_yield=qy, estimated=estimated,
    )


def test_a_body_carries_the_label_and_the_label_carries_the_features():
    """The whole premise: the animal is the animal, the dye is what changed."""
    label = _label(em=640.0, ab=615.0)
    hare = bestiary.Beast(bestiary.BY_KEY["hare"], label)
    boar = bestiary.Beast(bestiary.BY_KEY["boar"], label)

    assert hare.emission_nm == boar.emission_nm == 640.0, "the colour is the label's"
    assert boar.max_hp > hare.max_hp, "the stamina is the body's"
    assert hare.speed > boar.speed, "and so is who moves first"
    assert hare.name == "Garnet Hare" and boar.name == "Garnet Boar"
    assert "marked with Dye" in hare.subtitle


def test_an_unmarked_animal_is_an_animal():
    """It can be befriended and carried home; it cannot fight."""
    hare = bestiary.Beast(bestiary.BY_KEY["hare"])
    assert not hare.marked
    assert hare.attack <= 5, "nothing to shine with"
    assert hare.cost_rate == 0.0, "and so nothing to burn"
    assert hare.tier == 1
    assert hare.name == "hare"


def test_fitting_a_label_makes_a_different_creature_of_the_same_animal():
    """That is the build, and nothing is consumed doing it."""
    body = bestiary.Beast(bestiary.BY_KEY["newt"], _label(em=470.0, ab=450.0))
    other = body.fitted(_label(name="Far", em=700.0, ab=670.0, probe_id=2))
    assert other.species is body.species
    assert other.emission_nm == 700.0 and body.emission_nm == 470.0
    assert "nightsight" in other.traits and "hardlight" in body.traits


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"qy": 0.9}, "bloom"),
        ({"qy": 0.15}, "slowburn"),
        ({"protein": True}, "barrel"),
        ({"em": 700.0, "ab": 670.0}, "nightsight"),
        ({"em": 440.0, "ab": 420.0}, "hardlight"),
        ({"em": 620.0, "ab": 500.0}, "shiftwalk"),
        ({"estimated": frozenset({"quantum_yield"})}, "unmeasured"),
    ],
)
def test_every_feature_a_label_grants_is_a_real_property_of_the_dye(kwargs, expected):
    """No invented perks: each one is something the molecule actually does."""
    assert expected in bestiary.label_traits(_label(**kwargs))


def test_tier_is_derived_from_what_a_beast_is_not_assigned():
    """So the ladder measures the roster instead of a table somebody balanced."""
    weak = bestiary.Beast(bestiary.BY_KEY["moth"], _label(ec=8000.0, qy=0.1))
    strong = bestiary.Beast(bestiary.BY_KEY["boar"], _label(ec=250000.0, qy=0.85))
    assert weak.tier < strong.tier
    assert 1 <= weak.tier <= 5 and 1 <= strong.tier <= 5
    assert weak.grade < strong.grade
    assert tiers.TIER_NAMES[strong.tier]


def test_the_wild_is_the_same_wild_every_visit_and_never_over_your_licence():
    """A guardian that rerolls per visit is a slot machine, not a place."""
    pool = [_label(name=f"d{i}", ec=20000.0 + i * 40000.0, qy=0.3 + i * 0.06,
                   probe_id=i) for i in range(10)]
    once = bestiary.wild_beast("docs/a.md", 0.8, pool)
    twice = bestiary.wild_beast("docs/a.md", 0.8, pool)
    assert once == twice
    assert bestiary.wild_beast("docs/b.md", 0.8, pool) != once

    for cap in (1, 2, 3):
        beast = bestiary.wild_beast("docs/a.md", 1.0, pool, tier_cap=cap)
        assert beast.tier <= cap, "a beast you are not licensed for must not spawn"


def test_bodies_come_from_the_ground_you_are_standing_on():
    """A heron in a wood is a body that wandered in from a different game."""
    assert bestiary.terrain_for_tile(T.WATER) == bestiary.WATER
    assert bestiary.terrain_for_tile(T.TREE) == bestiary.WOOD
    assert bestiary.terrain_for_tile(T.ASH) == bestiary.RUIN
    assert bestiary.terrain_for_tile(T.GRASS) == bestiary.MEADOW
    for terrain in (bestiary.MEADOW, bestiary.WOOD, bestiary.WATER, bestiary.RUIN):
        assert bestiary.species_for_terrain(terrain), terrain


def test_the_wellspring_bodies_are_never_found_in_the_grass():
    """They were shining before any of this; the story gives them out."""
    pool = [_label(probe_id=i, ec=60000.0 + i * 1000.0) for i in range(6)]
    for index in range(40):
        beast = bestiary.wild_beast(f"docs/{index}.md", 0.9, pool,
                                    terrain=bestiary.WELLSPRING)
        assert beast.species.habitat != bestiary.WELLSPRING


def test_a_starting_team_is_readable_and_spread_across_the_spectrum():
    """Something fast, something tough, and more than one colour to answer with."""
    pool = [_label(name=f"d{i}", em=420.0 + i * 30.0, ab=400.0 + i * 30.0,
                   probe_id=i) for i in range(12)]
    team = bestiary.starters(pool)
    assert len(team) == 3
    assert len({beast.species.key for beast in team}) == 3
    bands = sorted(beast.emission_nm for beast in team)
    assert bands[-1] - bands[0] > 100.0, "one colour is not a team"
