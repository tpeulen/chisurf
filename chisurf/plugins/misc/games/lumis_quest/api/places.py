"""Settlements: how a village is laid out, and what is in it.

The compounds used to be a wall around a grid of identical boxes, which is a
housing estate rather than a village. A 16-bit town is legible because it has a
*middle* and things arranged around it: you walk in the gate, up the street,
past the stalls, into the square with the well, and the tavern is on the corner
because taverns are always on the corner.

So a settlement is planned in **cells** rather than painted row by row. Every
cell is one building plot; the square takes a block of them in the middle, the
premises take the cells that face the square, the pages take what is left
working outward, and gardens fill the back. The wall goes round whatever that
came to.

Three sizes, because a corpus has three sizes of section and pretending
otherwise is what made every village look the same:

* a **hamlet** (up to three pages) has no wall at all -- a fence, a well, and
  the feeling of being outside;
* a **village** has a wall, a gate, a square, a tavern and a shop;
* a **town** has all of that, a market row along the main street, a smithy and
  a shrine, and room for a Warden's hall.

Qt-free and grid-only: this module knows nothing about how any of it is drawn.
"""

from __future__ import annotations

import dataclasses

from .tiles import (
    BUILDING,
    CLINIC,
    FENCE,
    FLOOR,
    FLOWERS,
    GARDEN,
    GATE,
    GRASS,
    HALL,
    LANTERN,
    PLAZA,
    SHOP,
    SHRINE,
    SIGN,
    SERVICE_SMITHYY,
    STALL,
    TAVERN,
    WALL,
    WELL,
)

#: Tiles from one building plot to the next. At 2 the buildings sat on every
#: other tile -- a grid of doors with a one-tile alley between them. At 3 the
#: streets were two tiles, which is wide enough to walk down and narrow enough
#: that every lantern post and market stall in one is something to catch on.
#: At 4 a street is three tiles: room to pass a stall, and room for the people
#: who live there to walk past each other.
PITCH = 4

#: Open ground kept between the wall and the outermost plot, so a compound has
#: a perimeter street rather than houses jammed against the wall.
MARGIN = 3

#: Page counts at which a settlement changes kind. A town is the interesting
#: one and the corpus has plenty of sections that deserve to be one, so the
#: threshold is low.
HAMLET_MAX = 2
VILLAGE_MAX = 6

#: Which premises each kind of settlement has, in the order they claim the
#: cells facing the square.
PREMISES_FOR: dict[str, tuple[int, ...]] = {
    "hamlet": (WELL,),
    "village": (TAVERN, SHOP),
    "town": (TAVERN, SHOP, SERVICE_SMITHYY, SHRINE),
}

#: Landmark key for each premises tile, and the words the world uses for it.
PREMISES_KEY: dict[int, str] = {
    TAVERN: "tavern",
    SHOP: "shop",
    SERVICE_SMITHYY: "smithy",
    SHRINE: "shrine",
    HALL: "hall",
}
PREMISES_NAME: dict[int, str] = {
    TAVERN: "the tavern",
    SHOP: "the supply house",
    SERVICE_SMITHYY: "the lens-grinder",
    SHRINE: "the shrine",
    HALL: "the warden's hall",
}


@dataclasses.dataclass
class Plan:
    """Where everything in a settlement goes, before anything is painted.

    Attributes
    ----------
    kind : str
        ``hamlet``, ``village`` or ``town``.
    width, height : int
        Compound size in tiles, wall included.
    cells : list of tuple
        ``(col, row)`` plot coordinates, in tiles, relative to the compound.
    plaza : tuple of int
        ``(col, row, width, height)`` of the square, relative.
    room_cells : list of tuple
        Plots the pages take, in the order the pages are given.
    premises : dict
        Tile kind to relative ``(col, row)``.
    gardens : list of tuple
        Relative ``(col, row)`` of garden plots.
    gate : tuple of int
        Relative ``(col, row)`` of the gate in the south wall.
    """

    kind: str
    width: int
    height: int
    cells: list[tuple[int, int]] = dataclasses.field(default_factory=list)
    plaza: tuple[int, int, int, int] = (0, 0, 0, 0)
    room_cells: list[tuple[int, int]] = dataclasses.field(default_factory=list)
    premises: dict[int, tuple[int, int]] = dataclasses.field(default_factory=dict)
    gardens: list[tuple[int, int]] = dataclasses.field(default_factory=list)
    gate: tuple[int, int] = (0, 0)


def kind_for(room_count: int, boss_seat: bool = False) -> str:
    """How big a settlement this many pages makes.

    Parameters
    ----------
    room_count : int
        Pages in the section.
    boss_seat : bool, optional
        Whether a Warden holds their hall here. A Warden's seat is never a
        hamlet: somebody has to have built the hall.

    Returns
    -------
    str
        ``hamlet``, ``village`` or ``town``.
    """
    if boss_seat:
        return "town"
    if room_count <= HAMLET_MAX:
        return "hamlet"
    if room_count <= VILLAGE_MAX:
        return "village"
    return "town"


def plan(room_count: int, kind: str, boss_seat: bool = False) -> Plan:
    """Lay a settlement out in plots.

    Parameters
    ----------
    room_count : int
        How many pages need a building.
    kind : str
        From :func:`kind_for`.
    boss_seat : bool, optional
        Reserve a plot for the Warden's hall.

    Returns
    -------
    Plan
        Everything placed, in compound-relative tiles.
    """
    premises = list(PREMISES_FOR.get(kind, ()))
    if boss_seat:
        premises.insert(0, HALL)
    # A hamlet's well is placed at the square's centre rather than on a plot.
    plot_premises = [tile for tile in premises if tile != WELL]

    # Plots needed: the pages, the premises, the 2x2 square, and a back row of
    # gardens. Squaring that up gives a compound that reads as deliberate.
    gardens = 2 if kind != "hamlet" else 1
    needed = room_count + len(plot_premises) + 4 + gardens
    # Wider than square. A town you can see across in one screen is a
    # courtyard; laying the plots out broad rather than deep gives a main
    # street with length to it.
    columns = max(4, min(9, int((needed * 1.4) ** 0.5 + 0.999)))
    rows = max(3, -(-needed // columns))

    width = (columns - 1) * PITCH + 2 * (1 + MARGIN) + 1
    height = (rows - 1) * PITCH + 2 * (1 + MARGIN) + 1
    layout = Plan(kind=kind, width=width, height=height)

    def cell(index_x: int, index_y: int) -> tuple[int, int]:
        return (1 + MARGIN + index_x * PITCH, 1 + MARGIN + index_y * PITCH)

    layout.cells = [cell(x, y) for y in range(rows) for x in range(columns)]

    # The square sits in the middle of the compound, one plot up from centre so
    # the walk in from the gate is a street rather than a doorstep.
    square_x = max(0, (columns - 2) // 2)
    square_y = max(0, (rows - 2) // 2)
    square_cells = {(square_x + dx, square_y + dy) for dx in (0, 1) for dy in (0, 1)
                    if square_x + dx < columns and square_y + dy < rows}
    left, top = cell(square_x, square_y)
    right, bottom = cell(min(square_x + 1, columns - 1), min(square_y + 1, rows - 1))
    layout.plaza = (left - 1, top - 1, right - left + 3, bottom - top + 3)

    # Premises claim the plots that face the square, so the tavern is on the
    # corner of the square the way it is in every town anyone has walked
    # through. Then the pages fill outward from there.
    facing: list[tuple[int, int]] = []
    others: list[tuple[int, int]] = []
    for y in range(rows):
        for x in range(columns):
            if (x, y) in square_cells:
                continue
            touches = any((x + dx, y + dy) in square_cells
                          for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                                         (1, 1), (1, -1), (-1, 1), (-1, -1)))
            (facing if touches else others).append((x, y))

    # Outward from the square: the pages nearest the middle are the ones a
    # reader is most likely to want.
    centre = (square_x + 0.5, square_y + 0.5)
    others.sort(key=lambda spot: (spot[0] - centre[0]) ** 2 + (spot[1] - centre[1]) ** 2)

    for tile_kind in plot_premises:
        if facing:
            layout.premises[tile_kind] = cell(*facing.pop(0))
        elif others:
            layout.premises[tile_kind] = cell(*others.pop(0))

    remaining = facing + others
    layout.room_cells = [cell(*spot) for spot in remaining[:room_count]]
    layout.gardens = [cell(*spot) for spot in remaining[room_count:room_count + gardens]]

    layout.gate = (width // 2, height - 1)
    return layout


def paint(grid: list[list[int]], origin: tuple[int, int], layout: Plan,
          seed: int, boss_seat: bool = False) -> dict[str, tuple[int, int]]:
    """Paint a planned settlement onto the world grid.

    Parameters
    ----------
    grid : list of list of int
        The tile grid, modified in place.
    origin : tuple of int
        Where the compound's top-left corner sits in world tiles.
    layout : Plan
        From :func:`plan`.
    seed : int
        Deterministic decoration.
    boss_seat : bool, optional
        Whether this settlement has a Warden's hall.

    Returns
    -------
    dict
        Named landmarks in world tiles: ``gate``, ``clinic``, ``well``, and one
        entry per premises (``tavern``, ``shop``, ``smithy``, ``shrine``,
        ``hall``).
    """
    col, row = origin
    height_g, width_g = len(grid), len(grid[0]) if grid else 0

    def put(x: int, y: int, tile: int) -> None:
        if 0 <= row + y < height_g and 0 <= col + x < width_g:
            grid[row + y][col + x] = tile

    def get(x: int, y: int) -> int:
        if 0 <= row + y < height_g and 0 <= col + x < width_g:
            return grid[row + y][col + x]
        return 0

    walled = layout.kind != "hamlet"
    for y in range(layout.height):
        for x in range(layout.width):
            edge = x in (0, layout.width - 1) or y in (0, layout.height - 1)
            if edge:
                # A hamlet is fenced, not walled. You can see out of it, and
                # that changes how it feels to stand in one.
                put(x, y, WALL if walled else FENCE)
            else:
                put(x, y, FLOOR if walled else GRASS)

    landmarks: dict[str, tuple[int, int]] = {}

    # The square, and the well in the middle of it.
    px, py, pw, ph = layout.plaza
    for y in range(py, py + ph):
        for x in range(px, px + pw):
            put(x, y, PLAZA)
    well = (px + pw // 2, py + ph // 2)
    put(*well, WELL)
    landmarks["well"] = (col + well[0], row + well[1])

    # The main street: gate to square, paved, so there is one obvious way in.
    gate_x, gate_y = layout.gate
    street_x = min(max(gate_x, px + 1), px + pw - 2)
    for y in range(py + ph, gate_y):
        put(gate_x, y, PLAZA)
        put(gate_x - 1 if gate_x > 1 else gate_x + 1, y, PLAZA)
    for x in range(min(gate_x, street_x), max(gate_x, street_x) + 1):
        put(x, py + ph, PLAZA)

    if walled:
        put(gate_x, gate_y, GATE)
        # The recovery station is just inside the gate, where somebody limping
        # home finds it first.
        clinic = (gate_x + 1, gate_y - 1)
        if get(*clinic) in (FLOOR, PLAZA):
            put(*clinic, CLINIC)
        else:
            clinic = (gate_x, gate_y - 1)
            put(*clinic, CLINIC)
        landmarks["clinic"] = (col + clinic[0], row + clinic[1])
        put(gate_x - 1, gate_y - 1, SIGN)
    else:
        # A fenced hamlet still needs a way in and somewhere to recover.
        put(gate_x, gate_y, GRASS)
        clinic = (gate_x + 1, gate_y - 2)
        put(*clinic, CLINIC)
        landmarks["clinic"] = (col + clinic[0], row + clinic[1])
    landmarks["gate"] = (col + gate_x, row + gate_y)

    for tile_kind, (x, y) in layout.premises.items():
        put(x, y, tile_kind)
        landmarks[PREMISES_KEY.get(tile_kind, "premises")] = (col + x, row + y)
        # A lit doorstep: a building you can enter should look like one.
        put(x, y + 1, PLAZA)

    for x, y in layout.gardens:
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                if get(x + dx, y + dy) in (FLOOR, GRASS):
                    put(x + dx, y + dy, GARDEN)

    # Market stalls line the street of a town, which is what makes it a street
    # rather than a corridor.
    if layout.kind == "town":
        for index, y in enumerate(range(py + ph + 1, gate_y - 1, 2)):
            side = gate_x + (2 if index % 2 else -2)
            if get(side, y) == FLOOR:
                put(side, y, STALL)

    # Lanterns at the square's corners and down the street. A town at dusk is
    # lit by somebody's decision to light it, and this world is about exactly
    # that.
    for corner in ((px, py), (px + pw - 1, py), (px, py + ph - 1), (px + pw - 1, py + ph - 1)):
        if get(*corner) == PLAZA:
            put(*corner, LANTERN)
    for y in range(py + ph + 2, gate_y, 4):
        for x in (gate_x - 2, gate_x + 2):
            if get(x, y) == FLOOR:
                put(x, y, LANTERN)

    # A few flowers where nothing else claimed the ground.
    for index in range(12):
        x = 1 + (seed >> (index % 8)) % max(1, layout.width - 2)
        y = 1 + (seed >> ((index + 3) % 9)) % max(1, layout.height - 2)
        if get(x, y) in (FLOOR, GRASS):
            put(x, y, FLOWERS)

    return landmarks


def paint_rooms(grid: list[list[int]], origin: tuple[int, int],
                cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Put the page-buildings on their plots.

    Parameters
    ----------
    grid : list of list of int
        The tile grid, modified in place.
    origin : tuple of int
        Compound origin in world tiles.
    cells : list of tuple
        Relative plot coordinates, from :attr:`Plan.room_cells`.

    Returns
    -------
    list of tuple
        The same plots in world tiles, in the same order.
    """
    col, row = origin
    placed: list[tuple[int, int]] = []
    for x, y in cells:
        if 0 <= row + y < len(grid) and 0 <= col + x < len(grid[0]):
            grid[row + y][col + x] = BUILDING
        placed.append((col + x, row + y))
    return placed
