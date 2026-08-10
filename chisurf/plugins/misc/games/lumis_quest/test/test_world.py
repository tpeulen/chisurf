"""The overworld is derived from the documentation, deterministically.

These tests build small worlds from fixtures rather than the installed corpus,
so they stay fast and do not change meaning when someone reviews a page. Two
tests do touch the real docs, because "it covers every page" is only worth
asserting against the real thing.
"""

from __future__ import annotations

import pathlib

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import tiles, world as world_api
from chisurf.plugins.misc.games.lumis_quest.api.world import (
    SCOUTED,
    SETTLED,
    WILD,
    Room,
    World,
    build_world,
)


def _docs(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a miniature documentation tree.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory.

    Returns
    -------
    pathlib.Path
        The docs root.
    """
    root = tmp_path / "docs"
    section = root / "guides"
    section.mkdir(parents=True)
    (section / "one.md").write_text("# One\n\nText.\n", encoding="utf-8")
    (section / "two.md").write_text("# Two\n\nText.\n", encoding="utf-8")
    (section / "index.md").write_text(
        "# Guides\n\n```{toctree}\n:maxdepth: 1\n\none\ntwo\n```\n", encoding="utf-8"
    )
    return root


def test_a_page_becomes_a_room(tmp_path):
    """Every linked page appears exactly once, with its own title."""
    world = build_world(_docs(tmp_path))
    titles = sorted(room.title for room in world.rooms)
    assert titles == ["One", "Two"]
    assert len(world.regions) == 1 and world.regions[0].name == "guides"


def test_the_layout_is_stable_across_builds(tmp_path):
    """Positions are seeded by path, so the map does not move between runs.

    ``hash()`` is salted per process; using it would reshuffle the world every
    time the game started.
    """
    docs = _docs(tmp_path)
    first = {room.address: room.position for room in build_world(docs).rooms}
    second = {room.address: room.position for room in build_world(docs).rooms}
    assert first == second


def test_adding_a_page_does_not_move_the_others(tmp_path):
    """A new page is a new building, not a reshuffle."""
    docs = _docs(tmp_path)
    before = {room.address: room.position for room in build_world(docs).rooms}

    (docs / "guides" / "three.md").write_text("# Three\n", encoding="utf-8")
    (docs / "guides" / "index.md").write_text(
        "# Guides\n\n```{toctree}\n:maxdepth: 1\n\none\ntwo\nthree\n```\n", encoding="utf-8"
    )
    after = {room.address: room.position for room in build_world(docs).rooms}

    assert set(after) - set(before) == {"docs/guides/three.md"}
    for address, position in before.items():
        assert after[address] == position, address


def test_an_unlinked_page_still_gets_a_room(tmp_path):
    """An orphan is the one page nothing links to, so the map must carry it.

    Leaving it out would make it the only thing the game can never send a
    player to -- exactly the page most in need of attention.
    """
    docs = _docs(tmp_path)
    (docs / "guides" / "orphan.md").write_text("# Orphan\n", encoding="utf-8")
    world = build_world(docs)
    assert "Orphan" in {room.title for room in world.rooms}
    assert "The Unlinked" in {village.name for village in world.villages}


def test_villages_do_not_overlap(tmp_path):
    """A village's pitch must follow its own height, not a fixed spacing.

    A 30-room village is six rows of rooms; at a fixed pitch it sat on top of
    the village below it.
    """
    docs = tmp_path / "docs"
    section = docs / "reference"
    section.mkdir(parents=True)
    entries = []
    for index in range(60):
        (section / f"p{index:02d}.md").write_text(f"# Page {index}\n", encoding="utf-8")
        entries.append(f"p{index:02d}")
    groups = "\n\n".join(
        "## Group %d\n\n```{toctree}\n\n%s\n```" % (g, "\n".join(entries[g * 20:(g + 1) * 20]))
        for g in range(3)
    )
    (section / "index.md").write_text(f"# Reference\n\n{groups}\n", encoding="utf-8")

    world = build_world(docs)
    assert len(world.villages) >= 2
    positions = [room.position for room in world.rooms]
    assert len(set(positions)) == len(positions), "two rooms share a position"


def test_review_state_maps_to_three_distinct_world_states():
    """Absent, ai-reviewed and reviewed must not collapse into each other."""
    assert len({WILD, SCOUTED, SETTLED}) == 3
    village = world_api.Village(name="v", rooms=[
        Room("a", pathlib.Path("a"), "a", 1, SETTLED, (0.0, 0.0)),
        Room("b", pathlib.Path("b"), "b", 1, WILD, (1.0, 0.0)),
    ])
    assert village.prosperity == pytest.approx(0.5)


def test_remoteness_rewards_review_debt_over_depth():
    """The gradient must point at unreviewed pages, not merely deep ones."""
    deep_but_settled = Room("a", pathlib.Path("a"), "a", 5, SETTLED, (0.0, 0.0))
    shallow_but_wild = Room("b", pathlib.Path("b"), "b", 0, WILD, (0.0, 0.0))
    assert shallow_but_wild.remoteness > deep_but_settled.remoteness


def test_an_empty_world_is_safe_to_query():
    """The helpers the map view depends on must not raise on nothing."""
    world = World()
    assert world.bounds() == (0.0, 0.0, 0.0, 0.0)
    assert world.nearest_room((0.0, 0.0)) is None
    assert world.region_at(0.0, 0.0) is None
    assert world.counts() == {
        WILD: 0, world_api.WITHERED: 0, SCOUTED: 0, SETTLED: 0
    }


def test_nearest_room_finds_the_closest_building():
    """What the HUD names as "here"."""
    world = World()
    region = world_api.Region(name="r", title="R")
    region.villages.append(world_api.Village(name="v", rooms=[
        Room("near", pathlib.Path("a"), "a", 1, WILD, (1, 1)),
        Room("far", pathlib.Path("b"), "b", 1, WILD, (40, 40)),
    ]))
    world.regions.append(region)
    assert world.nearest_room((0.0, 0.0)).title == "near"


def test_the_world_is_a_painted_grid(tmp_path):
    """A map is tiles you collide with, not markers floating on nothing."""
    world = build_world(_docs(tmp_path))
    assert world.width > 0 and world.height > 0
    assert world.array.shape == (world.height, world.width)

    kinds = {tile for row in world.grid for tile in row}
    # The pieces that make it a place rather than a diagram.
    for expected in (tiles.WATER, tiles.GRASS, tiles.WALL, tiles.GATE, tiles.BUILDING):
        assert expected in kinds, tiles.NAMES[expected]


def test_water_and_walls_block_but_gates_do_not(tmp_path):
    """Bounds are real: the world is not an open plane you drift across."""
    world = build_world(_docs(tmp_path))

    # Outside the grid must read as solid, or a walker leaves the world.
    assert world.blocked(-10.0, -10.0)
    assert world.blocked(world.width * tiles.TILE + 10.0, 0.0)

    village = world.villages[0]
    col, row, width, height = village.rect
    corner = ((col + 0.5) * tiles.TILE, (row + 0.5) * tiles.TILE)
    assert world.blocked(*corner), "a compound wall must stop a walker"

    gate_col, gate_row = village.gate
    gate = ((gate_col + 0.5) * tiles.TILE, (gate_row + 0.5) * tiles.TILE)
    assert not world.blocked(*gate), "the gate is the way in"

    building = world.rooms[0]
    assert world.blocked(*building.position), "you stand in front of a building, not inside it"


def test_spawn_is_somewhere_you_can_stand(tmp_path):
    """A start position inside a wall is a game that never begins."""
    world = build_world(_docs(tmp_path))
    assert not world.blocked(*world.spawn())


def test_lands_are_named_as_places_not_folders(tmp_path):
    """`reference` is a directory; The Great Library is somewhere to go."""
    from chisurf.plugins.misc.games.lumis_quest.api.names import region_name

    assert region_name("reference")[0] == "The Great Library"
    assert region_name("guides")[0] == "The Pilgrim Road"
    # An unknown directory still arrives with a name rather than a slug.
    generated, _ = region_name("some_new_section")
    assert generated.startswith("The ") and "_" not in generated

    world = build_world(_docs(tmp_path))
    assert all(region.title.startswith("The ") for region in world.regions)


@pytest.mark.parametrize("directory", ["concepts", "guides", "fundamentals"])
def test_the_real_corpus_is_covered_page_for_page(directory):
    """Every non-index page in a section becomes a room.

    A page missing from the world is a page the game can never send anyone to,
    and nothing else would notice.
    """
    from chisurf.plugins.core.help.api import toc

    docs = toc.docs_root()
    section = docs / directory
    if not section.is_dir():
        pytest.skip(f"{directory} is not present in this install")

    on_disk = {
        path.resolve()
        for path in section.rglob("*")
        if path.suffix in {".md", ".rst"} and not path.name.startswith("index.")
    }
    world = build_world(docs)
    in_world = {
        room.path.resolve()
        for region in world.regions
        if region.name == directory
        for room in region.rooms
    }
    assert on_disk - in_world == set(), sorted(str(p) for p in (on_disk - in_world))[:5]
