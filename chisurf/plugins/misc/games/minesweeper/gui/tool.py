"""Minesweeper, on the chigame engine.

The rules were already Qt-free in :mod:`..core.game`, so this is a *view* port:
the same :class:`MinesweeperGame` drives the board and nothing about the logic
moves. What changes is the renderer and, more importantly, the input model --
there is no mouse. A pad cursor walks the grid, Confirm reveals, Menu flags.

Minesweeper is the engine's picking test. Picking with a pad turns out to be
simpler and more precise than hit-testing a pointer: the cursor is game state,
so it is exact by construction and trivially scriptable in a test.

The theme is a detector array being scanned for hot pixels: cells are pixels,
mines are hot pixels, and the adjacency count is how many hot neighbours a
pixel sees.
"""

from __future__ import annotations

from qtpy import QtWidgets

from chisurf.gui import chigame
from chisurf.gui.chigame.assets import spectral_band, wavelength_to_srgb
from chisurf.gui.chigame.input import Action

from ..core.game import DIFFICULTIES, GameStatus, MinesweeperGame

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - stand-alone use

    def persist_plugin_state(name):
        """Return an identity decorator when the host is unavailable."""
        return lambda cls: cls


#: Cell pitch in world units.
CELL = 26.0

#: Board origin in world units.
ORIGIN_X = 24.0
ORIGIN_Y = 54.0

#: Adjacency counts are coloured by wavelength, so a higher count is bluer and
#: therefore reads as more energetic -- the same ordering the other games use.
COUNT_NM = [spectral_band(1.0 - min(n, 8) / 8.0) for n in range(9)]

BINDINGS = {
    "ArrowUp": Action.UP,
    "ArrowDown": Action.DOWN,
    "ArrowLeft": Action.LEFT,
    "ArrowRight": Action.RIGHT,
    "w": Action.UP,
    "s": Action.DOWN,
    "a": Action.LEFT,
    "d": Action.RIGHT,
    "Enter": Action.CONFIRM,
    " ": Action.CONFIRM,
    "f": Action.MENU,
    "r": Action.CANCEL,
    "q": Action.SHOULDER_L,
    "e": Action.SHOULDER_R,
}

#: Held-direction auto-repeat, so crossing a 30-wide board is not 30 presses.
REPEAT_DELAY = 0.30
REPEAT_RATE = 0.07


class MinesweeperChiGame(chigame.Game):
    """Renders and drives a :class:`MinesweeperGame` with a pad cursor."""

    title = "Minesweeper"
    background = (0.030, 0.034, 0.042, 1.0)
    music_context = "underworld"

    def setup(self, host) -> None:
        """Bind the controller and start on the first preset.

        Parameters
        ----------
        host : chisurf.gui.chigame.game.GameHost
            The host running this game.
        """
        self.host = host
        host.keys.bindings = dict(BINDINGS)
        self.difficulty_names = list(DIFFICULTIES)
        self.difficulty_index = 0
        self.game = MinesweeperGame()
        self.message = ""
        self._repeat: dict[Action, float] = {}
        self.apply_difficulty()

    def apply_difficulty(self) -> None:
        """Configure the board for the selected preset and recentre the view."""
        rows, columns, mines = DIFFICULTIES[self.difficulty_names[self.difficulty_index]]
        self.game.configure(rows, columns, mines)
        self.cursor_row = rows // 2
        self.cursor_col = columns // 2
        self.message = ""
        width = columns * CELL
        height = rows * CELL
        self.host.camera.center[:] = (
            ORIGIN_X + width * 0.5,
            ORIGIN_Y + height * 0.5 - 4.0,
        )
        # The view must fit the board's *width* as well as its height. Sizing it
        # from the height alone works for the square Beginner board and clips
        # the 30-column Expert one straight off the sides. The camera spans
        # `height * aspect` horizontally, so the width requirement has to be
        # converted back into a height; MIN_ASPECT is a conservative stand-in
        # for a window that has not been laid out yet.
        MIN_ASPECT = 0.80
        self.host.camera.height = max(height + 150.0, (width + 70.0) / MIN_ASPECT)

    @property
    def rows(self) -> int:
        """Board height in cells.

        Returns
        -------
        int
            Number of rows.
        """
        return self.game.rows

    @property
    def columns(self) -> int:
        """Board width in cells.

        Returns
        -------
        int
            Number of columns.
        """
        return self.game.columns

    def update(self, dt: float, keys) -> None:
        """Advance one frame.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        if keys.just_pressed(Action.CANCEL):
            self.game.reset()
            self.message = ""
            return
        if keys.just_pressed(Action.SHOULDER_L) or keys.just_pressed(Action.SHOULDER_R):
            step = 1 if keys.just_pressed(Action.SHOULDER_R) else -1
            self.difficulty_index = (self.difficulty_index + step) % len(self.difficulty_names)
            self.apply_difficulty()
            return

        self._move_cursor(dt, keys)

        if self.game.status is not GameStatus.ACTIVE:
            return
        if keys.just_pressed(Action.CONFIRM):
            result = self.game.reveal(self.cursor_row, self.cursor_col)
            self.message = result.message
            self.host.audio.sfx("reveal", 620.0)
        elif keys.just_pressed(Action.MENU):
            result = self.game.toggle_flag(self.cursor_row, self.cursor_col)
            self.message = result.message
            self.host.audio.sfx("flag", 480.0)

    def _move_cursor(self, dt: float, keys) -> None:
        """Walk the cursor, repeating while a direction is held.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        steps = {
            Action.UP: (-1, 0),
            Action.DOWN: (1, 0),
            Action.LEFT: (0, -1),
            Action.RIGHT: (0, 1),
        }
        for action, (dr, dc) in steps.items():
            if keys.just_pressed(action):
                self._step(dr, dc)
                self._repeat[action] = -REPEAT_DELAY
            elif keys.is_held(action):
                self._repeat[action] = self._repeat.get(action, 0.0) + dt
                while self._repeat[action] >= REPEAT_RATE:
                    self._repeat[action] -= REPEAT_RATE
                    self._step(dr, dc)
            else:
                self._repeat.pop(action, None)

    def _step(self, dr: int, dc: int) -> None:
        """Move the cursor one cell, clamped to the board.

        Parameters
        ----------
        dr, dc : int
            Row and column deltas.
        """
        self.cursor_row = min(max(self.cursor_row + dr, 0), self.rows - 1)
        self.cursor_col = min(max(self.cursor_col + dc, 0), self.columns - 1)

    def _cell_center(self, row: int, col: int) -> tuple[float, float]:
        """World position of a cell's centre.

        Parameters
        ----------
        row, col : int
            Cell coordinates.

        Returns
        -------
        tuple of float
            Centre in world units.
        """
        return ORIGIN_X + (col + 0.5) * CELL, ORIGIN_Y + (row + 0.5) * CELL

    def draw(self, scene) -> None:
        """Queue the frame.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        """
        width = self.columns * CELL
        height = self.rows * CELL

        for row in range(self.rows):
            for col in range(self.columns):
                cell = self.game.board[row][col]
                at = self._cell_center(row, col)
                if not cell.revealed:
                    scene.draw(
                        "ui",
                        "pixel",
                        at=at,
                        size=(CELL - 2.0, CELL - 2.0),
                        color=(0.19, 0.21, 0.25, 1.0),
                    )
                    if cell.flagged:
                        scene.draw(
                            "photon",
                            "flag",
                            at=at,
                            size=(CELL * 0.34, CELL * 0.34),
                            emission_nm=488.0,
                        )
                    continue
                scene.draw(
                    "ui",
                    "pixel",
                    at=at,
                    size=(CELL - 2.0, CELL - 2.0),
                    color=(0.10, 0.11, 0.13, 1.0),
                )
                if cell.mine:
                    # A hot pixel: it is emitting when it should not be.
                    scene.draw(
                        "photon", "hot", at=at, size=(CELL * 0.5, CELL * 0.5), emission_nm=660.0
                    )
                elif cell.adjacent_mines:
                    nm = COUNT_NM[cell.adjacent_mines]
                    scene.text(
                        str(cell.adjacent_mines),
                        at=(at[0], at[1]),
                        height=CELL * 0.62,
                        align="center",
                        color=(*wavelength_to_srgb(nm), 1.0),
                    )

        # The cursor is game state, so picking is exact by construction.
        scene.draw(
            "aura",
            "cursor",
            at=self._cell_center(self.cursor_row, self.cursor_col),
            size=(CELL + 4.0, CELL + 4.0),
        )

        top = ORIGIN_Y - 34.0
        scene.text(
            f"Hot pixels: {self.game.flags_remaining}",
            at=(ORIGIN_X, top),
            height=13.0,
            color=(0.78, 0.82, 0.88, 1.0),
        )
        scene.text(
            self.difficulty_names[self.difficulty_index],
            at=(ORIGIN_X + width, top),
            height=13.0,
            align="right",
            color=(0.44, 0.48, 0.55, 1.0),
        )

        if self.game.status is GameStatus.WON:
            banner, tint = "Array mapped", (0.35, 0.85, 0.80, 1.0)
        elif self.game.status is GameStatus.LOST:
            banner, tint = "Detector saturated", (0.90, 0.32, 0.30, 1.0)
        else:
            banner, tint = self.message, (0.44, 0.48, 0.55, 1.0)
        if banner:
            scene.text(
                banner,
                at=(ORIGIN_X + width * 0.5, ORIGIN_Y + height + 22.0),
                height=16.0,
                align="center",
                color=tint,
            )

        scene.text(
            "Move   Confirm scan   Menu flag",
            at=(ORIGIN_X + width * 0.5, ORIGIN_Y + height + 44.0),
            height=12.0,
            align="center",
            color=(0.44, 0.48, 0.55, 1.0),
        )
        scene.text(
            "Cancel reset   L/R preset",
            at=(ORIGIN_X + width * 0.5, ORIGIN_Y + height + 62.0),
            height=12.0,
            align="center",
            color=(0.44, 0.48, 0.55, 1.0),
        )


@persist_plugin_state("minesweeper")
class MinesweeperWidget(QtWidgets.QWidget):
    """Dockable container hosting the game.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Minesweeper")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.game = MinesweeperChiGame()
        canvas, self.host = chigame.create_widget(self.game, parent=self)
        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 0)
        bar.addWidget(chigame.sound_button(self.host, self))
        bar.addStretch(1)
        layout.addLayout(bar)
        layout.addWidget(canvas)
        self.resize(560, 620)
