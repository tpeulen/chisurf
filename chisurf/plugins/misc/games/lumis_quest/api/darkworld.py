"""The dark manifold: the same world with the light taken out of it.

Every game of this shape has a second map under the first one, and this one has
a reason to. A fluorophore that is pushed too hard does not simply stop -- it
**crosses**, into a state where it still exists and no longer shines. That is
the triplet manifold, it is where a bleaching dye actually goes, and it is the
best second world anybody has been handed for free.

So the dark manifold is not a separate map to author. It is *this* map,
transformed: ash where the grass was, tar where the water was, dead wood, and
ruins where people built. You go down through a **cave mouth** and come back up
through a **rift**, and the geography is the same, which is the whole trick --
you already know the way, and none of it is where you left it.

What lives there was ours. A label driven all the way down does not die; it
shelves. The things you meet are those, and they are the reason the story has
somewhere to end.

Qt-free, and the transform is a lookup table so crossing over is instant.
"""

from __future__ import annotations

import numpy as np

from . import tiles as T

#: Lit tile -> its shadow. Anything not named here crosses unchanged, which is
#: deliberate: walls, roads and paving are the bones of the place and the point
#: is that the bones are still there.
SHADOW: dict[int, int] = {
    T.GRASS: T.ASH,
    T.FLOWERS: T.ASH,
    T.SAND: T.ASH,
    T.MARSH: T.TAR,
    T.WATER: T.TAR,
    T.TREE: T.DEADTREE,
    T.BUILDING: T.RUIN,
    T.TAVERN: T.RUIN,
    T.SHOP: T.RUIN,
    T.SMITHY: T.RUIN,
    T.SHRINE: T.RUIN,
    T.HALL: T.RUIN,
    T.STALL: T.RUIN,
    T.WELL: T.RUIN,
    T.FENCE: T.RUIN,
    T.LANTERN: T.RUIN,
    T.GARDEN: T.ASH,
    # No recovery station down here. Somewhere that heals you is a promise
    # somebody keeps, and nobody is keeping anything in the dark.
    T.CLINIC: T.FLOOR,
    # The way back up. A one-way trip into the dark would be a bug, not a
    # design.
    T.CAVE: T.RIFT,
}

#: How far the Lanternwright's tower reaches, in tiles. It is the only thing in
#: the dark manifold that was *built* rather than left, and it should read that
#: way from a long way off.
TOWER_RADIUS = 6


def shadow(array: np.ndarray) -> np.ndarray:
    """Cast a lit grid into its dark counterpart.

    Parameters
    ----------
    array : numpy.ndarray
        The lit world, ``(rows, cols)`` uint8.

    Returns
    -------
    numpy.ndarray
        The same shape. Empty in, empty out.
    """
    if not array.size:
        return np.zeros((0, 0), np.uint8)
    table = np.arange(256, dtype=np.uint8)
    for lit, dark in SHADOW.items():
        table[lit] = dark
    return table[array]


def raise_tower(world) -> tuple[int, int] | None:
    """Build the Lanternwright's tower into the dark manifold.

    It goes in the last land, because that is the far end of the ladder, and it
    is walled with one way in so that arriving at it feels like arriving
    somewhere rather than walking past.

    Parameters
    ----------
    world : chisurf.plugins.misc.games.lumis_quest.api.world.World
        The world, whose ``dark`` grid is modified in place.

    Returns
    -------
    tuple of int or None
        Grid cell of the tower door, or ``None`` for a world with no lands.
    """
    if not world.regions or not world.dark.size:
        return None
    region = world.regions[-1]
    col, row, width, height = region.rect
    cx = col + width // 2
    cy = row + height // 2
    rows, cols = world.dark.shape

    for y in range(cy - TOWER_RADIUS, cy + TOWER_RADIUS + 1):
        for x in range(cx - TOWER_RADIUS, cx + TOWER_RADIUS + 1):
            if not (0 <= y < rows and 0 <= x < cols):
                continue
            edge = (abs(y - cy) == TOWER_RADIUS or abs(x - cx) == TOWER_RADIUS)
            world.dark[y, x] = T.WALL if edge else T.FLOOR

    door = (cx, min(cy + TOWER_RADIUS, rows - 1))
    if 0 <= door[1] < rows and 0 <= door[0] < cols:
        world.dark[door[1], door[0]] = T.GATE
    # The lantern itself, at the middle: the thing every marked animal in the
    # world is, in the end, wired to.
    if 0 <= cy < rows and 0 <= cx < cols:
        world.dark[cy, cx] = T.HALL
    return door


#: What the shelved say. They are not monsters; they are labels that were
#: driven all the way down, and one of the few things the game asks a player to
#: feel is that this is somebody's fault.
WRAITH_LINES: tuple[str, ...] = (
    "It is shaped like something that used to shine.",
    "It does not attack. It waits to see whether you are carrying light.",
    "A shape with a hare's outline and nothing inside it.",
    "You have seen this one before, in a field, in colour.",
)

#: A line the world says when you first come down. Said once.
ARRIVAL: tuple[str, ...] = (
    "The same country, with the light taken out of it.",
    "Ash where the grass was. Tar where the water was. Your own road, "
    "under your feet, going the same way it always did.",
    "Everything that was ever driven all the way down is here. It has been "
    "getting crowded.",
)
