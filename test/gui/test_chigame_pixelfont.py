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


#: Capitals sit on rows 1-8, so anything below row 8 is a descender.
BASELINE = 8


def test_the_letters_that_descend_do_descend():
    """The rows below the baseline exist for exactly these five.

    A 5x7 body had nowhere to put them and they ended up tucked onto the
    baseline, which is one of the things that made the old face read as four-bit.
    """
    descenders = [char for char in "abcdefghijklmnopqrstuvwxyz"
                  if pixelfont.bitmap(char)[BASELINE + 1:].any()]
    assert set(descenders) == set("gjpqy")


def test_capitals_stay_out_of_the_descender_rows():
    """Otherwise a line of capitals sits lower than a line of text."""
    for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        assert not pixelfont.bitmap(char)[BASELINE + 1:].any(), char


def test_the_face_is_proportional():
    """An ``i`` must not take an ``m``'s room.

    Monospace is the loudest tell of a font that was not designed, and it is
    what the old face was: every glyph in a cell the width of an M.
    """
    table = pixelfont.metrics()
    assert table["i"][2] < table["m"][2]
    assert table["."][2] < table["W"][2]


def test_every_advance_is_its_ink_plus_the_gap():
    """The widths are measured from the art, not declared beside it.

    A hand-maintained width table goes wrong the first time somebody nudges a
    stem, and goes wrong silently.
    """
    for char, (_, ink, advance) in pixelfont.metrics().items():
        assert advance == ink + pixelfont.GAP, char


def test_the_atlas_is_the_ink_and_nothing_else():
    """Trimmed cells are what make the face proportional at draw time."""
    grid = pixelfont.atlas(scale=2)
    total = sum(pixelfont.extent(char)[1] for char in pixelfont.CHARSET)
    assert grid.shape == (pixelfont.HEIGHT * 2, total * 2)
    assert set(np.unique(grid)) <= {0, 255}


def test_an_unknown_character_is_visible_rather_than_absent():
    """A missing character that renders as a space is one nobody reports."""
    assert pixelfont.bitmap("é").any()
