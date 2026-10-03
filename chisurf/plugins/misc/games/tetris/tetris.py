"""Tetris, on the chigame engine.

Ported from a hand-written ``QPainter`` board. The rules, the piece table, the
board size and the scoring carry over unchanged -- but the game logic is lifted
*out* of the widget, so the whole simulation now steps with no Qt and no window.

Tetris is the engine's grid-and-text test: a 10x22 well of cells plus a
continuously changing score readout.

The seven pieces are spectral packets rather than arcade colours: each shape has
its own emission wavelength, so a filled well reads as a spectrum accumulating
in a detection channel.
"""

from __future__ import annotations

from qtpy import QtWidgets

from chisurf.gui import chigame
from chisurf.gui.chigame.input import Action

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - stand-alone use

    def persist_plugin_state(name):
        """Return an identity decorator when the host is unavailable."""
        return lambda cls: cls


from .model import (
    BOARD_H,
    BOARD_W,
    FALL_INTERVAL,
    LINE_SCORE,
    REPEAT_DELAY,
    REPEAT_RATE,
    SHAPE_NM,
    SHAPES,
    SOFT_DROP_INTERVAL,
    SQUARE,
    TetrisModel,
    rotated,
)

BINDINGS = {
    "ArrowLeft": Action.LEFT,
    "ArrowRight": Action.RIGHT,
    "ArrowDown": Action.DOWN,
    "ArrowUp": Action.CONFIRM,
    " ": Action.SHOULDER_R,
    "p": Action.MENU,
    "r": Action.CANCEL,
}


class TetrisGame(TetrisModel, chigame.Game):
    """The rules and the drawing, free of Qt and of GPU objects."""

    title = "Tetris"
    background = (0.030, 0.034, 0.042, 1.0)
    music_context = "town"

    #: Cell size and well origin, in world units.
    CELL = 22.0
    ORIGIN_X = 40.0
    ORIGIN_Y = 30.0

    def __init__(self):
        # The legacy host owns initial setup; avoid consuming an extra random
        # piece before setup() starts the original run.
        pass

    def setup(self, host) -> None:
        """Bind the controller and start a game.

        Parameters
        ----------
        host : chisurf.gui.chigame.game.GameHost
            The host running this game.
        """
        self.host = host
        host.keys.bindings = dict(BINDINGS)
        width = BOARD_W * self.CELL
        height = BOARD_H * self.CELL
        # The view has to leave room *below* the well for the two help lines;
        # sizing it to the well alone clipped them against the bottom edge.
        host.camera.center[:] = (
            self.ORIGIN_X + width * 0.5 + 60.0,
            self.ORIGIN_Y + height * 0.5 + 14.0,
        )
        host.camera.height = height + 2 * self.ORIGIN_Y + 44.0
        self.restart()

    def update(self, dt, keys):
        class QtInputs:
            def just_pressed(self, action):
                return keys.just_pressed(Action(action))
            def is_held(self, action):
                return keys.is_held(Action(action))
        super().update(dt, QtInputs())

    def _cell_center(self, col: int, row: int) -> tuple[float, float]:
        """World position of a cell's centre.

        Parameters
        ----------
        col, row : int
            Cell coordinates.

        Returns
        -------
        tuple of float
            Centre in world units.
        """
        return (
            self.ORIGIN_X + (col + 0.5) * self.CELL,
            self.ORIGIN_Y + (row + 0.5) * self.CELL,
        )

    def draw(self, scene) -> None:
        """Queue the frame.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        """
        width = BOARD_W * self.CELL
        height = BOARD_H * self.CELL

        # The well itself: a dark channel with a thin housing.
        scene.draw(
            "ui",
            "well",
            at=(self.ORIGIN_X + width * 0.5, self.ORIGIN_Y + height * 0.5),
            size=(width + 6.0, height + 6.0),
            color=(0.13, 0.145, 0.17, 1.0),
        )
        for col in range(BOARD_W):
            for row in range(BOARD_H):
                shape = self.well[row][col]
                if shape is None:
                    continue
                self._draw_cell(scene, col, row, shape)

        if not self.over:
            for dx, dy in self.coords:
                self._draw_cell(scene, self.x + dx, self.y + dy, self.shape, live=True)

        panel_x = self.ORIGIN_X + width + 70.0
        scene.text(
            "COUNTS", at=(panel_x, 60.0), height=13.0, align="center", color=(0.44, 0.48, 0.55, 1.0)
        )
        scene.text(f"{self.score}", at=(panel_x, 84.0), height=24.0, align="center")
        scene.text(
            "LINES", at=(panel_x, 124.0), height=13.0, align="center", color=(0.44, 0.48, 0.55, 1.0)
        )
        scene.text(f"{self.lines}", at=(panel_x, 146.0), height=20.0, align="center")
        scene.text(
            "GAIN", at=(panel_x, 184.0), height=13.0, align="center", color=(0.44, 0.48, 0.55, 1.0)
        )
        scene.text(f"{self.level}", at=(panel_x, 206.0), height=20.0, align="center")

        if self.paused:
            scene.text(
                "HELD",
                at=(self.ORIGIN_X + width * 0.5, self.ORIGIN_Y + height * 0.5),
                height=36.0,
                align="center",
                color=(0.35, 0.85, 0.80, 1.0),
            )
        if self.over:
            scene.draw(
                "ui",
                "panel",
                at=(self.ORIGIN_X + width * 0.5, self.ORIGIN_Y + height * 0.5),
                size=(width + 4.0, 96.0),
            )
            scene.text(
                "Channel full",
                at=(self.ORIGIN_X + width * 0.5, self.ORIGIN_Y + height * 0.5 - 12.0),
                height=24.0,
                align="center",
                color=(0.90, 0.32, 0.30, 1.0),
            )
            scene.text(
                "Confirm to reset",
                at=(self.ORIGIN_X + width * 0.5, self.ORIGIN_Y + height * 0.5 + 18.0),
                height=14.0,
                align="center",
            )

        scene.text(
            "Move  Confirm rotate  Down soft  R drop",
            at=(self.ORIGIN_X + width * 0.5 + 30.0, self.ORIGIN_Y + height + 14.0),
            height=11.0,
            align="center",
            color=(0.44, 0.48, 0.55, 1.0),
        )
        scene.text(
            "Menu hold  Cancel reset",
            at=(self.ORIGIN_X + width * 0.5 + 30.0, self.ORIGIN_Y + height + 30.0),
            height=11.0,
            align="center",
            color=(0.44, 0.48, 0.55, 1.0),
        )

    def _draw_cell(self, scene, col: int, row: int, shape: int, live: bool = False) -> None:
        """Draw one occupied cell as a spectral packet.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        col, row : int
            Cell coordinates.
        shape : int
            Which tetromino, which selects the wavelength.
        live : bool, optional
            Whether this is the falling piece. The live piece carries a halo so
            it is unmistakable against settled cells of the same colour --
            dimming the settled ones instead just made the well muddy.
        """
        at = self._cell_center(col, row)
        nm = SHAPE_NM[shape]
        if live:
            scene.draw(
                "photon", "halo", at=at, size=(self.CELL * 0.5, self.CELL * 0.5), emission_nm=nm
            )
        scene.draw(
            "band", f"{nm:.0f}", at=at, size=(self.CELL - 3.0, self.CELL - 3.0), emission_nm=nm
        )


@persist_plugin_state("tetris")
class Tetris(QtWidgets.QWidget):
    """Dockable container hosting the game.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tetris")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.game = TetrisGame()
        canvas, self.host = chigame.create_widget(self.game, parent=self)
        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 0)
        bar.addWidget(chigame.sound_button(self.host, self))
        bar.addStretch(1)
        layout.addLayout(bar)
        layout.addWidget(canvas)
        self.resize(520, 620)
