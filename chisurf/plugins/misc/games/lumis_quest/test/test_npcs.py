"""The world is inhabited, and the population means something."""

from __future__ import annotations

import pathlib

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import npcs, tiles
from chisurf.plugins.misc.games.lumis_quest.api.world import SETTLED, WILD, build_world


def _docs(tmp_path: pathlib.Path) -> pathlib.Path:
    """A small documentation tree.

    Returns
    -------
    pathlib.Path
        The docs root.
    """
    root = tmp_path / "docs"
    section = root / "guides"
    section.mkdir(parents=True)
    names = [f"p{index}" for index in range(6)]
    for name in names:
        (section / f"{name}.md").write_text(f"# {name}\n\nProse here.\n", encoding="utf-8")
    # One heading, so the pages form a single village. A flat toctree makes a
    # village per page, which would give every settled page a 100%-prosperous
    # village of one and hide what prosperity is for.
    (section / "index.md").write_text(
        "# Guides\n\n## Everything\n\n```{toctree}\n\n" + "\n".join(names) + "\n```\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def world(tmp_path):
    """A small world.

    Returns
    -------
    World
        Built from a temporary corpus.
    """
    built = build_world(_docs(tmp_path))
    # A temporary corpus lies outside the tracked directories, so its pages come
    # back *settled* rather than wild. These tests are about state, so they set
    # it rather than inheriting whatever the review system says about a tmpdir.
    for room in built.rooms:
        room.state = WILD
    return built


def test_a_settled_page_becomes_a_villager(world):
    """The population of a village *is* how much of it somebody has read.

    That is the design: reviewing a page turns a wild room into a villager, so
    a ghost town is a section nobody has touched.
    """
    for room in world.rooms[:3]:
        room.state = SETTLED
    people = npcs.populate(world)
    villagers = [n for n in people if n.kind == "villager"]
    assert len(villagers) == 3
    assert {n.address for n in villagers} == {r.address for r in world.rooms[:3]}


def test_an_unread_page_has_nobody_outside_it(world):
    """A dark building is dark."""
    people = npcs.populate(world)
    assert [n for n in people if n.kind == "villager"] == []


def test_the_world_gets_animals_and_beasts(world):
    """Not everything on the map is a metric; some of it just lives there."""
    people = npcs.populate(world)
    kinds = {n.kind for n in people}
    assert "animal" in kinds
    assert people, "an empty world is a diagram"


def test_nobody_is_spawned_inside_a_wall(world):
    """A villager in a wall is not standing anywhere."""
    for room in world.rooms:
        room.state = SETTLED
    for npc in npcs.populate(world):
        assert not npcs._blocked(world, npc.x, npc.y), f"{npc.kind} {npc.name}"


def test_the_population_is_the_same_on_every_run(world):
    """A village whose people rearrange themselves is not somewhere you can
    come to know."""
    for room in world.rooms[:2]:
        room.state = SETTLED
    first = [(n.kind, round(n.x, 3), round(n.y, 3), n.line) for n in npcs.populate(world)]
    second = [(n.kind, round(n.x, 3), round(n.y, 3), n.line) for n in npcs.populate(world)]
    assert first == second


def test_villagers_stand_still_and_animals_do_not(world):
    """A keeper keeps their page; an animal crops the grass."""
    for room in world.rooms[:2]:
        room.state = SETTLED
    people = npcs.populate(world)
    villager = next(n for n in people if n.kind == "villager")
    movers = [n for n in people if n.kind in ("animal", "beast")]
    if not movers:
        pytest.skip("this small world spawned nothing that wanders")

    fixed = (villager.x, villager.y)
    before = [(n.x, n.y) for n in movers]
    for step in range(60):
        npcs.update(people, world, 1 / 30, step / 30.0, near=(villager.x, villager.y),
                    radius=1e9)
    assert (villager.x, villager.y) == fixed
    assert any((n.x, n.y) != was for n, was in zip(movers, before))


def test_a_wanderer_stays_near_home_and_out_of_walls(world):
    """It wanders; it does not emigrate, and it does not walk into a building."""
    people = npcs.populate(world)
    movers = [n for n in people if n.kind in ("animal", "beast")]
    if not movers:
        pytest.skip("this small world spawned nothing that wanders")
    for step in range(400):
        npcs.update(people, world, 1 / 30, step / 30.0, near=(movers[0].x, movers[0].y),
                    radius=1e9)
    for npc in movers:
        assert abs(npc.x - npc.home[0]) <= npc.radius + tiles.TILE
        assert abs(npc.y - npc.home[1]) <= npc.radius + tiles.TILE
        assert not npcs._blocked(world, npc.x, npc.y)


def test_only_nearby_inhabitants_are_stepped(world):
    """A hundred creatures nobody can see do not need to breathe."""
    people = npcs.populate(world)
    movers = [n for n in people if n.kind in ("animal", "beast")]
    if not movers:
        pytest.skip("this small world spawned nothing that wanders")
    far = movers[0]
    before = (far.x, far.y)
    npcs.update(people, world, 1 / 30, 1.0, near=(far.x + 5000.0, far.y), radius=100.0)
    assert (far.x, far.y) == before


def test_you_can_only_speak_to_someone_within_reach(world):
    """Otherwise the whole village talks at once."""
    for room in world.rooms[:1]:
        room.state = SETTLED
    people = npcs.populate(world)
    villager = next(n for n in people if n.kind == "villager")
    assert npcs.nearest(people, villager.x, villager.y) is villager
    assert npcs.nearest(people, villager.x + 900.0, villager.y) is None


def test_a_villager_in_a_neglected_village_says_so(world):
    """A ghost town knows it is one."""
    world.rooms[0].state = SETTLED
    people = npcs.populate(world)
    villager = next(n for n in people if n.kind == "villager")
    assert villager.line in npcs.STRUGGLING, villager.line

    for room in world.rooms:
        room.state = SETTLED
    proud = next(n for n in npcs.populate(world) if n.kind == "villager")
    assert proud.line in npcs.GREETINGS
