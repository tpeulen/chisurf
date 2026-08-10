"""The overworld: walking the documentation.

The map comes from :mod:`..api.world`, which paints a real tile grid from the
docs' own toctrees and review sidecars. This module draws that grid and walks
**Iris** across it, with **Lumi** trailing -- the same two characters who are the
ball in Pong and the probe in Breakout (see :mod:`...characters`).

The arc comes from :mod:`..api.story`, whose beats complete because the corpus
changed rather than because the player pressed something.

Only the tiles inside the view are drawn. The world is ~76,000 tiles, so
uploading all of them every frame would spend the whole frame budget on scenery
nobody can see.
"""

from __future__ import annotations

import math

import numpy as np

from chisurf.gui import chigame
from chisurf.gui.chigame.input import Action

from ...characters import IRIS, LUMI, draw as draw_character
from ..api import tiles as T
from ..api.story import Story
from ..api.world import SCOUTED, SETTLED, WILD, World, build_world

#: Emission wavelengths that stand for the two lit room states.
SCOUTED_NM = 488.0
SETTLED_NM = 545.0

#: Walking speed in world units per second, and the sprint multiplier.
WALK_SPEED = 190.0
SPRINT = 2.6

#: How fast the camera catches up with Iris, per second.
CAMERA_LAG = 7.0

#: How closely Lumi follows, in world units.
LUMI_TRAIL = 26.0

#: Iris' collision radius. Smaller than a tile so she fits through a one-tile
#: gate without catching on its jambs.
BODY = 5.0

#: View heights: walking, and the range the shoulders zoom over.
VIEW_HEIGHT = 420.0
VIEW_MIN = 240.0
VIEW_MAX = 3000.0

#: Beyond this the view is a map and per-tile detail becomes noise.
MAP_THRESHOLD = 1400.0

#: Flat colours per tile kind, sRGB. Terrain is muted so anything lit reads.
TILE_COLORS = {
    T.WATER: (0.055, 0.085, 0.145, 1.0),
    T.GRASS: (0.115, 0.180, 0.130, 1.0),
    T.TREE: (0.070, 0.130, 0.090, 1.0),
    T.ROCK: (0.190, 0.200, 0.215, 1.0),
    T.ROAD: (0.230, 0.205, 0.160, 1.0),
    T.FLOOR: (0.175, 0.170, 0.155, 1.0),
    T.WALL: (0.300, 0.290, 0.270, 1.0),
    T.GATE: (0.360, 0.300, 0.180, 1.0),
    T.BRIDGE: (0.260, 0.215, 0.150, 1.0),
    T.BUILDING: (0.230, 0.225, 0.215, 1.0),
    T.VOID: (0.020, 0.022, 0.028, 1.0),
}

BINDINGS = {
    "ArrowUp": Action.UP,
    "ArrowDown": Action.DOWN,
    "ArrowLeft": Action.LEFT,
    "ArrowRight": Action.RIGHT,
    "w": Action.UP,
    "s": Action.DOWN,
    "a": Action.LEFT,
    "d": Action.RIGHT,
    "Shift": Action.CONFIRM,
    " ": Action.CONFIRM,
    "q": Action.SHOULDER_L,
    "e": Action.SHOULDER_R,
    "Tab": Action.MENU,
}


class OverworldGame(chigame.Game):
    """Walk the corpus.

    Parameters
    ----------
    world : chisurf.plugins.misc.games.lumis_quest.api.world.World, optional
        A prebuilt world. Omitted builds one from the installed documentation;
        tests pass a small one instead.
    """

    title = "Lumis Quest"
    background = (0.020, 0.024, 0.030, 1.0)
    music_context = "overworld"

    def __init__(self, world: World | None = None) -> None:
        self._world = world

    def setup(self, host) -> None:
        """Bind the controller, build the world and place Iris.

        Parameters
        ----------
        host : chisurf.gui.chigame.game.GameHost
            The host running this game.
        """
        self.host = host
        host.keys.bindings = dict(BINDINGS)
        self.world = self._world if self._world is not None else build_world()
        self.story = Story(self.world)
        self.view_height = VIEW_HEIGHT
        self.show_map = False

        # Tile kind -> RGBA, as an array so a whole window maps in one index.
        self._palette = np.zeros((max(TILE_COLORS) + 1, 4), dtype=np.float32)
        for kind, colour in TILE_COLORS.items():
            self._palette[kind] = colour
        self.scene_batch = host.batch

        start = self.world.spawn()
        self.iris = [float(start[0]), float(start[1])]
        self.lumi = [self.iris[0] - LUMI_TRAIL, self.iris[1]]
        host.camera.center[:] = self.iris
        host.camera.height = self.view_height

    @property
    def here(self):
        """The room Iris is standing nearest.

        Returns
        -------
        Room or None
            ``None`` for an empty world.
        """
        return self.world.nearest_room(tuple(self.iris))

    @property
    def land(self):
        """The land Iris is standing in.

        Returns
        -------
        Region or None
            ``None`` when out on the water between lands.
        """
        return self.world.region_at(self.iris[0], self.iris[1])

    def update(self, dt: float, keys) -> None:
        """Advance one frame.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        if keys.just_pressed(Action.MENU):
            self.show_map = not self.show_map

        dx, dy = keys.axis()
        if dx or dy:
            length = math.hypot(dx, dy) or 1.0
            speed = WALK_SPEED * (SPRINT if keys.is_held(Action.CONFIRM) else 1.0)
            self._walk(dx / length * speed * dt, dy / length * speed * dt)

        if keys.is_held(Action.SHOULDER_L):
            self.view_height = min(self.view_height * (1.0 + 1.9 * dt), VIEW_MAX)
        if keys.is_held(Action.SHOULDER_R):
            self.view_height = max(self.view_height * (1.0 - 1.9 * dt), VIEW_MIN)

        self.story.observe(self.here)

        # Lumi moves toward a point behind Iris rather than to Iris, so the two
        # never collapse into one blob.
        to_lumi = (self.iris[0] - self.lumi[0], self.iris[1] - self.lumi[1])
        distance = math.hypot(*to_lumi)
        if distance > LUMI_TRAIL:
            move = min((distance - LUMI_TRAIL) * 6.0 * dt, distance)
            self.lumi[0] += to_lumi[0] / distance * move
            self.lumi[1] += to_lumi[1] / distance * move

        camera = self.host.camera
        blend = min(CAMERA_LAG * dt, 1.0)
        centre, height = (
            self._map_view() if self.show_map else (tuple(self.iris), self.view_height)
        )
        camera.center[0] += (centre[0] - camera.center[0]) * blend
        camera.center[1] += (centre[1] - camera.center[1]) * blend
        camera.height += (height - camera.height) * blend

    def _walk(self, dx: float, dy: float) -> None:
        """Move Iris, sliding along anything solid.

        Each axis resolves separately, so walking into a wall at an angle slides
        along it instead of stopping dead. Without that the one-tile gates are
        nearly impossible to enter.

        Parameters
        ----------
        dx, dy : float
            Intended movement in world units.
        """
        if not self._solid(self.iris[0] + dx, self.iris[1]):
            self.iris[0] += dx
        if not self._solid(self.iris[0], self.iris[1] + dy):
            self.iris[1] += dy

    def _solid(self, x: float, y: float) -> bool:
        """Whether Iris' body would overlap something solid.

        Parameters
        ----------
        x, y : float
            Candidate centre in world units.

        Returns
        -------
        bool
            True when the move must be refused.
        """
        for ox, oy in ((-BODY, 0.0), (BODY, 0.0), (0.0, -BODY), (0.0, BODY)):
            if self.world.blocked(x + ox, y + oy):
                return True
        return False

    def _map_view(self) -> tuple[tuple[float, float], float]:
        """Camera centre and height that frame the whole world.

        Returns
        -------
        tuple
            ``((x, y), height)``. The camera spans ``height * aspect``
            horizontally, so a world wider than it is tall sets its height from
            the width.
        """
        min_x, min_y, max_x, max_y = self.world.bounds()
        width, height = self.host.ctx.size
        aspect = width / max(height, 1)
        margin = 1.06
        return (
            ((min_x + max_x) * 0.5, (min_y + max_y) * 0.5),
            max((max_y - min_y) * margin, (max_x - min_x) * margin / max(aspect, 1e-3), 200.0),
        )

    def draw(self, scene) -> None:
        """Queue the frame.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        """
        camera = self.host.camera
        width, height = self.host.ctx.size
        half = camera.half_extent(width / max(height, 1))
        as_map = camera.height > MAP_THRESHOLD

        self._draw_tiles(scene, camera, half, as_map)
        self._draw_rooms(scene, camera, half)

        if not as_map:
            for village in self.world.villages:
                vx, vy = village.position
                if abs(vx - camera.center[0]) > half[0] or abs(vy - camera.center[1]) > half[1]:
                    continue
                _, row, _, _ = village.rect
                scene.text(
                    village.name.upper(),
                    at=(vx, row * T.TILE - 9.0),
                    height=10.0, align="center", color=(0.52, 0.56, 0.64, 1.0),
                )

        draw_character(scene, LUMI, tuple(self.lumi), 9.0)
        scene.draw("aura", "iris-ring", at=tuple(self.iris), size=(26.0, 26.0))
        draw_character(scene, IRIS, tuple(self.iris), 13.0)

        self._draw_hud(scene, camera, half)

    def _visible_tiles(self, camera, half) -> tuple[int, int, int, int]:
        """Grid range covering the view.

        Parameters
        ----------
        camera : chisurf.gui.chigame.render.Camera
            The view.
        half : numpy.ndarray
            Half-extent in world units.

        Returns
        -------
        tuple of int
            ``(col0, row0, col1, row1)``, clamped to the grid.
        """
        col0 = max(0, int((camera.center[0] - half[0]) // T.TILE) - 1)
        row0 = max(0, int((camera.center[1] - half[1]) // T.TILE) - 1)
        col1 = min(self.world.width, int((camera.center[0] + half[0]) // T.TILE) + 2)
        row1 = min(self.world.height, int((camera.center[1] + half[1]) // T.TILE) + 2)
        return col0, row0, col1, row1

    def _draw_tiles(self, scene, camera, half, as_map: bool) -> None:
        """Draw the ground, culled to the view.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        camera : chisurf.gui.chigame.render.Camera
            The view.
        half : numpy.ndarray
            Half-extent in world units.
        as_map : bool
            Whether the view is wide enough to be a map.
        """
        col0, row0, col1, row1 = self._visible_tiles(camera, half)
        if col1 <= col0 or row1 <= row0:
            return
        # At map scale a tile is under a pixel, so every other one conveys the
        # same shape for a quarter of the quads.
        step = 2 if as_map else 1
        window = self.world.array[row0:row1:step, col0:col1:step]
        rows, cols = window.shape
        if not rows or not cols:
            return

        # Built as arrays rather than one draw call per tile: a screenful is
        # thousands of quads, and the per-quad Python call was the entire frame.
        size = T.TILE * step
        xs = (col0 + np.arange(cols) * step + step / 2) * T.TILE
        ys = (row0 + np.arange(rows) * step + step / 2) * T.TILE
        grid_x, grid_y = np.meshgrid(xs, ys)

        colors = self._palette[window.reshape(-1)]
        count = colors.shape[0]
        instances = np.zeros((count, chigame.FLOATS_PER_INSTANCE), dtype=np.float32)
        instances[:, 0] = grid_x.reshape(-1)
        instances[:, 1] = grid_y.reshape(-1)
        instances[:, 2] = size
        instances[:, 3] = size
        instances[:, 4:8] = colors
        instances[:, 8] = chigame.RECT
        instances[:, 11] = 0.0          # hard edges: this is a tile grid
        instances[:, 14] = 1.0
        instances[:, 15] = 1.0

        # Buildings are drawn with the rooms so their state can colour them.
        keep = window.reshape(-1) != T.BUILDING
        self.scene_batch.add_array(instances[keep])

    def _draw_rooms(self, scene, camera, half) -> None:
        """Draw the buildings, culled to the view.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        camera : chisurf.gui.chigame.render.Camera
            The view.
        half : numpy.ndarray
            Half-extent in world units.
        """
        for room in self.world.rooms:
            x, y = room.position
            if abs(x - camera.center[0]) > half[0] + T.TILE:
                continue
            if abs(y - camera.center[1]) > half[1] + T.TILE:
                continue
            if room.state == SETTLED:
                scene.draw("photon", "halo", at=(x, y), size=(T.TILE, T.TILE),
                           emission_nm=SETTLED_NM)
                scene.draw("villager", room.address, at=(x, y),
                           size=(T.TILE * 0.8, T.TILE * 0.8))
            elif room.state == SCOUTED:
                scene.draw("photon", "halo", at=(x, y), size=(T.TILE * 0.8, T.TILE * 0.8),
                           emission_nm=SCOUTED_NM)
                scene.draw("ui", "scouted", at=(x, y), size=(T.TILE * 0.8, T.TILE * 0.8),
                           color=(0.17, 0.32, 0.38, 1.0))
            else:
                scene.draw("wall", room.address, at=(x, y),
                           size=(T.TILE * 0.82, T.TILE * 0.82))
                scene.draw("mount", room.address, at=(x, y - T.TILE * 0.30),
                           size=(T.TILE * 0.86, T.TILE * 0.22),
                           color=(0.30, 0.24, 0.20, 1.0))

    def _draw_hud(self, scene, camera, half) -> None:
        """Draw the readouts, pinned to the camera rather than the world.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        camera : chisurf.gui.chigame.render.Camera
            The view.
        half : numpy.ndarray
            Half-extent in world units.
        """
        left = camera.center[0] - half[0]
        top = camera.center[1] - half[1]
        bottom = camera.center[1] + half[1]
        scale = camera.height / VIEW_HEIGHT

        counts = self.world.counts()
        total = max(len(self.world.rooms), 1)
        scene.text(
            f"settled {counts[SETTLED]}/{total}   scouted {counts[SCOUTED]}   wild {counts[WILD]}",
            at=(left + 14.0 * scale, top + 16.0 * scale),
            height=11.0 * scale, color=(0.55, 0.60, 0.68, 1.0),
        )

        land = self.land
        if land is not None:
            scene.text(
                land.title,
                at=(left + 14.0 * scale, top + 36.0 * scale),
                height=15.0 * scale, color=(0.82, 0.78, 0.62, 1.0),
            )
            if land.subtitle:
                scene.text(
                    land.subtitle,
                    at=(left + 14.0 * scale, top + 52.0 * scale),
                    height=9.5 * scale, color=(0.44, 0.46, 0.52, 1.0),
                )

        beat = self.story.current
        if beat is not None:
            scene.text(
                beat.headline,
                at=(camera.center[0], top + 20.0 * scale),
                height=11.0 * scale, align="center", color=(0.62, 0.70, 0.80, 1.0),
            )

        room = self.here
        if room is not None:
            scene.text(
                room.title,
                at=(camera.center[0], bottom - 30.0 * scale),
                height=13.0 * scale, align="center", color=(0.80, 0.84, 0.90, 1.0),
            )
            scene.text(
                f"{room.address}   [{room.state}]",
                at=(camera.center[0], bottom - 16.0 * scale),
                height=9.0 * scale, align="center", color=(0.42, 0.46, 0.54, 1.0),
            )
