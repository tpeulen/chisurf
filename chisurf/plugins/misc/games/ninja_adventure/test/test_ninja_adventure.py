"""The Ninja Adventure port plays: map, crates, teleporter, combat, respawn.

The map itself is converted data (see
``build_tools/dev_utils/import_ninja_map.py``); what these pin is that the
game built on it is *playable* — the systems wired to the author's data
actually move, hit, teleport and recover.
"""

from __future__ import annotations

import json
import pathlib

import pytest

pytest.importorskip("wgpu")
pytest.importorskip("rendercanvas")

from qtpy.QtWidgets import QApplication  # noqa: E402

from chisurf.gui import chigame  # noqa: E402
from chisurf.gui.chigame import Damage, InputMap  # noqa: E402
from chisurf.gui.chigame.input import Action  # noqa: E402

from chisurf.plugins.misc.games.ninja_adventure import NinjaAdventure  # noqa: E402

DATA = pathlib.Path(__file__).resolve().parents[1] / "data"


@pytest.fixture()
def keys():
    """A quiescent controller."""
    return InputMap()


@pytest.fixture()
def game(keys):
    """A booted game, past the title screen."""
    instance = NinjaAdventure()

    def boot(index, host):
        if index == 0:
            host.keys.press(Action.CONFIRM)
            host.keys.release(Action.CONFIRM)

    chigame.capture(instance, size=(160, 96), frames=3, script=boot)
    assert instance.phase == "play"
    return instance


def step(game, keys, frames: int) -> None:
    """Advance the simulation without rendering.

    Parameters
    ----------
    game : NinjaAdventure
        The booted game.
    keys : InputMap
        The controller.
    frames : int
        Frames at 60 fps.
    """
    for _ in range(frames):
        game.update(1.0 / 60.0, keys)


# -- the converted map ------------------------------------------------------


def test_the_shipped_map_is_the_authors():
    """The game plays the reference's own village, not a stand-in.

    The counts are the importer's output for the checkout's
    ``map_village.tscn``; a map that drifted (a stale conversion, a hand
    edit) shows up here first.
    """
    data = json.loads((DATA / "map_village.json").read_text(encoding="utf-8"))
    cells = sum(len(layer["cells"]) for layer in data["layers"])
    assert cells == 3588
    assert len(data["characters"]) == 4
    assert len(data["teleporters"]) == 2
    assert {character["sheet"] for character in data["characters"]} == {
        "ninja_blue", "pig", "samurai_green", "samurai_blue",
    }


def test_the_ninja_starts_where_the_scene_puts_him(game):
    """NinjaBlue is authored at (64, 48) — the tilemap offset applied."""
    assert game.player.position[0] == pytest.approx(64.0)
    assert game.player.position[1] == pytest.approx(48.0)


def test_no_actor_spawns_inside_a_wall(game):
    """Everything that walks stands on walkable ground.

    The swamp's water is solid; an actor embedded in it can never move,
    which is exactly how the first hostile-samurai spawn shipped. Props
    (crates, grass) are excluded: the author places them on object tiles,
    and they do not move anyway.
    """
    for actor in game.actors:
        assert not game._solid_at(*actor.position), actor.alias


# -- play -------------------------------------------------------------------


def test_walking_moves_and_walls_hold(game, keys):
    """The ninja walks where the ground is clear and stops where it is not."""
    start = game.player.position.copy()
    keys.press(Action.DOWN)
    step(game, keys, 60)
    keys.release(Action.DOWN)
    assert game.player.position[1] > start[1] + 10.0

    # Straight down from the spawn the map ends in wall tiles; a long walk
    # must come to rest rather than leave the built map.
    keys.press(Action.DOWN)
    step(game, keys, 600)
    keys.release(Action.DOWN)
    game.player.velocity[:] = 0.0
    assert not game._solid_at(*game.player.position)


def test_a_swing_breaks_the_crate_in_front_of_her(game, keys):
    """The village's clutter is the reference's destroyable, and it breaks."""
    crate = next(d for d in game.destroyables if d.alias == "crate")
    game.player.position[:] = crate.position[0], crate.position[1] - 12.0
    game.player.velocity[:] = 0.0
    game.player_weapon.direction[:] = (0.0, 1.0)
    game.player_weapon.holder_position[:] = game.player.position
    game.player_weapon.cooldown = 0.0
    assert game.player_weapon.swing() is True
    game.player_weapon.timer = game.player_weapon.duration
    game.player.attack()
    hits = chigame.strike(
        game.player_weapon, game.enemies + game.destroyables, once=game.weapon_hits
    )
    assert crate in hits
    assert not crate.health.alive


def test_the_paired_teleporter_moves_her_and_locks_out(game, keys):
    """Walking onto the village teleporter lands her at its pair, offset the
    way the reference places arrivals, with the re-entry lockout armed."""
    portal = game._teleporters[0]
    game._teleport_lockout = 0.0
    game.transition.alpha = 0.0
    game.transition.finished = True
    game.player.position[:] = portal["position"]
    step(game, keys, 1)
    target = game._teleporters[1]["position"]
    assert game.player.position[1] == pytest.approx(
        target[1] - 25.0, abs=40.0
    )  # the portal's own direction
    assert game._teleport_lockout > 0.0
    # And the lockout holds: standing on the destination's own pair does
    # not immediately fire her back.
    game.player.position[:] = game._teleporters[1]["position"]
    step(game, keys, 10)
    assert game.player.position[0] == pytest.approx(game._teleporters[1]["position"][0], abs=30.0)


def test_the_swamp_samurai_fight_back(game, keys):
    """A hostile in sense range closes, swings, and hurts her for real."""
    enemy = game.enemies[0]
    ex, ey = enemy.position
    game.player.position[:] = ex, ey + 18.0
    game.player.velocity[:] = 0.0
    worst = game.player.health.current
    for _ in range(300):
        before = game.player.health.current
        step(game, keys, 1)
        worst = min(worst, game.player.health.current)
    assert worst < 6.0  # she was actually hit


def test_a_swung_club_kills_a_hostile(game, keys):
    """Her weapon does damage too, at its own rate."""
    enemy = game.enemies[0]
    game.player.position[:] = enemy.position[0], enemy.position[1] - 12.0
    game.player.velocity[:] = 0.0
    game.player_weapon.direction[:] = (0.0, 1.0)
    game.player_weapon.holder_position[:] = game.player.position
    game.player_weapon.cooldown = 0.0
    for frame in range(120):
        if frame % 20 == 0:
            keys.press(Action.CONFIRM)
        if frame % 20 == 5:
            keys.release(Action.CONFIRM)
        step(game, keys, 1)
    assert not enemy.health.alive


def test_death_fades_and_returns_her_to_the_spawn(game, keys):
    """Losing all hearts covers the screen and restores her at the start."""
    game.player.take_damage(Damage(99.0), (0.0, 0.0))
    step(game, keys, 90)
    assert game.player.health.current == game.player.health.maximum
    assert game.player.position[0] == pytest.approx(64.0)
    assert game.player.position[1] == pytest.approx(48.0)


def test_the_weather_answers_the_area_she_stands_in(game, keys):
    """The village's environment areas drive the engine weather."""
    area = next(
        env for env in game._environments if env["meteo"]
    )
    x0, y0, x1, y1 = area["rect"]
    game.player.position[:] = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    step(game, keys, 5)
    assert game.weather.active == set(area["meteo"])


def test_it_renders_the_authors_village(qapp, tmp_path):
    """The real pixels: the village composes and the palette is tile art,
    not the flat placeholder white of an unbound texture."""
    instance = NinjaAdventure()
    image = chigame.capture(instance, size=(640, 384), frames=90)
    chigame.save_png(image, tmp_path / "ninja_village.png")
    import numpy as np
    from PIL import Image

    pixels = np.asarray(Image.open(tmp_path / "ninja_village.png").convert("RGB"))
    colours = np.unique(pixels.reshape(-1, 3), axis=0)
    assert len(colours) > 20  # real art, not a placeholder wash
    green = (
        (pixels[..., 1] > pixels[..., 0])
        & (pixels[..., 1] > pixels[..., 2])
        & (pixels[..., 1] > 70)
    )
    assert green.mean() > 0.2  # the village's grass tones are present
    browns = (pixels[..., 0] > 140) & (pixels[..., 0] > pixels[..., 2]) & (pixels[..., 2] < 120)
    assert browns.mean() > 0.05  # its dirt and timber structures too
