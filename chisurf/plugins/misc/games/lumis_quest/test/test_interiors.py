"""A building is one tile outside and a room when you are in it."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.misc.games.lumis_quest.api import interiors, screens
from chisurf.plugins.misc.games.lumis_quest.api import tiles as T


@pytest.mark.parametrize("kind", sorted(interiors.SIZES))
def test_every_room_is_walled_with_one_way_out(kind):
    """A room you can walk out of the side of is not a room."""
    room = interiors.build(f"k:{kind}", kind, "Somewhere")
    width, height = room.size

    exits = [(col, row) for row in range(height) for col in range(width)
             if room.tile_at(col, row) == T.EXIT]
    assert exits == [room.door], "exactly one way out, and it is the door"

    for col in range(width):
        assert T.is_blocking(room.tile_at(col, 0)), col
        assert room.tile_at(col, height - 1) in (T.IWALL, T.EXIT), col
    for row in range(height):
        assert T.is_blocking(room.tile_at(row * 0, row)), row
        assert T.is_blocking(room.tile_at(width - 1, row)), row

    # Outside the grid reads as wall, so nothing can leave by walking off it.
    assert T.is_blocking(room.tile_at(-1, 0))
    assert T.is_blocking(room.tile_at(width, height))


@pytest.mark.parametrize("kind", sorted(interiors.SIZES))
def test_a_room_is_furnished_from_what_it_is_for(kind):
    """A scatter of crates is not a tavern."""
    room = interiors.build(f"k:{kind}", kind, "Somewhere")
    present = set(np.unique(room.grid).tolist())
    wanted = {
        "house": {T.BED, T.HEARTH, T.SHELF},
        "tavern": {T.COUNTER, T.TABLE, T.BARREL},
        "shop": {T.COUNTER, T.SHELF},
        "smithy": {T.ANVIL, T.HEARTH},
        "shrine": {T.ALTAR, T.RUG},
        "hall": {T.ALTAR, T.RUG},
    }[kind]
    assert wanted <= present, (kind, wanted - present)
    assert room.spots, "somebody has to be able to stand in it"
    for col, row in room.spots:
        assert not T.is_blocking(room.tile_at(col, row)), (kind, col, row)


def test_the_door_is_reachable_from_inside():
    """Furniture in front of the only exit would trap the player."""
    for kind in interiors.SIZES:
        room = interiors.build(f"k:{kind}", kind, "Somewhere")
        col, row = room.door
        assert not T.is_blocking(room.tile_at(col, row - 1)), kind


def test_a_room_is_the_same_room_every_visit():
    """Somewhere you have been has to be somewhere you can come back to."""
    once = interiors.build("page:docs/a.md", "house", "A")
    twice = interiors.build("page:docs/a.md", "house", "A")
    assert np.array_equal(once.grid, twice.grid)
    other = interiors.build("page:docs/b.md", "house", "B")
    assert other.size == once.size


def test_a_room_is_bigger_than_the_tile_it_is_entered_from():
    """The whole trick: the exterior is a doorway, not a floor plan."""
    for kind, (width, height) in interiors.SIZES.items():
        assert width * height > 100, kind
        # ...and it fits on one 16-bit screen, so a room needs no scrolling.
        assert width <= screens.COLS and height <= screens.ROWS, kind


def test_an_unknown_kind_is_a_house_rather_than_a_crash():
    """A corpus can name anything; the room generator cannot refuse."""
    room = interiors.build("odd", "not-a-kind", "Odd")
    assert room.kind == "house"


def test_a_room_is_authored_as_ascii_art_and_replaced_with_artwork():
    """A map you cannot read in a diff is a map nobody can review.

    The characters are a stand-in: the file says where the bar is, and the
    atlas says what a bar looks like.
    """
    for kind in interiors.SIZES:
        path = interiors.ROOM_DIR / f"{kind}.txt"
        assert path.is_file(), kind
        lines = [line for line in path.read_text(encoding="utf-8").splitlines()
                 if line and not line.lstrip().startswith("# ")]
        assert len({len(line) for line in lines}) == 1, f"{kind} is ragged"
        assert set("".join(lines)) <= set(interiors.LEGEND), kind
        assert "+" in "".join(lines), f"{kind} has no way out"
        assert interiors.SPOT in "".join(lines), f"{kind} has nowhere to stand"

        room = interiors.build(f"k:{kind}", kind)
        assert room.size == (len(lines[0]), len(lines))
