"""Tetris' rules survived being lifted out of the widget.

The logic used to live inside a ``QFrame``; it is a plain object now, so the
whole simulation steps here with no Qt and no window.
"""

from __future__ import annotations

import pytest

pytest.importorskip("wgpu")
pytest.importorskip("rendercanvas")

from chisurf.gui import chigame  # noqa: E402
from chisurf.gui.chigame.input import Action  # noqa: E402
from chisurf.plugins.misc.games.tetris.tetris import (  # noqa: E402
    BOARD_H,
    BOARD_W,
    SHAPE_NM,
    SHAPES,
    SQUARE,
    TetrisGame,
    rotated,
)


@pytest.fixture
def game(qapp):
    """A game wired to a headless host.

    Returns
    -------
    TetrisGame
        Ready to step.
    """
    try:
        context = chigame.create_offscreen(size=(160, 200))
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    instance = TetrisGame()
    chigame.GameHost(instance, context, with_text=False, with_audio=False)
    return instance


def test_a_new_game_starts_with_an_empty_well(game):
    """Nothing is settled and a piece is in play."""
    assert all(cell is None for row in game.well for cell in row)
    assert len(game.well) == BOARD_H and len(game.well[0]) == BOARD_W
    assert len(game.coords) == 4
    assert game.score == 0 and game.lines == 0 and game.level == 1


def test_rotation_is_a_quarter_turn_and_reversible():
    """Four rotations return a piece to where it started."""
    coords = list(SHAPES[0])
    assert rotated(rotated(rotated(rotated(coords)))) == coords


def test_the_square_piece_does_not_rotate(game):
    """Rotating a symmetric piece would only shift it, so it is skipped."""
    game.shape = SQUARE
    game.coords = list(SHAPES[SQUARE])
    before = list(game.coords)
    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    assert game.coords == before


def test_a_piece_cannot_leave_the_well(game):
    """Walls and floor both reject a move."""
    assert not game.fits(game.coords, -5, game.y)
    assert not game.fits(game.coords, BOARD_W + 5, game.y)
    assert not game.fits(game.coords, game.x, BOARD_H + 5)


def test_a_hard_drop_settles_the_piece_on_the_floor(game):
    """The piece lands, is written into the well, and a new one appears."""
    game.host.keys.tap(Action.SHOULDER_R)
    game.update(1 / 60, game.host.keys)
    filled = [(r, c) for r in range(BOARD_H) for c in range(BOARD_W) if game.well[r][c] is not None]
    assert len(filled) == 4
    assert max(r for r, _ in filled) == BOARD_H - 1, "it must rest on the floor"


def test_a_full_row_is_cleared_and_scored(game):
    """Completing a line removes it, scores it, and keeps the well the same size."""
    game.well[BOARD_H - 1] = [0 for _ in range(BOARD_W)]
    game.remove_full_lines()
    assert game.lines == 1
    assert game.score > 0
    assert len(game.well) == BOARD_H
    assert all(cell is None for cell in game.well[0])


def test_four_rows_at_once_score_more_than_four_singles(game):
    """The scoring table rewards clearing together, as the original did."""
    for row in range(BOARD_H - 4, BOARD_H):
        game.well[row] = [0 for _ in range(BOARD_W)]
    game.remove_full_lines()
    quad = game.score

    game.restart()
    single = 0
    for _ in range(4):
        game.well[BOARD_H - 1] = [0 for _ in range(BOARD_W)]
        game.remove_full_lines()
    single = game.score
    assert quad > single, (quad, single)


def test_the_level_rises_every_ten_lines_and_speeds_the_fall(game):
    """Gain follows lines cleared, and a higher level falls faster."""
    slow = game.fall_interval
    game.lines = 20
    game.level = 1 + game.lines // 10
    assert game.level == 3
    assert game.fall_interval < slow


def test_filling_the_spawn_column_ends_the_run(game):
    """A well with no room at the top is over."""
    for row in range(BOARD_H):
        game.well[row] = [0 for _ in range(BOARD_W)]
    game.new_piece()
    assert game.over is True


def test_each_shape_has_its_own_wavelength():
    """The well is a spectrum, so no two pieces may share a colour."""
    assert len(SHAPE_NM) == len(SHAPES)
    assert len(set(SHAPE_NM)) == len(SHAPES)
    assert SHAPE_NM == sorted(SHAPE_NM)


def test_it_renders(qapp):
    """A frame comes out with the well drawn on it."""
    try:
        frame = chigame.capture(TetrisGame(), size=(260, 310), frames=2, with_audio=False)
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    assert frame.shape == (310, 260, 4)
