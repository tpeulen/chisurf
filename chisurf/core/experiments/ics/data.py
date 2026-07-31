"""Data containers for image correlation spectroscopy (ICS).

RICS, STICS, TICS and iMSD are not four methods. They are four ways of reading
one object: the spatiotemporal correlation carpet

.. math::

    G(\\xi, \\psi, \\Delta)

of an image stack, where :math:`\\xi` is the lag along the fast (pixel) scan
axis, :math:`\\psi` the lag along the slow (line) axis, and :math:`\\Delta` the
lag in whole frames. What distinguishes the named methods is only *which part
of the carpet is looked at* and *which lag time the scanner assigns to it* --
see :func:`lag_time` and :class:`IcsCarpet`.

The pair-correlation function (pCF) is the fifth reading, and the one that
measures *transport* rather than a decay rate: follow the carpet column a
distance :math:`\\delta` from the origin and its peak is the time molecules
need to cross that distance (:meth:`IcsCarpet.pcf_curve`). Tracking where that
peak sits as :math:`\\Delta` grows gives a velocity
(:meth:`IcsCarpet.velocity`), and doing that on a grid of tiles gives the
velocity *field* -- see
:mod:`chisurf.core.experiments.ics.flow_map`. The region-averaged readings here
are cheap because the carpet already exists; the position-resolved pCF, which
is what localizes a barrier, needs its own kernel in
:mod:`chisurf.core.experiments.ics.pair_correlation`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np


def lag_time(
    pixel_shift: np.ndarray | float,
    line_shift: np.ndarray | float,
    frame_shift: np.ndarray | float = 0.0,
    pixel_duration_us: float = 11.1,
    line_duration_ms: float = 3.33,
    frame_duration_ms: float = 0.0,
) -> np.ndarray:
    r"""Return the physical lag time of a correlation carpet point, in seconds.

    This is the one identity that unifies the image-correlation family. A raster
    scanner visits pixels sequentially, so a displacement in the correlation
    carpet *is* a delay:

    .. math::

        \tau(\xi, \psi, \Delta)
            = \left| \xi\,\tau_\mathrm{p}
                   + \psi\,\tau_\mathrm{l}
                   + \Delta\,\tau_\mathrm{f} \right|

    with the pixel dwell time :math:`\tau_\mathrm{p}`, the line time
    :math:`\tau_\mathrm{l}` and the frame time :math:`\tau_\mathrm{f}`. Every
    named method is a choice of which term dominates:

    ==========  ==========================  ==================================
    Method      Region of the carpet        Lag time it probes
    ==========  ==========================  ==================================
    RICS        :math:`\Delta = 0`          µs (fast axis) to ms (slow axis)
    STICS       :math:`\Delta > 0`          frame time and multiples
    TICS        :math:`\xi = \psi = 0`      frame time only
    iMSD        all :math:`\Delta`          width of each slice vs :math:`\tau`
    ==========  ==========================  ==================================

    Parameters
    ----------
    pixel_shift : numpy.ndarray or float
        Lag :math:`\xi` along the fast (pixel) scan axis, in pixels.
    line_shift : numpy.ndarray or float
        Lag :math:`\psi` along the slow (line) scan axis, in lines.
    frame_shift : numpy.ndarray or float
        Lag :math:`\Delta` in whole frames.
    pixel_duration_us : float
        Pixel dwell time :math:`\tau_\mathrm{p}`, in microseconds.
    line_duration_ms : float
        Line time :math:`\tau_\mathrm{l}`, in milliseconds.
    frame_duration_ms : float
        Frame time :math:`\tau_\mathrm{f}`, in milliseconds. When zero, frame
        lags contribute nothing and the result is the pure RICS lag time.

    Returns
    -------
    numpy.ndarray
        Lag time in seconds, broadcast over the inputs.

    Examples
    --------
    A one-pixel lag on the fast axis costs one pixel dwell time, while a
    one-line lag costs a whole line -- two to three orders of magnitude more.
    That spread is exactly why one RICS map is sensitive to diffusion at all:

    >>> round(float(lag_time(1, 0, 0, pixel_duration_us=10.0, line_duration_ms=3.0)), 9)
    1e-05
    >>> round(float(lag_time(0, 1, 0, pixel_duration_us=10.0, line_duration_ms=3.0)), 9)
    0.003
    """
    tau_p = float(pixel_duration_us) * 1.0e-6
    tau_l = float(line_duration_ms) * 1.0e-3
    tau_f = float(frame_duration_ms) * 1.0e-3
    return np.abs(
        np.asarray(pixel_shift, dtype=float) * tau_p
        + np.asarray(line_shift, dtype=float) * tau_l
        + np.asarray(frame_shift, dtype=float) * tau_f
    )


def _gauss_peak(
    values: np.ndarray, cols: np.ndarray, rows: np.ndarray
) -> Optional[Tuple[float, float]]:
    r"""Locate a Gaussian peak to sub-pixel precision, in closed form.

    A correlation peak is Gaussian to a very good approximation, and the
    logarithm of a Gaussian is a parabola. So after removing a baseline, one
    **linear** least-squares fit of

    .. math::

        \ln g = c_0 + c_1 \xi + c_2 \psi + c_3 (\xi^2 + \psi^2)

    puts the vertex at :math:`(-c_1/2c_3,\; -c_2/2c_3)` with no iteration and no
    pixel locking -- unlike a centre of mass, which is biased towards the
    brightest pixel whenever the window is narrower than the peak.

    Parameters
    ----------
    values : numpy.ndarray
        The correlation window, shape ``(n_rows, n_cols)``.
    cols : numpy.ndarray
        Fast-axis lag of each column, shape ``(n_cols,)``.
    rows : numpy.ndarray
        Slow-axis lag of each row, shape ``(n_rows,)``.

    Returns
    -------
    tuple of float or None
        ``(xi, psi)`` of the peak, or ``None`` when the window does not hold a
        maximum -- too few points, a non-positive dynamic range, or a fitted
        curvature that is not negative (a valley, or a plane).
    """
    if values.size < 6:
        return None
    baseline = float(values.min())
    span = float(values.max()) - baseline
    if not np.isfinite(span) or span <= 0.0:
        return None
    # The window minimum would take the logarithm to -inf; lifting the floor to
    # a small fraction of the dynamic range keeps the fit finite and weights the
    # skirt of the peak down, which is where the Gaussian model is worst anyway.
    z = np.log(np.clip(values - baseline, 0.01 * span, None))
    xi, psi = np.meshgrid(np.asarray(cols, float), np.asarray(rows, float))
    design = np.stack(
        [np.ones(xi.size), xi.ravel(), psi.ravel(), (xi ** 2 + psi ** 2).ravel()],
        axis=1,
    )
    try:
        coefficients, *_ = np.linalg.lstsq(design, z.ravel(), rcond=None)
    except np.linalg.LinAlgError:  # pragma: no cover - singular window
        return None
    c1, c2, c3 = coefficients[1], coefficients[2], coefficients[3]
    if not np.isfinite(c3) or c3 >= 0.0:
        return None
    return float(-c1 / (2.0 * c3)), float(-c2 / (2.0 * c3))


def _fit_drift(lags: np.ndarray, shifts: np.ndarray) -> Tuple[float, float, float]:
    """Fit a straight line to peak displacement versus frame lag, both axes.

    Parameters
    ----------
    lags : numpy.ndarray
        Frame lags, shape ``(n,)``.
    shifts : numpy.ndarray
        Peak displacements, shape ``(n, 2)`` as ``(xi, psi)``.

    Returns
    -------
    tuple of float
        ``(slope_xi, slope_psi, r_squared)`` with the slopes in pixels per
        frame lag.

    Notes
    -----
    The goodness of fit is **pooled over both axes** rather than taken per
    axis. A flow purely along ``x`` leaves ``psi`` at zero, which is a perfect
    physical answer and a terrible one-dimensional fit -- its own
    :math:`R^2` is meaningless noise. Pooling weights each axis by how much it
    actually moved, so an honest one-directional flow scores high.
    """
    x = np.asarray(lags, dtype=float)
    y = np.asarray(shifts, dtype=float)
    n = x.size
    if n < 2:
        return 0.0, 0.0, 0.0
    mean_x = float(x.mean())
    var_x = float(((x - mean_x) ** 2).sum())
    if var_x <= 0.0:
        return 0.0, 0.0, 0.0
    slopes = ((x - mean_x)[:, None] * (y - y.mean(axis=0))).sum(axis=0) / var_x
    predicted = y.mean(axis=0) + slopes * (x - mean_x)[:, None]
    ss_res = float(((y - predicted) ** 2).sum())
    ss_tot = float(((y - y.mean(axis=0)) ** 2).sum())
    r2 = 0.0 if ss_tot <= 0.0 else max(0.0, 1.0 - ss_res / ss_tot)
    return float(slopes[0]), float(slopes[1]), r2


@dataclass
class IcsTiming:
    """Scanner timing and geometry needed to turn carpet lags into lag times.

    Attributes
    ----------
    pixel_duration_us : float
        Pixel dwell time in microseconds.
    line_duration_ms : float
        Line time in milliseconds.
    frame_duration_ms : float
        Frame time in milliseconds. Zero means "unknown"; :meth:`resolved`
        then estimates it from the line time and the number of lines.
    pixel_size_nm : float
        Physical pixel size in nanometres.
    """

    pixel_duration_us: float = 11.1
    line_duration_ms: float = 3.33
    frame_duration_ms: float = 0.0
    pixel_size_nm: float = 40.0

    def resolved(self, n_lines: int = 0) -> "IcsTiming":
        """Return a copy with a usable frame time.

        An unset frame time is estimated as ``n_lines * line_duration_ms``,
        which is exact for a scanner without inter-frame dead time and is the
        only estimate available from the pixel/line timing alone.

        Parameters
        ----------
        n_lines : int
            Number of lines per frame, used only when the frame time is unset.

        Returns
        -------
        IcsTiming
            A timing object whose ``frame_duration_ms`` is non-zero whenever it
            can be determined.
        """
        if self.frame_duration_ms > 0.0 or n_lines <= 0:
            return self
        return IcsTiming(
            pixel_duration_us=self.pixel_duration_us,
            line_duration_ms=self.line_duration_ms,
            frame_duration_ms=float(n_lines) * self.line_duration_ms,
            pixel_size_nm=self.pixel_size_nm,
        )

    def lag_time(
        self,
        pixel_shift: np.ndarray | float,
        line_shift: np.ndarray | float,
        frame_shift: np.ndarray | float = 0.0,
    ) -> np.ndarray:
        """Return :func:`lag_time` evaluated with this timing.

        Parameters
        ----------
        pixel_shift : numpy.ndarray or float
            Lag along the fast (pixel) scan axis, in pixels.
        line_shift : numpy.ndarray or float
            Lag along the slow (line) scan axis, in lines.
        frame_shift : numpy.ndarray or float
            Lag in whole frames.

        Returns
        -------
        numpy.ndarray
            Lag time in seconds.
        """
        return lag_time(
            pixel_shift,
            line_shift,
            frame_shift,
            pixel_duration_us=self.pixel_duration_us,
            line_duration_ms=self.line_duration_ms,
            frame_duration_ms=self.frame_duration_ms,
        )

    def to_dict(self) -> Dict[str, float]:
        """Return the timing as a plain dictionary for metadata storage."""
        return {
            "pixel_duration_us": float(self.pixel_duration_us),
            "line_duration_ms": float(self.line_duration_ms),
            "frame_duration_ms": float(self.frame_duration_ms),
            "pixel_size_nm": float(self.pixel_size_nm),
        }

    @classmethod
    def from_meta(cls, meta: Dict[str, Any]) -> "IcsTiming":
        """Build a timing object from an ICS metadata dictionary.

        Parameters
        ----------
        meta : dict
            Metadata as produced by :meth:`IcsCarpet.to_meta`. Missing or
            non-positive entries fall back to the class defaults.

        Returns
        -------
        IcsTiming
            The reconstructed timing.
        """
        out = cls()
        for key in ("pixel_duration_us", "line_duration_ms",
                    "frame_duration_ms", "pixel_size_nm"):
            value = meta.get(key)
            if isinstance(value, (int, float)) and float(value) > 0.0:
                setattr(out, key, float(value))
        return out


@dataclass
class IcsSettings:
    """Acquisition/ROI settings for a spatiotemporal correlation.

    Attributes
    ----------
    x_range, y_range : tuple of int, optional
        Region of interest in pixels/lines. ``None`` means the full field.
    frame_lags : sequence of int
        Frame lags :math:`\\Delta` to correlate. ``(0,)`` reproduces a classic
        RICS map; ``range(0, n)`` builds the full carpet.
    subtract_average : str
        Background handling passed to the correlator: ``'frame'``, ``'stack'``
        or ``''``.
    timing : IcsTiming
        Scanner timing and pixel size.
    extra : dict
        Free-form additional settings.
    """

    x_range: Optional[Tuple[int, int]] = None
    y_range: Optional[Tuple[int, int]] = None
    frame_lags: Sequence[int] = (0,)
    subtract_average: str = "frame"
    timing: IcsTiming = field(default_factory=IcsTiming)

    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowVector:
    """A velocity read from the displacement of a correlation peak.

    Attributes
    ----------
    vx, vy : float
        Velocity along the fast (pixel) and slow (line) scan axes, in µm/s.
    quality : float
        Coefficient of determination of the straight line fitted to peak
        displacement versus frame lag, in ``[0, 1]``. A tile with no directed
        transport has a peak that stays at zero and jitters, which fits a line
        badly -- so this is the number to threshold on before drawing an arrow.
    shifts : numpy.ndarray
        The tracked peak displacements, shape ``(n_lags, 2)`` as
        ``(xi, psi)`` in pixels, kept so a suspicious arrow can be traced back
        to the peaks it came from.
    """

    vx: float
    vy: float
    quality: float
    shifts: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))

    @property
    def speed(self) -> float:
        """Magnitude of the velocity in µm/s."""
        return float(np.hypot(self.vx, self.vy))

    @property
    def angle(self) -> float:
        """Direction of the velocity in radians, measured from the fast axis."""
        return float(np.arctan2(self.vy, self.vx))


@dataclass
class IcsCarpet:
    """A spatiotemporal image-correlation carpet :math:`G(\\xi, \\psi, \\Delta)`.

    The carpet is the single object behind RICS, STICS, TICS and iMSD; the
    named methods are the accessors below, not separate analyses.

    Attributes
    ----------
    correlation : numpy.ndarray
        Correlation of shape ``(n_lags, ny, nx)``, one spatial map per frame
        lag, zero lag centred when the producer applied an ``fftshift``.
    error : numpy.ndarray
        Standard error of the mean over the averaged frame pairs, same shape.
    pixel_shift : numpy.ndarray
        Fast-axis lag :math:`\\xi` of every carpet point, shape ``(ny, nx)``,
        in the same order as the maps (centred or FFT order).
    line_shift : numpy.ndarray
        Slow-axis lag :math:`\\psi` of every carpet point, shape ``(ny, nx)``,
        in the same order as the maps (centred or FFT order).
    frame_lags : numpy.ndarray
        The frame lags :math:`\\Delta`, shape ``(n_lags,)``.
    timing : IcsTiming
        Scanner timing used to convert lags into lag times.
    meta : dict
        Free-form provenance (filename, ROI, frame count, ...).
    """

    correlation: np.ndarray
    error: np.ndarray
    pixel_shift: np.ndarray
    line_shift: np.ndarray
    frame_lags: np.ndarray
    timing: IcsTiming = field(default_factory=IcsTiming)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def shape(self) -> Tuple[int, int, int]:
        """Shape of the carpet ``(n_lags, ny, nx)``."""
        return tuple(np.asarray(self.correlation).shape)  # type: ignore[return-value]

    @property
    def n_lags(self) -> int:
        """Number of frame lags in the carpet."""
        return int(np.asarray(self.frame_lags).size)

    def lag_time_grid(self) -> np.ndarray:
        """Return the lag time of every carpet point, shape ``(n_lags, ny, nx)``.

        Returns
        -------
        numpy.ndarray
            Lag time in seconds for each :math:`(\\Delta, \\psi, \\xi)`.
        """
        d = np.asarray(self.frame_lags, dtype=float)[:, None, None]
        return self.timing.lag_time(
            self.pixel_shift[None, ...], self.line_shift[None, ...], d
        )

    # --- the four named readings of one carpet ----------------------------
    def rics_map(self) -> np.ndarray:
        """Return the RICS map: the zero-frame-lag slice :math:`G(\\xi, \\psi, 0)`.

        Returns
        -------
        numpy.ndarray
            Spatial correlation map of shape ``(ny, nx)``.
        """
        return np.asarray(self.correlation)[self.lag_index(0)]

    def stics_map(self, frame_lag: int) -> np.ndarray:
        """Return the STICS map at a given frame lag.

        Parameters
        ----------
        frame_lag : int
            The frame lag :math:`\\Delta` to read.

        Returns
        -------
        numpy.ndarray
            Spatial correlation map of shape ``(ny, nx)``.
        """
        return np.asarray(self.correlation)[self.lag_index(frame_lag)]

    def tics_curve(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return the TICS decay: the zero-spatial-lag column vs lag time.

        Returns
        -------
        tuple of numpy.ndarray
            ``(tau, g)`` with the lag time in seconds and the correlation
            amplitude at :math:`\\xi = \\psi = 0` for every frame lag.
        """
        corr = np.asarray(self.correlation)
        iy, ix = self.zero_lag_index()
        g = corr[:, iy, ix]
        tau = self.timing.lag_time(0.0, 0.0, np.asarray(self.frame_lags, dtype=float))
        return np.asarray(tau, dtype=float), np.asarray(g, dtype=float)

    def pcf_curve(
        self, distance: int, axis: str = "pixel"
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Return the pair-correlation decay at a fixed spatial lag.

        This is the fifth reading of the same carpet: instead of the zero-lag
        column that :meth:`tics_curve` takes, follow the column a *distance*
        away. The correlation there is the distribution of times molecules need
        to travel that distance, so its peak is a transit time rather than a
        decay constant -- and it is the reading in which a barrier shows up,
        because a barrier removes the peak entirely while leaving both local
        autocorrelations untouched.

        ``pcf_curve(0)`` is exactly :meth:`tics_curve`.

        Parameters
        ----------
        distance : int
            Signed spatial lag :math:`\\delta`, in pixels (``axis='pixel'``) or
            lines (``axis='line'``). The sign is the direction, and it is the
            whole point: directed transport correlates in one direction only.
        axis : str
            ``'pixel'`` for the fast scan axis, ``'line'`` for the slow one.

        Returns
        -------
        tuple of numpy.ndarray
            ``(tau, g)``: lag time in seconds and correlation amplitude, one
            entry per frame lag in the carpet.

        Raises
        ------
        ValueError
            If *axis* is not ``'pixel'`` or ``'line'``, or if the requested
            distance is outside the carpet.

        Notes
        -----
        This reading is **averaged over the whole region** -- the carpet is
        built by an FFT over space, which destroys position -- and its time
        axis is quantized to the frame time. Both limits are lifted by
        :func:`chisurf.core.experiments.ics.pair_correlation.pcf_from_stack`,
        which resolves position and reaches lags below the line time.
        """
        if axis not in ("pixel", "line"):
            raise ValueError(f"axis must be 'pixel' or 'line', not {axis!r}")
        iy, ix = self.zero_lag_index()
        if axis == "pixel":
            target = self.pixel_shift[iy, :]
            index = int(np.argmin(np.abs(target - float(distance))))
            if abs(float(target[index]) - float(distance)) > 0.5:
                raise ValueError(
                    f"pixel lag {distance} is outside the carpet "
                    f"({target.min():.0f} .. {target.max():.0f})"
                )
            g = np.asarray(self.correlation)[:, iy, index]
            tau = self.timing.lag_time(
                float(distance), 0.0, np.asarray(self.frame_lags, dtype=float)
            )
        else:
            target = self.line_shift[:, ix]
            index = int(np.argmin(np.abs(target - float(distance))))
            if abs(float(target[index]) - float(distance)) > 0.5:
                raise ValueError(
                    f"line lag {distance} is outside the carpet "
                    f"({target.min():.0f} .. {target.max():.0f})"
                )
            g = np.asarray(self.correlation)[:, index, ix]
            tau = self.timing.lag_time(
                0.0, float(distance), np.asarray(self.frame_lags, dtype=float)
            )
        return np.asarray(tau, dtype=float), np.asarray(g, dtype=float)

    def pcf_map(self, axis: str = "pixel") -> Tuple[np.ndarray, np.ndarray]:
        """Return every pair-correlation decay along one axis at once.

        Parameters
        ----------
        axis : str
            ``'pixel'`` for the fast scan axis, ``'line'`` for the slow one.

        Returns
        -------
        tuple of numpy.ndarray
            ``(distances, g)`` with the signed spatial lags and a
            ``(n_distances, n_lags)`` array of correlation amplitudes -- the
            classic distance-versus-time pCF carpet, region-averaged.
        """
        if axis not in ("pixel", "line"):
            raise ValueError(f"axis must be 'pixel' or 'line', not {axis!r}")
        iy, ix = self.zero_lag_index()
        corr = np.asarray(self.correlation)
        if axis == "pixel":
            distances = np.asarray(self.pixel_shift[iy, :], dtype=float)
            g = corr[:, iy, :].T
        else:
            distances = np.asarray(self.line_shift[:, ix], dtype=float)
            g = corr[:, :, ix].T
        order = np.argsort(distances)
        return distances[order], np.asarray(g, dtype=float)[order]

    # --- directed transport: where the peak goes ---------------------------
    def peak_shift(
        self,
        frame_lag: int,
        window: int = 3,
        search: Optional[int] = None,
        method: str = "gauss",
    ) -> Tuple[float, float]:
        """Return the sub-pixel position of the correlation peak at a frame lag.

        Directed transport moves the correlation peak away from zero lag by the
        distance the sample travelled, so tracking that peak across frame lags
        *is* the velocity measurement (STICS).

        The brightest **pixel** is not good enough: a realistic flow moves the
        peak by a fraction of a pixel per frame, which an ``argmax`` cannot see
        at all. Two sub-pixel estimators are offered, and the difference between
        them is not academic:

        ``'gauss'`` (default)
            A Gaussian is fitted in closed form by least squares on the
            logarithm of the baseline-corrected window, which is exact for a
            Gaussian peak sampled at integer lags.
        ``'centroid'``
            Centre of mass over the window. Simple and robust to a non-Gaussian
            peak shape, but it **locks to whole pixels**: a window narrower than
            the peak pulls the estimate towards the brightest pixel. Measured on
            a drifting phantom at 0.2 pixels per frame, the centroid overshot the
            velocity by 19 % while the Gaussian fit stayed within 5 %; at whole-
            pixel displacements the two agree exactly, which is why the bias is
            easy to miss.

        Parameters
        ----------
        frame_lag : int
            The frame lag :math:`\\Delta` to read.
        window : int
            Half-width of the fit window in pixels. It should cover the peak;
            too small is what causes the locking described above.
        search : int, optional
            Half-width of the region the maximum is searched in, in pixels.
            Defaults to a quarter of the map, which keeps a noise spike in a far
            corner from being mistaken for the transport peak.
        method : str
            ``'gauss'`` or ``'centroid'``.

        Returns
        -------
        tuple of float
            ``(xi, psi)``: peak displacement along the fast and slow axes, in
            pixels and lines.

        Raises
        ------
        ValueError
            If *method* is unknown, or if the carpet was not centred
            (``use_fftshift=False``) -- the window would then straddle the
            wrap-around.
        """
        if method not in ("gauss", "centroid"):
            raise ValueError(f"method must be 'gauss' or 'centroid', not {method!r}")
        if not self.meta.get("fftshifted", True):
            raise ValueError(
                "peak_shift needs a centred carpet; recompute with use_fftshift=True"
            )
        m = np.asarray(self.correlation, dtype=float)[self.lag_index(frame_lag)]
        ny, nx = m.shape
        cy, cx = ny // 2, nx // 2
        ry = int(search) if search else max(1, ny // 4)
        rx = int(search) if search else max(1, nx // 4)
        y0, y1 = max(cy - ry, 0), min(cy + ry + 1, ny)
        x0, x1 = max(cx - rx, 0), min(cx + rx + 1, nx)
        region = m[y0:y1, x0:x1]
        finite = np.where(np.isfinite(region), region, -np.inf)
        jy, jx = np.unravel_index(int(np.argmax(finite)), region.shape)
        iy, ix = jy + y0, jx + x0

        w0, w1 = max(iy - window, 0), min(iy + window + 1, ny)
        v0, v1 = max(ix - window, 0), min(ix + window + 1, nx)
        sub = np.asarray(m[w0:w1, v0:v1], dtype=float)
        sub = np.where(np.isfinite(sub), sub, 0.0)
        rows = np.arange(w0, w1, dtype=float) - cy
        cols = np.arange(v0, v1, dtype=float) - cx

        if method == "gauss":
            fit = _gauss_peak(sub, cols, rows)
            if fit is not None:
                dx, dy = fit
                # A fit that ran away from the window it was fitted on is not a
                # peak position, it is an extrapolation; fall back rather than
                # report it.
                if abs(dx - (ix - cx)) <= window and abs(dy - (iy - cy)) <= window:
                    return dx, dy

        # A centroid is only meaningful on non-negative weights, and the carpet
        # away from the peak can be negative; shifting by the window minimum
        # makes the weights non-negative without moving the maximum.
        weights = np.clip(sub - sub.min(), 0.0, None)
        total = float(weights.sum())
        if total <= 0.0:
            return float(ix - cx), float(iy - cy)
        return (
            float((weights.sum(axis=0) * cols).sum() / total),
            float((weights.sum(axis=1) * rows).sum() / total),
        )

    def velocity(
        self, window: int = 3, search: Optional[int] = None, method: str = "gauss"
    ) -> FlowVector:
        """Return the flow velocity from the drift of the correlation peak.

        The peak displacement grows linearly with the frame lag,
        :math:`\\xi(\\Delta) = -v_x \\Delta \\tau_\\mathrm{f} / a` with pixel
        size :math:`a`, so a straight line through the tracked peaks gives the
        velocity. **The minus sign is not cosmetic**: the carpet is built by
        correlating frame *i* against frame *i+Δ*, and with that conjugation
        order the peak moves *against* the flow. A sign error here inverts the
        physics while every other number stays plausible, so it is pinned by a
        test.

        Parameters
        ----------
        window : int
            Half-width of the fit window passed to :meth:`peak_shift`.
        search : int, optional
            Half-width of the search region passed to :meth:`peak_shift`.
        method : str
            Peak estimator passed to :meth:`peak_shift`.

        Returns
        -------
        FlowVector
            Velocity in µm/s along both scan axes, with the goodness of the
            straight-line fit and the peak displacements it was fitted to.

        Raises
        ------
        ValueError
            If the carpet has fewer than two frame lags, or the frame time or
            pixel size is unknown.
        """
        lags = np.asarray(self.frame_lags, dtype=float)
        if lags.size < 2:
            raise ValueError(
                "a velocity needs at least two frame lags; recompute the carpet "
                "with frame_lags=range(0, n)"
            )
        frame_time = float(self.timing.frame_duration_ms) * 1.0e-3
        pixel_size = float(self.timing.pixel_size_nm) * 1.0e-3
        if frame_time <= 0.0 or pixel_size <= 0.0:
            raise ValueError(
                "a velocity needs a frame time and a pixel size; set them on "
                "IcsTiming (frame_duration_ms, pixel_size_nm)"
            )
        shifts = np.asarray(
            [
                self.peak_shift(int(d), window=window, search=search, method=method)
                for d in lags
            ],
            dtype=float,
        )
        slope_x, slope_y, r2 = _fit_drift(lags, shifts)
        scale = -pixel_size / frame_time
        return FlowVector(
            vx=float(slope_x * scale),
            vy=float(slope_y * scale),
            quality=float(r2),
            shifts=shifts,
        )

    def zero_lag_index(self) -> Tuple[int, int]:
        """Return the ``(row, column)`` index of the zero spatial lag.

        Returns
        -------
        tuple of int
            Index into a single ``(ny, nx)`` carpet slice.
        """
        d = np.abs(self.pixel_shift) + np.abs(self.line_shift)
        iy, ix = np.unravel_index(int(np.argmin(d)), d.shape)
        return int(iy), int(ix)

    def lag_index(self, frame_lag: int) -> int:
        """Return the carpet index of a frame lag.

        Parameters
        ----------
        frame_lag : int
            The frame lag :math:`\\Delta` to locate.

        Returns
        -------
        int
            Index into the first carpet axis; the nearest available lag when
            the exact lag was not computed.
        """
        lags = np.asarray(self.frame_lags, dtype=float)
        if lags.size == 0:
            return 0
        return int(np.argmin(np.abs(lags - float(frame_lag))))

    def ravel(self) -> np.ndarray:
        """Return the carpet flattened to the 1D vector the fit machinery uses."""
        return np.asarray(self.correlation, dtype=float).ravel()

    def to_meta(self) -> Dict[str, Any]:
        """Return the carpet as a metadata dictionary for a ``DataCurve``.

        Returns
        -------
        dict
            Arrays and timing under stable keys, consumed by the ICS models
            and the plot accessors. ``ics_mean`` is the zero-frame-lag slice,
            i.e. the classic RICS map.
        """
        meta: Dict[str, Any] = {
            "correlation": self.correlation,
            "error": self.error,
            "pixel_shift": self.pixel_shift,
            "line_shift": self.line_shift,
            "frame_lags": np.asarray(self.frame_lags),
            "ics_mean": self.rics_map(),
        }
        meta.update(self.timing.to_dict())
        meta.update(self.meta)
        return meta
