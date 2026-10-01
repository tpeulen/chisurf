"""Tetris rules shared by Qt and EMTK, with no GUI or GPU imports."""
from __future__ import annotations

import random
from types import SimpleNamespace

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
SHAPE_NM = [405.0 + i / (len(SHAPES) - 1) * 275.0 for i in range(len(SHAPES))]

#: The square piece is symmetric, so rotating it is a no-op.
SQUARE = 3

#: Points per number of lines cleared at once, indexed by count.
LINE_SCORE = [0, 100, 300, 500, 800]

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


class TetrisModel:
    def __init__(self, host=None):
        self.host = host or SimpleNamespace(audio=SimpleNamespace(sfx=lambda *args: None))
        self.restart()

    def restart(self) -> None:
        """Clear the well and start a fresh run."""
        # ``None`` is an empty cell; anything else is a settled shape index.
        self.well: list[list[int | None]] = [[None for _ in range(BOARD_W)] for _ in range(BOARD_H)]
        self.score = 0
        self.lines = 0
        self.level = 1
        self.paused = False
        self.muted = False
        self.over = False
        self._fall_timer = 0.0
        self._repeat_timer = 0.0
        self._repeat_action: str | None = None
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
        if keys.just_pressed('menu'):
            self.paused = not self.paused
        if keys.just_pressed('cancel'):
            self.restart()
            return
        if self.over:
            if keys.just_pressed('confirm'):
                self.restart()
            return
        if self.paused:
            return

        self._handle_steering(dt, keys)

        if keys.just_pressed('shoulder_r'):
            self.drop_down()
            return

        interval = SOFT_DROP_INTERVAL if keys.is_held('down') else self.fall_interval
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
        if keys.just_pressed('confirm') and self.shape != SQUARE:
            self.try_move(rotated(self.coords), self.x, self.y)

        for action, step in (('left', -1), ('right', 1)):
            if keys.just_pressed(action):
                self.try_move(self.coords, self.x + step, self.y)
                self._repeat_action = action
                self._repeat_timer = -REPEAT_DELAY
            elif keys.is_held(action) and self._repeat_action == action:
                self._repeat_timer += dt
                while self._repeat_timer >= REPEAT_RATE:
                    self._repeat_timer -= REPEAT_RATE
                    self.try_move(self.coords, self.x + step, self.y)
            elif self._repeat_action == action and not keys.is_held(action):
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

