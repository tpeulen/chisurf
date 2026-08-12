"""Cut buildings and the big tree canopy out of the CC0 reference pack.

Companion to :mod:`build_tools.dev_utils.import_tileart`, for sprites that do
**not** fit its contract: a building or a real tree canopy is not a flat,
seamlessly-tileable, one-cell fill, it is a whole shaped object several tiles
wide and tall. :func:`~...gui.pixelart.build_atlas` packs each one at its own
native size rather than forcing it into a 16x16 cell, and
:meth:`~...gui.overworld.OverworldGame._building` draws it anchored so its
*base* sits on the tile it was placed on, growing upward and outward from
there -- which is what makes a 16-bit town read as buildings standing on the
ground rather than static markers sitting in it.

Same source as the ground: **Ninja Adventure** by Pixel-boy and AAA, CC0 (see
``art/CREDITS.md``). Unlike :mod:`.import_tileart`'s ``TILES``, a bounding box
here is a rectangle chosen by eye against the sheet, not measured -- there is
no equivalent of "opaque, low-variance, seamless" for a house.

Run with the project environment on the path::

    PYTHONPATH=. python -m build_tools.dev_utils.import_bigart
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

#: Where the CC0 checkout lives. Gitignored, hence the import-once design.
SOURCE = pathlib.Path("junk/NinjaAdventure/content/map/tileset_village_abandoned.png")

#: Where the cut sprites are shipped.
TARGET = pathlib.Path("chisurf/plugins/misc/games/lumis_quest/gui/art")

#: Tile size, in pixels -- the same grid :mod:`.import_tileart` cuts against,
#: so a sprite's pixel size divided by this is its size in tiles.
SIZE = 16

#: Sprite name -> ``(x0, y0, x1, y1)`` in the sheet. Picked by eye, tile-
#: aligned, and cropped tight enough that neighbouring objects on the sheet
#: (it packs its buildings close, some touching) do not bleed into the box.
RECTS: dict[str, tuple[int, int, int, int]] = {
    # A domed, cave-mouthed hut with a ladder up its back -- the smallest of
    # the three, and the one closest to what a lone woodland dwelling wants
    # to look like.
    "house_hut": (0, 0, 64, 48),
    # A tall timber barn with two lit windows and a door -- the tallest, for
    # a settlement's more prosperous addresses.
    "house_barn": (192, 96, 240, 176),
    # The three-lobed canopy that made the ground's tree look like a
    # placeholder next to it. Two variants sit on the sheet (autumn above,
    # green below); the green one matches this world's palette.
    "big_tree": (0, 144, 64, 192),
}


def _load(path: pathlib.Path) -> np.ndarray:
    """Read a PNG as RGBA.

    Parameters
    ----------
    path : pathlib.Path
        The image.

    Returns
    -------
    numpy.ndarray
        ``(h, w, 4)`` uint8.
    """
    from qtpy import QtGui
    from qtpy.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    image = QtGui.QImage(str(path)).convertToFormat(QtGui.QImage.Format_RGBA8888)
    if image.isNull():
        raise SystemExit(f"cannot read {path}")
    height, stride = image.height(), image.bytesPerLine()
    raw = np.frombuffer(image.constBits().asstring(stride * height), np.uint8)
    return raw.reshape(height, stride // 4, 4)[:, : image.width()].copy()


def _save(path: pathlib.Path, image: np.ndarray) -> None:
    """Write an RGBA array as a PNG.

    Parameters
    ----------
    path : pathlib.Path
        Where to write.
    image : numpy.ndarray
        ``(h, w, 4)`` uint8.
    """
    from qtpy import QtGui

    height, width = image.shape[:2]
    tight = np.ascontiguousarray(image, dtype=np.uint8)
    out = QtGui.QImage(tight.tobytes(), width, height, width * 4,
                       QtGui.QImage.Format_RGBA8888)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not out.copy().save(str(path)):
        raise SystemExit(f"cannot write {path}")


def build() -> None:
    """Cut every rect in :data:`RECTS` into one shipped strip and its index."""
    sheet = _load(SOURCE)
    names = sorted(RECTS)
    crops = {}
    for name in names:
        x0, y0, x1, y1 = RECTS[name]
        w, h = x1 - x0, y1 - y0
        if w % SIZE or h % SIZE:
            raise SystemExit(f"{name}: {w}x{h} is not a whole number of tiles")
        crop = sheet[y0:y1, x0:x1]
        if crop.shape[:2] != (h, w):
            raise SystemExit(f"{name}: rect runs off the sheet")
        crops[name] = crop

    atlas_h = max(crop.shape[0] for crop in crops.values())
    total_w = sum(crop.shape[1] for crop in crops.values())
    strip = np.zeros((atlas_h, total_w, 4), dtype=np.uint8)
    sizes: dict[str, list[int]] = {}
    x = 0
    for name in names:
        crop = crops[name]
        h, w = crop.shape[:2]
        strip[0:h, x:x + w] = crop
        sizes[name] = [w, h]
        x += w

    _save(TARGET / "bigart.png", strip)
    (TARGET / "bigart.json").write_text(
        json.dumps({"names": names, "sizes": sizes,
                    "source": {name: list(RECTS[name]) for name in names}},
                   indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(names)} big sprites to {TARGET/'bigart.png'}")


def main(argv: list[str]) -> int:
    """Command line.

    Parameters
    ----------
    argv : list of str
        Arguments after the program name (unused; kept for symmetry with
        :mod:`.import_tileart`).

    Returns
    -------
    int
        Process status.
    """
    del argv
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
