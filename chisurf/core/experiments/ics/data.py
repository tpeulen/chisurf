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

    >>> float(lag_time(1, 0, 0, pixel_duration_us=10.0, line_duration_ms=3.0))
    1e-05
    >>> float(lag_time(0, 1, 0, pixel_duration_us=10.0, line_duration_ms=3.0))
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
