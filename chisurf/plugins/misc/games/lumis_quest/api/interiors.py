"""Buildings you can walk into, each its own map.

A building on the overworld is one tile. Inside it is a room several times that
size, which is the oldest trick the genre has and the reason its towns feel
inhabited rather than modelled: the exterior is a **doorway**, not a floor plan.
Nobody has ever complained that the inn is bigger on the inside.

That also answers the complaint the overworld could not: a settlement is only
so large before it stops being walkable, but every building in it can hold a
room with people in it, and those rooms cost nothing to cross.

Six kinds, and each is furnished from what it is *for* rather than from a
random scatter -- a tavern has a bar with somebody behind it and tables with
somebody at them, a smithy has a forge at the back and the anvil in front of
it. The layout is deterministic from the building's identity, so a room you
have been in is the room you come back to.

Qt-free and grid-only, like the rest of the world generation.
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import pathlib

import numpy as np

from . import tiles as T

#: Where the authored rooms live.
ROOM_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "rooms"

#: What each character in a room file means. A map is **ASCII art**, for
#: exactly the reason the sprites are: it is the only form of level design that
#: survives code review. Nobody can see in a diff that a binary map changed,
#: let alone how; here, moving the bar in the tavern is one character on one
#: line, and the reviewer sees the room.
#:
#: The art is a *stand-in*, not the thing: every character is replaced by real
#: tile artwork when the room is drawn, so the file says where the bar is and
#: the atlas says what a bar looks like.
LEGEND: dict[str, int] = {
    "#": T.IWALL,
    ".": T.BOARDS,
    "+": T.EXIT,
    "@": T.BOARDS,      # ...and somewhere a person can stand
    "b": T.BED,
    "s": T.SHELF,
    "h": T.HEARTH,
    "T": T.TABLE,
    "r": T.RUG,
    "o": T.BARREL,
    "C": T.COUNTER,
    "a": T.ALTAR,
    "n": T.ANVIL,
}

#: The character that marks a standing spot, painted as ordinary floor.
SPOT = "@"

#: Room size per kind, in tiles, walls included. A house is generous by design:
#: the whole point of going indoors is that it is not cramped.
#: Every room fits inside one screen (see :mod:`.screens`), so going indoors
#: never scrolls: you open the door and the whole room is in front of you,
#: which is the convention and also the reason a room reads as a room.
SIZES: dict[str, tuple[int, int]] = {
    "house": (13, 10),
    "tavern": (16, 13),
    "shop": (15, 10),
    "smithy": (15, 11),
    "shrine": (13, 12),
    "hall": (16, 14),
}

#: What each room is called when you are standing in it.
TITLES: dict[str, str] = {
    "house": "{name}",
    "tavern": "The tavern at {place}",
    "shop": "The supply house",
    "smithy": "The lens-grinder",
    "shrine": "The shrine",
    "hall": "{name}",
}


@dataclasses.dataclass
class Interior:
    """One room, as a map in its own right.

    Attributes
    ----------
    key : str
        Stable identity, so the same building is the same room every visit.
    kind : str
        ``house``, ``tavern``, ``shop``, ``smithy``, ``shrine`` or ``hall``.
    title : str
        What the room is called.
    grid : numpy.ndarray
        ``(rows, cols)`` uint8 of tile kinds.
    door : tuple of int
        The cell you arrive on and leave by.
    spots : list of tuple
        Cells where somebody could reasonably be standing.
    """

    key: str
    kind: str
    title: str
    grid: np.ndarray
    door: tuple[int, int]
    spots: list[tuple[int, int]] = dataclasses.field(default_factory=list)

    @property
    def size(self) -> tuple[int, int]:
        """Room size in tiles.

        Returns
        -------
        tuple of int
            ``(width, height)``.
        """
        return (int(self.grid.shape[1]), int(self.grid.shape[0]))

    def tile_at(self, col: int, row: int) -> int:
        """The tile at a cell.

        Parameters
        ----------
        col, row : int
            Grid coordinates.

        Returns
        -------
        int
            The tile kind; outside the room reads as an inner wall, so a walker
            cannot leave except by the door.
        """
        rows, cols = self.grid.shape
        if not (0 <= row < rows and 0 <= col < cols):
            return T.IWALL
        return int(self.grid[row, col])


def _seed(text: str) -> int:
    """A stable integer from a string.

    Parameters
    ----------
    text : str
        Any identifier.

    Returns
    -------
    int
        The same value on every run and every machine.
    """
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


@functools.lru_cache(maxsize=16)
def _authored(kind: str):
    """Read a room's ASCII map, if one is shipped.

    Parameters
    ----------
    kind : str
        Room kind, which is the file stem.

    Returns
    -------
    tuple or None
        ``(grid, door, spots)``, or ``None`` when there is no file for it.
    """
    path = ROOM_DIR / f"{kind}.txt"
    if not path.is_file():
        return None
    # Lines beginning "# " are commentary; a line of bare "#" is a wall.
    lines = [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.lstrip().startswith("# ")
    ]
    if not lines:
        return None
    width = max(len(line) for line in lines)
    grid = np.full((len(lines), width), T.IWALL, dtype=np.uint8)
    door: tuple[int, int] | None = None
    spots: list[tuple[int, int]] = []
    for row, line in enumerate(lines):
        for col, char in enumerate(line):
            grid[row, col] = LEGEND.get(char, T.BOARDS)
            if char == "+":
                door = (col, row)
            elif char == SPOT:
                spots.append((col, row))
    if door is None:
        door = (width // 2, len(lines) - 1)
        grid[door[1], door[0]] = T.EXIT
    return grid, door, spots


def build(key: str, kind: str, title: str = "") -> Interior:
    """Furnish a room.

    The layout comes from the room's **ASCII map** under ``data/rooms`` where
    one is shipped, and from :func:`_furnish` where one is not -- so a new kind
    of room is a text file rather than a code change, and an existing one is
    rearranged by moving characters around.

    Parameters
    ----------
    key : str
        Stable identity -- a page address, or a settlement and premises name.
    kind : str
        One of :data:`SIZES`.
    title : str, optional
        What to call it.

    Returns
    -------
    Interior
        The room, ready to walk into.
    """
    kind = kind if kind in SIZES else "house"
    authored = _authored(kind)
    if authored is not None:
        grid, door, spots = authored
        return Interior(key=key, kind=kind, title=title or kind.title(),
                        grid=grid.copy(), door=door, spots=list(spots))

    width, height = SIZES[kind]
    grid = np.full((height, width), T.BOARDS, dtype=np.uint8)
    grid[0, :] = T.IWALL
    grid[-1, :] = T.IWALL
    grid[:, 0] = T.IWALL
    grid[:, -1] = T.IWALL

    door = (width // 2, height - 1)
    grid[door[1], door[0]] = T.EXIT

    seed = _seed(f"{kind}:{key}")
    spots = []
    _furnish(grid, kind, seed, spots)

    return Interior(key=key, kind=kind, title=title or kind.title(),
                    grid=grid, door=door, spots=spots)


def _furnish(grid: np.ndarray, kind: str, seed: int,
             spots: list[tuple[int, int]]) -> None:
    """Put the furniture in, according to what the room is for.

    Parameters
    ----------
    grid : numpy.ndarray
        The room, modified in place.
    kind : str
        Which room.
    seed : int
        Deterministic variation.
    spots : list
        Filled with cells somebody could stand in.
    """
    height, width = grid.shape
    middle = width // 2

    def put(col: int, row: int, tile: int) -> None:
        if 1 <= col < width - 1 and 1 <= row < height - 1:
            grid[row, col] = tile

    if kind == "house":
        put(2, 2, T.BED)
        put(3, 2, T.BED)
        put(width - 3, 2, T.SHELF)
        put(width - 4, 2, T.SHELF)
        put(middle, 2, T.HEARTH)
        put(middle - 1, height - 4, T.TABLE)
        put(middle + 1, height - 4, T.TABLE)
        for col in range(middle - 1, middle + 2):
            put(col, height - 3, T.RUG)
        spots += [(middle, 4), (width - 4, height - 4), (3, height - 4)]

    elif kind == "tavern":
        # A bar across the back with somebody behind it, and tables to sit at.
        for col in range(2, width - 2):
            put(col, 2, T.COUNTER)
        put(width - 3, 1, T.SHELF)
        put(width - 4, 1, T.SHELF)
        put(2, 1, T.BARREL)
        put(3, 1, T.BARREL)
        put(1, height - 3, T.HEARTH)
        for row in (5, 8):
            for col in (3, middle + 1):
                put(col, row, T.TABLE)
                put(col + 1, row, T.TABLE)
        spots += [(middle, 1), (4, 6), (middle + 2, 6), (4, 9), (middle + 2, 9)]

    elif kind == "shop":
        for col in range(3, width - 3):
            put(col, 3, T.COUNTER)
        for col in range(2, width - 2, 2):
            put(col, 1, T.SHELF)
        put(2, height - 3, T.BARREL)
        put(3, height - 3, T.BARREL)
        put(width - 3, height - 3, T.BARREL)
        spots += [(middle, 2), (middle, 5)]

    elif kind == "smithy":
        put(2, 1, T.HEARTH)
        put(3, 1, T.HEARTH)
        put(2, 2, T.HEARTH)
        put(3, 2, T.HEARTH)
        put(middle, 4, T.ANVIL)
        put(width - 3, 2, T.SHELF)
        put(width - 3, 3, T.SHELF)
        for col in range(2, 5):
            put(col, height - 3, T.BARREL)
        spots += [(middle, 5), (5, 2)]

    elif kind == "shrine":
        for col in range(middle - 1, middle + 2):
            put(col, 2, T.ALTAR)
        for row in range(4, height - 2):
            put(middle, row, T.RUG)
        for row in (4, 6, 8):
            put(2, row, T.SHELF)
            put(width - 3, row, T.SHELF)
        spots += [(middle - 2, 3), (middle, height - 4)]

    elif kind == "hall":
        for col in range(middle - 2, middle + 3):
            put(col, 2, T.ALTAR)
        for row in range(4, height - 2):
            put(middle, row, T.RUG)
        for row in (3, 5, 7):
            put(2, row, T.BARREL)
            put(width - 3, row, T.BARREL)
        put(3, height - 4, T.TABLE)
        put(4, height - 4, T.TABLE)
        put(width - 4, height - 4, T.TABLE)
        spots += [(middle, 4), (4, height - 5), (width - 5, height - 5)]

    # A little variation so two houses in a row are not the same room.
    if seed % 3 == 0:
        put(width - 3, height - 3, T.BARREL)
    if seed % 5 == 0:
        put(2, height - 4, T.SHELF)


def key_for(village, tile: int, col: int, row: int, room=None) -> str:
    """A stable identity for the building at a cell.

    Parameters
    ----------
    village : Village
        Which settlement it stands in.
    tile : int
        The overworld tile kind.
    col, row : int
        Where it stands.
    room : Room, optional
        The page it holds, when it is a page-house.

    Returns
    -------
    str
        Stable across runs, and unique per building.
    """
    if room is not None:
        return f"page:{room.address}"
    place = getattr(village, "place", "somewhere")
    return f"{place}:{T.NAMES.get(tile, tile)}:{col},{row}"


def title_for(kind: str, village, room=None) -> str:
    """What the room is called when you are standing in it.

    Parameters
    ----------
    kind : str
        Which room.
    village : Village
        Which settlement.
    room : Room, optional
        The page it holds.

    Returns
    -------
    str
        A display title.
    """
    place = getattr(village, "place", "")
    if room is not None:
        return room.title
    if kind == "hall":
        return f"The warden's hall at {place}"
    return TITLES.get(kind, "{name}").format(name=kind.title(), place=place)
