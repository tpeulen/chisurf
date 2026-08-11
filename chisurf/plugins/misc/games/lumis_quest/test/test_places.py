"""A settlement is a place with a middle, and there is a country underneath it."""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.misc.games.lumis_quest.api import darkworld, places, tiers
from chisurf.plugins.misc.games.lumis_quest.api import tiles as T
from chisurf.plugins.misc.games.lumis_quest.api.world import build_world


def _docs(tmp_path: pathlib.Path, sizes=(2, 7, 16)) -> pathlib.Path:
    """A corpus with a small, a medium and a large section, one per kind."""
    root = tmp_path / "docs"
    for index, count in enumerate(sizes):
        section = root / f"s{index}"
        section.mkdir(parents=True)
        names = [f"p{page}" for page in range(count)]
        for name in names:
            (section / f"{name}.md").write_text(f"# {name}\n\nProse.\n", encoding="utf-8")
        (section / "index.md").write_text(
            "# Group\n\n```{toctree}\n\n" + "\n".join(names) + "\n```\n",
            encoding="utf-8",
        )
    return root


@pytest.fixture
def world(tmp_path):
    """A built world over that corpus."""
    return build_world(_docs(tmp_path))


def test_a_section_of_three_pages_is_not_the_same_place_as_one_of_twenty():
    """Three sizes, because a corpus has three sizes of section."""
    assert places.kind_for(2) == "hamlet"
    assert places.kind_for(5) == "village"
    assert places.kind_for(20) == "town"
    assert places.kind_for(places.HAMLET_MAX + 1) == "village"
    assert places.kind_for(places.VILLAGE_MAX + 1) == "town"
    assert places.kind_for(1, warden=True) == "town", "somebody built the hall"


def test_a_settlement_has_a_middle_and_things_arranged_around_it():
    """A wall around a grid of boxes is a housing estate."""
    plan = places.plan(14, "town")
    assert plan.plaza[2] > 0 and plan.plaza[3] > 0
    assert len(plan.room_cells) == 14
    assert set(plan.premises) >= {T.TAVERN, T.SHOP, T.SMITHY, T.SHRINE}
    assert plan.gate[1] == plan.height - 1, "the gate is in the south wall"
    # Nothing is stacked on anything.
    taken = list(plan.room_cells) + list(plan.premises.values()) + plan.gardens
    assert len(set(taken)) == len(taken)


def test_a_town_is_painted_with_what_it_was_planned_to_have(world):
    """The plan and the paint agree, which is not free -- they did not once."""
    towns = [village for village in world.villages if village.kind == "town"]
    assert towns
    for village in towns:
        for key in ("well", "tavern", "shop"):
            assert key in village.premises, (village.place, key)
            col, row = village.premises[key]
            assert world.tile_at(col, row) != T.FLOOR, key
        assert world.tile_at(*village.gate) in (T.GATE, T.GRASS)
        assert world.tile_at(*village.clinic) == T.CLINIC


def test_a_compound_is_sealed_except_at_its_gate(world):
    """Iris walked straight through an upgraded town's wall once. Never again."""
    for village in world.villages:
        if village.kind == "hamlet":
            continue  # a fence with a gap in it, on purpose
        col, row, width, height = village.rect
        edges = (
            [(x, row) for x in range(col, col + width)]
            + [(x, row + height - 1) for x in range(col, col + width)]
            + [(col, y) for y in range(row, row + height)]
            + [(col + width - 1, y) for y in range(row, row + height)]
        )
        holes = [spot for spot in edges
                 if world.tile_at(*spot) not in (T.WALL, T.GATE)]
        assert holes == [], (village.place, holes[:3])


def test_every_settlement_is_named_as_a_place_and_known_for_a_section(world):
    """Nobody says they are walking to Core Methods."""
    for village in world.villages:
        assert village.place and village.place != village.name
        assert village.name in village.label and village.place in village.label
    assert len({village.place for village in world.villages}) > 1


def test_every_warden_has_a_seat_and_a_hall_to_stand_in(world):
    """A Warden with nowhere to be is a fight nobody can find."""
    seated = {village.warden for village in world.villages if village.warden}
    assert seated == {warden.key for warden in tiers.WARDENS}
    for village in world.villages:
        if village.warden:
            assert "hall" in village.premises
            assert world.tile_at(*village.premises["hall"]) == T.HALL


def test_a_land_has_water_stone_and_a_way_down(world):
    """A map with none of that is a texture."""
    grid = world.array
    for kind in (T.WATER, T.SAND, T.TREE, T.ROAD):
        assert int(np.count_nonzero(grid == kind)) > 0, T.NAMES[kind]
    assert world.caves, "every land that can hold a crossing gets one"
    for col, row in world.caves:
        assert world.tile_at(col, row) == T.CAVE
        assert not T.is_blocking(T.CAVE), "a cave mouth is a door"


def test_the_dark_manifold_is_this_map_with_the_light_taken_out(world):
    """Same geography, and that is the trick -- you know the way already."""
    assert world.dark.shape == world.array.shape
    lit, dark = world.array, world.dark
    assert int(np.count_nonzero(dark == T.ASH)) > 0
    assert int(np.count_nonzero(dark == T.TAR)) > 0
    assert int(np.count_nonzero(dark == T.RUIN)) > 0
    assert int(np.count_nonzero(dark == T.CLINIC)) == 0, "nobody is keeping anything"

    # The bones stay: a road is a road on both sides.
    roads = lit == T.ROAD
    assert np.array_equal(dark[roads], lit[roads])
    # And every cave is a way back up.
    for col, row in world.caves:
        assert world.tile_at(col, row, dark=True) == T.RIFT


def test_the_shadow_transform_is_a_lookup_and_leaves_nothing_undefined():
    """Crossing over has to be instant, so it cannot be a rebuild."""
    grid = np.arange(0, 35, dtype=np.uint8).reshape(5, 7)
    shadow = darkworld.shadow(grid)
    assert shadow.shape == grid.shape and shadow.dtype == np.uint8
    assert darkworld.shadow(np.zeros((0, 0), np.uint8)).size == 0
    for lit, dark in darkworld.SHADOW.items():
        assert int(darkworld.shadow(np.array([[lit]], np.uint8))[0, 0]) == dark


def test_there_is_one_built_thing_in_the_dark_and_it_is_hers(world):
    """The tower is the only thing down there that was raised rather than left."""
    door = darkworld.raise_tower(world)
    assert door is not None
    col, row = door
    assert int(world.dark[row, col]) == T.GATE
    assert int(np.count_nonzero(world.dark == T.HALL)) == 1
