"""Pure, UI-independent rules for a small Minesweeper board."""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from enum import Enum


class GameStatus(str, Enum):
    """Possible states of a Minesweeper round."""

    ACTIVE = "active"
    WON = "won"
    LOST = "lost"


#: Named board presets: name -> (rows, columns, mines).
DIFFICULTIES: dict[str, tuple[int, int, int]] = {
    "Beginner": (9, 9, 10),
    "Intermediate": (16, 16, 40),
    "Expert": (16, 30, 99),
}

#: Bounds for custom boards (rows/columns share the same range).
MIN_BOARD_SIZE = 5
MAX_BOARD_SIZE = 30


@dataclass
class Cell:
    """A single square on the board."""

    mine: bool = False
    revealed: bool = False
    flagged: bool = False
    adjacent_mines: int = 0


@dataclass(frozen=True)
class GameResult:
    """A snapshot returned after a player action."""

    message: str
    status: GameStatus
    flags_remaining: int
    unrevealed_safe_cells: int


class MinesweeperGame:
    """Manage a rectangular Minesweeper game board."""

    def __init__(
        self,
        rows: int = 9,
        columns: int = 9,
        mines: int = 10,
        mine_positions: set[tuple[int, int]] | None = None,
    ) -> None:
        if rows < 1 or columns < 1:
            raise ValueError("board dimensions must be positive")
        if not 1 <= mines < rows * columns:
            raise ValueError("mines must be between 1 and the number of cells minus one")
        self.rows = rows
        self.columns = columns
        self.mines = mines
        self._fixed_mine_positions = mine_positions
        self.reset()

    def configure(self, rows: int, columns: int, mines: int) -> None:
        """Change the board dimensions and mine count, then start a new board.

        Parameters
        ----------
        rows, columns : int
            New board dimensions (positive).
        mines : int
            Number of mines; must leave at least one safe cell.
        """
        if rows < 1 or columns < 1:
            raise ValueError("board dimensions must be positive")
        if not 1 <= mines < rows * columns:
            raise ValueError("mines must be between 1 and the number of cells minus one")
        self.rows = rows
        self.columns = columns
        self.mines = mines
        self._fixed_mine_positions = None
        self.reset()

    def reset(self) -> None:
        """Start a new board using the configured dimensions and mine count."""
        positions = self._mine_positions()
        self.board = [
            [Cell(mine=(row, column) in positions) for column in range(self.columns)]
            for row in range(self.rows)
        ]
        for row, column in self.coordinates():
            self.board[row][column].adjacent_mines = sum(
                self.board[neighbor_row][neighbor_column].mine
                for neighbor_row, neighbor_column in self.neighbors(row, column)
            )
        self.status = GameStatus.ACTIVE

    def coordinates(self):
        """Yield every board coordinate in row-major order."""
        for row in range(self.rows):
            for column in range(self.columns):
                yield row, column

    def neighbors(self, row: int, column: int):
        """Yield valid neighboring coordinates around a cell."""
        for neighbor_row in range(max(0, row - 1), min(self.rows, row + 2)):
            for neighbor_column in range(max(0, column - 1), min(self.columns, column + 2)):
                if (neighbor_row, neighbor_column) != (row, column):
                    yield neighbor_row, neighbor_column

    @property
    def flags_remaining(self) -> int:
        """Return how many mine markers may still be placed."""
        return self.mines - sum(cell.flagged for row in self.board for cell in row)

    @property
    def unrevealed_safe_cells(self) -> int:
        """Return the number of safe cells that the player has not uncovered."""
        return sum(not cell.mine and not cell.revealed for row in self.board for cell in row)

    def reveal(self, row: int, column: int) -> GameResult:
        """Reveal one cell, cascading through adjacent empty cells when applicable."""
        cell = self._cell_at(row, column)
        if self.status is not GameStatus.ACTIVE:
            return self._result("Start a new game to play again.")
        if cell.flagged:
            return self._result("Remove the flag before revealing this cell.")
        if cell.revealed:
            return self._result("That cell is already revealed.")
        if cell.mine:
            cell.revealed = True
            self.status = GameStatus.LOST
            self._reveal_mines()
            return self._result("Boom! You found a mine.")

        self._reveal_safe_region(row, column)
        if self.unrevealed_safe_cells == 0:
            self.status = GameStatus.WON
            return self._result("You cleared the board! Victory!")
        return self._result("Keep searching.")

    def toggle_flag(self, row: int, column: int) -> GameResult:
        """Place or remove a mine marker on an unrevealed cell."""
        cell = self._cell_at(row, column)
        if self.status is not GameStatus.ACTIVE:
            return self._result("Start a new game to play again.")
        if cell.revealed:
            return self._result("Revealed cells cannot be flagged.")
        if not cell.flagged and self.flags_remaining == 0:
            return self._result("No flags remaining.")
        cell.flagged = not cell.flagged
        return self._result("Flag placed." if cell.flagged else "Flag removed.")

    def _mine_positions(self) -> set[tuple[int, int]]:
        if self._fixed_mine_positions is not None:
            if len(self._fixed_mine_positions) != self.mines:
                raise ValueError("mine_positions must contain exactly mines entries")
            for row, column in self._fixed_mine_positions:
                self._validate_coordinates(row, column)
            return set(self._fixed_mine_positions)
        return set(random.sample(list(self.coordinates()), self.mines))

    def _cell_at(self, row: int, column: int) -> Cell:
        self._validate_coordinates(row, column)
        return self.board[row][column]

    def _validate_coordinates(self, row: int, column: int) -> None:
        if not 0 <= row < self.rows or not 0 <= column < self.columns:
            raise ValueError("cell coordinates are outside the board")

    def _reveal_safe_region(self, row: int, column: int) -> None:
        pending = deque([(row, column)])
        while pending:
            current_row, current_column = pending.popleft()
            cell = self.board[current_row][current_column]
            if cell.revealed or cell.flagged or cell.mine:
                continue
            cell.revealed = True
            if cell.adjacent_mines == 0:
                pending.extend(self.neighbors(current_row, current_column))

    def _reveal_mines(self) -> None:
        for row in self.board:
            for cell in row:
                if cell.mine:
                    cell.revealed = True

    def _result(self, message: str) -> GameResult:
        return GameResult(
            message=message,
            status=self.status,
            flags_remaining=self.flags_remaining,
            unrevealed_safe_cells=self.unrevealed_safe_cells,
        )
