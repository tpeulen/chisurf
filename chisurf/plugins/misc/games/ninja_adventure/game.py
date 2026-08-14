"""Ninja Adventure — the reference game, playable on chigame.

This is the port of ``junk/NinjaAdventure`` (Godot 4, CC0 by pixel-boy): the
one map its author ships, ``content/map/map_village.tscn``, converted to JSON
by :mod:`build_tools.dev_utils.import_ninja_map` and played here on the
engine's ported systems. The world is the author's, not a stand-in: the same
tile cells, the same ninja at (64, 48), the same pig trailing the green
samurai who trails you, the same crate-and-grass clutter, the same paired
teleporter between the village and the swamp, the same weather areas.

What the reference's checkout does not ship — hostile enemies and a combat
encounter — is added on top, on its terms: enemy samurai beyond the teleporter
that sense, chase and swing, because a port you cannot lose is a screensaver.
Their team is the reference's own ``enemy_team``; the village's NPCs are its
``npc_team``, allied to the player and untouchable by the swing.

The engine systems this runs on are documented in
:mod:`chisurf.gui.chigame` — actors, weapons, behaviors, tile maps, the room
camera, weather, transitions. This module is orchestration: it loads the map,
wires the actors to it, and owns the game's own rules (spawning, teleport,
death, the HUD).
"""

from __future__ import annotations

import json
import pathlib
import random

import numpy as np

from chisurf.gui import chigame
from chisurf.gui.chigame.actors import (
    Actor,
    Damage,
    Destroyable,
    Team,
    Weapon,
    draw_sorted,
    strike,
)
from chisurf.gui.chigame.behavior import Follow, Patrol, Sense
from chisurf.gui.chigame.camera import RoomCamera
from chisurf.gui.chigame.fx import CLOUD, FOG, LEAF, RAIN, SNOW, Transition, Weather
from chisurf.gui.chigame.input import Action
from chisurf.gui.chigame.tilemap import TileMap

#: The converted village map, shipped beside this module.
MAP = pathlib.Path(__file__).resolve().parent / "data" / "map_village.json"

#: TileSet source id -> the pixel pack's grid name (see the tileset's own
#: ``sources/`` table, mirrored by the importer).
SOURCE_GRIDS = {0: "village", 1: "floor", 2: "interior", 3: "animated", 4: "wall"}

#: Scene-collection ids: what a destroyable tile spawns.
SCENE_KINDS = {1: "crate", 2: "grass", 3: "pot"}

#: The reference's teams, by their .tres values: player 1, npc 2 (allied to
#: the player), enemy 3 (allied to nobody).
TEAM_PLAYER = Team("player", allies=("npc",))
TEAM_NPC = Team("npc", allies=("player",))
TEAM_ENEMY = Team("enemy")

#: Character sheet -> pack alias. The map names characters by their scene
#: folder; the pack names them by role.
SHEETS = {
    "ninja_blue": "hero",
    "samurai_blue": "guardian",
    "samurai_green": "warden",
    "pig": "beast",
}

#: Meteo enum ints (the reference's ``ResourceEnvironment.Meteo``) -> the
#: engine's weather kinds. RAY is sunbeams, which the engine does not model.
METEO = {0: RAIN, 1: SNOW, 2: FOG, 3: CLOUD, 4: LEAF}

#: Seconds the teleporter lockout lasts after a teleport (the reference's
#: ``just_teleport`` timer).
TELEPORT_LOCKOUT = 1.0

#: How far off a teleporter's target the player lands, in the teleporter's
#: own direction — the reference places at ``target + direction * 25``.
TELEPORT_OFFSET = 25.0

#: Hostile samurai beyond the teleporter: positions relative to the swamp
#: teleporter, their weapon and senses. The reference ships no enemy scene;
#: these stand where its swamp environment area is.
PATROL_ENEMIES = (
    ((70.0, 10.0), "guardian"),
    ((110.0, -30.0), "warden"),
    ((20.0, -40.0), "guardian"),
)

#: Player starting life, in hearts (two life a heart, as the strip draws).
PLAYER_HEARTS = 3.0


class NinjaAdventure(chigame.Game):
    """The playable village map.

    Attributes
    ----------
    phase : str
        ``"title"`` or ``"play"``.
    """

    title = "Ninja Adventure"
    background = (0.055, 0.06, 0.09, 1.0)
    music_context = "overworld"

    def __init__(self, map_path: str | pathlib.Path | None = None) -> None:
        super().__init__()
        self.phase = "title"
        self._map_data = json.loads(
            (pathlib.Path(map_path) if map_path else MAP).read_text(encoding="utf-8")
        )
        self._rng = random.Random(1789)
        self._popups: list[tuple[str, tuple[float, float], float]] = []
        self._respawn: tuple[float, float] = (0.0, 0.0)
        self._teleport_lockout = 0.0
        self._env_index = -1
        self._battle = False

    # -- construction ------------------------------------------------------

    def setup(self, host) -> None:
        """Build the world from the map data.

        Parameters
        ----------
        host : chigame.GameHost
            The host running this game.
        """
        pack = chigame.SheetPack()
        host.bind_pack(pack)

        camera = RoomCamera()
        host.scene.camera = camera
        host.camera = camera

        data = self._map_data
        tile = float(data["tile_size"])
        offset = tuple(data["offset"])

        # Grids: one per layer, drawn back (ground) to front. A cell id
        # indexes the uv table built from every (source, atlas) the map uses.
        self._uv_entries: list[tuple[str, int, int]] = []
        lookup: dict[tuple[int, int, int], int] = {}

        def cell_id(source: int, ax: int, ay: int) -> int:
            key = (source, ax, ay)
            if key not in lookup:
                lookup[key] = len(self._uv_entries)
                self._uv_entries.append((SOURCE_GRIDS[source], ax, ay))
            return lookup[key]

        solids_raw = {
            (int(source), ax, ay)
            for source, cells in data["solids"].items()
            for ax, ay in cells
        }
        self.destroyables: list[Destroyable] = []
        self.layers: list[TileMap] = []
        self.solid_cells: set[tuple[int, int]] = set()
        for layer in sorted(data["layers"], key=lambda item: -item["index"]):
            cells = layer["cells"]
            spawn = [c for c in cells if c["source"] == 5]
            plain = [c for c in cells if c["source"] != 5]
            for cell in spawn:
                kind = SCENE_KINDS.get(cell["ax"], "crate")
                self._spawn_destroyable(kind, cell, offset, tile)
            if not plain:
                continue
            xs = [c["x"] for c in plain]
            ys = [c["y"] for c in plain]
            grid = np.full((max(ys) - min(ys) + 1, max(xs) - min(xs) + 1), -1, np.int32)
            for cell in plain:
                grid[cell["y"] - min(ys), cell["x"] - min(xs)] = cell_id(
                    cell["source"], cell["ax"], cell["ay"]
                )
                if (cell["source"], cell["ax"], cell["ay"]) in solids_raw:
                    self.solid_cells.add((cell["x"], cell["y"]))
            origin = (offset[0] + min(xs) * tile, offset[1] + min(ys) * tile)
            self.layers.append(
                TileMap(grid, None, tile=tile, offset=origin)
            )

        uv_table = np.zeros((len(self._uv_entries), 4), dtype=np.float32)
        for index, (grid_name, ax, ay) in enumerate(self._uv_entries):
            uv_table[index] = pack.cell_uv(grid_name, ay, ax)
        for layer in self.layers:
            layer.uv_table = uv_table

        # Actors from the scene file.
        self.actors: list[Actor] = []
        self.follows: list[tuple[Follow, Actor]] = []
        self.patrols: list[Patrol] = []
        self.senses: list[tuple[Sense, Actor, Weapon]] = []
        named: dict[str, Actor] = {}
        behaviors = {entry["node"].split("/")[-1]: entry["behavior"] for entry in data["behaviors"]}
        for character in data["characters"]:
            alias = SHEETS.get(character["sheet"], "hero")
            is_player = character["name"] == "NinjaBlue"
            actor = Actor(
                position=tuple(character["position"]),
                alias=alias,
                speed=character["speed"] or (110.0 if is_player else 55.0),
                solid=self._solid_at,
                half_extent=(5.0, 4.0),
                team=TEAM_PLAYER if is_player else TEAM_NPC,
                maximum_life=PLAYER_HEARTS * 2.0 if is_player else 4.0,
                two_column=alias == "beast",
            )
            named[character["name"]] = actor
            self.actors.append(actor)
            if is_player:
                self.player = actor
                self.player_weapon = Weapon(
                    "club", Damage(1.0, 130.0), team=TEAM_PLAYER,
                    reach=13.0, duration=0.18,
                )
                self._respawn = tuple(character["position"])
                actor.on_damaged = self._on_player_hit

        # Behaviors from the scene file: who follows whom, who patrols where.
        for name, actor in named.items():
            behavior = behaviors.get(name)
            if behavior is None:
                continue
            if behavior["type"] == "follow":
                target = named.get(behavior["target"].split("/")[-1])
                if target is not None:
                    self.follows.append(
                        (Follow(actor, target, 10.0, 26.0), target)
                    )
            elif behavior["type"] == "patrol":
                points = next(iter(data["paths"].values()), None)
                if points:
                    self.patrols.append(
                        Patrol(actor, points, loop=True,
                               wait_time=float(behavior.get("wait_time", 1.0)))
                    )

        # Hostiles beyond the teleporter — the one thing the reference's
        # checkout does not ship. They sense, chase, and swing.
        swamp = data["teleporters"][1]["position"]
        self.enemies: list[Actor] = []
        for (dx, dy), alias in PATROL_ENEMIES:
            enemy = Actor(
                position=self._free_spot(swamp[0] + dx, swamp[1] + dy),
                alias=alias,
                speed=62.0,
                solid=self._solid_at,
                half_extent=(5.0, 4.0),
                team=TEAM_ENEMY,
                maximum_life=3.0,
            )
            weapon = Weapon("bone", Damage(1.0, 110.0), team=TEAM_ENEMY,
                            reach=12.0, duration=0.25)
            weapon.cooldown = 0.0
            self.enemies.append(enemy)
            self.actors.append(enemy)
            self.senses.append((Sense(radius=70.0), enemy, weapon))

        self.weapon_hits: set = set()
        self.camera = camera
        self.camera.snap_to(self.player.position)
        self.transition = Transition(duration=0.25)
        self.weather = Weather(view=(360.0, 200.0))
        self._teleporters = data["teleporters"]
        self._environments = [
            {
                "rect": (
                    env["position"][0] - env["size"][0] / 2.0,
                    env["position"][1] - env["size"][1] / 2.0,
                    env["position"][0] + env["size"][0] / 2.0,
                    env["position"][1] + env["size"][1] / 2.0,
                ),
                "meteo": [METEO[value] for value in env["meteo"] if value in METEO],
                "music": env["music"],
            }
            for env in data["environments"]
            if any(value in METEO for value in env["meteo"])
        ]

    def _spawn_destroyable(self, kind: str, cell: dict, offset, tile: float) -> None:
        """Place one crate / grass tuft / pot from a scene tile.

        Parameters
        ----------
        kind : str
            One of the :data:`SCENE_KINDS`.
        cell : dict
            The map cell.
        offset : tuple of float
            Tilemap origin.
        tile : float
            Cell size.
        """
        at = (
            offset[0] + (cell["x"] + 0.5) * tile,
            offset[1] + (cell["y"] + 0.5) * tile,
        )
        burst = {"crate": "burst_wood", "grass": "burst_grass", "pot": "burst_pot"}[kind]
        self.destroyables.append(Destroyable(at, life=1.0, burst=burst))

    # -- world queries -----------------------------------------------------

    def _solid_at(self, x: float, y: float) -> bool:
        """Whether a world position is inside a solid tile.

        Parameters
        ----------
        x, y : float
            World position.

        Returns
        -------
        bool
        """
        data = self._map_data
        tile = data["tile_size"]
        cell = (
            int((x - data["offset"][0]) // tile),
            int((y - data["offset"][1]) // tile),
        )
        return cell in self.solid_cells

    def _free_spot(self, x: float, y: float) -> tuple[float, float]:
        """The nearest position to ``(x, y)`` a body can stand.

        The map's own actors are authored on free ground; anything this port
        adds (the hostile samurai, a teleporter's exit) has to find its own
        footing, and the swamp's water is solid — spawning inside it is a
        figure that can never move.

        Parameters
        ----------
        x, y : float
            Desired position.

        Returns
        -------
        tuple of float
            The first clear spot found, spiralling out by tile.
        """
        tile = self._map_data["tile_size"]
        for ring in range(0, 12):
            for step in range(-ring, ring + 1):
                for dx, dy in ((step, -ring), (step, ring),
                               (-ring, step), (ring, step)) if ring else ((0, 0),):
                    spot = (x + dx * tile, y + dy * tile)
                    if not self._solid_at(*spot):
                        return spot
        return (x, y)

    # -- per frame ---------------------------------------------------------

    def update(self, dt: float, keys) -> None:
        """Advance the game one frame.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        self.transition.update(dt)
        self._popups = [(text, at, left - dt) for text, at, left in self._popups if left > dt]
        if self.phase == "title":
            if keys.just_pressed(Action.CONFIRM):
                self.phase = "play"
                self.transition.play(cover=False, instant=False)
            return

        move = np.zeros(2)
        if keys.is_held(Action.RIGHT):
            move[0] += 1.0
        if keys.is_held(Action.LEFT):
            move[0] -= 1.0
        if keys.is_held(Action.DOWN):
            move[1] += 1.0
        if keys.is_held(Action.UP):
            move[1] -= 1.0
        if np.any(move):
            self.player.move_vector[:] = move / np.hypot(*move)
        else:
            self.player.move_vector[:] = 0.0

        if keys.just_pressed(Action.CONFIRM):
            if self.player_weapon.swing():
                self.player.attack()
                self.weapon_hits = set()

        self.player.update(dt)
        self.player_weapon.update(dt, self.player)
        for hit in strike(
            self.player_weapon, self.enemies + self.destroyables, once=self.weapon_hits
        ):
            if isinstance(hit, Destroyable):
                continue
            self._popup(f"-{int(self.player_weapon.damage.amount)}", hit.position)

        for follow, _target in self.follows:
            follow.update(dt)
        for patrol in self.patrols:
            patrol.update(dt)

        self._battle = False
        for sense, enemy, weapon in self.senses:
            target = sense.update(enemy, [self.player])
            if target is None:
                enemy.move_vector[:] = 0.0
            else:
                self._battle = True
                distance = float(np.hypot(*(target.position - enemy.position)))
                if distance < weapon.reach + 8.0:
                    enemy.move_vector[:] = 0.0
                    if weapon.swing():
                        enemy.attack()
                        self._enemy_hits = getattr(self, "_enemy_hits", set())
                        for victim in strike(weapon, [self.player], once=self._enemy_hits):
                            self._popup(
                                f"-{int(weapon.damage.amount)}", victim.position
                            )
                else:
                    direction = (target.position - enemy.position) / distance
                    enemy.move_vector[:] = direction
            weapon.update(dt, enemy)
            if weapon.timer <= 0.0:
                self._enemy_hits = set()
            enemy.update(dt)

        for actor in self.actors:
            if actor not in self.enemies and actor is not self.player:
                actor.update(dt)
        for destroyable in self.destroyables:
            destroyable.update(dt)

        self.camera.follow(self.player.position)
        self.camera.update(dt)
        self._update_weather(dt)
        self._update_teleporter(dt)
        self._update_music()

    def _popup(self, text: str, at) -> None:
        """Show a short floating label.

        Parameters
        ----------
        text : str
            What it says.
        at : array-like
            World position.
        """
        self._popups.append((text, (float(at[0]), float(at[1] - 10.0)), 0.8))

    def _on_player_hit(self, _player: Actor) -> None:
        """React to the player taking a hit.

        Parameters
        ----------
        _player : Actor
            The player.
        """
        if self.player.health is not None and not self.player.health.alive:
            self.transition.play(cover=True)
            self._dying = 0.4

    def _update_weather(self, dt: float) -> None:
        """Keep the weather pointed at the area the player stands in.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        """
        self.weather.update(dt)
        x, y = self.player.position
        kinds: list[str] = []
        for index, env in enumerate(self._environments):
            x0, y0, x1, y1 = env["rect"]
            if x0 <= x <= x1 and y0 <= y <= y1:
                self._env_index = index
                kinds = env["meteo"]
                break
        else:
            self._env_index = -1
        if tuple(sorted(kinds)) != tuple(sorted(self.weather.active)):
            self.weather.set(kinds)

    def _update_teleporter(self, dt: float) -> None:
        """Teleport on contact, with the reference's fade and offset.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        """
        self._teleport_lockout = max(0.0, self._teleport_lockout - dt)
        dying = getattr(self, "_dying", 0.0)
        if dying > 0.0:
            self._dying = dying - dt
            if dying <= dt:
                self._respawn_player()
            return
        if self._teleport_lockout > 0.0 or self.transition.covered:
            return
        x, y = self.player.position
        for portal in self._teleporters:
            px, py = portal["position"]
            if abs(x - px) < 10.0 and abs(y - py) < 14.0:
                target = next(
                    item for item in self._teleporters if item["name"] == portal["target"]
                )
                dx, dy = portal["direction"]
                self.player.position[:] = self._free_spot(
                    target["position"][0] + dx * TELEPORT_OFFSET,
                    target["position"][1] + dy * TELEPORT_OFFSET,
                )
                self.camera.snap_to(self.player.position)
                self._teleport_lockout = TELEPORT_LOCKOUT
                self.transition.play(cover=True)
                self.transition.finished = False
                return
        if self.transition.alpha > 0.9 and not self.transition.finished:
            self.transition.play(cover=False)

    def _respawn_player(self) -> None:
        """Bring the player back at the spawn, with fresh hearts."""
        self.player.position[:] = self._respawn
        self.player.push_velocity[:] = 0.0
        if self.player.health is not None:
            self.player.health.heal()
        self.camera.snap_to(self.player.position)
        self.transition.play(cover=False)
        self._teleport_lockout = TELEPORT_LOCKOUT

    def _update_music(self) -> None:
        """Pick the soundtrack context for where the player is."""
        if self._battle:
            self.music_context = "battle"
        elif self._env_index >= 0:
            self.music_context = "town"
        else:
            self.music_context = "overworld"

    # -- drawing -----------------------------------------------------------

    def draw(self, scene) -> None:
        """Queue the frame.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            The frame under construction.
        """
        camera = scene.camera
        width, height = scene.batch._ctx.size
        aspect = width / max(height, 1)
        for layer in self.layers:
            layer.draw_visible(scene, camera, aspect)

        figures = [a for a in self.actors if a is not self.player]
        figures += self.destroyables
        draw_sorted(scene, figures)
        if self.player.health is None or self.player.health.alive:
            self.player_weapon.draw(scene, self.player)
            self.player.draw(scene)

        self.weather.draw(scene, camera)

        for text, at, _left in self._popups:
            scene.text(text, at=at, height=7.0, align="center",
                       color=(0.95, 0.85, 0.55, 1.0))

        if self.phase == "play":
            self._draw_hud(scene, camera, aspect)
        else:
            self._draw_title(scene, camera, aspect)
        self.transition.draw(scene, camera, aspect)

    def _draw_hud(self, scene, camera, aspect: float) -> None:
        """Hearts and the weapon in hand, pinned to the view.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            The frame under construction.
        camera : chigame.Camera
            The view.
        aspect : float
            Canvas width over height.
        """
        half = camera.half_extent(aspect)
        left = float(camera.center[0] - half[0])
        top = float(camera.center[1] - half[1])
        if self.player.health is not None:
            quarters = (
                self.player.health.current / self.player.health.maximum * PLAYER_HEARTS * 4.0
            )
            for heart in range(int(PLAYER_HEARTS)):
                filled = quarters - heart * 4.0
                step = 4 if filled >= 4.0 else 3 if filled >= 3.0 else 2 if filled >= 2.0 else 1 if filled >= 1.0 else 0
                scene.draw("tile", "hearts", at=(left + 12.0 + heart * 17.0, top + 12.0),
                           size=(16.0, 16.0), state=f"0,{step}")
        scene.draw("sprite", "club_held", at=(left + 12.0, top + 34.0), size=(12.0, 12.0))

    def _draw_title(self, scene, camera, aspect: float) -> None:
        """The title card over the world, the way the reference opens.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            The frame under construction.
        camera : chigame.Camera
            The view.
        aspect : float
            Canvas width over height.
        """
        half = camera.half_extent(aspect)
        cx, cy = float(camera.center[0]), float(camera.center[1])
        scene.window((cx, cy), (260.0, 120.0), scale=1.0)
        scene.text("NINJA ADVENTURE", at=(cx, cy - 30.0), height=18.0,
                   align="center", color=(0.93, 0.88, 0.66, 1.0))
        scene.text("a pixel-boy map, ported to chigame", at=(cx, cy - 6.0),
                   height=8.0, align="center", color=(0.62, 0.66, 0.74, 1.0))
        scene.text("arrows walk   enter swings the club", at=(cx, cy + 14.0),
                   height=8.0, align="center", color=(0.75, 0.78, 0.84, 1.0))
        scene.text("PRESS ENTER", at=(cx, cy + 40.0), height=10.0, align="center",
                   color=(0.95, 0.90, 0.60, 1.0))
