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
import time

import numpy as np

from chisurf.gui import chigame
from chisurf.gui.chigame.input import Action

from ...characters import IRIS, LUMI, draw as draw_character
from ..api import tiles as T
from ..api import agents as agents_api
from ..api import battle as battle_api
from ..api import bestiary as bestiary_api
from ..api import context as context_api
from ..api import darkworld as darkworld_api
from ..api import engine as engine_api
from ..api import tiers as tiers_api
from ..api import findings as findings_api
from ..api import npcs as npcs_api
from ..api import gear as gear_api
from ..api import roster as roster_api
from ..api import providers as providers_api
from ..api import review_bridge
from ..api import rig as rig_api
from ..api import farm as farm_api
from ..api import personas as personas_api
from ..api import save as save_api
from ..api import tutorial as tutorial_api
from ..api.story import EPILOGUES, ORDERS, PROLOGUE, Story, cleared_in_lands
from ..api.world import SCOUTED, SETTLED, WILD, WITHERED, World, build_world
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
    # The wider overworld.
    T.SAND: "sand",
    T.MARSH: "marsh",
    T.CLIFF: "cliff",
    T.CAVE: "cave",
    T.PLAZA: "plaza",
    T.GARDEN: "garden",
    T.FLOWERS: "flowers",
    T.DOCK: "dock",
    # Premises sit on paving and are drawn over it, so the tile under each is
    # the square it stands on rather than a second copy of the building.
    T.WELL: "plaza",
    T.TAVERN: "plaza",
    T.SHOP: "plaza",
    T.SMITHY: "plaza",
    T.SHRINE: "plaza",
    T.HALL: "plaza",
    T.LANTERN: "floor",
    T.SIGN: "floor",
    T.STALL: "floor",
    T.FENCE: "grass",
    # The dark manifold.
    T.ASH: "ash",
    T.TAR: "tar",
    T.DEADTREE: "deadtree",
    T.RUIN: "ash",
    T.RIFT: "rift",
}

#: Tiles whose sprite is a *building* drawn over the ground tile above, and the
#: sprite that draws it. Kept apart from :data:`TILE_SPRITES` because the tile
#: layer is one textured quad per cell and these need a second, taller one.
STRUCTURE_SPRITES = {
    T.WELL: "well",
    T.TAVERN: "tavern",
    T.SHOP: "shop",
    T.SMITHY: "smithy",
    T.SHRINE: "shrine",
    T.HALL: "hall",
    T.LANTERN: "lantern",
    T.SIGN: "sign",
    T.STALL: "stall",
    T.FENCE: "fence",
    T.RUIN: "ruin",
}

#: A house is one drawing, tinted by whether anyone has read the page. Dark for
#: untouched, cool for scouted-but-unconfirmed, warm for settled — and a sick
#: brown for withered, the plot that was tended and has rotted under its
#: sign-off. Crop rot the gardener cannot see is crop rot nobody fixes.
HOUSE_TINT = {
    # Not so dark that the house stops reading as a house: most of a town is
    # unread, and a town of murk is a town nobody wants to walk through. The
    # difference from settled is warmth and the lit windows, not brightness.
    WILD: (0.74, 0.76, 0.86, 1.0),
    WITHERED: (0.80, 0.62, 0.42, 1.0),
    SCOUTED: (0.78, 0.92, 1.00, 1.0),
    SETTLED: (1.00, 0.97, 0.84, 1.0),
}

#: How many tiles tall anything built is drawn. A building the size of its own
#: tile sits inside the ground; at one and a half it stands on it and overlaps
#: the row behind, which is the whole reason a 16-bit town reads as a town.
BUILDING_HEIGHT = 1.5

#: Structures that are *ground furniture* rather than buildings, and so are
#: drawn at their own tile size. A fence post standing a tile and a half tall
#: is a fence you cannot see over.
FLAT_STRUCTURES = frozenset({T.FENCE, T.SIGN})

#: Frames per second of the walk cycle.
WALK_FPS = 6.0

#: An emissary is tinted -- and haloed -- in the colour of their doctrine, so
#: the three are tellable apart from across a field.
EMISSARY_NM = {"rigour": 620.0, "clarity": 470.0, "discovery": 530.0}
EMISSARY_TINT = {
    "rigour": (1.00, 0.82, 0.66, 1.0),
    "clarity": (0.72, 0.88, 1.00, 1.0),
    "discovery": (0.74, 1.00, 0.80, 1.0),
}

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
    T.SAND: (0.500, 0.455, 0.330, 1.0),
    T.MARSH: (0.135, 0.165, 0.110, 1.0),
    T.CLIFF: (0.290, 0.285, 0.275, 1.0),
    T.CAVE: (0.040, 0.035, 0.045, 1.0),
    T.PLAZA: (0.330, 0.325, 0.310, 1.0),
    T.GARDEN: (0.200, 0.145, 0.095, 1.0),
    T.FLOWERS: (0.150, 0.205, 0.140, 1.0),
    T.DOCK: (0.260, 0.215, 0.150, 1.0),
    T.WELL: (0.330, 0.325, 0.310, 1.0),
    T.TAVERN: (0.420, 0.240, 0.200, 1.0),
    T.SHOP: (0.400, 0.300, 0.200, 1.0),
    T.SMITHY: (0.300, 0.260, 0.230, 1.0),
    T.SHRINE: (0.560, 0.545, 0.510, 1.0),
    T.HALL: (0.600, 0.520, 0.300, 1.0),
    T.LANTERN: (0.480, 0.400, 0.220, 1.0),
    T.SIGN: (0.260, 0.220, 0.170, 1.0),
    T.STALL: (0.380, 0.240, 0.210, 1.0),
    T.FENCE: (0.210, 0.180, 0.140, 1.0),
    T.ASH: (0.240, 0.235, 0.245, 1.0),
    T.TAR: (0.045, 0.040, 0.060, 1.0),
    T.DEADTREE: (0.170, 0.160, 0.170, 1.0),
    T.RUIN: (0.200, 0.195, 0.200, 1.0),
    T.RIFT: (0.560, 0.360, 0.780, 1.0),
}

def _trait_name(key: str) -> str:
    """Display name of a body's own trait.

    Parameters
    ----------
    key : str
        A key of :data:`..api.bestiary.TRAITS`.

    Returns
    -------
    str
        The trait's name, or the key when it is not one.
    """
    trait = bestiary_api.TRAITS.get(key)
    return trait.name if trait is not None else key


def _emission_tint(nanometres: float) -> tuple[float, float, float, float]:
    """Approximate the colour of an emission wavelength, for tinting a sprite.

    A marked animal is drawn in the colour of whatever is fixed into it, so the
    pale body art has to be multiplied by something. This is a coarse
    wavelength-to-RGB ramp -- coarse is right, because it is read at 16 pixels
    across and only has to say "that one is red and that one is green".

    Parameters
    ----------
    nanometres : float
        Emission maximum. Zero, for an unmarked animal, reads as plain white.

    Returns
    -------
    tuple of float
        RGBA in 0..1, never fully dark in any channel: a sprite tinted to black
        in two channels is a silhouette, and the player still has to see the
        animal.
    """
    if nanometres <= 0.0:
        return (0.90, 0.90, 0.88, 1.0)
    stops = (
        (420.0, (0.55, 0.35, 0.95)),
        (470.0, (0.35, 0.55, 1.00)),
        (500.0, (0.30, 0.85, 0.95)),
        (530.0, (0.40, 0.95, 0.50)),
        (570.0, (0.95, 0.92, 0.40)),
        (600.0, (1.00, 0.68, 0.30)),
        (640.0, (1.00, 0.40, 0.35)),
        (700.0, (0.85, 0.30, 0.45)),
        (780.0, (0.60, 0.25, 0.40)),
    )
    if nanometres <= stops[0][0]:
        red, green, blue = stops[0][1]
    elif nanometres >= stops[-1][0]:
        red, green, blue = stops[-1][1]
    else:
        red, green, blue = stops[-1][1]
        for (low, lowc), (high, highc) in zip(stops, stops[1:]):
            if low <= nanometres <= high:
                t = (nanometres - low) / (high - low)
                red, green, blue = (a + (b - a) * t for a, b in zip(lowc, highc))
                break
    return (red, green, blue, 1.0)


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


#: Selectable control schemes. Rebinding every key individually needs raw-key
#: capture the abstract controller deliberately does not expose, so the option
#: offered is the one players actually want: a whole scheme at once.
SCHEMES: dict[str, dict[str, Action]] = {
    "arrows": {
        "ArrowUp": Action.UP, "ArrowDown": Action.DOWN,
        "ArrowLeft": Action.LEFT, "ArrowRight": Action.RIGHT,
        "Shift": Action.CONFIRM, " ": Action.CONFIRM,
        "q": Action.SHOULDER_L, "e": Action.SHOULDER_R,
        "Backspace": Action.CANCEL, "Tab": Action.MENU,
    },
    "wasd": {
        "w": Action.UP, "s": Action.DOWN, "a": Action.LEFT, "d": Action.RIGHT,
        " ": Action.CONFIRM, "Shift": Action.CONFIRM,
        "q": Action.SHOULDER_L, "e": Action.SHOULDER_R,
        "Backspace": Action.CANCEL, "Tab": Action.MENU,
    },
    "left-handed": {
        "i": Action.UP, "k": Action.DOWN, "j": Action.LEFT, "l": Action.RIGHT,
        " ": Action.CONFIRM, "Enter": Action.CONFIRM,
        "u": Action.SHOULDER_L, "o": Action.SHOULDER_R,
        "Backspace": Action.CANCEL, "Tab": Action.MENU,
    },
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
    save_path : pathlib.Path, optional
        Where the run is stored. Omitted uses the per-user file; tests pass a
        temporary one so they never touch a real save.
    docs_root : pathlib.Path, optional
        Corpus to rebuild from when the wilderness is regenerated. Omitted uses
        the documentation the help browser reads.
    """

    title = "Lumis Quest"
    background = (0.020, 0.024, 0.030, 1.0)

    def __init__(self, world: World | None = None, save_path=None, docs_root=None) -> None:
        self._world = world
        # Where to rebuild from. Without it a game handed a prebuilt world has
        # no idea which corpus it came from, and regenerating silently switches
        # to the installed documentation instead.
        self._docs_root = docs_root
        # Injectable so a test never reads or writes the player's real run.
        self._save_path = save_path

    def setup(self, host) -> None:
        """Bind the controller and start loading.

        The world is **not** built here. Building it takes over a second, and
        doing that inside setup means the window appears already frozen with
        nothing on it. The stages run one per frame instead, so the first thing
        drawn is a loading screen that says what is happening.

        Parameters
        ----------
        host : chisurf.gui.chigame.game.GameHost
            The host running this game.
        """
        self.host = host
        host.keys.bindings = dict(BINDINGS)
        self.scheme = "arrows"
        self.walk_speed = WALK_SPEED
        self.phase = "loading"
        self.load_step = 0
        self.load_note = "waking"
        self.prologue_index = 0
        self.seed = ""
        self._pending = self._world
        self._boot()

    def _boot(self) -> None:
        """Prepare a bare game so the loading screen has something to draw."""
        self.world = self._pending if self._pending is not None else World()
        self.story = Story(self.world)
        self.tutorial = tutorial_api.Tutorial()
        self.people = []
        self.iris = [0.0, 0.0]
        self.lumi = [0.0, 0.0]
        self._clock = 0.0

    #: What each loading stage is called, in order.
    #: The first is deliberately empty work. Without it the heaviest stage runs
    #: before anything has been drawn, and the loading screen appears only after
    #: the freeze it exists to explain.
    LOAD_STAGES = ("waking", "reading the archive", "raising the lands",
                   "waking the living", "recalling your run")

    def _load_next(self) -> None:
        """Run one loading stage.

        Split so that each is a frame the player sees rather than one long
        freeze with nothing on screen.
        """
        if self.load_step == 0:
            pass  # a frame with nothing to do, so the screen is on before the work
        elif self.load_step == 1:
            if self._pending is None:
                self.world = build_world(self._docs_root, seed=self.seed)
            self.story = Story(self.world)
        elif self.load_step == 2:
            self._prepare_visuals()
        elif self.load_step == 3:
            self.people = npcs_api.populate(self.world)
            self._build_society()
        elif self.load_step == 4:
            self._restore()
            start = self.world.spawn() if self._resume is None else self._resume
            self.iris = [float(start[0]), float(start[1])]
            self.lumi = [self.iris[0] - LUMI_TRAIL, self.iris[1]]
            self.host.camera.center[:] = self.iris
            self.host.camera.height = self.view_height
            # Every run opens on the title: a game has a front door, and the
            # door is where Continue, a new journey and the controls live.
            self.phase = "title"
            self.title_index = 0
            self.title_confirm_new = False
            return
        self.load_step += 1
        self.load_note = self.LOAD_STAGES[min(self.load_step, len(self.LOAD_STAGES) - 1)]

    def finish_loading(self, skip_prologue: bool = True) -> None:
        """Run every loading stage at once.

        The staged loader exists so a player sees progress rather than a frozen
        window. A caller that does not need to *watch* it -- a test, a headless
        capture -- wants the world ready on the next line instead.

        Parameters
        ----------
        skip_prologue : bool, optional
            Also step past the title and the opening: continue a saved run, or
            start straight into play with the companion already at heel. False
            stops at the title screen, where a real session begins.
        """
        guard = 0
        while self.phase == "loading" and guard < 32:
            self._load_next()
            guard += 1
        if skip_prologue and self.phase == "title":
            if self._resume is not None:
                self._continue_run()
            else:
                self._quick_start()

    def _continue_run(self) -> None:
        """Resume the saved run from the title."""
        self.phase = "play"

    def _quick_start(self) -> None:
        """Start playing without the opening -- the test and capture path.

        The scripted awakening exists for players; a harness that wants a
        walkable world on the next line gets the pre-arc state: companion at
        heel, waking already witnessed.
        """
        self.story.has_lumi = True
        self.story.witness("wake")
        self.story.witness("the-hound")
        self.phase = "play"

    def _begin_journey(self) -> None:
        """Start a fresh run: the opening cards, then the waking scene.

        Resets everything a run owns, stages the awakening cast, and hands
        the player to the prologue. The old save is overwritten at once --
        the title menu asked before letting it get this far.
        """
        self.team = [battle_api.Fighter(b) for b in bestiary_api.starters(self.pool)]
        self.bodies = []
        self.labels = []
        self.dark = False
        self.inventory = []
        self.loadout = gear_api.starting_loadout(self.gear_pool)
        self.rig = rig_api.Rig()
        self.lab = farm_api.Lab()
        self.cleared = set()
        self.last_loot = None
        self.mode = review_bridge.TRAINING
        self.story = Story(self.world)
        self.tutorial = tutorial_api.Tutorial()
        self.menu_open = False
        self.speaking = None
        self.screen = None
        self._resume = None
        self._rebuild_context()

        self.people = [npc for npc in self.people if npc.role not in ("elder", "lumi")]
        spot, cast = npcs_api.awakening_cast(self.world)
        self.people.extend(cast)
        self.iris = [float(spot[0]), float(spot[1])]
        self.lumi = list(self.iris)
        self.host.camera.center[:] = self.iris

        self.save_run()
        self.prologue_index = 0
        self._wake_pending = True
        self.phase = "prologue"

    def _after_prologue(self) -> None:
        """Leave the opening cards for the world.

        A fresh journey wakes with the keeper already speaking -- the scene
        the cards were setting up. A replayed opening returns to play as it
        always did.
        """
        self.phase = "play"
        if not getattr(self, "_wake_pending", False):
            return
        self._wake_pending = False
        elder = next((npc for npc in self.people if npc.role == "elder"), None)
        if elder is not None:
            self._talk_to(elder)

    def _prepare_visuals(self) -> None:
        """Build the atlas and the palettes."""
        host = self.host
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
        # Variant table: same as the base, except where a second drawing
        # exists. Grass alternates by position so the field does not read as a
        # grid; water alternates by position *and* time so it moves.
        self._tile_uv_alt = self._tile_uv.copy()
        self._tile_uv_alt[T.GRASS] = self._uvs["grass2"]
        self._tile_uv_alt[T.WATER] = self._uvs["water2"]

        self.facing = "down"
        self.walking = False
        self._walk_clock = 0.0

        # The team's photon budgets persist between fights: a single encounter
        # is winnable three-on-one, so the danger is attrition across a run.
        self.pool = [c for c in roster_api.load_roster() if not c.estimated]
        self.team = [battle_api.Fighter(b) for b in bestiary_api.starters(self.pool)]
        #: Bodies and labels are collected *separately*: you strip a dye off a
        #: marked animal, the animal walks away, and the two are recombined by
        #: hand. That split is the build game.
        self.bodies: list = []
        self.labels: list = []
        #: Whether Iris is standing in the dark manifold. Every tile read,
        #: collision and draw goes through this, so crossing is one flag.
        self.dark = False
        self.battle: battle_api.Battle | None = None
        #: A Warden fight is the same fight with a name on it.
        self.warden_fight = ""
        self.menu_index = 0
        self.encounter_room = None

        self.gear_pool = gear_api.load_gear()
        self.loadout = gear_api.starting_loadout(self.gear_pool)
        self.inventory: list = []
        self.last_loot = None
        self.cleared: set[str] = set()
        # Training teaches; expert reviews. They must not grant the same thing.
        self.rig = rig_api.Rig()
        # One menu with tabs, rather than more chords. Nine actions is the whole
        # controller, and the overworld had already spent all of them -- so
        # every extra screen has to live behind Menu, which is the convention
        # this kind of game uses anyway.
        self.menu_open = False
        self.menu_tab = 0
        self.menu_row = 0
        #: Which team slot the build screen is editing.
        self.party_slot = 0
        self.mode = review_bridge.TRAINING
        # Everything a character says and everything talking to them does is
        # data (``data/*.json``), run by the engine. Nothing in this class
        # knows what a tavern is.
        self.ctx = context_api.GameContext(
            world=self.world, story=self.story, team=self.team,
            bodies=[], labels=[], inventory=self.inventory,
            loadout=self.loadout, cleared=[],
        )
        self.runner = engine_api.Runner(engine_api.scenes(), self.ctx)
        self.screen = None
        # Off by default. A configured provider would otherwise mean the first
        # visit to every page makes a network call mid-encounter, which is both
        # a surprise and a stall. Opt in from the MODE tab; the cache means only
        # the first visit to a page ever pays for it.
        self.use_model = False
        # Flagging: a span picked with the pad, then a category. No typing, and
        # the record is machine-checkable rather than prose.
        self.flagging = False
        self.flag_spans: list[str] = []
        self.flag_span_index = 0
        self.flag_category_index = 0
        self.flag_stage = "span"
        self.findings_path = None
        self.challenge = None
        self.challenge_hash = ""
        self.verdict = None
        self._guardian_nm: dict[str, float] = {}
        self.resting = False
        # The world was a diagram until something lived on it. Dialogue is a
        # sequence of screens now, and talking to an emissary can end in a
        # pledge -- and all of that is a script, not a branch in here.
        self.speaking = None
        #: Model-voiced dialogue for the current speaker, when the model is on
        #: and has already found this character's voice; None speaks the
        #: authored lines.
        self._speaking_lines = None
        #: Fetches and gates character voices off the frame loop. Built lazily
        #: so a run with the model off never touches provider settings.
        self._director = None
        # The bench: cultures maturing on a real-world clock.
        self.lab = farm_api.Lab()
        # Title-screen state.
        self.title_index = 0
        self.title_confirm_new = False
        self._has_save = False
        self._wake_pending = False
        self.epilogue_index = 0


    def _restore(self) -> None:
        """Load a saved run, if there is one.

        Everything is stored by identifier, so a creature whose stats have since
        been corrected in the database comes back with the corrected ones.
        """
        self._resume = None
        state = save_api.RunState.load(self._save_path)
        self._has_save = bool(state.team)
        if not state.team:
            return
        creatures = save_api.creatures_by_id(self.pool)
        team = []
        for species_key, probe_id, hp in state.team:
            species = bestiary_api.BY_KEY.get(species_key)
            if species is None:
                continue
            beast = bestiary_api.Beast(species=species, label=creatures.get(probe_id))
            team.append(battle_api.Fighter(beast, hp=hp))
        if not team:
            return
        self.team = team
        self.bodies = [
            bestiary_api.BY_KEY[key] for key in state.bodies if key in bestiary_api.BY_KEY
        ]
        self.labels = [
            creatures[probe_id] for probe_id in state.labels if probe_id in creatures
        ]
        self.dark = bool(state.dark)
        self.story.seals = {key for key in state.seals if key in tiers_api.BY_KEY}
        self.story.unbound = int(state.unbound)
        parts = save_api.gear_by_id(self.gear_pool)
        self.inventory = [parts[probe_id] for probe_id in state.inventory if probe_id in parts]
        self.loadout = save_api.restore_loadout(state, self.gear_pool)
        self.cleared = set(state.cleared)
        self.tutorial = tutorial_api.Tutorial(set(state.tutorial))
        if not state.tutorial and state.cleared:
            # A save from before the tutorial existed, on a run that has
            # already cleared rooms: this player does not need teaching.
            self.tutorial.finish()
        self.lab = farm_api.Lab.from_rows(state.lab)
        self.story.has_lumi = state.has_lumi
        self.story.seen = set(state.story_seen)
        if not state.story_seen:
            # A save from before the waking act: this run has already begun,
            # so it does not replay its own opening.
            self.story.witness("wake")
        if state.order:
            try:
                self.story.choose(state.order)
            except KeyError:
                pass
            self.story.pledge_baseline = state.pledge_baseline
        if state.position != (0.0, 0.0):
            self._resume = state.position
        self._rebuild_context()

    def snapshot(self) -> save_api.RunState:
        """Capture the run for saving.

        Returns
        -------
        chisurf.plugins.misc.games.lumis_quest.api.save.RunState
            The current run.
        """
        return save_api.RunState(
            position=(float(self.iris[0]), float(self.iris[1])),
            dark=bool(self.dark),
            team=[
                (f.beast.species.key,
                 f.creature.probe_id if f.creature is not None else -1,
                 int(f.hp))
                for f in self.team
            ],
            bodies=[species.key for species in self.bodies],
            labels=[label.probe_id for label in self.labels],
            seals=sorted(self.story.seals),
            unbound=int(self.story.unbound),
            inventory=[part.probe_id for part in self.inventory],
            emission_id=self.loadout.emission.probe_id if self.loadout.emission else None,
            detector_id=self.loadout.detector.probe_id if self.loadout.detector else None,
            cleared=sorted(self.cleared),
            order=self.story.chosen_order,
            tutorial=sorted(self.tutorial.done),
            has_lumi=self.story.has_lumi,
            story_seen=sorted(self.story.seen),
            pledge_baseline=self.story.pledge_baseline,
            lab=self.lab.as_rows(),
        )

    def save_run(self) -> None:
        """Write the run to disk."""
        self.snapshot().save(self._save_path)

    @property
    def music_context(self) -> str:
        """Which piece should be playing.

        The game had one context and therefore one loop, everywhere, forever --
        which is most of why the soundtrack was unbearable however good the
        tune was. Where you are is now what you hear.

        Returns
        -------
        str
            One of :data:`chisurf.gui.chigame.audio.CONTEXTS`.
        """
        if getattr(self, "battle", None) is not None:
            return "battle"
        if getattr(self, "dark", False):
            return "underworld"
        if getattr(self, "phase", "") in ("title", "prologue", "epilogue"):
            return "town"
        world = getattr(self, "world", None)
        if world is not None and world.villages:
            if world.village_at(self.iris[0], self.iris[1]) is not None:
                return "town"
        return "overworld"

    @property
    def grid_array(self):
        """The tile array the player is actually standing in.

        Returns
        -------
        numpy.ndarray
            The dark manifold when Iris has crossed, else the lit world.
        """
        if self.dark and self.world.dark.size:
            return self.world.dark
        return self.world.array

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
        if self.phase == "loading":
            self._load_next()
            return
        if self.phase == "title":
            self._title_input(keys)
            return
        if self.phase == "prologue":
            if keys.just_pressed(Action.CONFIRM) or keys.just_pressed(Action.CANCEL):
                self.prologue_index += 1
                if self.prologue_index >= len(PROLOGUE) or keys.just_pressed(Action.CANCEL):
                    self._after_prologue()
            return
        if self.phase == "epilogue":
            if keys.just_pressed(Action.CONFIRM) or keys.just_pressed(Action.CANCEL):
                self.epilogue_index += 1
                if self.epilogue_index >= len(self._epilogue_cards()):
                    self.story.witness("dawn")
                    self.phase = "play"
            return

        # The teaching sequence watches the same state the story does, and it
        # watches through battles too -- half its steps complete inside one.
        self.tutorial.observe(self)

        # The doctrine work counts cleared rooms in the order's own lands;
        # clears live in the run, so the story is fed rather than left to ask.
        if self.story.chosen_order is not None:
            self.story.doctrine_count = cleared_in_lands(
                self.cleared, self.story.chosen_order
            )
            beat = self.story.current
            if (beat is not None and beat.key == "the-dawn"
                    and self.battle is None and not self.menu_open
                    and self.speaking is None):
                self.epilogue_index = 0
                self.phase = "epilogue"
                return

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
        if self.speaking is not None:
            self._dialogue_input(keys)
            return
        if keys.just_pressed(Action.SHOULDER_L):
            neighbour = npcs_api.nearest(self.people, *self.iris)
            door = self._door_scene()
            if self._overhear():
                pass
            elif neighbour is not None and neighbour.kind != "beast":
                self._talk_to(neighbour)
            elif door:
                self._play_scene(door)
            else:
                self._try_encounter()

        dx, dy = keys.axis()
        self.walking = bool(dx or dy)
        if self.walking:
            length = math.hypot(dx, dy) or 1.0
            speed = self.walk_speed * (SPRINT if keys.is_held(Action.CONFIRM) else 1.0)
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

        self._clock += dt
        npcs_api.update(self.people, self.world, dt, self._clock, near=tuple(self.iris),
                        dark=self.dark)
        if not self.dark:
            # The town gets on with its day. What it gossips about is read off
            # the run, so nobody discusses a probe who takes labels off before
            # there is one.
            self.society.mood = agents_api.mood_from(self.story, self.story.unbound)
            self.society.step(dt, near=tuple(self.iris))
        self._rest(dt)
        self.story.observe(self.here)

        # A beast you walk into is a fight, so the wilds are dangerous in a way
        # that standing beside a building is not.
        if self.battle is None and self.pool:
            for npc in self.people:
                if npc.kind == "beast" and npc.distance_to(*self.iris) < T.TILE * 0.7:
                    self._try_encounter(force=True)
                    break

        # Lumi moves toward a point behind Iris rather than to Iris, so the two
        # never collapse into one blob. Before the hound is befriended it is
        # not at heel at all -- it lies out in the world, waiting to be found.
        if self.story.has_lumi:
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

    def _voice_lines(self, npc) -> tuple[str, ...] | None:
        """Ask the director for a model voice, without ever blocking.

        Parameters
        ----------
        npc : chisurf.plugins.misc.games.lumis_quest.api.npcs.Npc
            Who is about to speak.

        Returns
        -------
        tuple of str or None
            Gated model lines if already fetched; ``None`` speaks the authored
            lines while the voice is (maybe) being found in the background.
        """
        if not self.use_model:
            return None
        land = self.land
        village = min(
            self.world.villages,
            key=lambda v: (v.position[0] - npc.x) ** 2 + (v.position[1] - npc.y) ** 2,
            default=None,
        ) if self.world.villages else None
        persona = personas_api.persona_for(
            npc,
            land_title=land.title if land is not None else "",
            prosperity=village.prosperity if village is not None else None,
            counts=self.world.counts(),
        )
        if persona is None:
            return None
        if self._director is None:
            self._director = personas_api.DialogueDirector()
        return self._director.lines_for(persona)

    def _build_society(self) -> None:
        """Give the population an inner life.

        The town's day is deterministic and runs with no provider at all; the
        model, when one is configured, only writes the words. That split is why
        this can be switched on by default without any run ever waiting on a
        network call.
        """
        self.society = agents_api.Society(self.world, self.people, voice=self._exchange)
        self._overheard = None

    def _exchange(self, one, other, topic: str):
        """Model-written words for two inhabitants talking to each other.

        Never blocks: a miss starts a background fetch and the authored
        exchange stands until it lands, exactly as a single character's voice
        does.

        Parameters
        ----------
        one, other : chisurf.plugins.misc.games.lumis_quest.api.npcs.Npc
            Who is talking.
        topic : str
            What about.

        Returns
        -------
        list of tuple or None
            ``(speaker, line)``, or ``None`` to keep the authored exchange.
        """
        if not self.use_model:
            return None
        gist = agents_api.Society(self.world, []).data.get("topics", {}).get(topic, {})
        persona = personas_api.exchange_persona(
            one, other, topic, gist=(gist.get("openers") or [topic])[0]
        )
        if self._director is None:
            self._director = personas_api.DialogueDirector()
        lines = self._director.lines_for(persona)
        if not lines:
            return None
        speakers = (one.name, other.name)
        return [(speakers[index % 2], line) for index, line in enumerate(lines)]

    def _rebuild_context(self) -> None:
        """Point the script facade at the current run.

        Everything the engine reads lives somewhere else -- the team in the
        game loop, the arc in the story, the corpus in the world -- so the
        facade is rebuilt whenever one of those is replaced wholesale (a fresh
        journey, a restored save) rather than mutated in place.
        """
        self.ctx = context_api.GameContext(
            world=self.world, story=self.story, team=self.team,
            bodies=self.bodies, labels=self.labels, inventory=self.inventory,
            loadout=self.loadout, cleared=sorted(self.cleared), dark=self.dark,
        )
        self.runner = engine_api.Runner(engine_api.scenes(), self.ctx)

    def _scene_for(self, npc) -> tuple[str, dict, str]:
        """Which script a character runs, and what they bring to it.

        The mapping is one dict lookup on the NPC's declared role. There is no
        branch here on what kind of building it is: a new premises is a new
        scene in ``data/dialogue.json`` and a role string in :mod:`..api.npcs`.

        Parameters
        ----------
        npc : chisurf.plugins.misc.games.lumis_quest.api.npcs.Npc
            Whoever is being spoken to.

        Returns
        -------
        tuple
            ``(scene id, authored line bundles, subject)``.
        """
        voiced = self._voice_lines(npc)
        lines = {"lines": voiced or npc.dialogue}
        role = npc.role or npc.kind
        if role.startswith("warden:"):
            key = role.split(":", 1)[1]
            warden = tiers_api.BY_KEY.get(key)
            if warden is not None:
                lines = {"lines": voiced or warden.lines, "after": (warden.after,)}
            return ("warden", lines, key)
        if role.startswith("emissary:"):
            return ("emissary", lines, role.split(":", 1)[1])
        if role in engine_api.scenes():
            return (role, lines, "")
        if npc.kind in engine_api.scenes():
            return (npc.kind, lines, "")
        return ("talk", lines, "")

    def _talk_to(self, npc) -> None:
        """Begin a conversation.

        Parameters
        ----------
        npc : chisurf.plugins.misc.games.lumis_quest.api.npcs.Npc
            Whoever is being spoken to.
        """
        self.speaking = npc
        self.menu_index = 0
        self.ctx.village = self.world.village_at(*self.iris)
        self.ctx.dark = self.dark
        self.ctx.cleared = sorted(self.cleared)
        self.ctx.tick += 1
        scene_id, lines, subject = self._scene_for(npc)
        self._sound("talk", 620.0)
        self.screen = self.runner.start(scene_id, who=npc.name, lines=lines,
                                        subject=subject)
        self._after_step(npc)

    def _overhear(self) -> bool:
        """Walk in on two people talking, if there are two people talking.

        Returns
        -------
        bool
            True when a conversation was opened, so the caller stops looking
            for something else to do with the button.
        """
        if self.dark:
            return False
        mind = self.society.conversation_near(*self.iris)
        if mind is None or mind.partner is None:
            return False
        self._overheard = mind
        lines = tuple(f"{who}: {what}" for who, what in self.society.transcript(mind))
        if not lines:
            return False
        self.speaking = None
        self.menu_index = 0
        self.ctx.tick += 1
        self.screen = self.runner.start("overheard", who="", lines={"lines": lines})
        self._after_step(None)
        return True

    def _play_scene(self, scene_id: str) -> None:
        """Run a scene that belongs to a place rather than a person.

        Parameters
        ----------
        scene_id : str
            Key into the scene table -- ``cave``, ``rift``.
        """
        self.speaking = None
        self.menu_index = 0
        self.ctx.dark = self.dark
        self.ctx.tick += 1
        self.screen = self.runner.start(scene_id)
        self._after_step(None)

    def _dialogue_input(self, keys) -> None:
        """Step the running scene from the pad.

        Parameters
        ----------
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        screen = self.screen
        if screen is None:
            self.speaking = None
            return
        if keys.just_pressed(Action.CANCEL) and not screen.choices:
            self.screen = None
            self.speaking = None
            return
        if screen.choices:
            if keys.just_pressed(Action.DOWN):
                self.menu_index = (self.menu_index + 1) % len(screen.choices)
            if keys.just_pressed(Action.UP):
                self.menu_index = (self.menu_index - 1) % len(screen.choices)
            if keys.just_pressed(Action.CONFIRM):
                self.screen = self.runner.choose(self.menu_index)
                self.menu_index = 0
                self._after_step(self.speaking)
            return
        if keys.just_pressed(Action.CONFIRM):
            self.screen = self.runner.advance()
            self._after_step(self.speaking)

    def _after_step(self, npc) -> None:
        """Do whatever the scene just asked the host to do.

        Parameters
        ----------
        npc : Npc or None
            Whoever is speaking, so a character who has finished their part in
            the world (the hound, once befriended) can leave it.
        """
        for request in self.runner.take_requests():
            self._serve(request)
        if self.screen is None:
            if npc is not None and npc.role == "lumi" and self.story.has_lumi:
                # The hound is at heel now, so he is no longer lying in the
                # grass waiting to be found.
                self.people = [other for other in self.people if other is not npc]
                self.lumi = [npc.x, npc.y]
            self.speaking = None

    def _sound(self, event: str, frequency: float = 660.0) -> None:
        """Play one of the shipped effects, if there is audio at all.

        Parameters
        ----------
        event : str
            An event name the asset pack maps onto a recording.
        frequency : float, optional
            Pitch of the synthesised blip used when the pack has no recording
            for this event.
        """
        host = getattr(self, "host", None)
        if host is not None and getattr(host, "audio", None) is not None:
            host.audio.sfx(event, frequency)

    def _serve(self, request) -> None:
        """Satisfy one host request from a script.

        Parameters
        ----------
        request : chisurf.plugins.misc.games.lumis_quest.api.engine.Request
            What the scene wants done.
        """
        if request.kind == "save":
            self.save_run()
            self._sound("seal", 720.0)
        elif request.kind == "menu":
            self.menu_open = True
            self.menu_row = 0
        elif request.kind == "cross":
            self._sound("cross", 300.0)
            self._cross(request.args.get("to", "dark"))
        elif request.kind == "battle":
            self._begin_warden_fight(request.args.get("warden", ""))
        elif request.kind == "join":
            if self._overheard is not None:
                self.society.interrupt(self._overheard)
                self._overheard = None

    def _cross(self, to: str) -> None:
        """Move between the lit world and the dark manifold.

        The geography is the same on both sides -- that is the whole trick, and
        it is why crossing is a flag rather than a second map. What changes is
        the ground, the buildings, and who is standing on them.

        Parameters
        ----------
        to : str
            ``dark`` or ``light``.
        """
        want_dark = to == "dark"
        if want_dark == self.dark:
            return
        self.dark = want_dark
        self.ctx.dark = want_dark
        if want_dark:
            self._lit_people = self.people
            self.people = npcs_api.dark_population(self.world)
        else:
            self.people = getattr(self, "_lit_people", None) or npcs_api.populate(self.world)
        # A step clear of the mouth, so the crossing does not immediately offer
        # itself again from the other side.
        if not self._solid(self.iris[0], self.iris[1] + T.TILE):
            self.iris[1] += T.TILE

    def _door_scene(self) -> str:
        """The scene the ground under Iris runs, if any.

        Returns
        -------
        str
            A scene id, or empty when standing on ordinary ground.
        """
        tile = self.world.tile_at(int(self.iris[0] // T.TILE),
                                  int(self.iris[1] // T.TILE), self.dark)
        if tile == T.CAVE:
            return "cave"
        if tile == T.RIFT:
            return "rift"
        return ""

    def _warden_beast(self, warden):
        """What a Warden fields.

        Their body is written in ``data/wardens.json``; the label is picked off
        the roster at the brightness their tier calls for, so the ladder gets
        harder because the *beasts* get harder rather than because a number
        went up.

        Parameters
        ----------
        warden : chisurf.plugins.misc.games.lumis_quest.api.tiers.Warden
            Who is being faced.

        Returns
        -------
        Beast or None
            ``None`` when there is no roster to draw from.
        """
        if not self.pool:
            return None
        species = bestiary_api.BY_KEY.get(warden.body) or bestiary_api.SPECIES[0]
        ranked = sorted(self.pool, key=lambda label: label.attack)
        index = min(len(ranked) - 1,
                    int(round((warden.tier / 5.0) * (len(ranked) - 1))))
        return bestiary_api.Beast(species=species, label=ranked[index])

    def _begin_warden_fight(self, key: str) -> None:
        """Face a Warden for their seal.

        Parameters
        ----------
        key : str
            The Warden's key.
        """
        warden = tiers_api.BY_KEY.get(key)
        beast = self._warden_beast(warden) if warden is not None else None
        if beast is None or not any(fighter.alive for fighter in self.team):
            return
        self.screen = None
        self.speaking = None
        self.encounter_room = None
        self.menu_index = 0
        self.warden_fight = key
        self.battle = battle_api.Battle(
            self.team,
            battle_api.Fighter(beast),
            loadout=self.loadout,
            seals=self.story.seals,
            opponent_power=1.9,
        )

    def _title_rows(self) -> list[str]:
        """The title menu, top to bottom.

        Returns
        -------
        list of str
            Continue appears only when there is a run to continue; starting
            over on top of one asks before it erases.
        """
        rows = []
        if self._has_save:
            rows.append("Continue")
        rows.append(
            "New Journey -- erase the saved run?"
            if self.title_confirm_new and self._has_save
            else "New Journey"
        )
        rows.append(f"controls: {self.scheme}")
        return rows

    def _title_input(self, keys) -> None:
        """Drive the title menu.

        Parameters
        ----------
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        rows = self._title_rows()
        if keys.just_pressed(Action.DOWN):
            self.title_index = (self.title_index + 1) % len(rows)
            self.title_confirm_new = False
        if keys.just_pressed(Action.UP):
            self.title_index = (self.title_index - 1) % len(rows)
            self.title_confirm_new = False
        if keys.just_pressed(Action.CANCEL):
            self.title_confirm_new = False
        if not keys.just_pressed(Action.CONFIRM):
            return

        row = self.title_index - (1 if self._has_save else 0)
        if row == -1:
            self._continue_run()
        elif row == 0:
            # Starting over discards a run; with one on disk that takes a
            # second, separate press to mean it.
            if self._has_save and not self.title_confirm_new:
                self.title_confirm_new = True
            else:
                self.title_confirm_new = False
                self._begin_journey()
        else:
            names = list(SCHEMES)
            self.scheme = names[(names.index(self.scheme) + 1) % len(names)]
            self.host.keys.bindings = dict(SCHEMES[self.scheme])

    def _epilogue_cards(self) -> tuple[tuple[str, str], ...]:
        """The dawn, in the chosen order's voice.

        Returns
        -------
        tuple
            ``(title, body)`` cards; a fallback card if somehow no order.
        """
        cards = EPILOGUES.get(self.story.chosen_order or "")
        return cards or (("The Dawn", "Where you worked, the lamps hold."),)

    #: The tabs of the pause menu, in order.
    TABS = ("MAP", "RIG", "PARTY", "LAB", "MODE", "OPTIONS")

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

    def _options_confirm(self) -> None:
        """Act on the selected option."""
        row = self.menu_row
        if row == 0:
            names = list(SCHEMES)
            self.scheme = names[(names.index(self.scheme) + 1) % len(names)]
            self.host.keys.bindings = dict(SCHEMES[self.scheme])
        elif row == 1:
            self.walk_speed = 120.0 if self.walk_speed >= 260.0 else self.walk_speed + 35.0
        elif row == 2:
            self.view_height = VIEW_MIN if self.view_height >= 600.0 else self.view_height + 90.0
        elif row == 3:
            # Only the wilderness is redrawn. Which lands exist and where each
            # page stands comes from the documentation and must not move: a
            # player who has learned where something lives should not lose that
            # by asking for new scenery.
            self.seed = f"{self.seed}+" if self.seed else "regenerated"
            self._pending = None
            self.menu_open = False
            self.phase = "loading"
            self.load_step = 0
            self.load_note = self.LOAD_STAGES[0]
        elif row == 4:
            self.menu_open = False
            self.prologue_index = 0
            self.phase = "prologue"

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
            # The build screen: bodies and labels are separate lists, and a
            # team member is one of each. Picking a slot then picking a body or
            # a label is the whole interaction.
            rows = [
                f"{'>' if index == self.party_slot else ' '} {f.name}"
                f"  {f.hp}/{f.beast.max_hp}  T{f.beast.tier}"
                for index, f in enumerate(self.team)
            ]
            rows.append("-- bodies --")
            rows.extend(f"   {body.name}  ({_trait_name(body.trait)})"
                        for body in self.bodies)
            rows.append("-- labels --")
            rows.extend(f"   {label.name}  {label.emission_nm:.0f} nm"
                        for label in self.labels)
            return rows
        if tab == "OPTIONS":
            return [
                f"controls: {self.scheme}",
                f"walk speed: {self.walk_speed:.0f}",
                f"default zoom: {self.view_height:.0f}",
                "regenerate the wilderness",
                "watch the opening again",
            ]
        if tab == "LAB":
            now = time.time()
            rows = []
            names = save_api.creatures_by_id(self.pool)
            for plot in self.lab.plots:
                name = getattr(names.get(plot.probe_id), "name", f"#{plot.probe_id}")
                rows.append(
                    f"{name}  READY -- harvest"
                    if plot.ready(now)
                    else f"{name}  maturing {plot.progress(now):.0%}"
                )
            if self.lab.can_plant():
                rows.extend(f"culture {label.name}" for label in self.labels)
            return rows or ["unbind a label, then culture it here"]
        if tab == "MODE":
            return [
                review_bridge.TRAINING,
                review_bridge.EXPERT,
                f"model voices & questions: {'on' if self.use_model else 'off'}",
            ]
        return []

    def _menu_confirm(self) -> None:
        """Act on the selected row."""
        tab = self.TABS[self.menu_tab]
        if tab == "MAP":
            self.show_map = not self.show_map
            self.menu_open = False
        elif tab == "MODE":
            if self.menu_row < 2:
                self.mode = (review_bridge.TRAINING, review_bridge.EXPERT)[self.menu_row]
            else:
                self.use_model = not self.use_model
        elif tab == "RIG" and self.inventory:
            part = self.inventory[min(self.menu_row, len(self.inventory) - 1)]
            # Fitting into the rig and fitting the single filter are the same
            # act from the player's side, so both happen.
            self.rig.fit(part)
            self.equip(part)
        elif tab == "LAB":
            now = time.time()
            if self.menu_row < len(self.lab.plots):
                probe_id = self.lab.harvest(self.menu_row, now)
                if probe_id is not None:
                    # A mature culture is a fresh, unbleached copy; the
                    # planted creature was a template and is still yours.
                    creatures = save_api.creatures_by_id(self.pool)
                    if probe_id in creatures:
                        self.labels.append(creatures[probe_id])
            else:
                index = self.menu_row - len(self.lab.plots)
                if 0 <= index < len(self.labels) and self.lab.can_plant():
                    self.lab.plant(self.labels[index].probe_id, now)
        elif tab == "OPTIONS":
            self._options_confirm()
        elif tab == "PARTY":
            self._party_confirm()

    def _party_confirm(self) -> None:
        """Act on a row of the build screen.

        Three kinds of row, and the rule is the same for all of them: picking a
        team member selects the slot you are building, picking a body swaps the
        animal in that slot, picking a label fits the dye. Whatever came out
        goes back into the corresponding list -- nothing is destroyed, because
        the animal is not a consumable.
        """
        row = self.menu_row
        if not self.team:
            return
        if row < len(self.team):
            self.party_slot = row
            return
        bodies_at = len(self.team) + 1
        labels_at = bodies_at + len(self.bodies) + 1
        slot = min(self.party_slot, len(self.team) - 1)
        current = self.team[slot]
        if bodies_at <= row < bodies_at + len(self.bodies):
            body = self.bodies.pop(row - bodies_at)
            self.bodies.append(current.beast.species)
            self.team[slot] = battle_api.Fighter(
                bestiary_api.Beast(species=body, label=current.beast.label)
            )
        elif labels_at <= row < labels_at + len(self.labels):
            label = self.labels.pop(row - labels_at)
            if current.beast.label is not None:
                self.labels.append(current.beast.label)
            self.team[slot] = battle_api.Fighter(current.beast.fitted(label))
        self.ctx.team = self.team

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
        self.resting = self.world.tile_at(col, row, self.dark) == T.CLINIC
        if not self.resting:
            return
        for fighter in self.team:
            if fighter.hp < fighter.beast.max_hp:
                fighter.hp = min(
                    fighter.beast.max_hp,
                    fighter.hp + max(1, int(fighter.beast.max_hp * 0.6 * dt)),
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
            guardian = battle_api.wild_encounter(room.address, room.remoteness, self.pool)
            cached = guardian.beast.emission_nm
            self._guardian_nm[room.address] = cached
        return cached

    def _try_encounter(self, force: bool = False) -> None:
        """Start a fight with whatever guards the nearest wild building.

        Only wild rooms hold a guardian: a page somebody has already read is a
        village you walk through, not a place that fights you.
        """
        room = self.here
        if room is None or room.state not in (WILD, WITHERED) or not self.pool:
            return
        x, y = room.position
        if not force and math.hypot(x - self.iris[0], y - self.iris[1]) > T.TILE * 2.2:
            return
        if not any(fighter.alive for fighter in self.team):
            return
        self.encounter_room = room
        self.menu_index = 0
        self.warden_fight = ""
        # Which bodies are around is the ground you are standing on, and how
        # far the beast may outrank you is your seals: a land you have no
        # licence for does not open with something you cannot answer.
        tile = self.world.tile_at(int(self.iris[0] // T.TILE),
                                  int(self.iris[1] // T.TILE), self.dark)
        self.battle = battle_api.Battle(
            self.team,
            battle_api.wild_encounter(
                room.address, room.remoteness, self.pool,
                terrain=bestiary_api.terrain_for_tile(tile),
                tier_cap=tiers_api.licence(self.story.seals),
            ),
            loadout=self.loadout,
            seals=self.story.seals,
        )
        self.story.witness("the-marked")

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
            self._collect_spoils(fight)
            if fight.won and self.encounter_room is not None:
                self._award_loot(self.encounter_room)
                self._begin_challenge(self.encounter_room)

            if self.flagging:
                self._flag_input(keys)
                return
            if self.challenge is not None:
                self._challenge_input(keys)
                return
            if keys.just_pressed(Action.CONFIRM) or keys.just_pressed(Action.CANCEL):
                self.battle = None
                self.encounter_room = None
                self.warden_fight = ""
                self.verdict = None
            return

        options = self._battle_options()
        if keys.just_pressed(Action.DOWN):
            self.menu_index = (self.menu_index + 1) % len(options)
        if keys.just_pressed(Action.UP):
            self.menu_index = (self.menu_index - 1) % len(options)
        if keys.just_pressed(Action.CONFIRM):
            label = options[self.menu_index][0]
            options[self.menu_index][1]()
            self._sound("unbind" if label.startswith("Unbind") else "emit", 700.0)
        elif keys.just_pressed(Action.CANCEL):
            fight.flee()

    def _collect_spoils(self, fight) -> None:
        """Take what a finished fight leaves behind, once.

        A win is not a kill. What you carry away is the *label* you unbound and,
        if the animal took to you, the animal -- which is why the two are
        collected separately and why the ethics of the thing survive contact
        with the loot loop.

        Parameters
        ----------
        fight : chisurf.plugins.misc.games.lumis_quest.api.battle.Battle
            The finished encounter.
        """
        if getattr(fight, "_spoiled", False):
            return
        fight._spoiled = True
        if fight.taken is not None:
            if fight.taken.probe_id not in {label.probe_id for label in self.labels}:
                self.labels.append(fight.taken)
            self.story.unbound += 1
        elif fight.won and not fight.fled:
            self._sound("bleach", 240.0)
        if fight.joined and fight.freed is not None:
            if fight.freed.key not in {body.key for body in self.bodies}:
                self.bodies.append(fight.freed)
        if fight.won and self.warden_fight:
            self.story.seal(self.warden_fight)
            self._sound("seal", 880.0)
            self.save_run()

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
        questions, content_hash = review_bridge.challenge_for(
            room.path,
            provider=providers_api.best_available(prefer_model=self.use_model),
        )
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
        if keys.just_pressed(Action.SHOULDER_L) and self.mode == review_bridge.EXPERT:
            self._begin_flag()
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

    def _begin_flag(self) -> None:
        """Start reporting a defect instead of answering.

        Signing off says "this is fine". This is the other half.
        """
        from ..api.challenge import _sentences

        room = self.encounter_room
        if room is None:
            return
        try:
            text = room.path.read_text(encoding="utf-8")
        except OSError:
            return
        spans = _sentences(text)
        if not spans:
            self.verdict = review_bridge.Verdict(
                False, "Nothing here specific enough to flag.", "unavailable"
            )
            self.challenge = None
            return
        self.flag_spans = spans[:40]
        self.flag_span_index = 0
        self.flag_category_index = 0
        self.flag_stage = "span"
        self.flagging = True
        self.challenge = None

    def _flag_input(self, keys) -> None:
        """Pick a span, then a category.

        Parameters
        ----------
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        if keys.just_pressed(Action.CANCEL):
            if self.flag_stage == "category":
                self.flag_stage = "span"
                return
            self.flagging = False
            return

        if self.flag_stage == "span":
            if keys.just_pressed(Action.DOWN):
                self.flag_span_index = (self.flag_span_index + 1) % len(self.flag_spans)
            if keys.just_pressed(Action.UP):
                self.flag_span_index = (self.flag_span_index - 1) % len(self.flag_spans)
            if keys.just_pressed(Action.CONFIRM):
                self.flag_stage = "category"
            return

        if keys.just_pressed(Action.DOWN):
            self.flag_category_index = (
                self.flag_category_index + 1
            ) % len(findings_api.CATEGORIES)
        if keys.just_pressed(Action.UP):
            self.flag_category_index = (
                self.flag_category_index - 1
            ) % len(findings_api.CATEGORIES)
        if keys.just_pressed(Action.CONFIRM):
            self._record_finding()

    def _record_finding(self) -> None:
        """Pool the finding. Nothing is written into the documentation."""
        room = self.encounter_room
        if room is None:
            self.flagging = False
            return
        finding = findings_api.Finding(
            address=room.address,
            content_hash=self.challenge_hash or findings_api.current_hash(room.path),
            span=self.flag_spans[self.flag_span_index],
            category=findings_api.CATEGORIES[self.flag_category_index][0],
        )
        findings_api.add(finding, self.findings_path)
        self.flagging = False
        self.verdict = review_bridge.Verdict(
            False, f"Recorded: {finding.category}.", "flagged"
        )

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
        options = [("Emit", fight.attack)]
        if fight.opponent.beast.marked:
            options.append(
                (f"Unbind ({fight.take_chance():.0%})", fight.unbind)
            )
        for index, fighter in enumerate(fight.team):
            if index != fight.active_index and fighter.alive:
                options.append(
                    (f"Send {fighter.name}", lambda i=index: fight.swap(i))
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
            if self.world.blocked(x + ox, y + oy, self.dark):
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

        if self.phase in ("loading", "prologue", "title", "epilogue"):
            self._draw_curtain(scene, camera, half)
            return

        as_map = camera.height > MAP_THRESHOLD
        self._draw_tiles(scene, camera, half, as_map)
        if not as_map:
            self._draw_structures(scene, camera, half)
        if not self.dark:
            self._draw_rooms(scene, camera, half)

        if not as_map:
            for village in self.world.villages:
                vx, vy = village.position
                if abs(vx - camera.center[0]) > half[0] or abs(vy - camera.center[1]) > half[1]:
                    continue
                _, row, _, _ = village.rect
                # A settlement announces itself by its *place* name. "Core
                # Methods" is a section heading; nobody says they are walking
                # to Core Methods.
                scene.text(
                    village.place.upper() or village.name.upper(),
                    at=(vx, row * T.TILE - 22.0),
                    height=11.0, align="center", color=(0.86, 0.80, 0.60, 1.0),
                )
                scene.text(
                    village.name.lower(),
                    at=(vx, row * T.TILE - 11.0),
                    height=8.0, align="center", color=(0.48, 0.52, 0.60, 1.0),
                )

        # Everyone who lives here, drawn before Iris so she walks in front of
        # them. Culled to the view: the world holds well over a hundred.
        frame_index = int(self._clock * 3.0) % 2
        for npc in self.people:
            if abs(npc.x - camera.center[0]) > half[0] + T.TILE:
                continue
            if abs(npc.y - camera.center[1]) > half[1] + T.TILE:
                continue
            tint = (1.0, 1.0, 1.0, 1.0)
            sprite = f"{npc.kind}_{frame_index}"
            if npc.species:
                # An animal is drawn as the animal it is, in the colour of
                # whatever is fixed into it. A marked hare and an unmarked one
                # are the same drawing and read completely differently, which
                # is the point of the whole bestiary.
                sprite = pixelart.creature_sprite(npc.species)
                if npc.kind == "beast":
                    nm = self._marked_nm(npc)
                    scene.draw("photon", "halo", at=(npc.x, npc.y),
                               size=(T.TILE * 0.8, T.TILE * 0.8), emission_nm=nm)
                    tint = _emission_tint(nm)
                elif npc.kind == "wraith":
                    tint = (0.30, 0.26, 0.36, 1.0)
            elif npc.kind == "beast":
                scene.draw("photon", "halo", at=(npc.x, npc.y),
                           size=(T.TILE * 0.9, T.TILE * 0.9), emission_nm=405.0)
            elif npc.kind == "warden":
                scene.draw("photon", "halo", at=(npc.x, npc.y),
                           size=(T.TILE * 1.2, T.TILE * 1.2), emission_nm=600.0)
                tint = (1.00, 0.92, 0.74, 1.0)
            elif npc.kind == "emissary":
                doctrine = npc.role.split(":", 1)[-1]
                scene.draw("photon", "halo", at=(npc.x, npc.y),
                           size=(T.TILE * 1.1, T.TILE * 1.1),
                           emission_nm=EMISSARY_NM.get(doctrine, 488.0))
                tint = EMISSARY_TINT.get(doctrine, tint)
            elif npc.kind == "lumi":
                # The dim hound: an ember of the glow it will have at heel.
                scene.draw("photon", "halo", at=(npc.x, npc.y),
                           size=(T.TILE * 0.5, T.TILE * 0.5),
                           emission_nm=LUMI.wavelength_nm)
                tint = (0.55, 0.62, 0.55, 1.0)
            self._sprite(scene, "shadow", (npc.x, npc.y + 2.0), T.TILE)
            self._sprite(scene, sprite, (npc.x, npc.y), T.TILE,
                         mirror=npc.facing == "left", tint=tint)
        # ...and whatever any of them is in the middle of saying. Two people
        # talking has to be legible from across the square or the whole layer
        # is invisible work.
        if not self.dark:
            for mind in self.society.minds:
                spoken = mind.line
                if spoken is None or spoken[0] != mind.npc.name:
                    continue
                if abs(mind.npc.x - camera.center[0]) > half[0] or \
                        abs(mind.npc.y - camera.center[1]) > half[1]:
                    continue
                wrapped = _wrap(spoken[1], 28)[:2]
                scene.draw("ui", "panel",
                           at=(mind.npc.x, mind.npc.y - 27.0 + (len(wrapped) - 1) * 4.5),
                           size=(150.0, 8.0 + 10.0 * len(wrapped)),
                           color=(0.04, 0.05, 0.07, 0.86))
                for offset, line in enumerate(wrapped):
                    scene.text(line, at=(mind.npc.x, mind.npc.y - 30.0 + offset * 9.5),
                               height=8.5, align="center",
                               color=(0.90, 0.92, 0.97, 1.0))

        # The glow under each of them is the photon they are; the sprite on top
        # is the body that photon wears. No hound at heel until it is found.
        frame = int(self._walk_clock * WALK_FPS) % 2 if self.walking else 0
        if self.story.has_lumi:
            self._sprite(scene, "shadow", (self.lumi[0], self.lumi[1] + 2.0), T.TILE)
            scene.draw("photon", "halo", at=tuple(self.lumi),
                       size=(T.TILE * 0.7, T.TILE * 0.7),
                       emission_nm=LUMI.wavelength_nm)
            self._sprite(scene, f"lumi_{self._facing_for('lumi')}_{frame}",
                         self.lumi, T.TILE)
        self._sprite(scene, "shadow", (self.iris[0], self.iris[1] + 3.0), T.TILE * 1.15)
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

    def _marked_nm(self, npc) -> float:
        """What colour a marked animal in the world burns.

        Cached per NPC, because the map asks it of everything in view every
        frame and the answer is fixed the moment the labeller chose.

        Parameters
        ----------
        npc : chisurf.plugins.misc.games.lumis_quest.api.npcs.Npc
            The marked beast.

        Returns
        -------
        float
            Emission maximum in nm, or 0 when there is no roster.
        """
        if not self.pool:
            return 0.0
        key = (npc.species, int(npc.home[0]), int(npc.home[1]))
        nm = self._guardian_nm.get(key)
        if nm is None:
            beast = bestiary_api.wild_beast(
                f"{key}", 0.5, self.pool,
                terrain=bestiary_api.BY_KEY[npc.species].habitat
                if npc.species in bestiary_api.BY_KEY else bestiary_api.MEADOW,
                tier_cap=tiers_api.licence(self.story.seals),
            )
            nm = beast.emission_nm
            self._guardian_nm[key] = nm
        return nm

    def _beast_portrait(self, scene, fighter, at, size: float) -> None:
        """Draw a marked animal: the body, in the colour of its label.

        This is the premise made visible. One hare drawing is a Verdant Hare
        and a Garnet Hare and an Umbral Hare, because the animal is the animal
        and the colour is somebody else's doing.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        fighter : chisurf.plugins.misc.games.lumis_quest.api.battle.Fighter
            Who to draw.
        at : sequence of float
            Centre in world units.
        size : float
            Edge length in world units.
        """
        if fighter.beast.marked:
            scene.draw("photon", f"aura{id(fighter) & 0xFF}", at=at,
                       size=(size * 0.9, size * 0.9),
                       emission_nm=fighter.beast.emission_nm)
        tint = _emission_tint(fighter.beast.emission_nm) if fighter.beast.marked \
            else (0.86, 0.86, 0.84, 1.0)
        self._sprite(scene, pixelart.creature_sprite(fighter.beast.species.key),
                     at, size, tint=tint)

    def _draw_structures(self, scene, camera, half) -> None:
        """Draw what a settlement is built of, over the ground.

        The tile layer is one textured quad per cell and every quad in it is the
        *ground*; a well, a tavern or a lantern post is a second, taller drawing
        standing on that ground. Doing it in one layer would mean a lantern
        erasing the paving it stands on.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        camera : chisurf.gui.chigame.render.Camera
            The view.
        half : numpy.ndarray
            Half-extent in world units.
        """
        col0, row0, col1, row1 = self._visible_tiles(camera, half)
        if col1 <= col0 or row1 <= row0:
            return
        window = self.grid_array[row0:row1, col0:col1]
        for kind, sprite in STRUCTURE_SPRITES.items():
            rows, cols = np.nonzero(window == kind)
            if not rows.size:
                continue
            # Only the lamp posts cast light, and only a little. At a tile and
            # a half of additive glow apiece a square with four of them was a
            # white hole with a town somewhere underneath it.
            lit = kind is T.LANTERN and not self.dark
            for row, col in zip(rows, cols):
                x = (col0 + int(col) + 0.5) * T.TILE
                y = (row0 + int(row) + 0.5) * T.TILE
                if lit:
                    scene.draw("photon", f"lamp{int(row)}_{int(col)}",
                               at=(x, y - T.TILE * 0.3),
                               size=(T.TILE * 0.85, T.TILE * 0.85), emission_nm=600.0)
                if kind in FLAT_STRUCTURES:
                    self._sprite(scene, sprite, (x, y), T.TILE)
                else:
                    self._building(scene, sprite, (x, y))

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
        window = self.grid_array[row0:row1:step, col0:col1:step]
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
            # Two drawings per organic material, chosen by position so the
            # field never reads as a repeating grid -- and water additionally
            # flips with time, which is what makes it read as water.
            gx = col0 + np.arange(cols) * step
            gy = row0 + np.arange(rows) * step
            checker = ((((gx[None, :] * 7 + gy[:, None] * 13) >> 1) & 1)
                       .astype(bool).reshape(-1))
            ripple = bool(int(self._clock * 1.6) & 1)
            swap = checker ^ ((flat == T.WATER) & ripple)
            instances[:, 12:16] = np.where(
                swap[:, None], self._tile_uv_alt[flat], self._tile_uv[flat]
            )
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
            if room.state in (WILD, WITHERED) and self.pool:
                # A creature the fitted filter blocks is not rendered as itself:
                # this is the loot loop, and it is why re-walking cleared ground
                # with different optics shows you things that were always there.
                nm = self.guardian_nm(room)
                if nm and not self.loadout.sees(nm):
                    self._building(scene, self._house_sprite(room, lit=False), (x, y),
                                   tint=(0.16, 0.17, 0.20, 1.0))
                    continue

            if room.state == SETTLED:
                scene.draw("photon", "halo", at=(x, y - T.TILE * 0.2),
                           size=(T.TILE * 1.7, T.TILE * 1.7), emission_nm=SETTLED_NM)
            elif room.state == SCOUTED:
                scene.draw("photon", "halo", at=(x, y - T.TILE * 0.2),
                           size=(T.TILE * 1.2, T.TILE * 1.2), emission_nm=SCOUTED_NM)
            lit = room.state in (SETTLED, SCOUTED)
            self._building(scene, self._house_sprite(room, lit), (x, y),
                           tint=HOUSE_TINT[room.state])

    def _house_sprite(self, room, lit: bool) -> str:
        """Which of the four house styles a page is built in.

        Chosen by the page's own address, so a street is slate beside thatch
        beside tile the way a street is, and the same page is the same house on
        every visit.

        Parameters
        ----------
        room : chisurf.plugins.misc.games.lumis_quest.api.world.Room
            The page.
        lit : bool
            Whether anybody has read it.

        Returns
        -------
        str
            A sprite name.
        """
        style = npcs_api._seed(room.address) % pixelart.HOUSE_STYLES
        return f"house{style}_{'lit' if lit else 'dark'}"

    def _building(self, scene, sprite: str, at, tint=(1.0, 1.0, 1.0, 1.0)) -> None:
        """Draw something built, standing a tile and a half tall.

        A building the size of its own tile sits *in* the ground; a 16-bit town
        reads because its buildings stand over it and overlap the row behind.
        The sprite is drawn oversized and pushed up so its base stays exactly
        where the tile is.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        sprite : str
            Sprite name.
        at : sequence of float
            Centre of the *tile*, in world units.
        tint : tuple of float, optional
            Multiplied into the artwork.
        """
        size = T.TILE * BUILDING_HEIGHT
        self._sprite(scene, sprite, (at[0], at[1] - (size - T.TILE) * 0.5), size,
                     tint=tint)

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

        if self.flagging:
            if self.flag_stage == "span":
                scene.text("Which sentence is at fault?", at=(cx, cy - half[1] * 0.44),
                           height=12.0 * scale, align="center",
                           color=(0.90, 0.80, 0.55, 1.0))
                base = max(0, self.flag_span_index - 2)
                for offset, span in enumerate(self.flag_spans[base:base + 5]):
                    selected = base + offset == self.flag_span_index
                    y = cy - half[1] * 0.26 + offset * 26.0 * scale
                    for line_no, line in enumerate(_wrap(span, 58)[:2]):
                        scene.text(line, at=(cx, y + line_no * 11.0 * scale),
                                   height=9.5 * scale, align="center",
                                   color=(0.95, 0.93, 0.86, 1.0) if selected
                                   else (0.45, 0.49, 0.56, 1.0))
            else:
                scene.text("What is wrong with it?", at=(cx, cy - half[1] * 0.44),
                           height=12.0 * scale, align="center",
                           color=(0.90, 0.80, 0.55, 1.0))
                for index, (key, description) in enumerate(findings_api.CATEGORIES):
                    selected = index == self.flag_category_index
                    y = cy - half[1] * 0.24 + index * 13.0 * scale
                    if selected:
                        scene.draw("ui", "selected", at=(cx - half[0] * 0.52, y),
                                   size=(7.0 * scale, 7.0 * scale))
                    scene.text(f"{key}", at=(cx - half[0] * 0.47, y),
                               height=10.5 * scale,
                               color=(0.94, 0.92, 0.86, 1.0) if selected
                               else (0.56, 0.60, 0.68, 1.0))

            if self.flag_stage == "category":
                # On its own line: right-aligning it beside the key put the two
                # on top of each other for the longer descriptions.
                _, description = findings_api.CATEGORIES[self.flag_category_index]
                scene.text(description, at=(cx, cy + half[1] * 0.42),
                           height=10.0 * scale, align="center",
                           color=(0.66, 0.70, 0.78, 1.0))
            scene.text("Up/Down choose   Confirm select   Cancel back",
                       at=(cx, cy + half[1] * 0.66), height=9.5 * scale, align="center",
                       color=(0.48, 0.52, 0.60, 1.0))
            return

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
            scene.text(f"[{self.mode}]  L flag a problem   Cancel to leave it unread",
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


        # The opponent, drawn in the colour it actually emits.
        enemy = fight.opponent
        top = cy - half[1] * 0.52
        self._beast_portrait(scene, enemy, (cx + half[0] * 0.46, top + 6.0 * scale),
                             34.0 * scale)
        scene.text(enemy.name, at=(cx - half[0] * 0.10, top - 14.0 * scale),
                   height=13.0 * scale, align="center", color=(0.90, 0.88, 0.82, 1.0))
        self._bar(scene, (cx - half[0] * 0.10, top + 4.0 * scale), 130.0 * scale, 7.0 * scale,
                  enemy.hp / max(enemy.beast.max_hp, 1), (0.90, 0.42, 0.38, 1.0))
        scene.text(f"{enemy.beast.summary}",
                   at=(cx - half[0] * 0.10, top + 18.0 * scale),
                   height=9.0 * scale, align="center", color=(0.52, 0.56, 0.64, 1.0))
        scene.text("  ".join(enemy.beast.trait_names[:3]),
                   at=(cx - half[0] * 0.10, top + 28.0 * scale),
                   height=8.5 * scale, align="center", color=(0.62, 0.56, 0.72, 1.0))

        # Your active creature.
        active = fight.active
        low = cy + half[1] * 0.10
        self._beast_portrait(scene, active, (cx - half[0] * 0.48, low + 6.0 * scale),
                             32.0 * scale)
        scene.text(active.name, at=(cx + half[0] * 0.10, low - 14.0 * scale),
                   height=13.0 * scale, align="center", color=(0.82, 0.90, 0.96, 1.0))
        self._bar(scene, (cx + half[0] * 0.10, low + 4.0 * scale), 130.0 * scale, 7.0 * scale,
                  active.hp / max(active.beast.max_hp, 1), (0.40, 0.85, 0.70, 1.0))
        scene.text(f"{active.beast.summary}",
                   at=(cx + half[0] * 0.10, low + 18.0 * scale),
                   height=9.0 * scale, align="center", color=(0.52, 0.56, 0.64, 1.0))
        scene.text(active.beast.subtitle,
                   at=(cx + half[0] * 0.10, low - 25.0 * scale),
                   height=8.5 * scale, align="center", color=(0.50, 0.58, 0.62, 1.0))

        # The last two things that happened, newest at the bottom.
        # Wrapped to the panel: a single long line ran off both edges, and the
        # interesting half of it ("barely couples for 16") was the half cut off.
        lines: list[str] = []
        for turn in fight.log[-2:]:
            lines.extend(_wrap(turn.text, 52))
        for offset, line in enumerate(lines[-3:]):
            scene.text(line, at=(cx, cy + half[1] * 0.30 + offset * 12.0 * scale),
                       height=10.0 * scale, align="center", color=(0.74, 0.78, 0.86, 1.0))

        if fight.finished:
            outcome = "The light holds." if fight.won else (
                "You withdraw." if fight.fled else "Your team is spent."
            )
            if fight.taken is not None:
                outcome = f"{fight.taken.name} is yours."
            elif fight.won and not fight.fled:
                outcome = "Driven all the way down. It crossed."
            if fight.won and self.warden_fight:
                warden = tiers_api.BY_KEY.get(self.warden_fight)
                if warden is not None:
                    outcome = warden.after
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

    def _draw_curtain(self, scene, camera, half) -> None:
        """Draw the loading screen and the opening.

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
        scale = camera.height / VIEW_HEIGHT
        scene.draw("ui", "panel", at=(cx, cy), size=(half[0] * 2.4, half[1] * 2.4),
                   color=(0.020, 0.024, 0.032, 1.0))

        if self.phase == "loading":
            scene.text("LUMIS QUEST", at=(cx, cy - 26.0 * scale), height=20.0 * scale,
                       align="center", color=(0.88, 0.82, 0.58, 1.0))
            scene.text(self.load_note, at=(cx, cy + 6.0 * scale), height=11.0 * scale,
                       align="center", color=(0.52, 0.58, 0.66, 1.0))
            done = min(self.load_step, len(self.LOAD_STAGES))
            self._bar(scene, (cx, cy + 26.0 * scale), 160.0 * scale, 5.0 * scale,
                      done / len(self.LOAD_STAGES), (0.45, 0.85, 0.75, 1.0))
            # A pilot light, so the screen is never simply still.
            scene.draw("photon", "spark", at=(cx, cy - 58.0 * scale),
                       size=(14.0 * scale, 14.0 * scale), emission_nm=488.0)
            return

        if self.phase == "title":
            scene.draw("photon", "halo", at=(cx, cy - 62.0 * scale),
                       size=(46.0 * scale, 46.0 * scale), emission_nm=488.0)
            scene.text("LUMIS QUEST", at=(cx, cy - 62.0 * scale), height=24.0 * scale,
                       align="center", color=(0.92, 0.86, 0.60, 1.0))
            scene.text("the documentation is the world",
                       at=(cx, cy - 40.0 * scale), height=10.0 * scale,
                       align="center", color=(0.52, 0.58, 0.66, 1.0))
            for index, row in enumerate(self._title_rows()):
                selected = index == self.title_index
                y = cy + (index * 16.0 - 2.0) * scale
                if selected:
                    scene.draw("ui", "selected", at=(cx - 92.0 * scale, y),
                               size=(7.0 * scale, 7.0 * scale))
                scene.text(row, at=(cx, y), height=12.0 * scale, align="center",
                           color=(0.94, 0.92, 0.86, 1.0) if selected
                           else (0.55, 0.59, 0.66, 1.0))
            labels = self._key_labels()
            scene.text("Up/Down choose   Confirm select",
                       at=(cx, cy + half[1] * 0.56), height=9.5 * scale,
                       align="center", color=(0.46, 0.50, 0.58, 1.0))
            scene.text(f"in the world, {labels['menu']} opens your pack",
                       at=(cx, cy + half[1] * 0.66), height=9.5 * scale,
                       align="center", color=(0.42, 0.46, 0.54, 1.0))
            return

        if self.phase == "epilogue":
            cards = self._epilogue_cards()
            title, body = cards[min(self.epilogue_index, len(cards) - 1)]
            scene.draw("photon", "halo", at=(cx, cy - 70.0 * scale),
                       size=(30.0 * scale, 30.0 * scale), emission_nm=575.0)
            scene.text(title, at=(cx, cy - 66.0 * scale), height=17.0 * scale,
                       align="center", color=(0.95, 0.88, 0.58, 1.0))
            lines = _wrap(body, 42)
            top = cy - 6.0 * scale - (len(lines) - 1) * 7.0 * scale
            for offset, line in enumerate(lines):
                scene.text(line, at=(cx, top + offset * 14.0 * scale),
                           height=11.0 * scale, align="center",
                           color=(0.82, 0.86, 0.92, 1.0))
            scene.text(f"{self.epilogue_index + 1} / {len(cards)}    Confirm to go on",
                       at=(cx, cy + half[1] * 0.62), height=9.5 * scale,
                       align="center", color=(0.46, 0.50, 0.58, 1.0))
            return

        title, body = PROLOGUE[min(self.prologue_index, len(PROLOGUE) - 1)]
        scene.text(title, at=(cx, cy - 66.0 * scale), height=17.0 * scale,
                   align="center", color=(0.88, 0.82, 0.58, 1.0))
        # Centred and wrapped to the view: left-aligning a 52-character line ran
        # it off the right edge, and the last words of every card were lost.
        lines = _wrap(body, 42)
        top = cy - 6.0 * scale - (len(lines) - 1) * 7.0 * scale
        for offset, line in enumerate(lines):
            scene.text(line, at=(cx, top + offset * 14.0 * scale),
                       height=11.0 * scale, align="center",
                       color=(0.80, 0.84, 0.90, 1.0))
        scene.text(f"{self.prologue_index + 1} / {len(PROLOGUE)}    "
                   "Confirm to go on, Cancel to skip",
                   at=(cx, cy + half[1] * 0.62), height=9.5 * scale, align="center",
                   color=(0.46, 0.50, 0.58, 1.0))

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

        # Spread across the panel rather than at a fixed pitch: a fixed one fit
        # four tabs and clipped the fifth off the edge.
        span = half[0] * 1.5
        for index, label in enumerate(self.TABS):
            selected = index == self.menu_tab
            x = cx - span * 0.5 + (index + 0.5) * span / len(self.TABS)
            scene.text(label, at=(x, cy - half[1] * 0.62), height=11.0 * scale,
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

    #: How a raw key name reads on a banner.
    KEY_LABELS = {" ": "Space", "ArrowUp": "Up", "ArrowDown": "Down",
                  "ArrowLeft": "Left", "ArrowRight": "Right"}

    def _key_labels(self) -> dict[str, str]:
        """Resolve the active scheme's keys for the tutorial placeholders.

        Read from the live bindings rather than hard-coded, so a banner stays
        true after the player switches control schemes.

        Returns
        -------
        dict
            ``talk``, ``menu``, ``confirm``, ``cancel`` to a key name.
        """
        def label(action: Action) -> str:
            for key, bound in self.host.keys.bindings.items():
                if bound is action:
                    return self.KEY_LABELS.get(key, key.capitalize() if len(key) > 1 else key.upper())
            return "?"

        return {
            "talk": label(Action.SHOULDER_L),
            "menu": label(Action.MENU),
            "confirm": label(Action.CONFIRM),
            "cancel": label(Action.CANCEL),
        }

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

        # A quiet backing behind the readouts: light text on the pale town
        # floor was unreadable, and a HUD you cannot read is not a HUD.
        scene.draw("ui", "panel",
                   at=(left + 95.0 * scale, top + 62.0 * scale),
                   size=(206.0 * scale, 168.0 * scale),
                   color=(0.02, 0.025, 0.035, 0.82))

        counts = self.world.counts()
        total = max(len(self.world.rooms), 1)
        tally = (f"settled {counts[SETTLED]}/{total}   scouted {counts[SCOUTED]}"
                 f"   wild {counts[WILD]}")
        if counts[WITHERED]:
            tally += f"   withered {counts[WITHERED]}"
        scene.text(
            tally,
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

        # Dialogue owns the bottom band outright: the beat, the banner and the
        # loot line all live there too, and drawn first they bled through the
        # panel as ghost text behind whoever was talking.
        if self.screen is not None:
            screen = self.screen
            wrapped = _wrap(screen.text, 46)[:3] if screen.text else []
            # Sized to what it actually holds. A fixed-height panel is either
            # mostly empty above one line of greeting or too short for four
            # choices, and this one has to serve both.
            rows = len(wrapped) + len(screen.choices)
            tall = 34.0 + 12.5 * max(rows, 1)
            middle = bottom - (tall * 0.5 + 22.0) * scale
            scene.draw("ui", "panel", at=(camera.center[0], middle),
                       size=(half[0] * 1.7, tall * scale),
                       color=(0.055, 0.065, 0.085, 0.97))
            head = middle - (tall * 0.5 - 10.0) * scale
            who = screen.who or (self.speaking.name if self.speaking else "")
            if who:
                scene.text(who, at=(camera.center[0], head),
                           height=11.0 * scale, align="center",
                           color=(0.90, 0.84, 0.60, 1.0))
            for offset, line in enumerate(wrapped):
                scene.text(line, at=(camera.center[0],
                                     head + (14.0 + offset * 12.0) * scale),
                           height=10.0 * scale, align="center",
                           color=(0.82, 0.86, 0.92, 1.0))
            base = head + (16.0 + len(wrapped) * 12.0) * scale
            for index, option in enumerate(screen.choices):
                selected = index == self.menu_index
                y = base + index * 12.5 * scale
                if selected:
                    scene.draw("ui", "selected",
                               at=(camera.center[0] - half[0] * 0.60, y),
                               size=(6.5 * scale, 6.5 * scale))
                scene.text(option, at=(camera.center[0] - half[0] * 0.56, y),
                           height=10.0 * scale,
                           color=(0.95, 0.92, 0.84, 1.0) if selected
                           else (0.56, 0.60, 0.68, 1.0))
            hint = ("Up/Down choose   Confirm select" if screen.choices
                    else "Confirm to go on   Cancel to leave")
            scene.text(hint, at=(camera.center[0], bottom - 10.0 * scale),
                       height=9.0 * scale, align="center", color=(0.48, 0.52, 0.60, 1.0))
            return

        beat = self.story.current
        if beat is not None:
            # Along the bottom, above the room name: the top band already holds
            # the counts and the land, and all three collided there.
            headline = beat.headline
            if beat.key == "the-work" and self.story.work_progress is not None:
                done, goal = self.story.work_progress
                headline += f"   {done}/{goal}"
            scene.text(
                headline,
                at=(camera.center[0], bottom - 48.0 * scale),
                height=10.5 * scale, align="center", color=(0.62, 0.70, 0.80, 1.0),
            )

        step = self.tutorial.current
        if step is not None:
            # One line, in the reward gold, above everything else along the
            # bottom. It names the next real control and waits for the real
            # press -- it never presses anything for the player.
            scene.text(
                step.teach.format(**self._key_labels()),
                at=(camera.center[0], bottom - 76.0 * scale),
                height=10.5 * scale, align="center", color=(0.95, 0.86, 0.50, 1.0),
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
        if self.labels or self.bodies:
            scene.text(
                f"{len(self.labels)} labels   {len(self.bodies)} bodies",
                at=(left + 14.0 * scale, top + 84.0 * scale),
                height=9.5 * scale, color=(0.72, 0.78, 0.62, 1.0),
            )
        # The ladder, always visible: what you are licensed to unbind is the
        # single number that decides which half of the world is available.
        licence = tiers_api.licence(self.story.seals)
        scene.text(
            f"seal {len(self.story.seals)}/5   licence "
            f"{tiers_api.TIER_NAMES[licence]}",
            at=(left + 14.0 * scale, top + 126.0 * scale),
            height=9.5 * scale, color=(0.86, 0.76, 0.94, 1.0),
        )
        if self.dark:
            scene.text(
                "the dark manifold",
                at=(left + 14.0 * scale, top + 140.0 * scale),
                height=9.5 * scale, color=(0.72, 0.50, 0.92, 1.0),
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
