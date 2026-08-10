"""The overworld: a real tile map, generated from the documentation.

The map is not authored, and it is not a scatter of markers either. It is a grid
that gets *painted*: grass and woodland, water you cannot cross without a bridge,
roads that run between places, and villages that are walled compounds with a gate
rather than dots on a rectangle. A walker collides with it.

Its shape comes from the documentation:

* a **region** is a top-level documentation directory, named as a place rather
  than a folder (see :mod:`.names`);
* a **village** is a toctree group -- a walled compound whose buildings are its
  pages;
* a **room** is a page, and it is a building you stand in front of.

Three rules hold the generation together:

* **Layout is seeded by a page's path**, so a page keeps its place as the corpus
  churns and adding one is a new building rather than a reshuffle. Nothing is
  random at run time.
* **Fog is review state, and the three states stay three things.** Untouched,
  AI-scouted, human-settled. The middle one is the frontier the game exists to
  work and must not be collapsed into either neighbour.
* **Remoteness is review debt**, weighted above depth, so the reward gradient
  points where the corpus actually needs attention.

Qt-free and engine-free: this is the model the view draws, which is what makes
the map testable without a window.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import pathlib

import numpy as np

from chisurf.plugins.core.help.api import review, toc

from .names import region_name
from .tiles import (
    BRIDGE,
    BUILDING,
    FLOOR,
    GATE,
    GRASS,
    ROAD,
    ROCK,
    TILE,
    TREE,
    VOID,
    WALL,
    WATER,
    is_blocking,
)

#: Room states, in increasing order of settledness.
WILD = "wild"
SCOUTED = "scouted"
SETTLED = "settled"

#: Buildings per row inside a village compound before it wraps.
VILLAGE_COLUMNS = 5

#: Villages per row inside a region before it wraps.
REGION_COLUMNS = 3

#: Open ground between compounds and between lands, in tiles. These are large
#: on purpose: a world you cross in four strides is a menu with scenery, and
#: the wilderness between villages is where exploration happens at all.
VILLAGE_GAP = 15
REGION_GAP = 30

#: Thickness of the water separating one land from the next.
MOAT = 7


def _tile_noise(salt: int, x: int, y: int) -> int:
    """Cheap, stable per-tile noise in 0..99.

    Terrain is scattered per tile, and there are tens of thousands of tiles:
    a cryptographic hash each is most of the world-build time for no benefit,
    since nothing here needs to be unguessable -- only *repeatable*. This is an
    integer mix, so it is identical on every run and every machine.

    Parameters
    ----------
    salt : int
        Per-region seed, so two lands do not share a forest.
    x, y : int
        Grid coordinates.

    Returns
    -------
    int
        A value in 0..99.
    """
    value = (salt ^ (x * 73856093) ^ (y * 19349663)) & 0xFFFFFFFF
    value ^= value >> 13
    value = (value * 1274126177) & 0xFFFFFFFF
    value ^= value >> 16
    return value % 100


def _seed(text: str) -> int:
    """A stable integer derived from a string.

    ``hash()`` is salted per process, so it cannot be used: the world would be
    laid out differently every time the game started.

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


@dataclasses.dataclass
class Room:
    """One documentation page, as a building on the grid.

    Attributes
    ----------
    title : str
        The page's own title.
    path : pathlib.Path
        Absolute path to the source file.
    address : str
        Repository-relative address, e.g. ``docs/guides/11_burst.md``.
    depth : int
        How deep the page sits in the toctree.
    state : str
        One of :data:`WILD`, :data:`SCOUTED`, :data:`SETTLED`.
    tile : tuple of int
        Grid cell the building occupies, as ``(col, row)``.
    """

    title: str
    path: pathlib.Path
    address: str
    depth: int
    state: str
    tile: tuple[int, int] = (0, 0)

    @property
    def position(self) -> tuple[float, float]:
        """Centre of the building in world units.

        Returns
        -------
        tuple of float
            World coordinates.
        """
        return ((self.tile[0] + 0.5) * TILE, (self.tile[1] + 0.5) * TILE)

    @property
    def remoteness(self) -> float:
        """How far off the beaten path this room is, in 0..1.

        Review debt counts for more than depth, because the point of the
        gradient is to send a player toward pages nobody has looked at rather
        than toward pages that merely sit deep in a well-tended section.

        Returns
        -------
        float
            Higher means more rewarding to reach.
        """
        debt = {WILD: 1.0, SCOUTED: 0.5, SETTLED: 0.0}[self.state]
        return 0.65 * debt + 0.35 * (min(self.depth, 5) / 5.0)


@dataclasses.dataclass
class Village:
    """A toctree group: a walled compound whose buildings are its pages.

    Attributes
    ----------
    name : str
        The group's own title.
    rooms : list of Room
        Its pages.
    rect : tuple of int
        ``(col, row, width, height)`` of the compound, walls included.
    gate : tuple of int
        Grid cell of the gate in the wall.
    """

    name: str
    rooms: list[Room] = dataclasses.field(default_factory=list)
    rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    gate: tuple[int, int] = (0, 0)

    @property
    def position(self) -> tuple[float, float]:
        """Centre of the compound in world units.

        Returns
        -------
        tuple of float
            World coordinates.
        """
        col, row, width, height = self.rect
        return ((col + width / 2) * TILE, (row + height / 2) * TILE)

    @property
    def prosperity(self) -> float:
        """Fraction of this village's rooms that are settled.

        Returns
        -------
        float
            0 for a ghost town, 1 for a fully reviewed section.
        """
        if not self.rooms:
            return 0.0
        return sum(room.state == SETTLED for room in self.rooms) / len(self.rooms)


@dataclasses.dataclass
class Region:
    """A top-level documentation directory, as a named land.

    Attributes
    ----------
    name : str
        Directory name, e.g. ``guides``.
    title : str
        The land's name, e.g. ``The Pilgrim Road``.
    subtitle : str
        A line describing it.
    villages : list of Village
        Its compounds.
    rect : tuple of int
        ``(col, row, width, height)`` of the land, in tiles.
    """

    name: str
    title: str
    subtitle: str = ""
    villages: list[Village] = dataclasses.field(default_factory=list)
    rect: tuple[int, int, int, int] = (0, 0, 0, 0)

    @property
    def position(self) -> tuple[float, float]:
        """Centre of the land in world units.

        Returns
        -------
        tuple of float
            World coordinates.
        """
        col, row, width, height = self.rect
        return ((col + width / 2) * TILE, (row + height / 2) * TILE)

    @property
    def rooms(self) -> list[Room]:
        """Every room in the land.

        Returns
        -------
        list of Room
            Flattened across villages.
        """
        return [room for village in self.villages for room in village.rooms]


@dataclasses.dataclass
class World:
    """The generated overworld, as a painted grid.

    Attributes
    ----------
    regions : list of Region
        One per top-level documentation directory.
    grid : list of list of int
        ``grid[row][col]`` tile kinds. Empty for an empty world.
    """

    regions: list[Region] = dataclasses.field(default_factory=list)
    grid: list[list[int]] = dataclasses.field(default_factory=list)
    #: The same grid as a 2-D uint8 array. The renderer slices the visible
    #: window out of this every frame; doing that over lists of ints is most of
    #: a frame's budget once the world is tens of thousands of tiles.
    array: np.ndarray = dataclasses.field(default_factory=lambda: np.zeros((0, 0), np.uint8))

    @property
    def height(self) -> int:
        """Grid height in tiles.

        Returns
        -------
        int
            Number of rows.
        """
        return len(self.grid)

    @property
    def width(self) -> int:
        """Grid width in tiles.

        Returns
        -------
        int
            Number of columns.
        """
        return len(self.grid[0]) if self.grid else 0

    @property
    def rooms(self) -> list[Room]:
        """Every room in the world.

        Returns
        -------
        list of Room
            Flattened across regions and villages.
        """
        return [room for region in self.regions for room in region.rooms]

    @property
    def villages(self) -> list[Village]:
        """Every village in the world.

        Returns
        -------
        list of Village
            Flattened across regions.
        """
        return [village for region in self.regions for village in region.villages]

    def tile_at(self, col: int, row: int) -> int:
        """The tile at a grid cell.

        Parameters
        ----------
        col, row : int
            Grid coordinates.

        Returns
        -------
        int
            The tile kind. Outside the grid reads as :data:`VOID`, so a walker
            cannot leave the world by walking off the edge.
        """
        if row < 0 or row >= self.height or col < 0 or col >= self.width:
            return VOID
        return self.grid[row][col]

    def blocked(self, x: float, y: float) -> bool:
        """Whether a world position is inside something solid.

        Parameters
        ----------
        x, y : float
            World coordinates.

        Returns
        -------
        bool
            True when a walker cannot stand there.
        """
        return is_blocking(self.tile_at(int(x // TILE), int(y // TILE)))

    def bounds(self) -> tuple[float, float, float, float]:
        """Extent of the whole grid in world units.

        Returns
        -------
        tuple of float
            ``(min_x, min_y, max_x, max_y)``.
        """
        return (0.0, 0.0, self.width * TILE, self.height * TILE)

    def counts(self) -> dict[str, int]:
        """How many rooms are in each state.

        Returns
        -------
        dict
            Keys :data:`WILD`, :data:`SCOUTED`, :data:`SETTLED`.
        """
        tally = {WILD: 0, SCOUTED: 0, SETTLED: 0}
        for room in self.rooms:
            tally[room.state] += 1
        return tally

    def region_at(self, x: float, y: float) -> Region | None:
        """The land containing a world position.

        Parameters
        ----------
        x, y : float
            World coordinates.

        Returns
        -------
        Region or None
            ``None`` when standing on open water between lands.
        """
        col, row = int(x // TILE), int(y // TILE)
        for region in self.regions:
            rcol, rrow, width, height = region.rect
            if rcol <= col < rcol + width and rrow <= row < rrow + height:
                return region
        return None

    def nearest_room(self, position: tuple[float, float]) -> Room | None:
        """The room closest to a point.

        Parameters
        ----------
        position : tuple of float
            World coordinates.

        Returns
        -------
        Room or None
            ``None`` for an empty world.
        """
        best: Room | None = None
        best_distance = float("inf")
        for room in self.rooms:
            here = room.position
            dx = here[0] - position[0]
            dy = here[1] - position[1]
            distance = dx * dx + dy * dy
            if distance < best_distance:
                best_distance = distance
                best = room
        return best

    def spawn(self) -> tuple[float, float]:
        """A walkable place to start: just outside the first village's gate.

        Returns
        -------
        tuple of float
            World coordinates.
        """
        for region in self.regions:
            for village in region.villages:
                col, row = village.gate
                return ((col + 0.5) * TILE, (row + 1.5) * TILE)
        return (TILE * 1.5, TILE * 1.5)


def _state_for(path: pathlib.Path) -> str:
    """Map a page's review status onto a world state.

    Parameters
    ----------
    path : pathlib.Path
        The page.

    Returns
    -------
    str
        One of :data:`WILD`, :data:`SCOUTED`, :data:`SETTLED`.
    """
    try:
        status = review.status_of(path).status
    except Exception:
        # An untracked directory has no sidecar at all, which is not an error:
        # it is the most common state in the corpus and means "never touched".
        return WILD
    if status == review.STATUS_REVIEWED:
        return SETTLED
    if status == review.STATUS_AI_REVIEWED:
        return SCOUTED
    # STATUS_STALE is deliberately wild again: the page moved under a sign-off,
    # so whatever was approved is no longer what is there.
    return WILD


def _collect(node: toc.Node, depth: int = 0) -> list[tuple[toc.Node, int]]:
    """Flatten a toctree node into its pages, keeping depth.

    Parameters
    ----------
    node : chisurf.plugins.core.help.api.toc.Node
        Root to walk.
    depth : int, optional
        Depth of ``node`` itself.

    Returns
    -------
    list of tuple
        ``(node, depth)`` for every node that has a document.
    """
    found = []
    if node.path is not None:
        found.append((node, depth))
    for child in node.children:
        found.extend(_collect(child, depth + 1))
    return found


def _village_size(room_count: int) -> tuple[int, int]:
    """Compound size in tiles for a given number of buildings.

    Buildings sit on every other interior tile so there is always a lane to walk
    between them; the compound adds a wall ring around that.

    Parameters
    ----------
    room_count : int
        Number of buildings.

    Returns
    -------
    tuple of int
        ``(width, height)`` in tiles, wall included.
    """
    columns = min(max(room_count, 1), VILLAGE_COLUMNS)
    rows = max(1, math.ceil(room_count / VILLAGE_COLUMNS))
    return (columns * 2 + 3, rows * 2 + 3)


def _address(path: pathlib.Path, repo_root: pathlib.Path) -> str:
    """Repository-relative address of a page.

    Parameters
    ----------
    path : pathlib.Path
        The page.
    repo_root : pathlib.Path
        Directory holding ``docs/``.

    Returns
    -------
    str
        A POSIX-style relative address, or the absolute path when the page lies
        outside the repository.
    """
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _read_groups(directory: pathlib.Path) -> list[tuple[str, list[tuple[toc.Node, int]]]]:
    """Read a directory's toctree into named groups of pages.

    Parameters
    ----------
    directory : pathlib.Path
        A top-level documentation directory.

    Returns
    -------
    list of tuple
        ``(group title, [(node, depth), ...])`` in the author's order, with any
        unlinked pages appended as their own group.
    """
    groups: list[tuple[str, list[tuple[toc.Node, int]]]] = []
    index_file = next(
        (directory / f"index{suffix}" for suffix in (".md", ".rst")
         if (directory / f"index{suffix}").is_file()),
        None,
    )
    if index_file is not None:
        for node in toc.read_index(index_file):
            pages = _collect(node)
            if pages:
                groups.append((node.title, pages))

    linked = {
        node.path.resolve()
        for _, pages in groups
        for node, _ in pages
        if node.path is not None
    }
    # Pages the toctree never mentions. Nobody arrives at them by reading, so
    # leaving them off would make them the one thing the map can never send a
    # player to -- exactly the pages most in need of a visit.
    orphans = [
        path
        for path in sorted(directory.rglob("*"))
        if path.suffix in {".md", ".rst"}
        and path.resolve() not in linked
        and not path.name.startswith("index.")
    ]
    if orphans:
        groups.append(
            (
                "The Unlinked",
                [
                    (toc.Node(title=path.stem.replace("_", " ").title(), path=path), 4)
                    for path in orphans
                ],
            )
        )
    return groups


def build_world(docs_root: pathlib.Path | None = None) -> World:
    """Generate the overworld from the documentation tree.

    Parameters
    ----------
    docs_root : pathlib.Path, optional
        Documentation root. Defaults to the one the help browser reads, so the
        game and the help window always describe the same corpus.

    Returns
    -------
    World
        Regions, villages, rooms, and the painted tile grid.
    """
    root = pathlib.Path(docs_root) if docs_root is not None else toc.docs_root()
    repo_root = root.parent
    world = World()
    if not root.is_dir():
        return world

    directories = sorted(
        entry for entry in root.iterdir() if entry.is_dir() and not entry.name.startswith("_")
    )

    pending: list[Region] = []
    for directory in directories:
        groups = _read_groups(directory)
        if not groups:
            continue
        title, subtitle = region_name(directory.name)
        region = Region(name=directory.name, title=title, subtitle=subtitle)

        sizes = [_village_size(len(pages)) for _, pages in groups]
        cursor_col = 0
        cursor_row = 0
        row_height = 0
        placements: list[tuple[int, int]] = []
        for index, (width, height) in enumerate(sizes):
            if index and index % REGION_COLUMNS == 0:
                cursor_col = 0
                cursor_row += row_height + VILLAGE_GAP
                row_height = 0
            placements.append((cursor_col, cursor_row))
            row_height = max(row_height, height)
            cursor_col += width + VILLAGE_GAP

        region.rect = (
            0,
            0,
            max((col + size[0] for (col, _), size in zip(placements, sizes)), default=1)
            + VILLAGE_GAP,
            cursor_row + row_height + VILLAGE_GAP,
        )

        for (group_title, pages), (col, row), (width, height) in zip(groups, placements, sizes):
            village = Village(name=group_title, rect=(col, row, width, height))
            for page_index, (node, depth) in enumerate(pages):
                village.rooms.append(
                    Room(
                        title=node.title,
                        path=node.path,
                        address=_address(node.path, repo_root),
                        depth=depth,
                        state=_state_for(node.path),
                        tile=(
                            col + 2 + (page_index % VILLAGE_COLUMNS) * 2,
                            row + 2 + (page_index // VILLAGE_COLUMNS) * 2,
                        ),
                    )
                )
            # The gate sits in the middle of the south wall, so every compound is
            # entered the same way and the roads have something to aim at.
            village.gate = (col + width // 2, row + height - 1)
            region.villages.append(village)
        pending.append(region)

    cursor_col = MOAT
    cursor_row = MOAT
    row_height = 0
    for index, region in enumerate(pending):
        _, _, width, height = region.rect
        if index and index % REGION_COLUMNS == 0:
            cursor_col = MOAT
            cursor_row += row_height + REGION_GAP
            row_height = 0
        _translate_region(region, cursor_col, cursor_row)
        row_height = max(row_height, height)
        cursor_col += width + REGION_GAP
        world.regions.append(region)

    _paint(world)
    return world


def _translate_region(region: Region, col: int, row: int) -> None:
    """Move a region and everything in it onto the grid.

    Regions are measured at the origin, so this is a pure translation. Anchoring
    to where the *contents* happen to sit would mean one page's placement could
    shift its whole land.

    Parameters
    ----------
    region : Region
        The region.
    col, row : int
        Destination origin, in tiles.
    """
    _, _, width, height = region.rect
    region.rect = (col, row, width, height)
    for village in region.villages:
        vcol, vrow, vwidth, vheight = village.rect
        village.rect = (vcol + col, vrow + row, vwidth, vheight)
        village.gate = (village.gate[0] + col, village.gate[1] + row)
        for room in village.rooms:
            room.tile = (room.tile[0] + col, room.tile[1] + row)


def _paint(world: World) -> None:
    """Paint the tile grid from the placed regions.

    Parameters
    ----------
    world : World
        The world to paint in situ. Its ``grid`` is replaced.
    """
    if not world.regions:
        return

    width = max(region.rect[0] + region.rect[2] for region in world.regions) + MOAT
    height = max(region.rect[1] + region.rect[3] for region in world.regions) + MOAT

    # Everything is water until a land claims it, so the regions read as islands
    # and the gaps between them are impassable rather than merely empty.
    grid = [[WATER for _ in range(width)] for _ in range(height)]

    for region in world.regions:
        _paint_region(grid, region)
    _paint_bridges(grid, world.regions)
    for region in world.regions:
        _paint_roads(grid, region)
    for region in world.regions:
        for village in region.villages:
            _paint_village(grid, village)

    world.grid = grid
    world.array = np.asarray(grid, dtype=np.uint8)


def _paint_region(grid: list[list[int]], region: Region) -> None:
    """Lay a land's ground: grass, with woodland and rock scattered over it.

    Parameters
    ----------
    grid : list of list of int
        The tile grid.
    region : Region
        The region to paint.
    """
    col, row, width, height = region.rect
    salt = _seed(region.name) & 0xFFFFFFFF
    for y in range(row, row + height):
        for x in range(col, col + width):
            if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
                continue
            # A tile's own coordinates seed its terrain, so the wilderness is
            # identical on every run without anything being stored.
            roll = _tile_noise(salt, x, y)
            if roll < 11:
                grid[y][x] = TREE
            elif roll < 14:
                grid[y][x] = ROCK
            else:
                grid[y][x] = GRASS


def _paint_roads(grid: list[list[int]], region: Region) -> None:
    """Run roads gate to gate through a land.

    Parameters
    ----------
    grid : list of list of int
        The tile grid.
    region : Region
        The region whose villages are being connected.
    """
    gates = [village.gate for village in region.villages]
    for start, end in zip(gates, gates[1:]):
        # Leave the gate southward first, so a road never tries to start inside
        # the compound it is leaving.
        approach = (start[0], start[1] + 2)
        exit_ = (end[0], end[1] + 2)
        _paint_line(grid, start, approach)
        _paint_line(grid, approach, (exit_[0], approach[1]))
        _paint_line(grid, (exit_[0], approach[1]), exit_)
        _paint_line(grid, exit_, end)


def _paint_line(grid: list[list[int]], start: tuple[int, int], end: tuple[int, int]) -> None:
    """Paint a straight run of road between two cells.

    Parameters
    ----------
    grid : list of list of int
        The tile grid.
    start, end : tuple of int
        Grid cells. The run must be axis-aligned.
    """
    x0, y0 = start
    x1, y1 = end
    step_x = (x1 > x0) - (x1 < x0)
    step_y = (y1 > y0) - (y1 < y0)
    x, y = x0, y0
    while True:
        if 0 <= y < len(grid) and 0 <= x < len(grid[0]) and grid[y][x] not in (WATER, BRIDGE):
            grid[y][x] = ROAD
        if (x, y) == (x1, y1):
            break
        x += step_x
        y += step_y


def _paint_village(grid: list[list[int]], village: Village) -> None:
    """Paint a walled compound with a gate, a floor, and its buildings.

    Parameters
    ----------
    grid : list of list of int
        The tile grid.
    village : Village
        The village to paint.
    """
    col, row, width, height = village.rect
    for y in range(row, row + height):
        for x in range(col, col + width):
            if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
                continue
            on_edge = x in (col, col + width - 1) or y in (row, row + height - 1)
            grid[y][x] = WALL if on_edge else FLOOR

    gate_col, gate_row = village.gate
    if 0 <= gate_row < len(grid) and 0 <= gate_col < len(grid[0]):
        grid[gate_row][gate_col] = GATE

    for room in village.rooms:
        x, y = room.tile
        if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
            grid[y][x] = BUILDING


def _paint_bridges(grid: list[list[int]], regions: list[Region]) -> None:
    """Bridge the water between neighbouring lands.

    Without these the lands are unreachable from one another, which would make
    the moat a wall rather than a border.

    Parameters
    ----------
    grid : list of list of int
        The tile grid.
    regions : list of Region
        The placed regions, in layout order.
    """
    for index, region in enumerate(regions):
        col, row, width, height = region.rect
        if index + 1 < len(regions) and (index + 1) % REGION_COLUMNS != 0:
            other = regions[index + 1]
            ocol, orow, _, oheight = other.rect
            y = min(row + height // 2, orow + oheight // 2)
            for x in range(col + width, ocol):
                if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
                    grid[y][x] = BRIDGE
        if index + REGION_COLUMNS < len(regions):
            other = regions[index + REGION_COLUMNS]
            ocol, orow, owidth, _ = other.rect
            x = min(col + width // 2, ocol + owidth // 2)
            for y in range(row + height, orow):
                if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
                    grid[y][x] = BRIDGE
