"""Somebody with an errand has a destination, and walking at it is not a plan."""

from __future__ import annotations

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import pathing
from chisurf.plugins.misc.games.lumis_quest.api.tiles import TILE


def _open(col: int, row: int) -> bool:
    """A world with nothing in it."""
    return 0 <= col < 20 and 0 <= row < 20


def _wall_at(*cells):
    """A world that is open except for the given cells."""
    blocked = set(cells)

    def passable(col: int, row: int) -> bool:
        return _open(col, row) and (col, row) not in blocked
    return passable


def _centre(cell):
    """The world point at the middle of a cell."""
    return ((cell[0] + 0.5) * TILE, (cell[1] + 0.5) * TILE)


def test_a_clear_run_is_the_short_way():
    """Manhattan distance is exact for four-way movement, so A* is optimal."""
    path = pathing.search(_open, (2, 2), (2, 7))
    assert path[0] == (2, 2) and path[-1] == (2, 7)
    assert len(path) == 6


def test_it_goes_round_a_wall_rather_than_giving_up():
    """The whole reason this exists.

    An errand whose destination sat behind a building used to be abandoned
    outright, and the code said so in as many words.
    """
    wall = _wall_at(*[(3, row) for row in range(0, 9)])
    path = pathing.search(wall, (2, 4), (4, 4))
    assert path, "no way round a wall that has an end to it"
    assert (3, 4) not in path
    assert path[-1] == (4, 4)


def test_a_walled_in_goal_has_no_path_at_all():
    """And says so, rather than returning one that goes through the wall."""
    boxed = _wall_at((4, 3), (4, 5), (3, 4), (5, 4))
    assert pathing.search(boxed, (1, 1), (4, 4)) == []


def test_a_solid_start_or_goal_is_refused_immediately():
    """Nothing stands in a wall, so nothing walks out of one either."""
    wall = _wall_at((5, 5))
    assert pathing.search(wall, (5, 5), (1, 1)) == []
    assert pathing.search(wall, (1, 1), (5, 5)) == []


def test_the_search_gives_up_before_it_costs_a_frame():
    """The reference had no budget, and its maps were one screen.

    This world is tens of thousands of tiles, and an unreachable goal makes an
    uncapped search expand *every reachable cell* -- per walker, per
    recalculation. The budget turns the pathological case into the fallback.
    """
    def wide(col: int, row: int) -> bool:
        return 0 <= col < 400 and 0 <= row < 400 and (col, row) != (399, 399)

    assert pathing.search(wide, (0, 0), (399, 399), budget=200) == []


def test_a_route_recomputes_when_the_goal_changes_cell_not_when_it_wiggles():
    """The half of the policy that is easy to leave out.

    On a timer alone a follower cuts a corner into a wall for half a second
    after its target has turned. Every frame, and the pathfinding *is* the
    frame.
    """
    route = pathing.Route(interval=10.0)
    route.waypoint(_open, _centre((1, 1)), _centre((6, 6)), 0.0)
    assert route.searches == 1

    # Same cell, a nudge: no new search.
    goal = _centre((6, 6))
    route.waypoint(_open, _centre((1, 1)), (goal[0] + 1.0, goal[1]), 0.0)
    assert route.searches == 1

    # A different cell: immediately.
    route.waypoint(_open, _centre((1, 1)), _centre((7, 6)), 0.0)
    assert route.searches == 2


def test_a_stale_route_is_recomputed_even_when_nothing_moved():
    """The world can change under a plan -- a gate shuts, somebody stands up."""
    route = pathing.Route(interval=0.5)
    route.waypoint(_open, _centre((1, 1)), _centre((6, 6)), 0.0)
    route.waypoint(_open, _centre((1, 1)), _centre((6, 6)), 0.2)
    assert route.searches == 1
    route.waypoint(_open, _centre((1, 1)), _centre((6, 6)), 0.4)
    assert route.searches == 2


def test_a_walker_following_a_route_gets_round_the_corner():
    """End to end: a wall between the two, and it arrives anyway."""
    wall = _wall_at(*[(3, row) for row in range(0, 8)])
    route = pathing.Route(interval=0.2)
    at = list(_centre((1, 4)))
    goal = _centre((5, 4))
    for _ in range(900):
        step = route.waypoint(wall, tuple(at), goal, 1 / 60)
        dx, dy = step[0] - at[0], step[1] - at[1]
        gap = (dx * dx + dy * dy) ** 0.5
        if gap > 1e-9:
            move = min(1.0, gap)
            at[0] += dx / gap * move
            at[1] += dy / gap * move
        assert wall(int(at[0] // TILE), int(at[1] // TILE)), "walked into the wall"
        if abs(at[0] - goal[0]) < TILE * 0.4 and abs(at[1] - goal[1]) < TILE * 0.4:
            break
    else:
        pytest.fail("never arrived")


def test_no_path_falls_back_to_the_direct_line():
    """A creature that freezes because a search failed reads as broken.

    One that walks at the thing and bumps reads as stupid, which is better --
    and is sometimes right, because the obstruction may be a shut door.
    """
    boxed = _wall_at((4, 3), (4, 5), (3, 4), (5, 4))
    route = pathing.Route()
    goal = _centre((4, 4))
    assert route.waypoint(boxed, _centre((1, 1)), goal, 0.0) == goal


def test_the_route_hands_back_one_cell_at_a_time():
    """A waypoint is the next cell, not the destination, or the plan is unused."""
    route = pathing.Route()
    step = route.waypoint(_open, _centre((1, 1)), _centre((8, 1)), 0.0)
    assert step == _centre((2, 1))


def test_townsfolk_walk_round_their_own_buildings(tmp_path):
    """The real world, not a fixture: a settlement is full of obstacles."""
    from chisurf.plugins.misc.games.lumis_quest.api import agents as agents_api
    from chisurf.plugins.misc.games.lumis_quest.api import npcs as npcs_api
    from chisurf.plugins.misc.games.lumis_quest.api.world import build_world

    root = tmp_path / "docs"
    section = root / "guides"
    section.mkdir(parents=True)
    names = [f"p{index}" for index in range(8)]
    for name in names:
        (section / f"{name}.md").write_text(f"# {name}\n\nProse.\n", encoding="utf-8")
    (section / "index.md").write_text(
        "# Guides\n\n## All\n\n```{toctree}\n\n" + "\n".join(names) + "\n```\n",
        encoding="utf-8")

    world = build_world(root)
    people = npcs_api.populate(world)
    society = agents_api.Society(world, people, seed=3)
    if not society.minds:
        pytest.skip("this small world has nobody with an inner life")

    for _ in range(400):
        society.step(1 / 30)
    # Nobody may end up standing inside a building, and at least one errand
    # must have needed a plan rather than a straight line.
    for mind in society.minds:
        assert not npcs_api._blocked(world, mind.npc.x, mind.npc.y)
    assert any(mind.route.searches for mind in society.minds)
