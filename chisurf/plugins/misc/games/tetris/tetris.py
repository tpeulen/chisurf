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

import random

from qtpy import QtWidgets

from chisurf.gui import chigame
from chisurf.gui.chigame.assets import spectral_band
from chisurf.gui.chigame.input import Action

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - stand-alone use

    def persist_plugin_state(name):
        """Return an identity decorator when the host is unavailable."""
        return lambda cls: cls


BOARD_W = 10
BOARD_H = 22

#: Seconds a piece takes to fall one row, and how much a soft drop accelerates.
FALL_INTERVAL = 0.4
SOFT_DROP_INTERVAL = 0.04

#: How long a held direction waits before repeating, and the repeat period.
REPEAT_DELAY = 0.22
REPEAT_RATE = 0.06

#: The seven tetrominoes, as (x, y) offsets from their rotation centre.
SHAPES = [
    [(0, -1), (0, 0), (0, 1), (0, 2)],
    [(-1, -1), (-1, 0), (0, 0), (1, 0)],
    [(1, -1), (-1, 0), (0, 0), (1, 0)],
    [(0, -1), (1, -1), (0, 0), (1, 0)],
    [(0, -1), (1, -1), (-1, 0), (0, 0)],
    [(-1, -1), (0, -1), (1, -1), (0, 0)],
    [(-1, -1), (0, -1), (0, 0), (1, 0)],
]

#: One emission wavelength per shape, spread across the visible range so a
#: settled well reads as an accumulated spectrum rather than a colour salad.
SHAPE_NM = [spectral_band(i / (len(SHAPES) - 1)) for i in range(len(SHAPES))]

#: The square piece is symmetric, so rotating it is a no-op.
SQUARE = 3

#: Points per number of lines cleared at once, indexed by count.
LINE_SCORE = [0, 100, 300, 500, 800]

BINDINGS = {
    "ArrowLeft": Action.LEFT,
    "ArrowRight": Action.RIGHT,
    "ArrowDown": Action.DOWN,
    "ArrowUp": Action.CONFIRM,
    "a": Action.LEFT,
    "d": Action.RIGHT,
    "s": Action.DOWN,
    "w": Action.CONFIRM,
    " ": Action.SHOULDER_R,
    "p": Action.MENU,
    "r": Action.CANCEL,
}


def rotated(coords: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Rotate a piece a quarter turn.

    Parameters
    ----------
    coords : list of tuple
        Offsets from the rotation centre.

    Returns
    -------
    list of tuple
        The rotated offsets.
    """
    return [(-y, x) for x, y in coords]


class TetrisGame(chigame.Game):
    """The rules and the drawing, free of Qt and of GPU objects."""

    title = "Tetris"
    background = (0.030, 0.034, 0.042, 1.0)
    music_context = "town"

    #: Cell size and well origin, in world units.
    CELL = 22.0
    ORIGIN_X = 40.0
    ORIGIN_Y = 30.0

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

    def restart(self) -> None:
        """Clear the well and start a fresh run."""
        # ``None`` is an empty cell; anything else is a settled shape index.
        self.well: list[list[int | None]] = [
            [None for _ in range(BOARD_W)] for _ in range(BOARD_H)
        ]
        self.score = 0
        self.lines = 0
        self.level = 1
        self.paused = False
        self.muted = False
        self.over = False
        self._fall_timer = 0.0
        self._repeat_timer = 0.0
        self._repeat_action: Action | None = None
        self.new_piece()

    def new_piece(self) -> None:
        """Spawn the next piece at the top of the well."""
        self.shape = random.randrange(len(SHAPES))
        self.coords = list(SHAPES[self.shape])
        self.x = BOARD_W // 2
        self.y = 1
        if not self.fits(self.coords, self.x, self.y):
            self.over = True

    @property
    def fall_interval(self) -> float:
        """Seconds per row at the current level.

        Returns
        -------
        float
            Falls faster as the level rises, with a floor so it stays playable.
        """
        return max(0.06, FALL_INTERVAL * (0.85 ** (self.level - 1)))

    def fits(self, coords, x: int, y: int) -> bool:
        """Whether a piece would sit legally at a position.

        Parameters
        ----------
        coords : list of tuple
            Offsets from the rotation centre.
        x, y : int
            Candidate centre, in cells.

        Returns
        -------
        bool
            True when every cell is inside the well and unoccupied.
        """
        for dx, dy in coords:
            cx, cy = x + dx, y + dy
            if cx < 0 or cx >= BOARD_W or cy < 0 or cy >= BOARD_H:
                return False
            if self.well[cy][cx] is not None:
                return False
        return True

    def try_move(self, coords, x: int, y: int) -> bool:
        """Move the piece if the destination is legal.

        Parameters
        ----------
        coords : list of tuple
            Offsets to adopt.
        x, y : int
            Destination centre.

        Returns
        -------
        bool
            True when the move was applied.
        """
        if not self.fits(coords, x, y):
            return False
        self.coords = list(coords)
        self.x = x
        self.y = y
        return True

    def _sfx(self, name: str, frequency: float) -> None:
        """Play a sound effect unless muted.

        Parameters
        ----------
        name : str
            Effect name.
        frequency : float
            Pitch in Hz.
        """
        if not self.muted:
            self.host.audio.sfx(name, frequency)

    def update(self, dt: float, keys) -> None:
        """Advance one frame.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        if keys.just_pressed(Action.MENU):
            self.paused = not self.paused
        if keys.just_pressed(Action.CANCEL):
            self.restart()
            return
        if self.over:
            if keys.just_pressed(Action.CONFIRM):
                self.restart()
            return
        if self.paused:
            return

        self._handle_steering(dt, keys)

        if keys.just_pressed(Action.SHOULDER_R):
            self.drop_down()
            return

        interval = SOFT_DROP_INTERVAL if keys.is_held(Action.DOWN) else self.fall_interval
        self._fall_timer += dt
        while self._fall_timer >= interval and not self.over:
            self._fall_timer -= interval
            self.one_line_down()

    def _handle_steering(self, dt: float, keys) -> None:
        """Move and rotate, with auto-repeat on a held direction.

        A gamepad has no key auto-repeat of its own, so a held direction has to
        repeat here or the piece moves exactly one cell per press.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        if keys.just_pressed(Action.CONFIRM) and self.shape != SQUARE:
            self.try_move(rotated(self.coords), self.x, self.y)

        for action, step in ((Action.LEFT, -1), (Action.RIGHT, 1)):
            if keys.just_pressed(action):
                self.try_move(self.coords, self.x + step, self.y)
                self._repeat_action = action
                self._repeat_timer = -REPEAT_DELAY
            elif keys.is_held(action) and self._repeat_action is action:
                self._repeat_timer += dt
                while self._repeat_timer >= REPEAT_RATE:
                    self._repeat_timer -= REPEAT_RATE
                    self.try_move(self.coords, self.x + step, self.y)
            elif self._repeat_action is action and not keys.is_held(action):
                self._repeat_action = None

    def one_line_down(self) -> None:
        """Drop the piece a row, settling it when it cannot fall."""
        if not self.try_move(self.coords, self.x, self.y + 1):
            self.piece_dropped()

    def drop_down(self) -> None:
        """Drop the piece as far as it will go, then settle it."""
        while self.try_move(self.coords, self.x, self.y + 1):
            pass
        self.piece_dropped()

    def piece_dropped(self) -> None:
        """Write the piece into the well and take the next one."""
        for dx, dy in self.coords:
            self.well[self.y + dy][self.x + dx] = self.shape
        self._sfx("settle", 300.0)
        self.remove_full_lines()
        if not self.over:
            self.new_piece()

    def remove_full_lines(self) -> None:
        """Clear completed rows and score them."""
        kept = [row for row in self.well if any(cell is None for cell in row)]
        cleared = BOARD_H - len(kept)
        if not cleared:
            return
        for _ in range(cleared):
            kept.insert(0, [None for _ in range(BOARD_W)])
        self.well = kept
        self.lines += cleared
        self.score += LINE_SCORE[min(cleared, 4)] * self.level
        self.level = 1 + self.lines // 10
        self._sfx("clear", 700.0 + 80.0 * cleared)

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
            "ui", "well",
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
        scene.text("COUNTS", at=(panel_x, 60.0), height=13.0, align="center",
                   color=(0.44, 0.48, 0.55, 1.0))
        scene.text(f"{self.score}", at=(panel_x, 84.0), height=24.0, align="center")
        scene.text("LINES", at=(panel_x, 124.0), height=13.0, align="center",
                   color=(0.44, 0.48, 0.55, 1.0))
        scene.text(f"{self.lines}", at=(panel_x, 146.0), height=20.0, align="center")
        scene.text("GAIN", at=(panel_x, 184.0), height=13.0, align="center",
                   color=(0.44, 0.48, 0.55, 1.0))
        scene.text(f"{self.level}", at=(panel_x, 206.0), height=20.0, align="center")

        if self.paused:
            scene.text("HELD", at=(self.ORIGIN_X + width * 0.5, self.ORIGIN_Y + height * 0.5),
                       height=36.0, align="center", color=(0.35, 0.85, 0.80, 1.0))
        if self.over:
            scene.draw("ui", "panel",
                       at=(self.ORIGIN_X + width * 0.5, self.ORIGIN_Y + height * 0.5),
                       size=(width + 4.0, 96.0))
            scene.text("Channel full", at=(self.ORIGIN_X + width * 0.5,
                                           self.ORIGIN_Y + height * 0.5 - 12.0),
                       height=24.0, align="center", color=(0.90, 0.32, 0.30, 1.0))
            scene.text("Confirm to reset", at=(self.ORIGIN_X + width * 0.5,
                                               self.ORIGIN_Y + height * 0.5 + 18.0),
                       height=14.0, align="center")

        scene.text(
            "Move  Confirm rotate  Down soft  R drop",
            at=(self.ORIGIN_X + width * 0.5 + 30.0, self.ORIGIN_Y + height + 14.0),
            height=11.0, align="center", color=(0.44, 0.48, 0.55, 1.0),
        )
        scene.text(
            "Menu hold  Cancel reset",
            at=(self.ORIGIN_X + width * 0.5 + 30.0, self.ORIGIN_Y + height + 30.0),
            height=11.0, align="center", color=(0.44, 0.48, 0.55, 1.0),
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
            scene.draw("photon", "halo", at=at, size=(self.CELL * 0.5, self.CELL * 0.5),
                       emission_nm=nm)
        scene.draw("band", f"{nm:.0f}", at=at,
                   size=(self.CELL - 3.0, self.CELL - 3.0), emission_nm=nm)


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
        layout.addWidget(canvas)
        self.resize(520, 620)
