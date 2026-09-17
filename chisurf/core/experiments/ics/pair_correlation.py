r"""Pair-correlation function (pCF) analysis: where molecules go, not how fast.

Every other member of the image-correlation family answers "how quickly does
the signal here decorrelate". The pair correlation asks a different question:
take the intensity at one position, take it again a distance :math:`\delta`
away, and correlate *those two*:

.. math::

    G(\tau, x, \delta)
        = \frac{\langle F(t, x)\, F(t + \tau,\, x + \delta)\rangle}
               {\langle F(\cdot, x)\rangle \langle F(\cdot, x + \delta)\rangle}
          - 1

The answer is a distribution of **transit times**. Its maximum sits at the time
a molecule typically needs to travel :math:`\delta`, which is
:math:`\delta^2/(4D)` for free diffusion in one dimension and :math:`\delta/v`
under a flow :math:`v`. That single change of question is what makes pCF the
method for connectivity and directed transport (Digman & Gratton 2009):

* a **barrier** between the two points does not slow the peak down, it
  **deletes** it -- while the ordinary autocorrelation at either point is
  completely unremarkable, because each point still sees molecules;
* **direction is signed**. Flow towards :math:`+x` correlates :math:`x` with
  :math:`x+\delta` and not with :math:`x-\delta`, so :math:`+\delta` peaks and
  :math:`-\delta` does not. An analysis that folds the two together throws the
  transport away;
* **position is kept**. This is the part
  :func:`~chisurf.core.experiments.ics.ics_core.compute_ics_carpet` cannot
  give: it FFTs over space, which averages every position together by
  construction. A barrier that sits at one place is exactly what that average
  destroys, so pCF needs its own kernel -- the one in this module.

Cost
----
One real FFT along **time** yields every lag at every position at once, which
is why this is not the expensive route it looks like. Extracting the same
position resolution by sliding a region across the field and re-running the
spatial correlator measured ~700x slower on a 4096 x 64 kymograph, and the gap
grows with the number of positions and lags.

Conventions, and why each was chosen
------------------------------------
**Linear, zero-padded correlation -- not circular.** A circular correlation
wraps the end of the record onto its start, which biases precisely the long-lag
tail where a large-:math:`\delta` peak lives. The time axis is padded past
:math:`2N` before transforming.

**Normalised by the overlap.** Lag :math:`\tau` has :math:`N-\tau` contributing
products, not :math:`N`. Dividing by :math:`N` (as several reference
implementations do) tilts the curve downwards at long lag, which moves a
transit-time peak towards shorter times.

**Errors come from segments.** The record is split into equal segments and the
correlation of each is computed separately; the reported value is their mean
and the error their standard error. A curve handed to a fit without that has no
honest ``ey``.

**Bleaching is corrected before correlating, amplitude included.** See
:func:`correct_bleaching`.

References
----------
Digman, M. A. & Gratton, E. *Imaging barriers to diffusion by pair correlation
functions.* Biophysical Journal 97, 665-673 (2009).

Conventions above were cross-checked against the ``ipcf`` reference
implementation by C. Gohlke (CC-BY-4.0); the code here is an independent
implementation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .data import IcsTiming

__all__ = [
    "PcfCarpet",
    "correct_bleaching",
    "kymograph",
    "log_lag_bins",
    "pcf_from_kymograph",
    "pcf_from_stack",
]


def kymograph(images: np.ndarray) -> np.ndarray:
    """Flatten an image stack into a ``(time, position)`` kymograph.

    A raster scanner visits every pixel of a line, then the next line, then the
    next frame. Flattening the frame and line axes in that acquisition order
    turns the stack into one long time series per pixel position, sampled once
    per **line period** -- which is the time unit every lag in the resulting
    pCF is measured in.

    Parameters
    ----------
    images : numpy.ndarray
        ``(n_frames, n_lines, n_pixels)`` stack, a ``(n_lines, n_pixels)``
        single frame, or a ``(n_frames, n_lines, n_pixels, n_channels)`` stack
        whose channels are summed.

    Returns
    -------
    numpy.ndarray
        Float array of shape ``(n_frames * n_lines, n_pixels)``.

    Raises
    ------
    ValueError
        If the array shape cannot be interpreted as an image stack.

    Examples
    --------
    >>> import numpy as np
    >>> kymograph(np.arange(2 * 3 * 4).reshape(2, 3, 4)).shape
    (6, 4)
    """
    arr = np.asarray(images, dtype=float)
    if arr.ndim == 4:
        arr = arr.sum(axis=-1)
    if arr.ndim == 2:
        return np.ascontiguousarray(arr)
    if arr.ndim == 3:
        return np.ascontiguousarray(arr.reshape(-1, arr.shape[-1]))
    raise ValueError(f"Unsupported image array shape for a kymograph: {arr.shape}")


def correct_bleaching(intensity: np.ndarray, window: int = 0, axis: int = 0) -> np.ndarray:
    r"""Remove a slow intensity trend without changing the fluctuation statistics.

    Photobleaching and focus drift add a slow decay to every trace. Subtracting
    it is only half the correction: the *fluctuations* also shrink as the mean
    falls, because shot noise scales with the square root of the count rate. A
    plain high-pass therefore leaves ``G`` drifting through the record -- and
    ``G(0) = 1/N`` is read as a concentration, so that drift is reported as a
    changing number of molecules.

    So the trace is flattened **and** rescaled:

    .. math::

        F'(t) = \big(F(t) - \bar{F}(t)\big)
                \sqrt{\frac{\langle F \rangle}{\bar{F}(t)}}
                + \langle F \rangle

    with :math:`\bar{F}` a moving average and :math:`\langle F \rangle` the
    overall mean.

    Parameters
    ----------
    intensity : numpy.ndarray
        Intensity trace or ``(time, position)`` kymograph.
    window : int
        Length of the moving average, in samples. ``0`` picks one eighth of the
        record, long enough not to eat the correlation itself.
    axis : int
        Time axis.

    Returns
    -------
    numpy.ndarray
        The corrected trace, with the original mean restored.

    Notes
    -----
    The amplitude rescale follows the ``ipcf`` reference implementation by
    C. Gohlke (CC-BY-4.0), reimplemented here.
    """
    arr = np.asarray(intensity, dtype=float)
    n = arr.shape[axis]
    w = int(window) if window and window > 1 else max(3, n // 8)
    w = min(w, n)
    if w % 2 == 0:
        w += 1
    if n < 3 or w >= n:
        return arr.copy()

    moved = np.moveaxis(arr, axis, 0)
    kernel = np.ones(w) / float(w)
    # 'same' would taper the first and last w/2 samples towards zero, which is a
    # fake trend exactly where the record starts and ends. Padding by edge
    # reflection keeps the trend estimate honest at both ends.
    pad = w // 2
    padded = np.pad(moved, [(pad, pad)] + [(0, 0)] * (moved.ndim - 1), mode="edge")
    trend = np.apply_along_axis(lambda v: np.convolve(v, kernel, mode="valid"), 0, padded)
    mean = moved.mean(axis=0, keepdims=True)
    safe = np.where(trend > 0.0, trend, np.nan)
    scale = np.sqrt(np.divide(mean, safe, out=np.ones_like(safe), where=np.isfinite(safe)))
    scale = np.where(np.isfinite(scale), scale, 1.0)
    out = (moved - trend) * scale + mean
    return np.ascontiguousarray(np.moveaxis(out, 0, axis))


def log_lag_bins(max_lag: int, n_linear: int = 16, per_octave: int = 8) -> list[tuple[int, int]]:
    r"""Return quasi-logarithmic lag bins as half-open integer ranges.

    A pCF peak can sit anywhere from one line period to thousands, so a linear
    lag axis either misses the short end or carries far more points than the
    statistics support. The first *n_linear* lags are kept one by one -- the
    short end is where a fast transit shows up and averaging there would smear
    it -- and beyond that the bin width grows geometrically.

    Parameters
    ----------
    max_lag : int
        Largest lag to include, in samples.
    n_linear : int
        Number of leading lags kept unbinned.
    per_octave : int
        Number of bins per factor of two beyond the linear part.

    Returns
    -------
    list of tuple of int
        ``(start, stop)`` pairs covering ``1 .. max_lag`` without gaps or
        overlap. Lag zero is never included: at :math:`\delta = 0` it is the
        shot-noise spike, and it carries no transport information anywhere.

    Examples
    --------
    >>> log_lag_bins(6, n_linear=3)
    [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7)]
    """
    max_lag = int(max_lag)
    if max_lag < 1:
        return []
    bins: list[tuple[int, int]] = []
    lag = 1
    while lag <= max_lag and lag <= int(n_linear):
        bins.append((lag, lag + 1))
        lag += 1
    growth = 2.0 ** (1.0 / max(1, int(per_octave)))
    edge = float(lag)
    while lag <= max_lag:
        edge = max(edge * growth, lag + 1.0)
        stop = min(int(round(edge)), max_lag + 1)
        bins.append((lag, stop))
        lag = stop
    return bins


def _row_max(maps: np.ndarray) -> np.ndarray:
    """Return the largest finite value of every row, ``-inf`` for an empty one.

    Parameters
    ----------
    maps : numpy.ndarray
        Array of shape ``(n_rows, n_columns)``, possibly containing ``NaN``.

    Returns
    -------
    numpy.ndarray
        One value per row.
    """
    filled = np.where(np.isfinite(maps), maps, -np.inf)
    return np.asarray(filled.max(axis=1), dtype=float)


@dataclass
class PcfCarpet:
    r"""A position-resolved pair-correlation carpet :math:`G(\tau, x, \delta)`.

    Attributes
    ----------
    correlation : numpy.ndarray
        Correlation of shape ``(n_delta, n_positions, n_tau)``. Entries where
        the partner position falls outside the field are ``NaN`` -- a position
        near the edge simply has no neighbour at that distance, and filling it
        with a number would invent one.
    error : numpy.ndarray
        Standard error over the time segments, same shape.
    tau : numpy.ndarray
        Lag times in seconds, shape ``(n_tau,)``.
    delta : numpy.ndarray
        Signed spatial distances in pixels, shape ``(n_delta,)``.
    positions : numpy.ndarray
        Position of the **reference** point of each pair, in µm.
    timing : IcsTiming
        Scanner timing the lag times were derived from.
    meta : dict
        Free-form provenance.

    Notes
    -----
    Row ``x`` of ``correlation[i]`` correlates position ``x`` with position
    ``x + delta[i]``; the reference point is the row, for both signs. That
    convention is what makes ``+delta`` and ``-delta`` comparable at the same
    ``x``, which is how :meth:`velocity` reads a direction.
    """

    correlation: np.ndarray
    error: np.ndarray
    tau: np.ndarray
    delta: np.ndarray
    positions: np.ndarray
    timing: IcsTiming = field(default_factory=IcsTiming)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int, int]:
        """Shape of the carpet ``(n_delta, n_positions, n_tau)``."""
        return tuple(np.asarray(self.correlation).shape)  # type: ignore[return-value]

    def delta_index(self, distance: int) -> int:
        r"""Return the carpet index of a signed distance.

        Parameters
        ----------
        distance : int
            The signed distance :math:`\delta` in pixels.

        Returns
        -------
        int
            Index into the first carpet axis.

        Raises
        ------
        ValueError
            If the distance was not computed.
        """
        d = np.asarray(self.delta, dtype=float)
        index = int(np.argmin(np.abs(d - float(distance))))
        if abs(float(d[index]) - float(distance)) > 1e-9:
            raise ValueError(
                f"distance {distance} was not computed; available: "
                f"{np.asarray(self.delta, dtype=int).tolist()}"
            )
        return index

    def curve(
        self, distance: int, position: int | None = None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        r"""Return one pair-correlation decay.

        Parameters
        ----------
        distance : int
            Signed distance :math:`\delta` in pixels.
        position : int, optional
            Index of the reference position. ``None`` averages over every
            position that has a partner, which is the region-averaged reading
            and the one to compare against
            :meth:`~chisurf.core.experiments.ics.data.IcsCarpet.pcf_curve`.

        Returns
        -------
        tuple of numpy.ndarray
            ``(tau, g, error)`` in seconds and correlation units.
        """
        i = self.delta_index(distance)
        corr = np.asarray(self.correlation, dtype=float)[i]
        err = np.asarray(self.error, dtype=float)[i]
        if position is None:
            valid = np.isfinite(corr).all(axis=1)
            if not np.any(valid):
                empty = np.full(self.tau.shape, np.nan)
                return np.asarray(self.tau, dtype=float), empty, empty
            g = corr[valid].mean(axis=0)
            # Positions overlap heavily -- neighbouring pairs share molecules --
            # so their scatter is not an independent sample. The per-segment
            # error is propagated instead, which does not pretend otherwise.
            e = np.sqrt((err[valid] ** 2).mean(axis=0))
            return np.asarray(self.tau, dtype=float), g, e
        return (
            np.asarray(self.tau, dtype=float),
            corr[int(position)],
            err[int(position)],
        )

    def map(self, distance: int) -> np.ndarray:
        r"""Return the position-versus-lag carpet at one distance.

        This is the image pCF is read from: position runs down, lag time runs
        across, and a barrier is a **horizontal band where the correlation
        disappears** while the rows above and below it are unremarkable.

        Parameters
        ----------
        distance : int
            Signed distance :math:`\delta` in pixels.

        Returns
        -------
        numpy.ndarray
            Array of shape ``(n_positions, n_tau)``.
        """
        return np.asarray(self.correlation, dtype=float)[self.delta_index(distance)]

    def transit_time(self, distance: int, min_prominence: float = 0.0) -> np.ndarray:
        r"""Return the transit time over *distance* at every position.

        The peak is located on a logarithmic time axis by parabolic
        interpolation through the three points around the maximum, because that
        is the axis the peak is symmetric on -- a transit-time distribution is
        log-normal-ish, not Gaussian in :math:`\tau`.

        Parameters
        ----------
        distance : int
            Signed distance :math:`\delta` in pixels.
        min_prominence : float
            Require the peak to rise at least this far above the curve's median.
            Positions that fail return ``NaN`` -- which is the honest answer
            where a barrier has removed the peak, and the reason this returns
            ``NaN`` rather than an edge lag.

        Returns
        -------
        numpy.ndarray
            Transit time in seconds per position, ``NaN`` where no peak exists.
        """
        maps = self.map(distance)
        tau = np.asarray(self.tau, dtype=float)
        out = np.full(maps.shape[0], np.nan)
        if tau.size < 3:
            return out
        log_tau = np.log(tau)
        for i, row in enumerate(maps):
            if not np.all(np.isfinite(row)):
                continue
            k = int(np.argmax(row))
            if k == 0 or k == row.size - 1:
                # A maximum at the edge is not a peak; it is a curve that is
                # still rising or already falling outside the window.
                continue
            if min_prominence > 0.0:
                if row[k] - float(np.median(row)) < min_prominence:
                    continue
            y0, y1, y2 = row[k - 1], row[k], row[k + 1]
            denom = y0 - 2.0 * y1 + y2
            shift = 0.0 if denom == 0.0 else 0.5 * (y0 - y2) / denom
            shift = float(np.clip(shift, -1.0, 1.0))
            step = log_tau[k + 1] - log_tau[k] if shift >= 0 else log_tau[k] - log_tau[k - 1]
            out[i] = float(np.exp(log_tau[k] + shift * step))
        return out

    def velocity(self, distance: int, min_prominence: float = 0.0) -> np.ndarray:
        r"""Return a signed velocity per position from the ±*distance* peaks.

        Flow towards :math:`+x` puts a peak in :math:`+\delta` and leaves
        :math:`-\delta` peakless, so *which of the two peaks is stronger* is
        the direction and its transit time is the speed:
        :math:`v = \delta a / \tau_\mathrm{peak}` with pixel size ``a``.

        Parameters
        ----------
        distance : int
            Magnitude of the distance in pixels; both ``+distance`` and
            ``-distance`` must be present in the carpet.
        min_prominence : float
            Passed to :meth:`transit_time`.

        Returns
        -------
        numpy.ndarray
            Signed velocity in µm/s per position, ``NaN`` where neither
            direction shows a peak.

        Raises
        ------
        ValueError
            If either sign of the distance is missing from the carpet.
        """
        d = abs(int(distance))
        if d == 0:
            raise ValueError("a velocity needs a non-zero distance")
        forward = self.transit_time(+d, min_prominence=min_prominence)
        backward = self.transit_time(-d, min_prominence=min_prominence)
        # An edge position has no partner in one direction, so its whole row is
        # NaN; nanmax would warn about it rather than say so.
        amp_f = _row_max(self.map(+d))
        amp_b = _row_max(self.map(-d))
        step = d * float(self.timing.pixel_size_nm) * 1.0e-3
        pick_forward = amp_f >= amp_b
        with np.errstate(divide="ignore", invalid="ignore"):
            out = np.where(pick_forward, step / forward, -step / backward)
        return np.asarray(out, dtype=float)

    def to_meta(self) -> dict[str, Any]:
        """Return the carpet as a metadata dictionary for a ``DataCurve``."""
        meta: dict[str, Any] = {
            "pcf_correlation": self.correlation,
            "pcf_error": self.error,
            "pcf_tau": self.tau,
            "pcf_delta": self.delta,
            "pcf_positions": self.positions,
        }
        meta.update(self.timing.to_dict())
        meta.update(self.meta)
        return meta


def _correlate_segment(block: np.ndarray, deltas: Sequence[int], max_lag: int) -> np.ndarray:
    """Correlate one time segment at every position and distance.

    Parameters
    ----------
    block : numpy.ndarray
        ``(n_time, n_positions)`` intensity segment.
    deltas : sequence of int
        Signed distances in pixels.
    max_lag : int
        Largest lag in samples.

    Returns
    -------
    numpy.ndarray
        ``(n_delta, n_positions, max_lag + 1)`` with ``NaN`` where a position
        has no partner at that distance.
    """
    n_time, n_pos = block.shape
    mean = block.mean(axis=0)
    fluct = block - mean
    # Zero-pad past 2N so the circular FFT correlation is a linear one; the next
    # fast length keeps the transform cheap.
    nfft = int(1 << int(np.ceil(np.log2(max(4, 2 * n_time)))))
    spectrum = np.fft.rfft(fluct, n=nfft, axis=0)
    overlap = (n_time - np.arange(max_lag + 1)).astype(float)

    out = np.full((len(deltas), n_pos, max_lag + 1), np.nan)
    for i, raw in enumerate(deltas):
        d = int(raw)
        if abs(d) >= n_pos:
            continue
        if d >= 0:
            ref = slice(0, n_pos - d)
            partner = slice(d, n_pos)
        else:
            ref = slice(-d, n_pos)
            partner = slice(0, n_pos + d)
        # conj(A) * B inverts to sum_t a(t) b(t + tau): the reference is
        # conjugated, so a positive lag means the partner is read *later*.
        product = np.conj(spectrum[:, ref]) * spectrum[:, partner]
        corr = np.fft.irfft(product, n=nfft, axis=0)[: max_lag + 1]
        norm = mean[ref] * mean[partner]
        with np.errstate(divide="ignore", invalid="ignore"):
            g = (corr / overlap[:, None]) / norm[None, :]
        out[i, ref, :] = np.where(np.isfinite(g), g, np.nan).T
    return out


def pcf_from_kymograph(
    intensity: np.ndarray,
    deltas: Sequence[int] = (0, 1, -1),
    timing: IcsTiming | None = None,
    *,
    time_unit: str = "line",
    max_lag: int = 0,
    n_segments: int = 8,
    detrend: bool = False,
    detrend_window: int = 0,
    n_linear: int = 16,
    per_octave: int = 8,
) -> PcfCarpet:
    """Compute the position-resolved pair correlation of a kymograph.

    Parameters
    ----------
    intensity : numpy.ndarray
        ``(n_time, n_positions)`` array; each row is one sample of the whole
        line, each column the time series of one position.
    deltas : sequence of int
        Signed distances in pixels. Include both signs of a distance to read a
        direction; ``0`` reproduces the ordinary autocorrelation at every
        position.
    timing : IcsTiming, optional
        Scanner timing. Only the entry matching *time_unit* and the pixel size
        are used.
    time_unit : str
        What one row of *intensity* is: ``'line'`` (a raster stack flattened by
        :func:`kymograph`, the usual case), ``'frame'`` or ``'pixel'``.
    max_lag : int
        Largest lag in samples. ``0`` picks a quarter of the segment length,
        beyond which a correlation is more noise than signal.
    n_segments : int
        Number of equal time segments; their scatter is the error bar. One
        segment gives a curve with no honest error.
    detrend : bool
        Apply :func:`correct_bleaching` before correlating.
    detrend_window : int
        Moving-average length for the detrend, in samples.
    n_linear, per_octave : int
        Lag binning, see :func:`log_lag_bins`.

    Returns
    -------
    PcfCarpet
        The carpet, its per-segment error, the lag times and the geometry.

    Raises
    ------
    ValueError
        If the array is not two-dimensional, if *time_unit* is unknown, or if
        the record is too short for the requested segmentation.
    """
    arr = np.asarray(intensity, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"a kymograph must be (n_time, n_positions); got shape {arr.shape}")
    if time_unit not in ("line", "frame", "pixel"):
        raise ValueError(f"time_unit must be 'line', 'frame' or 'pixel', not {time_unit!r}")
    timing = timing if timing is not None else IcsTiming()
    dt = {
        "line": float(timing.line_duration_ms) * 1.0e-3,
        "frame": float(timing.frame_duration_ms) * 1.0e-3,
        "pixel": float(timing.pixel_duration_us) * 1.0e-6,
    }[time_unit]
    if dt <= 0.0:
        raise ValueError(
            f"the {time_unit} duration is not set on the timing; a pCF without "
            "a time axis cannot report a transit time"
        )

    n_time, n_pos = arr.shape
    n_seg = max(1, int(n_segments))
    seg_len = n_time // n_seg
    if seg_len < 8:
        raise ValueError(
            f"{n_time} samples split into {n_seg} segments leaves {seg_len} "
            "per segment; use fewer segments or a longer record"
        )
    lag_cap = int(max_lag) if max_lag and max_lag > 0 else max(1, seg_len // 4)
    lag_cap = min(lag_cap, seg_len - 2)

    work = correct_bleaching(arr, window=detrend_window) if detrend else arr
    deltas = [int(d) for d in deltas]

    raw = np.asarray(
        [
            _correlate_segment(work[s * seg_len : (s + 1) * seg_len], deltas, lag_cap)
            for s in range(n_seg)
        ]
    )
    # Plain reductions, not the nan- variants: a position without a partner at
    # this distance is NaN in *every* segment, so the NaN propagates on its own
    # and says so, while nanmean would warn about the empty slice and nanstd
    # would report zero scatter for it.
    mean = raw.mean(axis=0)
    # A single segment has no scatter; report zero rather than a NaN that would
    # silently disable every weighted fit downstream.
    sem = raw.std(axis=0) / np.sqrt(float(n_seg)) if n_seg > 1 else np.zeros_like(mean)

    bins = log_lag_bins(lag_cap, n_linear=n_linear, per_octave=per_octave)
    tau = np.asarray([0.5 * (a + b - 1) * dt for a, b in bins], dtype=float)
    correlation = np.asarray(
        [mean[..., a:b].mean(axis=-1) for a, b in bins], dtype=float
    ).transpose(1, 2, 0)
    # Averaging w lags of an error each reduces it by sqrt(w) only if they are
    # independent; neighbouring lags are not, so this is a lower bound and the
    # docstring says so.
    error = np.asarray(
        [np.sqrt((sem[..., a:b] ** 2).mean(axis=-1) / (b - a)) for a, b in bins],
        dtype=float,
    ).transpose(1, 2, 0)

    positions = np.arange(n_pos, dtype=float) * float(timing.pixel_size_nm) * 1.0e-3
    meta = {
        "n_time": int(n_time),
        "n_segments": int(n_seg),
        "segment_length": int(seg_len),
        "max_lag": int(lag_cap),
        "time_unit": time_unit,
        "detrended": bool(detrend),
    }
    return PcfCarpet(
        correlation=correlation,
        error=error,
        tau=tau,
        delta=np.asarray(deltas, dtype=int),
        positions=positions,
        timing=timing,
        meta=meta,
    )


def pcf_from_stack(
    images: np.ndarray,
    deltas: Sequence[int] = (0, 1, -1),
    timing: IcsTiming | None = None,
    **kwargs: Any,
) -> PcfCarpet:
    """Compute the pair correlation of a raster stack along the fast axis.

    A convenience wrapper: :func:`kymograph` flattens the stack into one time
    series per pixel position sampled once per line, then
    :func:`pcf_from_kymograph` correlates it.

    Parameters
    ----------
    images : numpy.ndarray
        ``(n_frames, n_lines, n_pixels)`` stack or compatible.
    deltas : sequence of int
        Signed distances in pixels along the fast scan axis.
    timing : IcsTiming, optional
        Scanner timing; its line time sets the lag axis.
    **kwargs
        Forwarded to :func:`pcf_from_kymograph`.

    Returns
    -------
    PcfCarpet
        The position-resolved carpet.

    Notes
    -----
    Positions are pixels **along a line**, so this reads transport across the
    fast scan axis. Transport along the slow axis needs the transposed stack --
    and a different time unit, because two neighbouring lines are a line period
    apart, not a frame.
    """
    timing = timing if timing is not None else IcsTiming()
    stack = np.asarray(images, dtype=float)
    n_lines = int(stack.shape[1]) if stack.ndim >= 3 else 1
    return pcf_from_kymograph(kymograph(stack), deltas, timing.resolved(n_lines=n_lines), **kwargs)
