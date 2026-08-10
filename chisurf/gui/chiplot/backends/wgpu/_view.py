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

#: Exponent range a log axis is allowed to reach. ``10 ** 309`` is not a float,
#: and the exponent is *not* bounded by the data: it comes from a pixel
#: position, which is unbounded because a drag keeps delivering mouse events
#: after the cursor has left the panel. Unclamped, moving the mouse off a
#: logarithmic plot raises ``OverflowError: (34, 'Result too large')`` out of
#: the move handler.
_LOG_MAX_EXP = 300.0
_LOG_MIN_EXP = -300.0


def pow10(exponent: float) -> float:
    """Return ``10 ** exponent``, clamped to what a float can hold.

    Every conversion out of log space goes through here — the transform, the
    inverse, the tick range, and the pan/zoom arithmetic — so none of them can
    produce a value the next one cannot represent.
    """
    if not math.isfinite(exponent):
        return _LOG_FLOOR if exponent < 0 else 10.0 ** _LOG_MAX_EXP
    return 10.0 ** min(max(exponent, _LOG_MIN_EXP), _LOG_MAX_EXP)


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
        invert_x: bool = False,
        invert_y: bool = False,
    ):
        self.x_range = list(x_range)
        self.y_range = list(y_range)
        self.log_x = log_x
        self.log_y = log_y
        self.invert_x = invert_x
        self.invert_y = invert_y

    # -- forward --------------------------------------------------------
    #: Decades an empty or non-positive log axis falls back to spanning.
    _LOG_FALLBACK_DECADES = 3.0

    @classmethod
    def _axis_bounds(cls, rng, log: bool) -> tuple[float, float]:
        """Return the axis bounds in the space the axis is linear in.

        A log axis whose low bound is non-positive cannot be taken literally.
        Flooring it at the smallest representable number is what an empty panel
        did — the default range is ``[0, 1]``, so a plot created with
        ``set_log(y=True)`` before any data came up spanning **three hundred
        decades**, with ``1e-300`` as its first tick. Falling back to a few
        decades below the top gives an axis a reader can use, and one that the
        first real data replaces anyway.
        """
        lo, hi = float(rng[0]), float(rng[1])
        if not math.isfinite(lo) or not math.isfinite(hi):
            # A range that already overflowed: fall back rather than propagate.
            lo, hi = (0.0, 1.0) if not log else (_LOG_FLOOR, 1.0)
        if log:
            if hi <= 0:
                hi = 1.0
            if lo <= 0:
                lo = hi * pow10(-cls._LOG_FALLBACK_DECADES)
            lo = min(max(math.log10(max(lo, _LOG_FLOOR)), _LOG_MIN_EXP), _LOG_MAX_EXP)
            hi = min(max(math.log10(max(hi, _LOG_FLOOR)), _LOG_MIN_EXP), _LOG_MAX_EXP)
        if hi - lo == 0:
            hi = lo + 1.0
        return lo, hi

    def visible_range(self, axis: str = "x") -> tuple[float, float]:
        """Return an axis's range in **data** units, sanitised for its scale.

        The same numbers the transform uses, so ticks cannot be generated for a
        span the geometry does not draw — which is how an empty log panel got
        ticks from ``1e-300`` while its curves were mapped over three decades.

        Parameters
        ----------
        axis : str
            ``"x"`` or ``"y"``.

        Returns
        -------
        tuple of float
            ``(lo, hi)`` in data units.
        """
        log = self.log_x if axis == "x" else self.log_y
        rng = self.x_range if axis == "x" else self.y_range
        lo, hi = self._axis_bounds(rng, log)
        return (pow10(lo), pow10(hi)) if log else (lo, hi)

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
        if self.invert_x:
            nx = -nx
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
        if self.invert_x:
            nx = -nx
        if self.invert_y:
            ny = -ny
        return (self._from_ndc(nx, self.x_range, self.log_x),
                self._from_ndc(ny, self.y_range, self.log_y))

    @classmethod
    def _from_ndc(cls, ndc: float, rng, log: bool) -> float:
        """Invert one axis's clip-space mapping."""
        lo, hi = cls._axis_bounds(rng, log)
        v = lo + (ndc + 1.0) * 0.5 * (hi - lo)
        return pow10(v) if log else v
