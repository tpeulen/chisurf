"""The people, animals and beasts that live in the world.

A map with nothing moving on it is a diagram. This is what makes it a place.

Three kinds, and each is derived rather than sprinkled:

* **Villagers** stand outside settled buildings. That is not decoration -- the
  design has always been that reviewing a page *turns a wild room into a
  villager*, so the population of a village is literally how much of that
  section somebody has read. A ghost town is a section nobody has touched.
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

#: Tiles an NPC may stand on.
WALKABLE = frozenset({GRASS, ROAD, FLOOR, CLINIC})


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
        ``villager``, ``animal`` or ``beast``.
    name : str
        Display name.
    x, y : float
        Position in world units.
    home : tuple of float
        Where it wanders around.
    radius : float
        How far it strays from home.
    line : str
        What it says when spoken to.
    facing : str
        ``down``, ``up``, ``left`` or ``right``.
    address : str
        For a villager, the page they keep.
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
    _phase: float = 0.0

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

            # One or two animals per village, on the open ground outside it.
            col, row, width, height = village.rect
            for index in range(1 + (_seed(village.name) % 2)):
                seed = _seed(f"{village.name}:animal:{index}")
                kind, line = ANIMALS[seed % len(ANIMALS)]
                spot = _open_spot(world, col + width // 2, row + height + 3 + index * 2, seed)
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
            )
            if spot is None:
                continue
            people.append(
                Npc(kind="beast", name="something in the grass", x=spot[0], y=spot[1],
                    home=spot, radius=TILE * 5.0,
                    line="It does not want to talk.",
                    _phase=(seed % 1000) / 1000.0 * math.tau)
            )
    return people


def _open_spot(world, col: int, row: int, seed: int, span: int = 5):
    """Find a walkable tile near a target cell.

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

    Returns
    -------
    tuple of float or None
        World coordinates, or ``None`` when nothing walkable is near.
    """
    for step in range(span * span):
        dx = (step + seed) % span - span // 2
        dy = (step // span + seed // 7) % span - span // 2
        c, r = col + dx, row + dy
        if world.tile_at(c, r) in WALKABLE:
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
        if npc.kind == "villager":
            continue  # they stand where they stand
        if near is not None and npc.distance_to(*near) > radius:
            continue
        speed = 14.0 if npc.kind == "animal" else 22.0
        angle = npc._phase + clock * (0.35 if npc.kind == "animal" else 0.22)
        dx = math.cos(angle) * speed * dt
        dy = math.sin(angle * 1.3) * speed * dt

        if not _blocked(world, npc.x + dx, npc.y) and \
                abs(npc.x + dx - npc.home[0]) < npc.radius:
            npc.x += dx
        if not _blocked(world, npc.x, npc.y + dy) and \
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
