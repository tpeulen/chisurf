"""chigame — the shared 2-D game engine.

`chisurf.gui.chigame` is *the* game engine of the application, in the same sense
that `chisurf.gui.chiplot` is the plotting API. Games use it; they never touch
the graphics API directly.

It renders through WebGPU, embedded in an ordinary Qt dock, and is built around
four seams:

* **AssetPack** — games emit semantic draw calls (``draw("dye", "atto488")``)
  and a pack decides how that looks and sounds, so the whole presentation is
  swappable without touching game code.
* **InputMap** — nine abstract actions and no text entry, so everything is
  playable on a gamepad and scriptable in a test.
* **Audio** — synthesised, context-switched music; no audio files ship.
* **Offscreen capture** — real pixels with no window server, which is what makes
  screenshot verification of a game possible.

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

from .assets import Appearance, AssetPack, ProceduralPack, wavelength_to_srgb
from .audio import Audio
from .game import Game, GameHost, capture, create_widget, save_png
from .gpu import GpuContext, create_offscreen, get_adapter, get_device
from .input import Action, InputMap
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

__all__ = [
    "Action",
    "Appearance",
    "AssetPack",
    "Audio",
    "Camera",
    "ELLIPSE",
    "FLOATS_PER_INSTANCE",
    "FontAtlas",
    "GLOW",
    "GLYPH",
    "Game",
    "GameHost",
    "GpuContext",
    "InputMap",
    "Particle",
    "ParticleField",
    "ProceduralPack",
    "RECT",
    "RING",
    "ROUND",
    "SPRITE",
    "Scene",
    "SpriteBatch",
    "TRI",
    "capture",
    "create_offscreen",
    "create_widget",
    "get_adapter",
    "get_device",
    "save_png",
    "wavelength_to_srgb",
]
