"""The room camera — the screen as a place, not a window.

A plain follow camera makes a top-down world feel like a scrolling map. The
reference instead locks the view to a grid of rooms (320 by 176 world units —
twenty by eleven 16-pixel tiles) and glides to the neighbouring room when the
player crosses its edge, which is what makes each screen read as a *place*:
its layout is stable, its edges are walls, and moving between places is an
event. This is the port of ``camera_grid.gd``: cell tracking, a 0.8-second
sine-in-out glide, and a snap on teleport.
"""

from __future__ import annotations

import math

import numpy as np

from .render import Camera

#: The reference's room grid: 320x176 world units, twenty by eleven tiles.
ROOM_SIZE = (320.0, 176.0)

#: Seconds a room-to-room glide takes.
GLIDE_TIME = 0.8


class RoomCamera(Camera):
    """A camera that lives on a grid of rooms.

    Parameters
    ----------
    room_size : tuple of float, optional
        Room width and height in world units.
    transition_time : float, optional
        Seconds a glide between rooms takes.
    """

    def __init__(
        self,
        room_size: tuple[float, float] = ROOM_SIZE,
        transition_time: float = GLIDE_TIME,
    ) -> None:
        super().__init__(center=(room_size[0] * 0.5, room_size[1] * 0.5), height=room_size[1])
        self.room_size = np.asarray(room_size, dtype=np.float64)
        self.transition_time = float(transition_time)
        self.cell = np.array([0, 0], dtype=np.int64)
        self._glide_from: np.ndarray | None = None
        self._glide_time = 0.0
        self.on_cell_changed = None
        self.on_glide_finished = None

    # -- placement ---------------------------------------------------------

    def cell_of(self, position) -> np.ndarray:
        """Which room a world position belongs to.

        Parameters
        ----------
        position : array-like
            World position.

        Returns
        -------
        numpy.ndarray
            ``(column, row)`` room indices.
        """
        point = np.asarray(position, dtype=np.float64)
        return np.round(point / self.room_size).astype(np.int64)

    def cell_centre(self, cell) -> np.ndarray:
        """The world position at a room's centre.

        Parameters
        ----------
        cell : array-like
            ``(column, row)`` room indices.

        Returns
        -------
        numpy.ndarray
        """
        return np.asarray(cell, dtype=np.float64) * self.room_size

    def snap_to(self, position) -> None:
        """Jump to a position's room with no glide.

        Parameters
        ----------
        position : array-like
            World position.
        """
        self.cell = self.cell_of(position)
        self.center[:] = self.cell_centre(self.cell)
        self._glide_from = None

    # -- per frame ---------------------------------------------------------

    def follow(self, position, snap: bool = False) -> None:
        """Track a position, gliding when it changes rooms.

        Parameters
        ----------
        position : array-like
            The position to keep on screen.
        snap : bool, optional
            Teleport instead of gliding (on map changes).
        """
        cell = self.cell_of(position)
        if not np.array_equal(cell, self.cell):
            self.cell = cell
            if snap:
                self.center[:] = self.cell_centre(cell)
                self._glide_from = None
            else:
                self._glide_from = self.center.copy()
                self._glide_time = 0.0
            if self.on_cell_changed is not None:
                self.on_cell_changed(tuple(self.cell))

    def update(self, dt: float) -> bool:
        """Advance an in-progress glide.

        Parameters
        ----------
        dt : float
            Frame step in seconds.

        Returns
        -------
        bool
            Whether a glide is still running.
        """
        if self._glide_from is None:
            return False
        self._glide_time += dt
        t = min(1.0, self._glide_time / self.transition_time)
        eased = 0.5 - 0.5 * math.cos(math.pi * t)
        target = self.cell_centre(self.cell)
        self.center[:] = self._glide_from + (target - self._glide_from) * eased
        if t >= 1.0:
            self._glide_from = None
            if self.on_glide_finished is not None:
                self.on_glide_finished(tuple(self.cell))
        return True

    @property
    def gliding(self) -> bool:
        """Whether a room transition is in flight.

        Returns
        -------
        bool
        """
        return self._glide_from is not None
