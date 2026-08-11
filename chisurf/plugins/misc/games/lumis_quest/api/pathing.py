"""Getting somewhere when the direct line is a wall.

Steering (:mod:`.steering`) answers "which way now" for a creature with nowhere
in particular to be. This answers the other question: somebody with an
*errand* -- the innkeeper going to the well, Lumi following at heel -- has a
destination, and walking at it until something stops you is not a plan. Before
this, an agent whose tavern happened to sit behind a house gave the errand up:
the code said so in as many words ("blocked flat. Give up on this errand rather
than grinding into a wall"), which is an honest workaround for not having a
pathfinder and not a substitute for one.

Ported from the pathfinding in a small MIT-licensed top-down RPG under
``junk/pyzelda-rpg``. The search itself is textbook A* and is the *cheap* half.
The valuable half is the policy around it, which that game got right and which
is easy to leave out:

* **Recalculate when the path is stale or when the goal has changed cell,
  whichever comes first.** Recomputing every frame is what makes pathfinding
  expensive; recomputing only on a timer is what makes a follower cut corners
  into walls after its target has moved.
* **Fall back to the direct line when there is no path.** A creature that
  freezes because the search failed reads as broken; one that walks at you and
  bumps reads as stupid, which is much better and is sometimes even correct --
  the goal may be a doorway that is legitimately shut.

One thing is deliberately different. That game's maps are a screen; this world
is tens of thousands of tiles, and an unreachable goal makes an uncapped A*
explore **every reachable cell** before returning nothing -- per walker, per
recalculation. So the search takes a node budget and gives up, which turns the
pathological case into the fallback rather than into a dropped frame.
"""

from __future__ import annotations

import dataclasses
import heapq

from .tiles import TILE

#: The four ways out of a cell. Four, not eight: a diagonal step between two
#: blocked cells slips through a corner that has no gap in it, and every
#: eight-way grid search needs a special case to stop doing that.
NEIGHBOURS: tuple[tuple[int, int], ...] = ((0, -1), (0, 1), (-1, 0), (1, 0))

#: How many cells a single search may expand before giving up. Generous for a
#: walk across a settlement, and far short of a frame.
BUDGET = 1500

#: Seconds before a path is considered stale even if nothing moved.
INTERVAL = 0.5

#: How close, in world units, counts as having reached a waypoint. Below about
#: a third of a tile a walker jitters between two cells it is between.
REACHED = TILE * 0.35


def search(passable, start: tuple[int, int], goal: tuple[int, int],
           budget: int = BUDGET) -> list[tuple[int, int]]:
    """Find a way from one cell to another.

    Parameters
    ----------
    passable : callable
        ``passable(col, row) -> bool``. The world is not passed in, so this
        works equally on the lit grid, the dark manifold and a room interior.
    start, goal : tuple of int
        Grid cells.
    budget : int, optional
        Maximum cells to expand before giving up.

    Returns
    -------
    list of tuple
        Cells from ``start`` to ``goal`` inclusive, or an empty list when there
        is no way, when either end is solid, or when the budget ran out.
    """
    if start == goal:
        return [start]
    if not passable(*start) or not passable(*goal):
        return []

    came: dict[tuple[int, int], tuple[int, int]] = {}
    best = {start: 0}
    queue = [(_estimate(start, goal), 0, start)]
    seen: set[tuple[int, int]] = set()
    expanded = 0

    while queue:
        _, cost, cell = heapq.heappop(queue)
        if cell in seen:
            continue
        seen.add(cell)
        expanded += 1
        if expanded > budget:
            return []
        if cell == goal:
            return _unwind(came, cell)
        for dx, dy in NEIGHBOURS:
            step = (cell[0] + dx, cell[1] + dy)
            if step in seen or not passable(*step):
                continue
            walked = cost + 1
            if walked < best.get(step, 1 << 30):
                best[step] = walked
                came[step] = cell
                heapq.heappush(queue, (walked + _estimate(step, goal), walked, step))
    return []


def _estimate(cell: tuple[int, int], goal: tuple[int, int]) -> int:
    """Manhattan distance, which is exact for four-way movement on a grid.

    Parameters
    ----------
    cell, goal : tuple of int
        Grid cells.

    Returns
    -------
    int
        Steps, ignoring obstacles.
    """
    return abs(cell[0] - goal[0]) + abs(cell[1] - goal[1])


def _unwind(came: dict, cell: tuple[int, int]) -> list[tuple[int, int]]:
    """Turn the came-from map into a path.

    Parameters
    ----------
    came : dict
        Cell to the cell it was reached from.
    cell : tuple of int
        The goal.

    Returns
    -------
    list of tuple
        Start to goal inclusive.
    """
    path = [cell]
    while cell in came:
        cell = came[cell]
        path.append(cell)
    path.reverse()
    return path


@dataclasses.dataclass
class Route:
    """One walker's plan, kept between frames.

    Attributes
    ----------
    interval : float
        Seconds before the path is recomputed even if nothing has moved.
    cells : list of tuple
        What is left of the plan, nearest first.
    goal : tuple of int or None
        The cell the current plan was computed for. When the destination moves
        to a different cell the plan is wrong *now*, not in half a second,
        which is the other half of the policy.
    age : float
        Seconds since the last search.
    searches : int
        How many searches this route has run. Diagnostic -- a route that
        recomputes every frame is a bug, and this is how it becomes visible.
    """

    interval: float = INTERVAL
    cells: list[tuple[int, int]] = dataclasses.field(default_factory=list)
    goal: tuple[int, int] | None = None
    age: float = 0.0
    searches: int = 0

    def clear(self) -> None:
        """Forget the plan, e.g. when the errand changes."""
        self.cells.clear()
        self.goal = None

    def waypoint(self, passable, position: tuple[float, float],
                 destination: tuple[float, float],
                 dt: float = 0.0) -> tuple[float, float]:
        """Where to walk *next* on the way to where you are going.

        Parameters
        ----------
        passable : callable
            ``passable(col, row) -> bool``.
        position : tuple of float
            Where the walker is, in world units.
        destination : tuple of float
            Where it wants to be.
        dt : float, optional
            Seconds since the last call, for the staleness timer.

        Returns
        -------
        tuple of float
            A point in world units to steer at. When no path exists this is
            the destination itself, so a walker with nowhere to go still tries
            -- which is the right failure, because the obstruction may be a
            door that is merely shut.
        """
        self.age += dt
        here = (int(position[0] // TILE), int(position[1] // TILE))
        goal = (int(destination[0] // TILE), int(destination[1] // TILE))

        if self.goal != goal or self.age >= self.interval or not self.cells:
            self.cells = search(passable, here, goal)[1:]
            self.goal = goal
            self.age = 0.0
            self.searches += 1

        # Drop waypoints already reached. More than one can fall in a frame
        # when the walker is fast or the frame was slow.
        while self.cells and _near(position, self.cells[0]):
            self.cells.pop(0)
        if not self.cells:
            return destination
        cell = self.cells[0]
        return ((cell[0] + 0.5) * TILE, (cell[1] + 0.5) * TILE)


def _near(position: tuple[float, float], cell: tuple[int, int]) -> bool:
    """Whether a walker has arrived at a cell's middle.

    Parameters
    ----------
    position : tuple of float
        World units.
    cell : tuple of int
        Grid cell.

    Returns
    -------
    bool
        True when close enough to move on to the next waypoint.
    """
    return (abs(position[0] - (cell[0] + 0.5) * TILE) <= REACHED
            and abs(position[1] - (cell[1] + 0.5) * TILE) <= REACHED)


def open_ground(world, walkable, dark: bool = False):
    """A passability test over a world's grid.

    Parameters
    ----------
    world : World
        The world.
    walkable : container of int
        Tile kinds that may be stood on.
    dark : bool, optional
        Test the dark manifold.

    Returns
    -------
    callable
        ``passable(col, row) -> bool``.
    """
    def passable(col: int, row: int) -> bool:
        return world.tile_at(col, row, dark) in walkable

    return passable
