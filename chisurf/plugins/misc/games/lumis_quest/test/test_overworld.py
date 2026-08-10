"""Walking the overworld, headlessly."""

from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("wgpu")
pytest.importorskip("rendercanvas")

from chisurf.gui import chigame  # noqa: E402
from chisurf.gui.chigame.input import Action  # noqa: E402
from chisurf.plugins.misc.games.lumis_quest.api import tiles  # noqa: E402
from chisurf.plugins.misc.games.lumis_quest.api.world import build_world  # noqa: E402
from chisurf.plugins.misc.games.lumis_quest.gui.overworld import (  # noqa: E402
    OverworldGame,
)


def _docs(tmp_path: pathlib.Path) -> pathlib.Path:
    """A miniature documentation tree, so tests never build the real corpus.

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
    names = [f"p{index}" for index in range(8)]
    for name in names:
        (section / f"{name}.md").write_text(f"# {name.upper()}\n", encoding="utf-8")
    listing = "\n".join(names)
    (section / "index.md").write_text(
        f"# Guides\n\n```{{toctree}}\n:maxdepth: 1\n\n{listing}\n```\n", encoding="utf-8"
    )
    return root


@pytest.fixture
def game(qapp, tmp_path):
    """An overworld on a tiny world, wired to a headless host.

    Returns
    -------
    OverworldGame
        Ready to step.
    """
    try:
        context = chigame.create_offscreen(size=(240, 180))
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    instance = OverworldGame(world=build_world(_docs(tmp_path)))
    chigame.GameHost(instance, context, with_text=False, with_audio=False)
    return instance


def test_iris_walks(game):
    """The pad moves Iris and the camera follows."""
    start = list(game.iris)
    game.host.keys.press(Action.DOWN)
    for _ in range(20):
        game.update(1 / 60, game.host.keys)
    assert game.iris[1] > start[1]
    assert game.host.camera.center[1] > start[1]


def test_iris_cannot_walk_through_a_wall(game):
    """The world has bounds, and they are the tiles themselves."""
    village = game.world.villages[0]
    col, row, width, height = village.rect
    # Stand just below the south wall, off to one side of the gate.
    game.iris = [(col + 1.5) * tiles.TILE, (row + height + 0.5) * tiles.TILE]
    before = list(game.iris)

    game.host.keys.press(Action.UP)
    for _ in range(120):
        game.update(1 / 60, game.host.keys)
    assert game.iris[1] >= before[1] - tiles.TILE, "she walked through the compound wall"


def test_iris_cannot_leave_the_world(game):
    """Walking hard at the edge must not put her outside the grid.

    She starts where the game starts her -- a land is ringed by water, so
    teleporting her into the moat first would only prove she cannot swim.
    """
    game.host.keys.press(Action.LEFT)
    game.host.keys.press(Action.UP)
    for _ in range(600):
        game.update(1 / 60, game.host.keys)
    assert 0.0 <= game.iris[0] <= game.world.width * tiles.TILE
    assert 0.0 <= game.iris[1] <= game.world.height * tiles.TILE
    assert not game.world.blocked(*game.iris), "she ended up inside something solid"


def test_the_story_advances_from_the_world_not_from_a_button(game):
    """A beat completes because the corpus shows it, not because of input."""
    from chisurf.plugins.misc.games.lumis_quest.api.story import ACT_ONE

    assert game.story.current is not None
    game.update(1 / 60, game.host.keys)
    assert game.story.current.key != ACT_ONE[0].key, "arrival completes on arriving"

    game.story.choose("clarity")
    assert game.story.order["name"] == "The Order of Clarity"
    with pytest.raises(KeyError):
        game.story.choose("nonsense")


def test_diagonal_movement_is_not_faster(game):
    """Normalising the axis stops diagonals being a speed exploit."""
    game.iris = [0.0, 0.0]
    game.host.keys.press(Action.RIGHT)
    for _ in range(30):
        game.update(1 / 60, game.host.keys)
    straight = abs(game.iris[0])

    game.host.keys.release(Action.RIGHT)
    game.host.keys.end_frame()
    game.iris = [0.0, 0.0]
    game.host.keys.press(Action.RIGHT)
    game.host.keys.press(Action.DOWN)
    for _ in range(30):
        game.update(1 / 60, game.host.keys)
    diagonal = (game.iris[0] ** 2 + game.iris[1] ** 2) ** 0.5
    assert diagonal == pytest.approx(straight, rel=0.02)


def test_lumi_follows_without_overlapping(game):
    """The companion trails rather than sticking to Iris."""
    game.host.keys.press(Action.RIGHT)
    for _ in range(90):
        game.update(1 / 60, game.host.keys)
    gap = ((game.iris[0] - game.lumi[0]) ** 2 + (game.iris[1] - game.lumi[1]) ** 2) ** 0.5
    assert 5.0 < gap < 60.0, gap


def test_the_nearest_room_is_reported(game):
    """The HUD names where you are standing."""
    first = game.world.rooms[0]
    game.iris = list(first.position)
    assert game.here is first

    last = game.world.rooms[-1]
    game.iris = list(last.position)
    assert game.here is last


def test_the_land_is_named_where_she_stands(game):
    """Standing on a land reports its fantasy name, not the directory."""
    game.iris = list(game.world.rooms[0].position)
    assert game.land is not None
    assert game.land.title.startswith("The ")


def test_menu_toggles_a_map_that_fits_the_world(game):
    """The map view frames everything rather than guessing a height."""
    game.host.keys.tap(Action.MENU)
    # `update` is driven directly here, so this test owns the frame boundary
    # that GameHost.frame() would otherwise call. Without it `just_pressed`
    # stays latched and the toggle fires on every iteration.
    for step in range(120):
        game.update(1 / 30, game.host.keys)
        game.host.keys.end_frame()
        assert game.show_map is True, f"toggled off again at step {step}"
    assert game.show_map is True

    min_x, min_y, max_x, max_y = game.world.bounds()
    width, height = game.host.ctx.size
    aspect = width / height
    assert game.host.camera.height >= (max_y - min_y)
    assert game.host.camera.height * aspect >= (max_x - min_x)


def test_the_shoulders_zoom_within_bounds(game):
    """Zoom is clamped, so the view cannot be lost."""
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import VIEW_MAX, VIEW_MIN

    game.host.keys.press(Action.SHOULDER_L)
    for _ in range(600):
        game.update(1 / 60, game.host.keys)
    assert game.view_height <= VIEW_MAX

    game.host.keys.release(Action.SHOULDER_L)
    game.host.keys.press(Action.SHOULDER_R)
    for _ in range(600):
        game.update(1 / 60, game.host.keys)
    assert game.view_height >= VIEW_MIN


def test_it_renders(qapp, tmp_path):
    """A frame comes out with the world drawn on it."""
    try:
        frame = chigame.capture(
            OverworldGame(world=build_world(_docs(tmp_path))), size=(320, 240),
            frames=3, with_audio=False
        )
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    assert frame.shape == (240, 320, 4)
