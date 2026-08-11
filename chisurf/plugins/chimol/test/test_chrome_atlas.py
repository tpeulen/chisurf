"""The baked glyph atlas is complete, and no glyph spills into its neighbour.

The atlas is a committed build artefact, so it is the kind of thing that goes
wrong once and stays wrong: a missing glyph draws as a blank box, and a glyph
whose ink crosses its cell boundary makes the *neighbouring* character grow a
sliver of something else along one edge. Neither raises, and both are the sort
of defect that a screenshot at 10 pt does not obviously show.

Both were real. Baking with the cell sized to the font's advance left the bold
``#`` and ``─`` touching their borders -- a monospaced font's advance bounds its
*spacing*, not its ink, and ``─`` is a box-drawing character deliberately drawn
to join the one beside it. The padding is measured from both faces' ink now, and
this is what says it stayed measured.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

#: The committed atlas.
_ATLAS = (
    pathlib.Path(__file__).resolve().parents[1]
    / "chimol" / "renderer" / "ui" / "atlas"
)


def _load():
    """Return ``(alpha, metrics)`` for the committed atlas.

    Returns
    -------
    tuple
        ``(numpy.ndarray, dict)`` -- the alpha channel and ``chrome.json``.
    """
    Image = pytest.importorskip("PIL.Image", reason="Pillow reads the atlas")
    png, meta = _ATLAS / "chrome.png", _ATLAS / "chrome.json"
    if not png.exists() or not meta.exists():
        pytest.skip("no baked atlas; run build_tools.bake_chrome_atlas")
    alpha = np.array(Image.open(png).convert("RGBA"))[..., 3]
    return alpha, json.loads(meta.read_text(encoding="utf-8"))


def test_both_faces_carry_every_character():
    """Regular and bold each hold the whole charset."""
    _alpha, meta = _load()
    assert set(meta["glyphs"]) == {"regular", "bold"}
    for face, table in meta["glyphs"].items():
        missing = [c for c in meta["charset"] if c not in table]
        assert not missing, f"{face} is missing {missing!r}"


def test_no_glyph_baked_blank():
    """Every character except the space has ink.

    Catches a font that lacks a symbol and silently substitutes nothing --
    which at runtime is an empty box where a menu marker should be.
    """
    alpha, meta = _load()
    blank = [
        (face, char)
        for face, table in meta["glyphs"].items()
        for char, (x, y, w, h, _adv) in table.items()
        if char != " " and alpha[y:y + h, x:x + w].max() == 0
    ]
    assert not blank, f"these glyphs baked blank: {blank}"


def test_no_glyph_touches_its_cell_border():
    """Ink stays inside its cell, so a quad cannot sample its neighbour."""
    alpha, meta = _load()
    spills = []
    for face, table in meta["glyphs"].items():
        for char, (x, y, w, h, _adv) in table.items():
            cell = alpha[y:y + h, x:x + w]
            border = np.concatenate(
                [cell[0, :], cell[-1, :], cell[:, 0], cell[:, -1]]
            )
            if border.max() > 0:
                spills.append((face, char, int(border.max())))
    assert not spills, (
        "ink on the cell border -- raise the padding: " + repr(spills[:8])
    )


def test_the_bold_face_is_actually_bolder():
    """Bold carries measurably more ink than regular, at the same advance.

    Worth asserting because it cannot be seen: Menlo is monospaced, so the bold
    face has the *same* advance and, at a glance in an atlas, looks like the
    regular one. A ``setBold`` that silently failed would leave menu titles
    indistinguishable from their items, and nothing else would complain.
    """
    alpha, meta = _load()
    regular, bold = meta["glyphs"]["regular"], meta["glyphs"]["bold"]
    for char in "AWio":
        rx, ry, rw, rh, _ = regular[char]
        bx, by, bw, bh, _ = bold[char]
        light = float(alpha[ry:ry + rh, rx:rx + rw].sum())
        heavy = float(alpha[by:by + bh, bx:bx + bw].sum())
        assert heavy > light * 1.05, (
            f"the bold {char!r} carries {heavy / light:.3f}x the ink of the "
            "regular one; the bold face did not resolve"
        )


def test_the_charset_covers_what_the_chrome_draws():
    """Every non-ASCII character in the panel's source is in the atlas.

    The panel's symbols are literals scattered through its paint methods --
    ``▾`` for an open group, ``▸`` for a submenu, ``▴`` for a scroll mark, the
    transport's ``◀ ■ ▶ ▼``. Adding one and forgetting the atlas is a blank box
    at runtime, so the source is the authority and this is the check.
    """
    _alpha, meta = _load()
    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "chimol" / "renderer" / "internal_gui.py"
    ).read_text(encoding="utf-8")
    used = {c for c in source if ord(c) > 127}
    assert used <= set(meta["charset"]), (
        "these characters are drawn but not baked: "
        f"{sorted(used - set(meta['charset']))}"
    )
