"""Cut the shipped terrain tiles out of the CC0 reference pack.

The world's ground was string art in :mod:`~...gui.pixelart` -- three tones and
a scatter of noise per material, authored by hand. It was honest and it was
flat, and next to real 16-bit tile art it reads as a placeholder, which is what
it was.

This imports the ground from **Ninja Adventure** by Pixel-boy and AAA, which is
released **CC0** by its authors (`github.com/pixel-boy/NinjaAdventure`, and the
same pack on itch.io). CC0 is a public-domain dedication: no attribution
required, no licence to propagate, nothing to reconcile with this repository's
GPL. Attribution is given anyway in ``art/CREDITS.md``, because not being
obliged to is not a reason not to.

It is a *script*, run once, rather than a runtime dependency on a checkout under
``junk/`` -- that directory is gitignored, so a build that reads from it works
on one machine and nowhere else. What ships is the cut result and this file,
so the provenance of every pixel is a command anyone can re-run::

    PYTHONPATH=. python -m build_tools.dev_utils.import_tileart

Which cells were chosen was **measured, not eyeballed**: a ground tile has to
be fully opaque, low-variance, and have matching opposite edges or it shows a
seam at every tile boundary. ``--survey`` prints that ranking for a sheet,
which is how the coordinates below were found.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np

#: Where the CC0 checkout lives. Gitignored, hence the import-once design.
SOURCE = pathlib.Path("junk/NinjaAdventure/content/map")

#: Where the cut tiles are shipped.
TARGET = pathlib.Path("chisurf/plugins/misc/games/lumis_quest/gui/art")

#: Tile size, in pixels. The pack is authored at 16, which is also what
#: :data:`...gui.pixelart.SIZE` is, so nothing is resampled.
SIZE = 16

#: Sprite name -> (sheet, column, row). The names are
#: :mod:`~...gui.pixelart`'s, so anything listed here simply replaces the
#: string art of the same name and nothing else has to know.
#:
#: Grass and water each get a second variant because the renderer picks between
#: two by position -- one tile repeated across a field betrays the grid
#: immediately, and that is as true of good art as of bad.
TILES: dict[str, tuple[str, int, int]] = {
    "grass": ("tileset_floor", 2, 12),
    "grass2": ("tileset_floor", 3, 12),
    # No sand2: the renderer only picks a positional variant where a "<name>2"
    # sprite exists, and sand has none. Cutting a tile nothing draws is waste,
    # and the guard in test_pixelart is what said so.
    "sand": ("tileset_floor", 2, 5),
    # Two *interior* water cells, whose ripples fall in different places. The
    # renderer alternates them on a clock, so the pair has to differ in detail
    # and not in kind: pairing a rippled tile with the block's plain fill makes
    # the whole sea blink rather than move -- and a flat fill is exactly what
    # the "terrain is dithered rather than flat" guard exists to catch.
    "water": ("tileset_floor", 5, 22),
    "water2": ("tileset_floor", 6, 23),
    "marsh": ("tileset_floor", 12, 12),
    "road": ("tileset_floor", 13, 19),
    "garden": ("tileset_floor", 15, 12),
    # The made ground -- paving, boards, the recovery pad, and the dark
    # manifold's dead stone -- comes from the interior sheet, because the floor
    # sheet is all *natural* ground and its palest tile is snow. A town square
    # paved in snow was the first thing the screenshot said.
    "plaza": ("tileset_interior_floor", 14, 11),
    "floor": ("tileset_interior_floor", 14, 5),
    "clinic": ("tileset_interior_floor", 11, 4),
    "ash": ("tileset_interior_floor", 12, 13),
    "boards": ("tileset_interior_floor", 1, 13),
    "iwall": ("tileset_interior_floor", 14, 13),
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


def survey(sheet: str, limit: int = 40) -> None:
    """Rank a sheet's cells by how well they would tile.

    This is how :data:`TILES` was chosen. Three things disqualify a cell as
    ground, and only the first is obvious: any transparency at all; a high
    colour spread, which means it is a *feature* rather than a fill; and
    mismatched opposite edges, which is invisible in the sheet and shows up as
    a seam at every tile boundary in the world.

    Parameters
    ----------
    sheet : str
        Sheet stem, e.g. ``tileset_floor``.
    limit : int, optional
        How many to print.
    """
    image = _load(SOURCE / f"{sheet}.png")
    rows, cols = image.shape[0] // SIZE, image.shape[1] // SIZE
    ranked = []
    for row in range(rows):
        for col in range(cols):
            cell = image[row * SIZE:(row + 1) * SIZE, col * SIZE:(col + 1) * SIZE]
            if (cell[..., 3] < 250).any():
                continue
            rgb = cell[..., :3].astype(float)
            spread = float(rgb.reshape(-1, 3).std(axis=0).mean())
            seam = float(abs(rgb[0].mean(0) - rgb[-1].mean(0)).mean()
                         + abs(rgb[:, 0].mean(0) - rgb[:, -1].mean(0)).mean())
            mean = rgb.reshape(-1, 3).mean(axis=0).round().astype(int)
            ranked.append((spread + seam, spread, seam, col, row, tuple(mean)))
    ranked.sort()
    for score, spread, seam, col, row, mean in ranked[:limit]:
        print(f"({col:2d},{row:2d})  {score:6.2f}  spread {spread:5.2f} "
              f"seam {seam:5.2f}  rgb {mean}")


def build() -> None:
    """Cut every tile in :data:`TILES` into one shipped strip and its index."""
    sheets = {name: _load(SOURCE / f"{name}.png")
              for name in {sheet for sheet, _, _ in TILES.values()}}
    names = sorted(TILES)
    strip = np.zeros((SIZE, SIZE * len(names), 4), dtype=np.uint8)
    for index, name in enumerate(names):
        sheet, col, row = TILES[name]
        cell = sheets[sheet][row * SIZE:(row + 1) * SIZE,
                             col * SIZE:(col + 1) * SIZE]
        if cell.shape[:2] != (SIZE, SIZE):
            raise SystemExit(f"{name}: {sheet} has no cell at ({col},{row})")
        strip[:, index * SIZE:(index + 1) * SIZE] = cell

    _save(TARGET / "terrain.png", strip)
    (TARGET / "terrain.json").write_text(
        json.dumps({"size": SIZE, "names": names,
                    "source": {name: list(TILES[name]) for name in names}},
                   indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(names)} tiles to {TARGET/'terrain.png'}")


def main(argv: list[str]) -> int:
    """Command line.

    Parameters
    ----------
    argv : list of str
        Arguments after the program name.

    Returns
    -------
    int
        Process status.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--survey", metavar="SHEET",
                        help="rank a sheet's cells instead of building")
    args = parser.parse_args(argv)
    if args.survey:
        survey(args.survey)
    else:
        build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
