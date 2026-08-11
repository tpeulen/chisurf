"""The shipped ground tiles, and how they get into the sprite atlas.

The world's terrain was authored as string art in :mod:`.pixelart` -- three
tones and a scatter of noise per material. It was honest, and it was flat, and
beside real 16-bit tile art it read as a placeholder, which is what it was.

The ground now comes from **Ninja Adventure** by Pixel-boy and AAA, released
**CC0** by its authors. CC0 is a public-domain dedication: nothing to reconcile
with this package's licence, no notice to propagate, no attribution required.
Attribution is in ``art/CREDITS.md`` regardless.

Only the *ground* is replaced. Every building, character and creature is still
string art, because those are this game's own -- a marked hare in the colour of
its own label is not something a generic pack has -- and because the two share
a 16x16 grid, mixing them is a substitution rather than a second pipeline.

The tiles are cut and **shipped** by
:mod:`build_tools.dev_utils.import_tileart` rather than read from the reference
checkout at run time: ``junk/`` is gitignored, so anything that reads from it
works on one machine and nowhere else.

Decoding is done with Qt, which the game already needs for its window. If Qt is
missing or the file is not there, this returns nothing at all and the string art
stands -- an art pack that fails to load must degrade to the drawing that was
already working, never to a blank world.
"""

from __future__ import annotations

import functools
import json
import pathlib

import numpy as np

#: Where the cut tiles are shipped, beside this module.
ART = pathlib.Path(__file__).resolve().parent / "art"

#: The strip and its index, both written by the import script.
STRIP = ART / "terrain.png"
INDEX = ART / "terrain.json"


@functools.lru_cache(maxsize=1)
def tiles() -> dict[str, np.ndarray]:
    """Every shipped ground tile, by sprite name.

    Returns
    -------
    dict
        ``name -> (16, 16, 4)`` uint8 RGBA. Empty when the art is not present
        or cannot be decoded, in which case the caller falls back to the
        authored string art and the world still draws.
    """
    if not (STRIP.is_file() and INDEX.is_file()):
        return {}
    try:
        meta = json.loads(INDEX.read_text(encoding="utf-8"))
        image = _decode(STRIP)
    except Exception:
        # A missing or broken art pack is a degraded look, never a broken
        # game. The authored tiles are still there.
        return {}
    if image is None:
        return {}

    size = int(meta.get("size", 16))
    names = list(meta.get("names", ()))
    if image.shape[0] != size or image.shape[1] < size * len(names):
        return {}
    return {name: image[:, index * size:(index + 1) * size].copy()
            for index, name in enumerate(names)}


def _decode(path: pathlib.Path) -> np.ndarray | None:
    """Read a PNG into an RGBA array.

    Parameters
    ----------
    path : pathlib.Path
        The image.

    Returns
    -------
    numpy.ndarray or None
        ``(h, w, 4)`` uint8, or ``None`` when Qt is unavailable or the file
        will not decode.
    """
    try:
        from qtpy import QtGui
    except Exception:
        return None
    image = QtGui.QImage(str(path))
    if image.isNull():
        return None
    image = image.convertToFormat(QtGui.QImage.Format_RGBA8888)
    height, stride = image.height(), image.bytesPerLine()
    raw = np.frombuffer(image.constBits().asstring(stride * height), np.uint8)
    return raw.reshape(height, stride // 4, 4)[:, : image.width()].copy()


def names() -> tuple[str, ...]:
    """Which sprites the shipped art covers.

    Returns
    -------
    tuple of str
        Sprite names, empty when no art is present.
    """
    return tuple(tiles())
