"""The overworld: walking the documentation.

The map comes from :mod:`..api.world`, which derives it from the docs' own
toctrees and review sidecars. This module only draws it and moves Iris around
it -- there is no combat and no AI here, deliberately. The world has to be worth
walking before anything is layered on top of it.

Iris is followed by **Lumi**, a dye-sprite whose colour is the starter
fluorophore's emission. Lumi trails rather than sticking, which is what makes
the pair read as two things rather than one sprite with a halo.

Room state is drawn as three visibly different things, because it *is* three
different things: a page nobody has touched, a page the AI has scouted but no
human has signed off, and a page that is settled. Collapsing the middle state
into either neighbour would hide the exact frontier the game exists to work.
"""

from __future__ import annotations

import math

from chisurf.gui import chigame
from chisurf.gui.chigame.input import Action

from ..api.world import SCOUTED, SETTLED, WILD, World, build_world

#: Emission wavelengths that stand for each state, in nanometres.
SCOUTED_NM = 488.0
SETTLED_NM = 545.0

#: Lumi's colour: the starter dye's emission.
LUMI_NM = 520.0

#: Walking speed in world units per second, and the sprint multiplier.
WALK_SPEED = 210.0
SPRINT = 2.4

#: How fast the camera catches up with Iris, per second. Below 1 it lags
#: visibly; a hard follow makes the whole world jitter with every step.
CAMERA_LAG = 6.0

#: How closely Lumi follows, in world units.
LUMI_TRAIL = 26.0

#: Default view height in world units, and the range the shoulders zoom over.
VIEW_HEIGHT = 460.0
VIEW_MIN = 220.0
VIEW_MAX = 2600.0

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
        A prebuilt world. Omitted builds one from the installed documentation,
        which is what the game does; tests pass a small one instead.
    """

    title = "Lumis Quest"
    background = (0.024, 0.028, 0.036, 1.0)
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
        self.view_height = VIEW_HEIGHT
        self.show_map = False

        rooms = self.world.rooms
        start = rooms[0].position if rooms else (0.0, 0.0)
        self.iris = [float(start[0]), float(start[1]) - 60.0]
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
            self.iris[0] += dx / length * speed * dt
            self.iris[1] += dy / length * speed * dt

        if keys.is_held(Action.SHOULDER_L):
            self.view_height = min(self.view_height * (1.0 + 1.8 * dt), VIEW_MAX)
        if keys.is_held(Action.SHOULDER_R):
            self.view_height = max(self.view_height * (1.0 - 1.8 * dt), VIEW_MIN)

        # Lumi trails: it moves toward a point behind Iris rather than to Iris,
        # so the two never overlap into a single blob.
        to_lumi = (self.iris[0] - self.lumi[0], self.iris[1] - self.lumi[1])
        distance = math.hypot(*to_lumi)
        if distance > LUMI_TRAIL:
            move = min((distance - LUMI_TRAIL) * 6.0 * dt, distance)
            self.lumi[0] += to_lumi[0] / distance * move
            self.lumi[1] += to_lumi[1] / distance * move

        target_height = self._map_height() if self.show_map else self.view_height
        camera = self.host.camera
        blend = min(CAMERA_LAG * dt, 1.0)
        if self.show_map:
            centre = self._world_centre()
            camera.center[0] += (centre[0] - camera.center[0]) * blend
            camera.center[1] += (centre[1] - camera.center[1]) * blend
        else:
            camera.center[0] += (self.iris[0] - camera.center[0]) * blend
            camera.center[1] += (self.iris[1] - camera.center[1]) * blend
        camera.height += (target_height - camera.height) * blend

    def _world_centre(self) -> tuple[float, float]:
        """Centre of the world's extent, for the map view.

        The *mean* room position is not the centre: `reference` holds 145 of the
        377 rooms, so averaging drags the view into it and clips everything
        else. The bounding box is what has to be centred.

        Returns
        -------
        tuple of float
            World coordinates.
        """
        min_x, min_y, max_x, max_y = self.world.bounds()
        return ((min_x + max_x) * 0.5, (min_y + max_y) * 0.5)

    def _map_height(self) -> float:
        """View height that fits the whole world, including its width.

        Returns
        -------
        float
            World units. The camera spans ``height * aspect`` horizontally, so
            a world wider than it is tall has to set the height from the width.
        """
        min_x, min_y, max_x, max_y = self.world.bounds()
        width, height = self.host.ctx.size
        aspect = width / max(height, 1)
        margin = 1.12
        return max((max_y - min_y) * margin, (max_x - min_x) * margin / max(aspect, 1e-3), 200.0)

    def draw(self, scene) -> None:
        """Queue the frame.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        """
        zoomed_out = self.host.camera.height > 900.0

        for region in self.world.regions:
            villages = region.villages
            for first, second in zip(villages, villages[1:]):
                self._draw_path(scene, first.position, second.position)

        for village in self.world.villages:
            prosperity = village.prosperity
            # A village's ground brightens as its pages are settled, so a
            # neglected section is visibly a ghost town from across the map.
            tint = 0.055 + 0.10 * prosperity
            scene.draw(
                "ui", "ground",
                at=village.position,
                size=(240.0, 60.0 + 46.0 * (len(village.rooms) // 5 + 1)),
                color=(tint * 0.75, tint, tint * 0.95, 1.0),
            )

        for room in self.world.rooms:
            self._draw_room(scene, room, zoomed_out)

        if not zoomed_out:
            for village in self.world.villages:
                scene.text(
                    village.name.upper(),
                    at=(village.position[0], village.position[1] - 40.0),
                    height=11.0, align="center", color=(0.40, 0.44, 0.52, 1.0),
                )

        scene.draw("photon", "lumi", at=tuple(self.lumi), size=(9.0, 9.0),
                   emission_nm=LUMI_NM)
        # Iris has to out-read her own companion: a ring around a bright core,
        # rather than a dot that Lumi's halo swamps.
        scene.draw("aura", "iris-ring", at=tuple(self.iris), size=(30.0, 30.0))
        scene.draw("hero", "iris", at=tuple(self.iris), size=(15.0, 15.0))

        self._draw_hud(scene)

    def _draw_room(self, scene, room, zoomed_out: bool) -> None:
        """Draw one room according to its state.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        room : Room
            The room.
        zoomed_out : bool
            Whether the view is wide enough that detail would be noise.
        """
        if room.state == SETTLED:
            scene.draw("photon", "halo", at=room.position, size=(13.0, 13.0),
                       emission_nm=SETTLED_NM)
            scene.draw("villager", room.address, at=room.position, size=(15.0, 15.0))
        elif room.state == SCOUTED:
            scene.draw("photon", "halo", at=room.position, size=(9.0, 9.0),
                       emission_nm=SCOUTED_NM)
            scene.draw("ui", "scouted", at=room.position, size=(13.0, 13.0),
                       color=(0.16, 0.30, 0.36, 1.0))
        else:
            # Wild: unlit. It is a shape in the dark, not a coloured marker --
            # which is what makes the settled ones read as light. It still needs
            # a roof, or 269 of the 377 rooms are featureless smudges.
            scene.draw("wall", room.address, at=room.position, size=(13.0, 13.0))
            scene.draw("mount", room.address, at=(room.position[0], room.position[1] - 5.0),
                       size=(14.0, 4.0), color=(0.15, 0.16, 0.19, 1.0))

        if not zoomed_out and room.state != WILD:
            scene.text(room.title[:22], at=(room.position[0], room.position[1] + 16.0),
                       height=7.5, align="center", color=(0.42, 0.46, 0.54, 1.0))

    def _draw_path(self, scene, start, end) -> None:
        """Draw a faint track between two places.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        start, end : tuple of float
            Endpoints in world units.
        """
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.hypot(dx, dy)
        if length < 1.0:
            return
        steps = max(2, int(length / 26.0))
        for step in range(steps + 1):
            fraction = step / steps
            scene.draw(
                "ui", "track",
                at=(start[0] + dx * fraction, start[1] + dy * fraction),
                size=(3.0, 3.0),
                color=(0.11, 0.12, 0.14, 1.0),
            )

    def _draw_hud(self, scene) -> None:
        """Draw the readouts, pinned to the camera rather than the world.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        """
        camera = self.host.camera
        width, height = self.host.ctx.size
        half = camera.half_extent(width / max(height, 1))
        left = camera.center[0] - half[0]
        top = camera.center[1] - half[1]
        bottom = camera.center[1] + half[1]
        scale = camera.height / VIEW_HEIGHT

        counts = self.world.counts()
        total = max(len(self.world.rooms), 1)
        settled = counts[SETTLED]

        scene.text(
            f"settled {settled}/{total}   scouted {counts[SCOUTED]}   wild {counts[WILD]}",
            at=(left + 14.0 * scale, top + 16.0 * scale),
            height=11.0 * scale, color=(0.55, 0.60, 0.68, 1.0),
        )

        room = self.here
        if room is not None:
            scene.text(
                room.title,
                at=(camera.center[0], bottom - 30.0 * scale),
                height=14.0 * scale, align="center", color=(0.80, 0.84, 0.90, 1.0),
            )
            scene.text(
                f"{room.address}   [{room.state}]",
                at=(camera.center[0], bottom - 15.0 * scale),
                height=9.5 * scale, align="center", color=(0.42, 0.46, 0.54, 1.0),
            )
