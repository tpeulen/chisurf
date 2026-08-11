"""The tile vocabulary the overworld is painted in.

A map made of floating markers is a diagram, not a place. The world is a real
grid: terrain you walk over, water and cliffs you cannot, roads that go
somewhere, and settlements that are enclosed compounds with a gate rather than a
scatter of dots on a rectangle.

The vocabulary is deliberately the one a 16-bit overworld has, because those
maps are legible at a glance and this one has to be: ground you walk, water you
do not, a shore between them, woodland, cliffs, a cave mouth in the cliffs, and
inside the walls a plaza, a well, a tavern, a shop, a smithy, a shrine, market
stalls, lantern posts and garden plots. Every one of them is somewhere a player
can be *going*, which is the difference between a map and a texture.

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

#: Terrain the world grew after the first pass. Sand rims every body of water,
#: marsh sits in the low ground, and a cliff is a mountain you walk around
#: until you find the cave in it.
SAND = 12
MARSH = 13
CLIFF = 14
CAVE = 15

#: Inside the walls. A settlement without a middle is a housing estate: the
#: plaza and the well are what make it a village.
PLAZA = 16
WELL = 17
TAVERN = 18
SHOP = 19
SMITHY = 20
SHRINE = 21
HALL = 22
GARDEN = 23
LANTERN = 24
SIGN = 25
FENCE = 26
FLOWERS = 27
STALL = 28
DOCK = 29

#: Indoors. A building is one tile on the overworld and a whole room when you
#: are inside it, which is the oldest trick the genre has: the exterior is a
#: doorway, not a floor plan.
BOARDS = 35
IWALL = 36
COUNTER = 37
TABLE = 38
BED = 39
SHELF = 40
HEARTH = 41
ALTAR = 42
RUG = 43
ANVIL = 44
BARREL = 45
#: The way out, at the bottom of every room.
EXIT = 46

#: The dark manifold. The same ground with the light taken out of it: ash where
#: the grass was, tar where the water was, dead wood, and ruins where people
#: lived. See :mod:`.darkworld`.
ASH = 30
TAR = 31
DEADTREE = 32
RUIN = 33
#: The way back up. A crossing is two-way, and a one-way trip into the dark
#: would be a bug rather than a design.
RIFT = 34

#: Tiles that stop a walker. A gate is a hole in a wall, so it is *not* here;
#: nor is a cave mouth, which is a door.
BLOCKING = frozenset({
    VOID, WATER, TREE, ROCK, WALL, BUILDING, CLIFF, WELL, TAVERN, SHOP,
    SMITHY, SHRINE, HALL, LANTERN, SIGN, FENCE, STALL, TAR, DEADTREE, RUIN,
    IWALL, COUNTER, TABLE, BED, SHELF, HEARTH, ALTAR, ANVIL, BARREL,
})

#: Tiles you can walk on that are, in some way, *somewhere*: standing on one
#: means something to the game rather than merely being legal.
DOORS = frozenset({GATE, CAVE, CLINIC, RIFT, EXIT})

#: Buildings you can talk to from outside. Each has an interior scene in
#: :mod:`.places` rather than an interior map -- a tavern the size of one room
#: is worse than a tavern you enter by talking to its door.
PREMISES = frozenset({TAVERN, SHOP, SMITHY, SHRINE, HALL})

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
    SAND: "sand",
    MARSH: "marsh",
    CLIFF: "cliff",
    CAVE: "cave",
    PLAZA: "plaza",
    WELL: "well",
    TAVERN: "tavern",
    SHOP: "shop",
    SMITHY: "smithy",
    SHRINE: "shrine",
    HALL: "hall",
    GARDEN: "garden",
    LANTERN: "lantern",
    SIGN: "sign",
    FENCE: "fence",
    FLOWERS: "flowers",
    STALL: "stall",
    DOCK: "dock",
    ASH: "ash",
    TAR: "tar",
    DEADTREE: "dead tree",
    RUIN: "ruin",
    RIFT: "rift",
    BOARDS: "boards",
    IWALL: "inner wall",
    COUNTER: "counter",
    TABLE: "table",
    BED: "bed",
    SHELF: "shelf",
    HEARTH: "hearth",
    ALTAR: "altar",
    RUG: "rug",
    ANVIL: "anvil",
    BARREL: "barrel",
    EXIT: "way out",
}

#: Which overworld tiles are a building you can walk into, and what kind of
#: room is behind each.
ENTERABLE: dict[int, str] = {
    BUILDING: "house",
    TAVERN: "tavern",
    SHOP: "shop",
    SMITHY: "smithy",
    SHRINE: "shrine",
    HALL: "hall",
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


def is_premises(tile: int) -> bool:
    """Whether a tile is a building you can do business with.

    Parameters
    ----------
    tile : int
        A tile kind.

    Returns
    -------
    bool
        True for the tavern, shop, smithy, shrine and hall.
    """
    return tile in PREMISES
