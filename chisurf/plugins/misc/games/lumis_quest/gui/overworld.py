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
from ..api import battle as battle_api
from ..api import gear as gear_api
from ..api import roster as roster_api
from ..api import review_bridge
from ..api import rig as rig_api
from ..api import save as save_api
from ..api.story import Story
from ..api.world import SCOUTED, SETTLED, WILD, World, build_world
from . import pixelart

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
VIEW_HEIGHT = 330.0
VIEW_MIN = 240.0
VIEW_MAX = 3000.0

#: Beyond this the view is a map and per-tile detail becomes noise.
MAP_THRESHOLD = 1400.0

#: Tile kind -> sprite in the pixel-art atlas.
TILE_SPRITES = {
    T.WATER: "water",
    T.GRASS: "grass",
    T.TREE: "tree",
    T.ROCK: "rock",
    T.ROAD: "road",
    T.FLOOR: "floor",
    T.WALL: "wall",
    T.GATE: "gate",
    T.BRIDGE: "bridge",
    T.CLINIC: "clinic",
    T.BUILDING: "grass",   # the house is drawn over it, tinted by state
    T.VOID: "water",
}

#: A house is one drawing, tinted by whether anyone has read the page. Dark for
#: untouched, cool for scouted-but-unconfirmed, warm for settled.
HOUSE_TINT = {
    WILD: (0.42, 0.44, 0.50, 1.0),
    SCOUTED: (0.70, 0.90, 1.00, 1.0),
    SETTLED: (1.00, 0.96, 0.80, 1.0),
}

#: Frames per second of the walk cycle.
WALK_FPS = 6.0

#: Kept for the map view, where a sprite is smaller than a pixel.
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
    T.CLINIC: (0.30, 0.42, 0.38, 1.0),
    T.BUILDING: (0.230, 0.225, 0.215, 1.0),
    T.VOID: (0.020, 0.022, 0.028, 1.0),
}

def _wrap(text: str, width: int) -> list[str]:
    """Break a line to fit the battle panel.

    Parameters
    ----------
    text : str
        The line.
    width : int
        Maximum characters per line.

    Returns
    -------
    list of str
        One or more lines.
    """
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


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
    save_path : pathlib.Path, optional
        Where the run is stored. Omitted uses the per-user file; tests pass a
        temporary one so they never touch a real save.
    """

    title = "Lumis Quest"
    background = (0.020, 0.024, 0.030, 1.0)
    music_context = "overworld"

    def __init__(self, world: World | None = None, save_path=None) -> None:
        self._world = world
        # Injectable so a test never reads or writes the player's real run.
        self._save_path = save_path

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

        # The pixel-art atlas: authored as string art, packed and uploaded once.
        image, self._uvs = pixelart.build_atlas()
        host.batch.set_sprites(pixelart.upload(host.ctx.device, image))
        self._tile_uv = np.zeros((max(TILE_SPRITES) + 1, 4), dtype=np.float32)
        for kind, sprite in TILE_SPRITES.items():
            self._tile_uv[kind] = self._uvs[sprite]

        self.facing = "down"
        self.walking = False
        self._walk_clock = 0.0

        # The team's photon budgets persist between fights: a single encounter
        # is winnable three-on-one, so the danger is attrition across a run.
        self.pool = [c for c in roster_api.load_roster() if not c.estimated]
        self.team = [battle_api.Fighter(c) for c in roster_api.starters()]
        self.battle: battle_api.Battle | None = None
        self.menu_index = 0
        self.encounter_room = None

        self.gear_pool = gear_api.load_gear()
        self.loadout = gear_api.starting_loadout(self.gear_pool)
        self.inventory: list = []
        self.last_loot = None
        self.cleared: set[str] = set()
        self.collection: list = []
        # Training teaches; expert reviews. They must not grant the same thing.
        self.rig = rig_api.Rig()
        # One menu with tabs, rather than more chords. Nine actions is the whole
        # controller, and the overworld had already spent all of them -- so
        # every extra screen has to live behind Menu, which is the convention
        # this kind of game uses anyway.
        self.menu_open = False
        self.menu_tab = 0
        self.menu_row = 0
        self.mode = review_bridge.TRAINING
        self.challenge = None
        self.challenge_hash = ""
        self.verdict = None
        self._guardian_nm: dict[str, float] = {}
        self.resting = False

        self._restore()
        start = self.world.spawn() if self._resume is None else self._resume
        self.iris = [float(start[0]), float(start[1])]
        self.lumi = [self.iris[0] - LUMI_TRAIL, self.iris[1]]
        host.camera.center[:] = self.iris
        host.camera.height = self.view_height

    def _restore(self) -> None:
        """Load a saved run, if there is one.

        Everything is stored by identifier, so a creature whose stats have since
        been corrected in the database comes back with the corrected ones.
        """
        self._resume = None
        state = save_api.RunState.load(self._save_path)
        if not state.team:
            return
        creatures = save_api.creatures_by_id(self.pool)
        team = [
            battle_api.Fighter(creatures[probe_id], hp=hp)
            for probe_id, hp in state.team
            if probe_id in creatures
        ]
        if not team:
            return
        self.team = team
        self.collection = [
            creatures[probe_id] for probe_id in state.collection if probe_id in creatures
        ]
        parts = save_api.gear_by_id(self.gear_pool)
        self.inventory = [parts[probe_id] for probe_id in state.inventory if probe_id in parts]
        self.loadout = save_api.restore_loadout(state, self.gear_pool)
        self.cleared = set(state.cleared)
        if state.order:
            try:
                self.story.choose(state.order)
            except KeyError:
                pass
        if state.position != (0.0, 0.0):
            self._resume = state.position

    def snapshot(self) -> save_api.RunState:
        """Capture the run for saving.

        Returns
        -------
        chisurf.plugins.misc.games.lumis_quest.api.save.RunState
            The current run.
        """
        return save_api.RunState(
            position=(float(self.iris[0]), float(self.iris[1])),
            team=[(f.creature.probe_id, int(f.hp)) for f in self.team],
            collection=[c.probe_id for c in self.collection],
            inventory=[part.probe_id for part in self.inventory],
            emission_id=self.loadout.emission.probe_id if self.loadout.emission else None,
            detector_id=self.loadout.detector.probe_id if self.loadout.detector else None,
            cleared=sorted(self.cleared),
            order=self.story.chosen_order,
        )

    def save_run(self) -> None:
        """Write the run to disk."""
        self.snapshot().save(self._save_path)

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
        if self.battle is not None:
            self._battle_input(keys)
            return

        if self.menu_open:
            self._menu_input(keys)
            return
        if keys.just_pressed(Action.MENU):
            self.menu_open = True
            self.menu_row = 0
            return
        if keys.just_pressed(Action.SHOULDER_L):
            self._try_encounter()

        dx, dy = keys.axis()
        self.walking = bool(dx or dy)
        if self.walking:
            length = math.hypot(dx, dy) or 1.0
            speed = WALK_SPEED * (SPRINT if keys.is_held(Action.CONFIRM) else 1.0)
            self._walk(dx / length * speed * dt, dy / length * speed * dt)
            # Vertical facing wins on a diagonal, which is the convention every
            # game of this shape uses: it keeps the sprite from flickering
            # between two facings while walking a diagonal.
            if dy:
                self.facing = "down" if dy > 0 else "up"
            elif dx:
                self.facing = "right" if dx > 0 else "left"
            self._walk_clock += dt

        if keys.is_held(Action.SHOULDER_R):
            self.view_height = max(self.view_height * (1.0 - 1.9 * dt), VIEW_MIN)
        elif keys.is_held(Action.CANCEL):
            self.view_height = min(self.view_height * (1.0 + 1.9 * dt), VIEW_MAX)

        self._rest(dt)
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

    #: The tabs of the pause menu, in order.
    TABS = ("MAP", "RIG", "PARTY", "MODE")

    def _menu_input(self, keys) -> None:
        """Drive the pause menu.

        Parameters
        ----------
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        if keys.just_pressed(Action.CANCEL) or keys.just_pressed(Action.MENU):
            self.menu_open = False
            return
        if keys.just_pressed(Action.SHOULDER_R):
            self.menu_tab = (self.menu_tab + 1) % len(self.TABS)
            self.menu_row = 0
            return
        if keys.just_pressed(Action.SHOULDER_L):
            self.menu_tab = (self.menu_tab - 1) % len(self.TABS)
            self.menu_row = 0
            return

        rows = self._menu_rows()
        if rows:
            if keys.just_pressed(Action.DOWN):
                self.menu_row = (self.menu_row + 1) % len(rows)
            if keys.just_pressed(Action.UP):
                self.menu_row = (self.menu_row - 1) % len(rows)
        if keys.just_pressed(Action.CONFIRM):
            self._menu_confirm()

    def _menu_rows(self) -> list[str]:
        """The lines the current tab offers.

        Returns
        -------
        list of str
            Selectable rows; empty for a tab that only displays.
        """
        tab = self.TABS[self.menu_tab]
        if tab == "RIG":
            return [part.summary for part in self.inventory] or ["nothing found yet"]
        if tab == "PARTY":
            return [
                f"{f.creature.name}  {f.hp}/{f.creature.max_hp}" for f in self.team
            ] + [c.name for c in self.collection]
        if tab == "MODE":
            return [review_bridge.TRAINING, review_bridge.EXPERT]
        return []

    def _menu_confirm(self) -> None:
        """Act on the selected row."""
        tab = self.TABS[self.menu_tab]
        if tab == "MAP":
            self.show_map = not self.show_map
            self.menu_open = False
        elif tab == "MODE":
            self.mode = (review_bridge.TRAINING, review_bridge.EXPERT)[self.menu_row]
        elif tab == "RIG" and self.inventory:
            part = self.inventory[min(self.menu_row, len(self.inventory) - 1)]
            # Fitting into the rig and fitting the single filter are the same
            # act from the player's side, so both happen.
            self.rig.fit(part)
            self.equip(part)
        elif tab == "PARTY":
            # Swap a collected creature into the party for the selected slot.
            index = self.menu_row - len(self.team)
            if 0 <= index < len(self.collection) and self.team:
                creature = self.collection.pop(index)
                spent = min(range(len(self.team)), key=lambda i: self.team[i].hp)
                self.collection.append(self.team[spent].creature)
                self.team[spent] = battle_api.Fighter(creature)

    def _rest(self, dt: float) -> None:
        """Recover photons while standing on a recovery station.

        Fluorescence recovery after photobleaching, as a place you walk to.
        Budgets persist between fights, so without somewhere to recover a run
        is a one-way slide into a bleached team.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        """
        col = int(self.iris[0] // T.TILE)
        row = int(self.iris[1] // T.TILE)
        self.resting = self.world.tile_at(col, row) == T.CLINIC
        if not self.resting:
            return
        for fighter in self.team:
            if fighter.hp < fighter.creature.max_hp:
                fighter.hp = min(
                    fighter.creature.max_hp,
                    fighter.hp + max(1, int(fighter.creature.max_hp * 0.6 * dt)),
                )

    def guardian_nm(self, room) -> float:
        """Emission wavelength of whatever guards a room.

        Cached, because the map asks this of every visible room every frame and
        the answer never changes for a given page.

        Parameters
        ----------
        room : Room
            The room.

        Returns
        -------
        float
            Wavelength in nm, or 0 when there is no roster to draw from.
        """
        if not self.pool:
            return 0.0
        cached = self._guardian_nm.get(room.address)
        if cached is None:
            guardian = battle_api.wild_opponent(room.address, room.remoteness, self.pool)
            cached = guardian.creature.emission_nm
            self._guardian_nm[room.address] = cached
        return cached

    def _try_encounter(self) -> None:
        """Start a fight with whatever guards the nearest wild building.

        Only wild rooms hold a guardian: a page somebody has already read is a
        village you walk through, not a place that fights you.
        """
        room = self.here
        if room is None or room.state != WILD or not self.pool:
            return
        x, y = room.position
        if math.hypot(x - self.iris[0], y - self.iris[1]) > T.TILE * 2.2:
            return
        if not any(fighter.alive for fighter in self.team):
            return
        self.encounter_room = room
        self.menu_index = 0
        self.battle = battle_api.Battle(
            self.team,
            battle_api.wild_opponent(room.address, room.remoteness, self.pool),
            loadout=self.loadout,
        )

    def _battle_input(self, keys) -> None:
        """Drive the encounter menu from the pad.

        Parameters
        ----------
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        fight = self.battle
        if fight is None:
            return
        if fight.finished:
            if fight.won and self.encounter_room is not None:
                self._award_loot(self.encounter_room)
                if fight.caught is not None and fight.caught not in self.collection:
                    self.collection.append(fight.caught)
                self._begin_challenge(self.encounter_room)

            if self.challenge is not None:
                self._challenge_input(keys)
                return
            if keys.just_pressed(Action.CONFIRM) or keys.just_pressed(Action.CANCEL):
                self.battle = None
                self.encounter_room = None
                self.verdict = None
            return

        options = self._battle_options()
        if keys.just_pressed(Action.DOWN):
            self.menu_index = (self.menu_index + 1) % len(options)
        if keys.just_pressed(Action.UP):
            self.menu_index = (self.menu_index - 1) % len(options)
        if keys.just_pressed(Action.CONFIRM):
            options[self.menu_index][1]()
        elif keys.just_pressed(Action.CANCEL):
            fight.flee()

    def _begin_challenge(self, room) -> None:
        """Put the page's own question, once, after its guardian is beaten.

        Beating the guardian is spectroscopy and says nothing about whether
        anyone read the page. This is the half that does.

        Parameters
        ----------
        room : Room
            The room that was cleared.
        """
        if self.challenge is not None or self.verdict is not None:
            return
        questions, content_hash = review_bridge.challenge_for(room.path)
        if not questions:
            # A stub has nothing to ask. That is not a pass: it simply cannot
            # be signed off this way, and saying so is better than pretending.
            self.verdict = review_bridge.Verdict(
                False, "Too little here to question.", "unavailable"
            )
            return
        self.challenge = questions[0]
        self.challenge_hash = content_hash
        self.menu_index = 0

    def _challenge_input(self, keys) -> None:
        """Drive the question menu.

        Parameters
        ----------
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        options = self.challenge.options
        if keys.just_pressed(Action.DOWN):
            self.menu_index = (self.menu_index + 1) % len(options)
        if keys.just_pressed(Action.UP):
            self.menu_index = (self.menu_index - 1) % len(options)
        if keys.just_pressed(Action.CANCEL):
            self.challenge = None
            self.verdict = review_bridge.Verdict(False, "You leave it unread.", "wrong")
            return
        if not keys.just_pressed(Action.CONFIRM):
            return

        room = self.encounter_room
        self.verdict = review_bridge.clear_page(
            room.path, self.mode, self.challenge, self.menu_index, self.challenge_hash
        )
        if self.verdict.signed_off:
            room.state = SETTLED
        self.challenge = None

    def _award_loot(self, room) -> None:
        """Give the player what a cleared room yields, once.

        Parameters
        ----------
        room : Room
            The room that was cleared.
        """
        if room.address in self.cleared:
            return
        self.cleared.add(room.address)
        part = gear_api.loot_for(room.address, room.remoteness, self.gear_pool)
        if part is None:
            return
        self.inventory.append(part)
        self.last_loot = part

    def equip(self, part) -> None:
        """Fit a piece of gear into its slot.

        Parameters
        ----------
        part : chisurf.plugins.misc.games.lumis_quest.api.gear.Gear
            What to fit.
        """
        if part.slot == "emission":
            self.loadout.emission = part
        elif part.slot == "detector":
            self.loadout.detector = part

    def _battle_options(self):
        """The menu, as label/action pairs.

        Returns
        -------
        list of tuple
            One entry per choice, in display order.
        """
        fight = self.battle
        options = [("Emit", fight.attack), (f"Collect ({fight.catch_chance():.0%})", fight.catch)]
        for index, fighter in enumerate(fight.team):
            if index != fight.active_index and fighter.alive:
                options.append(
                    (f"Send {fighter.creature.name}", lambda i=index: fight.swap(i))
                )
        options.append(("Withdraw", fight.flee))
        return options

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
                    at=(vx, row * T.TILE - 14.0),
                    height=10.0, align="center", color=(0.52, 0.56, 0.64, 1.0),
                )

        # The glow under each of them is the photon they are; the sprite on top
        # is the body that photon wears.
        frame = int(self._walk_clock * WALK_FPS) % 2 if self.walking else 0
        scene.draw("photon", "halo", at=tuple(self.lumi), size=(T.TILE * 0.7, T.TILE * 0.7),
                   emission_nm=LUMI.wavelength_nm)
        self._sprite(scene, f"lumi_{self._facing_for('lumi')}_{frame}", self.lumi, T.TILE)
        scene.draw("photon", "halo", at=tuple(self.iris), size=(T.TILE * 0.9, T.TILE * 0.9),
                   emission_nm=IRIS.wavelength_nm)
        self._sprite(scene, f"iris_{self._sheet_facing()}_{frame}", self.iris,
                     T.TILE * 1.15, mirror=self.facing == "left")

        if self.battle is not None:
            self._draw_battle(scene, camera, half)
        elif self.menu_open:
            self._draw_menu(scene, camera, half)
        else:
            self._draw_hud(scene, camera, half)

    def _sheet_facing(self) -> str:
        """Which drawn facing to use for Iris.

        Returns
        -------
        str
            ``left`` reuses the ``right`` artwork mirrored, so the atlas holds
            three facings rather than four.
        """
        return "right" if self.facing in ("left", "right") else self.facing

    def _facing_for(self, who: str) -> str:
        """Which drawn facing to use for a follower.

        Parameters
        ----------
        who : str
            Character key.

        Returns
        -------
        str
            ``down`` or ``right``; Lumi has no back view.
        """
        return "right" if self.facing in ("left", "right") else "down"

    def _sprite(self, scene, name: str, at, size: float, mirror: bool = False,
                tint=(1.0, 1.0, 1.0, 1.0)) -> None:
        """Draw one pixel-art sprite.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        name : str
            Sprite name in the atlas.
        at : sequence of float
            Centre in world units.
        size : float
            Edge length in world units.
        mirror : bool, optional
            Flip horizontally. Swapping the uv rectangle's ends mirrors the
            artwork, which is why the atlas needs no left-facing sprites.
        tint : tuple of float, optional
            Multiplied into the artwork; white leaves it alone.
        """
        u0, v0, u1, v1 = self._uvs[name]
        if mirror:
            u0, u1 = u1, u0
        scene.batch.add(
            pos=(float(at[0]), float(at[1])),
            size=(size, size),
            color=tint,
            shape=chigame.SPRITE,
            uv=(u0, v0, u1, v1),
        )

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

        flat = window.reshape(-1)
        count = flat.shape[0]
        instances = np.zeros((count, chigame.FLOATS_PER_INSTANCE), dtype=np.float32)
        instances[:, 0] = grid_x.reshape(-1)
        instances[:, 1] = grid_y.reshape(-1)
        instances[:, 2] = size
        instances[:, 3] = size
        if as_map:
            # A sprite smaller than a pixel is noise, so the map view falls back
            # to one flat colour per tile.
            instances[:, 4:8] = self._palette[flat]
            instances[:, 8] = chigame.RECT
            instances[:, 12:16] = (0.0, 0.0, 1.0, 1.0)
        else:
            instances[:, 4:8] = 1.0
            instances[:, 8] = chigame.SPRITE
            instances[:, 12:16] = self._tile_uv[flat]
        instances[:, 11] = 0.0          # hard edges: this is a tile grid

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
            if room.state == WILD and self.pool:
                # A creature the fitted filter blocks is not rendered as itself:
                # this is the loot loop, and it is why re-walking cleared ground
                # with different optics shows you things that were always there.
                nm = self.guardian_nm(room)
                if nm and not self.loadout.sees(nm):
                    self._sprite(scene, "house_wild", (x, y), T.TILE,
                                 tint=(0.16, 0.17, 0.20, 1.0))
                    continue

            if room.state == SETTLED:
                scene.draw("photon", "halo", at=(x, y), size=(T.TILE * 1.5, T.TILE * 1.5),
                           emission_nm=SETTLED_NM)
            elif room.state == SCOUTED:
                scene.draw("photon", "halo", at=(x, y), size=(T.TILE * 1.1, T.TILE * 1.1),
                           emission_nm=SCOUTED_NM)
            self._sprite(scene, f"house_{room.state}", (x, y), T.TILE,
                         tint=HOUSE_TINT[room.state])

    def _draw_battle(self, scene, camera, half) -> None:
        """Draw the encounter over the world.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        camera : chisurf.gui.chigame.render.Camera
            The view.
        half : numpy.ndarray
            Half-extent in world units.
        """
        fight = self.battle
        cx, cy = float(camera.center[0]), float(camera.center[1])
        width, height = half[0] * 2.0, half[1] * 2.0
        scale = camera.height / VIEW_HEIGHT

        # Near-opaque: an encounter has to be readable, and the terrain showing
        # through the numbers is worse than losing the view of it for a moment.
        scene.draw("ui", "panel", at=(cx, cy), size=(width * 0.94, height * 0.92),
                   color=(0.055, 0.065, 0.085, 0.985))

        # The opponent, drawn in the colour it actually emits.
        enemy = fight.opponent
        top = cy - half[1] * 0.52
        scene.draw("photon", "enemy", at=(cx + half[0] * 0.46, top + 6.0 * scale),
                   size=(15.0 * scale, 15.0 * scale),
                   emission_nm=enemy.creature.emission_nm)
        scene.text(enemy.creature.name, at=(cx - half[0] * 0.10, top - 14.0 * scale),
                   height=13.0 * scale, align="center", color=(0.90, 0.88, 0.82, 1.0))
        self._bar(scene, (cx - half[0] * 0.10, top + 4.0 * scale), 130.0 * scale, 7.0 * scale,
                  enemy.hp / max(enemy.creature.max_hp, 1), (0.90, 0.42, 0.38, 1.0))
        scene.text(f"{enemy.creature.emission_nm:.0f} nm   hp {enemy.hp}",
                   at=(cx - half[0] * 0.10, top + 18.0 * scale),
                   height=9.0 * scale, align="center", color=(0.52, 0.56, 0.64, 1.0))

        # Your active creature.
        active = fight.active
        low = cy + half[1] * 0.10
        scene.draw("photon", "mine", at=(cx - half[0] * 0.48, low + 6.0 * scale),
                   size=(14.0 * scale, 14.0 * scale),
                   emission_nm=active.creature.emission_nm)
        scene.text(active.creature.name, at=(cx + half[0] * 0.10, low - 14.0 * scale),
                   height=13.0 * scale, align="center", color=(0.82, 0.90, 0.96, 1.0))
        self._bar(scene, (cx + half[0] * 0.10, low + 4.0 * scale), 130.0 * scale, 7.0 * scale,
                  active.hp / max(active.creature.max_hp, 1), (0.40, 0.85, 0.70, 1.0))
        scene.text(f"{active.creature.emission_nm:.0f} nm   hp {active.hp}",
                   at=(cx + half[0] * 0.10, low + 18.0 * scale),
                   height=9.0 * scale, align="center", color=(0.52, 0.56, 0.64, 1.0))

        # The last two things that happened, newest at the bottom.
        # Wrapped to the panel: a single long line ran off both edges, and the
        # interesting half of it ("barely couples for 16") was the half cut off.
        lines: list[str] = []
        for turn in fight.log[-2:]:
            lines.extend(_wrap(turn.text, 52))
        for offset, line in enumerate(lines[-3:]):
            scene.text(line, at=(cx, cy + half[1] * 0.30 + offset * 12.0 * scale),
                       height=10.0 * scale, align="center", color=(0.74, 0.78, 0.86, 1.0))

        if self.challenge is not None:
            scene.text("The page puts its question", at=(cx, cy - half[1] * 0.30),
                       height=12.0 * scale, align="center", color=(0.86, 0.84, 0.70, 1.0))
            for offset, line in enumerate(_wrap(self.challenge.prompt, 54)[:4]):
                scene.text(line, at=(cx, cy - half[1] * 0.18 + offset * 12.0 * scale),
                           height=10.5 * scale, align="center", color=(0.80, 0.84, 0.90, 1.0))
            for index, option in enumerate(self.challenge.options):
                selected = index == self.menu_index
                y = cy + half[1] * 0.30 + index * 13.0 * scale
                if selected:
                    scene.draw("ui", "selected", at=(cx - half[0] * 0.34, y),
                               size=(7.0 * scale, 7.0 * scale))
                scene.text(option, at=(cx - half[0] * 0.29, y), height=11.0 * scale,
                           color=(0.94, 0.92, 0.86, 1.0) if selected
                           else (0.56, 0.60, 0.68, 1.0))
            scene.text(f"[{self.mode}]  Cancel to leave it unread",
                       at=(cx, cy + half[1] * 0.62), height=9.5 * scale, align="center",
                       color=(0.50, 0.54, 0.62, 1.0))
            return

        if self.verdict is not None:
            scene.text(self.verdict.message, at=(cx, cy), height=14.0 * scale,
                       align="center",
                       color=(0.45, 0.90, 0.70, 1.0) if self.verdict.signed_off
                       else (0.86, 0.72, 0.45, 1.0))
            scene.text("Confirm to continue", at=(cx, cy + half[1] * 0.20),
                       height=10.0 * scale, align="center", color=(0.50, 0.54, 0.62, 1.0))
            return

        if fight.finished:
            outcome = "The light holds." if fight.won else (
                "You withdraw." if fight.fled else "Your team is spent."
            )
            scene.text(outcome, at=(cx, cy + half[1] * 0.60), height=15.0 * scale,
                       align="center", color=(0.90, 0.84, 0.52, 1.0))
            scene.text("Confirm to continue", at=(cx, cy + half[1] * 0.70),
                       height=10.0 * scale, align="center", color=(0.50, 0.54, 0.62, 1.0))
            return

        for index, (label, _) in enumerate(self._battle_options()):
            selected = index == self.menu_index
            y = cy + half[1] * 0.56 + index * 13.0 * scale
            if selected:
                scene.draw("ui", "selected", at=(cx - half[0] * 0.34, y),
                           size=(7.0 * scale, 7.0 * scale))
            scene.text(label, at=(cx - half[0] * 0.29, y), height=11.0 * scale,
                       color=(0.94, 0.92, 0.86, 1.0) if selected else (0.56, 0.60, 0.68, 1.0))

    def _draw_menu(self, scene, camera, half) -> None:
        """Draw the pause menu.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        camera : chisurf.gui.chigame.render.Camera
            The view.
        half : numpy.ndarray
            Half-extent in world units.
        """
        cx, cy = float(camera.center[0]), float(camera.center[1])
        width, height = half[0] * 2.0, half[1] * 2.0
        scale = camera.height / VIEW_HEIGHT
        scene.draw("ui", "panel", at=(cx, cy), size=(width * 0.94, height * 0.92),
                   color=(0.055, 0.065, 0.085, 0.985))

        for index, label in enumerate(self.TABS):
            selected = index == self.menu_tab
            x = cx - half[0] * 0.62 + index * half[0] * 0.40
            scene.text(label, at=(x, cy - half[1] * 0.62), height=12.0 * scale,
                       align="center",
                       color=(0.95, 0.86, 0.50, 1.0) if selected else (0.45, 0.49, 0.56, 1.0))

        tab = self.TABS[self.menu_tab]
        top = cy - half[1] * 0.44

        if tab == "RIG":
            for offset, slot in enumerate(rig_api.SLOTS):
                part = getattr(self.rig, slot)
                scene.text(f"{slot:<11}{part.name if part else '--'}",
                           at=(cx - half[0] * 0.62, top + offset * 13.0 * scale),
                           height=10.5 * scale, color=(0.78, 0.84, 0.90, 1.0))
            probe = 560.0
            scene.text(
                f"path {self.rig.summary}" if self.rig.parts else "bare path",
                at=(cx - half[0] * 0.62, top + 60.0 * scale), height=9.5 * scale,
                color=(0.55, 0.62, 0.70, 1.0),
            )
            scene.text(
                f"response at {probe:.0f} nm  {self.rig.response(probe):.2f}",
                at=(cx - half[0] * 0.62, top + 74.0 * scale), height=9.5 * scale,
                color=(0.55, 0.62, 0.70, 1.0),
            )

        rows = self._menu_rows()
        start = top + (92.0 if tab == "RIG" else 0.0) * scale
        window = rows[max(0, self.menu_row - 6): max(0, self.menu_row - 6) + 8]
        base = max(0, self.menu_row - 6)
        for offset, row in enumerate(window):
            selected = base + offset == self.menu_row
            y = start + offset * 13.0 * scale
            if selected:
                scene.draw("ui", "selected", at=(cx - half[0] * 0.66, y),
                           size=(7.0 * scale, 7.0 * scale))
            scene.text(row, at=(cx - half[0] * 0.62, y), height=10.5 * scale,
                       color=(0.94, 0.92, 0.86, 1.0) if selected else (0.56, 0.60, 0.68, 1.0))

        scene.text("L/R tab   Up/Down choose   Confirm use   Cancel close",
                   at=(cx, cy + half[1] * 0.66), height=9.5 * scale, align="center",
                   color=(0.48, 0.52, 0.60, 1.0))

    def _bar(self, scene, at, width: float, height: float, fraction: float, colour) -> None:
        """Draw a proportion bar.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        at : tuple of float
            Centre in world units.
        width, height : float
            Size in world units.
        fraction : float
            0..1 filled.
        colour : tuple of float
            Fill colour.
        """
        fraction = max(0.0, min(float(fraction), 1.0))
        scene.draw("ui", "bar", at=at, size=(width, height), color=(0.16, 0.17, 0.20, 1.0))
        if fraction > 0.0:
            scene.draw(
                "ui", "bar",
                at=(at[0] - width * (1.0 - fraction) * 0.5, at[1]),
                size=(width * fraction, height),
                color=colour,
            )

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
            at=(left + 14.0 * scale, top + 54.0 * scale),
            height=10.0 * scale, color=(0.55, 0.60, 0.68, 1.0),
        )

        land = self.land
        if land is not None:
            scene.text(
                land.title,
                at=(left + 14.0 * scale, top + 20.0 * scale),
                height=15.0 * scale, color=(0.82, 0.78, 0.62, 1.0),
            )
            if land.subtitle:
                scene.text(
                    land.subtitle,
                    at=(left + 14.0 * scale, top + 36.0 * scale),
                    height=9.5 * scale, color=(0.44, 0.46, 0.52, 1.0),
                )

        beat = self.story.current
        if beat is not None:
            # Along the bottom, above the room name: the top band already holds
            # the counts and the land, and all three collided there.
            scene.text(
                beat.headline,
                at=(camera.center[0], bottom - 48.0 * scale),
                height=10.5 * scale, align="center", color=(0.62, 0.70, 0.80, 1.0),
            )

        scene.text(
            self.loadout.summary,
            at=(left + 14.0 * scale, top + 70.0 * scale),
            height=9.5 * scale, color=(0.62, 0.70, 0.66, 1.0),
        )
        scene.text(
            f"[{self.mode}]",
            at=(left + 14.0 * scale, top + 112.0 * scale),
            height=9.5 * scale,
            color=(0.90, 0.78, 0.45, 1.0) if self.mode == review_bridge.EXPERT
            else (0.50, 0.56, 0.64, 1.0),
        )
        if self.collection:
            scene.text(
                f"collected {len(self.collection)}",
                at=(left + 14.0 * scale, top + 84.0 * scale),
                height=9.5 * scale, color=(0.72, 0.78, 0.62, 1.0),
            )
        if self.resting:
            scene.text(
                "recovering",
                at=(left + 14.0 * scale, top + 98.0 * scale),
                height=9.5 * scale, color=(0.45, 0.90, 0.75, 1.0),
            )
        if self.last_loot is not None:
            scene.text(
                f"found {self.last_loot.summary}",
                at=(camera.center[0], bottom - 62.0 * scale),
                height=10.0 * scale, align="center", color=(0.90, 0.84, 0.52, 1.0),
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
