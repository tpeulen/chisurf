"""Real character sheets under the game's own sprite names.

The game's vocabulary — ``iris_down_1``, ``warden_0``, ``hearts_a_4`` — was
authored as string art in :mod:`.pixelart`, and beside the shipped tile art it
read as the placeholder it was. This module answers those same names with
frames of the CC0 character sheets shipped with the engine
(``chisurf/gui/chigame/assets/pixel``, credited there): four direction columns
by seven animation rows of 16-pixel cells, the layout the engine's
:class:`~chisurf.gui.chigame.actors.SheetAnimation` drives.

The resolver contract is one function: given a sprite name, return an RGBA
array or ``None`` to fall back to the string art. Nothing else in the game
changes — the atlas (:func:`.pixelart.build_atlas`) packs whatever the resolver
provides, so tints, mirrors and multi-tile sizes all keep working.

Frame digits are walk-cycle rows: ``0`` is the idle/contact pose a standing
figure shows, ``1``-``3`` are the rest of the cycle, and the suffixes ``a``
(attack), ``j`` (airborne) and ``d`` (downed) pick the single-pose rows.
"""

from __future__ import annotations

import functools
import re

import numpy as np
from PIL import Image

from chisurf.gui.chigame.pack import PACK_ROOT

#: Cell size of the character sheets, in pixels.
SIZE = 16

#: Direction columns in every four-direction sheet.
_COLUMNS = {"down": 0, "up": 1, "left": 2, "right": 3}

#: Walk-frame digit / pose suffix to sheet row.
_ROWS = {"0": 0, "1": 1, "2": 2, "3": 3, "a": 4, "j": 5, "d": 6}

#: Which sheet a kind of figure wears. Villagers are the blue-robed figure;
#: Wardens, emissaries and lanternwrights are the green-robed one; the beasts
#: spread across all four so a variant never repeats a neighbour's silhouette.
_SHEETS = {
    "iris": "hero.png",
    "villager": "samurai_blue.png",
    "townsfolk": "samurai_blue.png",
    "healer": "samurai_blue.png",
    "keeper": "samurai_blue.png",
    "emissary": "samurai_green.png",
    "warden": "samurai_green.png",
    "lanternwright": "samurai_green.png",
    "lumi": "animal.png",
    "animal": "animal.png",
    "beast": "animal.png",
    "wraith": "animal.png",
    "squid_beast": "animal.png",
    "ninja_beast": "hero.png",
    "samurai_beast": "samurai_blue.png",
    "spirit_beast": "samurai_green.png",
}

#: Weapon key (the game's own vocabulary) to pack sprite stem.
_WEAPON_ART = {
    "sword": "big_sword",
    "lance": "bone",
    "axe": "axe",
    "rapier": "club",
    "sai": "book",
}

#: Vitality strip styles: the game's letter to the pack's sheet.
_HEART_STRIPS = {"a": "hearts", "b": "hearts_b", "c": "hearts_c"}

#: Weather and effect art, by the name the overworld draws them under.
_FX = {
    "fx_rain": "fx/rain",
    "fx_cloud": "fx/cloud",
    "fx_fog": "fx/fog",
    "fx_raylight": "fx/raylight",
}
for _step in range(7):
    _FX[f"fx_snow_{_step}"] = None  # sliced below
for _step in range(6):
    _FX[f"fx_leaf_{_step}"] = None
_FX = {k: v for k, v in _FX.items() if v is not None}

#: Sprite name with an optional facing and a frame digit or pose suffix.
_NAMED = re.compile(
    r"^(?P<kind>[a-z_]+?)(?:_(?P<facing>down|up|left|right))?_(?P<frame>[0-3ajd])$"
)


@functools.lru_cache(maxsize=None)
def _sheet(name: str) -> np.ndarray:
    """Load one character sheet as RGBA.

    Parameters
    ----------
    name : str
        File name under the pack's ``characters/`` directory.

    Returns
    -------
    numpy.ndarray
        ``(height, width, 4)`` uint8.
    """
    return np.asarray(Image.open(PACK_ROOT / "characters" / name).convert("RGBA"))


@functools.lru_cache(maxsize=None)
def _image(relative: str) -> np.ndarray:
    """Load any pack image by path relative to the pack root.

    Parameters
    ----------
    relative : str
        Path without extension.

    Returns
    -------
    numpy.ndarray
        RGBA uint8.
    """
    return np.asarray(Image.open(PACK_ROOT / f"{relative}.png").convert("RGBA"))


def _cell(sheet: np.ndarray, column: int, row: int) -> np.ndarray:
    """One 16x16 cell of a sheet.

    Parameters
    ----------
    sheet : numpy.ndarray
        The sheet.
    column, row : int
        Cell coordinates.

    Returns
    -------
    numpy.ndarray
        ``(16, 16, 4)`` uint8.
    """
    return sheet[row * SIZE:(row + 1) * SIZE,
                 column * SIZE:(column + 1) * SIZE].copy()


def resolve(name: str) -> np.ndarray | None:
    """Answer a sprite name with real art, or None for the string fallback.

    Parameters
    ----------
    name : str
        A sprite name from the game's vocabulary.

    Returns
    -------
    numpy.ndarray or None
        ``(h, w, 4)`` uint8 RGBA, or ``None`` when the name is not ours.
    """
    if name.startswith("fx_snow_") or name.startswith("fx_leaf_"):
        stem, _, step = name.rpartition("_")
        is_snow = stem == "fx_snow"
        columns = 7 if is_snow else 6
        if not step.isdigit() or int(step) >= columns:
            return None
        strip = _image("fx/snow" if is_snow else "fx/leaf")
        # These strips are horizontal: cells are as wide as the strip
        # divides, and only as tall as it is (8px snow, 7px leaves).
        width = strip.shape[1] // columns
        column = int(step)
        return strip[:, column * width:(column + 1) * width].copy()
    if name in _FX:
        return _image(_FX[name])
    if name.startswith("body_"):
        return _cell(_sheet("animal.png"), 0, 0)
    if name.startswith("weapon_"):
        key = name[len("weapon_"):]
        held = key.endswith("_held")
        stem = _WEAPON_ART.get(key[:-5] if held else key)
        if stem is None:
            return None
        return _image(f"weapons/{stem}_held" if held else f"weapons/{stem}")
    if name.startswith("hearts_"):
        style, _, step = name[len("hearts_"):].partition("_")
        if style not in _HEART_STRIPS or not step.isdigit():
            return None
        strip = _image(f"ui/{_HEART_STRIPS[style]}")
        # The alternative strips carry four steps rather than five; the last
        # step a strip has stands in for "full".
        last = strip.shape[1] // SIZE - 1
        return _cell(strip, min(int(step), last), 0)
    match = _NAMED.match(name)
    if match is None:
        return None
    kind = match.group("kind")
    facing = match.group("facing")
    frame = match.group("frame")
    sheet_name = _SHEETS.get(kind)
    if sheet_name is None:
        return None
    sheet = _sheet(sheet_name)
    if sheet_name == "animal.png":
        # Two-column animal sheet: the frame is the column, facings are
        # mirrored by the caller.
        return _cell(sheet, _ROWS.get(frame, 0) % 2, 0)
    column = _COLUMNS.get(facing or "down", 0)
    return _cell(sheet, column, _ROWS.get(frame, 0))


def names() -> tuple[str, ...]:
    """Every name this resolver answers that the string art does not.

    The atlas packs the union of its own names and these, so a name that only
    exists here (a weapon or a vitality strip) is still drawable.

    Returns
    -------
    tuple of str
    """
    every = [f"iris_{facing}_{frame}"
             for facing in _COLUMNS for frame in "0123ajd"]
    every.extend(f"{kind}_{frame}" for kind in _SHEETS for frame in "0123")
    # Facing-qualified names only where the game constructs them: the player
    # (``iris_{facing}_{pose}``) and the companion (``lumi_{facing}_{frame}``,
    # mirroring the left). Everyone else is drawn frame-only, and a name the
    # resolver answers but names() does not list never gets a uv — the frame
    # dies with a KeyError. The list stays small on purpose: the atlas packs
    # in a single row and WebGPU's default texture cap is 8192 px.
    every.extend(f"lumi_{facing}_{frame}"
                 for facing in _COLUMNS for frame in "0123")
    every.extend(f"weapon_{key}{suffix}"
                 for key in _WEAPON_ART for suffix in ("", "_held"))
    every.extend(f"hearts_{style}_{step}"
                 for style in _HEART_STRIPS for step in range(5))
    every.extend(_FX)
    every.extend(f"fx_snow_{step}" for step in range(7))
    every.extend(f"fx_leaf_{step}" for step in range(6))
    return tuple(every)
