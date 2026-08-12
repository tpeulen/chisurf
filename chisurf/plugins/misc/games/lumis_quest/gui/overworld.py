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

import collections
import math
import random
import time
import zlib

import numpy as np

from chisurf.gui import chigame
from chisurf.gui.chigame.input import Action

from ...characters import IRIS, LUMI, draw as draw_character
from ..api import tiles as T
from ..api import agents as agents_api
from ..api import screens as screens_api
from ..api import battle as battle_api
from ..api import bestiary as bestiary_api
from ..api import crafting as crafting_api
from ..api import context as context_api
from ..api import darkworld as darkworld_api
from ..api import engine as engine_api
from ..api import tiers as tiers_api
from ..api import findings as findings_api
from ..api import interiors as interiors_api
from ..api import npcs as npcs_api
from ..api import gear as gear_api
from ..api import roster as roster_api
from ..api import providers as providers_api
from ..api import review_bridge
from ..api import rig as rig_api
from ..api import farm as farm_api
from ..api import personas as personas_api
from ..api import save as save_api
from ..api import game_state as game_state_api
from ..api import tutorial as tutorial_api
from ..api import perks as perks_api
from ..api.story import EPILOGUES, ORDERS, PROLOGUE, Story, cleared_in_lands
from ..api.world import SCOUTED, SETTLED, WILD, WITHERED, World, build_world
from . import imgui_controls, pixelart

#: Emission wavelengths that stand for the two lit room states.
SCOUTED_NM = 488.0
SETTLED_NM = 545.0

#: Walking speed in world units per second, and the sprint multiplier.
WALK_SPEED = 190.0
SPRINT = 2.6

#: Iris' own life in real-time combat, and how many photons her casting
#: energy holds -- a real-time spell used to spend story.unbound (labels
#: taken off, ever) as if it were a wallet. It is its own bar now.
IRIS_MAX_HP = 100
PHOTONS_MAX = 100

#: How fast the camera catches up with Iris, per second.
CAMERA_LAG = 7.0

#: How closely Lumi follows, in world units.
LUMI_TRAIL = 26.0

#: Half-width of Iris' collision box. A gate is one tile (18 units) wide, so a
#: 12-unit box leaves three units of clearance each side -- forgiving enough to
#: walk through, small enough that she cannot stand inside a wall.
BODY = 6.0

#: How far a blocked move is nudged sideways to slip past a corner.
CORNER_SLIP = 3.0

#: Jumping, on the model Zelda Classic uses for its top-down z axis (see
#: ``junk/ZQuestClassic/src/zc/hero.cpp``): height and *fall velocity* are the
#: state, gravity is added to the velocity each frame and the velocity is taken
#: off the height, and landing is the moment height reaches zero.
GRAVITY = 900.0
JUMP_SPEED = 235.0

#: Releasing the button while still rising cuts the jump short, which is what
#: gives a jump a *height you choose* rather than one fixed arc. Their
#: ``jump_loss``.
JUMP_CUT = 620.0

#: How high off the ground counts as clear of the things you can hop.
HOP_HEIGHT = 5.0

#: What a jump carries you over. Not walls and not buildings -- those are the
#: shape of the place -- but the low things that would otherwise be a detour.
HOPPABLE = frozenset({T.WATER, T.MARSH, T.FENCE, T.TAR})

#: View heights: walking, and the range the shoulders zoom over.
VIEW_HEIGHT = 330.0
VIEW_MIN = 240.0
VIEW_MAX = 3000.0

#: Beyond this the view is a map and per-tile detail becomes noise.
MAP_THRESHOLD = 1400.0

#: How long the land banner stays up after Iris crosses into a new land, and
#: how much of that is spent fading rather than fully lit. A readout that sat
#: on screen forever was blocking the view of the very world it described; one
#: that names the place and gets out of the way does the same job without
#: doing that.
LAND_BANNER_SECONDS = 3.5
LAND_BANNER_FADE = 1.0

#: How fast dialogue letters appear, Zelda-style, and how many of them share
#: one blip -- one tick a character reads as a buzz at this rate, so the
#: sound lags a step behind the text instead of matching it one for one.
TYPE_CPS = 32.0
TYPE_BLIP_EVERY = 2

#: How close the bottom band's room title shows. `self.here` is the
#: *nearest* room with no cutoff of its own -- across open ground that can be
#: many tiles away, and the band showing its name anyway was most of why it
#: never went away. Slightly wider than talking range (`npcs.nearest`'s
#: ``TILE * 1.6``), since reading a name is more forgiving than starting a
#: conversation.
ROOM_LABEL_RANGE = T.TILE * 2.0

#: How far from her own tile _door_scene samples for a cave mouth or rift.
#: Requiring her exact centre inside the one-tile door was most of what "the
#: door is too small to hit" was: this widens the check to the ring of tiles
#: around wherever she is standing, not just that one cell.
DOOR_REACH = T.TILE * 0.9

#: How often free-roam play autosaves itself, in seconds of played time
#: (paused while loading, talking, fighting or in a menu -- see update()).
#: The explicit saves (a new journey, a Warden's seal, a page's own request)
#: are a ceremony; this is the plain safety net between them.
AUTOSAVE_SECONDS = 60.0

#: How much one wheel "tick" changes view_height, as a fraction per unit of
#: InputMap.wheel_delta(). Qt reports roughly 120 per physical click of a
#: mouse wheel; at this sensitivity that is about a 12% zoom step, which
#: reads as one deliberate notch rather than a jump. A trackpad's continuous,
#: much smaller deltas fall out of the same formula for free.
WHEEL_ZOOM_SENSITIVITY = 0.001

#: A wild encounter opens at this fraction of the overworld's own zoom --
#: closer than normal play, which is what "zoom in" going into a fight reads
#: as -- and eases back out to it (see BATTLE_ZOOM_SETTLE) rather than
#: snapping, over ENCOUNTER_FLASH_SECONDS. A white flash fades over the same
#: window in _draw_battle, so the two together read as one beat: zoom, flash,
#: settled into the fight.
BATTLE_ZOOM_START = 0.55
BATTLE_ZOOM_SETTLE = 7.0
ENCOUNTER_FLASH_SECONDS = 0.4

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

#: Tile kind -> sprite, for a room's own grid (:mod:`.interiors`). Every one
#: of these is already-shipped art (`gui/pixelart.py`'s ``INDOORS``) -- what
#: was missing was a room to draw it in, not the art.
INDOOR_TILE_SPRITES = {
    T.BOARDS: "boards",
    T.IWALL: "iwall",
    T.COUNTER: "counter",
    T.TABLE: "table",
    T.BED: "bed",
    T.SHELF: "shelf",
    T.HEARTH: "hearth",
    T.ALTAR: "altar",
    T.RUG: "rug",
    T.ANVIL: "anvil",
    T.BARREL: "barrel",
    T.EXIT: "exit",
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

#: Zelda-style overworld weapons: stats, reach, cooldowns, and visual palette.
WEAPON_DATA: dict[str, dict] = {
    "sword": {"name": "Laser Sword", "damage": 25.0, "reach": 22.0, "cooldown": 0.22, "color": (0.4, 0.9, 1.0, 1.0), "sfx": "slash"},
    "lance": {"name": "Photon Lance", "damage": 35.0, "reach": 36.0, "cooldown": 0.40, "color": (1.0, 0.85, 0.3, 1.0), "sfx": "thrust"},
    "axe": {"name": "Beam Axe", "damage": 50.0, "reach": 24.0, "cooldown": 0.55, "color": (1.0, 0.4, 0.3, 1.0), "sfx": "cleave"},
    "rapier": {"name": "Strobe Rapier", "damage": 15.0, "reach": 20.0, "cooldown": 0.12, "color": (0.9, 0.4, 1.0, 1.0), "sfx": "stab"},
    "sai": {"name": "Quantum Sai", "damage": 20.0, "reach": 18.0, "cooldown": 0.16, "color": (0.4, 1.0, 0.6, 1.0), "sfx": "slash"},
}

#: Zelda-style overworld magic spells: photon costs, effects, cooldowns, and colors.
MAGIC_DATA: dict[str, dict] = {
    "flame": {"name": "Photon Flame", "cost": 10, "damage": 30.0, "range": 80.0, "cooldown": 0.35, "color": (1.0, 0.5, 0.2, 1.0)},
    "heal": {"name": "Fluorescence Heal", "cost": 20, "heal": 35.0, "cooldown": 0.80, "color": (0.3, 1.0, 0.6, 1.0)},
    "shield": {"name": "FRET Shield", "cost": 15, "duration": 5.0, "cooldown": 1.00, "color": (0.2, 0.85, 1.0, 1.0)},
}

#: What every tile is multiplied by underneath. Cool, and dimmer than the lit
#: world without being so dark that the geography stops reading -- the point of
#: the dark manifold is that you already know the way.
DARK_WASH = (0.66, 0.68, 0.80, 1.0)

#: What an unexplored land looks like on the map -- flat and near-black, so
#: an explored one still reads as ground rather than as another shade of fog.
FOG_COLOR = (0.03, 0.035, 0.05, 1.0)

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
        "Escape": Action.CANCEL, "Backspace": Action.CANCEL, "Tab": Action.MENU,
    },
    "wasd": {
        "w": Action.UP, "s": Action.DOWN, "a": Action.LEFT, "d": Action.RIGHT,
        " ": Action.CONFIRM, "Shift": Action.CONFIRM,
        "q": Action.SHOULDER_L, "e": Action.SHOULDER_R,
        "Escape": Action.CANCEL, "Backspace": Action.CANCEL, "Tab": Action.MENU,
    },
    "left-handed": {
        "i": Action.UP, "k": Action.DOWN, "j": Action.LEFT, "l": Action.RIGHT,
        " ": Action.CONFIRM, "Enter": Action.CONFIRM,
        "u": Action.SHOULDER_L, "o": Action.SHOULDER_R,
        "Escape": Action.CANCEL, "Backspace": Action.CANCEL, "Tab": Action.MENU,
    },
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
        # Every setting the OPTIONS and GAMELOGIC tabs read, defaulted here
        # rather than in `setup`. A game that has not been bound to a host is
        # still a game that can be asked what its settings are -- and half of
        # these were only set in `setup`, so `_menu_rows` raised AttributeError
        # on any game that had not been run.
        self.scheme = "arrows"
        self.walk_speed = WALK_SPEED
        self.view_height = VIEW_HEIGHT
        # Quieter than Audio's own 1.0/1.0 defaults out of the box: the synth
        # music runs under dialogue and easily drowns it out at full volume.
        self.music_volume = 0.1
        self.sfx_volume = 0.5
        self.screen_mode = False
        self.soundtrack_theme = self.SOUNDTRACKS[0]
        self.enemy_aggro_radius = 4.5
        self.action_combat_enabled = True
        self.particle_fx_enabled = True
        self.crt_filter_enabled = False
        self.ui_accent_tone = "Gold"
        #: The last few frames' cost in milliseconds, oldest first, drawn as a
        #: sparkline in OPTIONS. Bounded, so a run left open overnight does not
        #: quietly grow a list nobody reads past the last second of it.
        self.frame_ms: collections.deque[float] = collections.deque(maxlen=90)

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
        # The settings themselves are the game's, and were defaulted in
        # __init__. What happens here is only the half that needs a host:
        # pushing them at the controller and the mixer.
        host.keys.bindings = dict(SCHEMES[self.scheme])
        host.audio.set_music_volume(self.music_volume)
        host.audio.set_sfx_volume(self.sfx_volume)
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
        #: Which way Lumi is drawn facing -- its own, from how it is actually
        #: moving, not Iris's (see the chase in update()).
        self.lumi_facing = "down"
        self._clock = 0.0
        # Short-lived feedback: damage numbers, the burst when a label comes
        # off, the photons that fly into you afterwards. Two fields, because
        # the battle screen and the overworld are different coordinate spaces
        # and a spark from one drawn in the other lands in a field somewhere.
        self.sparks = chigame.ParticleField()
        self.battle_sparks = chigame.ParticleField()
        #: Appearing-text state: which line is revealing and how far into it,
        #: shared by every dialogue box so only one line ever animates.
        self._type_key: str | None = None
        self._type_chars = 0.0
        #: Where the two portraits were drawn last frame, so a hit can put its
        #: number over the thing that took it. The layout does not move, so a
        #: frame of lag is invisible.
        self._portraits: dict[str, tuple[float, float]] = {}
        #: The battle screen's own scale, so feedback is sized in the same
        #: units as the panel it lands on rather than in raw world units.
        self._portrait_scale = 1.0
        # Overworld Zelda Action combat & magic state
        self.active_weapon = "sword"
        self.weapons = ["sword", "lance", "axe", "rapier", "sai"]
        self.active_magic = "flame"
        self.magics = ["flame", "heal", "shield"]
        self._attack_cooldown = 0.0
        self._attack_anim_timer = 0.0
        self._attack_arc_pos = (0.0, 0.0)
        self._magic_cooldown = 0.0
        self._shield_timer = 0.0
        self._iris_hit_flash = 0.0
        #: Her own life and casting energy -- real-time combat used to show a
        #: "-10 HP" number that never actually cost her anything, and magic
        #: spent story.unbound (labels taken off, ever -- a permanent
        #: narrative counter scripts gate content on) as if it were a
        #: wallet, corrupting it on every spell. Both are their own bars now.
        self.iris_max_hp = IRIS_MAX_HP
        self.iris_hp = IRIS_MAX_HP
        self.photons_max = PHOTONS_MAX
        self.photons = PHOTONS_MAX // 2

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
        self.workshop = crafting_api.Workshop()
        self.cleared = set()
        #: Land names Iris has physically stood in -- fog of war on the map
        #: is everywhere else, regardless of what wandered into view there.
        self.explored: set[str] = set()
        self.salvaged = set()
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
        self._land_banner_land = None
        self._land_banner_timer = 0.0
        self._autosave_timer = 0.0
        self._battle_intro = 0.0
        self._encounter_cooldown = 0.0
        self.interior: interiors_api.Interior | None = None
        self.indoor_people: list[npcs_api.Npc] = []
        self._indoor_pos = [0.0, 0.0]
        self._interior_return: list[float] | None = None

        # Tile kind -> RGBA, as an array so a whole window maps in one index.
        self._palette = np.zeros((max(TILE_COLORS) + 1, 4), dtype=np.float32)
        for kind, colour in TILE_COLORS.items():
            self._palette[kind] = colour
        self.scene_batch = host.batch

        # The pixel-art atlas: authored as string art, packed and uploaded once.
        image, self._uvs, self._sprite_tiles = pixelart.build_atlas()
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

        # A real building sprite is wider than the one BUILDING tile its room
        # sits on, and _building draws it exactly that wide -- so walking
        # blocked only the grid's own tile let her step straight through the
        # painted wall on either side of the door. The columns either side of
        # a room's own tile that its sprite actually covers get the same
        # whole-tile solidity BUILDING has (see _solid), computed once here
        # rather than per frame: it depends only on which sprite a room's
        # address picked, which never changes after the world is built.
        self._building_solid: frozenset[tuple[int, int]] = frozenset(
            self._building_footprint())

    def _building_footprint(self):
        """Extra grid cells a room's building sprite covers besides its own.

        Yields
        ------
        tuple of int
            ``(col, row)`` of a cell to treat as solid alongside the room's
            own ``BUILDING`` tile.
        """
        for room in self.world.rooms:
            sprite = self._house_sprite(room, lit=False)
            tiles_wide, _ = self._sprite_tiles.get(sprite, (1.0, 1.0))
            spread = int(round((tiles_wide - 1) / 2))
            if spread <= 0:
                continue
            col = int(room.position[0] // T.TILE)
            row = int(room.position[1] // T.TILE)
            for offset in range(1, spread + 1):
                yield (col - offset, row)
                yield (col + offset, row)

        # Screen-by-screen holds the camera on one composed screen and flips
        # it when she crosses an edge, the way an 8-bit overworld does;
        # scrolling instead follows her continuously. Scrolling is the
        # default, by request; switchable from OPTIONS ("camera: ...").
        self.screen_mode = False
        self.screen_at = (0, 0)
        self.flip_from: tuple[float, float] | None = None
        self.flip_left = 0.0

        self.facing = "down"
        self.walking = False
        self._walk_clock = 0.0
        #: Height above the ground, and the velocity taking her back to it.
        self.z = 0.0
        self.fall = 0.0
        self.jumping = False

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
        # The other bench: reagents gathered in the world, combined into
        # what protects a label against its own bleaching.
        self.workshop = crafting_api.Workshop()
        self.explored: set[str] = set()
        #: Dark-manifold ruin cells already picked clean this run. A ruin is a
        #: collapsed premises, and what is worth taking out of one is taken
        #: once -- otherwise standing at a ruin tapping the key is a reagent
        #: fountain and the crafting economy has no economy in it.
        self.salvaged: set[tuple[int, int]] = set()
        # XP, level and streaks -- a person's standing, not a run's, so it
        # loads once here rather than in _restore() and keeps its own save
        # file (see .game_state) instead of living in the run's. Riding on
        # whatever directory the run save was pointed at (a temp one, for a
        # test or a capture) rather than always the real default is what
        # keeps a headless test from writing into the real player's
        # standing; a real run passes no save_path, so this still resolves
        # to GameState's own real default file.
        game_state_path = (
            self._save_path.parent / "lumis_quest_game_state.json"
            if self._save_path is not None else None
        )
        self.game_state = game_state_api.GameState.load(path=game_state_path)
        self._pending_first_clear = False
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
        for species_key, probe_id, hp, infusion in state.team:
            species = bestiary_api.BY_KEY.get(species_key)
            if species is None:
                continue
            beast = bestiary_api.Beast(species=species, label=creatures.get(probe_id),
                                       infusion=infusion)
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
        self.workshop = crafting_api.Workshop(
            materials=dict(state.materials), crafted=list(state.crafted),
        )
        self.explored = set(state.explored)
        self.salvaged = set()
        for cell in state.salvaged:
            col_text, _, row_text = cell.partition(",")
            try:
                self.salvaged.add((int(col_text), int(row_text)))
            except ValueError:
                continue
        self.iris_hp = self.iris_max_hp if state.iris_hp < 0 else min(state.iris_hp, self.iris_max_hp)
        self.photons = (self.photons_max // 2 if state.photons < 0
                        else min(state.photons, self.photons_max))
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
                 int(f.hp), f.beast.infusion)
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
            materials=dict(self.workshop.materials),
            crafted=list(self.workshop.crafted),
            explored=sorted(self.explored),
            salvaged=[f"{col},{row}" for col, row in sorted(self.salvaged)],
            iris_hp=int(self.iris_hp),
            photons=int(self.photons),
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

    def _nearby_room(self):
        """The nearest room, but only if she is actually near it.

        :attr:`here` has no cutoff of its own -- it is *the* nearest room
        anywhere in the world, which across open ground can be many tiles
        away. Callers that mean "standing at" rather than "nearest of all"
        add their own distance check on top of it (:meth:`_try_encounter`
        does the same against :data:`ROOM_LABEL_RANGE`'s sibling); this is
        that check for the bottom band's room title, which used to show
        wherever the nearest room happened to be and so almost never went
        away.

        Returns
        -------
        Room or None
            ``None`` when there is no room within :data:`ROOM_LABEL_RANGE`.
        """
        room = self.here
        if room is None:
            return None
        if math.hypot(room.position[0] - self.iris[0],
                       room.position[1] - self.iris[1]) > ROOM_LABEL_RANGE:
            return None
        return room

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
        self.frame_ms.append(float(dt) * 1000.0)
        # Feedback ages regardless of what screen is up, so a number thrown
        # just before a fight ends still finishes rising. Empty fields cost
        # nothing, which is why this sits above every early return.
        self.sparks.update(dt)
        self.battle_sparks.update(dt)
        if self.phase == "loading":
            self._load_next()
            return
        if self.phase == "title":
            self._title_input(keys)
            return
        if self.phase == "prologue":
            _, body = PROLOGUE[min(self.prologue_index, len(PROLOGUE) - 1)]
            key = f"prologue:{self.prologue_index}"
            # Advanced before it is asked about: checking "done" against a
            # key that has never been advanced falls through to
            # ``_revealed``'s no-animator fallback and shows the whole card,
            # which a confirm mashed right on a card's first frame would hit.
            self._reveal_advance(key, body, dt)
            done = self._revealed(key, body) == body
            if keys.just_pressed(Action.CANCEL):
                self._after_prologue()
                return
            if keys.just_pressed(Action.CONFIRM):
                # The first press finishes the line rather than skipping it --
                # a reader mid-sentence who taps through does not want to lose
                # the second half of what Iris just said.
                if done:
                    self.prologue_index += 1
                    if self.prologue_index >= len(PROLOGUE):
                        self._after_prologue()
                else:
                    self._type_chars = float(len(body))
            return
        if self.phase == "epilogue":
            cards = self._epilogue_cards()
            _, body = cards[min(self.epilogue_index, len(cards) - 1)]
            key = f"epilogue:{self.epilogue_index}"
            self._reveal_advance(key, body, dt)
            done = self._revealed(key, body) == body
            if keys.just_pressed(Action.CONFIRM) or keys.just_pressed(Action.CANCEL):
                if done:
                    self.epilogue_index += 1
                    if self.epilogue_index >= len(cards):
                        self.story.witness("dawn")
                        self.phase = "play"
                else:
                    self._type_chars = float(len(body))
            return

        # The teaching sequence watches the same state the story does, and it
        # watches through battles too -- half its steps complete inside one.
        self.tutorial.observe(self)

        # The land banner names wherever Iris just arrived, then counts itself
        # down. It is retimed only on a genuine crossing, not every frame she
        # happens to still be standing in the same land.
        land = self.land
        if land is not self._land_banner_land:
            self._land_banner_land = land
            self._land_banner_timer = LAND_BANNER_SECONDS if land is not None else 0.0
        elif self._land_banner_timer > 0.0:
            self._land_banner_timer = max(0.0, self._land_banner_timer - dt)
        if land is not None:
            # Fog of war on the map is everywhere Iris has not physically
            # stood, regardless of what has wandered into view there --
            # a set that only grows, so nothing is ever un-explored.
            self.explored.add(land.name)

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
            if self._battle_intro > 0.0:
                # The fight opens zoomed in and settles to its normal
                # framing, with _draw_battle fading a flash out over the same
                # window -- the beat every game this shape opens a random
                # encounter with, cut to instead of eased into because the
                # camera was, until this frame, still the overworld's.
                self._battle_intro = max(0.0, self._battle_intro - dt)
                camera = self.host.camera
                blend = min(BATTLE_ZOOM_SETTLE * dt, 1.0)
                camera.height += (self.view_height - camera.height) * blend
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
            self._dialogue_input(keys, dt)
            return
        if self.interior is not None:
            self._update_indoors(dt, keys)
            return
        # Action timers update
        self._attack_cooldown = max(0.0, getattr(self, "_attack_cooldown", 0.0) - dt)
        self._attack_anim_timer = max(0.0, getattr(self, "_attack_anim_timer", 0.0) - dt)
        self._magic_cooldown = max(0.0, getattr(self, "_magic_cooldown", 0.0) - dt)
        self._shield_timer = max(0.0, getattr(self, "_shield_timer", 0.0) - dt)
        self._iris_hit_flash = max(0.0, getattr(self, "_iris_hit_flash", 0.0) - dt)
        self._encounter_cooldown = max(0.0, getattr(self, "_encounter_cooldown", 0.0) - dt)
        self._update_overworld_enemies(dt)

        if keys.just_pressed(Action.SHOULDER_L):
            neighbour = npcs_api.nearest(self.people, *self.iris)
            door = self._door_scene()
            building = self._building_scene()
            ruin = self._ruin_scene()
            if self._overhear():
                pass
            elif neighbour is not None and neighbour.kind != "beast":
                self._talk_to(neighbour)
            elif ruin is not None:
                self._salvage_dark_ruin(*ruin)
            elif building is not None:
                self._enter_building(*building)
            elif door:
                self._play_scene(door)
            else:
                self._attack_overworld()

        if keys.just_released(Action.SHOULDER_R):
            if not keys.is_held(Action.SHOULDER_R):
                self._cast_magic()

        # A tap jumps, a hold sprints. Nine actions is the whole controller and
        # they were all spoken for, so the jump shares the key rather than
        # asking the player to learn a tenth.
        if keys.just_pressed(Action.CONFIRM) and not self.jumping and self.z <= 0.0:
            self.jumping = True
            self.fall = -JUMP_SPEED
            self._sound("jump", 520.0)
        if self.jumping and self.fall < 0.0 and not keys.is_held(Action.CONFIRM):
            # Let go early and she does not go as high.
            self.fall = min(0.0, self.fall + JUMP_CUT * dt)
        self._airborne(dt)

        dx, dy = keys.axis()
        self.walking = bool(dx or dy)
        if self.walking:
            length = math.hypot(dx, dy) or 1.0
            speed = self.walk_speed * (SPRINT if keys.is_held(Action.CONFIRM) else 1.0)
            if self.game_state.level >= 2:
                speed *= 1.15
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
        if keys.just_pressed(Action.CANCEL):
            # Cancel used to double as hold-to-zoom-out, which made Escape's
            # actual job -- opening the menu -- depend on exactly how long it
            # was held before release. The wheel already zooms both ways (see
            # below), so Cancel is just the menu key now, like every game of
            # this shape ships it.
            self.menu_open = True
            self.menu_row = 0

        # A mouse is not a gamepad input (see InputMap.wheel_delta), so this
        # is on top of the shoulder-button zoom above, never a replacement
        # for it -- scrolled up (negative dy) is zoom in, matching a map.
        wheel = keys.wheel_delta()
        if wheel:
            factor = 1.0 + wheel * WHEEL_ZOOM_SENSITIVITY
            self.view_height = max(VIEW_MIN, min(VIEW_MAX, self.view_height * factor))

        self._unstick()
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

        # A quiet safety net between the ceremony saves (a new journey, a
        # Warden's seal, a page's own "remember this" request): those cover
        # the moments the story cares about, not the fifteen minutes of
        # ordinary walking, fighting and talking in between, which used to be
        # lost outright to a crash or a closed window. Only reached in free
        # roam -- battle, menu, dialogue and every curtain phase return
        # before this line, so autosave never fires mid-transaction.
        self._autosave_timer += dt
        if self._autosave_timer >= AUTOSAVE_SECONDS:
            self._autosave_timer = 0.0
            self.save_run()

        # A beast you walk into is a fight, so the wilds are dangerous in a way
        # that standing beside a building is not.
        if self.battle is None and self.pool and getattr(self, "_encounter_cooldown", 0.0) <= 0.0:
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
                step_x = to_lumi[0] / distance * move
                step_y = to_lumi[1] / distance * move
                self.lumi[0] += step_x
                self.lumi[1] += step_y
                # Its own facing, from the step it just took -- not Iris's,
                # which is wherever *she* last turned and often points a
                # different way than the catch-up hound is actually walking.
                if abs(step_y) >= abs(step_x):
                    self.lumi_facing = "down" if step_y > 0 else "up"
                else:
                    self.lumi_facing = "right" if step_x > 0 else "left"

        camera = self.host.camera
        blend = min(CAMERA_LAG * dt, 1.0)
        if self.show_map:
            centre, height = self._map_view()
        elif self.screen_mode:
            centre, height = self._screen_view(dt)
            # A flip is a hard cut in the geometry and a slide on screen, so
            # the camera is placed rather than eased -- easing on top of the
            # slide reads as drift.
            camera.center[0], camera.center[1] = centre
            camera.height += (height - camera.height) * blend
            return
        else:
            centre, height = (tuple(self.iris), self.view_height)
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
        if role == "lanternwright":
            # Her four screens and Iris' answer both live in data/story.json;
            # the answer is the doctrine's whole argument in a sentence, so
            # which one it is depends on who you pledged to.
            from ..api.story import LANTERNWRIGHT

            return ("lanternwright",
                    {"lines": LANTERNWRIGHT, "reply": (self.story.reply,)}, "")
        if npc.kind == "wraith":
            # The species is the subject, so the scene can hand it back to the
            # rekindle action without the renderer knowing what a wraith is.
            return ("wraith", lines, npc.species)
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

    def _dialogue_input(self, keys, dt: float) -> None:
        """Step the running scene from the pad.

        Parameters
        ----------
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        dt : float
            Seconds elapsed, for the appearing-text effect.
        """
        screen = self.screen
        if screen is None:
            self.speaking = None
            return
        # Each screen the runner hands back is a fresh object, so its id is
        # a key that resets the reveal exactly when the line does. Advanced
        # unconditionally, *then* checked: asking whether it is done before
        # it has ever been advanced for this key falls through to
        # ``_revealed``'s no-animator fallback and shows the whole line on
        # the very first frame.
        key = f"screen:{id(screen)}"
        text = screen.text or ""
        self._reveal_advance(key, text, dt)
        done = self._revealed(key, text) == text
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
                if not done:
                    self._type_chars = float(len(text))
                else:
                    self.screen = self.runner.choose(self.menu_index)
                    self.menu_index = 0
                    self._after_step(self.speaking)
            return
        if keys.just_pressed(Action.CONFIRM):
            if not done:
                self._type_chars = float(len(text))
            else:
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

    def _reveal_advance(self, key: str, text: str, dt: float) -> None:
        """Advance the appearing-text effect for whichever line is showing.

        Parameters
        ----------
        key : str
            Identifies the line -- a new key restarts the reveal rather than
            continuing wherever the last line left off.
        text : str
            The full line.
        dt : float
            Seconds elapsed.
        """
        if key != self._type_key:
            self._type_key = key
            self._type_chars = 0.0
        shown = int(self._type_chars)
        if shown >= len(text):
            return
        self._type_chars = min(len(text), self._type_chars + TYPE_CPS * dt)
        if int(self._type_chars) // TYPE_BLIP_EVERY > shown // TYPE_BLIP_EVERY:
            self._sound("type", 900.0)

    def _revealed(self, key: str, text: str) -> str:
        """The visible prefix of an appearing-text line, for drawing.

        Parameters
        ----------
        key : str
            Identifies the line.
        text : str
            The full line.

        Returns
        -------
        str
            ``text`` truncated to how much of it has been revealed. A ``key``
            nothing has advanced -- a screenshot taken without stepping
            :meth:`update` -- shows the line whole rather than blank.
        """
        if key != self._type_key:
            return text
        return text[:int(self._type_chars)]

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

    def _gather(self, material_key: str, at: tuple[float, float], chance: float = 1.0) -> None:
        """Maybe add a bench reagent to the shelf, with feedback if it lands.

        Parameters
        ----------
        material_key : str
            A key into :data:`chisurf.plugins.misc.games.lumis_quest.api.crafting.MATERIALS`.
        at : tuple of float
            Where to rise the pickup notice.
        chance : float, optional
            0..1. A drop, not a guarantee -- the world does not hand over a
            reagent every time you cut the grass it grows in.
        """
        if random.random() >= chance:
            return
        self.workshop.gather(material_key)
        material = crafting_api.MATERIALS.get(material_key)
        name = material.name if material is not None else material_key
        self.sparks.rise(f"+1 {name}", at, color=(0.55, 0.85, 0.95, 1.0), height=7.0)

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
        elif request.kind == "rekindle":
            species_key = request.args.get("species", "")
            if self.labels:
                used_label = self.labels.pop(0)
                if self.speaking is not None and self.speaking in self.people:
                    self.people.remove(self.speaking)
                self.sparks.rise("Rekindled!", tuple(self.iris), color=(0.4, 0.95, 0.7, 1.0), height=9.0)
                self.sparks.burst(tuple(self.iris), count=16, kind="sparkle", color=(0.4, 0.95, 0.7, 1.0))
                self._sound("heal", 750.0)
        elif request.kind == "minigame":
            game_kind = request.args.get("game", "minesweeper")
            self.photons = min(self.photons_max, self.photons + 40)
            reward = self.game_state.record_review(difficulty="easy")
            self._sound("confirm", frequency=680.0)
            self.sparks.rise(f"Tavern Minigame Won! +{reward['xp']} XP", tuple(self.iris),
                             color=(0.4, 0.95, 0.9, 1.0), height=10.0)
            self.sparks.burst(tuple(self.iris), count=14, kind="sparkle", color=(0.4, 0.95, 0.9, 1.0))

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
        # itself again from the other side -- and out of anything that is solid
        # on this side but was not on the other.
        if not self._solid(self.iris[0], self.iris[1] + T.TILE):
            self.iris[1] += T.TILE
        self._unstick()

    def _door_scene(self) -> str:
        """The scene a cave mouth or rift near Iris runs, if any.

        Checked against every tile her body's box touches rather than only
        the one cell her exact centre sits in -- a door is one tile wide, and
        requiring her centre to be inside that exact cell before Confirm did
        anything made it genuinely hard to walk up to and press the key at
        the right moment, especially approaching at an angle.

        Returns
        -------
        str
            A scene id, or empty when nothing crossable is close enough.
        """
        for offset_x in (-DOOR_REACH, 0.0, DOOR_REACH):
            for offset_y in (-DOOR_REACH, 0.0, DOOR_REACH):
                tile = self.world.tile_at(
                    int((self.iris[0] + offset_x) // T.TILE),
                    int((self.iris[1] + offset_y) // T.TILE), self.dark)
                if tile == T.CAVE:
                    return "cave"
                if tile == T.RIFT:
                    return "rift"
        return ""

    def _building_scene(self) -> tuple[int, int, int] | None:
        """A house, tavern, shop, smithy, shrine or hall near Iris, if any.

        The overworld exterior is one tile; the room behind it, generated by
        :mod:`.interiors`, was built and tested and had nothing on the
        overworld that opened it -- this is that opening, the same
        ring-of-samples reach :meth:`_door_scene` uses so a door a tile wide
        is not also a pixel wide to actually hit.

        Returns
        -------
        tuple of int or None
            ``(tile, col, row)``, or ``None`` when nothing enterable is close
            enough.
        """
        for offset_x in (-DOOR_REACH, 0.0, DOOR_REACH):
            for offset_y in (-DOOR_REACH, 0.0, DOOR_REACH):
                col = int((self.iris[0] + offset_x) // T.TILE)
                row = int((self.iris[1] + offset_y) // T.TILE)
                tile = self.world.tile_at(col, row, self.dark)
                if tile in T.ENTERABLE:
                    return tile, col, row
        return None

    def _ruin_scene(self) -> tuple[int, int] | None:
        """A dark-manifold ruin near Iris she has not yet picked clean, if any.

        Only in the dark manifold -- on the lit side these cells are living
        premises and open as interiors instead. Same ring-of-samples reach as
        :meth:`_door_scene`, for the same reason.

        Returns
        -------
        tuple of int or None
            ``(col, row)`` of the ruin cell, or ``None`` when there is no
            unsalvaged ruin close enough.
        """
        if not self.dark:
            return None
        for offset_x in (-DOOR_REACH, 0.0, DOOR_REACH):
            for offset_y in (-DOOR_REACH, 0.0, DOOR_REACH):
                col = int((self.iris[0] + offset_x) // T.TILE)
                row = int((self.iris[1] + offset_y) // T.TILE)
                if (self.world.tile_at(col, row, True) == T.RUIN
                        and (col, row) not in self.salvaged):
                    return col, row
        return None

    def _salvage_dark_ruin(self, col: int, row: int) -> None:
        """Pick a collapsed premises clean -- once, ever.

        Every ruin on the dark side is a building someone kept stocked on the
        lit side, so what is left in it is a bench reagent. Which one is
        decided by the cell, not by a roll: reloading a save and walking back
        cannot reroll a ruin into a rarer find. The dark manifold favours the
        reagents the lit world drops rarely -- that is the reason to go down.

        Parameters
        ----------
        col, row : int
            The ruin cell, from :meth:`_ruin_scene`.
        """
        self.salvaged.add((col, row))
        # Weighted toward the beast-drop rarities; deterministic per cell.
        stock = ("pagfp", "trolox", "godcat", "trolox", "pagfp", "roxs", "godcat")
        material_key = stock[(col * 31 + row * 17) % len(stock)]
        self.workshop.gather(material_key)
        material = crafting_api.MATERIALS[material_key]
        at = (col * T.TILE + T.TILE / 2.0, row * T.TILE + T.TILE / 2.0)
        self.sparks.burst(at, count=10, kind="sparkle", color=(0.75, 0.65, 0.95, 1.0))
        self.sparks.rise(f"salvaged {material.name}", at,
                         color=(0.75, 0.65, 0.95, 1.0), height=8.0)
        self._sound("pickup", 540.0)

    def _room_at_tile(self, col: int, row: int):
        """Which page's building stands at a cell, if any.

        Parameters
        ----------
        col, row : int
            Grid coordinates.

        Returns
        -------
        chisurf.plugins.misc.games.lumis_quest.api.world.Room or None
            ``None`` when the cell is not a page's own building -- a
            settlement's tavern, shop, smithy, shrine and hall are not tied
            to any one page.
        """
        for room in self.world.rooms:
            if room.tile == (col, row):
                return room
        return None

    def _enter_building(self, tile: int, col: int, row: int) -> None:
        """Step through a door into the room behind it.

        Parameters
        ----------
        tile : int
            The overworld tile kind (``T.ENTERABLE``'s key).
        col, row : int
            Where it stands.
        """
        kind = T.ENTERABLE[tile]
        room = self._room_at_tile(col, row) if tile == T.BUILDING else None
        village = self.world.village_at((col + 0.5) * T.TILE, (row + 0.5) * T.TILE)
        key = interiors_api.key_for(village, tile, col, row, room=room)
        title = interiors_api.title_for(kind, village, room=room)
        self.interior = interiors_api.build(key, kind, title)
        self.indoor_people = npcs_api.indoor_population(self.interior)
        self._interior_return = list(self.iris)
        door_col, door_row = self.interior.door
        # A step inside the door, not on it -- landing exactly on the door
        # cell is how she would walk straight back out on the very first
        # _update_indoors call, which checks that same cell every frame.
        self._indoor_pos = [(door_col + 0.5) * T.TILE, (door_row - 0.6) * T.TILE]
        self.facing = "up"
        self._sound("door", 440.0)

    def _leave_interior(self) -> None:
        """Step back out to wherever the door was on the overworld."""
        if self._interior_return is not None:
            self.iris = self._interior_return
        self.interior = None
        self.indoor_people = []
        self._interior_return = None
        self.facing = "down"
        self._sound("door", 380.0)

    def _indoor_solid(self, x: float, y: float) -> bool:
        """Whether a point inside the current interior is inside a wall.

        The interior's own :meth:`~.interiors.Interior.tile_at` already
        answers "outside the room" as a wall, so a walker cannot leave except
        through the door -- this only adds the per-quadrant solidity check
        :meth:`_solid` uses outdoors, so a counter or a table blocks the half
        of its tile it stands on rather than the whole thing.

        Parameters
        ----------
        x, y : float
            Candidate position in world units, local to the room.

        Returns
        -------
        bool
            True when the point is inside something solid.
        """
        col = int(x // T.TILE)
        row = int(y // T.TILE)
        return bool(T.solidity(self.interior.tile_at(col, row)) & T.quadrant(x, y))

    def _update_indoors(self, dt: float, keys) -> None:
        """Walk inside a room, and step back out through its door.

        A room is small enough to fit inside one screen by construction
        (:mod:`.interiors`), so the camera holds it fixed rather than
        following her the way the overworld's does.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        # Fixed on the room's own centre, every frame -- cheap enough not to
        # bother caching, and it never needs the overworld's lerp since
        # nothing here moves it. camera.height in tiles is the same
        # convention screens_api.HEIGHT already sets for screen mode
        # outdoors: every room is sized to fit inside one screen (see
        # interiors.SIZES), so the same height-only convention fits it too.
        width, height = self.interior.size
        camera = self.host.camera
        camera.center[0] = width * 0.5 * T.TILE
        camera.center[1] = height * 0.5 * T.TILE
        camera.height = height * T.TILE

        dx, dy = keys.axis()
        self.walking = bool(dx or dy)
        if self.walking:
            length = math.hypot(dx, dy) or 1.0
            step_x = dx / length * self.walk_speed * dt
            step_y = dy / length * self.walk_speed * dt
            # One axis at a time, same as _step outdoors, so she slides along
            # a wall on a diagonal instead of being stopped dead by it.
            for axis_dx, axis_dy in ((step_x, 0.0), (0.0, step_y)):
                if axis_dx == 0.0 and axis_dy == 0.0:
                    continue
                nx = self._indoor_pos[0] + axis_dx
                ny = self._indoor_pos[1] + axis_dy
                for corner_x in (-BODY, BODY - 0.001):
                    for corner_y in (-BODY, BODY - 0.001):
                        if self._indoor_solid(nx + corner_x, ny + corner_y):
                            break
                    else:
                        continue
                    break
                else:
                    self._indoor_pos[0], self._indoor_pos[1] = nx, ny
            if dy:
                self.facing = "down" if dy > 0 else "up"
            elif dx:
                self.facing = "right" if dx > 0 else "left"
            self._walk_clock += dt

        if keys.just_pressed(Action.SHOULDER_L) or keys.just_pressed(Action.CONFIRM):
            neighbour = npcs_api.nearest(self.indoor_people, *self._indoor_pos, within=T.TILE * 2.2)
            if neighbour is not None:
                self._talk_to(neighbour)
                return

        if keys.just_pressed(Action.CANCEL):
            self.menu_open = True
            self.menu_row = 0

        col = int(self._indoor_pos[0] // T.TILE)
        row = int(self._indoor_pos[1] // T.TILE)
        if self.interior.tile_at(col, row) == T.EXIT:
            self._leave_interior()

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
        label = ranked[index]
        if warden.key == "prism":
            azure_labels = [l for l in self.pool if 460.0 <= l.emission_nm <= 510.0]
            if azure_labels:
                label = azure_labels[0]
        elif warden.key == "shutter":
            umbral_labels = [l for l in self.pool if l.emission_nm >= 640.0]
            if umbral_labels:
                label = umbral_labels[0]
        return bestiary_api.Beast(species=species, label=label)

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
            warden_key=key,
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
        click_row = self._title_click_row(keys, rows)
        if click_row is not None:
            self.title_index = click_row
            self._title_confirm()
            return
        if keys.just_pressed(Action.DOWN):
            self.title_index = (self.title_index + 1) % len(rows)
            self.title_confirm_new = False
        if keys.just_pressed(Action.UP):
            self.title_index = (self.title_index - 1) % len(rows)
            self.title_confirm_new = False
        if keys.just_pressed(Action.CANCEL):
            self.title_confirm_new = False
        if keys.just_pressed(Action.CONFIRM):
            self._title_confirm()

    def _title_click_row(self, keys, rows: list[str]) -> int | None:
        """Which title-menu row a click this frame landed on, if any.

        Same hit-zone-next-to-its-draw-math discipline as
        :meth:`_menu_click_target`, against the layout :meth:`_draw_curtain`'s
        ``"title"`` branch draws.

        Parameters
        ----------
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        rows : list of str
            The current title rows, so the hit-test never disagrees with
            what was actually drawn this frame.

        Returns
        -------
        int or None
            A row index, or ``None``.
        """
        point = self._click_world(keys)
        if point is None:
            return None
        wx, wy = point
        camera = self.host.camera
        cx, cy = float(camera.center[0]), float(camera.center[1])
        scale = camera.height / VIEW_HEIGHT
        pitch = 16.0
        wide = max(self._text_width(None, row, 12.0) for row in rows) + 64.0
        for index in range(len(rows)):
            y = cy + index * pitch * scale
            if (abs(wy - y) < pitch * 0.5 * scale
                    and cx - wide * 0.5 * scale <= wx <= cx + wide * 0.5 * scale):
                return index
        return None

    def _title_confirm(self) -> None:
        """Act on the selected title row."""
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
    TABS = ("STATUS", "MAP", "RIG", "PARTY", "LAB", "CRAFT", "PERKS", "MODE", "OPTIONS", "GAMELOGIC")

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

        target = self._menu_click_target(keys)
        if target is not None:
            kind, index = target
            if kind == "tab":
                self.menu_tab = index
                self.menu_row = 0
            else:
                self.menu_row = index
                self._menu_confirm()
            return

        tab = self.TABS[self.menu_tab]
        if keys.just_pressed(Action.SHOULDER_R):
            self.menu_tab = (self.menu_tab + 1) % len(self.TABS)
            self.menu_row = 0
            return
        if keys.just_pressed(Action.SHOULDER_L):
            self.menu_tab = (self.menu_tab - 1) % len(self.TABS)
            self.menu_row = 0
            return

        if keys.just_pressed(Action.RIGHT):
            if tab in ("OPTIONS", "GAMELOGIC"):
                if tab == "OPTIONS":
                    self._options_confirm(direction=1)
                else:
                    self._gamelogic_confirm(direction=1)
            else:
                self.menu_tab = (self.menu_tab + 1) % len(self.TABS)
                self.menu_row = 0
            return
        if keys.just_pressed(Action.LEFT):
            if tab in ("OPTIONS", "GAMELOGIC"):
                if tab == "OPTIONS":
                    self._options_confirm(direction=-1)
                else:
                    self._gamelogic_confirm(direction=-1)
            else:
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

    def _click_world(self, keys) -> tuple[float, float] | None:
        """A click this frame, converted from canvas pixels to world units.

        A mouse is not a gamepad input (see ``InputMap.click``), so this is
        the one, deliberately narrow place that bridges it into anything
        position-based -- every other input stays action-based.

        Parameters
        ----------
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.

        Returns
        -------
        tuple of float or None
            World-space point, or ``None`` on a frame with no click.
        """
        click = keys.click()
        if click is None:
            return None
        camera = self.host.camera
        width_px, height_px = self.host.ctx.size
        half = camera.half_extent(width_px / max(height_px, 1))
        # Qt's own mouse-event coordinates are logical points, not the
        # physical pixels ctx.size reports -- on any HiDPI display (2x on
        # most Macs) that mismatch halved the fraction every click landed
        # at, so a click on a menu row resolved to a world point nowhere
        # near the row and nothing ever seemed to respond. The canvas' own
        # logical size is what the click is actually measured against; the
        # offscreen canvas used in tests has a 1:1 ratio, so this is a no-op
        # there.
        canvas = getattr(self.host.ctx, "canvas", None)
        get_logical = getattr(canvas, "get_logical_size", None)
        width_pt, height_pt = get_logical() if get_logical is not None else (width_px, height_px)
        x = float(camera.center[0]) - half[0] + click[0] / max(width_pt, 1) * half[0] * 2.0
        y = float(camera.center[1]) - half[1] + click[1] / max(height_pt, 1) * half[1] * 2.0
        return x, y

    def _menu_click_target(self, keys) -> tuple[str, int] | None:
        """Which tab or row a click this frame landed on, if any.

        Hit-zones are computed with exactly the layout math :meth:`_draw_menu`
        draws from, kept next to each other for that reason -- two formulas
        for the same boxes is how a click stops landing where the text is.

        Parameters
        ----------
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.

        Returns
        -------
        tuple of (str, int) or None
            ``("tab", index)`` or ``("row", index)``, or ``None``.
        """
        point = self._click_world(keys)
        if point is None:
            return None
        wx, wy = point
        camera = self.host.camera
        width_px, height_px = self.host.ctx.size
        half = camera.half_extent(width_px / max(height_px, 1))
        cx, cy = float(camera.center[0]), float(camera.center[1])
        scale = camera.height / VIEW_HEIGHT

        span = half[0] * 1.5
        tab_y = cy - half[1] * 0.62
        if abs(wy - tab_y) < 8.0 * scale:
            for index in range(len(self.TABS)):
                x0 = cx - span * 0.5 + index * span / len(self.TABS)
                if x0 <= wx < x0 + span / len(self.TABS):
                    return "tab", index

        tab = self.TABS[self.menu_tab]
        top = cy - half[1] * 0.44
        start = top + (92.0 if tab == "RIG" else 0.0) * scale
        rows = self._menu_rows()
        base = max(0, self.menu_row - 6)
        window = rows[base:base + 8]
        for offset in range(len(window)):
            y = start + offset * 13.0 * scale
            if abs(wy - y) < 6.5 * scale and cx - half[0] * 0.7 <= wx <= cx + half[0] * 0.9:
                return "row", base + offset
        return None

    def _options_confirm(self, direction: int = 0) -> None:
        """Act on the selected option."""
        row = self.menu_row
        if row == 0:
            names = list(SCHEMES)
            step_dir = direction if direction != 0 else 1
            self.scheme = names[(names.index(self.scheme) + step_dir) % len(names)]
            self.host.keys.bindings = dict(SCHEMES[self.scheme])
        elif row == 1:
            self.screen_mode = not self.screen_mode
        elif row == 2:
            step_val = direction * 20.0 if direction != 0 else 35.0
            val = self.walk_speed + step_val
            if val > 260.0:
                val = 120.0
            self.walk_speed = max(120.0, min(260.0, val))
        elif row == 3:
            step_val = direction * 45.0 if direction != 0 else 90.0
            val = self.view_height + step_val
            if val > 600.0:
                val = VIEW_MIN
            self.view_height = max(300.0, min(600.0, val))
        elif row == 4:
            step_val = direction * 0.1 if direction != 0 else 0.1
            val = round(self.music_volume + step_val, 2)
            if val > 1.0:
                val = 0.0
            self.music_volume = max(0.0, min(1.0, val))
            self.host.audio.set_music_volume(self.music_volume)
        elif row == 5:
            step_val = direction * 0.1 if direction != 0 else 0.1
            val = round(self.sfx_volume + step_val, 2)
            if val > 1.0:
                val = 0.0
            self.sfx_volume = max(0.0, min(1.0, val))
            self.host.audio.set_sfx_volume(self.sfx_volume)
            self._sound("confirm", frequency=600.0)
        elif row == 6:
            info = providers_api.llm_status()
            msg = f"LLM: {info['summary_short']}"
            self.sparks.rise(msg, tuple(self.iris), color=info["color"], height=9.0)
            self._sound("confirm" if info["wired"] else "cancel", 600.0 if info["wired"] else 240.0)
        elif row == 7:
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
        elif row == 8:
            self.menu_open = False
            self.prologue_index = 0
            self.phase = "prologue"

    def _gamelogic_confirm(self, direction: int = 0) -> None:
        """Act on the selected gamelogic option."""
        row = self.menu_row
        if row == 0:
            themes = list(self.SOUNDTRACKS)
            step_dir = direction if direction != 0 else 1
            curr = getattr(self, "soundtrack_theme", themes[0])
            idx = (themes.index(curr) if curr in themes else 0) + step_dir
            self.soundtrack_theme = themes[idx % len(themes)]
        elif row == 1:
            step_val = direction * 0.5 if direction != 0 else 1.0
            val = getattr(self, "enemy_aggro_radius", 4.5) + step_val
            if val > 8.0:
                val = 2.0
            self.enemy_aggro_radius = round(max(2.0, min(8.0, val)), 1)
        elif row == 2:
            self.action_combat_enabled = not getattr(self, "action_combat_enabled", True)
        elif row == 3:
            self.particle_fx_enabled = not getattr(self, "particle_fx_enabled", True)
        elif row == 4:
            self.crt_filter_enabled = not getattr(self, "crt_filter_enabled", False)
        elif row == 5:
            tones = ["Gold", "Cyan", "Emerald", "Ruby", "Violet"]
            step_dir = direction if direction != 0 else 1
            curr = getattr(self, "ui_accent_tone", "Gold")
            idx = (tones.index(curr) if curr in tones else 0) + step_dir
            self.ui_accent_tone = tones[idx % len(tones)]
        elif row == 6:
            self.save_run()
            self.sparks.rise("Run Saved!", tuple(self.iris), color=(0.35, 0.90, 0.45, 1.0), height=9.0)
            self._sound("confirm", frequency=750.0)
        elif row == 7:
            self._boot()
            self.sparks.rise("Run Loaded!", tuple(self.iris), color=(0.40, 0.82, 0.95, 1.0), height=9.0)
            self._sound("confirm", frequency=650.0)
        elif row == 8:
            self._sound("confirm", frequency=880.0)
            self.sparks.burst(tuple(self.iris), count=8, kind="sparkle", color=(0.96, 0.88, 0.50, 1.0))

    def _menu_rows(self) -> list[str]:
        """The lines the current tab offers.

        Returns
        -------
        list of str
            Selectable rows; empty for a tab that only displays.
        """
        tab = self.TABS[self.menu_tab]
        if tab == "STATUS":
            # Everything that used to sit permanently on screen, now read on
            # request instead of blocking the world it describes.
            counts = self.world.counts()
            total = max(len(self.world.rooms), 1)
            licence = tiers_api.licence(self.story.seals)
            xp_in, xp_needed = self.game_state.level_progress
            level_row = f"level {self.game_state.level} {self.game_state.level_title}"
            if xp_needed:
                level_row += f"   {xp_in}/{xp_needed} xp"
            rows = [
                level_row,
                f"perks: {len(perks_api.unlocked_perks(self.game_state.level))}/{len(perks_api.PERKS)} active",
                self._warden_compass(),
                f"settled {counts[SETTLED]}/{total}   scouted {counts[SCOUTED]}",
                f"wild {counts[WILD]}" + (f"   withered {counts[WITHERED]}"
                                          if counts[WITHERED] else ""),
                self.loadout.summary,
                f"{len(self.labels)} labels   {len(self.bodies)} bodies",
                f"seal {len(self.story.seals)}/5   licence {tiers_api.TIER_NAMES[licence]}",
                f"mode: {self.mode}",
            ]
            if self.dark:
                rows.append("in the dark manifold")
            if self.resting:
                rows.append("recovering")
            return rows
        if tab == "MAP":
            # Confirm on this tab closes the menu and swaps the camera to
            # the whole-world view instead of listing rows here -- a blank
            # panel while just browsing past it on the way to another tab
            # read as the map being broken, so it says what pressing
            # Confirm actually does instead of showing nothing.
            total = len(self.world.regions)
            return [
                f"{len(self.explored)}/{total} lands explored",
                "Confirm to view the map",
            ]
        if tab == "RIG":
            # The overworld weapon and spell were only ever cycled through
            # dead code -- no button on the nine-action pad was free for a
            # dedicated key, so they are menu rows instead, the same way
            # every other loadout choice already works.
            rows = [
                f"weapon: {WEAPON_DATA[self.active_weapon]['name']}",
                f"magic: {MAGIC_DATA[self.active_magic]['name']}",
            ]
            rows.extend(part.summary for part in self.inventory)
            if not self.inventory:
                rows.append("nothing found yet")
            return rows
        if tab == "PARTY":
            # The build screen: bodies and labels are separate lists, and a
            # team member is one of each. Picking a slot then picking a body or
            # a label is the whole interaction.
            rows = [
                f"{'>' if index == self.party_slot else ' '} {f.name}"
                f"  {f.hp}/{f.beast.max_hp} HP  spd:{f.beast.speed:.1f}  T{f.beast.tier}"
                for index, f in enumerate(self.team)
            ]
            rows.append("-- bodies (befriended animals) --")
            rows.extend(f"   {body.name}  vit:{body.vitality:.1f} agi:{body.agility:.1f}  ({_trait_name(body.trait)})"
                        for body in self.bodies)
            rows.append("-- labels (fluorophores) --")
            rows.extend(f"   {label.name}  {label.emission_nm:.0f} nm  qy:{label.quantum_yield:.2f}"
                        for label in self.labels)
            if self.workshop.crafted:
                rows.append("-- bench reagents --")
                rows.extend(f"   {crafting_api.RECIPES[key].name}"
                            for key in self.workshop.crafted
                            if key in crafting_api.RECIPES)
            return rows
        if tab == "OPTIONS":
            info = providers_api.llm_status()
            return [
                f"controls: {self.scheme}",
                f"camera: {'scrolling' if not self.screen_mode else 'screen by screen'}",
                f"walk speed: {self.walk_speed:.0f}",
                f"default zoom: {self.view_height:.0f}",
                f"music volume: {self.music_volume:.0%}",
                f"sound volume: {self.sfx_volume:.0%}",
                f"llm provider: [{info['indicator']}] {info['summary_short']}",
                "regenerate the wilderness",
                "watch the opening again",
            ]
        if tab == "GAMELOGIC":
            return [
                f"soundtrack: {getattr(self, 'soundtrack_theme', 'Ninja Adventure (CC0)')}",
                f"enemy aggro: {getattr(self, 'enemy_aggro_radius', 4.5):.1f} tiles",
                f"action combat: {'[✓] enabled' if getattr(self, 'action_combat_enabled', True) else '[ ] disabled'}",
                f"particle effects: {'[✓] enabled' if getattr(self, 'particle_fx_enabled', True) else '[ ] disabled'}",
                f"crt retro shader: {'[✓] enabled' if getattr(self, 'crt_filter_enabled', False) else '[ ] disabled'}",
                f"ui accent tone: {getattr(self, 'ui_accent_tone', 'Gold')}",
                "quick save run",
                "quick load run",
                "test audio sfx",
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
                rows.extend(f"culture {label.name} ({label.emission_nm:.0f} nm)" for label in self.labels)
            return rows or ["unbind a label, then culture it here"]
        if tab == "CRAFT":
            # A shelf, then a bench: what is gathered, then what it can
            # become. A recipe short of its reagents is still shown -- a
            # crafting list that hides what you cannot yet make teaches
            # nothing about what to go find.
            rows = [
                f"{material.name}: {self.workshop.materials.get(key, 0)}  ({material.found})"
                for key, material in crafting_api.MATERIALS.items()
            ]
            rows.append("-- bench --")
            for key, recipe in crafting_api.RECIPES.items():
                need = ", ".join(
                    f"{crafting_api.MATERIALS[mat].name} x{count}"
                    for mat, count in recipe.inputs
                )
                mark = "" if self.workshop.can_craft(key) else "  (short)"
                rows.append(f"{recipe.name}: {need}{mark}")
            return rows
        if tab == "PERKS":
            level = self.game_state.level
            rows = []
            for perk in perks_api.PERKS:
                if level >= perk.level_req:
                    rows.append(f"[✓] {perk.name}: {perk.text}")
                else:
                    rows.append(f"[🔒 Req: Lvl {perk.level_req}] {perk.name}: {perk.text}")
            return rows
        if tab == "MODE":
            info = providers_api.llm_status()
            return [
                review_bridge.TRAINING,
                review_bridge.EXPERT,
                f"model voices & questions: {'on' if self.use_model else 'off'}",
                f"llm status: [{info['indicator']}] {info['summary_short']}",
            ]
        return []

    def _menu_confirm(self) -> None:
        """Act on the selected row."""
        tab = self.TABS[self.menu_tab]
        if tab == "MAP":
            self.show_map = not self.show_map
            self.menu_open = False
        elif tab == "OPTIONS":
            self._options_confirm()
        elif tab == "GAMELOGIC":
            self._gamelogic_confirm()
        elif tab == "MODE":
            if self.menu_row < 2:
                self.mode = (review_bridge.TRAINING, review_bridge.EXPERT)[self.menu_row]
            elif self.menu_row == 2:
                self.use_model = not self.use_model
            elif self.menu_row == 3:
                info = providers_api.llm_status()
                msg = f"LLM: {info['summary_short']}"
                self.sparks.rise(msg, tuple(self.iris), color=info["color"], height=9.0)
                self._sound("confirm" if info["wired"] else "cancel", 600.0 if info["wired"] else 240.0)
        elif tab == "RIG":
            if self.menu_row == 0:
                self._cycle_weapon()
            elif self.menu_row == 1:
                self._cycle_magic()
            elif self.inventory:
                part = self.inventory[min(self.menu_row - 2, len(self.inventory) - 1)]
                # Fitting into the rig and fitting the single filter are the
                # same act from the player's side, so both happen.
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
        elif tab == "CRAFT":
            self._craft_confirm()
        elif tab == "PERKS":
            level = self.game_state.level
            if 0 <= self.menu_row < len(perks_api.PERKS):
                perk = perks_api.PERKS[self.menu_row]
                if level >= perk.level_req:
                    self.sparks.rise(f"Active Perk: {perk.name}", tuple(self.iris),
                                     color=(0.4, 0.95, 0.8, 1.0), height=9.0)
                    self._sound("confirm", frequency=640.0)
                else:
                    self.sparks.rise(f"Locked until Level {perk.level_req}", tuple(self.iris),
                                     color=(0.95, 0.45, 0.45, 1.0), height=9.0)
                    self._sound("cancel", frequency=240.0)

    def _craft_confirm(self) -> None:
        """Craft the selected recipe, if the shelf can answer for it."""
        row = self.menu_row - len(crafting_api.MATERIALS) - 1  # past the shelf and its header
        keys = list(crafting_api.RECIPES)
        if not 0 <= row < len(keys):
            return
        recipe = crafting_api.RECIPES[keys[row]]
        if self.workshop.craft(keys[row]):
            self._sound("confirm", frequency=680.0)
            self.sparks.rise(f"Crafted {recipe.name}", tuple(self.iris),
                             color=(0.4, 0.9, 0.85, 1.0), height=8.0)
        else:
            self._sound("cancel", frequency=220.0)

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
        infusions_at = labels_at + len(self.labels) + 1
        slot = min(self.party_slot, len(self.team) - 1)
        current = self.team[slot]
        if bodies_at <= row < bodies_at + len(self.bodies):
            body = self.bodies.pop(row - bodies_at)
            self.bodies.append(current.beast.species)
            self.team[slot] = battle_api.Fighter(
                bestiary_api.Beast(species=body, label=current.beast.label,
                                   infusion=current.beast.infusion)
            )
        elif labels_at <= row < labels_at + len(self.labels):
            label = self.labels.pop(row - labels_at)
            if current.beast.label is not None:
                self.labels.append(current.beast.label)
            self.team[slot] = battle_api.Fighter(current.beast.fitted(label))
        elif (self.workshop.crafted
              and infusions_at <= row < infusions_at + len(self.workshop.crafted)):
            # Fixed in, not swapped: the bench reagent already fitted (if
            # any) is spent, the same way a fresh coat replaces an old one
            # rather than layering.
            trait_key = self.workshop.crafted.pop(row - infusions_at)
            self.team[slot] = battle_api.Fighter(current.beast.infused(trait_key), hp=current.hp)
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
        # Her own bars recover the same way and the same place.
        self.iris_hp = min(self.iris_max_hp, self.iris_hp + max(1, int(self.iris_max_hp * 0.6 * dt)))
        self.photons = min(self.photons_max, self.photons + max(1, int(self.photons_max * 0.4 * dt)))

    def _faint(self) -> None:
        """Iris' HP has run out in real-time combat or battle defeat.

        Not a game over -- a beast's HP running out is a defeat screen with
        stakes worth having, and duplicating that for the overworld's
        separate combat system is a bigger redesign than a bleached-out walk
        needs. She is walked back to the world's own spawn point with both
        bars half restored, the same shape as fainting costs a trip, not a
        run.
        """
        self.iris_hp = self.iris_max_hp // 2
        self.photons = min(self.photons_max, self.photons + self.photons_max // 4)
        for fighter in self.team:
            if fighter.hp <= 0:
                fighter.hp = max(1, fighter.beast.max_hp // 3)
        self.iris = list(self.world.spawn())
        self.host.camera.center[:] = self.iris
        self._sound("cancel", frequency=180.0)
        self.sparks.rise("Bleached out...", tuple(self.iris),
                         color=(1.0, 0.5, 0.5, 1.0), height=9.0)
        self._encounter_cooldown = 3.0
        self._iris_hit_flash = 2.0

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
        if getattr(self, "_encounter_cooldown", 0.0) > 0.0:
            return
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
        # Opens zoomed in; update() eases it back out and _draw_battle fades
        # a flash over the same window -- see BATTLE_ZOOM_START.
        self._battle_intro = ENCOUNTER_FLASH_SECONDS
        self.host.camera.height = self.view_height * BATTLE_ZOOM_START

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
                # _award_loot marks the room cleared, so whether this is its
                # first clear has to be read before calling it, not after.
                self._pending_first_clear = self.encounter_room.address not in self.cleared
                self._award_loot(self.encounter_room)
                self._begin_challenge(self.encounter_room)

            if self.flagging:
                self._flag_input(keys)
                return
            if self.challenge is not None:
                self._challenge_input(keys)
                return
            if keys.just_pressed(Action.CONFIRM) or keys.just_pressed(Action.CANCEL):
                self._say_what_you_carried_away(fight)
                was_won = fight.won
                was_fled = fight.fled
                self.battle = None
                self.battle_sparks.clear()
                self.encounter_room = None
                self.warden_fight = ""
                self.verdict = None
                self._encounter_cooldown = 3.0
                if not was_won and not was_fled:
                    self._faint()
                elif was_fled:
                    for npc in self.people:
                        if npc.kind == "beast" and npc.distance_to(*self.iris) < T.TILE * 1.5:
                            dx = npc.x - self.iris[0]
                            dy = npc.y - self.iris[1]
                            dist = math.hypot(dx, dy) or 1.0
                            npc.x += (dx / dist) * T.TILE * 2.5
                            npc.y += (dy / dist) * T.TILE * 2.5
                            npc.knockback_vx = (dx / dist) * 120.0
                            npc.knockback_vy = (dy / dist) * 120.0
                            npc.knockback_timer = 0.5
            return

        options = self._battle_options()
        if keys.just_pressed(Action.DOWN):
            self.menu_index = (self.menu_index + 1) % len(options)
        if keys.just_pressed(Action.UP):
            self.menu_index = (self.menu_index - 1) % len(options)
        if keys.just_pressed(Action.CONFIRM):
            label = options[self.menu_index][0]
            # Health per *fighter*, keyed by identity: a relay or a knock-out
            # can change which one is active inside a single press, and reading
            # `fight.active.hp` before and after then compares two different
            # animals and reports nothing.
            before = ({id(one): one.hp for one in [*fight.team, fight.opponent]},
                      fight.taken, fight.active.beast.emission_nm)
            options[self.menu_index][1]()
            self._sound("unbind" if label.startswith("Unbind") else "emit", 700.0)
            self._show_exchange(fight, before)
        elif keys.just_pressed(Action.CANCEL):
            fight.flee()

    def _say_what_you_carried_away(self, fight) -> None:
        """Repeat the spoils on the overworld, where the player is looking.

        The battle screen already said it, but it said it on a screen that is
        about to be torn down, and the two are different places. A label and an
        animal are the two things a run is made of, so both get a line.

        Parameters
        ----------
        fight : chisurf.plugins.misc.games.lumis_quest.api.battle.Battle
            The finished encounter.
        """
        at = (self.iris[0], self.iris[1] - T.TILE * 0.9)
        if fight.taken is not None:
            self.sparks.rise(f"+ {fight.taken.name}", at, span=1.8,
                             distance=20.0, height=8.5,
                             color=(0.72, 0.96, 0.84, 1.0))
            self.sparks.burst(tuple(self.iris), count=10, span=0.7, speed=32.0,
                              emission_nm=fight.taken.emission_nm)
            at = (at[0], at[1] - 11.0)
        if fight.joined and fight.freed is not None:
            self.sparks.rise(f"the {fight.freed.name} follows you", at,
                             span=2.2, distance=18.0, height=8.0,
                             color=(0.94, 0.88, 0.62, 1.0))

    def _show_exchange(self, fight, before) -> None:
        """Say what an exchange did, where it did it.

        A bar that moves is a bar that moved; a number over the thing that took
        the hit is the hit. Which side lost health is read from the hp deltas
        rather than from the log text, because the log is prose and an exchange
        can hurt both sides in one press.

        Parameters
        ----------
        fight : chisurf.plugins.misc.games.lumis_quest.api.battle.Battle
            The encounter, after the action.
        before : tuple
            ``({id(fighter): hp}, taken, emitted nm)`` from immediately before
            it -- the wavelength being the one *your* beast emits, which is
            what lands on the other one.
        """
        health, had, emitted = before
        if not {"enemy", "ours"} <= set(self._portraits):
            return  # nothing has been drawn yet, so there is nowhere to put it
        # The battle screen is laid out in multiples of its own scale, so
        # feedback has to be too -- fixed sizes were a glow three times the
        # portrait with a number too small to read inside it.
        scale = self._portrait_scale
        enemy, ours = self._portraits["enemy"], self._portraits["ours"]

        dealt = health.get(id(fight.opponent), fight.opponent.hp) - fight.opponent.hp
        if dealt > 0:
            self.battle_sparks.rise(f"-{int(dealt)}",
                                    (enemy[0], enemy[1] - 16.0 * scale),
                                    color=(1.00, 0.86, 0.42, 1.0),
                                    height=13.0 * scale, distance=14.0 * scale)
            # In the colour *your* beast emits, not the colour the target
            # does: an impact is light arriving. Drawn in the target's own
            # band it was invisible, because the target is already glowing
            # that colour -- which is the sort of thing only a picture says.
            self.battle_sparks.burst(enemy, count=10, size=3.2 * scale,
                                     speed=30.0 * scale, span=0.55, drag=1.6,
                                     radius=17.0 * scale, emission_nm=emitted)

        took = max((was - one.hp for one in fight.team
                    for was in [health.get(id(one), one.hp)]), default=0)
        if took > 0:
            self.battle_sparks.rise(f"-{int(took)}",
                                    (ours[0], ours[1] - 16.0 * scale),
                                    color=(0.96, 0.52, 0.48, 1.0),
                                    height=13.0 * scale, distance=14.0 * scale)

        if had is None and fight.taken is not None:
            # The moment the whole game is about: the label comes off, and it
            # visibly goes from the animal into you.
            self.battle_sparks.rise("unbound", (enemy[0], enemy[1] - 26.0 * scale),
                                    color=(0.62, 0.94, 0.78, 1.0), span=1.6,
                                    distance=18.0 * scale, height=11.0 * scale)
            self.battle_sparks.orbs(enemy, ours, count=9, size=1.5 * scale,
                                    speed=95.0 * scale, span=2.0,
                                    scatter=5.0 * scale,
                                    emission_nm=fight.taken.emission_nm)

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
            # Levelling answers to a page actually signed off -- training
            # mode and a wrong answer never reach here, so XP tracks real
            # review work rather than combat grinding.
            level_before = self.game_state.level
            reward = self.game_state.record_review(
                difficulty=self._difficulty_for(room),
                is_first_ever=self._pending_first_clear,
            )
            self._celebrate_reward(reward, level_before)
        self.challenge = None

    def _difficulty_for(self, room) -> str:
        """A review's difficulty, read off how overdue the page was.

        Parameters
        ----------
        room : Room
            The room just cleared.

        Returns
        -------
        str
            A key of :data:`chisurf.plugins.misc.games.lumis_quest.api.game_state.DIFFICULTY_MULTIPLIER`.
        """
        remoteness = room.remoteness
        if remoteness >= 0.9:
            return "expert"
        if remoteness >= 0.7:
            return "hard"
        if remoteness >= 0.4:
            return "medium"
        return "easy"

    def _celebrate_reward(self, reward: dict, level_before: int) -> None:
        """Show what a signed-off review just paid out.

        Parameters
        ----------
        reward : dict
            Whatever :meth:`~.game_state.GameState.record_review` returned.
        level_before : int
            The level going in, so a level-up gets its own line rather than
            reading as an ordinary XP tick.
        """
        at = (self.iris[0], self.iris[1] - 20.0)
        self._sound("seal", 760.0)
        self.sparks.burst(tuple(self.iris), count=10, kind="photon", speed=60.0)
        self.sparks.rise(f"+{reward['xp']} XP -- {reward['label']}", at,
                         color=(1.0, 0.90, 0.45, 1.0), height=9.0)
        if reward["level"] > level_before:
            self.sparks.rise(f"Level {reward['level']}: {reward['level_title']}!",
                             (self.iris[0], self.iris[1] - 32.0),
                             color=(0.55, 0.95, 1.0, 1.0), height=11.0)
            self._sound("cross", 900.0)
        if reward["streak"] > 1:
            self.sparks.rise(f"{reward['streak']}-day streak",
                             (self.iris[0], self.iris[1] - 44.0),
                             color=(0.95, 0.75, 0.45, 1.0), height=8.0)

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

    #: Eight-way compass, index by the octant a bearing falls in (0 = east,
    #: counterclockwise -- math convention, since that is what atan2 gives).
    _COMPASS = ("east", "northeast", "north", "northwest",
               "west", "southwest", "south", "southeast")

    def _warden_compass(self) -> str:
        """Which way the next unbeaten Warden lies.

        The seal ladder used to be findable only by wandering until a
        gold-tinted NPC turned up. ``tiers_api.next_warden`` already knew
        which one was next; nothing ever asked it where they stood.

        Returns
        -------
        str
            A STATUS row naming the Warden, their land, and a bearing --
            or that the ladder is already climbed.
        """
        warden = tiers_api.next_warden(self.story.seals)
        if warden is None:
            return "every Warden's seal is held"
        village = next((v for v in self.world.villages if v.warden == warden.key), None)
        if village is None:
            return f"next: {warden.name}, seat unknown"
        col, row, width, height = village.rect
        vx, vy = (col + width * 0.5) * T.TILE, (row + height * 0.5) * T.TILE
        region = self.world.region_at(vx, vy)
        land = region.title if region is not None else village.place
        bearing = math.atan2(-(vy - self.iris[1]), vx - self.iris[0])
        octant = int(round(bearing / (math.pi / 4.0))) % 8
        return f"next: {warden.name}, {self._COMPASS[octant]} in {land}"

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

    def _airborne(self, dt: float) -> None:
        """Advance the jump, and land when the ground comes back.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        """
        if not self.jumping and self.z <= 0.0:
            return
        self.fall += GRAVITY * dt
        self.z -= self.fall * dt
        if self.z <= 0.0:
            self.z = 0.0
            self.fall = 0.0
            self.jumping = False
            self._sound("step", 300.0)
            # Landing on something solid is the one way a jump could leave her
            # inside geometry, so the ground is checked the moment she reaches
            # it rather than on the next frame.
            self._unstick()

    @property
    def hopping(self) -> bool:
        """Whether she is high enough to clear the low obstacles.

        Returns
        -------
        bool
            True in the middle of a jump.
        """
        return self.z > HOP_HEIGHT

    def _walk(self, dx: float, dy: float) -> None:
        """Move Iris, sliding along anything solid and slipping past corners.

        Three things this has to get right, and the version before it got none
        of them:

        * **Never move more than a fraction of a tile at once.** The frame step
          is capped at 0.1 s and a sprint is nearly 500 units a second, so one
          hitched frame moved her *two and a half tiles* -- straight through a
          wall, after which she was inside geometry and every subsequent move
          was refused. That is what "stuck on objects" was.
        * **Resolve the axes separately**, so walking into a wall at an angle
          slides along it rather than stopping dead.
        * **Slip past corners.** Catching the lip of a doorway and stopping
          when you are a pixel off the opening is the most irritating thing a
          tile game does. A blocked move is retried nudged to each side before
          it is given up on.

        Parameters
        ----------
        dx, dy : float
            Intended movement in world units.
        """
        steps = max(1, int(math.hypot(dx, dy) / (BODY * 0.6)) + 1)
        step_x, step_y = dx / steps, dy / steps
        for _ in range(steps):
            self._step(step_x, step_y)

    def _step(self, dx: float, dy: float) -> None:
        """Move by one sub-step, resolving each axis and slipping corners.

        Parameters
        ----------
        dx, dy : float
            Movement for this sub-step.
        """
        if dx and not self._slide(dx, 0.0):
            for nudge in (CORNER_SLIP, -CORNER_SLIP):
                if not self._solid(self.iris[0] + dx, self.iris[1] + nudge):
                    self.iris[0] += dx
                    self.iris[1] += nudge
                    break
        if dy and not self._slide(0.0, dy):
            for nudge in (CORNER_SLIP, -CORNER_SLIP):
                if not self._solid(self.iris[0] + nudge, self.iris[1] + dy):
                    self.iris[0] += nudge
                    self.iris[1] += dy
                    break

    def _slide(self, dx: float, dy: float) -> bool:
        """Take a move if the destination is clear.

        Parameters
        ----------
        dx, dy : float
            Movement.

        Returns
        -------
        bool
            Whether it was taken.
        """
        if self._solid(self.iris[0] + dx, self.iris[1] + dy):
            return False
        self.iris[0] += dx
        self.iris[1] += dy
        return True

    def _solid(self, x: float, y: float) -> bool:
        """Whether Iris' body would overlap something solid.

        The body is a **box**, and every tile the box touches is tested. The
        version before this sampled four points on a cross, which never looked
        at the body's own corners -- so she could clip diagonally into the
        corner of a building, end up overlapping it, and then be refused every
        move back out.

        Parameters
        ----------
        x, y : float
            Candidate centre in world units.

        Returns
        -------
        bool
            True when the move must be refused.
        """
        # Sampled at the box's four corners, and each against the *quarter* of
        # its tile that corner is in -- so a lantern post blocks the half of
        # its tile it stands on and you can walk past it, which is most of what
        # "getting stuck on objects" was.
        for offset_x in (-BODY, BODY - 0.001):
            for offset_y in (-BODY, BODY - 0.001):
                point_x, point_y = x + offset_x, y + offset_y
                col, row = int(point_x // T.TILE), int(point_y // T.TILE)
                # Buildings do not stand in the dark manifold (_draw_rooms is
                # skipped there), so the extra width their sprites cover in
                # the lit world means nothing there either.
                if not self.dark and (col, row) in self._building_solid:
                    return True
                tile = self.world.tile_at(col, row, self.dark)
                if self.hopping and tile in HOPPABLE:
                    continue
                if T.solidity(tile) & T.quadrant(point_x, point_y):
                    return True
        return False

    def _solid_at_tile(self, tile: int) -> bool:
        """Whether a tile of this kind would stop her right now.

        Exists so the jump's hop rule can be asserted without needing a world
        that happens to have a fence in the right place.

        Parameters
        ----------
        tile : int
            A tile kind.

        Returns
        -------
        bool
            True when it blocks, given her current height.
        """
        if self.hopping and tile in HOPPABLE:
            return False
        return bool(T.solidity(tile) & T.TOP_LEFT)

    def _unstick(self) -> bool:
        """Get Iris out of anything she has ended up inside.

        Nothing should put her inside a wall any more, but a save from an older
        build, a corpus that changed under a stored position, or crossing into
        the dark manifold onto ground that is solid *there* all can. Freezing
        the player is the worst possible answer: the game looks broken and
        there is no way out but a restart.

        Returns
        -------
        bool
            Whether she had to be moved.
        """
        if not self._solid(*self.iris):
            return False
        col = int(self.iris[0] // T.TILE)
        row = int(self.iris[1] // T.TILE)
        for radius in range(1, 24):
            for drow in range(-radius, radius + 1):
                for dcol in range(-radius, radius + 1):
                    if max(abs(drow), abs(dcol)) != radius:
                        continue
                    x = (col + dcol + 0.5) * T.TILE
                    y = (row + drow + 0.5) * T.TILE
                    if not self._solid(x, y):
                        self.iris[0], self.iris[1] = x, y
                        return True
        return False

    def _screen_view(self, dt: float) -> tuple[tuple[float, float], float]:
        """Camera centre and height for the screen Iris is standing on.

        Crossing an edge is a *flip*: the destination screen is chosen at once
        -- so the geometry and the collision never disagree with what is drawn
        -- and the camera slides to it over a fraction of a second.

        Parameters
        ----------
        dt : float
            Seconds elapsed.

        Returns
        -------
        tuple
            ``((x, y), height)``.
        """
        here = screens_api.screen_of(*self.iris)
        if here != self.screen_at:
            self.flip_from = screens_api.centre_of(*self.screen_at)
            self.flip_left = screens_api.FLIP_SECONDS
            self.screen_at = here
        target = screens_api.centre_of(*self.screen_at)

        if self.flip_left > 0.0 and self.flip_from is not None:
            self.flip_left = max(0.0, self.flip_left - dt)
            through = 1.0 - self.flip_left / screens_api.FLIP_SECONDS
            # Smoothstep, so the slide starts and stops rather than jerking.
            eased = through * through * (3.0 - 2.0 * through)
            target = (
                self.flip_from[0] + (target[0] - self.flip_from[0]) * eased,
                self.flip_from[1] + (target[1] - self.flip_from[1]) * eased,
            )
        return (target, screens_api.HEIGHT)

    @property
    def screen_name(self) -> str:
        """Where she is, as a paper map would say it.

        Returns
        -------
        str
            e.g. ``H7``.
        """
        return screens_api.label(*self.screen_at)

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

        if self.phase == "title":
            # The world itself as the backdrop, at wherever the run spawns --
            # real 16-bit ground, buildings and trees rather than a flat panel
            # with a name on it. _draw_curtain washes it down and puts the
            # menu over the top.
            self._draw_tiles(scene, camera, half, as_map=False)
            self._draw_structures(scene, camera, half)
            self._draw_trees(scene, camera, half)
            # _draw_tiles excludes BUILDING cells, expecting _draw_rooms to
            # cover them with the room's actual sprite -- skipping it here
            # left every house a plain black hole.
            self._draw_rooms(scene, camera, half)
            self._draw_curtain(scene, camera, half)
            return
        if self.phase in ("prologue", "epilogue"):
            # Same backdrop as the title: the world she is about to wake into
            # (or has just saved), not a black hole with words over it. The
            # world is already built and the camera already parked on the
            # spawn point by the time either phase is reachable.
            self._draw_tiles(scene, camera, half, as_map=False)
            self._draw_structures(scene, camera, half)
            self._draw_trees(scene, camera, half)
            self._draw_rooms(scene, camera, half)
            self._draw_curtain(scene, camera, half)
            return
        if self.phase == "loading":
            self._draw_curtain(scene, camera, half)
            return

        if self.interior is not None:
            self._draw_interior(scene, camera, half)
            return

        as_map = camera.height > MAP_THRESHOLD
        self._draw_tiles(scene, camera, half, as_map)
        if not as_map:
            self._draw_structures(scene, camera, half)
            self._draw_trees(scene, camera, half)
        if not self.dark:
            self._draw_rooms(scene, camera, half, as_map=as_map)

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

        # Where the dark manifold is entered -- shown up close the moment
        # Iris is standing in front of one, unlike a village's name, because
        # the whole point is finding it before knowing it is there. At map
        # zoom it is fogged like everything else until its land is explored.
        map_scale = camera.height / VIEW_HEIGHT
        for cave_col, cave_row in self.world.caves:
            cave_x, cave_y = (cave_col + 0.5) * T.TILE, (cave_row + 0.5) * T.TILE
            if abs(cave_x - camera.center[0]) > half[0] or abs(cave_y - camera.center[1]) > half[1]:
                continue
            if as_map:
                # Fog of war applies to the overview the same way it does to
                # the ground itself: a dungeon only marks itself on the map
                # while Iris is standing in the land around it -- it returns
                # to hiding the moment she leaves.
                cave_region = self.world.region_at(cave_x, cave_y)
                if cave_region is None or cave_region is not self.land:
                    continue
            # A halo the size of a tile is a fixed *world* size, so at the
            # world-spanning zoom the map screen uses it would shrink to a
            # few pixels -- sized in screen space instead, the way the HUD is.
            scene.draw("photon", "halo", at=(cave_x, cave_y),
                       size=(T.TILE * (2.6 * map_scale if as_map else 0.9),) * 2,
                       emission_nm=410.0)
            if not as_map:
                scene.text(
                    "cave -- crosses into the dark manifold",
                    at=(cave_x, cave_y - T.TILE * 1.3),
                    height=8.0, align="center", color=(0.78, 0.58, 0.94, 1.0),
                )

        # Everyone who lives here, drawn before Iris so she walks in front of
        # them. Culled to the view: the world holds well over a hundred.
        frame_index = int(self._clock * 3.0) % 2
        for npc in self.people:
            if abs(npc.x - camera.center[0]) > half[0] + T.TILE:
                continue
            if abs(npc.y - camera.center[1]) > half[1] + T.TILE:
                continue
            if as_map:
                # Fog of war again -- a dot for every villager and beast in
                # the world was the map giving away far more than the ground
                # it stood on did.
                npc_region = self.world.region_at(npc.x, npc.y)
                if npc_region is None or npc_region is not self.land:
                    continue
            tint = (1.0, 1.0, 1.0, 1.0)
            sprite = f"{npc.kind}_{frame_index}"
            # A hovering thing is *drawn* above its own feet and collides at
            # them, which is a second height that never reaches the physics --
            # see the fake z in :mod:`~..api.steering`. The shadow stays on the
            # ground and shrinks, because a shadow that rises with the sprite
            # is how a hover ends up reading as a creature standing further
            # north.
            lift = npc.lift
            drawn = (npc.x, npc.y - lift)
            if npc.startled:
                # It has just seen you. Which way that goes is the animal's
                # business -- most of them are about to run -- but the noticing
                # itself has to be legible, or a creature that has not seen you
                # and one that is stalking you look exactly the same.
                npc.startled = False
                self.sparks.rise("!", (npc.x, npc.y - T.TILE * 0.8),
                                 color=(1.00, 0.90, 0.55, 1.0), span=0.85,
                                 distance=6.0, height=9.0)
            if npc.species:
                # An animal is drawn as the animal it is, in the colour of
                # whatever is fixed into it. A marked hare and an unmarked one
                # are the same drawing and read completely differently, which
                # is the point of the whole bestiary.
                sprite = pixelart.creature_sprite(npc.species)
                if npc.kind == "beast":
                    nm = self._marked_nm(npc)
                    scene.draw("photon", "halo", at=drawn,
                               size=(T.TILE * 0.8, T.TILE * 0.8), emission_nm=nm)
                    tint = _emission_tint(nm)
                elif npc.kind == "wraith":
                    tint = (0.30, 0.26, 0.36, 1.0)
            elif npc.kind == "beast":
                variants = ["ninja_beast", "samurai_beast", "spirit_beast", "squid_beast", "beast"]
                # Never hash() here: a str hash is salted per process, so the
                # same beast would change species between sessions.
                beast_key = variants[zlib.crc32(npc.name.encode()) % len(variants)]
                sprite = f"{beast_key}_{frame_index}"
                scene.draw("photon", "halo", at=drawn,
                           size=(T.TILE * 0.9, T.TILE * 0.9), emission_nm=405.0)
            elif npc.kind == "lanternwright":
                # The only thing burning in the dark manifold, and it is her.
                scene.draw("photon", "vesper", at=drawn,
                           size=(T.TILE * 1.8, T.TILE * 1.8), emission_nm=690.0)
                tint = (1.00, 0.72, 0.86, 1.0)
            elif npc.kind == "warden":
                scene.draw("photon", "halo", at=drawn,
                           size=(T.TILE * 1.2, T.TILE * 1.2), emission_nm=600.0)
                tint = (1.00, 0.92, 0.74, 1.0)
            elif npc.kind == "emissary":
                doctrine = npc.role.split(":", 1)[-1]
                scene.draw("photon", "halo", at=drawn,
                           size=(T.TILE * 1.1, T.TILE * 1.1),
                           emission_nm=EMISSARY_NM.get(doctrine, 488.0))
                tint = EMISSARY_TINT.get(doctrine, tint)
            elif npc.kind == "lumi":
                # The dim hound: an ember of the glow it will have at heel.
                scene.draw("photon", "halo", at=drawn,
                           size=(T.TILE * 0.5, T.TILE * 0.5),
                           emission_nm=LUMI.wavelength_nm)
                tint = (0.55, 0.62, 0.55, 1.0)
            self._sprite(scene, "shadow", (npc.x, npc.y + 2.0),
                         T.TILE * (1.0 - min(lift / 12.0, 0.35)))
            self._sprite(scene, sprite, drawn, T.TILE,
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
                # A bubble legible from across the square reads as every
                # townsperson narrating themselves at once -- it only earns
                # its keep once the player is close enough to actually hear
                # the two of them, same reach as walking up and joining in.
                if mind.npc.distance_to(*self.iris) > agents_api.OVERHEAR_RANGE:
                    continue
                wrapped = _wrap(spoken[1], 16)[:2]
                width = 10.0 + 5.2 * max((len(line) for line in wrapped), default=0)
                scene.draw("ui", "panel",
                           at=(mind.npc.x, mind.npc.y - 24.0 + (len(wrapped) - 1) * 3.5),
                           size=(width, 7.0 + 8.0 * len(wrapped)),
                           color=(0.04, 0.05, 0.07, 0.86))
                for offset, line in enumerate(wrapped):
                    scene.text(line, at=(mind.npc.x, mind.npc.y - 26.0 + offset * 7.5),
                               height=6.5, align="center",
                               color=(0.90, 0.92, 0.97, 1.0))

        # The glow under each of them is the photon they are; the sprite on top
        # is the body that photon wears. No hound at heel until it is found.
        frame = int(self._walk_clock * WALK_FPS) % 2 if self.walking else 0
        if self.story.has_lumi:
            self._sprite(scene, "shadow", (self.lumi[0], self.lumi[1] + 2.0), T.TILE)
            scene.draw("photon", "halo", at=tuple(self.lumi),
                       size=(T.TILE * 0.7, T.TILE * 0.7),
                       emission_nm=LUMI.wavelength_nm)
            lumi_suffix, lumi_mirror = self._lumi_sprite()
            self._sprite(scene, f"lumi_{lumi_suffix}_{frame}",
                         self.lumi, T.TILE, mirror=lumi_mirror)
        # The shadow stays on the ground and shrinks; the body rises off it.
        # Nothing else reads as height in a top-down view -- without the
        # shadow staying put, a jump is indistinguishable from walking north.
        shade = 1.15 - min(self.z / 40.0, 0.45)
        self._sprite(scene, "shadow", (self.iris[0], self.iris[1] + 3.0),
                     T.TILE * shade)
        scene.draw("photon", "halo", at=tuple(self.iris), size=(T.TILE * 0.9, T.TILE * 0.9),
                   emission_nm=IRIS.wavelength_nm)
        self._sprite(scene, f"iris_{self._sheet_facing()}_{frame}", self._drawn_at,
                     T.TILE * 1.15, mirror=self.facing == "left")

        if getattr(self, "_attack_anim_timer", 0.0) > 0.0:
            self._draw_attack_effect(scene)
        if getattr(self, "_shield_timer", 0.0) > 0.0:
            self._draw_shield_effect(scene)

        # World feedback goes over the world and under the panels: a number
        # behind a dialogue box is a number nobody saw.
        self.sparks.draw(scene)

        if self.battle is not None:
            self._draw_battle(scene, camera, half)
            # ...and battle feedback goes over the battle screen, because that
            # is what it is about.
            self.battle_sparks.draw(scene)
        elif self.menu_open:
            self._draw_menu(scene, camera, half)
        else:
            self._draw_hud(scene, camera, half)

    @property
    def _drawn_at(self) -> tuple[float, float]:
        """Where Iris' body is drawn, which is not where she stands.

        Returns
        -------
        tuple of float
            Her position lifted by her height off the ground.
        """
        return (self.iris[0], self.iris[1] - self.z)

    def _sheet_facing(self) -> str:
        """Which drawn facing to use for Iris.

        Returns
        -------
        str
            ``left`` reuses the ``right`` artwork mirrored, so the atlas holds
            three facings rather than four.
        """
        return "right" if self.facing in ("left", "right") else self.facing

    def _lumi_sprite(self) -> tuple[str, bool]:
        """Which drawn sprite and mirror flag matches Lumi's own facing.

        Lumi has ``down``, ``up`` and ``right`` art (see :mod:`.pixelart`) --
        left mirrors the right frame, the same trick every other character in
        this file uses rather than drawing a fourth set from scratch.

        Returns
        -------
        tuple of (str, bool)
            Sprite-name facing suffix and whether to mirror it.
        """
        facing = self.lumi_facing
        if facing == "left":
            return "right", True
        return facing, False

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
            World units per native tile -- the edge length for a sprite drawn
            at the grid's own square size, which is every sprite except a
            :mod:`.pixelart.bigart` entry. For one of those, ``size`` scales
            the sprite's *own* width and height (:attr:`_sprite_tiles`)
            instead of forcing it square, so a building four tiles wide and
            six tall draws at that aspect rather than being squashed to a
            square the size of one of its tiles.
        mirror : bool, optional
            Flip horizontally. Swapping the uv rectangle's ends mirrors the
            artwork, which is why the atlas needs no left-facing sprites.
        tint : tuple of float, optional
            Multiplied into the artwork; white leaves it alone.
        """
        u0, v0, u1, v1 = self._uvs[name]
        if mirror:
            u0, u1 = u1, u0
        tiles_w, tiles_h = self._sprite_tiles.get(name, (1.0, 1.0))
        width = size * (tiles_w / tiles_h)
        scene.batch.add(
            pos=(float(at[0]), float(at[1])),
            size=(width, size),
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

    def _fighter_card(self, scene, fighter, at, scale: float, tone, numbers: bool) -> None:
        """One combatant's readout, as a framed window.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        fighter : chisurf.plugins.misc.games.lumis_quest.api.battle.Fighter
            Whose readout.
        at : tuple of float
            Centre, in world units.
        scale : float
            The battle screen's own scale.
        tone : tuple of float
            Bar colour.
        numbers : bool
            Show the hit points as a number. Only your own creature gets them,
            which is the convention and is also the right information rule: you
            know your own condition exactly and you have to read the other one.
        """
        card_w, card_h = 150.0 * scale, 46.0 * scale
        scene.window(at, (card_w, card_h), scale=scale)
        left = at[0] - card_w * 0.5 + 10.0 * scale
        scene.text(fighter.name, at=(left, at[1] - card_h * 0.5 + 12.0 * scale),
                   height=12.0 * scale, color=(0.96, 0.96, 0.92, 1.0))
        scene.text(f"T{fighter.beast.tier}",
                   at=(at[0] + card_w * 0.5 - 10.0 * scale,
                       at[1] - card_h * 0.5 + 12.0 * scale),
                   height=10.0 * scale, align="right", color=(0.80, 0.84, 0.94, 1.0))
        self._bar(scene, (at[0], at[1] + 2.0 * scale), card_w - 20.0 * scale,
                  6.0 * scale, fighter.hp / max(fighter.beast.max_hp, 1), tone)
        tail = (f"{fighter.hp}/{fighter.beast.max_hp}" if numbers
                else f"{fighter.beast.emission_nm:.0f} nm")
        scene.text(tail, at=(at[0] + card_w * 0.5 - 10.0 * scale,
                             at[1] + card_h * 0.5 - 9.0 * scale),
                   height=10.0 * scale, align="right", color=(0.78, 0.82, 0.90, 1.0))

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
        # No aura. An additive glow behind a sprite is what a modern engine
        # does because it can, and at this size it is a coloured blob with an
        # animal somewhere inside it -- the label's colour is already carried by
        # the tint, which is the whole point of the bestiary. What a creature
        # gets instead is a flat platform to stand on, which is how these
        # screens put a thing in a place -- turned earth on the lit side,
        # cold stone in the dark manifold, because a bright green pad floating
        # in the ash read as a sticker from a different game.
        if self.dark:
            rim, top = (0.16, 0.13, 0.22, 1.0), (0.28, 0.24, 0.34, 1.0)
        else:
            rim, top = (0.30, 0.40, 0.26, 1.0), (0.44, 0.56, 0.34, 1.0)
        scene.draw("ui", "frame", at=(at[0], at[1] + size * 0.46),
                   size=(size * 1.15, size * 0.30), color=rim)
        scene.draw("ui", "frame", at=(at[0], at[1] + size * 0.44),
                   size=(size * 1.02, size * 0.22), color=top)
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

    def _draw_trees(self, scene, camera, half) -> None:
        """Draw a tree at every ``TREE`` tile, standing over the ground.

        A real canopy (:mod:`.pixelart.bigart`'s ``big_tree``, four tiles wide
        and three tall) does not fit the tile-grid batch: that batch is one
        draw call for the *whole* screen at one uniform quad size, so every
        instance in it has to be the same shape. Giving trees their own size
        the way :meth:`_draw_structures` already gives buildings theirs means
        drawing them here instead, each its own quad -- :meth:`_building`
        already anchors a taller-than-one-tile sprite by its base, which is
        exactly what a tree standing in its tile wants too.

        Rows are visited top to bottom (``np.nonzero`` on a 2D array walks
        row-major), so a tree lower on screen is queued after one above it and
        draws over it where their canopies overlap -- the same "further down
        wins" rule the ground batch gets for free from its own raster order,
        made to hold here too since these are now separate draw calls.

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
        # Trees do not survive the dark manifold's lookup table (T.TREE ->
        # T.DEADTREE, still string art), so grid_array never holds one while
        # self.dark is set -- no wash to apply here.
        window = self.grid_array[row0:row1, col0:col1]
        rows, cols = np.nonzero(window == T.TREE)
        for row, col in zip(rows, cols):
            x = (col0 + int(col) + 0.5) * T.TILE
            y = (row0 + int(row) + 0.5) * T.TILE
            self._building(scene, "big_tree", (x, y))

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
            # Fog of war: only the land Iris is standing in right now, at map
            # zoom only -- up close she is always standing in it, so this
            # never touches ordinary play. It returns the moment she leaves,
            # the same as it does for the buildings, the people and the
            # dungeon markers -- an explored land is not a *remembered* one.
            # Land rects are few, so this loops over them rather than per
            # tile.
            gx = col0 + np.arange(cols) * step
            gy = row0 + np.arange(rows) * step
            fogged = np.ones((rows, cols), dtype=bool)
            here = self.land
            if here is not None:
                rc, rr, rw, rh = here.rect
                fogged &= ~((gx[None, :] >= rc) & (gx[None, :] < rc + rw)
                           & (gy[:, None] >= rr) & (gy[:, None] < rr + rh))
            instances[fogged.reshape(-1), 4:8] = FOG_COLOR
        else:
            # The dark manifold is drawn from the same art, drained. Without
            # this the trodden-earth floors and the roads keep their warmth and
            # sit in the ash looking like a different game -- and the roads are
            # supposed to still be there, just not to be inviting.
            instances[:, 4:8] = DARK_WASH if self.dark else 1.0
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
        # At full detail, trees are drawn in _draw_trees instead, each its own
        # oversized quad grown from real canopy art -- forcing that into one
        # grid cell here is exactly what made the ground's old tree read as a
        # placeholder. The map view never calls _draw_trees (a sprite smaller
        # than a pixel is noise there too), so it keeps drawing tree tiles as
        # the flat colour dots the rest of the map is made of.
        keep = window.reshape(-1) != T.BUILDING
        if not as_map:
            keep &= window.reshape(-1) != T.TREE
        self.scene_batch.add_array(instances[keep])

    def _draw_rooms(self, scene, camera, half, as_map: bool = False) -> None:
        """Draw the buildings, culled to the view.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        camera : chisurf.gui.chigame.render.Camera
            The view.
        half : numpy.ndarray
            Half-extent in world units.
        as_map : bool, optional
            Whether the view is the world map -- a settlement icon is exactly
            the kind of thing fog of war exists to hide outside the land
            Iris is standing in right now.
        """
        for room in self.world.rooms:
            x, y = room.position
            if abs(x - camera.center[0]) > half[0] + T.TILE:
                continue
            if abs(y - camera.center[1]) > half[1] + T.TILE:
                continue
            if as_map:
                room_region = self.world.region_at(x, y)
                if room_region is None or room_region is not self.land:
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

    #: The two Ninja Adventure house sprites, by style index -- see
    #: :data:`~.pixelart.HOUSE_STYLES`.
    HOUSE_SPRITES = ("house_hut", "house_barn")

    def _house_sprite(self, room, lit: bool) -> str:
        """Which of the house styles a page is built in.

        Chosen by the page's own address, so a street is a hut beside a barn
        the way a street is, and the same page is the same house on every
        visit. Both styles are one real CC0 sprite each rather than a lit and
        a dark drawing -- read-or-not is carried by :data:`HOUSE_TINT` alone
        now, the same colour multiply that already does wild/withered/scouted/
        settled.

        Parameters
        ----------
        room : chisurf.plugins.misc.games.lumis_quest.api.world.Room
            The page.
        lit : bool
            Unused now that a house has one drawing rather than a lit and a
            dark one; kept so callers do not have to change.

        Returns
        -------
        str
            A sprite name.
        """
        del lit
        style = npcs_api._seed(room.address) % pixelart.HOUSE_STYLES
        return self.HOUSE_SPRITES[style]

    def _building(self, scene, sprite: str, at, tint=(1.0, 1.0, 1.0, 1.0)) -> None:
        """Draw something built, standing over its own tile.

        A building the size of its own tile sits *in* the ground; a 16-bit town
        reads because its buildings stand over it and overlap the row behind.
        The sprite is drawn oversized and pushed up so its base stays exactly
        where the tile is. A real multi-tile building (:mod:`.pixelart.bigart`)
        is drawn at its own true height; a plain one-tile icon keeps the
        one-and-a-half-tile stretch that makes even those read as standing on
        the ground rather than sitting in it.

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
        _, tiles_tall = self._sprite_tiles.get(sprite, (1.0, 1.0))
        size = T.TILE * (tiles_tall if tiles_tall > 1.0 else BUILDING_HEIGHT)
        self._sprite(scene, sprite, (at[0], at[1] - (size - T.TILE) * 0.5), size,
                     tint=tint)

    def _battle_backdrop(self, scene, cx, cy, width, height, scale) -> None:
        """Paint the place the fight happens.

        Two flat rectangles -- one blue, one green -- were the whole scene
        before this, whichever land the encounter was in and on either side of
        the manifold. The backdrop is now read off where Iris is actually
        standing: the sky is a banded gradient (near-black in the dark
        manifold), a silhouetted treeline stands on the horizon, and the
        ground band is tiled with the same terrain art the land itself is
        painted with, so a marsh fight looks like a marsh and an ash fight
        looks like ash. Everything is deterministic in screen position --
        no per-frame rolls, so the scenery holds still.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        cx, cy : float
            Screen centre in world units.
        width, height : float
            Screen extent in world units.
        scale : float
            The battle screen's own scale.
        """
        region = self.world.region_at(float(self.iris[0]), float(self.iris[1]))
        biome = region.biome if region is not None else "meadow"
        horizon = cy + height * 0.10
        sky_top = cy - height * 0.5
        if self.dark:
            bands = ((0.04, 0.03, 0.08, 1.0), (0.09, 0.06, 0.14, 1.0),
                     (0.16, 0.11, 0.21, 1.0))
        else:
            bands = ((0.30, 0.47, 0.70, 1.0), (0.44, 0.62, 0.78, 1.0),
                     (0.63, 0.76, 0.86, 1.0))
        band_h = (horizon - sky_top) / len(bands)
        for index, tone in enumerate(bands):
            scene.draw("ui", "frame",
                       at=(cx, sky_top + (index + 0.5) * band_h),
                       size=(width, band_h + 1.0 * scale), color=tone)

        # The treeline: what stands on a horizon depends on the land. A
        # silhouette, not artwork -- it is far away, and a far thing is a
        # shape in the haze, which one dark tint does and detail would undo.
        if self.dark:
            standing, tint = "deadtree", (0.24, 0.17, 0.30, 1.0)
        elif biome == "highland":
            standing, tint = "rock", (0.38, 0.46, 0.58, 1.0)
        else:
            standing, tint = "tree", (0.34, 0.45, 0.55, 1.0)
        # Two offset rows, dense enough to close ranks: a single spaced row
        # read as bushes dotted along a line, not as a wood in the distance.
        back = tuple(component * 0.82 for component in tint[:3]) + (1.0,)
        for depth, (count, lift, tone) in enumerate(
                ((26, 0.42, back), (22, 0.30, tint))):
            for index in range(count):
                jitter = ((index * 37 + depth * 11) % 5 - 2) * scale
                tree_h = (22.0 + ((index * 23 + depth * 7) % 3) * 4.0) * scale
                self._sprite(scene, standing,
                             (cx - width * 0.5 + (index + 0.5) * width / count,
                              horizon - tree_h * lift + jitter),
                             tree_h, mirror=bool((index + depth) % 2), tint=tone)

        # The ground band, tiled with the land's own terrain art.
        if self.dark:
            base, accent, every = "ash", "tar", 9
        elif biome == "marsh":
            base, accent, every = "grass", "marsh", 5
        elif biome == "coast":
            base, accent, every = "sand", "grass2", 7
        elif biome == "highland":
            base, accent, every = "grass2", "rock", 8
        else:
            base, accent, every = "grass", "grass2", 2
        cols, rows = 16, 4
        tile = width / cols
        for row in range(rows):
            y = horizon + (row + 0.5) * (cy + height * 0.5 - horizon) / rows
            for col in range(cols):
                name = accent if (col * 13 + row * 7) % every == 0 else base
                self._sprite(scene, name,
                             (cx - width * 0.5 + (col + 0.5) * tile, y), tile)

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

        # The encounter takes the whole screen. A rounded box floating over the
        # overworld is a dialog; a battle is a *place you have gone to*, and
        # every game this one is modelled on cuts to a full screen with its own
        # ground and sky. It is also what stops the terrain showing through the
        # numbers, which no amount of opacity on a smaller box ever quite did.
        self._battle_backdrop(scene, cx, cy, width, height, scale)

        if self.flagging or self.challenge is not None or self.verdict is not None:
            # The reading screens sit over the same place the fight does, but
            # their text crosses the horizon -- dim the scenery under them so
            # a sentence is never fighting a treeline for contrast.
            scene.draw("ui", "panel", at=(cx, cy), size=(width, height),
                       color=(0.07, 0.09, 0.15, 0.82))

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


        # The console arrangement, and it is a convention worth keeping to the
        # letter: each combatant's *readout* sits diagonally opposite its
        # sprite. That is not decoration -- it is what stops a player's eye
        # having to cross the screen to pair a name with the thing it belongs
        # to, and it is why these screens are readable at a glance.
        enemy, active = fight.opponent, fight.active
        self._portrait_scale = scale
        # Big. These sprites were a third of this and the screen read as a
        # form with two icons on it; the creature is the subject of the scene
        # and has to be the largest thing in it. Yours is larger still, because
        # it is nearer.
        self._portraits["enemy"] = (cx + half[0] * 0.42, cy - half[1] * 0.44)
        self._portraits["ours"] = (cx - half[0] * 0.44, cy + half[1] * 0.02)
        self._beast_portrait(scene, enemy, self._portraits["enemy"], 66.0 * scale)
        self._beast_portrait(scene, active, self._portraits["ours"], 80.0 * scale)

        self._fighter_card(scene, enemy, (cx - half[0] * 0.42, cy - half[1] * 0.62),
                           scale, (0.90, 0.42, 0.38, 1.0), numbers=False)
        self._fighter_card(scene, active, (cx + half[0] * 0.40, cy + half[1] * 0.12),
                           scale, (0.40, 0.85, 0.70, 1.0), numbers=True)

        # The bottom band: what just happened on the left, what you may do on
        # the right, both in framed windows rather than floating over the art.
        band_h = half[1] * 0.62
        band_y = cy + half[1] - band_h * 0.5 - 4.0 * scale
        said_w = half[0] * 1.16
        scene.window((cx - half[0] + said_w * 0.5 + 4.0 * scale, band_y),
                     (said_w, band_h), scale=scale)

        lines: list[str] = []
        for turn in fight.log[-2:]:
            lines.extend(_wrap(turn.text, 34))
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
            lines = _wrap(outcome, 34)[:2] + ["", "Confirm to continue"]
        left = cx - half[0] + 16.0 * scale
        for offset, line in enumerate(lines[-4:]):
            scene.text(line, at=(left, band_y - band_h * 0.5 + (14.0 + offset * 13.0) * scale),
                       height=11.0 * scale, color=(0.92, 0.94, 0.98, 1.0))
        if fight.finished:
            return

        options = self._battle_options()
        menu_w = half[0] * 0.80
        menu_x = cx + half[0] - menu_w * 0.5 - 4.0 * scale
        scene.window((menu_x, band_y), (menu_w, band_h), scale=scale,
                     fill=(0.16, 0.13, 0.30, 0.98))
        pitch = min(13.0 * scale, (band_h - 20.0 * scale) / max(1, len(options)))
        first = band_y - (pitch * (len(options) - 1)) * 0.5
        for index, (label, _) in enumerate(options):
            selected = index == self.menu_index
            y = first + index * pitch
            if selected:
                scene.draw("ui", "selected",
                           at=(menu_x - menu_w * 0.5 + 12.0 * scale, y),
                           size=(6.0 * scale, 6.0 * scale))
            scene.text(label, at=(menu_x - menu_w * 0.5 + 20.0 * scale, y),
                       height=11.0 * scale,
                       color=(1.00, 0.98, 0.92, 1.0) if selected
                       else (0.68, 0.72, 0.84, 1.0))

        if self._battle_intro > 0.0:
            # The zoom-and-settle in update() is the motion; this is the
            # flash, fading from opaque white to nothing over the same
            # window -- drawn last so it sits over everything else above,
            # including the menu that is already fully live underneath it.
            fade = self._battle_intro / ENCOUNTER_FLASH_SECONDS
            scene.draw("ui", "panel", at=(cx, cy), size=(width, height),
                       color=(1.0, 1.0, 1.0, fade))

    def _draw_interior(self, scene, camera, half) -> None:
        """Draw the room a door just opened onto.

        Small enough (:mod:`.interiors`' room sizes) that every tile is its
        own draw call rather than the outdoor world's vectorised batch --
        that batch exists because a screenful of overworld is thousands of
        tiles; a room is at most 16x14 of them.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        camera : chisurf.gui.chigame.render.Camera
            The view.
        half : numpy.ndarray
            Half-extent in world units.
        """
        interior = self.interior
        scale = camera.height / VIEW_HEIGHT
        cols, rows = interior.grid.shape[1], interior.grid.shape[0]
        for row in range(rows):
            for col in range(cols):
                sprite = INDOOR_TILE_SPRITES.get(int(interior.grid[row, col]), "boards")
                self._sprite(scene, sprite,
                            ((col + 0.5) * T.TILE, (row + 0.5) * T.TILE), T.TILE)

        for npc in self.indoor_people:
            sprite_name = "samurai_green_down_0" if npc.role in ("barkeep", "smith", "merchant") else "samurai_blue_down_0"
            self._sprite(scene, "shadow", (npc.x, npc.y + 3.0), T.TILE)
            self._sprite(scene, sprite_name, (npc.x, npc.y), T.TILE)

        frame = int(self._walk_clock * WALK_FPS) % 2 if self.walking else 0
        self._sprite(scene, "shadow", (self._indoor_pos[0], self._indoor_pos[1] + 3.0), T.TILE)
        scene.draw("photon", "halo", at=tuple(self._indoor_pos),
                   size=(T.TILE * 0.9, T.TILE * 0.9), emission_nm=IRIS.wavelength_nm)
        self._sprite(scene, f"iris_{self._sheet_facing()}_{frame}", self._indoor_pos,
                     T.TILE * 1.15, mirror=self.facing == "left")

        cx, cy = float(camera.center[0]), float(camera.center[1])
        scene.window((cx, camera.center[1] - half[1] + 14.0 * scale),
                     (self._text_width(scene, interior.title, 12.0) + 24.0 * scale,
                      20.0 * scale), scale=scale)
        scene.text(interior.title, at=(cx, camera.center[1] - half[1] + 14.0 * scale),
                   height=12.0 * scale, align="center", color=(0.90, 0.86, 0.60, 1.0))

        if self.menu_open:
            self._draw_menu(scene, camera, half)
        else:
            scene.text("Walk to the door to leave", at=(cx, cy + half[1] * 0.86),
                       height=9.5 * scale, align="center", color=(0.48, 0.52, 0.60, 1.0))

    def _attack_overworld(self) -> None:
        """Perform a Zelda-style real-time weapon attack in the overworld."""
        if getattr(self, "_attack_cooldown", 0.0) > 0.0:
            return
        weapon_key = getattr(self, "active_weapon", "sword")
        info = WEAPON_DATA.get(weapon_key, WEAPON_DATA["sword"])

        self._attack_cooldown = info["cooldown"]
        self._attack_anim_timer = 0.18
        reach = info["reach"]

        facing = getattr(self, "facing", "down")
        dx, dy = 0.0, 0.0
        if facing == "up":
            dy = -reach
        elif facing == "down":
            dy = reach
        elif facing == "left":
            dx = -reach
        elif facing == "right":
            dx = reach
        else:
            dy = reach

        at_x = self.iris[0] + dx
        at_y = self.iris[1] + dy
        self._attack_arc_pos = (at_x, at_y)

        self._sound("slash", frequency=580.0)
        self.sparks.burst((at_x, at_y), count=8, kind="sparkle", color=info["color"], speed=50.0)

        # Cut grass/flowers/marsh
        tile_col = int(round(at_x / T.TILE))
        tile_row = int(round(at_y / T.TILE))
        grid = self.grid_array
        if 0 <= tile_row < grid.shape[0] and 0 <= tile_col < grid.shape[1]:
            cell_kind = grid[tile_row, tile_col]
            if cell_kind in (T.GRASS, T.MARSH, T.FLOWERS, T.GARDEN):
                self.sparks.burst((at_x, at_y), count=6, kind="leaf", speed=35.0)
                self.sparks.orbs((at_x, at_y), target=tuple(self.iris), count=3, kind="photon", speed=80.0)
                self.sparks.rise("+5 Photons", (at_x, at_y - 6), color=(0.4, 0.95, 0.5, 1.0), height=7.0)
                self.photons = min(self.photons_max, self.photons + 5)
                self._gather(random.choice(("roxs", "bsa")), (at_x, at_y - 14), chance=0.12)

        # Hit overworld beasts
        damage = info["damage"]
        for npc in list(getattr(self, "people", [])):
            if getattr(npc, "kind", "") == "beast":
                dist = math.hypot(npc.x - at_x, npc.y - at_y)
                if dist < reach * 1.2:
                    if self._marked_nm(npc) > 0.0:
                        # A marked animal is caught, not killed: swinging at
                        # one opens the same capture battle walking into it
                        # does, rather than deleting it from the world for a
                        # flat XP reward and skipping Unbind entirely.
                        self._try_encounter(force=True)
                        return
                    hp = getattr(npc, "hp", 60.0) - damage
                    npc.hp = max(0.0, hp)
                    npc.startled = True
                    self.sparks.rise(f"-{int(damage)}", (npc.x, npc.y - 10), color=(1.0, 0.3, 0.3, 1.0), height=9.0)
                    self.sparks.burst((npc.x, npc.y), count=10, kind="sparkle", speed=60.0)
                    kb_dir_x = (npc.x - self.iris[0]) or 1.0
                    kb_dir_y = (npc.y - self.iris[1]) or 0.0
                    kb_len = math.hypot(kb_dir_x, kb_dir_y) or 1.0
                    npc.knockback_vx = (kb_dir_x / kb_len) * 160.0
                    npc.knockback_vy = (kb_dir_y / kb_len) * 160.0
                    npc.knockback_timer = 0.25

                    if npc.hp <= 0.0 and npc in self.people:
                        self._sound("defeat", frequency=240.0)
                        self.sparks.burst((npc.x, npc.y), count=16, kind="nova", speed=90.0)
                        self.sparks.orbs((npc.x, npc.y), target=tuple(self.iris), count=8, kind="photon", speed=90.0)
                        self.sparks.rise("+50 Photons", (npc.x, npc.y - 14), color=(1.0, 0.85, 0.3, 1.0), height=10.0)
                        self.photons = min(self.photons_max, self.photons + 50)
                        self._gather(random.choice(("trolox", "godcat")),
                                    (npc.x, npc.y - 22), chance=0.2)
                        self._gather("pagfp", (npc.x, npc.y - 30), chance=0.08)
                        self.people.remove(npc)

    def _cast_magic(self) -> None:
        """Cast a Zelda-style magic spell in the overworld."""
        if getattr(self, "_magic_cooldown", 0.0) > 0.0:
            return
        magic_key = getattr(self, "active_magic", "flame")
        info = MAGIC_DATA.get(magic_key, MAGIC_DATA["flame"])
        cost = info["cost"]

        if self.photons < cost:
            self.sparks.rise("No Photons!", tuple(self.iris), color=(1.0, 0.4, 0.4, 1.0), height=8.0)
            self._sound("cancel", frequency=220.0)
            return

        self.photons -= cost
        self._magic_cooldown = info["cooldown"]

        if magic_key == "flame":
            self._sound("flame", frequency=440.0)
            facing = getattr(self, "facing", "down")
            dx, dy = 0.0, 0.0
            if facing == "up":
                dy = -1.0
            elif facing == "down":
                dy = 1.0
            elif facing == "left":
                dx = -1.0
            elif facing == "right":
                dx = 1.0
            else:
                dy = 1.0

            for step in range(1, 6):
                fx = self.iris[0] + dx * (step * T.TILE * 0.8)
                fy = self.iris[1] + dy * (step * T.TILE * 0.8)
                self.sparks.burst((fx, fy), count=5, kind="flame", color=info["color"], speed=40.0)
                for npc in list(getattr(self, "people", [])):
                    if getattr(npc, "kind", "") == "beast":
                        if math.hypot(npc.x - fx, npc.y - fy) < T.TILE:
                            if self._marked_nm(npc) > 0.0:
                                # Same rule as the blade: catch, not kill.
                                self._try_encounter(force=True)
                                return
                            damage = info["damage"]
                            npc.hp = max(0.0, getattr(npc, "hp", 60.0) - damage)
                            self.sparks.rise(f"-{int(damage)}", (npc.x, npc.y - 10), color=(1.0, 0.4, 0.2, 1.0), height=9.0)
                            if npc.hp <= 0.0 and npc in self.people:
                                self.sparks.burst((npc.x, npc.y), count=16, kind="nova")
                                self.sparks.orbs((npc.x, npc.y), target=tuple(self.iris), count=6)
                                self.people.remove(npc)

        elif magic_key == "heal":
            self._sound("heal", frequency=720.0)
            for f in getattr(self, "team", []):
                if hasattr(f, "hp") and hasattr(f, "max_hp"):
                    f.hp = min(f.max_hp, f.hp + info["heal"])
            self.sparks.burst(tuple(self.iris), count=18, radius=12.0, kind="aura", color=info["color"], speed=45.0)
            self.sparks.rise(f"+{int(info['heal'])} HP", (self.iris[0], self.iris[1] - 12.0), color=(0.3, 1.0, 0.6, 1.0), height=10.0)

        elif magic_key == "shield":
            self._sound("shield", frequency=880.0)
            self._shield_timer = info["duration"]
            self.sparks.burst(tuple(self.iris), count=14, radius=16.0, kind="sparkle", color=info["color"], speed=50.0)
            self.sparks.rise("FRET Shield Active!", tuple(self.iris), color=(0.2, 0.9, 1.0, 1.0), height=9.0)

    def _cycle_weapon(self) -> None:
        """Switch to the next available overworld weapon."""
        weapons = getattr(self, "weapons", ["sword", "lance", "axe", "rapier", "sai"])
        current = getattr(self, "active_weapon", "sword")
        idx = (weapons.index(current) + 1) % len(weapons) if current in weapons else 0
        self.active_weapon = weapons[idx]
        info = WEAPON_DATA[self.active_weapon]
        self.sparks.rise(f"Equipped {info['name']}", tuple(self.iris), color=info["color"], height=8.0)
        self._sound("confirm", frequency=600.0)

    def _cycle_magic(self) -> None:
        """Switch to the next available overworld magic spell."""
        magics = getattr(self, "magics", ["flame", "heal", "shield"])
        current = getattr(self, "active_magic", "flame")
        idx = (magics.index(current) + 1) % len(magics) if current in magics else 0
        self.active_magic = magics[idx]
        info = MAGIC_DATA[self.active_magic]
        self.sparks.rise(f"Selected {info['name']}", tuple(self.iris), color=info["color"], height=8.0)
        self._sound("confirm", frequency=680.0)

    def _update_overworld_enemies(self, dt: float) -> None:
        """Update overworld enemy AI, knockback, and aggro."""
        for npc in getattr(self, "people", []):
            if getattr(npc, "kind", "") == "beast":
                if not hasattr(npc, "hp"):
                    npc.hp = 60.0
                    npc.max_hp = 60.0

                if getattr(npc, "knockback_timer", 0.0) > 0.0:
                    npc.knockback_timer -= dt
                    npc.x += getattr(npc, "knockback_vx", 0.0) * dt
                    npc.y += getattr(npc, "knockback_vy", 0.0) * dt

                dist = npc.distance_to(*self.iris)
                notice_rad = getattr(npc, "notice_radius", T.TILE * 6.0)
                if dist < notice_rad and getattr(npc, "knockback_timer", 0.0) <= 0.0:
                    npc.startled = True
                    speed = getattr(npc, "speed", 75.0)
                    dx = (self.iris[0] - npc.x) / (dist or 1.0)
                    dy = (self.iris[1] - npc.y) / (dist or 1.0)
                    npc.x += dx * speed * dt
                    npc.y += dy * speed * dt

                    if dist < T.TILE * 0.7 and getattr(self, "_shield_timer", 0.0) <= 0.0 and getattr(self, "_iris_hit_flash", 0.0) <= 0.0:
                        self._iris_hit_flash = 0.4
                        self._sound("hit", frequency=180.0)
                        self.iris_hp = max(0, self.iris_hp - 10)
                        self.sparks.rise("-10 HP", tuple(self.iris), color=(1.0, 0.2, 0.2, 1.0), height=9.0)
                        self.sparks.burst(tuple(self.iris), count=6, kind="sparkle", color=(1.0, 0.2, 0.2, 1.0))
                        if self.iris_hp <= 0:
                            self._faint()

    def _draw_attack_effect(self, scene) -> None:
        """Draw the active weapon attack arc visual in front of Iris."""
        weapon = getattr(self, "active_weapon", "sword")
        info = WEAPON_DATA.get(weapon, WEAPON_DATA["sword"])
        arc_pos = getattr(self, "_attack_arc_pos", tuple(self.iris))
        reach = info["reach"]
        color = info["color"]
        scene.draw("photon", "halo", at=arc_pos, size=(reach * 1.6, reach * 1.6),
                   hints={"color": color, "alpha": 0.85})
        scene.draw("photon", "spark", at=arc_pos, size=(reach * 1.0, reach * 1.0),
                   hints={"color": (1.0, 1.0, 1.0, 0.9)})

    def _draw_shield_effect(self, scene) -> None:
        """Draw the rotating FRET Shield barrier around Iris."""
        angle = self._clock * 4.0
        color = MAGIC_DATA["shield"]["color"]
        for i in range(4):
            a = angle + i * (math.pi / 2.0)
            sx = self.iris[0] + math.cos(a) * 14.0
            sy = self.iris[1] + math.sin(a) * 14.0
            scene.draw("photon", "spark", at=(sx, sy), size=(6.0, 6.0),
                       hints={"color": color, "alpha": 0.85})

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
        # The title, prologue and epilogue wash the world down rather than
        # hiding it behind a flat panel -- loading is the one phase on the
        # curtain with no world drawn under it yet, so it alone stays opaque.
        has_backdrop = self.phase in ("title", "prologue", "epilogue")
        wash = (0.020, 0.024, 0.032, 0.72 if has_backdrop else 1.0)
        scene.draw("ui", "panel", at=(cx, cy), size=(half[0] * 2.4, half[1] * 2.4),
                   color=wash)

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
            # A framed window, the same console-dialogue box every other menu
            # and every line of speech in the game already stands in -- the
            # title screen was the one place still a name floating over a
            # flat panel with nothing to say it was a menu.
            rows = self._title_rows()
            pitch = 16.0
            tall = pitch * len(rows) + 20.0
            wide = max(self._text_width(scene, row, 12.0) for row in rows) + 64.0
            scene.window((cx, cy + (len(rows) - 1) * pitch * 0.5 * scale),
                         (wide * scale, tall * scale), scale=scale)
            for index, row in enumerate(rows):
                selected = index == self.title_index
                y = cy + index * pitch * scale
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
            # Positioned from the full card, so the block does not creep up
            # the screen as the appearing text fills it in; drawn from
            # however much of it has revealed so far. Left-aligned from a
            # fixed edge -- centring re-flows both edges of the line every
            # time a character is added, which is what makes appearing text
            # hard to read; left-aligned only the right edge moves.
            lines = _wrap(body, 42)
            shown_lines = _wrap(self._revealed(f"epilogue:{self.epilogue_index}", body), 42)
            widest = max((self._text_width(scene, ln, 11.0) for ln in lines), default=0.0)
            left = cx - widest * 0.5 * scale
            top = cy - 6.0 * scale - (len(lines) - 1) * 7.0 * scale
            for offset in range(len(lines)):
                line = shown_lines[offset] if offset < len(shown_lines) else ""
                scene.text(line, at=(left, top + offset * 14.0 * scale),
                           height=11.0 * scale, align="left",
                           color=(0.82, 0.86, 0.92, 1.0))
            scene.text(f"{self.epilogue_index + 1} / {len(cards)}    Confirm to go on",
                       at=(cx, cy + half[1] * 0.62), height=9.5 * scale,
                       align="center", color=(0.46, 0.50, 0.58, 1.0))
            return

        title, body = PROLOGUE[min(self.prologue_index, len(PROLOGUE) - 1)]
        scene.text(title, at=(cx, cy - 66.0 * scale), height=17.0 * scale,
                   align="center", color=(0.88, 0.82, 0.58, 1.0))
        # Wrapped to the view, then the whole block centred on the widest line
        # and each line left-aligned to that fixed edge -- centring every line
        # on its own ran a 52-character line off the right edge and lost the
        # last words of every card; left-aligning each line independently
        # made the block's left edge jump around from line to line. Fixed to
        # one edge, only the right edge moves as the appearing text fills in.
        lines = _wrap(body, 42)
        shown_lines = _wrap(self._revealed(f"prologue:{self.prologue_index}", body), 42)
        widest = max((self._text_width(scene, ln, 11.0) for ln in lines), default=0.0)
        left = cx - widest * 0.5 * scale
        top = cy - 6.0 * scale - (len(lines) - 1) * 7.0 * scale
        for offset in range(len(lines)):
            line = shown_lines[offset] if offset < len(shown_lines) else ""
            scene.text(line, at=(left, top + offset * 14.0 * scale),
                       height=11.0 * scale, align="left",
                       color=(0.80, 0.84, 0.90, 1.0))
        scene.text(f"{self.prologue_index + 1} / {len(PROLOGUE)}    "
                   "Confirm to go on, Cancel to skip",
                   at=(cx, cy + half[1] * 0.62), height=9.5 * scale, align="center",
                   color=(0.46, 0.50, 0.58, 1.0))

    #: What the soundtrack option cycles through. One list, read by the option
    #: that changes it and by the control that shows it -- two lists is how a
    #: selector ends up showing a theme the game cannot play.
    SOUNDTRACKS = ("Ninja Adventure (CC0)", "Classic Chiptune", "Synthesiser")

    def _menu_widget(self, tab: str, index: int, row: str):
        """The control a menu row is drawn as, if it is drawn as one.

        A row is a string everywhere else in the menu -- it is what the cursor
        moves over and what a click hit-tests against -- so the widgets are a
        *rendering* of a row rather than a replacement for it. Anything without
        a control here falls back to plain text.

        Parameters
        ----------
        tab : str
            The tab being drawn.
        index : int
            Row index within the tab.
        row : str
            The row's text, used for the parts of a label the tab already
            spells out.

        Returns
        -------
        object or None
            A control from :mod:`.imgui_controls`, or ``None`` for plain text.
        """
        if tab == "OPTIONS":
            if index == 0:
                schemes = list(SCHEMES)
                return imgui_controls.RadioGroup(
                    "controls", schemes,
                    index=schemes.index(self.scheme) if self.scheme in schemes else 0)
            if index == 1:
                return imgui_controls.RadioGroup(
                    "camera", ["scrolling", "screen"], index=1 if self.screen_mode else 0)
            if index in (2, 3, 4, 5):
                v_min, v_max, val, fmt = (
                    (120.0, 260.0, self.walk_speed, "%.0f") if index == 2 else
                    (300.0, 600.0, self.view_height, "%.0f") if index == 3 else
                    (0.0, 1.0, self.music_volume, "%.0%") if index == 4 else
                    (0.0, 1.0, self.sfx_volume, "%.0%")
                )
                return imgui_controls.SliderFloat(row.split(":")[0], v_min, v_max, val, fmt=fmt)
            if index in (7, 8):
                return imgui_controls.Button(
                    "regenerate wilderness" if index == 7 else "watch opening story")
            return None

        if tab == "GAMELOGIC":
            if index == 0:
                themes = list(self.SOUNDTRACKS)
                current = getattr(self, "soundtrack_theme", themes[0])
                return imgui_controls.Combo(
                    "soundtrack", themes,
                    index=themes.index(current) if current in themes else 0)
            if index == 1:
                return imgui_controls.SliderFloat(
                    "enemy aggro radius", 2.0, 8.0,
                    getattr(self, "enemy_aggro_radius", 4.5), fmt="%.1f tiles")
            if index in (2, 3, 4):
                label, on = (
                    ("zelda action combat", getattr(self, "action_combat_enabled", True))
                    if index == 2 else
                    ("particle bursts", getattr(self, "particle_fx_enabled", True))
                    if index == 3 else
                    ("crt retro shader", getattr(self, "crt_filter_enabled", False))
                )
                return imgui_controls.Toggle(label, on=on)
            if index == 5:
                tone = getattr(self, "ui_accent_tone", "Gold")
                return imgui_controls.ColorEdit4(
                    f"ui accent tone: {tone}",
                    color=imgui_controls.ACCENT_COLORS.get(tone, (0.96, 0.88, 0.50, 1.0)))
            if index in (6, 7, 8):
                return imgui_controls.Button(
                    "quick save run" if index == 6 else
                    "quick load run" if index == 7 else "test audio sfx")
            return None

        return None

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
        scene.window((cx, cy), (width * 0.94, height * 0.92), scale=scale,
                     fill=(0.055, 0.065, 0.085, 0.985))

        # Spread across the panel rather than at a fixed pitch: a fixed one fit
        # four tabs and clipped the fifth off the edge. The strip's own cell
        # width is span / len(TABS), which is what _menu_click_target hit-tests
        # against -- the two must stay the same arithmetic.
        span = half[0] * 1.5
        tab_y = cy - half[1] * 0.62
        strip = imgui_controls.Tabs(self.TABS, index=self.menu_tab)
        strip.draw(scene, at=(cx, tab_y), width=span, height=20.0 * scale,
                   scale=scale, text_height=9.0 * scale)

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
        row_w, row_h = half[0] * 1.2, 10.5 * scale
        for offset, row in enumerate(window):
            selected = base + offset == self.menu_row
            y = start + offset * 13.0 * scale
            if selected:
                scene.draw("ui", "selected", at=(cx - half[0] * 0.66, y),
                           size=(7.0 * scale, 7.0 * scale))

            widget = self._menu_widget(tab, base + offset, row)
            if widget is not None:
                widget.draw(scene, at=(cx, y), width=row_w, height=row_h,
                            scale=scale, selected=selected)
                continue

            if "[●]" in row:
                color = (0.35, 0.90, 0.45, 1.0) if selected else (0.28, 0.75, 0.36, 0.90)
            elif "[○]" in row:
                color = (0.95, 0.45, 0.45, 1.0) if selected else (0.78, 0.36, 0.36, 0.90)
            else:
                color = (0.96, 0.88, 0.50, 1.0) if selected else (0.56, 0.60, 0.68, 1.0)

            scene.text(row, at=(cx - half[0] * 0.62, y), height=10.5 * scale,
                       color=color)

        if tab == "OPTIONS" and len(self.frame_ms) > 1:
            # The one number a settings screen owes the player: what the last
            # second actually cost. A row of milliseconds would be read by
            # nobody; the shape of them is read at a glance.
            plot = imgui_controls.PlotLines(
                f"frame ms  {self.frame_ms[-1]:.1f}", list(self.frame_ms), v_min=0.0)
            plot.draw(scene, at=(cx + half[0] * 0.36, cy + half[1] * 0.40),
                      width=half[0] * 0.56, height=26.0 * scale, scale=scale,
                      text_height=8.0 * scale)

        rule = imgui_controls.Separator()
        rule.draw(scene, at=(cx, cy + half[1] * 0.58), width=half[0] * 1.5,
                  height=10.0 * scale, scale=scale)

        footer_hint = "L/R tab   Up/Down choose   Confirm use   Cancel close"
        if 0 <= self.menu_row < len(rows):
            sel_text = rows[self.menu_row]
            if "llm" in sel_text.lower():
                info = providers_api.llm_status()
                footer_hint = info["hover_info"]

        scene.text(footer_hint,
                   at=(cx, cy + half[1] * 0.66), height=9.5 * scale, align="center",
                   color=(0.40, 0.82, 0.95, 1.0) if "llm" in footer_hint.lower() else (0.48, 0.52, 0.60, 1.0))

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

    @staticmethod
    def _text_width(scene, text: str, height: float) -> float:
        """How wide a string will actually be, in world units.

        Asking the font rather than assuming is the difference between a panel
        that fits its contents and one that a longer land name walks out of.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            For its font.
        text : str
            The string.
        height : float
            Cell height in world units, before the HUD's own scale.

        Returns
        -------
        float
            Advance width, or a rough estimate when no font is loaded.
        """
        font = getattr(scene, "font", None)
        if font is not None and hasattr(font, "measure"):
            # Ask, rather than assume: the face is proportional, so there is no
            # per-character constant that would be right for both "iii" and
            # "WWW".
            return font.measure(text, height)
        return len(text) * height * 0.6

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

        # Life and casting energy, pinned top-left and always up during free
        # roam -- the real-time HUD this replaced (see the deleted duplicate
        # _draw_hud) had a "PHOTONS:" readout nobody ever saw, because Python
        # silently kept only the second of two methods with the same name.
        if getattr(self, "phase", "") == "play" and self.interior is None:
            bar_w = 74.0 * scale
            bar_x = left + 6.0 * scale + bar_w * 0.5
            scene.text(f"HP {self.iris_hp}/{self.iris_max_hp}",
                       at=(left + 6.0 * scale, top + 8.0 * scale), height=7.0 * scale,
                       color=(0.95, 0.90, 0.90, 1.0))
            self._bar(scene, (bar_x, top + 16.0 * scale), bar_w, 6.0 * scale,
                      self.iris_hp / max(self.iris_max_hp, 1), (0.90, 0.25, 0.30, 1.0))
            scene.text(f"EN {self.photons}/{self.photons_max}",
                       at=(left + 6.0 * scale, top + 26.0 * scale), height=7.0 * scale,
                       color=(0.88, 0.95, 0.96, 1.0))
            self._bar(scene, (bar_x, top + 34.0 * scale), bar_w, 6.0 * scale,
                      self.photons / max(self.photons_max, 1), (0.35, 0.85, 0.95, 1.0))
            # What Shoulder-L and Shoulder-R actually do right now -- cycled
            # from the RIG tab, since there was no button left to spare for a
            # dedicated key.
            w_info = WEAPON_DATA.get(self.active_weapon, WEAPON_DATA["sword"])
            m_info = MAGIC_DATA.get(self.active_magic, MAGIC_DATA["flame"])
            loadout_x = left + 88.0 * scale
            scene.text(w_info["name"], at=(loadout_x, top + 8.0 * scale),
                       height=7.0 * scale, color=w_info["color"])
            scene.text(m_info["name"], at=(loadout_x, top + 26.0 * scale),
                       height=7.0 * scale, color=m_info["color"])

        # The land's name, shown only while :attr:`_land_banner_timer` is
        # running down -- long enough to read on arrival, then gone. Everything
        # that used to live here permanently (settled/scouted, loadout, seals,
        # mode) moved to the STATUS tab of the pause menu: a stat block you can
        # only read by covering the world with it was not a HUD, it was a lid.
        if self._land_banner_timer > 0.0 and self._land_banner_land is not None:
            land = self._land_banner_land
            fade = min(1.0, self._land_banner_timer / LAND_BANNER_FADE)
            rows: list[tuple[str, float, tuple[float, float, float, float]]] = [
                (land.title, 15.0, (0.86, 0.82, 0.68, 1.0)),
            ]
            if land.subtitle:
                rows.append((land.subtitle, 9.5, (0.60, 0.62, 0.70, 1.0)))
            pad = 12.0
            # Dropped below the life/energy bars, which own the very top
            # corner now -- this used to be the first thing drawn there.
            banner_top = top + (44.0 * scale if getattr(self, "phase", "") == "play"
                                and self.interior is None else 0.0)
            widest = max(self._text_width(scene, text, size) for text, size, _ in rows)
            panel_w = widest + pad * 2.0
            panel_h = sum(size + 5.0 for _, size, _ in rows) + 14.0
            scene.window((left + panel_w * 0.5 * scale, banner_top + panel_h * 0.5 * scale),
                         (panel_w * scale, panel_h * scale), scale=scale,
                         fill=(0.055, 0.075, 0.16, 0.85 * fade))
            y = banner_top + 16.0 * scale
            for text, size, colour in rows:
                scene.text(text, at=(left + pad * scale, y), height=size * scale,
                           color=(colour[0], colour[1], colour[2], colour[3] * fade))
                y += (size + 5.0) * scale

        # The one piece of always-visible state: which world you are in. It is
        # a single short line in a corner rather than a panel, because it is
        # the one thing that changes what the rest of the screen means.
        if self.dark:
            tag = "the dark manifold"
            width = self._text_width(scene, tag, 9.0) + 20.0
            tx = left + half[0] * 2.0 - width * 0.5 * scale
            ty = top + 14.0 * scale
            scene.window((tx, ty), (width * scale, 18.0 * scale), scale=scale,
                         fill=(0.07, 0.05, 0.12, 0.80))
            scene.text(tag, at=(tx, ty), height=9.0 * scale, align="center",
                       color=(0.78, 0.58, 0.94, 1.0))

        # Dialogue owns the bottom band outright: the beat, the banner and the
        # loot line all live there too, and drawn first they bled through the
        # panel as ghost text behind whoever was talking.
        if self.screen is not None:
            screen = self.screen
            # Wrapped from the full line, so the panel is sized for what it
            # will hold rather than growing as the appearing text catches up;
            # wrapped again from however much of it has revealed so far for
            # what actually gets drawn into that layout.
            wrapped = _wrap(screen.text, 46)[:3] if screen.text else []
            shown = self._revealed(f"screen:{id(screen)}", screen.text or "")
            shown_wrapped = _wrap(shown, 46)[:3] if shown else []
            # Sized to what it actually holds. A fixed-height panel is either
            # mostly empty above one line of greeting or too short for four
            # choices, and this one has to serve both.
            rows = len(wrapped) + len(screen.choices)
            tall = 34.0 + 12.5 * max(rows, 1)
            middle = bottom - (tall * 0.5 + 22.0) * scale
            scene.window((camera.center[0], middle),
                         (half[0] * 1.7, tall * scale), scale=scale)
            head = middle - (tall * 0.5 - 10.0) * scale
            who = screen.who or (self.speaking.name if self.speaking else "")
            if who:
                scene.text(who, at=(camera.center[0], head),
                           height=11.0 * scale, align="center",
                           color=(0.90, 0.84, 0.60, 1.0))
            # Left-aligned from the panel's own inner edge -- centring
            # re-flows both edges of a line as the appearing text fills it
            # in, which is what makes it hard to read.
            left = camera.center[0] - half[0] * 0.85 + 16.0 * scale
            for offset in range(len(wrapped)):
                line = shown_wrapped[offset] if offset < len(shown_wrapped) else ""
                scene.text(line, at=(left, head + (14.0 + offset * 12.0) * scale),
                           height=10.0 * scale, align="left",
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
            # Inside the box, on its bottom rule. It used to sit at the very
            # edge of the screen, where the view cut it in half.
            scene.text(hint, at=(camera.center[0], middle + tall * 0.5 * scale - 7.0 * scale),
                       height=8.5 * scale, align="center", color=(0.56, 0.62, 0.78, 1.0))
            return

        # The bottom band, stacked from the bottom up and given a backing of its
        # own. These were five lines at five fixed offsets, so which of them
        # were on screen decided whether they collided -- the tutorial line and
        # the loot line are 14 units apart and both 10.5 tall -- and all of them
        # sat directly on the town floor, where pale text is unreadable. The
        # band is now sized to whatever is actually showing.
        band: list[tuple[str, float, tuple[float, float, float, float]]] = []
        step = self.tutorial.current
        if step is not None:
            # In the reward gold, above everything else along the bottom. It
            # names the next real control and waits for the real press -- it
            # never presses anything for the player.
            band.append((step.teach.format(**self._key_labels()), 10.5,
                         (0.95, 0.86, 0.50, 1.0)))
        if self.last_loot is not None:
            band.append((f"found {self.last_loot.summary}", 10.0,
                         (0.90, 0.84, 0.52, 1.0)))
        if self.resting:
            band.append(("recovering", 9.5, (0.45, 0.90, 0.75, 1.0)))
        beat = self.story.current
        if beat is not None:
            headline = beat.headline
            if beat.key == "the-work" and self.story.work_progress is not None:
                done, goal = self.story.work_progress
                headline += f"   {done}/{goal}"
            band.append((headline, 10.5, (0.62, 0.70, 0.80, 1.0)))
        room = self._nearby_room()
        if room is not None:
            band.append((room.title, 13.0, (0.80, 0.84, 0.90, 1.0)))
            band.append((f"{room.address}   [{room.state}]", 9.0,
                         (0.42, 0.46, 0.54, 1.0)))

        if band:
            pitch = 15.0
            tall = pitch * len(band) + 12.0
            wide = max(self._text_width(scene, text, size) for text, size, _ in band)
            base = bottom - (tall - 6.0) * scale
            scene.window((camera.center[0], base + (tall * 0.5 - 9.0) * scale),
                         (max(wide + 26.0, 180.0) * scale, tall * scale),
                         scale=scale, fill=(0.055, 0.075, 0.16, 0.88))
            for offset, (text, size, colour) in enumerate(band):
                scene.text(text, at=(camera.center[0], base + offset * pitch * scale),
                           height=size * scale, align="center", color=colour)
