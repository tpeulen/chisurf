"""The world as a grid of screens, at 16-bit scale.

A continuously scrolling camera is the modern default and it is the wrong one
for this. A world cut into fixed **screens** -- you walk to the edge, the view
flips, and you are somewhere else -- does three things a scrolling camera
cannot:

* **Every screen is composed.** The designer knows exactly what is on show, so
  a screen can be a puzzle, an ambush or a view. A scrolling map has no frame
  to compose inside.
* **It makes the world feel large.** A flip is a small ceremony, and a world
  that takes twenty flips to cross reads as bigger than the same tiles scrolled
  past in one continuous sweep.
* **You remember where things are.** "Two screens north of the cave" is a thing
  a person can hold; "about six hundred units north-east" is not.

The geometry is the **16-bit** playfield, not the 8-bit one: a SNES screen is
256 by 224 pixels, which at a 16-pixel tile is **16 by 14 tiles**. The NES
screen was 16 by 11, and the difference is not academic -- three more rows is
the difference between a room and a corridor, and it is why the 16-bit era's
towns could have a street with buildings on both sides of it.

This is pure geometry over the grid the world already has -- no second copy of
the map, and a screen is a *view* rather than a data structure. That is what
makes it cheap to add to a world that was built continuous.
"""

from __future__ import annotations

from .tiles import TILE

#: Tiles across and down one screen: the 16-bit playfield, 256x224 pixels at a
#: 16-pixel tile. Wide enough to hold a building and its approach, small enough
#: that a flip means something.
COLS = 16
ROWS = 14

#: One screen in world units.
WIDTH = COLS * TILE
HEIGHT = ROWS * TILE

#: How long a flip takes, in seconds. Long enough to read as a transition,
#: short enough that crossing five screens is not a cutscene.
FLIP_SECONDS = 0.28


def screen_of(x: float, y: float) -> tuple[int, int]:
    """Which screen a world position is on.

    Parameters
    ----------
    x, y : float
        World coordinates.

    Returns
    -------
    tuple of int
        ``(screen column, screen row)``.
    """
    return (int(x // WIDTH), int(y // HEIGHT))


def origin_of(screen_x: int, screen_y: int) -> tuple[float, float]:
    """The top-left corner of a screen, in world units.

    Parameters
    ----------
    screen_x, screen_y : int
        Screen coordinates.

    Returns
    -------
    tuple of float
        World coordinates.
    """
    return (screen_x * WIDTH, screen_y * HEIGHT)


def centre_of(screen_x: int, screen_y: int) -> tuple[float, float]:
    """The middle of a screen, which is where the camera sits.

    Parameters
    ----------
    screen_x, screen_y : int
        Screen coordinates.

    Returns
    -------
    tuple of float
        World coordinates.
    """
    return ((screen_x + 0.5) * WIDTH, (screen_y + 0.5) * HEIGHT)


def tiles_of(screen_x: int, screen_y: int) -> tuple[int, int, int, int]:
    """The grid range one screen covers.

    Parameters
    ----------
    screen_x, screen_y : int
        Screen coordinates.

    Returns
    -------
    tuple of int
        ``(col0, row0, col1, row1)``, the last exclusive.
    """
    return (screen_x * COLS, screen_y * ROWS,
            (screen_x + 1) * COLS, (screen_y + 1) * ROWS)


def label(screen_x: int, screen_y: int) -> str:
    """A name for a screen, for the map and for saying where something is.

    Parameters
    ----------
    screen_x, screen_y : int
        Screen coordinates.

    Returns
    -------
    str
        Column letter and row number, as a paper map would.
    """
    letters = ""
    index = screen_x
    while True:
        letters = chr(ord("A") + index % 26) + letters
        index = index // 26 - 1
        if index < 0:
            break
    return f"{letters}{screen_y + 1}"
