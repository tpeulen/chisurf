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
import random

from .roster import Creature

#: Where a body is found. Terrain the game already paints decides which of
#: these can turn up: meadow and wood in the open country, water at the moat
#: and the bridges, ruin inside the walls of a dark compound, and the
#: wellspring bodies only where the light originally came from.
MEADOW = "meadow"
WOOD = "wood"
WATER = "water"
RUIN = "ruin"
WELLSPRING = "wellspring"


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


#: The bodies. Real animals, with stat lines that follow the animal rather than
#: a curve: the fast ones are frail, the armoured ones are slow, and the three
#: at the bottom are the animals fluorescence was actually *taken from* — the
#: crystal jelly that gave up GFP, the disc coral behind every red protein, the
#: sea anemone behind the cherries. They are the only bodies that were shining
#: before anyone marked anything.
SPECIES: tuple[Species, ...] = (
    Species("hare", "hare", 0.85, 0.80, 1.60, MEADOW, "bolt",
            "Ears up before you have finished arriving."),
    Species("vole", "vole", 0.70, 0.70, 1.30, MEADOW, "burrow",
            "Lives in a tunnel it can reach from anywhere in the field."),
    Species("moth", "moth", 0.60, 1.15, 1.25, MEADOW, "phototaxis",
            "Goes to the brightest thing in the room. Always has."),
    Species("mantis", "mantis", 0.75, 1.30, 1.10, MEADOW, "ambush",
            "Holds perfectly still until the first exchange is already over."),
    Species("adder", "adder", 0.80, 1.35, 1.00, MEADOW, "venom",
            "Strikes once and lets the strike keep working."),
    Species("fox", "fox", 1.00, 1.10, 1.20, WOOD, "cunning",
            "Watches how you work, then declines to be where you are."),
    Species("owl", "owl", 0.90, 1.20, 1.15, WOOD, "silent",
            "Arrives without the sound that should have preceded it."),
    Species("boar", "boar", 1.50, 1.25, 0.70, WOOD, "charge",
            "One direction, committed to entirely."),
    Species("beetle", "beetle", 1.20, 0.85, 0.60, WOOD, "chitin",
            "Wearing most of a suit of armour and in no hurry."),
    Species("crow", "crow", 0.85, 1.00, 1.35, WOOD, "mimicry",
            "Has heard what you sound like and can do it back."),
    Species("shrew", "shrew", 0.60, 0.95, 1.45, WOOD, "frenzy",
            "Must eat constantly or die, and fights like it."),
    Species("newt", "newt", 1.05, 0.85, 0.80, WATER, "regrowth",
            "Grows the limb back. Grows most things back."),
    Species("carp", "carp", 1.35, 0.75, 0.65, WATER, "deepwater",
            "Old, cold, and extremely difficult to hurry."),
    Species("heron", "heron", 0.95, 1.20, 1.05, WATER, "spearfall",
            "Stands in the shallows for an hour and then is very fast once."),
    Species("otter", "otter", 1.10, 1.00, 1.20, WATER, "play",
            "Treats the whole encounter as a game it is winning."),
    Species("eel", "eel", 0.90, 1.30, 0.95, WATER, "discharge",
            "Holds a charge it did not ask anybody about."),
    Species("toad", "toad", 1.25, 0.80, 0.55, WATER, "mucus",
            "Coated in something that makes every grip fail."),
    Species("bat", "bat", 0.70, 1.05, 1.40, RUIN, "echo",
            "Does not need the light to know exactly where you are."),
    Species("rat", "rat", 0.75, 0.90, 1.25, RUIN, "frenzy",
            "Has outlived several better ideas about what should live here."),
    Species("olm", "olm", 1.10, 0.95, 0.70, RUIN, "regrowth",
            "A blind cave salamander, pale as a root and older than the cave."),
    Species("jelly", "crystal jelly", 1.60, 1.40, 0.50, WELLSPRING, "wellspring",
            "It was glowing on its own long before any of this. Green, at the rim."),
    Species("coral", "disc coral", 1.80, 1.30, 0.30, WELLSPRING, "wellspring",
            "A colony that has been red since before the word existed."),
    Species("anemone", "sea anemone", 1.50, 1.45, 0.40, WELLSPRING, "wellspring",
            "Waves in a current nobody else can feel, and burns cherry-dark."),
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


#: What each body does. The fight reads these by key; nothing here is a stat
#: bonus wearing a name.
TRAITS: dict[str, Trait] = {
    "bolt": Trait("bolt", "Bolt", "Withdrawing always works, and it is faster when hurt."),
    "burrow": Trait("burrow", "Burrow", "Sometimes simply is not there when the shot lands."),
    "phototaxis": Trait("phototaxis", "Phototaxis", "Hits a bright label much harder."),
    "ambush": Trait("ambush", "Ambush", "The first strike of a fight lands double."),
    "venom": Trait("venom", "Venom", "The target keeps bleaching after the hit."),
    "cunning": Trait("cunning", "Cunning", "Half again as likely to get a label off cleanly."),
    "silent": Trait("silent", "Silent", "Cannot be struck first, and hits a little harder."),
    "charge": Trait("charge", "Charge", "Much more damage, at twice the bleaching."),
    "chitin": Trait("chitin", "Chitin", "Takes a third less damage."),
    "mimicry": Trait("mimicry", "Mimicry", "Copies your band, so you are never strong against it."),
    "frenzy": Trait("frenzy", "Frenzy", "Strikes twice for half each."),
    "regrowth": Trait("regrowth", "Regrowth", "Recovers a little every turn."),
    "deepwater": Trait("deepwater", "Deep Water", "Bleaches at half the rate."),
    "spearfall": Trait("spearfall", "Spearfall", "Always moves first on turn one."),
    "play": Trait("play", "Play", "Recovers when swapped in, and is easy to befriend."),
    "discharge": Trait("discharge", "Discharge", "Sometimes shocks the target into a lost turn."),
    "mucus": Trait("mucus", "Mucus", "Bright labels do much less damage to it."),
    "echo": Trait("echo", "Echo", "Finds a target the fitted filter has blinded you to."),
    "wellspring": Trait("wellspring", "Wellspring", "Cannot be bleached out in one blow."),
    # Granted by the label, not the body. Every one of these is a real property
    # of the dye, which is the point: the features come from the marking.
    "shiftwalk": Trait("shiftwalk", "Shiftwalk",
                       "A wide Stokes shift -- hard to jam, and it dodges."),
    "bloom": Trait("bloom", "Bloom", "High yield: more damage, and it burns down fast."),
    "slowburn": Trait("slowburn", "Slow Burn", "Low yield: dim, but it lasts."),
    "barrel": Trait("barrel", "Barrel", "A protein shell takes the edge off a hit."),
    "nightsight": Trait("nightsight", "Nightsight", "Far-red: moves first against anything bluer."),
    "hardlight": Trait("hardlight", "Hard Light", "Blue and violent: more damage, more bleaching."),
    "unmeasured": Trait("unmeasured", "Unmeasured",
                        "Stats are class defaults -- its damage is unpredictable."),
    # Fixed in at the bench, not grown or worn -- see .crafting. Real
    # single-molecule antifade and passivation reagents, same rule as the
    # label traits above: nothing here is an invented stat.
    "photostable": Trait("photostable", "Antifade Cocktail",
                         "Trolox and an oxygen scavenger: bleaches much slower."),
    "unblinking": Trait("unblinking", "Triplet Quencher",
                        "A reducing-and-oxidizing system: bleaches slower still."),
    "shielded": Trait("shielded", "Passivation Coat",
                      "A blocking protein coat: bleaches a little slower."),
    "turn_on": Trait("turn_on", "Photoactivation Label",
                     "Dark until struck -- the hit that lands lights it, "
                     "and its own next hit lands much harder."),
}

#: Emission band -> the name a marked animal goes by. A player learns to read
#: "Garnet" as 625-660 nm without ever being told a number.
BANDS: tuple[tuple[float, str], ...] = (
    (450.0, "Violet"),
    (480.0, "Azure"),
    (505.0, "Cyan"),
    (540.0, "Verdant"),
    (565.0, "Gold"),
    (590.0, "Ember"),
    (625.0, "Crimson"),
    (660.0, "Garnet"),
    (1e9, "Umbral"),
)

#: Quantum yield above which a label counts as bright, and below which it counts
#: as dim. Several traits key off these, so they live in one place.
BRIGHT_QY = 0.70
DIM_QY = 0.30

#: Stokes shift, in nm, above which a label is hard to jam.
WIDE_SHIFT_NM = 80.0

#: Emission bounds for the two ends of the spectrum that behave differently.
FAR_RED_NM = 620.0
DEEP_BLUE_NM = 470.0

#: Grade boundaries between tiers. Derived, not assigned: a beast's grade is
#: its brightness against its stamina, so the ladder measures the roster.
TIER_BOUNDS: tuple[float, ...] = (0.32, 0.46, 0.60, 0.76)


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
    def bleach_rate(self) -> float:
        """Fraction of its own budget one shot costs.

        Returns
        -------
        float
            0 for an unmarked animal, which cannot shine and so cannot bleach.
        """
        if self.label is None:
            return 0.0
        rate = 0.045 * (0.6 + self.label.quantum_yield)
        if "deepwater" in self.traits:
            rate *= 0.5
        if "slowburn" in self.traits:
            rate *= 0.6
        if "bloom" in self.traits:
            rate *= 1.5
        if "charge" in self.traits:
            rate *= 2.0
        if "hardlight" in self.traits:
            rate *= 1.3
        # Bench reagents, not photophysics of the label or the body -- the
        # real thing they are named for is exactly this: protecting a dye
        # against its own bleaching, from outside it.
        if "photostable" in self.traits:
            rate *= 0.55
        if "unblinking" in self.traits:
            rate *= 0.7
        if "shielded" in self.traits:
            rate *= 0.85
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
