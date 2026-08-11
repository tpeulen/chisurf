"""The overworld: a real tile map, generated from the documentation.

The map is not authored, and it is not a scatter of markers either. It is a grid
that gets *painted*: grass and woodland, lakes with sand at their rim, rivers
you cross at a bridge, cliffs you walk around until you find the cave in them,
roads that run between places, and settlements that are laid out like towns
rather than stamped like tables.

Its shape comes from the documentation:

* a **region** is a top-level documentation directory, named as a place rather
  than a folder (see :mod:`.names`) and given a **biome**, so no two lands look
  alike;
* a **settlement** is a toctree group -- a hamlet, village or town depending on
  how many pages it holds (see :mod:`.places`);
* a **room** is a page, and it is a building you stand in front of.

Four rules hold the generation together:

* **Layout is seeded by a page's path**, so a page keeps its place as the corpus
  churns and adding one is a new building rather than a reshuffle. Nothing is
  random at run time.
* **Fog is review state, and the three states stay three things.** Untouched,
  AI-scouted, human-settled. The middle one is the frontier the game exists to
  work and must not be collapsed into either neighbour.
* **Remoteness is review debt**, weighted above depth, so the reward gradient
  points where the corpus actually needs attention.
* **The map opens in an order.** Each land's crossing wants a Warden's seal
  (see :mod:`.tiers`), so the world is large without being formless.

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

from . import places
from .names import biome_for, region_name, settlement_name
from .tiles import (
    BRIDGE,
    BUILDING,
    CAVE,
    CLIFF,
    CLINIC,
    DOCK,
    FLOWERS,
    GATE,
    GRASS,
    MARSH,
    ROAD,
    ROCK,
    SAND,
    TILE,
    TREE,
    VOID,
    WATER,
    is_blocking,
)
from .tiers import WARDENS, crossing_tier

#: Room states, in increasing order of settledness. WITHERED is the garden
#: half of the farm layer: a page whose content moved under its sign-off is
#: not merely wild again — it is a plot that was tended and has rotted, and
#: doc rot should be visible from across the map.
WILD = "wild"
WITHERED = "withered"
SCOUTED = "scouted"
SETTLED = "settled"

#: Settlements per row inside a region before it wraps.
REGION_COLUMNS = 3

#: Open ground between compounds and between lands, in tiles. These are large
#: on purpose: a world you cross in four strides is a menu with scenery, and
#: the wilderness between settlements is where exploration happens at all.
VILLAGE_GAP = 18
REGION_GAP = 30

#: Thickness of the water separating one land from the next.
MOAT = 7

#: Tiles of solid woodland around each land's rim. A border you can see beats an
#: invisible boundary, and it is what stops the map ending in mid-field.
BORDER_WOOD = 2

#: Clear ground kept either side of a road, and around every compound. Without
#: it a copse grows across the only way in and the road becomes impassable.
VERGE = 1

#: How much of a land is woodland, rock, marsh and flowers, per biome. These are
#: percentages against a per-tile roll, and they are most of why a coast does
#: not read like a deep wood.
BIOME_COVER: dict[str, dict[str, int]] = {
    "meadow": {"copse": 12, "tree": 45, "rock": 3, "marsh": 0, "flower": 2, "lakes": 2},
    "forest": {"copse": 34, "tree": 72, "rock": 4, "marsh": 2, "flower": 2, "lakes": 2},
    "marsh": {"copse": 16, "tree": 40, "rock": 1, "marsh": 22, "flower": 3, "lakes": 4},
    "highland": {"copse": 9, "tree": 38, "rock": 14, "marsh": 0, "flower": 2, "lakes": 2},
    "coast": {"copse": 10, "tree": 40, "rock": 4, "marsh": 4, "flower": 2, "lakes": 3},
}


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
        debt = {WILD: 1.0, WITHERED: 1.0, SCOUTED: 0.5, SETTLED: 0.0}[self.state]
        return 0.65 * debt + 0.35 * (min(self.depth, 5) / 5.0)


@dataclasses.dataclass
class Village:
    """A toctree group, as a settlement: hamlet, village or town.

    Attributes
    ----------
    name : str
        The group's own title -- what the place is known *for*.
    place : str
        Its place name, e.g. ``Emberford``. A section heading is not somewhere
        anybody walks to.
    kind : str
        ``hamlet``, ``village`` or ``town``.
    rooms : list of Room
        Its pages.
    rect : tuple of int
        ``(col, row, width, height)`` of the compound, walls included.
    gate : tuple of int
        Grid cell of the gate in the wall.
    clinic : tuple of int
        Grid cell of the recovery station, just inside the gate.
    premises : dict
        Named landmarks in world tiles: ``well``, ``tavern``, ``shop``,
        ``smithy``, ``shrine``, ``hall``.
    warden : str
        Key into :data:`chisurf.plugins.misc.games.lumis_quest.api.tiers.BY_KEY`
        when a Warden holds their hall here, else empty.
    """

    name: str
    place: str = ""
    kind: str = "village"
    rooms: list[Room] = dataclasses.field(default_factory=list)
    rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    gate: tuple[int, int] = (0, 0)
    clinic: tuple[int, int] = (0, 0)
    premises: dict[str, tuple[int, int]] = dataclasses.field(default_factory=dict)
    warden: str = ""

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

    @property
    def label(self) -> str:
        """How the place announces itself.

        Returns
        -------
        str
            Place name and what it keeps.
        """
        return f"{self.place} -- {self.name}" if self.place else self.name


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
    biome : str
        A key of :data:`chisurf.plugins.misc.games.lumis_quest.api.names.BIOMES`.
    index : int
        Position in layout order, which is also how far into the run it sits.
    villages : list of Village
        Its settlements.
    rect : tuple of int
        ``(col, row, width, height)`` of the land, in tiles.
    cave : tuple of int or None
        Grid cell of the cave mouth in its cliffs, when it has any.
    """

    name: str
    title: str
    subtitle: str = ""
    biome: str = "meadow"
    index: int = 0
    villages: list[Village] = dataclasses.field(default_factory=list)
    rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    cave: tuple[int, int] | None = None

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

    @property
    def crossing_tier(self) -> int:
        """Which licence the way into this land demands.

        Returns
        -------
        int
            1..5, from :func:`..tiers.crossing_tier`.
        """
        return crossing_tier(self.index)


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
    #: The dark manifold: the same ground with the light taken out. Built once
    #: beside the lit world so crossing over is a swap rather than a rebuild.
    dark: np.ndarray = dataclasses.field(default_factory=lambda: np.zeros((0, 0), np.uint8))
    #: Salts the terrain only; the structure is always the documentation's.
    seed: str = ""

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

    @property
    def caves(self) -> list[tuple[int, int]]:
        """Every cave mouth in the world.

        Returns
        -------
        list of tuple
            Grid cells. These are the crossings into the dark manifold.
        """
        return [region.cave for region in self.regions if region.cave is not None]

    def tile_at(self, col: int, row: int, dark: bool = False) -> int:
        """The tile at a grid cell.

        Parameters
        ----------
        col, row : int
            Grid coordinates.
        dark : bool, optional
            Read the dark manifold instead of the lit world.

        Returns
        -------
        int
            The tile kind. Outside the grid reads as :data:`VOID`, so a walker
            cannot leave the world by walking off the edge.
        """
        if row < 0 or row >= self.height or col < 0 or col >= self.width:
            return VOID
        if dark and self.dark.size:
            return int(self.dark[row, col])
        return self.grid[row][col]

    def blocked(self, x: float, y: float, dark: bool = False) -> bool:
        """Whether a world position is inside something solid.

        Parameters
        ----------
        x, y : float
            World coordinates.
        dark : bool, optional
            Test the dark manifold.

        Returns
        -------
        bool
            True when a walker cannot stand there.
        """
        return is_blocking(self.tile_at(int(x // TILE), int(y // TILE), dark))

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
        tally = {WILD: 0, WITHERED: 0, SCOUTED: 0, SETTLED: 0}
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

    def village_at(self, x: float, y: float) -> Village | None:
        """The settlement containing a world position.

        Parameters
        ----------
        x, y : float
            World coordinates.

        Returns
        -------
        Village or None
            ``None`` when standing outside every compound.
        """
        col, row = int(x // TILE), int(y // TILE)
        for village in self.villages:
            vcol, vrow, width, height = village.rect
            if vcol <= col < vcol + width and vrow <= row < vrow + height:
                return village
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
                return ((col + 0.5) * TILE, (row + 2.5) * TILE)
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
    if status == review.STATUS_STALE:
        # The page moved under a sign-off: a plot that was tended and has
        # rotted. It fights like a wild room but must not look like one --
        # crop rot the gardener cannot see is crop rot nobody fixes.
        return WITHERED
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


def _warden_seats(regions: list[Region]) -> None:
    """Give each Warden a hall, in a land whose character suits them.

    A Warden with no seat is a fight the player can never find, so the fallback
    matters more than the preference: every Warden gets a settlement even in a
    corpus that has none of the directories they would have chosen.

    Parameters
    ----------
    regions : list of Region
        The placed lands, modified in place.
    """
    if not regions:
        return
    by_name = {region.name: region for region in regions}
    taken: set[int] = set()
    for index, warden in enumerate(WARDENS):
        region = next((by_name[name] for name in warden.lands if name in by_name), None)
        if region is None or not region.villages:
            region = regions[index % len(regions)]
        village = next(
            (v for v in region.villages if id(v) not in taken and not v.warden),
            None,
        )
        if village is None:
            # Every settlement in the preferred land is spoken for: take the
            # biggest free one anywhere rather than dropping the Warden.
            free = [v for r in regions for v in r.villages if id(v) not in taken]
            if not free:
                continue
            village = max(free, key=lambda v: len(v.rooms))
        village.warden = warden.key
        taken.add(id(village))


def build_world(docs_root: pathlib.Path | None = None, seed: str = "") -> World:
    """Generate the overworld from the documentation tree.

    Parameters
    ----------
    docs_root : pathlib.Path, optional
        Documentation root. Defaults to the one the help browser reads, so the
        game and the help window always describe the same corpus.
    seed : str, optional
        Salts the terrain. The *structure* -- which lands exist, which villages,
        which buildings -- always comes from the documentation and never moves;
        only the wilderness between them is redrawn. That is the useful thing to
        regenerate: a player who has learned where a page lives should not lose
        that by asking for new scenery.

    Returns
    -------
    World
        Regions, villages, rooms, and the painted tile grid.
    """
    root = pathlib.Path(docs_root) if docs_root is not None else toc.docs_root()
    repo_root = root.parent
    world = World()
    world.seed = seed
    if not root.is_dir():
        return world

    directories = sorted(
        entry for entry in root.iterdir() if entry.is_dir() and not entry.name.startswith("_")
    )

    # First pass: what exists. No geometry yet -- a Warden's seat is always a
    # town, and deciding that *after* the compounds were measured is what made
    # the walls of an upgraded settlement paint at the old size while its rect
    # said otherwise. Iris walked straight through one.
    pending: list[Region] = []
    contents: list[list[tuple[str, list]]] = []
    for directory in directories:
        groups = _read_groups(directory)
        if not groups:
            continue
        title, subtitle = region_name(directory.name)
        region = Region(
            name=directory.name, title=title, subtitle=subtitle,
            biome=biome_for(len(pending), directory.name), index=len(pending),
        )
        for group_title, pages in groups:
            region.villages.append(
                Village(
                    name=group_title,
                    place=settlement_name(f"{directory.name}/{group_title}"),
                    rooms=[
                        Room(
                            title=node.title,
                            path=node.path,
                            address=_address(node.path, repo_root),
                            depth=depth,
                            state=_state_for(node.path),
                        )
                        for node, depth in pages
                    ],
                )
            )
        pending.append(region)
        contents.append(groups)

    _warden_seats(pending)

    # Second pass: geometry, now that every settlement knows what it is.
    plans: dict[int, places.Plan] = {}
    for region in pending:
        laid = []
        for village in region.villages:
            warden = bool(village.warden)
            village.kind = places.kind_for(len(village.rooms), warden=warden)
            laid.append(places.plan(len(village.rooms), village.kind, warden=warden))
        sizes = [(one.width, one.height) for one in laid]
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

        for village, (col, row), layout in zip(region.villages, placements, laid):
            village.rect = (col, row, layout.width, layout.height)
            for index, room in enumerate(village.rooms):
                cell = (layout.room_cells[index] if index < len(layout.room_cells)
                        else (1 + places.MARGIN, 1 + places.MARGIN))
                room.tile = (col + cell[0], row + cell[1])
            village.gate = (col + layout.gate[0], row + layout.gate[1])
            plans[id(village)] = layout

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

    _paint(world, plans)
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
        village.clinic = (village.clinic[0] + col, village.clinic[1] + row)
        for room in village.rooms:
            room.tile = (room.tile[0] + col, room.tile[1] + row)


def _paint(world: World, plans: dict[int, places.Plan]) -> None:
    """Paint the tile grid from the placed regions.

    Parameters
    ----------
    world : World
        The world to paint in situ. Its ``grid`` is replaced.
    plans : dict
        Settlement plans by ``id(village)``.
    """
    if not world.regions:
        return

    width = max(region.rect[0] + region.rect[2] for region in world.regions) + MOAT
    height = max(region.rect[1] + region.rect[3] for region in world.regions) + MOAT

    # Everything is water until a land claims it, so the regions read as islands
    # and the gaps between them are impassable rather than merely empty.
    grid = [[WATER for _ in range(width)] for _ in range(height)]

    for region in world.regions:
        _paint_region(grid, region, world.seed)
    for region in world.regions:
        _paint_lakes(grid, region, world.seed)
        _paint_cliffs(grid, region, world.seed)
    _paint_shores(grid)
    _paint_bridges(grid, world.regions)
    for region in world.regions:
        _paint_roads(grid, region)
    for region in world.regions:
        for village in region.villages:
            _clear_around(grid, village.rect, VERGE + 1)
    for region in world.regions:
        for village in region.villages:
            layout = plans.get(id(village))
            if layout is None:
                continue
            origin = (village.rect[0], village.rect[1])
            landmarks = places.paint(grid, origin, layout, _seed(village.place),
                                     warden=bool(village.warden))
            placed = places.paint_rooms(grid, origin, layout.room_cells)
            for room, tile in zip(village.rooms, placed):
                room.tile = tile
            village.gate = landmarks.get("gate", village.gate)
            village.clinic = landmarks.get("clinic", village.clinic)
            village.premises = {
                key: value for key, value in landmarks.items()
                if key not in ("gate", "clinic")
            }

    world.grid = grid
    world.array = np.asarray(grid, dtype=np.uint8)
    from . import darkworld
    world.dark = darkworld.shadow(world.array)
    darkworld.raise_tower(world)


def _paint_region(grid: list[list[int]], region: Region, world_seed: str = "") -> None:
    """Lay a land's ground, in the mix its biome calls for.

    Parameters
    ----------
    grid : list of list of int
        The tile grid.
    region : Region
        The region to paint.
    world_seed : str, optional
        Salts the scatter.
    """
    col, row, width, height = region.rect
    salt = _seed(region.name + world_seed) & 0xFFFFFFFF
    cover = BIOME_COVER.get(region.biome, BIOME_COVER["meadow"])
    for y in range(row, row + height):
        for x in range(col, col + width):
            if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
                continue

            # Woodland belongs at the edges, in a mass. Scattering single trees
            # across open ground is what makes walking feel like snagging: the
            # player is constantly clipping a one-tile obstacle in the middle of
            # a field. A border you can see, and clear ground inside it, is the
            # shape this kind of game has always used.
            edge = min(x - col, y - row, col + width - 1 - x, row + height - 1 - y)
            if edge < BORDER_WOOD:
                grid[y][x] = TREE
                continue

            # Inland, trees come in copses rather than singly: the coarse grid
            # decides whether there is a copse here at all, and only then does
            # the fine roll place trunks in it.
            copse = _tile_noise(salt, x // 4, y // 4) < cover["copse"]
            roll = _tile_noise(salt ^ 0x9E3779B9, x, y)
            boggy = _tile_noise(salt ^ 0x51ED270B, x // 5, y // 5) < cover["marsh"]
            if copse and roll < cover["tree"]:
                grid[y][x] = TREE
            elif boggy and roll < 70:
                grid[y][x] = MARSH
            elif not copse and roll < cover["rock"]:
                grid[y][x] = ROCK
            elif roll >= 100 - cover["flower"]:
                grid[y][x] = FLOWERS
            else:
                grid[y][x] = GRASS


def _free_of_villages(region: Region, col: int, row: int, radius: int) -> bool:
    """Whether a disc of ground has no settlement in it.

    Parameters
    ----------
    region : Region
        The land.
    col, row : int
        Centre, in tiles.
    radius : int
        How far to keep clear.

    Returns
    -------
    bool
        True when nothing built is within reach.
    """
    for village in region.villages:
        vcol, vrow, width, height = village.rect
        if (vcol - radius <= col <= vcol + width + radius
                and vrow - radius <= row <= vrow + height + radius):
            return False
    return True


def _open_basin(region: Region, radius_x: int, radius_y: int, salt: int,
                index: int = 0) -> tuple[int, int] | None:
    """Somewhere in a land with room for a mass of this size.

    Parameters
    ----------
    region : Region
        The land.
    radius_x, radius_y : int
        Half-extent of the thing being placed.
    salt : int
        Deterministic order of candidates.
    index : int, optional
        Which mass this is, so two do not land on the same spot.

    Returns
    -------
    tuple of int or None
        Centre in tiles, or ``None`` when the land has no room left.
    """
    col, row, width, height = region.rect
    clear = max(radius_x, radius_y) + 4
    span_x = max(1, width - 2 * BORDER_WOOD - 2 * radius_x - 4)
    span_y = max(1, height - 2 * BORDER_WOOD - 2 * radius_y - 4)
    for attempt in range(24):
        mix = salt >> (attempt % 20) ^ (attempt * 2654435761 + index * 40503)
        cx = col + BORDER_WOOD + radius_x + 2 + mix % span_x
        cy = row + BORDER_WOOD + radius_y + 2 + (mix >> 13) % span_y
        if _free_of_villages(region, cx, cy, clear):
            return (cx, cy)
    return None


def _paint_lakes(grid: list[list[int]], region: Region, world_seed: str = "") -> None:
    """Put standing water in a land, and a river out of it.

    A land with no water in it reads as a texture. A lake is a landmark you
    navigate by, a reason for a bridge, and where half the bodies in
    :mod:`.bestiary` live.

    Parameters
    ----------
    grid : list of list of int
        The tile grid.
    region : Region
        The land.
    world_seed : str, optional
        Salts placement.
    """
    col, row, width, height = region.rect
    cover = BIOME_COVER.get(region.biome, BIOME_COVER["meadow"])
    salt = _seed(f"{region.name}:lake:{world_seed}")
    for index in range(cover["lakes"]):
        spot_seed = salt >> (index * 7)
        radius_x = 5 + spot_seed % 7
        radius_y = 4 + (spot_seed >> 5) % 6
        # Try a spread of candidate basins rather than one. A single roll was
        # nearly always inside a settlement's clearance and the lake was simply
        # dropped, so most lands had no water in them at all.
        spot = _open_basin(region, radius_x, radius_y, spot_seed, index)
        if spot is None:
            continue
        cx, cy = spot
        for y in range(cy - radius_y - 1, cy + radius_y + 2):
            for x in range(cx - radius_x - 1, cx + radius_x + 2):
                if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
                    continue
                # A wobble on the rim, so the lake is not an ellipse anybody
                # would notice being an ellipse.
                wobble = 0.85 + _tile_noise(salt, x // 3, y // 3) / 300.0
                dx = (x - cx) / max(radius_x, 1)
                dy = (y - cy) / max(radius_y, 1)
                if dx * dx + dy * dy <= wobble:
                    grid[y][x] = WATER

        # A river leaves the lake for the sea, which is what stops the lake
        # being a puddle somebody dropped on the map.
        _paint_river(grid, region, (cx, cy + radius_y), salt >> (index * 3 + 1))


def _paint_river(grid: list[list[int]], region: Region, start: tuple[int, int],
                 salt: int) -> None:
    """Run a river from a point to the edge of its land.

    Parameters
    ----------
    grid : list of list of int
        The tile grid.
    region : Region
        The land, which bounds the run.
    start : tuple of int
        Where the river leaves the lake.
    salt : int
        Deterministic meander.
    """
    col, row, width, height = region.rect
    x, y = start
    for step in range(height):
        if not (row <= y < row + height and col <= x < col + width):
            break
        if not _free_of_villages(region, x, y, 3):
            break
        for dx in (0, 1):
            if 0 <= y < len(grid) and 0 <= x + dx < len(grid[0]):
                grid[y][x + dx] = WATER
        y += 1
        x += ((salt >> (step % 24)) & 3) - 1


def _paint_cliffs(grid: list[list[int]], region: Region, world_seed: str = "") -> None:
    """Raise a mass of cliff in a land, and open a cave in the foot of it.

    The cave is the crossing into the dark manifold, so every land that can
    hold one gets one: a way down that only exists in some lands would be a way
    down most players never find.

    Parameters
    ----------
    grid : list of list of int
        The tile grid.
    region : Region
        The land, modified through its ``cave`` field.
    world_seed : str, optional
        Salts placement.
    """
    col, row, width, height = region.rect
    salt = _seed(f"{region.name}:cliff:{world_seed}")
    tall = region.biome == "highland"
    radius_x = (9 if tall else 6) + salt % 4
    radius_y = (7 if tall else 4) + (salt >> 5) % 3

    # Cliffs sit against a land's rim, the way they do on every map of this
    # kind: a mountain in the middle of a field is a wall across the field. All
    # four corners are tried, then anywhere with room -- a land whose cliffs
    # were dropped is a land with no way down, and the crossing is the point.
    spot = None
    for corner in range(4):
        which = ((salt >> 9) + corner) % 4
        cx = col + (radius_x + BORDER_WOOD + 2 if which in (0, 2)
                    else width - radius_x - BORDER_WOOD - 2)
        cy = row + (radius_y + BORDER_WOOD + 2 if which in (0, 1)
                    else height - radius_y - BORDER_WOOD - 2)
        if _free_of_villages(region, cx, cy, max(radius_x, radius_y) + 3):
            spot = (cx, cy)
            break
    if spot is None:
        spot = _open_basin(region, radius_x, radius_y, salt, index=7)
    if spot is None:
        return
    cx, cy = spot

    for y in range(cy - radius_y, cy + radius_y + 1):
        for x in range(cx - radius_x, cx + radius_x + 1):
            if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
                continue
            wobble = 0.9 + _tile_noise(salt, x // 3, y // 3) / 260.0
            dx = (x - cx) / max(radius_x, 1)
            dy = (y - cy) / max(radius_y, 1)
            if dx * dx + dy * dy <= wobble:
                grid[y][x] = CLIFF

    # The mouth: at the foot of the mass, facing the open country, with the
    # cliff carved back either side so it reads as an opening.
    mouth_y = min(cy + radius_y, len(grid) - 1)
    while mouth_y > 0 and grid[mouth_y][cx] != CLIFF:
        mouth_y -= 1
    if 0 <= mouth_y < len(grid) and 0 <= cx < len(grid[0]):
        grid[mouth_y][cx] = CAVE
        if mouth_y + 1 < len(grid) and grid[mouth_y + 1][cx] == CLIFF:
            grid[mouth_y + 1][cx] = GRASS
        region.cave = (cx, mouth_y)


def _paint_shores(grid: list[list[int]]) -> None:
    """Put sand between every stretch of water and the ground beside it.

    Parameters
    ----------
    grid : list of list of int
        The tile grid, modified in place.
    """
    height = len(grid)
    width = len(grid[0]) if grid else 0
    shore: list[tuple[int, int]] = []
    for y in range(height):
        row = grid[y]
        for x in range(width):
            if row[x] not in (GRASS, FLOWERS, MARSH):
                continue
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width and grid[ny][nx] == WATER:
                    shore.append((x, y))
                    break
    for x, y in shore:
        grid[y][x] = SAND


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
    if region.cave is not None and gates:
        # A road to the cave mouth: a crossing nobody can find is a crossing
        # that is not in the game.
        cave = region.cave
        near = min(gates, key=lambda gate: abs(gate[0] - cave[0]) + abs(gate[1] - cave[1]))
        _paint_line(grid, (near[0], near[1] + 2), (cave[0], near[1] + 2))
        _paint_line(grid, (cave[0], near[1] + 2), (cave[0], cave[1] + 1))


def _clear_around(grid: list[list[int]], rect: tuple[int, int, int, int], margin: int) -> None:
    """Cut back woodland around a rectangle.

    A compound whose gate opens into a tree is a compound you cannot enter, and
    a road that a copse has grown across is not a road.

    Parameters
    ----------
    grid : list of list of int
        The tile grid.
    rect : tuple of int
        ``(col, row, width, height)``.
    margin : int
        How far out to clear.
    """
    col, row, width, height = rect
    for y in range(row - margin, row + height + margin):
        for x in range(col - margin, col + width + margin):
            if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
                continue
            if grid[y][x] in (TREE, ROCK, CLIFF, MARSH):
                grid[y][x] = GRASS


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
        for oy in range(-VERGE, VERGE + 1):
            for ox in range(-VERGE, VERGE + 1):
                cy, cx = y + oy, x + ox
                if 0 <= cy < len(grid) and 0 <= cx < len(grid[0]):
                    if grid[cy][cx] in (TREE, ROCK, CLIFF):
                        grid[cy][cx] = GRASS
        if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
            # A road that meets water becomes a bridge rather than stopping: a
            # river that cuts the only road in two is a river that strands the
            # player on one bank of their own map.
            if grid[y][x] in (WATER, BRIDGE):
                grid[y][x] = BRIDGE
            elif grid[y][x] not in (GATE, CAVE):
                grid[y][x] = ROAD
        if (x, y) == (x1, y1):
            break
        x += step_x
        y += step_y


def _paint_bridges(grid: list[list[int]], regions: list[Region]) -> None:
    """Bridge the water between neighbouring lands.

    Without these the lands are unreachable from one another, which would make
    the moat a wall rather than a border. A crossing also carries a *toll* in
    the game's terms -- see :attr:`Region.crossing_tier` -- so this is the point
    at which the map opens in an order.

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


def dock_tiles(world: World) -> list[tuple[int, int]]:
    """Every jetty in the world.

    Parameters
    ----------
    world : World
        The world to scan.

    Returns
    -------
    list of tuple
        Grid cells carrying :data:`..tiles.DOCK`.
    """
    if not world.array.size:
        return []
    rows, cols = np.nonzero(world.array == DOCK)
    return [(int(col), int(row)) for row, col in zip(rows, cols)]
