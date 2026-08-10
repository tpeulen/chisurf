"""The data <-> clip-space <-> pixel mapping, free of Qt and of the GPU.

Everything positional the backend does goes through this one class: the vertex
geometry handed to the renderer, the tick positions drawn by ``QPainter``, and
the inverse used to turn a mouse position back into data. Keeping the three in
one place is what stops a cursor readout from disagreeing with the curve under
it — the classic symptom of an axis whose forward and inverse transforms were
written twice.
"""

from __future__ import annotations

import math

import numpy as np

#: Smallest value a log axis will consider; below this a decade span is
#: meaningless and the transform would return infinities.
_LOG_FLOOR = 1e-300


class PixelView:
    """Maps data coordinates to clip space and to widget pixels.

    Parameters
    ----------
    x_range, y_range : tuple of float
        Visible ``(min, max)`` in data units.
    log_x, log_y : bool
        Whether the axis is logarithmic.
    invert_y : bool
        Draw y increasing downwards (image convention).
    """

    def __init__(
        self,
        x_range: tuple[float, float] = (0.0, 1.0),
        y_range: tuple[float, float] = (0.0, 1.0),
        *,
        log_x: bool = False,
        log_y: bool = False,
        invert_y: bool = False,
    ):
        self.x_range = list(x_range)
        self.y_range = list(y_range)
        self.log_x = log_x
        self.log_y = log_y
        self.invert_y = invert_y

    # -- forward --------------------------------------------------------
    @staticmethod
    def _axis_bounds(rng, log: bool) -> tuple[float, float]:
        """Return the axis bounds in the space the axis is linear in."""
        lo, hi = float(rng[0]), float(rng[1])
        if log:
            lo = math.log10(max(lo, _LOG_FLOOR))
            hi = math.log10(max(hi, _LOG_FLOOR))
        if hi - lo == 0:
            hi = lo + 1.0
        return lo, hi

    def _to_axis(self, values, log: bool):
        """Map data values into the axis's linear space."""
        arr = np.asarray(values, dtype=np.float64)
        if not log:
            return arr
        with np.errstate(divide="ignore", invalid="ignore"):
            # A non-positive sample has no place on a log axis; NaN breaks the
            # line there rather than clamping it onto the bottom edge, which
            # would draw a spike that is not in the data.
            return np.where(arr > 0, np.log10(np.where(arr > 0, arr, 1.0)), np.nan)

    def transform_array(self, xs, ys) -> tuple[np.ndarray, np.ndarray]:
        """Map data arrays to clip space ``[-1, 1]``.

        Returns
        -------
        tuple of numpy.ndarray
            ``(nx, ny)``, with non-representable samples set to NaN.
        """
        xlo, xhi = self._axis_bounds(self.x_range, self.log_x)
        ylo, yhi = self._axis_bounds(self.y_range, self.log_y)
        ax = self._to_axis(xs, self.log_x)
        ay = self._to_axis(ys, self.log_y)
        nx = 2.0 * (ax - xlo) / (xhi - xlo) - 1.0
        ny = 2.0 * (ay - ylo) / (yhi - ylo) - 1.0
        if self.invert_y:
            ny = -ny
        return nx, ny

    def data_to_ndc(self, x: float, y: float) -> tuple[float, float]:
        """Map one data point to clip space."""
        nx, ny = self.transform_array(np.array([x]), np.array([y]))
        return float(nx[0]), float(ny[0])

    def data_to_pixel(self, x, y, w: int, h: int, margins) -> tuple[float, float]:
        """Map a data point to widget pixels."""
        nx, ny = self.data_to_ndc(x, y)
        ix, iy, pw, ph = margins.plot_rect(w, h)
        return ix + (nx + 1.0) * 0.5 * pw, iy + (1.0 - (ny + 1.0) * 0.5) * ph

    # -- inverse --------------------------------------------------------
    def pixel_to_data(self, px: float, py: float, w: int, h: int,
                      margins) -> tuple[float, float]:
        """Map widget pixels back to data coordinates."""
        ix, iy, pw, ph = margins.plot_rect(w, h)
        nx = 2.0 * (px - ix) / max(pw, 1) - 1.0
        ny = 1.0 - 2.0 * (py - iy) / max(ph, 1)
        if self.invert_y:
            ny = -ny
        return (self._from_ndc(nx, self.x_range, self.log_x),
                self._from_ndc(ny, self.y_range, self.log_y))

    @classmethod
    def _from_ndc(cls, ndc: float, rng, log: bool) -> float:
        """Invert one axis's clip-space mapping."""
        lo, hi = cls._axis_bounds(rng, log)
        v = lo + (ndc + 1.0) * 0.5 * (hi - lo)
        return 10.0 ** v if log else v
