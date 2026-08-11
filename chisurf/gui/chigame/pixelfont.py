"""The typeface, authored as string art.

chigame drew text by rasterising the platform's font through Qt, and the result
was the worst-looking thing in every screenshot. Two reasons, and the first is a
plain bug: ``QFontDatabase.systemFont(FixedFont)`` returns ``.AppleSystemUIFont``
on this platform -- a **proportional** face -- and setting ``setFixedPitch(True)``
afterwards does not change which face was resolved. Every glyph was then drawn
into a fixed cell the width of an ``M``, so an ``i`` floated in the middle of
forty pixels of nothing. That is the spindly, over-spaced look: ``s e t t l e d``.

The second reason is that even fixed correctly it would be wrong. A system UI
font in a 16-bit game reads as a terminal that has been dressed up. The genre's
type is a *bitmap*: 5x7 in an 8-row cell, one pixel per stroke, no
anti-aliasing, no hinting, no opinion about your display.

So the font is authored here, as string art, for exactly the reasons the sprites
and the room maps are (:mod:`~chisurf.plugins.misc.games.lumis_quest.api.interiors`):
it is the only form that survives code review. Somebody can see in a diff that
the ``g`` changed, and see how. And it removes the last thing text needed Qt
for, so a headless render and a windowed one now draw identical glyphs.

The shape follows the 5x7 cell that arcade hardware used, because those
proportions are load-bearing rather than nostalgic: five columns is the
narrowest grid on which ``m``, ``w`` and ``8`` stay distinct, and the eighth row
is what gives ``g``, ``j``, ``p``, ``q`` and ``y`` somewhere to descend to
instead of being squashed onto the baseline.

Licensing note, since this replaced a proposal to ship a real font: nothing here
is anybody else's. It is one file of ``#`` and ``.``.
"""

from __future__ import annotations

import numpy as np

#: Printable ASCII. Enough for scores, menus and villager dialogue.
CHARSET = "".join(chr(code) for code in range(32, 127))

#: Glyph box, in pixels. Five wide is the narrowest grid on which ``m`` and
#: ``w`` stay legible; eight tall is seven of body plus one for descenders.
WIDTH = 5
HEIGHT = 8

#: Columns between one glyph box and the next. One, as the hardware did -- the
#: gap is part of the design rather than a layout parameter, which is why
#: letters in these fonts sit close enough to read as words.
GAP = 1

#: Pixel pitch from one character to the next.
ADVANCE = WIDTH + GAP

#: How many atlas pixels per font pixel. The glyphs are sampled with a nearest
#: filter, so this is not quality -- it is headroom, so that a glyph drawn
#: larger than its cell does not have to be magnified from five pixels across.
SCALE = 4

#: Every glyph, as eight rows of five. ``#`` is ink and ``.`` is paper.
#:
#: Rows 0-6 are the body and row 7 is the descender row: capitals and digits
#: fill rows 0-6, lower case sits on rows 2-6 with ascenders reaching row 0,
#: and the five descending letters use row 7.
GLYPHS: dict[str, str] = {
    " ": "...../...../...../...../...../...../...../.....",
    "!": "..#../..#../..#../..#../..#../...../..#../.....",
    '"': ".#.#./.#.#./...../...../...../...../...../.....",
    "#": ".#.#./.#.#./#####/.#.#./#####/.#.#./.#.#./.....",
    "$": "..#../.####/#.#../.###./..#.#/####./..#../.....",
    "%": "##.../##..#/...#./..#../.#.../#..##/...##/.....",
    "&": ".##../#..#./#..#./.##../#.#.#/#..#./.##.#/.....",
    "'": "..#../..#../...../...../...../...../...../.....",
    "(": "...#./..#../.#.../.#.../.#.../..#../...#./.....",
    ")": ".#.../..#../...#./...#./...#./..#../.#.../.....",
    "*": "...../..#../#.#.#/.###./#.#.#/..#../...../.....",
    "+": "...../..#../..#../#####/..#../..#../...../.....",
    ",": "...../...../...../...../...../..#../..#../.#...",
    "-": "...../...../...../#####/...../...../...../.....",
    ".": "...../...../...../...../...../..#../..#../.....",
    "/": "....#/....#/...#./..#../.#.../#..../#..../.....",
    "0": ".###./#...#/#..##/#.#.#/##..#/#...#/.###./.....",
    "1": "..#../.##../..#../..#../..#../..#../.###./.....",
    "2": ".###./#...#/....#/...#./..#../.#.../#####/.....",
    "3": "#####/...#./..#../...#./....#/#...#/.###./.....",
    "4": "...#./..##./.#.#./#..#./#####/...#./...#./.....",
    "5": "#####/#..../####./....#/....#/#...#/.###./.....",
    "6": "..##./.#.../#..../####./#...#/#...#/.###./.....",
    "7": "#####/....#/...#./..#../.#.../.#.../.#.../.....",
    "8": ".###./#...#/#...#/.###./#...#/#...#/.###./.....",
    "9": ".###./#...#/#...#/.####/....#/...#./.##../.....",
    ":": "...../..#../..#../...../..#../..#../...../.....",
    ";": "...../..#../..#../...../..#../..#../.#.../.....",
    "<": "...#./..#../.#.../#..../.#.../..#../...#./.....",
    "=": "...../...../#####/...../#####/...../...../.....",
    ">": ".#.../..#../...#./....#/...#./..#../.#.../.....",
    "?": ".###./#...#/....#/...#./..#../...../..#../.....",
    "@": ".###./#...#/#.###/#.#.#/#.###/#..../.###./.....",
    "A": ".###./#...#/#...#/#####/#...#/#...#/#...#/.....",
    "B": "####./#...#/#...#/####./#...#/#...#/####./.....",
    "C": ".####/#..../#..../#..../#..../#..../.####/.....",
    "D": "###../#..#./#...#/#...#/#...#/#..#./###../.....",
    "E": "#####/#..../#..../####./#..../#..../#####/.....",
    "F": "#####/#..../#..../####./#..../#..../#..../.....",
    "G": ".####/#..../#..../#.###/#...#/#...#/.####/.....",
    "H": "#...#/#...#/#...#/#####/#...#/#...#/#...#/.....",
    "I": ".###./..#../..#../..#../..#../..#../.###./.....",
    "J": "..###/...#./...#./...#./...#./#..#./.##../.....",
    "K": "#...#/#..#./#.#../##.../#.#../#..#./#...#/.....",
    "L": "#..../#..../#..../#..../#..../#..../#####/.....",
    "M": "#...#/##.##/#.#.#/#.#.#/#...#/#...#/#...#/.....",
    "N": "#...#/#...#/##..#/#.#.#/#..##/#...#/#...#/.....",
    "O": ".###./#...#/#...#/#...#/#...#/#...#/.###./.....",
    "P": "####./#...#/#...#/####./#..../#..../#..../.....",
    "Q": ".###./#...#/#...#/#...#/#.#.#/#..#./.##.#/.....",
    "R": "####./#...#/#...#/####./#.#../#..#./#...#/.....",
    "S": ".####/#..../#..../.###./....#/....#/####./.....",
    "T": "#####/..#../..#../..#../..#../..#../..#../.....",
    "U": "#...#/#...#/#...#/#...#/#...#/#...#/.###./.....",
    "V": "#...#/#...#/#...#/#...#/#...#/.#.#./..#../.....",
    "W": "#...#/#...#/#...#/#.#.#/#.#.#/##.##/#...#/.....",
    "X": "#...#/#...#/.#.#./..#../.#.#./#...#/#...#/.....",
    "Y": "#...#/#...#/#...#/.#.#./..#../..#../..#../.....",
    "Z": "#####/....#/...#./..#../.#.../#..../#####/.....",
    "[": "..###/..#../..#../..#../..#../..#../..###/.....",
    "\\": "#..../#..../.#.../..#../...#./....#/....#/.....",
    "]": "###../..#../..#../..#../..#../..#../###../.....",
    "^": "..#../.#.#./#...#/...../...../...../...../.....",
    "_": "...../...../...../...../...../...../...../#####",
    "`": ".#.../..#../...../...../...../...../...../.....",
    "a": "...../...../.###./....#/.####/#...#/.####/.....",
    "b": "#..../#..../#.##./##..#/#...#/#...#/####./.....",
    "c": "...../...../.###./#..../#..../#..../.###./.....",
    "d": "....#/....#/.##.#/##..#/#...#/#...#/.####/.....",
    "e": "...../...../.###./#...#/#####/#..../.###./.....",
    "f": "..##./.#..#/.#.../####./.#.../.#.../.#.../.....",
    "g": "...../...../.####/#...#/#...#/.####/....#/.###.",
    "h": "#..../#..../#.##./##..#/#...#/#...#/#...#/.....",
    "i": "..#../...../.##../..#../..#../..#../.###./.....",
    "j": "...#./...../..##./...#./...#./...#./#..#./.##..",
    "k": "#..../#..../#..#./#.#../##.../#.#../#..#./.....",
    "l": ".##../..#../..#../..#../..#../..#../.###./.....",
    "m": "...../...../##.#./#.#.#/#.#.#/#.#.#/#.#.#/.....",
    "n": "...../...../#.##./##..#/#...#/#...#/#...#/.....",
    "o": "...../...../.###./#...#/#...#/#...#/.###./.....",
    "p": "...../...../####./#...#/#...#/####./#..../#....",
    "q": "...../...../.####/#...#/#...#/.####/....#/....#",
    "r": "...../...../#.##./##..#/#..../#..../#..../.....",
    "s": "...../...../.####/#..../.###./....#/####./.....",
    "t": ".#.../.#.../####./.#.../.#.../.#..#/..##./.....",
    "u": "...../...../#...#/#...#/#...#/#..##/.##.#/.....",
    "v": "...../...../#...#/#...#/#...#/.#.#./..#../.....",
    "w": "...../...../#...#/#.#.#/#.#.#/#.#.#/.#.#./.....",
    "x": "...../...../#...#/.#.#./..#../.#.#./#...#/.....",
    "y": "...../...../#...#/#...#/#...#/.####/....#/.###.",
    "z": "...../...../#####/...#./..#../.#.../#####/.....",
    "{": "...##/..#../..#../.#.../..#../..#../...##/.....",
    "|": "..#../..#../..#../..#../..#../..#../..#../.....",
    "}": "##.../..#../..#../...#./..#../..#../##.../.....",
    "~": "...../...../.#..#/#.#.#/#..#./...../...../.....",
}

#: Drawn for anything not in :data:`GLYPHS`. A filled box, deliberately: a
#: missing character that renders as a space is a missing character nobody
#: reports.
MISSING = "#####/#...#/#...#/#...#/#...#/#...#/#####/....."


def bitmap(char: str) -> np.ndarray:
    """One glyph as a mask.

    Parameters
    ----------
    char : str
        A single character.

    Returns
    -------
    numpy.ndarray
        ``(HEIGHT, WIDTH)`` bool, True where there is ink.
    """
    rows = GLYPHS.get(char, MISSING).split("/")
    grid = np.zeros((HEIGHT, WIDTH), dtype=bool)
    for y, row in enumerate(rows[:HEIGHT]):
        for x, cell in enumerate(row[:WIDTH]):
            grid[y, x] = cell == "#"
    return grid


def atlas(scale: int = SCALE) -> np.ndarray:
    """Every glyph in :data:`CHARSET`, side by side, as coverage.

    Parameters
    ----------
    scale : int, optional
        Atlas pixels per font pixel.

    Returns
    -------
    numpy.ndarray
        ``(HEIGHT * scale, WIDTH * scale * len(CHARSET))`` uint8, 0 or 255.
        Boxes only -- the inter-character gap is layout, not atlas, so a glyph
        fills its cell exactly and nothing has to trim padding later.
    """
    scale = max(1, int(scale))
    cells = [bitmap(char) for char in CHARSET]
    grid = np.concatenate(cells, axis=1)
    grid = np.repeat(np.repeat(grid, scale, axis=0), scale, axis=1)
    return (grid * 255).astype(np.uint8)


def validate() -> list[str]:
    """Check every glyph is the right shape.

    A row of the wrong length silently truncates or leaves a column blank, and
    the result is a letter that looks *nearly* right -- which is exactly the
    kind of thing nobody spots in a screenshot but everybody feels.

    Returns
    -------
    list of str
        One complaint per malformed glyph; empty when the table is sound.
    """
    problems = []
    for char, art in GLYPHS.items():
        rows = art.split("/")
        if len(rows) != HEIGHT:
            problems.append(f"{char!r}: {len(rows)} rows, expected {HEIGHT}")
        for index, row in enumerate(rows):
            if len(row) != WIDTH:
                problems.append(f"{char!r} row {index}: {len(row)} wide, expected {WIDTH}")
            if set(row) - {"#", "."}:
                problems.append(f"{char!r} row {index}: unexpected characters")
    return problems
