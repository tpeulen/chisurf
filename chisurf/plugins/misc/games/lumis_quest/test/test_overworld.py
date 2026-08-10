"""Walking the overworld, headlessly."""

from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("wgpu")
pytest.importorskip("rendercanvas")

from chisurf.gui import chigame  # noqa: E402
from chisurf.gui.chigame.input import Action  # noqa: E402
from chisurf.plugins.misc.games.lumis_quest.api.world import (  # noqa: E402
    SETTLED,
    WILD,
    Region,
    Room,
    Village,
    World,
)
from chisurf.plugins.misc.games.lumis_quest.gui.overworld import (  # noqa: E402
    OverworldGame,
)


def _tiny_world() -> World:
    """A three-room world, so tests never touch the installed corpus.

    Returns
    -------
    World
        Two villages in one region.
    """
    world = World()
    region = Region(name="guides", title="Guides")
    region.villages.append(
        Village(name="First", position=(0.0, 0.0), rooms=[
            Room("Alpha", pathlib.Path("a.md"), "docs/a.md", 1, WILD, (0.0, 0.0)),
            Room("Beta", pathlib.Path("b.md"), "docs/b.md", 1, SETTLED, (44.0, 0.0)),
        ])
    )
    region.villages.append(
        Village(name="Second", position=(300.0, 0.0), rooms=[
            Room("Gamma", pathlib.Path("c.md"), "docs/c.md", 2, WILD, (300.0, 0.0)),
        ])
    )
    world.regions.append(region)
    return world


@pytest.fixture
def game(qapp):
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
    instance = OverworldGame(world=_tiny_world())
    chigame.GameHost(instance, context, with_text=False, with_audio=False)
    return instance


def test_iris_walks(game):
    """The pad moves Iris and the camera follows."""
    start = list(game.iris)
    game.host.keys.press(Action.RIGHT)
    for _ in range(20):
        game.update(1 / 60, game.host.keys)
    assert game.iris[0] > start[0]
    assert game.host.camera.center[0] > start[0]


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
    game.iris = [1.0, 1.0]
    assert game.here.title == "Alpha"
    game.iris = [299.0, 1.0]
    assert game.here.title == "Gamma"


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


def test_it_renders(qapp):
    """A frame comes out with the world drawn on it."""
    try:
        frame = chigame.capture(
            OverworldGame(world=_tiny_world()), size=(320, 240), frames=3, with_audio=False
        )
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    assert frame.shape == (240, 320, 4)
