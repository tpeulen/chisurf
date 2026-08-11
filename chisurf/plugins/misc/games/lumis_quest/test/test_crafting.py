"""A recipe is spent atomically, and a beast is fixed by a real reagent."""

from __future__ import annotations

from chisurf.plugins.misc.games.lumis_quest.api import bestiary
from chisurf.plugins.misc.games.lumis_quest.api import crafting
from chisurf.plugins.misc.games.lumis_quest.api.roster import Creature


def _label(name="Dye", em=520.0, ab=495.0, ec=60000.0, qy=0.6, protein=False,
           probe_id=1, estimated=frozenset()):
    """A fluorophore with chosen stats, so tests do not depend on the data."""
    return Creature(
        probe_id=probe_id, name=name, is_protein=protein, emission_nm=em,
        absorption_nm=ab, ext_coeff=ec, quantum_yield=qy, estimated=estimated,
    )


def test_a_recipe_cannot_be_crafted_short_of_its_reagents():
    """Coming up short must not spend what little is on the shelf."""
    bench = crafting.Workshop()
    bench.gather("trolox", 1)
    assert not bench.can_craft("photostable"), "needs two trolox, one godcat"
    assert bench.craft("photostable") is False
    assert bench.materials["trolox"] == 1, "a failed craft spends nothing"
    assert bench.crafted == []


def test_crafting_consumes_exactly_its_recipe():
    """Reagents used up; anything not asked for stays on the shelf."""
    bench = crafting.Workshop()
    bench.gather("trolox", 3)
    bench.gather("godcat", 1)
    assert bench.craft("photostable") is True
    assert bench.materials["trolox"] == 1, "two of three spent"
    assert bench.materials["godcat"] == 0
    assert bench.crafted == ["photostable"]


def test_every_recipe_names_materials_and_traits_that_exist():
    """A recipe that names nothing real is a recipe nobody can ever finish."""
    for recipe in crafting.RECIPES.values():
        assert recipe.key in bestiary.TRAITS, recipe.key
        for material_key, count in recipe.inputs:
            assert material_key in crafting.MATERIALS, material_key
            assert count > 0


def test_infusing_a_beast_adds_the_trait_and_nothing_else():
    """The bench fixes one thing into a beast; species and label are untouched."""
    beast = bestiary.Beast(bestiary.BY_KEY["hare"])
    assert "photostable" not in beast.traits

    infused = beast.infused("photostable")
    assert "photostable" in infused.traits
    assert infused.species is beast.species
    assert infused.label is beast.label
    assert "photostable" not in beast.traits, "the original is not mutated"


def test_an_antifade_infusion_measurably_slows_bleaching():
    """The whole point: a crafted reagent is a real photophysical effect."""
    plain = bestiary.Beast(bestiary.BY_KEY["hare"], _label())
    protected = plain.infused("photostable")
    assert protected.bleach_rate < plain.bleach_rate
