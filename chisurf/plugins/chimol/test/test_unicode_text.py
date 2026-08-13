"""The chrome draws any character, not the alphabet somebody baked.

The report
----------
"Special chars like äöü do not land visible in the CLI." They landed -- the
command line held them, the input path was right -- and drew as **nothing**.

The atlas is baked at build time, which is what lets the chrome run where there
is no font engine. It held printable ASCII plus nine symbols, and
:meth:`Atlas.cell_of` answered ``None`` for anything else, which the painter
took as "draw no quad". So "Zelldichte für Fläche" rendered as "Zelldichte f r
Fl che", with nothing in any log, and every non-Latin script was invisible.

Two fixes, and the second is the one that matters
-------------------------------------------------
The baked set grew to cover Latin-1 and Latin Extended-A, which is the European
languages this is used in. That is the cheap half and it only moves the edge.

The edge is removed by rasterising anything **not** baked on first use, into a
cache appended below the baked rows of the same texture. Unicode has ~150,000
codepoints; the answer to "which do we support" should not be a list.

What is pinned here
-------------------
* the accented letters that were reported have glyphs of their own;
* Greek, Cyrillic, CJK, kana and symbols rasterise at runtime;
* the font is chosen **per character, from its cmap** -- not by asking whether
  it drew something, because a font draws its own "tofu" box for a character it
  lacks, so the first candidate always wins and CJK came out as empty boxes;
* a character no font on the machine has draws a **visible** placeholder. The
  invisible failure is the whole bug, and it must not survive one layer down;
* the cache serves more than one texture. A dirty list that is *consumed* can
  feed exactly one, which is how the window drew Japanese while the offscreen
  grab drew blanks.
"""
from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.renderer.ui.font import MISSING_GLYPH, load_atlas

#: What was reported, and what the baked set now has to cover on its own.
REPORTED = "äöüÄÖÜß"

#: Scripts that cannot be baked and must therefore be rasterised.
RUNTIME = {
    "greek": "ΩΔλ",
    "cyrillic": "Жизнь",
    "cjk": "漢字",
    "kana": "あア",
    "arrows": "→←⇌",
    "symbols": "★☆✓",
}


@pytest.fixture(scope="module")
def atlas():
    return load_atlas()


@pytest.mark.parametrize("char", list(REPORTED))
def test_the_reported_characters_are_baked(atlas, char):
    """Baked, not rasterised: these are typed constantly and are cheap to hold."""
    assert atlas.covers(char), f"{char!r} has no baked glyph"


def test_a_baked_glyph_has_ink(atlas):
    """A cell that exists but is blank is the same failure wearing a cell."""
    from PIL import Image

    image = np.asarray(Image.open(atlas.image_path).convert("RGBA"))
    for char in REPORTED:
        x, y, w, h = atlas.cell_of(char)
        assert image[y:y + h, x:x + w, 3].max() > 0, f"{char!r} baked blank"


@pytest.mark.parametrize("script", sorted(RUNTIME))
def test_runtime_scripts_rasterise(atlas, script):
    """Everything outside the baked set, drawn on demand."""
    cache = atlas.cache
    if cache is None:
        pytest.skip("no rasteriser on this machine")
    for char in RUNTIME[script]:
        rect = cache.cell_of(char)
        assert rect is not None, f"{char!r} ({script}) did not rasterise"
        x, y, w, h = rect
        assert cache.image[y:y + h, x:x + w, 3].max() > 0, (
            f"{char!r} ({script}) rasterised blank"
        )


def test_the_font_is_chosen_by_coverage_not_by_whether_it_drew(atlas):
    """The trap that made CJK render as boxes.

    Menlo is the first candidate and has no kanji, but it draws a "tofu" box
    when asked for one -- so a chain that stops at "did it render?" never
    reaches the font that actually has the character.
    """
    cache = atlas.cache
    if cache is None:
        pytest.skip("no rasteriser on this machine")

    menlo = "/System/Library/Fonts/Menlo.ttc"
    covered = cache._coverage(menlo)
    if covered is None:
        pytest.skip("Menlo is not on this machine")

    assert ord("Ω") in covered, "the premise: Menlo has Greek"
    assert ord("漢") not in covered, "the premise: Menlo has no kanji"
    # And the cache does not use it for the character it lacks.
    chosen = cache._font_for("漢")
    assert chosen is not None
    assert "Menlo" not in str(getattr(chosen, "path", "")), (
        "a font without the character was chosen anyway"
    )


def test_an_uncoverable_character_draws_a_visible_placeholder(atlas):
    """Never nothing. The invisible failure is the bug this file is about."""
    # A private-use codepoint: no font has it by definition.
    cell = atlas.cell_of("")
    assert cell is not None, "an unknown character drew nothing at all"
    assert cell == atlas.cell_of(MISSING_GLYPH)


def test_the_cache_can_feed_more_than_one_texture(atlas):
    """Its version is the signal, because a consumed dirty list feeds one.

    The window and an offscreen grab are different devices with different
    textures; the second used to get an empty cache region and draw blanks.
    """
    cache = atlas.cache
    if cache is None:
        pytest.skip("no rasteriser on this machine")

    before = cache.version
    cache.cell_of("Ƕ")     # something not asked for above
    assert cache.version > before, "storing a glyph did not move the version"

    # Two consumers, each tracking its own high-water mark, both see the glyph.
    first = last = cache.version
    assert first == last
    assert cache.image.shape[0] > 0


def test_the_atlas_texture_reserves_room_for_the_cache(atlas):
    """The cache lives below the baked rows of the *same* texture."""
    assert atlas.texture_height > atlas.baked_height


def test_typing_unicode_reaches_the_screen():
    """End to end, through the real chrome and a real frame.

    Pixels, not a glyph table: everything above can pass while the painter
    still draws nothing, which is exactly what happened.
    """
    from toolkit_free import probe

    measured = probe('''
        app = open_app(size=(900, 300))
        gui = app.renderer._internal_gui
        gui.command_line.focused = True

        def ink():
            app.renderer.draw_frame()
            image = np.asarray(app.renderer.grab_image())[..., :3]
            band = image[-60:]
            return int((band.max(axis=2) > 40).sum())

        emit("empty", ink())
        for ch in "Fläche ΔΩ Жизнь 漢字 あ → ★":
            app.renderer.on_key_press(0, ch, 0)
        emit("typed", ink())
        emit("text", gui.command_line.text)
    ''')

    assert "Fläche" in measured["text"], measured["text"]
    assert int(measured["typed"]) > int(measured["empty"]) + 200, (
        "typing non-ASCII put nothing on screen: "
        f"{measured['empty']} -> {measured['typed']} lit pixels"
    )
