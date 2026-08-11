"""The face is in the tree, and it has to stay legible."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.gui.chigame import pixelfont


def test_every_glyph_is_the_shape_it_claims_to_be():
    """A short row silently blanks a column.

    The letter then looks *nearly* right, which is the kind of thing nobody
    spots in a screenshot and everybody feels.
    """
    assert pixelfont.validate() == []


def test_the_table_covers_every_printable_character():
    """A hole here renders as the missing-character box, mid-sentence."""
    missing = [char for char in pixelfont.CHARSET if char not in pixelfont.GLYPHS]
    assert missing == []


def test_nothing_but_space_is_blank():
    """An all-dots typo is an invisible letter, and invisible letters are
    words with holes in them."""
    blank = [char for char in pixelfont.CHARSET
             if char != " " and not pixelfont.bitmap(char).any()]
    assert blank == []


@pytest.mark.parametrize("pair", [
    ("0", "O"), ("1", "l"), ("1", "I"), ("l", "I"), ("5", "S"), ("2", "Z"),
    ("8", "B"), ("6", "G"), ("c", "e"), ("u", "v"), ("m", "n"), ("h", "b"),
])
def test_the_characters_people_confuse_are_distinct(pair):
    """Five columns is a tight grid, and this is where it gets tight.

    A page address is full of ``1``, ``l`` and ``I``, and a wavelength is full
    of ``0`` and ``O``. If any of these collide the font is unusable for the
    one job this game has for it.
    """
    first, second = pair
    assert not np.array_equal(pixelfont.bitmap(first), pixelfont.bitmap(second))


def test_no_two_glyphs_are_the_same_drawing():
    """Catches the copy-paste that leaves ``q`` looking like ``g``."""
    seen: dict[bytes, str] = {}
    clashes = []
    for char in pixelfont.CHARSET:
        if char == " ":
            continue
        key = pixelfont.bitmap(char).tobytes()
        if key in seen:
            clashes.append((seen[key], char))
        seen[key] = char
    assert clashes == []


def test_the_letters_that_descend_do_descend():
    """Row seven exists for exactly these five, and for nothing else."""
    descenders = [char for char in "abcdefghijklmnopqrstuvwxyz"
                  if pixelfont.bitmap(char)[pixelfont.HEIGHT - 1].any()]
    assert set(descenders) == set("gjpqy")


def test_capitals_stay_out_of_the_descender_row():
    """Otherwise a line of capitals sits a pixel lower than a line of text."""
    for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        assert not pixelfont.bitmap(char)[pixelfont.HEIGHT - 1].any(), char


def test_the_advance_is_wider_than_the_glyph():
    """The gap between letters is part of the face.

    Conflating the advance with the glyph box is what produced ``s e t t l e d``
    -- narrow letters centred in cells the width of an M.
    """
    assert pixelfont.ADVANCE > pixelfont.WIDTH
    assert pixelfont.ADVANCE - pixelfont.WIDTH == pixelfont.GAP


def test_the_atlas_is_one_row_of_boxes():
    """Layout arithmetic downstream assumes exactly this shape."""
    grid = pixelfont.atlas(scale=2)
    assert grid.shape == (pixelfont.HEIGHT * 2,
                          pixelfont.WIDTH * 2 * len(pixelfont.CHARSET))
    assert set(np.unique(grid)) <= {0, 255}


def test_an_unknown_character_is_visible_rather_than_absent():
    """A missing character that renders as a space is one nobody reports."""
    assert pixelfont.bitmap("é").any()
