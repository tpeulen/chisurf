"""The people, animals and beasts that live in the world.

A map with nothing moving on it is a diagram. This is what makes it a place.

The cast is derived rather than sprinkled:

* **Villagers** stand outside settled buildings. That is not decoration -- the
  design has always been that reviewing a page *turns a wild room into a
  villager*, so the population of a settlement is literally how much of that
  section somebody has read. A ghost town is a section nobody has touched.
* **Townsfolk** live in the compounds regardless of review state, scaled to the
  settlement's size rather than to its pages -- a walled town with exactly as
  many people as sign-offs is a spreadsheet wearing houses.
* **Keepers of premises** stand at the door of the tavern, the supply house,
  the lens-grinder and the shrine. Each is a *service*, not a line of flavour:
  rumours that point at your actual next objective, gear, a re-ground filter, a
  full restore.
* **Wardens** hold the halls. They are the ladder (see :mod:`.tiers`), and each
  teaches one real thing before making you use it.
* **Emissaries** are the moral cast: one per order. Talking to one is how a
  doctrine is chosen -- a doctrine you pledge to is a person you met.
* **Unmarked animals** wander the open ground. They mean nothing at all, and
  that is deliberate: a world where every object is a metric is exhausting.
* **Marked beasts** roam the wilds. Touching one starts a fight, so the
  wilderness is dangerous in a way that standing inside the walls is not -- and
  each is a real animal with a real dye fixed into it, which is the thing the
  whole story is about.

Everything is seeded by position or by page address, so the population is the
same on every run: a village whose people rearrange themselves each time you
visit is not somewhere you can come to know.
"""

from __future__ import annotations

import dataclasses
import math
import random

from . import steering
from . import tiles as T
from .bestiary import BY_KEY as SPECIES_BY_KEY
from .bestiary import SPECIES
from .story import ORDER_LANDS, ORDERS
from .tiers import BY_KEY as WARDEN_BY_KEY
from .tiles import CLINIC, FLOOR, GARDEN, GRASS, PLAZA, ROAD, SAND, TILE, is_blocking

#: What a villager might say. Chosen by page address, so a given villager always
#: greets you the same way and the words become theirs.
GREETINGS = (
    "This page has been read end to end. It holds.",
    "Somebody vouched for what is written here.",
    "The lamps stay lit while the words stay true.",
    "I keep this one. Ask me if a symbol puzzles you.",
    "It was dark here once. Not any more.",
    "Read it yourself if you like -- it will stand up.",
)

def page_lines(room) -> tuple[str, ...]:
    """What a settled page's keeper says, from the page itself.

    A keeper used to greet you from the shared bank and stop there, so every
    settlement in the world made the same small talk. Their page is right
    behind them and it is the reason they exist -- so the deterministic,
    model-free voice now reads it: the page's opening claim, then one more
    sentence picked by the page's own address as a "did you know". The model
    voices (:mod:`.personas`) still replace all of this when they are on;
    this is the offline floor, not the ceiling.

    Parameters
    ----------
    room : chisurf.plugins.misc.games.lumis_quest.api.world.Room
        The settled page.

    Returns
    -------
    tuple of str
        Zero, one or two lines of the page's own prose, cleaned for the
        dialogue panel. Empty when the page cannot be read or holds no
        usable sentence -- the caller keeps the canned greeting then.
    """
    from .challenge import _sentences

    try:
        text = room.path.read_text(encoding="utf-8")
    except OSError:
        return ()
    sentences = _sentences(text)
    if not sentences:
        return ()

    def clean(sentence: str) -> str:
        # The dialogue panel wraps at 46 characters over four lines, and the
        # text path has no em-dash glyph.
        line = " ".join(sentence.split()).replace("—", "--")
        return line if len(line) <= 168 else line[:165].rstrip() + "..."

    lines = [clean(sentences[0])]
    if len(sentences) > 1:
        pick = 1 + _seed(room.address) % (len(sentences) - 1)
        lines.append(f"Did you know? {clean(sentences[pick])}")
    return tuple(lines)


#: What a villager says about the state of their settlement.
STRUGGLING = (
    "Half our houses are dark. Nobody has been through them.",
    "We could use a reader. Plenty here has never been checked.",
    "The lamps go out one at a time when nobody comes.",
)

#: Unmarked animals, and what they do when you bother them. These are the ones
#: nobody has done anything to, and the game is quietly about keeping it that
#: way.
ANIMALS = (
    ("sheep", "It regards you, decides against it, and returns to the grass."),
    ("goose", "It hisses. You have been warned by better and survived."),
    ("hare", "Up on its back legs, ears working. Ordinary brown. Unmarked."),
    ("heron", "Standing in the shallows, entirely uninterested in you."),
    ("cat", "It watches your pocket, where the labels are."),
    ("dog", "Tail once, then back to whatever it was smelling."),
)

#: Townsfolk who are not keepers: a settlement the size of a town needs people
#: in it who are not a review metric.
TOWNSFOLK = (
    ("the carter", "I haul between the towns. The dark stretches get longer every year."),
    ("a child", "Have you seen the hound glow? Everyone says Lumi can smell light."),
    ("the gatekeeper", "The gate stays open. It is readers we are short of, not doors."),
    ("the gardener", "A tended page keeps its colour. Same as anything planted."),
    ("the lamplighter", "I light what I can reach. The high shelves need someone like you."),
    ("a drover", "Lost two beasts to the Marking this spring. Both came back gold."),
    ("the ferryman", "There is water between every land. There is a bridge for a reason."),
    ("an old woman", "I remember when a hare was brown. You will not, and that is the trouble."),
)

#: What the healer at every recovery station says.
HEALER_LINES = (
    "This pad rekindles a spent team. Stand on it a while.",
    "Bleached is not gone. Light comes back, if you give it somewhere quiet.",
    "Fill your team before the wilds. Attrition is what kills probes, not beasts.",
)

#: The premises keepers. Each is one screen of who they are and then a service.
TAVERN_KEEPER = "the innkeeper"
SHOP_KEEPER = "the supplier"
SMITH = "the lens-grinder"
PRIEST = "the shrine-keeper"

TAVERN_LINES = (
    "Sit down. Everyone who walks this road comes through here eventually.",
    "I hear things. Buy nothing and I will still tell you -- the light is "
    "going, and gossip is cheap.",
)
SHOP_LINES = (
    "Glass, mostly. Filters somebody ground before the Fading and nobody has "
    "matched since.",
    "Take what suits your team's band. It is no use to me: I cannot see half "
    "of it either.",
)
SMITH_LINES = (
    "Bring me glass and I will put an edge on it. Narrower passes less and "
    "sees better -- that is the whole trade.",
    "A wide filter is a kindness to a beginner and a lie to everyone else.",
)
SHRINE_LINES = (
    "The Wellspring is not a place. It is the fact that something was shining "
    "before anybody thought to make it.",
    "Rest here. Whatever you are carrying will come back up to full, and the "
    "road will still be there.",
)

#: The story cast: one emissary per order, in a land whose character suits their
#: doctrine.
EMISSARY_NAMES = {
    "rigour": "Merel, Voice of Rigour",
    "clarity": "Halden, Voice of Clarity",
    "discovery": "Sable, Voice of Discovery",
}
#: Each order's emissary stands in the first of the order's own lands -- the
#: same lands its doctrine work is counted against.
EMISSARY_LANDS = ORDER_LANDS

#: Kinds that stand where they are placed. A keeper keeps their page, a healer
#: keeps their station, a Warden keeps their hall, and a story character you
#: have to find again must not have wandered off.
FIXED = frozenset({"villager", "healer", "emissary", "lumi", "warden", "keeper",
                   "lanternwright"})

#: Tiles an NPC may stand on.
WALKABLE = frozenset({GRASS, ROAD, FLOOR, CLINIC, PLAZA, GARDEN, SAND})

#: Where wildlife may stand: the open country only. A beast on a village floor
#: would break the one safety rule the map teaches -- inside the walls, nothing
#: fights you.
WILD_GROUND = frozenset({GRASS, ROAD, SAND})


def _seed(text: str) -> int:
    """A stable integer from a string.

    Parameters
    ----------
    text : str
        Any identifier.

    Returns
    -------
    int
        The same value on every run.
    """
    value = 2166136261
    for char in text:
        value = ((value ^ ord(char)) * 16777619) & 0xFFFFFFFF
    return value


@dataclasses.dataclass
class Npc:
    """Someone or something living in the world.

    Attributes
    ----------
    kind : str
        ``villager``, ``townsfolk``, ``healer``, ``keeper``, ``warden``,
        ``emissary``, ``animal`` or ``beast``.
    name : str
        Display name.
    x, y : float
        Position in world units.
    home : tuple of float
        Where it wanders around.
    radius : float
        How far it strays from home.
    line : str
        What it says when spoken to. For someone with more to say this is the
        first of :attr:`lines`.
    facing : str
        ``down``, ``up``, ``left`` or ``right``.
    address : str
        For a villager, the page they keep.
    lines : tuple of str
        Full dialogue, one screen per entry. Empty means :attr:`line` is all
        of it.
    role : str
        What talking to them means to the game: ``""`` for flavour,
        ``healer``, ``tavern``, ``shop``, ``smithy``, ``shrine``,
        ``warden:<key>`` or ``emissary:<order>``.
    species : str
        For an animal or a marked beast, which body it is -- so an encounter
        fights the animal that was standing there rather than a fresh roll.
    tier : int
        For a marked beast, how hard its land is. Steering reads it: a heavier
        label is a bolder animal.
    """

    kind: str
    name: str
    x: float
    y: float
    home: tuple[float, float]
    radius: float
    line: str
    facing: str = "down"
    address: str = ""
    lines: tuple[str, ...] = ()
    role: str = ""
    species: str = ""
    tier: int = 1
    #: Set on the frame this one first becomes aware of the player and cleared
    #: by whoever draws it. The moment a creature notices you is the moment
    #: worth showing -- without it, "has not seen you" and "is stalking you"
    #: look identical, which is most of what a notice radius is for.
    startled: bool = False
    _phase: float = 0.0
    #: Steering state, built the first time this one is stepped. See
    #: :mod:`.steering`: what it is (:class:`~.steering.Temper`), where it is in
    #: its current decision (:class:`~.steering.Drift`), and its own generator
    #: so that one creature's wandering does not depend on how many others were
    #: updated first.
    _temper: steering.Temper | None = None
    _drift: steering.Drift | None = None
    _rng: random.Random | None = None

    @property
    def traits(self) -> tuple[str, ...]:
        """What this one's body does, if it has a body in the bestiary.

        Returns
        -------
        tuple of str
            Trait keys, empty for anybody who is not an animal.
        """
        body = SPECIES_BY_KEY.get(self.species)
        return (body.trait,) if body is not None else ()

    @property
    def drift(self) -> steering.Drift:
        """This one's steering state, created on demand.

        Returns
        -------
        chisurf.plugins.misc.games.lumis_quest.api.steering.Drift
            Mutated as it walks.
        """
        if self._drift is None:
            seed = _seed(f"{self.kind}:{self.name}:{self.home}")
            self._rng = random.Random(seed)
            self._temper = steering.temper_for(self.kind, self.traits, self.tier)
            self._drift = steering.Drift(
                facing=steering.NAMES.index(self.facing)
                if self.facing in steering.NAMES else steering.DOWN,
                phase=self._phase,
            )
        return self._drift

    @property
    def temper(self) -> steering.Temper:
        """What kind of mover this one is.

        Returns
        -------
        chisurf.plugins.misc.games.lumis_quest.api.steering.Temper
            Constant for its lifetime.
        """
        self.drift  # noqa: B018 -- builds both halves together
        return self._temper

    @property
    def lift(self) -> float:
        """How far off the ground to *draw* this one.

        Returns
        -------
        float
            World units, never applied to collision -- a hovering wraith is
            still something you walk into. Keeping the visual height separate
            from the real one is the reason a bob can be given to anything
            without re-auditing what it can now pass over.
        """
        return self._drift.fake_z() if self._drift is not None else 0.0

    @property
    def dialogue(self) -> tuple[str, ...]:
        """Everything they have to say, in order.

        Returns
        -------
        tuple of str
            :attr:`lines` when there are any, else the single :attr:`line`.
        """
        return self.lines if self.lines else (self.line,)

    def distance_to(self, x: float, y: float) -> float:
        """Distance to a point.

        Parameters
        ----------
        x, y : float
            World coordinates.

        Returns
        -------
        float
            World units.
        """
        return math.hypot(self.x - x, self.y - y)


def rumours(world, village) -> tuple[str, ...]:
    """What the tavern has heard.

    A rumour in a game of this kind is a hint system wearing a costume, and it
    only works if it points at something that is actually there. Every line here
    is read off the world: a Warden who really is in that town, a land that
    really is dark, a crossing that really is in those cliffs.

    Parameters
    ----------
    world : chisurf.plugins.misc.games.lumis_quest.api.world.World
        The world to read.
    village : chisurf.plugins.misc.games.lumis_quest.api.world.Village
        Where the tavern is, so the rumour is about somewhere else.

    Returns
    -------
    tuple of str
        Two or three lines.
    """
    heard: list[str] = []
    seats = [v for v in world.villages if v.warden and v is not village]
    if seats:
        seat = seats[_seed(village.place) % len(seats)]
        warden = WARDEN_BY_KEY.get(seat.warden)
        if warden is not None:
            heard.append(
                f"{warden.name} holds the hall at {seat.place}. They say "
                f"{warden.name.split()[0]} has never lost to anyone who "
                f"attacked every turn."
            )
    caves = world.caves
    if caves:
        col, row = caves[_seed(village.name) % len(caves)]
        region = world.region_at(col * TILE, row * TILE)
        where = region.title if region is not None else "the highlands"
        heard.append(f"There is a cave in the cliffs of {where}. People who go "
                     f"in come out saying the same three words.")
    darkest = None
    for region in world.regions:
        rooms = region.rooms
        if not rooms:
            continue
        dark = sum(1 for room in rooms if room.state == "wild") / len(rooms)
        if darkest is None or dark > darkest[1]:
            darkest = (region, dark)
    if darkest is not None and darkest[1] > 0.2:
        heard.append(f"Nobody has been through {darkest[0].title} in years. "
                     f"Whatever is in there has had the run of it.")
    return tuple(heard) or ("Quiet week. Nothing worth the price of the ale.",)


def populate(world) -> list[Npc]:
    """Fill a world with its inhabitants.

    Parameters
    ----------
    world : chisurf.plugins.misc.games.lumis_quest.api.world.World
        The world to populate.

    Returns
    -------
    list of Npc
        Villagers, townsfolk, premises keepers, Wardens, animals and beasts.
    """
    from .world import SETTLED, WILD

    people: list[Npc] = []

    for region in world.regions:
        for village in region.villages:
            prosperity = village.prosperity
            for room in village.rooms:
                if room.state != SETTLED:
                    continue
                seed = _seed(room.address)
                # Just south of their building, out of the doorway.
                x, y = room.position
                spot = (x, y + TILE)
                if is_blocking(world.tile_at(int(spot[0] // TILE), int(spot[1] // TILE))):
                    spot = (x, y)
                line = (
                    GREETINGS[seed % len(GREETINGS)]
                    if prosperity > 0.4
                    else STRUGGLING[seed % len(STRUGGLING)]
                )
                # The greeting stays theirs; what follows it comes off the
                # page they keep, when the page has prose worth repeating.
                people.append(
                    Npc(
                        kind="villager",
                        name=room.title[:28],
                        x=spot[0], y=spot[1], home=spot, radius=TILE * 0.9,
                        line=line, lines=(line, *page_lines(room)),
                        address=room.address,
                        _phase=(seed % 1000) / 1000.0 * math.tau,
                    )
                )

            people.extend(_premises_keepers(world, village))

            # Townsfolk, scaled to the compound's size rather than to how many
            # pages are settled: the keeper-per-page rule is the one thing on
            # the map that means something, and these are the people around it.
            col, row, width, height = village.rect
            interior = max(0, (width - 2) * (height - 2))
            for index in range(min(6, max(1, interior // 44))):
                seed = _seed(f"{village.place}:townsfolk:{index}")
                name, line = TOWNSFOLK[seed % len(TOWNSFOLK)]
                spot = _open_spot(
                    world,
                    col + 2 + (seed % max(1, width - 4)),
                    row + 2 + ((seed >> 8) % max(1, height - 4)),
                    seed,
                    span=3,
                )
                if spot is None:
                    continue
                people.append(
                    Npc(kind="townsfolk", name=name, x=spot[0], y=spot[1], home=spot,
                        radius=TILE * 1.2, line=line,
                        _phase=(seed % 1000) / 1000.0 * math.tau)
                )

            # The healer, at the recovery station just inside the gate.
            clinic_col, clinic_row = village.clinic
            seed = _seed(f"{village.place}:healer")
            spot = _open_spot(world, clinic_col + 1, clinic_row, seed, span=3)
            if spot is not None:
                people.append(
                    Npc(kind="healer", name="the recovery warden",
                        x=spot[0], y=spot[1], home=spot, radius=0.0,
                        line=HEALER_LINES[0], lines=HEALER_LINES, role="healer",
                        _phase=(seed % 1000) / 1000.0 * math.tau)
                )

            # Unmarked animals on the open ground outside. These are what the
            # marked ones used to be.
            for index in range(1 + (_seed(village.place) % 3)):
                seed = _seed(f"{village.place}:animal:{index}")
                kind, line = ANIMALS[seed % len(ANIMALS)]
                spot = _open_spot(world, col + width // 2, row + height + 3 + index * 2,
                                  seed, allowed=WILD_GROUND)
                if spot is None:
                    continue
                people.append(
                    Npc(kind="animal", name=kind, x=spot[0], y=spot[1], home=spot,
                        radius=TILE * 3.0, line=line, species=kind,
                        _phase=(seed % 1000) / 1000.0 * math.tau)
                )

        # Marked beasts roam the wilds: a handful per land, scaled to how much
        # of it is still unread, so a neglected land is also a dangerous one.
        wild = sum(1 for room in region.rooms if room.state == WILD)
        rcol, rrow, rwidth, rheight = region.rect
        for index in range(min(10, 2 + wild // 10)):
            seed = _seed(f"{region.name}:beast:{index}")
            spot = _open_spot(
                world,
                rcol + 3 + (seed % max(1, rwidth - 6)),
                rrow + 3 + ((seed >> 8) % max(1, rheight - 6)),
                seed,
                allowed=WILD_GROUND,
            )
            if spot is None:
                continue
            species = SPECIES[seed % len(SPECIES)]
            people.append(
                # A wide leash, because most of these are going to spend the
                # encounter running away from you and a short one would put a
                # wall behind them that the player cannot see.
                Npc(kind="beast", name=f"a marked {species.name}",
                    x=spot[0], y=spot[1], home=spot, radius=TILE * 8.0,
                    line="It is burning, and it cannot stop.",
                    species=species.key, tier=region.crossing_tier,
                    _phase=(seed % 1000) / 1000.0 * math.tau)
            )

    people.extend(_story_cast(world))
    people.extend(_warden_cast(world))
    return people


def _premises_keepers(world, village) -> list[Npc]:
    """Put somebody at the door of every premises in a settlement.

    Parameters
    ----------
    world : World
        For finding standable ground.
    village : Village
        The settlement, whose ``premises`` says what it has.

    Returns
    -------
    list of Npc
        One keeper per premises, fewer where there is nowhere to stand.
    """
    made: list[Npc] = []
    spec = {
        "tavern": (TAVERN_KEEPER, TAVERN_LINES, "tavern"),
        "shop": (SHOP_KEEPER, SHOP_LINES, "shop"),
        "smithy": (SMITH, SMITH_LINES, "smithy"),
        "shrine": (PRIEST, SHRINE_LINES, "shrine"),
    }
    for key, (name, lines, role) in spec.items():
        where = village.premises.get(key)
        if where is None:
            continue
        seed = _seed(f"{village.place}:{key}")
        spot = _open_spot(world, where[0], where[1] + 1, seed, span=3)
        if spot is None:
            continue
        made.append(
            Npc(kind="keeper", name=name, x=spot[0], y=spot[1], home=spot,
                radius=0.0, line=lines[0], lines=lines, role=role,
                _phase=(seed % 1000) / 1000.0 * math.tau)
        )
    return made


def _warden_cast(world) -> list[Npc]:
    """Stand each Warden at the door of their hall.

    Parameters
    ----------
    world : World
        The world to place them in.

    Returns
    -------
    list of Npc
        One per Warden with a seat.
    """
    made: list[Npc] = []
    for village in world.villages:
        warden = WARDEN_BY_KEY.get(village.warden)
        if warden is None:
            continue
        where = village.premises.get("hall") or village.premises.get("well")
        if where is None:
            continue
        seed = _seed(f"warden:{warden.key}")
        spot = _open_spot(world, where[0], where[1] + 1, seed, span=4)
        if spot is None:
            continue
        made.append(
            Npc(kind="warden", name=f"{warden.name}, {warden.title}",
                x=spot[0], y=spot[1], home=spot, radius=0.0,
                line=warden.lines[0], lines=warden.lines,
                role=f"warden:{warden.key}",
                _phase=(seed % 1000) / 1000.0 * math.tau)
        )
    return made


#: What the keeper says over you when you come to. The last line hands the
#: player their first goal, so the scene ends pointed somewhere.
ELDER_LINES = (
    "So. The probe is awake. I am Bram; I keep what is left of the lamps here.",
    "You were sent from the Wellspring, the way light is sent -- suddenly, and "
    "without being asked. The Fading has reached even this road.",
    "A hound of light came through before you and would not leave. He is lying "
    "out where the road bends, nearly spent. He has been waiting for someone "
    "to follow.",
    "Find him first. Then mind the grass -- there are hares out there burning "
    "gold, and nothing about that is natural. Go.",
)

#: What passes between Iris and the dim hound. No words on his side, of course.
LUMI_LINES = (
    "The hound is barely an ember. He lifts his head, and something in his "
    "glow steadies as he looks at you.",
    "He knows what you are. He gets to his feet, shakes the dark off his "
    "coat, and his light comes back green and full.",
    "Nobody ever marked his line. Whatever he carries, he carries by right.",
)


def awakening_cast(world) -> tuple[tuple[float, float], list[Npc]]:
    """Stage the waking scene: where Iris comes to, and who is there.

    A run does not start mid-stride: Iris wakes in the open with the keeper
    Bram standing over her, and the dim hound lies further along the road,
    waiting to be found. Both stand fixed; both are placed off the first
    settlement's gate so the scene points at the world's first door.

    Parameters
    ----------
    world : chisurf.plugins.misc.games.lumis_quest.api.world.World
        The world to stage in.

    Returns
    -------
    tuple
        ``(waking_spot, [elder, lumi])`` in world units. An empty world gives
        ``((0, 0), [])``.
    """
    village = next((v for region in world.regions for v in region.villages), None)
    if village is None:
        return ((0.0, 0.0), [])
    gate_col, gate_row = village.gate

    spot = _open_spot(world, gate_col, gate_row + 6, _seed("waking"),
                      span=7, allowed=WILD_GROUND) or (
        (gate_col + 0.5) * TILE, (gate_row + 1.5) * TILE)
    cast: list[Npc] = []

    elder_spot = _open_spot(world, int(spot[0] // TILE) - 1, int(spot[1] // TILE),
                            _seed("elder"), span=5, allowed=WILD_GROUND)
    if elder_spot is not None:
        cast.append(
            Npc(kind="villager", name="Bram, the last keeper",
                x=elder_spot[0], y=elder_spot[1], home=elder_spot, radius=0.0,
                line=ELDER_LINES[0], lines=ELDER_LINES, role="elder")
        )

    lumi_spot = _open_spot(world, gate_col + 3, gate_row + 9, _seed("dim-hound"),
                           span=7, allowed=WILD_GROUND)
    if lumi_spot is not None:
        cast.append(
            Npc(kind="lumi", name="a dim hound",
                x=lumi_spot[0], y=lumi_spot[1], home=lumi_spot, radius=0.0,
                line=LUMI_LINES[0], lines=LUMI_LINES, role="lumi")
        )
    return (spot, cast)


def _story_cast(world) -> list[Npc]:
    """Place the named story characters: one emissary per order.

    Each stands outside the gate of the first settlement in a land whose
    character suits their doctrine. Talking to one is how an order is chosen;
    :mod:`.story` holds what they believe.

    Parameters
    ----------
    world : chisurf.plugins.misc.games.lumis_quest.api.world.World
        The world to place them in.

    Returns
    -------
    list of Npc
        One fixed emissary per order, fewer if the world has nowhere to stand.
    """
    if not world.regions:
        return []
    by_name = {region.name: region for region in world.regions}
    cast: list[Npc] = []
    for index, (key, order) in enumerate(ORDERS.items()):
        region = next(
            (by_name[name] for name in EMISSARY_LANDS.get(key, ()) if name in by_name),
            world.regions[index % len(world.regions)],
        )
        village = next(
            (v for v in region.villages if v.name == "The Unlinked"), None
        ) if key == "discovery" else None
        village = village or (region.villages[0] if region.villages else None)
        if village is None:
            continue
        gate_col, gate_row = village.gate
        seed = _seed(f"emissary:{key}")
        spot = _open_spot(world, gate_col - 2, gate_row + 1, seed, span=5)
        if spot is None:
            continue
        lines = (
            f"I am {EMISSARY_NAMES[key]}. I speak for {order['name']}.",
            order["belief"],
            order["on_marking"],
            f"Our creed: {order['creed']}",
        )
        cast.append(
            Npc(kind="emissary", name=EMISSARY_NAMES[key],
                x=spot[0], y=spot[1], home=spot, radius=0.0,
                line=lines[0], lines=lines, role=f"emissary:{key}",
                _phase=(seed % 1000) / 1000.0 * math.tau)
        )
    return cast


def dark_population(world) -> list[Npc]:
    """Who is standing in the dark manifold.

    They are not monsters. They are the shelved: labels driven all the way down,
    still in the shape of whatever was carrying them. One of the few things the
    game asks a player to feel is that this is somebody's fault.

    Parameters
    ----------
    world : chisurf.plugins.misc.games.lumis_quest.api.world.World
        The world, read for its dark grid.

    Returns
    -------
    list of Npc
        Wraiths, thickest where the living world is emptiest.
    """
    from .darkworld import WRAITH_LINES

    made: list[Npc] = []
    # Vesper, at the door of the only built thing down here. Without her the
    # last two beats of the arc are unreachable: everything she says is
    # written, and nothing was standing anywhere to say it.
    if world.tower is not None:
        col, row = world.tower
        made.append(
            Npc(kind="lanternwright", name="Vesper, the Lanternwright",
                x=(col + 0.5) * TILE, y=(row + 1.5) * TILE,
                home=((col + 0.5) * TILE, (row + 1.5) * TILE), radius=0.0,
                line="She has been expecting somebody for a long time.",
                role="lanternwright")
        )
    for region in world.regions:
        rcol, rrow, rwidth, rheight = region.rect
        for index in range(12):
            seed = _seed(f"{region.name}:shelved:{index}")
            spot = _open_spot(
                world,
                rcol + 3 + (seed % max(1, rwidth - 6)),
                rrow + 3 + ((seed >> 8) % max(1, rheight - 6)),
                seed,
                allowed=frozenset({T.ASH, T.FLOOR, T.ROAD, T.PLAZA}),
                dark=True,
            )
            if spot is None:
                continue
            species = SPECIES[(seed >> 3) % len(SPECIES)]
            made.append(
                Npc(kind="wraith", name=f"the shape of a {species.name}",
                    x=spot[0], y=spot[1], home=spot, radius=TILE * 4.0,
                    line=WRAITH_LINES[seed % len(WRAITH_LINES)],
                    species=species.key,
                    _phase=(seed % 1000) / 1000.0 * math.tau)
            )
    return made


def species_of(npc: Npc):
    """The body an animal or beast NPC is.

    Parameters
    ----------
    npc : Npc
        Whoever is being fought or looked at.

    Returns
    -------
    Species or None
        ``None`` for anyone who is not an animal.
    """
    return SPECIES_BY_KEY.get(npc.species)


def _open_spot(world, col: int, row: int, seed: int, span: int = 5,
               allowed: frozenset[int] = WALKABLE, dark: bool = False):
    """Find a standable tile near a target cell.

    Parameters
    ----------
    world : World
        The world.
    col, row : int
        Where to look around.
    seed : int
        Deterministic offset.
    span : int, optional
        How far to search.
    allowed : frozenset of int, optional
        Tiles that qualify. Wildlife passes :data:`WILD_GROUND` so a beast can
        never end up standing on a village floor.
    dark : bool, optional
        Look in the dark manifold instead.

    Returns
    -------
    tuple of float or None
        World coordinates, or ``None`` when nothing suitable is near.
    """
    for step in range(span * span):
        dx = (step + seed) % span - span // 2
        dy = (step // span + seed // 7) % span - span // 2
        c, r = col + dx, row + dy
        if world.tile_at(c, r, dark) in allowed:
            return ((c + 0.5) * TILE, (r + 0.5) * TILE)
    return None


#: What can be walked on in the dark manifold. Almost nothing: down there the
#: road you built is the only thing still shaped like a road.
DARK_GROUND = frozenset({T.ASH, T.FLOOR, T.ROAD, T.PLAZA})


def update(people: list[Npc], world, dt: float, clock: float,
           near: tuple[float, float] | None = None, radius: float = 700.0,
           dark: bool = False) -> None:
    """Move the world's inhabitants.

    Everything here steers by :mod:`.steering` -- a tile-aligned decision, then
    a leg of exactly one tile -- rather than by a smooth curve through the
    clock, which is what this did before. The curve was cheap and it was
    wrong in a way that took a while to name: every creature in the world was
    tracing the *same* figure of eight at a different phase, nothing ever
    noticed the player, and because a curve does not respect a grid the
    unlucky ones spent their lives grinding along a wall they could not turn
    off. A creature that decides on the grid cannot end a step inside one.

    Only those near the player are stepped. The world holds well over a hundred
    of them and the ones nobody can see do not need to breathe.

    Parameters
    ----------
    people : list of Npc
        Everyone.
    world : World
        For collision, and for the lamp posts that wildlife steers by.
    dt : float
        Seconds elapsed.
    clock : float
        Running time. Kept for callers, and used for the visual hover.
    near : tuple of float, optional
        Only update within ``radius`` of this point. Doubles as the player's
        position, which is what homing and fleeing are measured against.
    radius : float, optional
        How far to bother.
    dark : bool, optional
        Collide against the dark manifold.
    """
    for npc in people:
        if npc.kind in FIXED:
            continue  # they stand where they stand
        if near is not None and npc.distance_to(*near) > radius:
            continue

        # A beast may never wander onto village ground, even through a gate:
        # inside the walls nothing fights you, and that rule is worth more than
        # a beast's freedom of movement.
        ground = WILD_GROUND if npc.kind == "beast" else WALKABLE
        if dark:
            ground = DARK_GROUND

        temper = npc.temper
        bait = _light_near(npc, world, temper, near, dark) if temper.greed else None

        was_aware = npc.drift.noticed
        npc.x, npc.y = steering.advance(
            temper, npc.drift, npc.x, npc.y, dt,
            _passage(npc, world, ground, dark), npc._rng,
            target=near, bait=bait,
        )
        if npc.drift.noticed and not was_aware and temper.homing:
            npc.startled = True
        npc.facing = npc.drift.name


def _light_near(npc: Npc, world, temper, player: tuple[float, float] | None,
                dark: bool) -> tuple[float, float] | None:
    """The brightest thing in this creature's neighbourhood.

    Two sources, and the nearer one wins. The lamp posts stand still and are
    the reason a moth is in the square at all; **Iris is the other**, and she is
    the brighter of the two -- a probe is a photon given a body, so the light
    the wildlife steers by is mostly the player walking through it. That gives
    the greed flag something to do everywhere rather than only inside town
    walls, where wildlife is not allowed to go in the first place: without her,
    a moth's whole reason for being a moth is switched off across the entire
    map, and nothing fails.

    In the dark manifold there are no lamps at all, and she is the only light
    there has been for a long time.

    Parameters
    ----------
    npc : Npc
        Whose neighbourhood.
    world : World
        For the lamp table.
    temper : chisurf.plugins.misc.games.lumis_quest.api.steering.Temper
        For its reach.
    player : tuple of float or None
        Where Iris is.
    dark : bool
        Which manifold.

    Returns
    -------
    tuple of float or None
        The light to steer by, or ``None`` when there is none in reach.
    """
    reach = temper.reach or TILE * 8.0
    lamp = None
    if not dark and hasattr(world, "nearest_light"):
        lamp = world.nearest_light(npc.x, npc.y, reach)
    if player is None:
        return lamp
    if npc.distance_to(*player) > reach:
        return lamp
    if lamp is None:
        return player
    return min((lamp, player), key=lambda one: npc.distance_to(*one))


def _passage(npc: Npc, world, ground: frozenset[int], dark: bool):
    """A test for whether one creature may take one step.

    The leash is folded in here rather than applied afterwards, so straying too
    far from home is indistinguishable from a wall -- which means the same
    thirty-two re-rolls that get a creature out of a dead end also turn it
    around at the edge of its range, instead of it pressing against a boundary
    that is not there and shivering.

    Parameters
    ----------
    npc : Npc
        Whose step it is.
    world : World
        For the grid.
    ground : frozenset of int
        Tiles this one may stand on.
    dark : bool
        Which manifold.

    Returns
    -------
    callable
        ``passable(direction) -> bool``.
    """
    def passable(direction: int) -> bool:
        step = steering.STEPS[direction]
        col = int(npc.x // TILE) + step[0]
        row = int(npc.y // TILE) + step[1]
        if world.tile_at(col, row, dark) not in ground:
            return False
        if npc.radius <= 0.0:
            return True
        x = (col + 0.5) * TILE
        y = (row + 0.5) * TILE
        return abs(x - npc.home[0]) < npc.radius and abs(y - npc.home[1]) < npc.radius

    return passable


def _blocked(world, x: float, y: float, dark: bool = False) -> bool:
    """Whether a position is solid.

    Parameters
    ----------
    world : World
        The world.
    x, y : float
        World coordinates.
    dark : bool, optional
        Test the dark manifold.

    Returns
    -------
    bool
        True when nothing may stand there.
    """
    return is_blocking(world.tile_at(int(x // TILE), int(y // TILE), dark))


def nearest(people: list[Npc], x: float, y: float, within: float = TILE * 1.6):
    """Whoever is close enough to speak to.

    Parameters
    ----------
    people : list of Npc
        Everyone.
    x, y : float
        Where the player stands.
    within : float, optional
        Reach, in world units.

    Returns
    -------
    Npc or None
        The closest one in reach.
    """
    best = None
    best_distance = within
    for npc in people:
        distance = npc.distance_to(x, y)
        if distance <= best_distance:
            best, best_distance = npc, distance
    return best


def indoor_population(interior) -> list[Npc]:
    """Populate an interior room with resident NPCs on its designated spots.

    Parameters
    ----------
    interior : chisurf.plugins.misc.games.lumis_quest.api.interiors.Interior
        The interior room.

    Returns
    -------
    list of Npc
        Resident NPCs standing inside the room.
    """
    cast: list[Npc] = []
    if not getattr(interior, "spots", None):
        return cast

    kind = getattr(interior, "kind", "house")
    seed = _seed(f"indoor:{getattr(interior, 'key', 'room')}")

    if kind == "tavern":
        roles = [
            ("barkeep", "Barkeep", "Welcome to the tavern! What's your story?"),
            ("patron", "Traveler", "The Wardens hold the seals of light in each land."),
        ]
    elif kind == "smithy":
        roles = [
            ("smith", "Lens-Grinder", "Optical precision is key to focusing emission."),
        ]
    elif kind == "shop":
        roles = [
            ("merchant", "Supply Merchant", "Need photostabilizers or reagents for your bench?"),
        ]
    elif kind == "shrine":
        roles = [
            ("priest", "Shrine Keeper", "May your fluorophores shine bright and untarnished."),
        ]
    elif kind == "hall":
        roles = [
            ("warden_guard", "Hall Guard", "This is the Warden's hall. Speak with care."),
        ]
    else:  # house
        roles = [
            ("resident", "Villager", "Make yourself at home. The wilds can be harsh."),
        ]

    for idx, spot in enumerate(interior.spots):
        if idx >= len(roles):
            break
        role_key, name, line = roles[idx]
        cast.append(
            Npc(
                kind="villager",
                name=name,
                x=(spot[0] + 0.5) * TILE,
                y=(spot[1] + 0.5) * TILE,
                home=((spot[0] + 0.5) * TILE, (spot[1] + 0.5) * TILE),
                radius=0.0,
                line=line,
                lines=(line,),
                role=role_key,
                _phase=(seed % 1000) / 1000.0 * math.tau,
            )
        )

    return cast
