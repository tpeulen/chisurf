"""The overworld, generated from the documentation itself.

The map is not authored. It is derived from the docs' own ``toctree`` blocks --
the structure a human curated, rather than whatever order the filesystem
happens to return -- and from the per-directory review sidecars that already
record what has been signed off.

Three ideas carry the whole thing:

* **Layout is seeded by a page's path.** A page keeps its position as the corpus
  churns, so adding a page puts a new building somewhere new instead of
  reshuffling the world. Nothing is random at run time.
* **Fog is review state, and the three states are different.** A page with no
  sidecar entry at all has never been *touched*; one marked ``ai-reviewed`` has
  been scouted but not signed off by a human; one ``reviewed`` is settled. The
  middle state is the interesting frontier and must not be collapsed into
  either neighbour.
* **Remoteness is review debt.** How far a room sits off the beaten path is a
  function of how deep and unlinked it is *and* whether anyone has looked at it,
  so the reward gradient points where the corpus actually needs attention.

This module is Qt-free and imports nothing from the engine: it is the model the
view draws, and it is what makes the map testable without a window.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import pathlib

from chisurf.plugins.core.help.api import review, toc

#: Room states, in increasing order of settledness.
WILD = "wild"
SCOUTED = "scouted"
SETTLED = "settled"

#: World units per room, and how far apart villages and regions sit.
ROOM_SPACING = 44.0
VILLAGE_SPACING = 260.0
REGION_SPACING = 1100.0

#: Rooms per row inside a village before it wraps.
VILLAGE_COLUMNS = 5

#: Villages per row inside a region before it wraps.
REGION_COLUMNS = 3

#: Clear space left between neighbouring regions, in world units.
REGION_MARGIN = 260.0


def _village_height(room_count: int) -> float:
    """Vertical extent a village needs for its rooms.

    Parameters
    ----------
    room_count : int
        Number of rooms.

    Returns
    -------
    float
        Height in world units.
    """
    rows = max(1, math.ceil(room_count / VILLAGE_COLUMNS))
    return rows * ROOM_SPACING + 70.0


def _seed(text: str) -> int:
    """A stable integer derived from a string.

    ``hash()`` is salted per process, so it cannot be used: the map would move
    every time the game started.

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


def _jitter(text: str, amount: float) -> tuple[float, float]:
    """A small deterministic offset, so a grid does not look like a grid.

    Parameters
    ----------
    text : str
        Identifier the offset is derived from.
    amount : float
        Maximum displacement in world units.

    Returns
    -------
    tuple of float
        ``(dx, dy)``.
    """
    seed = _seed(text)
    angle = (seed % 3600) / 3600.0 * math.tau
    radius = ((seed >> 12) % 1000) / 1000.0 * amount
    return math.cos(angle) * radius, math.sin(angle) * radius


@dataclasses.dataclass
class Room:
    """One documentation page, as a place.

    Attributes
    ----------
    title : str
        The page's own title.
    path : pathlib.Path
        Absolute path to the source file.
    address : str
        Repository-relative address, e.g. ``docs/guides/11_burst.md``.
    depth : int
        How deep the page sits in the toctree. Used for remoteness.
    state : str
        One of :data:`WILD`, :data:`SCOUTED`, :data:`SETTLED`.
    position : tuple of float
        World coordinates, seeded by ``address``.
    """

    title: str
    path: pathlib.Path
    address: str
    depth: int
    state: str
    position: tuple[float, float]

    @property
    def remoteness(self) -> float:
        """How far off the beaten path this room is, in 0..1.

        Depth and review debt both count, because the point of the gradient is
        to send a player toward pages nobody has looked at rather than toward
        pages that merely sit deep in a well-tended section.

        Returns
        -------
        float
            Higher means more rewarding to reach.
        """
        debt = {WILD: 1.0, SCOUTED: 0.5, SETTLED: 0.0}[self.state]
        depth_term = min(self.depth, 5) / 5.0
        return 0.65 * debt + 0.35 * depth_term


@dataclasses.dataclass
class Village:
    """A toctree group or subdirectory: a cluster of rooms.

    Attributes
    ----------
    name : str
        The group's title.
    rooms : list of Room
        Its pages.
    position : tuple of float
        Centre in world coordinates.
    """

    name: str
    rooms: list[Room] = dataclasses.field(default_factory=list)
    position: tuple[float, float] = (0.0, 0.0)

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
    """A top-level documentation directory.

    Attributes
    ----------
    name : str
        Directory name, e.g. ``guides``.
    title : str
        The section's own title where the toctree gives one.
    villages : list of Village
        Its groups.
    position : tuple of float
        Origin in world coordinates.
    extent : tuple of float
        Nominal ``(width, height)`` of the village grid, before jitter. Regions
        are packed by this rather than by where their rooms happen to land, so
        one page's jitter cannot shift a whole region.
    """

    name: str
    title: str
    villages: list[Village] = dataclasses.field(default_factory=list)
    position: tuple[float, float] = (0.0, 0.0)
    extent: tuple[float, float] = (0.0, 0.0)

    @property
    def rooms(self) -> list[Room]:
        """Every room in the region.

        Returns
        -------
        list of Room
            Flattened across villages.
        """
        return [room for village in self.villages for room in village.rooms]


@dataclasses.dataclass
class World:
    """The whole generated overworld.

    Attributes
    ----------
    regions : list of Region
        One per top-level documentation directory.
    """

    regions: list[Region] = dataclasses.field(default_factory=list)

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

    def bounds(self) -> tuple[float, float, float, float]:
        """Axis-aligned extent of every room.

        Returns
        -------
        tuple of float
            ``(min_x, min_y, max_x, max_y)``; a unit box for an empty world.
        """
        rooms = self.rooms
        if not rooms:
            return (0.0, 0.0, 1.0, 1.0)
        xs = [room.position[0] for room in rooms]
        ys = [room.position[1] for room in rooms]
        return (min(xs), min(ys), max(xs), max(ys))

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
            dx = room.position[0] - position[0]
            dy = room.position[1] - position[1]
            distance = dx * dx + dy * dy
            if distance < best_distance:
                best_distance = distance
                best = room
        return best


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
        Regions, villages and rooms with deterministic positions.
    """
    root = pathlib.Path(docs_root) if docs_root is not None else toc.docs_root()
    repo_root = root.parent
    world = World()
    if not root.is_dir():
        return world

    directories = sorted(
        entry for entry in root.iterdir() if entry.is_dir() and not entry.name.startswith("_")
    )

    region_index = 0
    for directory in directories:
        index_file = next(
            (directory / f"index{suffix}" for suffix in (".md", ".rst")
             if (directory / f"index{suffix}").is_file()),
            None,
        )
        groups: list[tuple[str, list[tuple[toc.Node, int]]]] = []
        if index_file is not None:
            nodes = toc.read_index(index_file)
            for node in nodes:
                pages = _collect(node)
                if pages:
                    groups.append((node.title, pages))
        if not groups:
            # No toctree to curate the order: fall back to the files themselves
            # so a region still appears rather than silently vanishing.
            pages = [
                (toc.Node(title=path.stem.replace("_", " ").title(), path=path), 1)
                for path in sorted(directory.rglob("*"))
                if path.suffix in {".md", ".rst"} and path.name != "index.rst"
            ]
            if pages:
                groups.append((directory.name.replace("_", " ").title(), pages))
        # Pages the toctree never mentions. They are the most interesting rooms
        # in the corpus -- nothing links them, so nobody arrives at them by
        # reading -- and leaving them out would make them the one thing the map
        # can never send a player to. They get their own outlying village.
        linked = {
            node.path.resolve()
            for _, pages in groups
            for node, _ in pages
            if node.path is not None
        }
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

        if not groups:
            continue

        region_pos = (0.0, 0.0)  # placed once the region's own size is known
        region = Region(name=directory.name, title=directory.name.replace("_", " ").title(),
                        position=region_pos)
        region_index += 1

        # Villages are packed with a flow layout that advances by the *tallest*
        # village in each row. A fixed pitch is what made a 30-room village
        # (six rows of rooms, 264 units) overlap the one below it at a 260-unit
        # spacing -- villages sat on top of each other in the map view.
        cursor_x = 0.0
        cursor_y = 0.0
        row_height = 0.0
        for village_index, (group_title, pages) in enumerate(groups):
            village_height = _village_height(len(pages))
            if village_index and village_index % REGION_COLUMNS == 0:
                cursor_x = 0.0
                cursor_y += row_height + VILLAGE_SPACING * 0.25
                row_height = 0.0
            row_height = max(row_height, village_height)

            jitter = _jitter(f"{directory.name}/{group_title}", VILLAGE_SPACING * 0.10)
            village_pos = (
                region_pos[0] + cursor_x + jitter[0],
                region_pos[1] + cursor_y + jitter[1],
            )
            cursor_x += VILLAGE_SPACING
            village = Village(name=group_title, position=village_pos)

            for page_index, (node, depth) in enumerate(pages):
                address = _address(node.path, repo_root)
                rcol = page_index % VILLAGE_COLUMNS
                rrow = page_index // VILLAGE_COLUMNS
                offset = _jitter(address, ROOM_SPACING * 0.30)
                village.rooms.append(
                    Room(
                        title=node.title,
                        path=node.path,
                        address=address,
                        depth=depth,
                        state=_state_for(node.path),
                        position=(
                            village_pos[0] + (rcol - (VILLAGE_COLUMNS - 1) / 2) * ROOM_SPACING
                            + offset[0],
                            village_pos[1] + rrow * ROOM_SPACING + offset[1],
                        ),
                    )
                )
            region.villages.append(village)

        region.extent = (
            min(len(groups), REGION_COLUMNS) * VILLAGE_SPACING,
            cursor_y + row_height,
        )
        world.regions.append(region)

    _place_regions(world)
    return world


def _place_regions(world: World) -> None:
    """Lay regions out so they do not overlap, and re-anchor their rooms.

    Each region is built at the origin because its extent is not known until
    its villages exist. This shifts every region into place afterwards, packing
    rows by the tallest region in each -- the same reason villages need a flow
    layout rather than a fixed pitch.

    Parameters
    ----------
    world : World
        The world to place in situ.
    """
    cursor_x = 0.0
    cursor_y = 0.0
    row_height = 0.0
    for index, region in enumerate(world.regions):
        width, height = region.extent
        if index and index % REGION_COLUMNS == 0:
            cursor_x = 0.0
            cursor_y += row_height + REGION_MARGIN
            row_height = 0.0
        row_height = max(row_height, height)
        _shift_region(region, cursor_x, cursor_y)
        cursor_x += width + REGION_MARGIN


def _shift_region(region: Region, x: float, y: float) -> None:
    """Translate a region and everything in it.

    Regions are built at the origin, so this is a pure translation by ``(x, y)``
    rather than a re-anchoring. Re-anchoring to the region's *room* bounds is
    what made adding one page move every other page in the region: a new room's
    jitter could lower the minimum, and the whole region slid to compensate.

    Parameters
    ----------
    region : Region
        The region.
    x, y : float
        Translation in world units.
    """
    dx, dy = x, y
    region.position = (region.position[0] + dx, region.position[1] + dy)
    for village in region.villages:
        village.position = (village.position[0] + dx, village.position[1] + dy)
        for room in village.rooms:
            room.position = (room.position[0] + dx, room.position[1] + dy)


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
        A POSIX-style relative address, or the absolute path when the page
        lies outside the repository.
    """
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()
