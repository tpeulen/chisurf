"""Inter-frame drift estimation and correction for image stacks.

Stage drift moves the sample between frames. For intensity work that is a
cosmetic blur; for correlation work it is a systematic error, because a
translation between two frames looks exactly like the decorrelation that
diffusion produces. It therefore inflates the diffusion coefficient fitted from
long frame lags — precisely the region a spatiotemporal correlation carpet
exposes (see :mod:`chisurf.core.experiments.ics`).

The estimator is the classic FFT cross-correlation between a reference frame
and each later frame, with the correlation smoothed before the peak search so
that a noisy tie between two neighbouring pixels cannot flip the answer. It
assumes pure translation: no rotation, no scaling.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np

REFERENCES = ("first", "previous", "mean")


def _reference_stack(images: np.ndarray, reference: str) -> np.ndarray:
    """Return the reference frame used for each frame of the stack.

    Parameters
    ----------
    images : numpy.ndarray
        Stack of shape ``(n_frames, ny, nx)``.
    reference : str
        ``'first'``, ``'previous'`` or ``'mean'``.

    Returns
    -------
    numpy.ndarray
        Stack of the same shape holding the reference for each frame.

    Raises
    ------
    ValueError
        If the reference mode is unknown.
    """
    if reference == "first":
        return np.repeat(images[:1], len(images), axis=0)
    if reference == "previous":
        return np.concatenate([images[:1], images[:-1]], axis=0)
    if reference == "mean":
        return np.repeat(images.mean(axis=0, keepdims=True), len(images), axis=0)
    raise ValueError(f"unknown reference {reference!r}; expected one of {REFERENCES}")


def _peak_shift(correlation: np.ndarray, subpixel: bool) -> Tuple[float, float]:
    """Return the ``(dy, dx)`` offset of the correlation peak from the centre.

    Parameters
    ----------
    correlation : numpy.ndarray
        Zero-lag-centred cross-correlation map.
    subpixel : bool
        Refine the integer peak by a parabolic fit through its neighbours.

    Returns
    -------
    tuple of float
        Shift in pixels along ``(y, x)``.
    """
    ny, nx = correlation.shape
    iy, ix = np.unravel_index(int(np.argmax(correlation)), correlation.shape)
    dy = float(iy) - ny // 2
    dx = float(ix) - nx // 2

    if subpixel:
        # Parabolic interpolation through the peak and its two neighbours on
        # each axis. Skipped at the border, where a neighbour is missing.
        if 0 < iy < ny - 1:
            a, b, c = correlation[iy - 1, ix], correlation[iy, ix], correlation[iy + 1, ix]
            denom = a - 2.0 * b + c
            if denom != 0:
                dy += 0.5 * (a - c) / denom
        if 0 < ix < nx - 1:
            a, b, c = correlation[iy, ix - 1], correlation[iy, ix], correlation[iy, ix + 1]
            denom = a - 2.0 * b + c
            if denom != 0:
                dx += 0.5 * (a - c) / denom
    return dy, dx


def estimate_drift(
    images: np.ndarray,
    reference: str = "first",
    roi=None,
    smooth: float = 2.0,
    subpixel: bool = False,
) -> np.ndarray:
    """Estimate the translation of every frame relative to a reference.

    Parameters
    ----------
    images : numpy.ndarray
        Image stack ``(n_frames, ny, nx)``.
    reference : str
        ``'first'`` compares every frame with frame 0 (what PAM's MIA does, and
        the right choice when drift is slow and monotonic); ``'previous'``
        compares consecutive frames and accumulates, which tracks non-monotonic
        wander better but lets error accumulate; ``'mean'`` compares against the
        stack average.
    roi : ROI, optional
        Restrict the estimate to a region — a bright, structured patch gives a
        far sharper correlation peak than a mostly-empty field. Any
        :class:`chisurf.core.roi.ROI`; its bounding box is used.
    smooth : float
        Standard deviation, in pixels, of the Gaussian applied to the
        correlation before the peak search. Guards against a noise-driven tie
        between neighbouring pixels. Zero disables it.
    subpixel : bool
        Refine each integer peak by parabolic interpolation.

    Returns
    -------
    numpy.ndarray
        Array of shape ``(n_frames, 2)`` holding the ``(dy, dx)`` shift of each
        frame relative to the reference. Row 0 is ``(0, 0)`` for ``'first'``
        and ``'previous'``, where frame 0 is the reference itself; under
        ``'mean'`` it is measured like every other frame, because the stack
        average is not frame 0.

    Examples
    --------
    A stack whose frames are rolled by a known amount recovers that amount:

    >>> rng = np.random.default_rng(0)
    >>> base = rng.random((32, 32))
    >>> stack = np.stack([np.roll(base, (dy, dx), axis=(0, 1))
    ...                   for dy, dx in [(0, 0), (2, -3), (4, -6)]])
    >>> estimate_drift(stack).tolist()
    [[0.0, 0.0], [2.0, -3.0], [4.0, -6.0]]
    """
    stack = np.asarray(images, dtype=float)
    if stack.ndim != 3:
        raise ValueError(f"drift estimation needs a (n_frames, ny, nx) stack; got {stack.shape}")
    n_frames = stack.shape[0]
    if n_frames < 2:
        return np.zeros((n_frames, 2), dtype=float)

    if roi is not None:
        box = roi.bounding_box(stack.shape[1:], image=stack)
        if box is not None:
            r0, c0, r1, c1 = box
            stack = stack[:, r0:r1, c0:c1]

    refs = _reference_stack(stack, reference)

    gaussian_filter = None
    if smooth and smooth > 0:
        try:
            from scipy.ndimage import gaussian_filter  # type: ignore[assignment]
        except Exception:  # pragma: no cover - scipy is a hard dependency
            gaussian_filter = None

    shifts = np.zeros((n_frames, 2), dtype=float)
    # Frame 0 *is* the reference under 'first' and 'previous', so its shift is
    # zero by construction and measuring it would only spend an FFT. Under
    # 'mean' the reference is the stack average, from which frame 0 is
    # displaced like any other frame — leaving it at zero would misalign it
    # from the whole corrected stack.
    first = 0 if reference == "mean" else 1
    for k in range(first, n_frames):
        a = refs[k] - refs[k].mean()
        b = stack[k] - stack[k].mean()
        corr = np.fft.fftshift(
            np.real(np.fft.ifft2(np.fft.fft2(a) * np.conj(np.fft.fft2(b))))
        )
        if gaussian_filter is not None:
            # Wrap, not the default reflect: an FFT cross-correlation is
            # *circular*, so the lag axis has no edge — index 0 and index n-1
            # are neighbours. Reflecting there mirrors the peak back onto
            # itself, and a peak near the maximum unambiguous lag gets dragged
            # by a whole pixel. On a 32-pixel frame a true shift of 15 was
            # reported as 16, which then misaligns that frame in every
            # correlation it takes part in.
            corr = gaussian_filter(corr, smooth, mode="wrap")
        dy, dx = _peak_shift(corr, subpixel)
        # The correlation peak sits at the offset that maps the frame onto the
        # reference, i.e. the correction. Negate it so the returned number is
        # the *measured displacement* of the sample, which is what "drift"
        # means and what is worth plotting.
        shifts[k] = (-dy, -dx)

    if reference == "previous":
        # Consecutive-frame shifts accumulate into an absolute displacement.
        shifts = np.cumsum(shifts, axis=0)
    return shifts


def apply_drift(
    images: np.ndarray,
    shifts: np.ndarray,
    mode: str = "wrap",
    cval: float = 0.0,
) -> np.ndarray:
    """Shift every frame back by its estimated drift.

    Parameters
    ----------
    images : numpy.ndarray
        Image stack ``(n_frames, ny, nx)``.
    shifts : numpy.ndarray
        ``(n_frames, 2)`` array of ``(dy, dx)`` displacements, as returned by
        :func:`estimate_drift`.
    mode : str
        ``'wrap'`` rolls each frame, keeping every photon but wrapping the
        content that leaves one edge back in at the other (what PAM does).
        ``'constant'`` shifts without wrapping and fills the vacated strip with
        ``cval`` — honest about the missing data, at the cost of an edge that
        no longer carries signal.
    cval : float
        Fill value for ``mode='constant'``.

    Returns
    -------
    numpy.ndarray
        The corrected stack.

    Raises
    ------
    ValueError
        If the shift array does not match the stack, or the mode is unknown.

    Notes
    -----
    *shifts* are measured displacements, so each frame is moved by the
    **negative** of its entry to bring it back onto the reference.
    """
    stack = np.asarray(images, dtype=float)
    sh = np.asarray(shifts, dtype=float)
    if stack.ndim != 3:
        raise ValueError(f"drift correction needs a (n_frames, ny, nx) stack; got {stack.shape}")
    if sh.shape != (stack.shape[0], 2):
        raise ValueError(
            f"shifts must be ({stack.shape[0]}, 2) to match the stack; got {sh.shape}"
        )
    if mode not in ("wrap", "constant"):
        raise ValueError(f"unknown mode {mode!r}; expected 'wrap' or 'constant'")

    out = np.empty_like(stack)
    ny, nx = stack.shape[1:]
    for k, (dy, dx) in enumerate(sh):
        # Move each frame back by its measured displacement.
        iy, ix = int(round(-dy)), int(round(-dx))
        if mode == "wrap":
            out[k] = np.roll(stack[k], (iy, ix), axis=(0, 1))
        else:
            frame = np.full((ny, nx), float(cval))
            # Source window [sy0, sy1) maps onto destination [dy0, dy1).
            sy0, sy1 = max(0, -iy), min(ny, ny - iy)
            sx0, sx1 = max(0, -ix), min(nx, nx - ix)
            if sy1 > sy0 and sx1 > sx0:
                frame[sy0 + iy:sy1 + iy, sx0 + ix:sx1 + ix] = stack[k, sy0:sy1, sx0:sx1]
            out[k] = frame
    return out


def correct_drift(
    images: np.ndarray,
    reference: str = "first",
    roi=None,
    smooth: float = 2.0,
    subpixel: bool = False,
    mode: str = "wrap",
    cval: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Estimate and remove inter-frame drift in one step.

    Parameters
    ----------
    images : numpy.ndarray
        Image stack ``(n_frames, ny, nx)``.
    reference, roi, smooth, subpixel
        Passed to :func:`estimate_drift`.
    mode, cval
        Passed to :func:`apply_drift`.

    Returns
    -------
    tuple
        ``(corrected_stack, shifts)``. Keeping the shifts is worthwhile: their
        magnitude tells you whether the correction mattered, and a drift larger
        than the beam waist means the long frame lags were compromised before
        correction.
    """
    shifts = estimate_drift(
        images, reference=reference, roi=roi, smooth=smooth, subpixel=subpixel
    )
    return apply_drift(images, shifts, mode=mode, cval=cval), shifts


def clsm_transform_pairs(
    shape: Sequence[int], shifts: np.ndarray, mode: str = "wrap"
) -> np.ndarray:
    """Return the source/target pixel-index pairs that undo a drift in a CLSM image.

    A confocal image reconstructed from a photon stream is not an array of
    intensities but an array of *photon lists*, so correcting it means moving
    photons between pixels rather than resampling numbers. The photon library
    expresses that as an interleaved ``(source, target, source, target, ...)``
    array of flat pixel indices, where a pixel index is
    ``frame * n_lines * n_pixels + line * n_pixels + pixel``.

    Correcting at photon level, rather than shifting a rendered image, is what
    keeps every downstream analysis valid: micro-times, lifetimes and
    correlations all still see real photons in the pixel they belong to.

    Parameters
    ----------
    shape : sequence of int
        CLSM shape ``(n_frames, n_lines, n_pixels)``.
    shifts : numpy.ndarray
        ``(n_frames, 2)`` measured displacements, from :func:`estimate_drift`.
    mode : str
        ``'wrap'`` maps every pixel onto some target, so no photon is lost (the
        photon-level equivalent of PAM's ``circshift``). ``'constant'`` drops
        photons that would move outside the frame.

    Returns
    -------
    numpy.ndarray
        Interleaved ``uint32`` source/target index pairs, ready to hand to the
        image's ``transform`` method.

    Raises
    ------
    ValueError
        If the shift array does not match the frame count, or the mode is
        unknown.
    """
    n_frames, n_lines, n_pixels = (int(v) for v in shape)
    sh = np.asarray(shifts, dtype=float)
    if sh.shape != (n_frames, 2):
        raise ValueError(f"shifts must be ({n_frames}, 2); got {sh.shape}")
    if mode not in ("wrap", "constant"):
        raise ValueError(f"unknown mode {mode!r}; expected 'wrap' or 'constant'")

    rows = np.arange(n_lines)
    cols = np.arange(n_pixels)
    grid_y, grid_x = np.meshgrid(rows, cols, indexing="ij")

    pairs: List[np.ndarray] = []
    for f in range(n_frames):
        dy, dx = int(round(-sh[f, 0])), int(round(-sh[f, 1]))
        ty, tx = grid_y + dy, grid_x + dx
        if mode == "wrap":
            ty %= n_lines
            tx %= n_pixels
            keep = np.ones(ty.shape, dtype=bool)
        else:
            keep = (ty >= 0) & (ty < n_lines) & (tx >= 0) & (tx < n_pixels)
        base = f * n_lines * n_pixels
        src = base + grid_y[keep] * n_pixels + grid_x[keep]
        dst = base + ty[keep] * n_pixels + tx[keep]
        pairs.append(np.stack([src, dst], axis=1).ravel())

    if not pairs:
        return np.zeros(0, dtype=np.uint32)
    return np.concatenate(pairs).astype(np.uint32)


def correct_clsm_drift(
    clsm,
    channel_image: Optional[np.ndarray] = None,
    reference: str = "first",
    roi=None,
    smooth: float = 2.0,
    subpixel: bool = False,
    mode: str = "wrap",
) -> np.ndarray:
    """Estimate and remove drift from a confocal image **in place**, photon by photon.

    Parameters
    ----------
    clsm : tttrlib.CLSMImage
        The image to correct. Its pixel contents are rearranged in place.
    channel_image : numpy.ndarray, optional
        Stack ``(n_frames, ny, nx)`` to estimate the drift from. Defaults to
        the image's own intensity. Supplying it lets a bright, structured
        channel drive the correction of all channels, as PAM does when it
        measures drift on channel 1 and applies it to the rest.
    reference, roi, smooth, subpixel
        Passed to :func:`estimate_drift`.
    mode : str
        ``'wrap'`` (conserve every photon) or ``'constant'`` (drop photons that
        leave the frame).

    Returns
    -------
    numpy.ndarray
        The ``(n_frames, 2)`` measured displacements that were removed.

    Raises
    ------
    ValueError
        If the estimation stack does not match the image's frame geometry.
    """
    intensity = np.asarray(clsm.intensity)
    n_frames, n_lines, n_pixels = intensity.shape

    source = intensity if channel_image is None else np.asarray(channel_image)
    if source.shape[0] != n_frames:
        raise ValueError(
            f"the estimation stack has {source.shape[0]} frames but the image has {n_frames}"
        )

    shifts = estimate_drift(
        source.astype(float), reference=reference, roi=roi,
        smooth=smooth, subpixel=subpixel,
    )
    pairs = clsm_transform_pairs((n_frames, n_lines, n_pixels), shifts, mode=mode)
    if pairs.size:
        clsm.transform(pairs)
    return shifts
