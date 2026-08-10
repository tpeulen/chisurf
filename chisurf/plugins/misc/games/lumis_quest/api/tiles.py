"""The tile vocabulary the overworld is painted in.

A map made of floating markers is a diagram, not a place. The world is a real
grid: terrain you walk over, water and cliffs you cannot, roads that go
somewhere, and villages that are enclosed compounds with a gate rather than a
scatter of dots on a rectangle.

Kept separate from :mod:`.world` so the renderer can import the vocabulary
without importing the generator.
"""

from __future__ import annotations

#: Tile kinds. Values are stable because they are written into the grid.
VOID = 0
WATER = 1
GRASS = 2
TREE = 3
ROCK = 4
ROAD = 5
FLOOR = 6
WALL = 7
GATE = 8
BUILDING = 9
BRIDGE = 10
CLINIC = 11

#: Tiles that stop a walker. A gate is a hole in a wall, so it is *not* here.
BLOCKING = frozenset({VOID, WATER, TREE, ROCK, WALL, BUILDING})

#: Human-readable names, for debugging and test failure messages.
NAMES = {
    VOID: "void",
    WATER: "water",
    GRASS: "grass",
    TREE: "tree",
    ROCK: "rock",
    ROAD: "road",
    FLOOR: "floor",
    WALL: "wall",
    GATE: "gate",
    BUILDING: "building",
    BRIDGE: "bridge",
    CLINIC: "clinic",
}

#: World units per tile.
TILE = 18.0


def is_blocking(tile: int) -> bool:
    """Whether a tile stops movement.

    Parameters
    ----------
    tile : int
        A tile kind.

    Returns
    -------
    bool
        True when a walker cannot enter.
    """
    return tile in BLOCKING
