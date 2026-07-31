r"""Velocity fields from image correlation: the arrows.

A single correlation carpet gives one velocity for the whole region it was
computed over. That is the right answer only when the sample has one velocity,
and biological flow almost never does -- a vessel has a profile across it, a
cell has traffic in one direction along one filament and none beside it. Tiling
the field of view and reading a velocity from each tile turns the one number
into a **map**, which is what gets drawn as a quiver plot on top of the image.

Two independent routes are here, and they are worth having both because they
fail differently:

:func:`stics_flow_map`
    Spatiotemporal image correlation. Each tile gets its own carpet over frame
    lags, and the correlation peak *moves* with the flow; a straight line
    through those peak positions is the velocity vector (Hebert, Costantino &
    Wiseman 2005). Two-dimensional and direct, but it needs the displacement to
    be resolvable within the tile, so it goes blind for a flow slower than
    roughly one pixel over the whole lag range.

:func:`pcf_flow_map`
    Pair correlation. For each position, correlate it with the point
    :math:`\pm\delta` away and see which direction produces a transit-time
    peak; the peak time is the speed. One-dimensional along the fast scan axis,
    but it resolves position down to the pixel and it is the route that sees a
    **barrier** -- a place where the correlation is absent in both directions
    while the local intensity is perfectly normal.

The quality number
------------------
Both routes return a ``quality`` per tile, and it is not decoration. A tile with
no directed transport still produces a velocity: peak jitter fitted to a line
gives a slope, and a slope is a speed. Drawing every arrow therefore paints a
convincing flow field onto a purely diffusive sample. ``quality`` is the
coefficient of determination of that straight-line fit, and
:meth:`FlowMap.quiver` drops the tiles that fail a threshold instead.

References
----------
Hebert, B., Costantino, S. & Wiseman, P. W. *Spatiotemporal image correlation
spectroscopy (STICS)*. Biophysical Journal 88, 3601-3614 (2005).

Digman, M. A. & Gratton, E. *Imaging barriers to diffusion by pair correlation
functions.* Biophysical Journal 97, 665-673 (2009).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

from .data import IcsSettings, IcsTiming
from .ics_core import compute_ics_carpet
from .pair_correlation import kymograph, pcf_from_kymograph

__all__ = ["FlowMap", "pcf_flow_map", "stics_flow_map", "tile_slices"]


@dataclass
class FlowMap:
    """A velocity field sampled on a grid of tiles.

    Attributes
    ----------
    x, y : numpy.ndarray
        Tile centres in µm, shape ``(n_rows, n_columns)``.
    vx, vy : numpy.ndarray
        Velocity along the fast and slow scan axes in µm/s, same shape.
    quality : numpy.ndarray
        Goodness of the fit the velocity came from, in ``[0, 1]``.
    amplitude : numpy.ndarray
        Zero-lag correlation amplitude of each tile, which is ``1/N`` for a
        clean measurement -- a tile whose amplitude is wildly out of line with
        its neighbours is usually an artefact rather than an unusual flow.
    timing : IcsTiming
        Scanner timing the velocities were derived with.
    meta : dict
        Free-form provenance, including the tile geometry.
    """

    x: np.ndarray
    y: np.ndarray
    vx: np.ndarray
    vy: np.ndarray
    quality: np.ndarray
    amplitude: np.ndarray
    timing: IcsTiming = field(default_factory=IcsTiming)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def speed(self) -> np.ndarray:
        """Speed of every tile in µm/s."""
        return np.hypot(self.vx, self.vy)

    @property
    def angle(self) -> np.ndarray:
        """Flow direction of every tile in radians, from the fast axis."""
        return np.arctan2(self.vy, self.vx)

    def quiver(
        self, min_quality: float = 0.5, max_speed: float = 0.0
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return the arrows worth drawing, as flat ``(x, y, vx, vy)``.

        Parameters
        ----------
        min_quality : float
            Drop tiles whose straight-line fit is worse than this. The default
            is deliberately not zero: an unfiltered map draws a plausible flow
            field on a sample that has none.
        max_speed : float
            Drop tiles faster than this, in µm/s. ``0`` keeps all. A speed far
            above the physical maximum is a peak that jumped to a neighbouring
            feature, not a fast molecule.

        Returns
        -------
        tuple of numpy.ndarray
            Four flat arrays ready for a quiver plot, in µm and µm/s.
        """
        keep = np.isfinite(self.vx) & np.isfinite(self.vy)
        keep &= self.quality >= float(min_quality)
        if max_speed > 0.0:
            keep &= self.speed <= float(max_speed)
        return (
            self.x[keep].ravel(),
            self.y[keep].ravel(),
            self.vx[keep].ravel(),
            self.vy[keep].ravel(),
        )

    def summary(self, min_quality: float = 0.5) -> Dict[str, float]:
        """Return mean speed, mean direction and coverage over the kept tiles.

        Parameters
        ----------
        min_quality : float
            Threshold passed to :meth:`quiver`.

        Returns
        -------
        dict
            ``n_tiles``, ``n_kept``, ``mean_speed`` (µm/s), ``mean_vx``,
            ``mean_vy`` and ``coherence`` -- the length of the mean unit vector,
            which is 1 for a field that points one way everywhere and 0 for
            arrows scattered at random.
        """
        _, _, vx, vy = self.quiver(min_quality=min_quality)
        total = int(self.vx.size)
        if vx.size == 0:
            return {
                "n_tiles": float(total), "n_kept": 0.0, "mean_speed": float("nan"),
                "mean_vx": float("nan"), "mean_vy": float("nan"),
                "coherence": float("nan"),
            }
        speed = np.hypot(vx, vy)
        unit = np.where(speed > 0, 1.0 / np.where(speed > 0, speed, 1.0), 0.0)
        return {
            "n_tiles": float(total),
            "n_kept": float(vx.size),
            "mean_speed": float(speed.mean()),
            "mean_vx": float(vx.mean()),
            "mean_vy": float(vy.mean()),
            "coherence": float(np.hypot((vx * unit).mean(), (vy * unit).mean())),
        }


def tile_slices(
    n: int, tile: int, step: int
) -> list[Tuple[int, int]]:
    """Return the tile boundaries along one axis.

    Parameters
    ----------
    n : int
        Length of the axis in pixels.
    tile : int
        Tile size in pixels.
    step : int
        Distance between neighbouring tile origins. A step below *tile* gives
        overlapping tiles, which smooths the field without adding information.

    Returns
    -------
    list of tuple of int
        ``(start, stop)`` pairs; the last tile is pulled back so it ends on the
        edge rather than being dropped.

    Examples
    --------
    >>> tile_slices(10, 4, 4)
    [(0, 4), (4, 8), (6, 10)]
    """
    tile = max(1, min(int(tile), int(n)))
    step = max(1, int(step))
    starts = list(range(0, max(1, n - tile + 1), step))
    if starts[-1] + tile < n:
        starts.append(n - tile)
    return [(s, s + tile) for s in starts]


def stics_flow_map(
    images: np.ndarray,
    *,
    tile: int = 16,
    step: Optional[int] = None,
    frame_lags: Optional[Sequence[int]] = None,
    timing: Optional[IcsTiming] = None,
    subtract_average: str = "frame",
    window: int = 3,
    search: Optional[int] = None,
    method: str = "gauss",
    escape_fraction: float = 0.35,
) -> FlowMap:
    """Map the velocity field by tracking each tile's correlation peak.

    Every tile is correlated on its own over the requested frame lags, and the
    displacement of its correlation peak versus lag gives the local velocity
    (see :meth:`~chisurf.core.experiments.ics.data.IcsCarpet.velocity`).

    Parameters
    ----------
    images : numpy.ndarray
        ``(n_frames, n_lines, n_pixels)`` stack.
    tile : int
        Tile size in pixels. It sets the trade-off that decides the whole
        result: a small tile localizes the flow but has few molecules in it and
        cannot hold a peak that has drifted far, a large tile averages distinct
        flows into one arrow. Several waists across is the usual compromise.
    step : int, optional
        Distance between tile origins. Defaults to *tile* (no overlap).
    frame_lags : sequence of int, optional
        Frame lags to correlate. Defaults to ``range(0, 6)``. The largest lag
        must still keep the peak inside the tile: the displacement is
        ``v * lag * frame_time / pixel_size`` pixels.
    timing : IcsTiming, optional
        Scanner timing. The frame time and the pixel size are what turn a peak
        displacement into a velocity, so both must be set.
    subtract_average : str
        Background handling passed to the correlator.
    window, search, method : optional
        Peak-tracking parameters passed through to
        :meth:`~chisurf.core.experiments.ics.data.IcsCarpet.peak_shift`.
    escape_fraction : float
        Reject a tile whose peak travelled further than this fraction of the
        tile size. See the note below -- this is not a cosmetic filter.

    Returns
    -------
    FlowMap
        The velocity field on the tile grid. A rejected tile has ``NaN``
        velocities and a finite ``amplitude``, and ``meta['n_escaped']`` counts
        them.

    Raises
    ------
    ValueError
        If the stack is not a stack, or the timing lacks a frame time or pixel
        size.

    Notes
    -----
    A tile is correlated over its **own** mean, not the mean of the field. That
    is what makes the map local: a bright region and a dim one then report the
    same velocity, as they should, rather than the bright one dominating.

    The tile size and the largest frame lag are **coupled**, and getting the
    pairing wrong is the failure mode of this method. A correlation map is
    periodic, so a peak that travels past the tile edge does not disappear -- it
    wraps around to the opposite side, where the tracker follows it happily and
    fits a straight line through a displacement that has changed sign. On a
    phantom flowing at 2 pixels per frame through a 16-pixel tile that produced
    a velocity of the right magnitude, pointing the wrong way, with a
    respectable :math:`R^2` of 0.7. Hence *escape_fraction*.
    """
    stack = np.asarray(images, dtype=float)
    if stack.ndim != 3:
        raise ValueError(
            f"a flow map needs a (n_frames, n_lines, n_pixels) stack; got {stack.shape}"
        )
    n_frames, ny, nx = stack.shape
    timing = (timing if timing is not None else IcsTiming()).resolved(n_lines=ny)
    if timing.frame_duration_ms <= 0.0 or timing.pixel_size_nm <= 0.0:
        raise ValueError(
            "a flow map needs a frame time and a pixel size on the timing"
        )
    lags = list(frame_lags) if frame_lags is not None else list(range(0, 6))
    if len(lags) < 2:
        raise ValueError("a velocity needs at least two frame lags")
    step_px = int(step) if step else int(tile)

    rows = tile_slices(ny, tile, step_px)
    cols = tile_slices(nx, tile, step_px)
    pixel_um = float(timing.pixel_size_nm) * 1.0e-3
    escape = float(escape_fraction) * float(min(tile, min(ny, nx)))
    # The search radius and the escape limit have to be the same number, or the
    # guard below is unreachable: a tracker clamped to a smaller radius can never
    # report a displacement large enough to trip it, and an aliased peak is then
    # silently rounded down into a plausible-looking slow flow.
    search_radius = int(search) if search else max(2, int(round(escape)))

    shape = (len(rows), len(cols))
    x = np.zeros(shape)
    y = np.zeros(shape)
    vx = np.full(shape, np.nan)
    vy = np.full(shape, np.nan)
    quality = np.zeros(shape)
    amplitude = np.full(shape, np.nan)

    settings = IcsSettings(
        frame_lags=tuple(int(d) for d in lags),
        subtract_average=subtract_average,
        timing=timing,
    )
    for i, (y0, y1) in enumerate(rows):
        for j, (x0, x1) in enumerate(cols):
            x[i, j] = 0.5 * (x0 + x1) * pixel_um
            y[i, j] = 0.5 * (y0 + y1) * pixel_um
            sub = np.ascontiguousarray(stack[:, y0:y1, x0:x1])
            try:
                carpet = compute_ics_carpet(sub, settings)
                flow = carpet.velocity(
                    window=window, search=search_radius, method=method
                )
            except (ValueError, RuntimeError):
                # One dead tile -- an empty region, a lag the stack is too short
                # for -- must not take the whole map down with it.
                continue
            iy, ix = carpet.zero_lag_index()
            amplitude[i, j] = float(np.asarray(carpet.correlation)[0, iy, ix])
            if float(np.abs(flow.shifts).max()) >= search_radius - 0.75:
                # The peak ran off the edge of its own tile. A correlation map is
                # periodic, so it does not vanish -- it **wraps**, and the tracker
                # then follows a peak that has changed sign, producing a
                # confident, well-fitted, backwards velocity. Measured on a
                # phantom at 2 px/frame in a 16 px tile: a clean R^2 of 0.7 and a
                # velocity pointing the wrong way. Refuse rather than report it.
                continue
            vx[i, j] = flow.vx
            vy[i, j] = flow.vy
            quality[i, j] = flow.quality

    meta = {
        "method": "stics",
        "tile": int(tile),
        "step": int(step_px),
        "frame_lags": tuple(int(d) for d in lags),
        "n_frames": int(n_frames),
        "escape_pixels": float(search_radius),
        "n_escaped": int(np.count_nonzero(np.isfinite(amplitude) & ~np.isfinite(vx))),
    }
    return FlowMap(
        x=x, y=y, vx=vx, vy=vy, quality=quality, amplitude=amplitude,
        timing=timing, meta=meta,
    )


def pcf_flow_map(
    images: np.ndarray,
    *,
    distance: int = 4,
    tile: int = 16,
    timing: Optional[IcsTiming] = None,
    min_prominence: float = 0.0,
    **kwargs: Any,
) -> FlowMap:
    r"""Map the velocity along the fast axis from pair-correlation peaks.

    Each band of *tile* lines is flattened into a kymograph and correlated at
    :math:`\pm` *distance*; the transit-time peak gives the speed and which of
    the two directions peaks gives the sign
    (:meth:`~chisurf.core.experiments.ics.pair_correlation.PcfCarpet.velocity`).

    This map is **one-dimensional** -- ``vy`` is zero throughout, because a pair
    correlation along the fast scan axis says nothing about motion across it.
    What it buys in return is position resolution down to the pixel, and the
    ability to report *no transport* rather than a small one: where a barrier
    removes the peak the velocity is ``NaN``, not a slow flow.

    Parameters
    ----------
    images : numpy.ndarray
        ``(n_frames, n_lines, n_pixels)`` stack.
    distance : int
        Pair distance in pixels. It has to be far enough that the transit time
        is longer than a line period and short enough that molecules survive
        the trip; a few waists is the usual range.
    tile : int
        Number of lines averaged into one row of the map.
    timing : IcsTiming, optional
        Scanner timing; its line time sets the lag axis and its pixel size the
        distance.
    min_prominence : float
        Minimum peak height above the curve median, passed through to the
        transit-time search.
    **kwargs
        Forwarded to
        :func:`~chisurf.core.experiments.ics.pair_correlation.pcf_from_kymograph`.

    Returns
    -------
    FlowMap
        A velocity field whose ``vy`` is identically zero and whose ``quality``
        is the peak height relative to the curve median, normalised to
        ``[0, 1]``.

    Raises
    ------
    ValueError
        If the stack is not a stack or the timing lacks a line time.
    """
    stack = np.asarray(images, dtype=float)
    if stack.ndim != 3:
        raise ValueError(
            f"a flow map needs a (n_frames, n_lines, n_pixels) stack; got {stack.shape}"
        )
    n_frames, ny, nx = stack.shape
    timing = (timing if timing is not None else IcsTiming()).resolved(n_lines=ny)
    d = abs(int(distance))
    if d == 0:
        raise ValueError("a pair-correlation velocity needs a non-zero distance")

    rows = tile_slices(ny, tile, tile)
    pixel_um = float(timing.pixel_size_nm) * 1.0e-3

    shape = (len(rows), nx)
    x = np.tile(np.arange(nx, dtype=float) * pixel_um, (len(rows), 1))
    y = np.zeros(shape)
    vx = np.full(shape, np.nan)
    quality = np.zeros(shape)
    amplitude = np.full(shape, np.nan)

    for i, (y0, y1) in enumerate(rows):
        y[i, :] = 0.5 * (y0 + y1) * pixel_um
        band = kymograph(stack[:, y0:y1, :])
        try:
            carpet = pcf_from_kymograph(band, (+d, -d), timing, **kwargs)
        except ValueError:
            continue
        vx[i, :] = carpet.velocity(d, min_prominence=min_prominence)
        # An edge position has no partner in one of the two directions, so its
        # whole row is NaN by construction; it gets quality 0 rather than a
        # warning from an all-NaN reduction.
        forward, backward = carpet.map(+d), carpet.map(-d)
        usable = np.isfinite(forward).all(axis=1) & np.isfinite(backward).all(axis=1)
        if not np.any(usable):
            continue
        both = np.concatenate([forward[usable], backward[usable]], axis=1)
        best = both.max(axis=1)
        base = np.median(both, axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            contrast = np.where(best > 0.0, 1.0 - base / best, 0.0)
        quality[i, usable] = np.clip(np.nan_to_num(contrast, nan=0.0), 0.0, 1.0)
        amplitude[i, usable] = best

    meta = {
        "method": "pcf",
        "distance": int(d),
        "tile": int(tile),
        "n_frames": int(n_frames),
    }
    return FlowMap(
        x=x, y=y, vx=vx, vy=np.zeros(shape), quality=quality,
        amplitude=amplitude, timing=timing, meta=meta,
    )
