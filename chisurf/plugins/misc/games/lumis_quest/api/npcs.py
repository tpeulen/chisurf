"""The people, animals and beasts that live in the world.

A map with nothing moving on it is a diagram. This is what makes it a place.

Six kinds, and each is derived rather than sprinkled:

* **Villagers** stand outside settled buildings. That is not decoration -- the
  design has always been that reviewing a page *turns a wild room into a
  villager*, so the population of a village is literally how much of that
  section somebody has read. A ghost town is a section nobody has touched.
* **Townsfolk** live in the compounds regardless of review state, scaled to the
  village's size rather than to its pages -- a walled town with exactly as many
  people as sign-offs is a spreadsheet wearing houses. The keeper-per-settled-
  page rule stays intact; these are the people around it.
* **Healers** keep the recovery station just inside every gate. One fixed,
  named person per clinic, so the place that heals you has someone in it.
* **Emissaries** are the story cast: one per order, standing in a land whose
  character suits their doctrine. Talking to one is how an order is chosen --
  a doctrine you pledge to is a person you met, not a menu row.
* **Animals** wander the open ground inside a land's borders. They are the only
  thing here that means nothing at all, and that is deliberate: a world in which
  every single object is a metric is exhausting to walk through.
* **Beasts** roam the wilds between compounds. Touching one starts a fight, so
  the wilderness is dangerous in a way that standing next to a building is not.

Everything is seeded by position or by page address, so the population is the
same on every run: a village whose people rearrange themselves each time you
visit is not somewhere you can come to know.
"""

from __future__ import annotations

import dataclasses
import math

from .story import ORDER_LANDS, ORDERS
from .tiles import CLINIC, FLOOR, GRASS, ROAD, TILE, is_blocking

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

#: What a villager says about the state of their village.
STRUGGLING = (
    "Half our houses are dark. Nobody has been through them.",
    "We could use a reader. Plenty here has never been checked.",
    "The lamps go out one at a time when nobody comes.",
)

#: Animal kinds and their calls.
ANIMALS = (
    ("sheep", "The creature regards you and returns to the grass."),
    ("bird", "It startles, circles once, and settles again."),
    ("hare", "It watches you from a safe distance."),
)

#: Townsfolk who are not keepers: a village the size of a town needs people in
#: it who are not a review metric. Chosen by seed, so a given village always
#: has the same smith.
TOWNSFOLK = (
    ("the smith", "Optics want grinding. Bring me glass and I will put an edge on it."),
    ("a child", "Have you seen the hound glow? Everyone says Lumi can smell light."),
    ("the gatekeeper", "The gate stays open. It is readers we are short of, not doors."),
    ("the gardener", "A tended page keeps its colour. Same as anything planted."),
    ("the carter", "I haul between villages. The dark stretches get longer every year."),
    ("the lamplighter", "I light what I can reach. The high shelves need someone like you."),
)

#: What the healer at every recovery station says.
HEALER_LINES = (
    "This pad rekindles a spent team. Stand on it a while.",
    "Bleached is not gone. Light comes back, if you give it somewhere quiet.",
    "Fill your team before the wilds. Attrition is what kills probes, not beasts.",
)

#: The story cast: one emissary per order, in a land whose character suits the
#: doctrine. Directories are tried in order; a corpus missing them all still
#: gets its emissary somewhere (see :func:`_story_cast`).
EMISSARY_NAMES = {
    "rigour": "Merel, Voice of Rigour",
    "clarity": "Halden, Voice of Clarity",
    "discovery": "Sable, Voice of Discovery",
}
#: Each order's emissary stands in the first of the order's own lands — the
#: same lands its doctrine work is counted against.
EMISSARY_LANDS = ORDER_LANDS

#: Kinds that stand where they are placed. A keeper keeps their page, a healer
#: keeps their station, and a story character you have to find again must not
#: have wandered off. The dim hound waits where it lies until befriended.
FIXED = frozenset({"villager", "healer", "emissary", "lumi"})

#: Tiles an NPC may stand on.
WALKABLE = frozenset({GRASS, ROAD, FLOOR, CLINIC})

#: Where wildlife may stand: the open country only. A beast on a village floor
#: would break the one safety rule the map teaches -- inside the walls, nothing
#: fights you.
WILD_GROUND = frozenset({GRASS, ROAD})


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
        ``villager``, ``townsfolk``, ``healer``, ``emissary``, ``animal`` or
        ``beast``.
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
        ``healer``, or ``emissary:<order>``.
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
    _phase: float = 0.0

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


def populate(world) -> list[Npc]:
    """Fill a world with its inhabitants.

    Parameters
    ----------
    world : chisurf.plugins.misc.games.lumis_quest.api.world.World
        The world to populate.

    Returns
    -------
    list of Npc
        Villagers, animals and beasts.
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
                people.append(
                    Npc(
                        kind="villager",
                        name=room.title[:28],
                        x=spot[0], y=spot[1], home=spot, radius=TILE * 0.9,
                        line=line, address=room.address,
                        _phase=(seed % 1000) / 1000.0 * math.tau,
                    )
                )

            # Townsfolk, scaled to the compound's size rather than to how many
            # pages are settled: the keeper-per-page rule is the one thing on
            # the map that means something, and these are the people around it.
            col, row, width, height = village.rect
            interior = max(0, (width - 2) * (height - 2))
            for index in range(min(5, max(1, interior // 48))):
                seed = _seed(f"{village.name}:townsfolk:{index}")
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

            # The healer, at the recovery station just inside the gate. The
            # place that heals you should have someone in it who says so.
            clinic_col, clinic_row = village.clinic
            seed = _seed(f"{village.name}:healer")
            spot = _open_spot(world, clinic_col + 1, clinic_row, seed, span=3)
            if spot is not None:
                people.append(
                    Npc(kind="healer", name="the recovery warden",
                        x=spot[0], y=spot[1], home=spot, radius=0.0,
                        line=HEALER_LINES[0], lines=HEALER_LINES, role="healer",
                        _phase=(seed % 1000) / 1000.0 * math.tau)
                )

            # One or two animals per village, on the open ground outside it.
            for index in range(1 + (_seed(village.name) % 2)):
                seed = _seed(f"{village.name}:animal:{index}")
                kind, line = ANIMALS[seed % len(ANIMALS)]
                spot = _open_spot(world, col + width // 2, row + height + 3 + index * 2,
                                  seed, allowed=WILD_GROUND)
                if spot is None:
                    continue
                people.append(
                    Npc(kind="animal", name=kind, x=spot[0], y=spot[1], home=spot,
                        radius=TILE * 3.0, line=line,
                        _phase=(seed % 1000) / 1000.0 * math.tau)
                )

        # Beasts roam the wilds: a handful per land, scaled to how much of it is
        # still unread, so a neglected land is also a dangerous one.
        wild = sum(1 for room in region.rooms if room.state == WILD)
        rcol, rrow, rwidth, rheight = region.rect
        for index in range(min(8, 1 + wild // 12)):
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
            people.append(
                Npc(kind="beast", name="something in the grass", x=spot[0], y=spot[1],
                    home=spot, radius=TILE * 5.0,
                    line="It does not want to talk.",
                    _phase=(seed % 1000) / 1000.0 * math.tau)
            )

    people.extend(_story_cast(world))
    return people


#: What the keeper says over you when you come to. The last line hands the
#: player their first goal, so the scene ends pointed somewhere.
ELDER_LINES = (
    "So. The probe is awake. I am Bram; I keep what is left of the lamps here.",
    "You were sent from the Wellspring, the way light is sent -- suddenly, and "
    "without being asked. The Fading has reached even this road.",
    "A hound of light came through before you and would not leave. It is lying "
    "out where the road bends, nearly spent. It has been waiting for someone "
    "to follow.",
    "Find it first. Then find the village -- the gate is the gap in the south "
    "wall, and the lamps inside still hold. Go.",
)

#: What passes between Iris and the dim hound. No words on its side, of course.
LUMI_LINES = (
    "The hound is barely an ember. It lifts its head, and something in its "
    "glow steadies as it looks at you.",
    "It knows what you are. It gets to its feet, shakes the dark off its "
    "coat, and its light comes back green and full.",
    "Lumi will follow you now. Where light has been, the hound can smell it.",
)


def awakening_cast(world) -> tuple[tuple[float, float], list[Npc]]:
    """Stage the waking scene: where Iris comes to, and who is there.

    A run does not start mid-stride: Iris wakes in the open with the keeper
    Bram standing over her, and the dim hound lies further along the road,
    waiting to be found. Both stand fixed; both are placed off the first
    village's gate so the scene points at the world's first door.

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

    Each stands outside the gate of the first village in a land whose character
    suits their doctrine -- Rigour among the exact and largely unread, Clarity
    on the road worn smooth by learners, Discovery at the markers pointing
    elsewhere. Talking to one is how an order is chosen; :mod:`.story` holds
    what they believe.

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
            f"Our creed: {order['creed']}",
            f"What we want is {order['wants']}.",
        )
        cast.append(
            Npc(kind="emissary", name=EMISSARY_NAMES[key],
                x=spot[0], y=spot[1], home=spot, radius=0.0,
                line=lines[0], lines=lines, role=f"emissary:{key}",
                _phase=(seed % 1000) / 1000.0 * math.tau)
        )
    return cast


def _open_spot(world, col: int, row: int, seed: int, span: int = 5,
               allowed: frozenset[int] = WALKABLE):
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

    Returns
    -------
    tuple of float or None
        World coordinates, or ``None`` when nothing suitable is near.
    """
    for step in range(span * span):
        dx = (step + seed) % span - span // 2
        dy = (step // span + seed // 7) % span - span // 2
        c, r = col + dx, row + dy
        if world.tile_at(c, r) in allowed:
            return ((c + 0.5) * TILE, (r + 0.5) * TILE)
    return None


def update(people: list[Npc], world, dt: float, clock: float,
           near: tuple[float, float] | None = None, radius: float = 700.0) -> None:
    """Move the world's inhabitants.

    Only those near the player are stepped. The world holds well over a hundred
    of them and the ones nobody can see do not need to breathe.

    Parameters
    ----------
    people : list of Npc
        Everyone.
    world : World
        For collision.
    dt : float
        Seconds elapsed.
    clock : float
        Running time, so wandering is a smooth function rather than a random
        walk that jitters.
    near : tuple of float, optional
        Only update within ``radius`` of this point.
    radius : float, optional
        How far to bother.
    """
    for npc in people:
        if npc.kind in FIXED:
            continue  # they stand where they stand
        if near is not None and npc.distance_to(*near) > radius:
            continue
        speed = {"animal": 14.0, "townsfolk": 9.0}.get(npc.kind, 22.0)
        angle = npc._phase + clock * (0.35 if npc.kind == "animal" else 0.22)
        dx = math.cos(angle) * speed * dt
        dy = math.sin(angle * 1.3) * speed * dt

        # A beast may never wander onto village ground, even through a gate:
        # inside the walls, nothing fights you, and that rule is worth more
        # than a beast's freedom of movement.
        ground = WILD_GROUND if npc.kind == "beast" else WALKABLE
        if world.tile_at(int((npc.x + dx) // TILE), int(npc.y // TILE)) in ground and \
                abs(npc.x + dx - npc.home[0]) < npc.radius:
            npc.x += dx
        if world.tile_at(int(npc.x // TILE), int((npc.y + dy) // TILE)) in ground and \
                abs(npc.y + dy - npc.home[1]) < npc.radius:
            npc.y += dy
        npc.facing = ("right" if dx > 0 else "left") if abs(dx) > abs(dy) else (
            "down" if dy > 0 else "up"
        )


def _blocked(world, x: float, y: float) -> bool:
    """Whether a position is solid.

    Parameters
    ----------
    world : World
        The world.
    x, y : float
        World coordinates.

    Returns
    -------
    bool
        True when nothing may stand there.
    """
    return is_blocking(world.tile_at(int(x // TILE), int(y // TILE)))


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
