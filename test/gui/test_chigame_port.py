"""The NinjaAdventure port: atlas, actors, behaviors, tiles, rooms, weather.

These cover the systems mined from the reference game (see
``okf/subsystems/chigame.md``). Most are pure simulation logic and need no GPU;
the render-side ones reuse the offscreen capture path the engine's other tests
use.
"""

from __future__ import annotations

import pathlib

import random

import numpy as np
import pytest

from chisurf.gui.chigame.actors import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    Actor,
    Damage,
    Destroyable,
    Health,
    Team,
    Weapon,
    direction_column,
    strike,
)
from chisurf.gui.chigame.atlas import TextureAtlas, load_pixel_pack
from chisurf.gui.chigame.behavior import Follow, Patrol, Sense, wander
from chisurf.gui.chigame.camera import RoomCamera
from chisurf.gui.chigame.fx import Transition, Weather
from chisurf.gui.chigame.tilemap import TileMap


# -- atlas ----------------------------------------------------------------


class _FakeDevice:
    """Records texture creation; the upload sink is a no-op."""

    class _Queue:
        @staticmethod
        def write_texture(*args, **kwargs):
            return None

    queue = _Queue()

    def create_texture(self, **kwargs):
        return kwargs


@pytest.fixture()
def atlas():
    """The shipped pixel pack, packed against a fake device (fresh each test:
    an atlas refuses to slice after it has built)."""
    root = pathlib.Path(__file__).parents[2] / "chisurf" / "gui" / "chigame" / "assets" / "pixel"
    return load_pixel_pack(root, _FakeDevice())


def test_the_pack_packs_every_image(atlas):
    assert len([n for n in atlas.frames if ":" not in n]) == 41
    width, height = atlas.size
    assert width <= 2048 and height <= 2048


def test_a_grid_slice_stays_inside_its_sheet(atlas):
    hero = atlas.slice_grid("characters/hero", 4, 7, prefix="hero")
    assert len(hero) == 28
    sheet = atlas.frame("characters/hero")
    atlas._build()
    for frame in hero:
        assert frame.x0 >= sheet.x0
        assert frame.y0 >= sheet.y0
        assert frame.x0 + frame.width <= sheet.x0 + sheet.width
        assert frame.y0 + frame.height <= sheet.y0 + sheet.height


def test_duplicate_names_are_refused(atlas):
    atlas.slice_grid("ui/hearts", 5, 1, prefix="hearts")
    with pytest.raises(ValueError):
        atlas.slice_grid("ui/hearts", 5, 1, prefix="hearts")


# -- sheet animation ------------------------------------------------------


def test_direction_quantises_to_sheet_columns():
    assert direction_column((0.0, 1.0)) == DOWN
    assert direction_column((0.0, -1.0)) == UP
    assert direction_column((-1.0, 0.0)) == LEFT
    assert direction_column((1.0, 0.0)) == RIGHT
    assert direction_column((1.0, -0.1)) == RIGHT


def test_the_walk_cycle_advances_six_cells_a_second():
    actor = Actor(alias="hero")
    poses = []
    for _ in range(12):
        actor.move_vector[:] = (0.0, 1.0)
        actor.update(1.0 / 12.0)
        poses.append(actor.anim.pose())
    rows = [int(p.split(",")[0]) for p in poses]
    # Half a cell a frame: 0.5, 1.0, 1.5, ... reads 0,1,1,2,2,3,3,0,0,1,1,2.
    assert rows == [0, 1, 1, 2, 2, 3, 3, 0, 0, 1, 1, 2]
    assert all(p.endswith(",0") for p in poses)


def test_a_dead_actor_stays_on_the_downed_row():
    actor = Actor(alias="hero")
    actor.anim.anim = "dead"
    actor.anim.advance(1.0, moving=True)
    assert actor.anim.pose() == "6,0"


def test_an_animal_sheet_flips_instead_of_turning():
    actor = Actor(alias="beast", two_column=True)
    actor.move_vector[:] = (-1.0, 0.0)
    actor.update(0.016)
    assert bool(actor.anim.flip) is True
    assert actor.anim.pose() in {"0,0", "1,0"}


# -- movement and collision ----------------------------------------------


def test_velocity_ramps_and_settles_like_the_reference():
    actor = Actor(speed=100.0)
    actor.move_vector[:] = (1.0, 0.0)
    actor.update(0.016)
    assert 0.0 < actor.velocity[0] < 100.0
    for _ in range(60):
        actor.update(0.016)
    assert actor.velocity[0] == pytest.approx(100.0)
    actor.move_vector[:] = 0.0
    for _ in range(60):
        actor.update(0.016)
    assert actor.velocity[0] == pytest.approx(0.0, abs=1.0)


def test_a_wall_stops_the_body_but_slides_along_it():
    grid = np.zeros((12, 12), dtype=np.int32)
    grid[:, 5] = 1  # a vertical wall at column 5
    uv = np.zeros((2, 4), dtype=np.float32)
    tiles = TileMap(grid, uv, tile=16.0, solid_ids=[1])
    actor = Actor(position=(4.5 * 16.0, 6 * 16.0), solid=tiles.solid_at, speed=200.0)
    actor.move_vector[:] = (1.0, 0.0)
    for _ in range(30):
        actor.update(0.016)
    assert actor.position[0] < 5 * 16.0 - 4.0
    actor.move_vector[:] = (1.0, 1.0)
    for _ in range(30):
        actor.update(0.016)
    assert actor.position[1] > 6 * 16.0  # the y axis still moved


# -- damage ---------------------------------------------------------------


def test_a_weapon_cools_down_between_swings():
    """A weapon polled every frame cannot machine-gun.

    The damage area anchoring also follows ``update`` rather than ``draw``:
    an enemy's weapon is never drawn, and it used to strike from wherever
    its holder last stood on screen.
    """
    holder = Actor(alias="hero", speed=0.0)
    holder.position[:] = (0.0, 0.0)
    sword = Weapon(reach=10.0, duration=0.2, recharge=0.3)
    assert sword.swing() is True
    assert sword.swing() is False  # mid-swing
    sword.update(0.25, holder)
    assert not sword.striking
    assert sword.swing() is False  # cooling
    for _ in range(20):
        sword.update(0.05, holder)
    assert sword.swing() is True
    # The area anchors at the holder even when the weapon is never drawn.
    holder.position[:] = (100.0, 50.0)
    sword.update(0.0, holder)
    assert sword.area_centre[0] == pytest.approx(100.0)


def test_a_strike_skips_allies_and_the_already_hit():
    villagers = Team("villagers")
    beasts = Team("beasts")
    sword = Weapon(team=villagers, damage=Damage(2.0, 100.0))
    sword.holder_position = np.array([0.0, 10.0])
    sword.direction = np.array([0.0, 1.0])
    sword.timer = sword.duration
    beast = Actor(alias="beast", team=beasts, maximum_life=5.0)
    beast.position[:] = (0.0, 26.0)
    friend = Actor(alias="guardian", team=villagers, maximum_life=5.0)
    friend.position[:] = (0.0, 26.0)
    hit = strike(sword, [beast, friend], once=set())
    assert hit == [beast]
    assert beast.health.current == 3.0
    assert friend.health.current == 5.0
    once = set()
    strike(sword, [beast], once=once)
    assert strike(sword, [beast], once=once) == []  # once per swing
    assert beast.push_velocity[1] > 0.0


def test_a_destroyable_bursts_when_its_life_runs_out():
    crate = Destroyable((50.0, 50.0), life=2.0)
    died = crate.take_damage(Damage(1.0), (0.0, 0.0))
    assert died is False and crate.health.current == 1.0
    died = crate.take_damage(Damage(1.0), (0.0, 0.0))
    assert died is True
    crate.update(0.1)
    assert crate.burst_timer > 0.0
    crate.burst_timer = 0.0
    crate.update(0.1)
    assert crate.burst_timer == 0.0


def test_health_heals_to_its_maximum_only():
    health = Health(4.0)
    health.damage(3.0)
    health.heal(10.0)
    assert health.current == 4.0


# -- behaviors ------------------------------------------------------------


def test_follow_keeps_a_band_around_the_target():
    leader = Actor(alias="guardian")
    leader.position[:] = (0.0, 0.0)
    trailer = Actor(alias="hero")
    trailer.position[:] = (0.0, 40.0)
    follow = Follow(trailer, leader, min_distance=8.0, max_distance=24.0)
    follow.update(0.016)
    assert trailer.move_vector[1] < 0.0  # closing
    trailer.position[:] = (0.0, 16.0)
    follow.update(0.016)
    assert np.all(trailer.move_vector == 0.0)  # inside the band
    trailer.position[:] = (0.0, 4.0)
    follow.update(0.016)
    assert trailer.move_vector[1] > 0.0  # backing off


def test_a_patrol_visits_its_points_in_order():
    walker = Actor(alias="guardian", speed=50.0)
    walker.position[:] = (0.0, 0.0)
    patrol = Patrol(walker, [(30.0, 0.0), (30.0, 30.0)], wait_time=0.2)
    reached_right = None
    reached_far = None
    for index in range(600):
        patrol.update(0.016)
        walker.update(0.016)
        if reached_right is None and walker.position[0] > 28.0:
            reached_right = index
        if reached_far is None and walker.position[1] > 28.0:
            reached_far = index
    assert reached_right is not None, "never reached the first waypoint"
    assert reached_far is not None, "never reached the second waypoint"
    assert reached_right < reached_far  # in order


def test_a_sense_drops_its_target_when_it_dies():
    hunter = Actor(alias="warden")
    hunter.position[:] = (0.0, 0.0)
    prey = Actor(alias="beast", maximum_life=1.0)
    prey.position[:] = (10.0, 0.0)
    sense = Sense(radius=48.0)
    assert sense.update(hunter, [prey]) is prey
    prey.take_damage(Damage(1.0), hunter.position)
    assert sense.update(hunter, [prey]) is None


def test_wander_stays_near_its_start(monkeypatch):
    random.seed(1789)
    beast = Actor(alias="beast", speed=30.0)
    beast.position[:] = (100.0, 100.0)
    for _ in range(600):
        wander(beast, 0.016)
        beast.update(0.016)
    assert np.hypot(*(beast.position - np.array([100.0, 100.0]))) < 120.0


# -- tile map -------------------------------------------------------------


def test_a_tile_map_draws_only_the_visible_window():
    grid = np.arange(40 * 40, dtype=np.int32).reshape(40, 40)
    uv = np.random.default_rng(0).random((40 * 40, 4)).astype(np.float32)
    tiles = TileMap(grid, uv, tile=16.0)
    camera = RoomCamera()
    camera.snap_to((0.0, 0.0))
    instances = tiles.visible_instances(camera, aspect=2.0)
    # A room centred at the origin: the view spans -176..176 x -88..88, of
    # which the grid supplies columns 0..12 and rows 0..6 (13 x 7 cells).
    assert instances.shape[0] == 13 * 7
    camera.follow((330.0, 0.0), snap=True)
    assert tuple(camera.cell) == (1, 0)
    instances = tiles.visible_instances(camera, aspect=2.0)
    assert instances.shape[0] == 25 * 7
    # Every instance samples the uv of the cell it sits on.
    for row in instances[:50]:
        col = int(row[0] // 16.0)
        line = int(row[1] // 16.0)
        assert np.allclose(row[12:16], uv[grid[line, col]], atol=1e-6)


def test_solidity_reads_the_grid_and_its_edges():
    grid = np.zeros((4, 4), dtype=np.int32)
    grid[1, 1] = 7
    tiles = TileMap(grid, np.zeros((8, 4), dtype=np.float32), solid_ids=[7])
    assert tiles.solid_at(1.5 * 16.0, 1.5 * 16.0) is True
    assert tiles.solid_at(0.5 * 16.0, 0.5 * 16.0) is False
    assert tiles.solid_at(-50.0, 0.0) is True  # outside is solid


# -- room camera ----------------------------------------------------------


def test_the_camera_glides_between_rooms_and_snaps_on_teleport():
    camera = RoomCamera(transition_time=0.4)
    camera.snap_to((160.0, 88.0))
    assert tuple(camera.cell) == (0, 0)
    camera.follow((330.0, 88.0))  # across the right edge: room (1, 0)
    assert tuple(camera.cell) == (1, 0)
    moved = [camera.update(0.05) for _ in range(9)]
    assert any(moved)
    assert not camera.update(0.05)  # glide finished
    assert camera.center[0] == pytest.approx(320.0)
    camera.follow((330.0, 300.0), snap=True)
    assert not camera.gliding
    assert camera.center[1] == pytest.approx(352.0)


# -- fx -------------------------------------------------------------------


def test_a_transition_fades_both_ways():
    fade = Transition(duration=0.2)
    fade.play(cover=True)
    for _ in range(30):
        fade.update(1.0 / 60.0)
    assert fade.covered
    fade.play(cover=False)
    for _ in range(30):
        fade.update(1.0 / 60.0)
    assert fade.alpha == 0.0


def test_weather_switches_its_population():
    weather = Weather(view=(320.0, 176.0))
    weather.set(["rain"])
    assert "rain" in weather._drops
    weather.update(0.016)
    before = weather._drops["rain"][0, 1]
    weather.update(0.016)
    assert weather._drops["rain"][0, 1] > before
    weather.set(["fog"])
    assert "rain" not in weather._drops
    for _ in range(200):
        weather.update(0.016)
    assert weather.fog_alpha == pytest.approx(1.0)
    weather.set([])
    for _ in range(200):
        weather.update(0.016)
    assert weather.fog_alpha == pytest.approx(0.0)
