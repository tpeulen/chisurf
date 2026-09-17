"""Spatiotemporal image correlation: one carpet for RICS, STICS, TICS and iMSD.

The correlator computes :math:`G(\\xi, \\psi, \\Delta)` -- the correlation of an
image stack over the fast-axis lag :math:`\\xi`, the slow-axis lag :math:`\\psi`
and the frame lag :math:`\\Delta`. Restricting :math:`\\Delta` to ``0`` gives a
classic RICS map; adding frame lags extends the same object along the time axis,
which is all that separates RICS from STICS, TICS and iMSD (see
:func:`chisurf.core.experiments.ics.data.lag_time`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

try:
    import tttrlib
except Exception:  # pragma: no cover - optional at import time
    tttrlib = None  # type: ignore[assignment]

from chisurf.core.roi import as_mask

from .data import IcsCarpet, IcsSettings


def _ensure_3d_stack(images: np.ndarray) -> np.ndarray:
    """Return images as an ``(n_frames, ny, nx)`` stack.

    Parameters
    ----------
    images : numpy.ndarray
        A single frame ``(ny, nx)``, a stack ``(n_frames, ny, nx)``, or a
        multi-channel stack ``(n_frames, ny, nx, n_channels)`` which is summed
        over its channels.

    Returns
    -------
    numpy.ndarray
        Float stack of shape ``(n_frames, ny, nx)``.

    Raises
    ------
    ValueError
        If the array shape cannot be interpreted as an image stack.
    """
    # The correlation backend reads the buffer directly, so a non-contiguous
    # view (e.g. an ROI slice of a larger stack) must be materialised first.
    arr = np.ascontiguousarray(np.asarray(images, dtype=float))
    if arr.ndim == 2:
        return arr[None, ...]
    if arr.ndim == 3:
        return arr
    if arr.ndim == 4:
        return np.ascontiguousarray(arr.sum(axis=-1))
    raise ValueError(f"Unsupported image array shape for ICS: {arr.shape}")


def frame_pairs(n_frames: int, frame_lag: int) -> list[tuple[int, int]]:
    """Return the frame pairs that realise a given frame lag.

    Parameters
    ----------
    n_frames : int
        Number of frames in the stack.
    frame_lag : int
        The frame lag :math:`\\Delta`.

    Returns
    -------
    list of tuple of int
        Pairs ``(i, i + Delta)`` for every frame that has a partner. Empty when
        the lag exceeds the stack length.

    Examples
    --------
    >>> frame_pairs(4, 0)
    [(0, 0), (1, 1), (2, 2), (3, 3)]
    >>> frame_pairs(4, 2)
    [(0, 2), (1, 3)]
    """
    d = int(frame_lag)
    if d < 0:
        d = -d
    if n_frames <= 0 or d >= n_frames:
        return []
    return [(i, i + d) for i in range(n_frames - d)]


def normalise_ics(
    ics_stack: np.ndarray,
    images: np.ndarray,
    x_range: Sequence[int],
    y_range: Sequence[int],
    mask: np.ndarray | None = None,
) -> np.ndarray:
    """Normalise a raw correlation stack to ``G`` when the correlator did not.

    Some builds of the correlator return the unnormalised correlation. The
    reference normalisation is ``G = corr / (<I>^2 * N)`` with ``N`` the number
    of pixels in the region of interest. A raw correlation is recognised by a
    median magnitude far above unity, which a normalised ``G`` cannot have.

    Parameters
    ----------
    ics_stack : numpy.ndarray
        Correlation stack of shape ``(n, ny, nx)``.
    images : numpy.ndarray
        The image stack the correlation was computed from. When a *mask* was
        applied, this is the already-masked stack.
    x_range, y_range : sequence of int
        Region of interest used for the correlation, as ``(start, stop)``.
    mask : numpy.ndarray, optional
        The boolean region the correlation was restricted to, shape
        ``(ny, nx)``. Both ``<I>`` and ``N`` are taken over the pixels it keeps.

    Returns
    -------
    numpy.ndarray
        The normalised correlation stack, or the input unchanged when it was
        already normalised.

    Notes
    -----
    ``<I>`` and ``N`` must describe the *same* set of pixels the correlation was
    computed over. Taking them over the enclosing rectangle instead is wrong
    whenever the region is not that rectangle: the pixels outside it have been
    zeroed, so they drag the mean down while still being counted in ``N``. Since
    ``G(0)`` scales as ``1/N_particles``, that misnormalisation lands directly on
    the reported particle number and concentration.
    """
    finite = np.isfinite(ics_stack)
    if not np.any(finite):
        return ics_stack
    if float(np.median(np.abs(ics_stack[finite]))) <= 1.0:
        return ics_stack

    ny_full, nx_full = int(images.shape[1]), int(images.shape[2])
    x0, x1 = int(x_range[0]), int(x_range[1])
    y0, y1 = int(y_range[0]), int(y_range[1])
    if x1 < 0 or x1 > nx_full:
        x1 = nx_full
    if y1 < 0 or y1 > ny_full:
        y1 = ny_full
    x0, y0 = max(0, x0), max(0, y0)
    roi = images[:, y0:y1, x0:x1]
    sub_mask = None if mask is None else np.asarray(mask, dtype=bool)[y0:y1, x0:x1]
    if roi.ndim != 3 or roi.size == 0:
        roi = images
        sub_mask = None if mask is None else np.asarray(mask, dtype=bool)

    if sub_mask is not None and sub_mask.shape == roi.shape[1:]:
        n_pixels = float(np.count_nonzero(sub_mask))
        if n_pixels <= 0.0:
            return ics_stack
        mean_intensity = float(roi[:, sub_mask].mean())
    else:
        mean_intensity = float(roi.mean())
        n_pixels = float(roi.shape[1] * roi.shape[2])

    norm = mean_intensity**2 * n_pixels
    if not np.isfinite(norm) or norm <= 0.0:
        return ics_stack
    return ics_stack / norm


def compute_ics_carpet(
    images: np.ndarray,
    settings: IcsSettings | None = None,
    mask: np.ndarray | None = None,
    use_fftshift: bool = True,
    **kwargs: Any,
) -> IcsCarpet:
    """Compute the spatiotemporal correlation carpet of an image stack.

    For every requested frame lag :math:`\\Delta` the correlation is averaged
    over all frame pairs separated by :math:`\\Delta`, giving one spatial map
    per lag. The default ``frame_lags=(0,)`` reproduces the classic RICS map;
    passing more lags extends the same carpet along time, which is what STICS,
    TICS and iMSD read.

    Parameters
    ----------
    images : numpy.ndarray
        Image stack of shape ``(n_frames, ny, nx)`` or compatible.
    settings : IcsSettings, optional
        Region of interest, frame lags, background handling and scanner timing.
        Defaults to a full-field, zero-frame-lag (RICS) correlation.
    mask : ROI or numpy.ndarray, optional
        Region to restrict the correlation to: any
        :class:`chisurf.core.roi.ROI` (rasterised against the frame shape and
        the stack, so intensity-dependent regions work) or a ready-made boolean
        array ``(ny, nx)``. The stack is **cropped** to the region's bounding
        box, so the returned maps are the size of that box rather than of the
        input. A region that is not its own bounding box additionally zeroes the
        remaining corners, which biases ``G`` slightly (see Notes).
    use_fftshift : bool
        Centre the zero lag in each spatial map. When false the maps are left in
        FFT order, with the zero lag at ``[0, 0]``, and the returned lag grids
        are built in that same order so that map and grids stay paired.
    **kwargs
        Extra keyword arguments forwarded to the low-level correlator.

    Returns
    -------
    IcsCarpet
        The carpet, its per-lag standard error, the lag grids and the timing.

    Raises
    ------
    RuntimeError
        If the correlation backend is unavailable.
    ValueError
        If none of the requested frame lags is realisable in the stack, or if
        the region selects no pixels.

    Notes
    -----
    A region is applied by **cropping**, not by blanking pixels in place. A
    zeroed pixel is not an absent one: it still enters the correlator's sum and
    the frame average it subtracts from every other pixel, which inflated
    ``G(0)`` — and so deflated the particle number read from it — by about 15 %
    for a rectangle and far more for a ragged region. Cropping is exact whenever
    the region *is* its bounding box. For a ragged region the corners of that
    box must still be zeroed, so a residual bias remains; removing it needs
    correlator-level support for excluded pixels.
    """
    if tttrlib is None:
        raise RuntimeError("tttrlib is not available; cannot compute ICS")

    if settings is None:
        settings = IcsSettings()

    stack = _ensure_3d_stack(images)
    n_frames, ny, nx = stack.shape

    region_mask: np.ndarray | None = None
    if mask is not None:
        m = as_mask(mask, (ny, nx), image=stack)
        if m.shape != (ny, nx):
            raise ValueError(f"Mask shape {m.shape} does not match image shape {(ny, nx)}")
        rows = np.flatnonzero(m.any(axis=1))
        cols = np.flatnonzero(m.any(axis=0))
        if rows.size == 0 or cols.size == 0:
            raise ValueError("The region selects no pixels; nothing to correlate")
        # Crop to the region rather than zeroing it in place. A zeroed pixel is
        # not an absent pixel: it still enters the correlator's sum and its
        # frame-average subtraction, which biases G by ~15 % for a rectangle and
        # far more for a ragged region. Cropping removes those pixels outright,
        # which is exact whenever the region *is* its bounding box.
        y0, y1 = int(rows[0]), int(rows[-1]) + 1
        x0, x1 = int(cols[0]), int(cols[-1]) + 1
        stack = np.ascontiguousarray(stack[:, y0:y1, x0:x1])
        m = m[y0:y1, x0:x1]
        if not m.all():
            # A ragged region still has to zero the corners of its own bounding
            # box, so the bias above is reduced but not removed. Normalising over
            # the kept pixels (below) is the most that can be done without
            # correlator-level support for excluded pixels.
            stack = stack * m[None, ...]
        region_mask = m
        n_frames, ny, nx = stack.shape

    x_range = list(settings.x_range) if settings.x_range is not None else [0, -1]
    y_range = list(settings.y_range) if settings.y_range is not None else [0, -1]

    subtract_average = settings.subtract_average or ""
    if subtract_average not in ("frame", "stack", ""):
        subtract_average = "frame"

    lags = [int(d) for d in settings.frame_lags] or [0]
    maps: list[np.ndarray] = []
    errors: list[np.ndarray] = []
    realised: list[int] = []

    for d in lags:
        pairs = frame_pairs(n_frames, d)
        if not pairs:
            continue
        ics_kwargs: dict[str, Any] = {
            "images": stack,
            "x_range": list(x_range),
            "y_range": list(y_range),
            "subtract_average": subtract_average,
            "frames_index_pairs": pairs,
        }
        ics_kwargs.update(kwargs)
        raw = tttrlib.CLSMImage.compute_ics(**ics_kwargs)  # type: ignore[call-arg]
        # Correlator builds before the compute_ics fix allocate one map per frame
        # *pair* but declare the first dimension as the number of input *frames*.
        # For any lag > 0 there are fewer pairs than frames, so the returned
        # array over-declares its length and touching the tail reads past the
        # allocation. Fixed upstream and ChiSurf builds that source, so this is
        # belt-and-braces against an older local build; slicing to the pair count
        # first only touches shape metadata, never the data.
        raw = np.asarray(raw)[: len(pairs)]
        raw = np.asarray(raw, dtype=float)
        if raw.ndim == 2:
            raw = raw[None, ...]
        raw = normalise_ics(raw, stack, x_range, y_range, mask=region_mask)

        n_pairs = raw.shape[0]
        mean = raw.mean(axis=0)
        err = raw.std(axis=0) / max(1.0, np.sqrt(float(n_pairs)))
        if use_fftshift:
            mean = np.fft.fftshift(mean)
            err = np.fft.fftshift(err)
        maps.append(mean)
        errors.append(err)
        realised.append(d)

    if not maps:
        raise ValueError(f"No frame lag in {lags} is realisable in a stack of {n_frames} frames")

    correlation = np.asarray(maps, dtype=float)
    error = np.asarray(errors, dtype=float)

    ny_out, nx_out = correlation.shape[1], correlation.shape[2]
    line_shift, pixel_shift = np.indices((ny_out, nx_out))
    line_shift = (line_shift - ny_out // 2).astype(float)
    pixel_shift = (pixel_shift - nx_out // 2).astype(float)
    if not use_fftshift:
        # The maps were left in FFT order, so the grids have to follow them: the
        # centred grids above describe a shifted map only. Every consumer pairs a
        # carpet element with the lag at the same index — zero_lag_index, the TICS
        # decay, lag_time_grid and the model fit — so a centred grid over an
        # unshifted map reads the wrong point at every position.
        line_shift = np.fft.ifftshift(line_shift, axes=0)
        pixel_shift = np.fft.ifftshift(pixel_shift, axes=1)

    timing = settings.timing.resolved(n_lines=ny)

    meta: dict[str, Any] = {
        "n_input_frames": int(n_frames),
        "fftshifted": bool(use_fftshift),
        "x_range": tuple(x_range),
        "y_range": tuple(y_range),
        "subtract_average": subtract_average,
    }

    return IcsCarpet(
        correlation=correlation,
        error=error,
        pixel_shift=pixel_shift,
        line_shift=line_shift,
        frame_lags=np.asarray(realised, dtype=int),
        timing=timing,
        meta=meta,
    )
