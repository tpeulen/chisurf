"""Qt widget for the Minesweeper game."""

from __future__ import annotations

from qtpy import QtCore, QtWidgets

from chisurf.plugins.misc.games.minesweeper.core import (
    DIFFICULTIES,
    MAX_BOARD_SIZE,
    MIN_BOARD_SIZE,
    GameStatus,
    MinesweeperGame,
)


class _CellButton(QtWidgets.QPushButton):
    """A board button that reports both primary and secondary clicks."""

    right_clicked = QtCore.Signal(int, int)

    def __init__(self, row: int, column: int, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.row = row
        self.column = column
        self.setFixedSize(30, 30)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

    def mousePressEvent(self, event) -> None:
        if event.button() == QtCore.Qt.RightButton:
            self.right_clicked.emit(self.row, self.column)
            event.accept()
            return
        super().mousePressEvent(event)


class MinesweeperWidget(QtWidgets.QWidget):
    """A Minesweeper board with selectable playfield size and mine count."""

    name = "Minesweeper"

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.game = MinesweeperGame()
        self.buttons: dict[tuple[int, int], _CellButton] = {}
        self.setWindowTitle("Minesweeper")
        self._build_ui()
        self._rebuild_board()
        self._render("Left-click to reveal. Right-click to flag.")

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QtWidgets.QLabel("Minesweeper")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: 600;")
        layout.addWidget(title)

        layout.addLayout(self._build_settings_row())

        self.status_label = QtWidgets.QLabel()
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # The board lives in a scroll area so large playfields stay usable.
        board_widget = QtWidgets.QWidget()
        self.board_layout = QtWidgets.QGridLayout(board_widget)
        self.board_layout.setSpacing(2)
        self.board_layout.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)

        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidget(board_widget)
        scroll.setWidgetResizable(False)
        scroll.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(scroll, 1)

        self.new_game_button = QtWidgets.QPushButton("New game")
        self.new_game_button.clicked.connect(self._new_game)
        layout.addWidget(self.new_game_button)

    def _build_settings_row(self) -> QtWidgets.QHBoxLayout:
        """Build the difficulty selector and the custom-board spin boxes."""
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)

        self.difficulty_combo = QtWidgets.QComboBox()
        self.difficulty_combo.setToolTip("Board preset; pick Custom to set size and mines freely.")
        for name, (rows, columns, mines) in DIFFICULTIES.items():
            self.difficulty_combo.addItem(f"{name} ({rows}×{columns}, {mines} mines)", name)
        self.difficulty_combo.addItem("Custom", "Custom")
        self.difficulty_combo.currentIndexChanged.connect(self._on_difficulty_changed)
        row.addWidget(self.difficulty_combo, 1)

        self.rows_spin = QtWidgets.QSpinBox()
        self.rows_spin.setToolTip("Number of board rows.")
        self.columns_spin = QtWidgets.QSpinBox()
        self.columns_spin.setToolTip("Number of board columns.")
        for spin in (self.rows_spin, self.columns_spin):
            spin.setRange(MIN_BOARD_SIZE, MAX_BOARD_SIZE)
        self.mines_spin = QtWidgets.QSpinBox()
        self.mines_spin.setToolTip("Number of mines on the board.")
        self.mines_spin.setRange(1, MAX_BOARD_SIZE * MAX_BOARD_SIZE - 1)

        self.rows_spin.setValue(self.game.rows)
        self.columns_spin.setValue(self.game.columns)
        self.mines_spin.setValue(self.game.mines)
        self.rows_spin.valueChanged.connect(self._clamp_mines)
        self.columns_spin.valueChanged.connect(self._clamp_mines)

        row.addWidget(QtWidgets.QLabel("Rows"))
        row.addWidget(self.rows_spin)
        row.addWidget(QtWidgets.QLabel("Cols"))
        row.addWidget(self.columns_spin)
        row.addWidget(QtWidgets.QLabel("Mines"))
        row.addWidget(self.mines_spin)

        self._on_difficulty_changed(self.difficulty_combo.currentIndex())
        return row

    def _on_difficulty_changed(self, index: int) -> None:
        """Sync the spin boxes with the chosen preset; unlock them for Custom."""
        preset = self.difficulty_combo.itemData(index)
        custom = preset == "Custom"
        for spin in (self.rows_spin, self.columns_spin, self.mines_spin):
            spin.setEnabled(custom)
        if not custom:
            rows, columns, mines = DIFFICULTIES[preset]
            self.rows_spin.setValue(rows)
            self.columns_spin.setValue(columns)
            self.mines_spin.setValue(mines)

    def _clamp_mines(self) -> None:
        """Keep the mine count below the number of cells."""
        max_mines = self.rows_spin.value() * self.columns_spin.value() - 1
        self.mines_spin.setMaximum(max_mines)

    def _rebuild_board(self) -> None:
        """Recreate the button grid to match the current game dimensions."""
        for button in self.buttons.values():
            self.board_layout.removeWidget(button)
            button.deleteLater()
        self.buttons.clear()
        for row, column in self.game.coordinates():
            button = _CellButton(row, column, self)
            button.clicked.connect(lambda checked=False, r=row, c=column: self._reveal(r, c))
            button.right_clicked.connect(self._toggle_flag)
            self.board_layout.addWidget(button, row, column)
            self.buttons[row, column] = button

    def _new_game(self) -> None:
        self._clamp_mines()
        rows = self.rows_spin.value()
        columns = self.columns_spin.value()
        mines = self.mines_spin.value()
        resized = (rows, columns) != (self.game.rows, self.game.columns)
        self.game.configure(rows, columns, mines)
        if resized:
            self._rebuild_board()
        self._render("New board ready. Good luck!")

    def _reveal(self, row: int, column: int) -> None:
        result = self.game.reveal(row, column)
        self._render(result.message)

    def _toggle_flag(self, row: int, column: int) -> None:
        result = self.game.toggle_flag(row, column)
        self._render(result.message)

    def _render(self, message: str) -> None:
        self.status_label.setText(
            f"{message}  Flags: {self.game.flags_remaining}"
        )
        for row, column in self.game.coordinates():
            cell = self.game.board[row][column]
            button = self.buttons[row, column]
            button.setEnabled(not cell.revealed and self.game.status is GameStatus.ACTIVE)
            button.setStyleSheet("font-weight: 600;")
            if cell.revealed:
                if cell.mine:
                    button.setText("💣")
                    button.setStyleSheet("background: #e57373; font-weight: 600;")
                elif cell.adjacent_mines:
                    button.setText(str(cell.adjacent_mines))
                    button.setStyleSheet("background: #eceff1; font-weight: 600;")
                else:
                    button.setText("")
                    button.setStyleSheet("background: #eceff1;")
            elif cell.flagged:
                button.setText("🚩")
            else:
                button.setText("")
