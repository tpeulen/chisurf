"""chigame — the shared 2-D game engine.

`chisurf.gui.chigame` is *the* game engine of the application, in the same sense
that `chisurf.gui.chiplot` is the plotting API. Games use it; they never touch
the graphics API directly.

It renders through WebGPU, embedded in an ordinary Qt dock, and is built around
four seams:

* **AssetPack** — games emit semantic draw calls (``draw("dye", "atto488")``)
  and a pack decides how that looks and sounds, so the whole presentation is
  swappable without touching game code. The shipped
  :class:`SheetPack` is backed by CC0 pixel art packed into one texture atlas
  at load time; :class:`ProceduralPack` draws the same vocabulary as
  signed-distance shapes with no image files at all.
* **InputMap** — nine abstract actions and no text entry, so everything is
  playable on a gamepad and scriptable in a test.
* **Audio** — synthesised, context-switched music plus shipped CC0 clips.
* **Offscreen capture** — real pixels with no window server, which is what makes
  screenshot verification of a game possible.

On top of the seams sit the gameplay systems a top-down action game needs,
ported from the reference game in ``junk/NinjaAdventure``: sheet-animated
actors with a damage model (:mod:`.actors`), steering behaviors
(:mod:`.behavior`), tile maps (:mod:`.tilemap`), the room-locked camera
(:mod:`.camera`) and frame effects (:mod:`.fx`).

The engine's design record is ``okf/subsystems/chigame.md``.

Examples
--------
>>> from chisurf.gui import chigame
>>> class Blank(chigame.Game):
...     def update(self, dt, keys): pass
...     def draw(self, scene): scene.draw("ui", "panel", at=(0, 0), size=(20, 10))
>>> frame = chigame.capture(Blank(), size=(64, 48))  # doctest: +SKIP
"""

from __future__ import annotations

from .actors import (
    DOWN,
    FLASH_TINT,
    LEFT,
    RIGHT,
    ROW_ATTACK,
    ROW_DEAD,
    ROW_JUMP,
    ROW_MOVE,
    UP,
    Actor,
    Damage,
    Destroyable,
    Health,
    Team,
    Weapon,
    direction_column,
    draw_sorted,
    strike,
)
from .assets import Appearance, AssetPack, ProceduralPack, wavelength_to_srgb
from .atlas import Frame, TextureAtlas, load_pixel_pack
from .audio import Audio
from .behavior import Follow, Patrol, Sense, wander
from .camera import GLIDE_TIME, ROOM_SIZE, RoomCamera
from .fx import CLOUD, FOG, LEAF, RAIN, SNOW, Transition, Weather
from .game import Game, GameHost, capture, create_widget, save_png, sound_button
from .gpu import GpuContext, create_offscreen, get_adapter, get_device
from .input import Action, InputMap
from .pack import SheetPack
from .particles import Field as ParticleField
from .particles import Particle
from .render import (
    ELLIPSE,
    FLOATS_PER_INSTANCE,
    GLOW,
    GLYPH,
    RECT,
    RING,
    ROUND,
    SPRITE,
    TRI,
    Camera,
    SpriteBatch,
)
from .scene import Scene
from .text import FontAtlas
from .tilemap import TileMap

__all__ = [
    "Action",
    "Actor",
    "Appearance",
    "AssetPack",
    "Audio",
    "CLOUD",
    "Camera",
    "Damage",
    "Destroyable",
    "DOWN",
    "ELLIPSE",
    "FLASH_TINT",
    "FLOATS_PER_INSTANCE",
    "FOG",
    "Follow",
    "FontAtlas",
    "Frame",
    "Game",
    "GameHost",
    "GLOW",
    "GLYPH",
    "GpuContext",
    "Health",
    "InputMap",
    "LEAF",
    "LEFT",
    "Particle",
    "ParticleField",
    "Patrol",
    "ProceduralPack",
    "RAIN",
    "RECT",
    "RIGHT",
    "RING",
    "ROOM_SIZE",
    "ROW_ATTACK",
    "ROW_DEAD",
    "ROW_JUMP",
    "ROW_MOVE",
    "ROUND",
    "RoomCamera",
    "Scene",
    "Sense",
    "SheetPack",
    "SNOW",
    "SPRITE",
    "SpriteBatch",
    "Team",
    "TextureAtlas",
    "TileMap",
    "TRI",
    "Transition",
    "UP",
    "Weapon",
    "Weather",
    "capture",
    "create_offscreen",
    "create_widget",
    "direction_column",
    "draw_sorted",
    "get_adapter",
    "get_device",
    "load_pixel_pack",
    "save_png",
    "sound_button",
    "strike",
    "wander",
    "wavelength_to_srgb",
]
