"""Shipped sprites bigger than one tile, and how they get into the atlas.

:mod:`.tileart` ships ground and ground-cover props, all exactly
``SIZE x SIZE`` -- the fast tile-grid batch draws every cell at one uniform
size, so its sprites have to be uniform too. A building is not drawn through
that batch (:meth:`~.overworld.OverworldGame._building` draws it as its own
oversized quad, anchored so its base sits on the tile), so it has no such
constraint -- and a real building sprite is not square: a five-tile-tall house
forced into a one-tile cell is either cropped to nothing or squashed flat.

This module is the sibling of :mod:`.tileart` for exactly that case: sprites
that keep their own native width and height rather than being resampled to
fit a grid cell. ``art/bigart.png`` is a single strip, sprites packed left to
right and top-aligned; ``art/bigart.json`` records each one's pixel size, so
the atlas (:func:`~.pixelart.build_atlas`) can place it without assuming every
entry is the same height the way :mod:`.tileart`'s entries are.

Cut and shipped by :mod:`build_tools.dev_utils.import_bigart`, for the same
reason :mod:`.tileart`'s art is cut and shipped rather than read from
``junk/`` at run time: that checkout is gitignored, so a build that depends on
it works on one machine and nowhere else.
"""

from __future__ import annotations

import functools
import json
import pathlib

import numpy as np

#: Where the cut sprites are shipped, beside :mod:`.tileart`'s.
ART = pathlib.Path(__file__).resolve().parent / "art"

STRIP = ART / "bigart.png"
INDEX = ART / "bigart.json"


@functools.lru_cache(maxsize=1)
def tiles() -> dict[str, np.ndarray]:
    """Every shipped big sprite, by name, at its own native size.

    Returns
    -------
    dict
        ``name -> (h, w, 4)`` uint8 RGBA. Empty when the art is not present or
        cannot be decoded, in which case callers fall back to whatever they
        draw when a name is not shipped -- a missing art pack degrades the
        look, it never blanks the world.
    """
    if not (STRIP.is_file() and INDEX.is_file()):
        return {}
    try:
        meta = json.loads(INDEX.read_text(encoding="utf-8"))
        image = _decode(STRIP)
    except Exception:
        return {}
    if image is None:
        return {}

    sizes = meta.get("sizes", {})
    out: dict[str, np.ndarray] = {}
    x = 0
    for name in meta.get("names", ()):
        w, h = sizes.get(name, (0, 0))
        if w <= 0 or h <= 0 or x + w > image.shape[1] or h > image.shape[0]:
            return {}
        out[name] = image[0:h, x:x + w].copy()
        x += w
    return out


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
    """Which sprites the shipped big art covers.

    Returns
    -------
    tuple of str
        Sprite names, empty when no art is present.
    """
    return tuple(tiles())
