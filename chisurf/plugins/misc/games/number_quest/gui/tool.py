"""Qt widget for the Number Quest guessing game."""

from __future__ import annotations

from qtpy import QtCore, QtWidgets

from chisurf.plugins.misc.games.number_quest.core import GuessStatus, NumberQuestGame


class NumberQuestWidget(QtWidgets.QWidget):
    """A small game window for guessing a number between one and one hundred."""

    name = "Number Quest"

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.game = NumberQuestGame()
        self.setWindowTitle("Number Quest")
        self._build_ui()
        self._refresh("I picked a number from 1 to 100. Can you find it?")

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("Number Quest")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: 600;")
        layout.addWidget(title)

        self.message_label = QtWidgets.QLabel()
        self.message_label.setAlignment(QtCore.Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        guess_row = QtWidgets.QHBoxLayout()
        self.guess_input = QtWidgets.QSpinBox()
        self.guess_input.setRange(NumberQuestGame.minimum, NumberQuestGame.maximum)
        self.guess_input.setValue(50)
        self.guess_input.setAccessibleName("Your guess")
        self.guess_button = QtWidgets.QPushButton("Guess")
        self.guess_button.clicked.connect(self._make_guess)
        self.guess_input.editingFinished.connect(self._make_guess)
        guess_row.addWidget(self.guess_input)
        guess_row.addWidget(self.guess_button)
        layout.addLayout(guess_row)

        self.stats_label = QtWidgets.QLabel()
        self.stats_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.stats_label)

        self.new_game_button = QtWidgets.QPushButton("New game")
        self.new_game_button.clicked.connect(self._new_game)
        layout.addWidget(self.new_game_button)

    def _make_guess(self) -> None:
        result = self.game.guess(self.guess_input.value())
        self._refresh(result.message)

    def _new_game(self) -> None:
        self.game.reset()
        self.guess_input.setValue(50)
        self._refresh("New number chosen. Good luck!")

    def _refresh(self, message: str) -> None:
        self.message_label.setText(message)
        self.stats_label.setText(
            f"Turns left: {self.game.attempts_remaining}    Score: {self.game.score}"
        )
        self.guess_button.setEnabled(self.game.status is GuessStatus.ACTIVE)
