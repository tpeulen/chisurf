"""Qt widget for the Lumis Quest game.

Shows the reviewer's level, XP, streak, and achievements, and lets them sign
off a documentation page (which awards variable XP). The sign-off goes through
the existing review system; the game layer adds the reward.
"""

from __future__ import annotations

from qtpy import QtCore, QtWidgets

from chisurf.plugins.misc.games.lumis_quest.api.game_state import (
    ACHIEVEMENTS,
    GameState,
)


class LumisQuestWidget(QtWidgets.QWidget):
    """A small game window for reviewing documentation with XP rewards."""

    name = "Lumis Quest"

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.game = GameState.load()
        self.setWindowTitle("Lumis Quest")
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("Lumis Quest")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: 600;")
        layout.addWidget(title)

        self.stats_label = QtWidgets.QLabel()
        self.stats_label.setAlignment(QtCore.Qt.AlignCenter)
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)

        # Review controls.
        row = QtWidgets.QHBoxLayout()
        self.page_input = QtWidgets.QLineEdit()
        self.page_input.setPlaceholderText("Path to a doc page, e.g. guides/11_burst_selection.md")
        self.page_input.setAccessibleName("Documentation page path")
        self.review_button = QtWidgets.QPushButton("Approve page")
        self.review_button.clicked.connect(self._approve)
        row.addWidget(self.page_input, 1)
        row.addWidget(self.review_button)
        layout.addLayout(row)

        self.difficulty_combo = QtWidgets.QComboBox()
        self.difficulty_combo.addItems(["easy", "medium", "hard", "expert"])
        self.difficulty_combo.setAccessibleName("Section difficulty")
        layout.addWidget(self.difficulty_combo)

        self.message_label = QtWidgets.QLabel()
        self.message_label.setAlignment(QtCore.Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        self.achievements_label = QtWidgets.QLabel()
        self.achievements_label.setAlignment(QtCore.Qt.AlignLeft)
        self.achievements_label.setWordWrap(True)
        layout.addWidget(self.achievements_label)

        self.new_game_button = QtWidgets.QPushButton("Reset progress")
        self.new_game_button.clicked.connect(self._reset)
        layout.addWidget(self.new_game_button)

    def _approve(self) -> None:
        path = self.page_input.text().strip()
        if not path:
            self.message_label.setText("Enter a documentation page path first.")
            return
        difficulty = self.difficulty_combo.currentText()
        result = self.game.record_review(difficulty=difficulty)
        self._refresh()
        unlocked = result["unlocked"]
        unlock_text = (
            f"\n🏆 Unlocked: {', '.join(unlocked)}!" if unlocked else ""
        )
        self.message_label.setText(
            f"✅ +{result['xp']} XP ({result['label']})\n"
            f"Level {result['level']}: {result['level_title']} · "
            f"🔥 Streak: {result['streak']}{unlock_text}"
        )

    def _reset(self) -> None:
        self.game = GameState(reviewer=self.game.reviewer)
        self.game.save()
        self._refresh()
        self.message_label.setText("Progress reset. Good luck!")

    def _refresh(self) -> None:
        g = self.game
        xp_into, xp_next = g.level_progress
        if xp_next:
            progress = f"{xp_into} / {xp_next} XP to next level"
        else:
            progress = "Max level reached!"
        self.stats_label.setText(
            f"Level {g.level}: {g.level_title}\n"
            f"Total XP: {g.xp} · {progress}\n"
            f"🔥 Streak: {g.streak.current} (best {g.streak.best})\n"
            f"Pages reviewed: {g.total_pages_reviewed} · "
            f"Suggestions merged: {g.total_suggestions_merged}"
        )
        have = {a["id"] for a in g.achievements}
        lines = []
        for aid, name, cond in ACHIEVEMENTS:
            mark = "✓" if aid in have else "✗"
            lines.append(f"{mark} {name} — {cond}")
        self.achievements_label.setText("\n".join(lines))
