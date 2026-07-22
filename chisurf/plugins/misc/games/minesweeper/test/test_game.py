"""Tests for the Minesweeper rules."""

import pytest

from chisurf.plugins.misc.games.minesweeper.core import (
    DIFFICULTIES,
    GameStatus,
    MinesweeperGame,
)


def test_empty_region_cascades_and_wins_when_every_safe_cell_is_revealed():
    game = MinesweeperGame(rows=3, columns=3, mines=1, mine_positions={(0, 0)})

    result = game.reveal(2, 2)

    assert result.status is GameStatus.WON
    assert result.unrevealed_safe_cells == 0
    assert not game.board[0][0].revealed


def test_flags_protect_cells_until_removed():
    game = MinesweeperGame(rows=2, columns=2, mines=1, mine_positions={(0, 0)})

    game.toggle_flag(0, 0)
    protected = game.reveal(0, 0)
    game.toggle_flag(0, 0)
    lost = game.reveal(0, 0)

    assert protected.status is GameStatus.ACTIVE
    assert protected.message == "Remove the flag before revealing this cell."
    assert lost.status is GameStatus.LOST


def test_revealing_a_mine_ends_the_game_and_shows_mines():
    game = MinesweeperGame(rows=2, columns=3, mines=2, mine_positions={(0, 0), (1, 2)})

    result = game.reveal(0, 0)

    assert result.status is GameStatus.LOST
    assert game.board[1][2].revealed
    assert result.message == "Boom! You found a mine."


def test_configure_resizes_the_board_and_restarts():
    game = MinesweeperGame(rows=2, columns=2, mines=1, mine_positions={(0, 0)})
    game.reveal(0, 0)

    game.configure(rows=16, columns=30, mines=99)

    assert game.status is GameStatus.ACTIVE
    assert (game.rows, game.columns, game.mines) == (16, 30, 99)
    assert len(game.board) == 16
    assert len(game.board[0]) == 30
    assert sum(cell.mine for row in game.board for cell in row) == 99


def test_configure_rejects_invalid_settings():
    game = MinesweeperGame()

    with pytest.raises(ValueError, match="mines must be between"):
        game.configure(rows=3, columns=3, mines=9)
    with pytest.raises(ValueError, match="dimensions must be positive"):
        game.configure(rows=0, columns=3, mines=1)


def test_difficulty_presets_are_valid_boards():
    for rows, columns, mines in DIFFICULTIES.values():
        game = MinesweeperGame(rows=rows, columns=columns, mines=mines)
        assert sum(cell.mine for row in game.board for cell in row) == mines


def test_invalid_board_and_coordinates_are_rejected():
    with pytest.raises(ValueError, match="mines must be between"):
        MinesweeperGame(rows=2, columns=2, mines=4)

    game = MinesweeperGame(rows=2, columns=2, mines=1, mine_positions={(0, 0)})
    with pytest.raises(ValueError, match="outside the board"):
        game.reveal(2, 0)
