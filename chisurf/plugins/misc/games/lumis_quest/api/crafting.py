"""Bench reagents: gathered in the world, combined into what protects a
label from itself.

A fluorophore does not fail cleanly -- it blinks, it bleaches, it can take a
neighbour down with it through a triplet state. The real bench answers this
with reagents, not incantations: an oxygen-scavenging enzyme, a triplet
quencher, a blocking protein. This is that shelf, in miniature. Gather the
makings out in the world -- a beast defeated in the field, grass and marsh cut
like anything else -- combine them at a bench, and what comes out is fixed
into a beast the same way a label already is (see :meth:`.bestiary.Beast.infused`).

Every recipe here is a real antifade or passivation reagent from single-molecule
fluorescence sample prep, the same rule :mod:`.bestiary` holds its traits to:
nothing here is a made-up stat.

Qt-free and engine-free.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class Material:
    """One gatherable reagent.

    Attributes
    ----------
    key : str
        Identity.
    name : str
        Display name.
    found : str
        Where it turns up, in one clause -- shown so a player without one
        knows what to go do instead of guessing at it.
    """

    key: str
    name: str
    found: str


#: Real single-molecule-fluorescence sample-prep reagents, not invented ones.
MATERIALS: dict[str, Material] = {
    "trolox": Material(
        "trolox", "Trolox",
        "a rare drop from a beast defeated in the field",
    ),
    "godcat": Material(
        "godcat", "Glucose Oxidase",
        "a rarer drop from a beast defeated in the field",
    ),
    "roxs": Material(
        "roxs", "ROXS Mix",
        "cut from marsh and garden tiles, like grass",
    ),
    "bsa": Material(
        "bsa", "BSA",
        "cut from marsh and garden tiles, like grass",
    ),
    "pagfp": Material(
        "pagfp", "PA-GFP",
        "a rare drop from a beast defeated in the field",
    ),
}


@dataclasses.dataclass(frozen=True)
class Recipe:
    """A bench combination: reagents in, one photophysical fix out.

    Attributes
    ----------
    key : str
        Identity, and the trait key the result grants -- see
        :data:`chisurf.plugins.misc.games.lumis_quest.api.bestiary.TRAITS`.
    name : str
        Display name of the result.
    inputs : tuple of (str, int)
        Material key and how many.
    """

    key: str
    name: str
    inputs: tuple[tuple[str, int], ...]


#: The gold-standard smFRET antifade cocktail (Trolox + an oxygen-scavenging
#: enzyme), ROXS (a reducing-and-oxidizing system that suppresses blinking),
#: plain surface passivation with a blocking protein, and a photoactivatable
#: label -- dark until struck with the activating light, the same way PA-GFP
#: and its relatives are dark until switched on for real.
RECIPES: dict[str, Recipe] = {
    "photostable": Recipe(
        "photostable", "Antifade Cocktail", inputs=(("trolox", 2), ("godcat", 1)),
    ),
    "unblinking": Recipe(
        "unblinking", "Triplet Quencher", inputs=(("roxs", 2), ("trolox", 1)),
    ),
    "shielded": Recipe(
        "shielded", "Passivation Coat", inputs=(("bsa", 3),),
    ),
    "turn_on": Recipe(
        "turn_on", "Photoactivation Label", inputs=(("pagfp", 2),),
    ),
}


@dataclasses.dataclass
class Workshop:
    """One player's gathered reagents and what has been crafted from them.

    Attributes
    ----------
    materials : dict of str to int
        Counts on hand, keyed by :data:`MATERIALS`.
    crafted : list of str
        Recipe keys crafted and not yet fixed into a beast -- consumed on
        use, the same way a label leaves the shelf once it is fitted.
    """

    materials: dict[str, int] = dataclasses.field(default_factory=dict)
    crafted: list[str] = dataclasses.field(default_factory=list)

    def gather(self, material_key: str, count: int = 1) -> None:
        """Add reagents to the shelf.

        Parameters
        ----------
        material_key : str
            Which one.
        count : int, optional
            How many.
        """
        self.materials[material_key] = self.materials.get(material_key, 0) + count

    def can_craft(self, recipe_key: str) -> bool:
        """Whether there is enough on the shelf for a recipe.

        Parameters
        ----------
        recipe_key : str
            Which one.

        Returns
        -------
        bool
        """
        recipe = RECIPES.get(recipe_key)
        if recipe is None:
            return False
        return all(self.materials.get(mat, 0) >= need for mat, need in recipe.inputs)

    def craft(self, recipe_key: str) -> bool:
        """Consume a recipe's reagents and add the result to hand.

        Parameters
        ----------
        recipe_key : str
            Which one.

        Returns
        -------
        bool
            True on success; false when the shelf came up short, in which
            case nothing was spent.
        """
        if not self.can_craft(recipe_key):
            return False
        recipe = RECIPES[recipe_key]
        for mat, need in recipe.inputs:
            self.materials[mat] -= need
        self.crafted.append(recipe_key)
        return True
