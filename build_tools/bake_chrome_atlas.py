"""Bake ChiMOL's chrome font into a glyph atlas.

Why an atlas at all
-------------------
The in-viewport chrome -- the object panel, the sequence strip, the menus, the
mouse-mode block -- is moving off ``QPainter`` and onto GPU quads, because
rasterising it on the CPU costs `9.6 ms of a 21 ms frame` and forces a staleness
timer to hide the cost. Quads can draw rectangles without help; text needs
glyphs, and a glyph is a textured quad. So the font is rasterised **once, at
build time**, into one image with a table of where each character sits.

That is also what makes the chrome run where Qt does not. Baking needs a font
engine; *drawing* needs a texture and a lookup, which any target has.

What is baked
-------------
``QFont("Menlo")`` at :data:`FONT_PT`, in a regular and a **bold** face -- the
bold has exactly one caller, a menu's title row, and a face that is not baked is
a face that silently renders as the regular one.

The character set is printable ASCII plus the seven symbols the chrome actually
uses: ``▾ ▸ ▴`` for menus and disclosure markers, ``─`` for separators, and
``◀ ■ ▶ ▼`` for the movie transport. Enumerated rather than "some Unicode
range", because an atlas is a fixed-size image and a missing glyph is an empty
box at runtime rather than an error at build time.

Supersampling
-------------
Baked at :data:`SCALE`× the point size and sampled down, rather than once per
device pixel ratio. A 1× atlas is visibly soft on a HiDPI screen and a per-ratio
atlas means baking on a machine that has the ratio you are baking for -- which
CI does not. The cost is one image, and text metrics still come from the atlas
so layout does not depend on the scale.

Use
---
    QT_QPA_PLATFORM=offscreen python -m build_tools.bake_chrome_atlas

writes ``chisurf/plugins/chimol/chimol/renderer/ui/atlas/chrome.png`` and
``chrome.json``. Both ship: ``pyproject.toml``'s package data already covers
``*.png`` and ``*.json``.
"""
from __future__ import annotations

import json
import pathlib
import string

__all__ = ["CHARSET", "FONT_PT", "SCALE", "OUT_DIR", "bake"]

#: Point size of the chrome font. Mirrors ``InternalGui.FONT_PT``; a mismatch
#: shows up as text that does not fit the rows it is laid out into.
FONT_PT = 10

#: Supersampling factor. See the module docstring.
SCALE = 4

#: Extra blank texels added to whatever the ink actually overhangs by.
#:
#: The padding itself is **measured**, not chosen -- see :func:`_padding`. This
#: is only the antialiasing margin on top of it, because a tight bounding box
#: describes the glyph's outline and the rasteriser puts partial coverage just
#: outside it.
AA_MARGIN = 2

#: Every character the chrome can draw.
#:
#: Printable ASCII, then the seven symbols in use:
#: ``▾`` menu marker, ``▸`` submenu marker, ``▴`` scroll-up mark, ``─``
#: separator, and ``◀ ■ ▶ ▼`` from ``MOVIE_BUTTONS``.
CHARSET: str = (
    "".join(sorted(set(string.printable[:95])))
    + "─▴▸▾◀■▶▼"
)

#: Where the atlas lands, inside the package so it ships.
OUT_DIR = (
    pathlib.Path(__file__).resolve().parents[1]
    / "chisurf" / "plugins" / "chimol" / "chimol" / "renderer" / "ui" / "atlas"
)


def _face(bold: bool):
    """Return the chrome font, at :data:`SCALE`× size.

    Parameters
    ----------
    bold : bool
        Whether to return the bold face.

    Returns
    -------
    QtGui.QFont
    """
    from qtpy import QtGui

    font = QtGui.QFont("Menlo")
    font.setStyleHint(QtGui.QFont.Monospace)
    font.setPointSize(FONT_PT * SCALE)
    font.setBold(bold)
    return font


def _padding(metrics: dict, advance: int) -> int:
    """Return the blank margin each cell needs, in texels.

    Parameters
    ----------
    metrics : dict
        ``{face name: QFontMetrics}``.
    advance : int
        The monospaced advance every cell is sized from.

    Returns
    -------
    int
        Half-width of the blank border, including :data:`AA_MARGIN`.

    Notes
    -----
    A monospaced font's *ink* is not bounded by its advance. ``─`` -- the
    separator -- starts a texel to the **left** of the pen and ends past it,
    because a box-drawing character is meant to join the one beside it; ``#``
    overhangs too, and both overhang further in the bold face than the regular
    one. Packed flush, that ink lands in the neighbouring cell, and at runtime
    a glyph quad samples a sliver of the wrong glyph along its edge.

    Measured across **both** faces rather than assumed, because sizing the
    padding from the regular face is exactly the mistake that left bold ``#``
    and ``─`` still touching their borders.
    """
    overhang = 0
    for face_metrics in metrics.values():
        for char in CHARSET:
            ink = face_metrics.tightBoundingRect(char)
            overhang = max(overhang, -ink.x(), ink.x() + ink.width() - advance)
    return int(max(overhang, 0)) + AA_MARGIN


def bake(out_dir: pathlib.Path | None = None) -> dict:
    """Rasterise both faces into one atlas and write it out.

    Parameters
    ----------
    out_dir : pathlib.Path, optional
        Where to write. Defaults to :data:`OUT_DIR`.

    Returns
    -------
    dict
        The metrics written as ``chrome.json``: ``scale``, ``font_pt``,
        ``cell``, ``glyphs`` (per face, per character, its cell and advance)
        and the shared ``ascent`` / ``descent`` / ``line_height``.

    Notes
    -----
    A fixed grid rather than a tight pack. There are fewer than 210 cells and
    the font is monospaced, so the wasted texels are not worth a packer -- and a
    grid means a glyph's cell can be computed from its index, which keeps the
    runtime lookup a multiply rather than a table read.
    """
    from qtpy import QtCore, QtGui, QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    assert app is not None  # a collected QApplication aborts the next QImage

    out_dir = pathlib.Path(out_dir or OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    faces = {"regular": _face(False), "bold": _face(True)}
    metrics = {name: QtGui.QFontMetrics(font) for name, font in faces.items()}

    # One cell size for every glyph of both faces: the widest advance and the
    # tallest line. Bold is a little wider than regular, so taking the max of
    # the two is what stops a bold glyph being clipped by a cell sized for the
    # regular face.
    advance = max(
        max(m.horizontalAdvance(c) for c in CHARSET) for m in metrics.values()
    )
    pad = _padding(metrics, advance)
    cell_w = advance + 2 * pad
    cell_h = max(m.height() for m in metrics.values()) + 2 * pad
    ascent = max(m.ascent() for m in metrics.values())

    columns = 16
    rows_per_face = (len(CHARSET) + columns - 1) // columns
    total_rows = rows_per_face * len(faces)

    image = QtGui.QImage(
        cell_w * columns, cell_h * total_rows, QtGui.QImage.Format_ARGB32
    )
    image.fill(QtCore.Qt.transparent)

    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
    painter.setPen(QtGui.QColor(255, 255, 255, 255))

    glyphs: dict[str, dict] = {}
    try:
        for face_index, (name, font) in enumerate(faces.items()):
            painter.setFont(font)
            face_metrics = metrics[name]
            row_offset = face_index * rows_per_face
            table: dict[str, list] = {}
            for index, char in enumerate(CHARSET):
                column, row = index % columns, index // columns
                x = column * cell_w
                y = (row_offset + row) * cell_h
                # The pen sits at (pad, pad + ascent) inside the cell, the same
                # for every glyph -- so a caller places a quad at
                # ``(pen_x - pad, baseline - ascent - pad)`` with the cell's
                # size, and needs no per-glyph bearing.
                painter.drawText(x + pad, y + pad + ascent, char)
                table[char] = [x, y, cell_w, cell_h,
                               face_metrics.horizontalAdvance(char)]
            glyphs[name] = table
    finally:
        painter.end()

    image.save(str(out_dir / "chrome.png"))

    record = {
        "font_pt": FONT_PT,
        "scale": SCALE,
        "pad": pad,
        "cell": [cell_w, cell_h],
        "advance": advance,
        "ascent": ascent,
        "descent": max(m.descent() for m in metrics.values()),
        "line_height": cell_h,
        "columns": columns,
        "charset": CHARSET,
        "glyphs": glyphs,
    }
    (out_dir / "chrome.json").write_text(
        json.dumps(record, indent=1, sort_keys=True), encoding="utf-8"
    )
    return record


if __name__ == "__main__":  # pragma: no cover - a build step
    _record = bake()
    print(
        f"{len(CHARSET)} glyphs x {len(_record['glyphs'])} faces, "
        f"cell {_record['cell'][0]}x{_record['cell'][1]} at {SCALE}x -> {OUT_DIR}"
    )
