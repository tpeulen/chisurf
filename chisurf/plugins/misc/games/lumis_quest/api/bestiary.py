"""What you actually fight: an animal, and the label somebody fixed into it.

The earlier design had you fighting *dyes* — a lone ATTO 425 hopping about in
the grass. That never made sense: a fluorophore is not an organism, it is a
thing you attach to one. So the world works the way the bench does.

* A **body** is a real animal — a hare, a heron, a crystal jelly. It brings
  stamina, speed and one behaviour that is its own.
* A **label** is a real fluorophore out of the spectra database (see
  :mod:`.roster`). It brings colour, brightness, and the cost of shining.
* A **marked beast** is one fixed into the other. Its features are the label's:
  what it emits, how hard it hits, how fast it burns out, what it is strong
  against. That is the premise of the whole story — somebody is doing this to
  the wild.

The two are collected **separately**, and that is the build game. You strip a
label off a beast (setting the animal free) and you befriend bodies; a team
member is a body you chose with a label you fitted. A far-red dye in a heron is
a different creature from the same dye in a boar, and both are different from
the same body wearing a blue protein.

Three rules keep it honest:

* **Bodies are real animals, and their stat lines follow the animal.** A hare is
  fast and frail. A boar is slow and heavy. Nothing is a reskin.
* **Every feature the label grants is real photophysics.** A high quantum yield
  hits harder and bleaches sooner. A protein barrel shields. A large Stokes
  shift is hard to jam. Far-red sees in the dark, because that is what far-red
  is *for*.
* **Tier is derived, never assigned.** A beast's tier falls out of its
  brightness and its stamina, so the ladder in :mod:`.tiers` is a measurement
  of the roster rather than a table someone balanced.

Qt-free and engine-free.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import random

from .roster import Creature

#: Where the bestiary data lives.
_DATA_FILE = pathlib.Path(__file__).resolve().parent.parent / "data" / "bestiary.json"

#: Where a body is found. Terrain the game already paints decides which of
#: these can turn up: meadow and wood in the open country, water at the moat
#: and the bridges, ruin inside the walls of a dark compound, and the
#: wellspring bodies only where the light originally came from.
MEADOW = "meadow"
WOOD = "wood"
WATER = "water"
RUIN = "ruin"
WELLSPRING = "wellspring"


def _load() -> dict:
    """Read the bestiary JSON, cached on the module after first load."""
    return json.loads(_DATA_FILE.read_text(encoding="utf-8"))


_DATA = _load()

#: Battle config loaded for the cost-rate rules (action_cost + cost_rules).
_BATTLE_FILE = pathlib.Path(__file__).resolve().parent.parent / "data" / "battle.json"
_BATTLE_CFG = json.loads(_BATTLE_FILE.read_text(encoding="utf-8"))


@dataclasses.dataclass(frozen=True)
class Species:
    """One real animal, as a body a label can be fixed into.

    Attributes
    ----------
    key : str
        Stable identifier, used in saves.
    name : str
        What it is called.
    vitality : float
        Stamina multiplier. A boar carries a lot of dye before it bleaches; a
        moth carries very little.
    power : float
        How much of the label's brightness the body can actually drive.
    agility : float
        Decides who moves first. This is the stat the old fight did not have,
        and without it every exchange was you-then-them forever.
    habitat : str
        One of :data:`MEADOW`, :data:`WOOD`, :data:`WATER`, :data:`RUIN`,
        :data:`WELLSPRING`.
    trait : str
        Key into :data:`TRAITS`: the one thing this animal does that no stat
        line can express.
    lore : str
        A line for the bestiary entry.
    """

    key: str
    name: str
    vitality: float
    power: float
    agility: float
    habitat: str
    trait: str
    lore: str


#: The bodies, loaded from ``data/bestiary.json``. Real animals, with stat
#: lines that follow the animal rather than a curve: the fast ones are frail,
#: the armoured ones are slow, and the three at the bottom are the animals
#: fluorescence was actually *taken from*.
SPECIES: tuple[Species, ...] = tuple(
    Species(
        key=e["key"], name=e["name"],
        vitality=float(e["vitality"]), power=float(e["power"]),
        agility=float(e["agility"]), habitat=e["habitat"],
        trait=e["trait"], lore=e["lore"],
    )
    for e in _DATA["species"]
)

#: By key, for saves and lookups.
BY_KEY: dict[str, Species] = {species.key: species for species in SPECIES}


@dataclasses.dataclass(frozen=True)
class Trait:
    """One behaviour, either the body's own or granted by the label.

    Attributes
    ----------
    key : str
        Stable identifier.
    name : str
        What it is called in the UI.
    text : str
        What it does, in one line a player can act on.
    """

    key: str
    name: str
    text: str


#: What each body does, loaded from ``data/bestiary.json``. The fight reads
#: these by key; nothing here is a stat bonus wearing a name.
TRAITS: dict[str, Trait] = {
    k: Trait(key=k, name=e["name"], text=e["text"])
    for k, e in _DATA["traits"].items()
}

#: Emission band, loaded from ``data/bestiary.json``.
BANDS: tuple[tuple[float, str], ...] = tuple(
    (float(edge), name) for edge, name in _DATA["bands"]
)
#: Quantum yield above which a label counts as bright, and below which it counts
#: as dim. Several traits key off these, so they live in one place.
_th = _DATA["thresholds"]
BRIGHT_QY = float(_th["bright_qy"])
DIM_QY = float(_th["dim_qy"])

#: Stokes shift, in nm, above which a label is hard to jam.
WIDE_SHIFT_NM = float(_th["wide_shift_nm"])

#: Emission bounds for the two ends of the spectrum that behave differently.
FAR_RED_NM = float(_th["far_red_nm"])
DEEP_BLUE_NM = float(_th["deep_blue_nm"])

#: Grade boundaries between tiers. Derived, not assigned: a beast's grade is
#: its brightness against its stamina, so the ladder measures the roster.
TIER_BOUNDS: tuple[float, ...] = tuple(float(v) for v in _th["tier_bounds"])


def band_name(emission_nm: float) -> str:
    """The colour word for an emission wavelength.

    Parameters
    ----------
    emission_nm : float
        Emission maximum in nm.

    Returns
    -------
    str
        One of :data:`BANDS`.
    """
    for edge, name in BANDS:
        if emission_nm < edge:
            return name
    return BANDS[-1][1]


def label_traits(label: Creature) -> tuple[str, ...]:
    """Which features a label grants whatever it is fixed into.

    Parameters
    ----------
    label : chisurf.plugins.misc.games.lumis_quest.api.roster.Creature
        The fluorophore.

    Returns
    -------
    tuple of str
        Keys into :data:`TRAITS`, in a stable order.
    """
    found: list[str] = []
    if label.stokes_shift_nm >= WIDE_SHIFT_NM:
        found.append("shiftwalk")
    if label.quantum_yield >= BRIGHT_QY:
        found.append("bloom")
    elif label.quantum_yield <= DIM_QY:
        found.append("slowburn")
    if label.is_protein:
        found.append("barrel")
    if label.emission_nm >= FAR_RED_NM:
        found.append("nightsight")
    elif label.emission_nm <= DEEP_BLUE_NM:
        found.append("hardlight")
    if label.estimated:
        found.append("unmeasured")
    return tuple(found)


@dataclasses.dataclass(frozen=True)
class Beast:
    """An animal, and whatever is fixed into it.

    Attributes
    ----------
    species : Species
        The body.
    label : chisurf.plugins.misc.games.lumis_quest.api.roster.Creature or None
        The fluorophore marking it. ``None`` is an *unmarked* animal: a body
        nobody has done anything to. It can be befriended and carried home, but
        it cannot fight until you fit it with something.
    infusion : str or None
        A bench reagent fixed in on top of the label -- see
        :mod:`chisurf.plugins.misc.games.lumis_quest.api.crafting`. A key into
        :data:`TRAITS`, the same as everything else here.
    """

    species: Species
    label: Creature | None = None
    infusion: str | None = None

    # -- identity ----------------------------------------------------------

    @property
    def name(self) -> str:
        """What this beast is called.

        Returns
        -------
        str
            Band and animal, e.g. ``Verdant Heron``. An unmarked body is named
            plainly, because nothing has been done to it.
        """
        if self.label is None:
            return self.species.name
        return f"{band_name(self.label.emission_nm)} {self.species.name.title()}"

    @property
    def marked(self) -> bool:
        """Whether a label is fixed into this animal.

        Returns
        -------
        bool
            True when it carries one.
        """
        return self.label is not None

    @property
    def subtitle(self) -> str:
        """The line under the name: what it is, and what is in it.

        Returns
        -------
        str
            e.g. ``heron marked with ATTO 594``.
        """
        if self.label is None:
            return f"{self.species.name}, unmarked"
        return f"{self.species.name} marked with {self.label.name}"

    @property
    def emission_nm(self) -> float:
        """The colour it shines, which is the label's.

        Returns
        -------
        float
            Nanometres, or 0 for an unmarked animal.
        """
        return self.label.emission_nm if self.label else 0.0

    @property
    def absorption_nm(self) -> float:
        """The colour it takes in.

        Returns
        -------
        float
            Nanometres, or 0 for an unmarked animal.
        """
        return self.label.absorption_nm if self.label else 0.0

    # -- derived stats -----------------------------------------------------

    @property
    def max_hp(self) -> int:
        """Photon budget: how long it can go on shining.

        The label decides how fast it burns; the body decides how much there is
        to burn.

        Returns
        -------
        int
            Roughly 20..200.
        """
        if self.label is None:
            return max(10, int(round(40 * self.species.vitality)))
        return max(12, int(round(self.label.max_hp * self.species.vitality)))

    @property
    def attack(self) -> int:
        """Damage per clean hit.

        Returns
        -------
        int
            Roughly 5..90. An unmarked animal can barely do anything: it has no
            light to spend, which is exactly why the labeller marks them.
        """
        if self.label is None:
            return 4
        return max(3, int(round(self.label.attack * self.species.power)))

    @property
    def speed(self) -> float:
        """Who moves first.

        Returns
        -------
        float
            The body's agility, nudged by the label: a heavy protein is a
            weight to carry, a small dye barely registers.
        """
        speed = self.species.agility
        if self.label is not None and self.label.is_protein:
            speed *= 0.88
        return speed

    @property
    def cost_rate(self) -> float:
        """Fraction of its own budget one action costs.

        The base rate and every trait multiplier are declared in
        ``data/battle.json`` under ``action_cost`` and ``cost_rules``, so
        changing how fast a trait burns is editing JSON, not this code.

        Returns
        -------
        float
            0 for an unmarked animal, which cannot act.
        """
        if self.label is None:
            return 0.0
        ac = _BATTLE_CFG["action_cost"]
        rate = float(ac["base_rate"]) * (float(ac["qy_factor"]) + self.label.quantum_yield)
        for trait_key, multiplier in _BATTLE_CFG["cost_rules"].items():
            if trait_key in self.traits:
                rate *= float(multiplier)
        return rate

    @property
    def traits(self) -> tuple[str, ...]:
        """Everything this beast does: the body's, the label's, the bench's.

        Returns
        -------
        tuple of str
            Keys into :data:`TRAITS`.
        """
        base = (self.species.trait,) if self.label is None \
            else (self.species.trait, *label_traits(self.label))
        return (*base, self.infusion) if self.infusion else base

    @property
    def trait_names(self) -> tuple[str, ...]:
        """Display names of :attr:`traits`.

        Returns
        -------
        tuple of str
            For the beast panel.
        """
        return tuple(TRAITS[key].name for key in self.traits if key in TRAITS)

    @property
    def grade(self) -> float:
        """How formidable this pairing is, in 0..1.

        Returns
        -------
        float
            Brightness against stamina. This, and nothing else, is what
            :attr:`tier` is read off.
        """
        if self.label is None:
            return 0.0
        power = min(self.attack / 70.0, 1.0)
        stamina = min(self.max_hp / 150.0, 1.0)
        return max(0.0, min(0.55 * power + 0.45 * stamina, 1.0))

    @property
    def tier(self) -> int:
        """Which rung of the ladder it stands on.

        Returns
        -------
        int
            1..5. An unmarked animal is tier 1: it is not dangerous, it is an
            animal.
        """
        if self.label is None:
            return 1
        grade = self.grade
        return 1 + sum(1 for bound in TIER_BOUNDS if grade >= bound)

    @property
    def summary(self) -> str:
        """One line for the battle UI.

        Returns
        -------
        str
            Colour, and the two headline stats.
        """
        if self.label is None:
            return f"{self.species.name}  unmarked  hp {self.max_hp}"
        mark = "~" if self.label.estimated else ""
        return (
            f"{self.emission_nm:.0f} nm  atk {self.attack}{mark}  "
            f"hp {self.max_hp}{mark}  T{self.tier}"
        )

    def fitted(self, label: Creature | None) -> Beast:
        """The same body wearing a different label.

        This is the build: one animal is many creatures depending on what you
        put in it.

        Parameters
        ----------
        label : Creature or None
            The fluorophore to fix in, or ``None`` to strip it.

        Returns
        -------
        Beast
            A new beast; nothing is mutated. Any bench infusion carries over
            -- it protects the animal, not the particular dye in it.
        """
        return Beast(species=self.species, label=label, infusion=self.infusion)

    def infused(self, trait_key: str) -> Beast:
        """The same animal, with one bench reagent fixed in.

        Parameters
        ----------
        trait_key : str
            A key into :data:`TRAITS` -- see
            :mod:`chisurf.plugins.misc.games.lumis_quest.api.crafting` for
            what is actually craftable.

        Returns
        -------
        Beast
            A new beast; nothing is mutated. Replaces any earlier infusion --
            the bench fixes in one reagent at a time, not a stack of them.
        """
        return Beast(species=self.species, label=self.label, infusion=trait_key)


def species_for_terrain(terrain: str) -> tuple[Species, ...]:
    """Which bodies live on a kind of ground.

    Parameters
    ----------
    terrain : str
        One of :data:`MEADOW`, :data:`WOOD`, :data:`WATER`, :data:`RUIN`,
        :data:`WELLSPRING`.

    Returns
    -------
    tuple of Species
        Everything at home there. Empty for an unknown terrain.
    """
    return tuple(species for species in SPECIES if species.habitat == terrain)


def terrain_for_tile(tile: int) -> str:
    """Which bodies are at home on a kind of ground.

    Parameters
    ----------
    tile : int
        A tile kind from :mod:`.tiles`.

    Returns
    -------
    str
        One of the habitat constants. Ground that names nothing in particular
        reads as meadow, which is where most animals are.
    """
    from . import tiles as T

    if tile in (T.WATER, T.SAND, T.MARSH, T.BRIDGE, T.DOCK, T.TAR):
        return WATER
    if tile in (T.TREE, T.DEADTREE):
        return WOOD
    if tile in (T.CLIFF, T.CAVE, T.RUIN, T.ASH, T.RIFT, T.WALL, T.FLOOR):
        return RUIN
    return MEADOW


def wild_beast(seed_text: str, difficulty: float, labels, terrain: str = MEADOW,
               tier_cap: int = 5) -> Beast:
    """The marked animal guarding a place.

    Seeded by the place's own address, so the same page always holds the same
    beast: an encounter that reshuffles every visit is a slot machine, not a
    place.

    Parameters
    ----------
    seed_text : str
        Usually the page address.
    difficulty : float
        0..1, from the room's remoteness. Decides how bright a label the
        labeller used, and therefore the tier.
    labels : sequence of Creature
        Fluorophores to choose from.
    terrain : str, optional
        Which bodies are around.
    tier_cap : int, optional
        Never produce a beast above this tier. The ladder in :mod:`.tiers`
        passes the player's own licence here, so a region cannot open with
        something they are not permitted to face.

    Returns
    -------
    Beast
        The marked animal.

    Raises
    ------
    ValueError
        If there are no labels at all.
    """
    if not labels:
        raise ValueError("no labels available")
    level = max(0.0, min(difficulty, 1.0))
    picker = random.Random(seed_text)

    # The wellspring animals are never wild encounters: they were shining
    # before any of this, and the story gives them out rather than the grass.
    # The fallback has to strip them too, or asking for wellspring ground is
    # the one way to meet one in a field.
    bodies = tuple(body for body in (species_for_terrain(terrain) or SPECIES)
                   if body.habitat != WELLSPRING)
    bodies = bodies or tuple(body for body in SPECIES if body.habitat != WELLSPRING)
    species = picker.choice(bodies)

    # Difficulty picks *which* label, not merely how much of it there is:
    # scaling health alone left remote pages guarded by whatever weakling came
    # up, which pointed the reward gradient somewhere the danger did not.
    ranked = sorted(labels, key=lambda creature: creature.attack)
    span = max(1, len(ranked) // 4)
    top = int(round(level * (len(ranked) - 1)))
    window = ranked[max(0, top - span // 2): max(1, top + span // 2 + 1)] or list(ranked)

    beast = Beast(species=species, label=picker.choice(window))
    if beast.tier <= tier_cap:
        return beast
    # Over the cap. Clamping the tier number instead would leave the *stats* of
    # a tier-5 beast wearing a tier-2 badge, which is worse than the encounter
    # it replaced -- so walk down the labels, and then down the bodies, until
    # something genuinely fits. A heavy body wearing the dimmest dye in the
    # roster can still be tier III, which is why the body has to give way too.
    for candidate_species in (species, *sorted(bodies, key=lambda one: one.vitality)):
        for label in ranked:
            candidate = Beast(species=candidate_species, label=label)
            if candidate.tier <= tier_cap:
                return candidate
    # Nothing in the roster is that gentle: hand back the least of it rather
    # than something over the cap.
    return min(
        (Beast(species=one, label=label) for one in bodies for label in ranked[:4]),
        key=lambda one: one.grade,
        default=beast,
    )


def starters(labels, count: int = 3) -> tuple[Beast, ...]:
    """A first team: three ordinary animals wearing three well-measured labels.

    Parameters
    ----------
    labels : sequence of Creature
        The roster to draw from.
    count : int, optional
        How many.

    Returns
    -------
    tuple of Beast
        Spread across the visible range so a starting team can answer more
        than one colour, in bodies a beginner can read: something fast,
        something tough, something in between.
    """
    measured = [label for label in labels if not label.estimated]
    if not measured:
        return ()
    bodies = [BY_KEY["hare"], BY_KEY["newt"], BY_KEY["beetle"]]
    lo, hi = measured[0].emission_nm, measured[-1].emission_nm
    chosen: list[Beast] = []
    for index in range(count):
        target = lo + (hi - lo) * (index + 0.5) / max(count, 1)
        label = min(measured, key=lambda c: abs(c.emission_nm - target))
        chosen.append(Beast(species=bodies[index % len(bodies)], label=label))
    return tuple(chosen)
