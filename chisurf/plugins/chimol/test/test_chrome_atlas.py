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

import ast
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
    # Whitespace, not just U+0020: the charset covers Latin-1, which brings the
    # no-break space with it. A space with ink would be the bug.
    blank = [
        (face, char)
        for face, table in meta["glyphs"].items()
        for char, (x, y, w, h, _adv) in table.items()
        if not char.isspace() and alpha[y:y + h, x:x + w].max() == 0
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
    """Every non-ASCII character in the panel's *string literals* is in the atlas.

    The panel's symbols are literals scattered through its paint methods --
    ``▾`` for an open group, ``▸`` for a submenu, ``▴`` for a scroll mark, the
    transport's ``◀ ■ ▶ ▼``. Adding one and forgetting the atlas is a blank box
    at runtime, so the source is the authority and this is the check.

    Literals, not the raw file. This test read every character of the source
    and so counted **comments and docstrings** as things the chrome draws. That
    is not a hypothetical: the window close button was moved from ``×`` to
    ``x`` precisely *because* the atlas has no multiplication sign, and the
    comment recording why -- which names the glyph in order to warn about it --
    then failed this test on its own. A check that fires on the note explaining
    the fix punishes writing the note down.

    Docstrings are excluded for the same reason and are not a loss: a docstring
    is not passed to :meth:`Painter.text`.
    """
    _alpha, meta = _load()
    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "chimol" / "renderer" / "internal_gui.py"
    ).read_text(encoding="utf-8")

    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    used = {
        char
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        for char in node.value
        if ord(char) > 127
    }
    assert used <= set(meta["charset"]), (
        "these characters are drawn but not baked: "
        f"{sorted(used - set(meta['charset']))}"
    )


#: Every module of painter-level controls. The atlas is what the **GPU**
#: painter draws from, so this list is the set of files whose string literals
#: can reach it.
_CONTROL_MODULES = sorted(
    p.name
    for p in (
        pathlib.Path(__file__).resolve().parents[1] / "chimol" / "renderer" / "ui"
    ).glob("*.py")
    if p.name != "__init__.py"
)


@pytest.mark.parametrize("module", _CONTROL_MODULES)
def test_every_control_module_draws_only_baked_glyphs(module):
    """No control draws a character the atlas has no glyph for.

    The same check as above, widened from the panel to every control module --
    and it is not a formality. The Qt painter draws with a **font**, so a
    missing glyph looks perfect there; the GPU painter draws from **this
    atlas**, so the same string comes out as nothing at all. A screenshot
    taken through Qt therefore *cannot* catch this, which is exactly why it
    needs an assertion.

    Four real cases, all found by running this: the ported tab bar drew its
    close button as ``✕`` and its scroll arrows as ``◂``, and the ported table
    drew ``▲`` and ``✓`` -- none of the four baked. The fifth was already
    shipped: ``widgets.Table``'s ascending sort mark was ``▲`` while its
    descending mark was ``▼``, and only ``▼`` is in the atlas, so sorting a
    column ascending in the GPU chrome showed no marker at all while
    descending showed one. That asymmetry had been live and unnoticed.

    The fix is to spell a symbol with a glyph that *is* baked (``▴``/``▾``,
    ``◀``/``▶``, ``■``, or plain ASCII), not to widen the atlas casually --
    every glyph costs texture area that the chrome uploads every repaint.
    """
    _alpha, meta = _load()
    path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "chimol" / "renderer" / "ui" / module
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    used = {
        char
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        for char in node.value
        if ord(char) > 127
    }
    # Word-wrap and text-classification tables hold characters the module
    # *reasons about* rather than draws -- CJK punctuation that must not start
    # a line, for one. Those never reach `Painter.text`, so they are named
    # here rather than being baked into the atlas for nothing.
    used -= set(_NOT_DRAWN.get(module, ""))
    assert used <= set(meta["charset"]), (
        f"{module} draws these but the atlas has no glyph, so they paint as "
        f"nothing on the GPU painter: {sorted(used - set(meta['charset']))}"
    )


#: Per module, characters that appear in a string literal but are classified,
#: not drawn. Keep this as small as it can honestly be: an entry here is a
#: promise that the character never reaches :meth:`Painter.text`.
_NOT_DRAWN = {
    # `_PUNCT_CHARS`, the set a line may break *after* -- the reference's
    # word-wrap rule for CJK, which has no spaces to break on.
    "text.py": "　、。",
}
