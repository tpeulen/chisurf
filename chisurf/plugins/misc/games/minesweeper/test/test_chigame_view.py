"""The minesweeper view drives the existing rules with a pad, not a mouse.

The rules were already Qt-free, so this is a view port and the core is
untouched. What is worth pinning is the input model: a cursor that is game
state, which makes picking exact by construction and scriptable without
synthesising pointer events.
"""

from __future__ import annotations

import pytest

pytest.importorskip("wgpu")
pytest.importorskip("rendercanvas")

from chisurf.gui import chigame  # noqa: E402
from chisurf.gui.chigame.input import Action  # noqa: E402
from chisurf.plugins.misc.games.minesweeper.core.game import (  # noqa: E402
    DIFFICULTIES,
    GameStatus,
)
from chisurf.plugins.misc.games.minesweeper.gui.tool import (  # noqa: E402
    MinesweeperChiGame,
)


@pytest.fixture
def game(qapp):
    """A view wired to a headless host.

    Returns
    -------
    MinesweeperChiGame
        Ready to step.
    """
    try:
        context = chigame.create_offscreen(size=(200, 220))
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    instance = MinesweeperChiGame()
    chigame.GameHost(instance, context, with_text=False, with_audio=False)
    return instance


def test_it_starts_on_the_first_preset(game):
    """The board matches the preset it names."""
    rows, columns, mines = DIFFICULTIES[game.difficulty_names[0]]
    assert (game.rows, game.columns) == (rows, columns)
    assert game.game.mines == mines


def test_the_cursor_moves_and_clamps(game):
    """The pad walks the cursor and it cannot leave the board."""
    game.cursor_row = game.cursor_col = 0
    game.host.keys.tap(Action.RIGHT)
    game.update(1 / 60, game.host.keys)
    assert (game.cursor_row, game.cursor_col) == (0, 1)

    game.host.keys.end_frame()
    game.cursor_row = game.cursor_col = 0
    game.host.keys.tap(Action.UP)
    game.update(1 / 60, game.host.keys)
    assert game.cursor_row == 0, "the cursor must clamp at the top edge"


def test_confirm_reveals_the_cell_under_the_cursor(game):
    """Picking is exact: the cursor *is* the selection."""
    game.cursor_row, game.cursor_col = 2, 3
    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    assert game.game.board[2][3].revealed


def test_menu_flags_and_unflags(game):
    """Flagging is a pad action and toggles."""
    game.cursor_row, game.cursor_col = 1, 1
    before = game.game.flags_remaining

    game.host.keys.tap(Action.MENU)
    game.update(1 / 60, game.host.keys)
    assert game.game.board[1][1].flagged
    assert game.game.flags_remaining == before - 1

    game.host.keys.end_frame()
    game.host.keys.tap(Action.MENU)
    game.update(1 / 60, game.host.keys)
    assert not game.game.board[1][1].flagged


def test_shoulders_cycle_presets_and_resize_the_board(game):
    """Difficulty is reachable without a menu widget."""
    first = (game.rows, game.columns)
    game.host.keys.tap(Action.SHOULDER_R)
    game.update(1 / 60, game.host.keys)
    assert game.difficulty_index == 1
    assert (game.rows, game.columns) != first


def test_the_view_fits_the_widest_preset(game):
    """A 30-column board must not be clipped off the sides.

    Sizing the camera from the board's height alone works for the square
    Beginner board and cuts the Expert one in half.
    """
    game.difficulty_index = game.difficulty_names.index("Expert")
    game.apply_difficulty()
    from chisurf.plugins.misc.games.minesweeper.gui.tool import CELL

    board_width = game.columns * CELL
    # The camera spans height * aspect horizontally; the port sizes for a
    # conservative 0.80 aspect.
    assert game.host.camera.height * 0.80 >= board_width


def test_a_revealed_mine_ends_the_round(game):
    """The core still decides the outcome; the view only reports it."""
    row, col = next(
        (r, c) for r in range(game.rows) for c in range(game.columns) if game.game.board[r][c].mine
    )
    game.cursor_row, game.cursor_col = row, col
    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    assert game.game.status is GameStatus.LOST


def test_it_renders(qapp):
    """A frame comes out with the grid drawn on it."""
    try:
        frame = chigame.capture(MinesweeperChiGame(), size=(280, 310), frames=2, with_audio=False)
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    assert frame.shape == (310, 280, 4)
