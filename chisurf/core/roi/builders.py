"""Build regions of interest from image data.

Where :mod:`chisurf.core.roi.roi` defines what a region *is*, this module
derives one from an image. The main entry point is :func:`arbitrary_region`, a
port of the reference suite's "arbitrary region" selection: a pixel is kept only
if its **local** statistics resemble those of its **neighbourhood**.

That two-scale comparison is what makes it more useful than a plain intensity
threshold. An aggregate, a piece of debris or a dead patch is not necessarily
brighter or dimmer than the image as a whole — but it is anomalous compared to
the area immediately around it, and that is what gets rejected here.
"""

from __future__ import annotations

import numpy as np

from .roi import ROI, MaskROI


def _box_mean(image: np.ndarray, size: int, mode: str = "nearest") -> np.ndarray:
    """Return the running mean of *image* over a square window.

    Parameters
    ----------
    image : numpy.ndarray
        2-D image.
    size : int
        Window edge length in pixels.
    mode : str
        Boundary handling passed to the uniform filter.

    Returns
    -------
    numpy.ndarray
        The windowed mean, same shape as the input.
    """
    from scipy.ndimage import uniform_filter

    return uniform_filter(np.asarray(image, dtype=float), size=size, mode=mode)


def local_statistics(
    image: np.ndarray, size: int, mode: str = "nearest"
) -> tuple[np.ndarray, np.ndarray]:
    """Return the running mean and population variance over a square window.

    Parameters
    ----------
    image : numpy.ndarray
        2-D image.
    size : int
        Window edge length in pixels.
    mode : str
        Boundary handling. The reference implementation zero-pads, which biases
        every border pixel downwards and makes the frame edge look anomalous;
        ``'nearest'`` avoids that spurious rejection.

    Returns
    -------
    tuple of numpy.ndarray
        ``(mean, variance)``. The variance carries the sample-to-population
        correction ``n²/(n² - 1)`` for a window of ``n × n`` pixels.
    """
    n = int(size)
    mean = _box_mean(image, n, mode)
    mean_sq = _box_mean(np.asarray(image, dtype=float) ** 2, n, mode)
    var = mean_sq - mean**2
    if n > 1:
        var = var * (n**2 / (n**2 - 1.0))
    return mean, np.maximum(var, 0.0)


def arbitrary_region(
    images: np.ndarray,
    *,
    intensity_min: float | None = None,
    intensity_max: float | None = None,
    window: int = 3,
    neighbourhood: int = 9,
    intensity_fold_min: float | None = None,
    intensity_fold_max: float | None = None,
    variance_fold_min: float | None = None,
    variance_fold_max: float | None = None,
    median_filter: bool = False,
    mode: str = "nearest",
    name: str = "arbitrary region",
) -> ROI:
    """Select pixels whose local statistics match their neighbourhood.

    Two stages, both optional:

    1. **Absolute intensity** — drop pixels of the frame-averaged image outside
       ``[intensity_min, intensity_max]``. Averaging over frames first is what
       makes this usable at the low per-pixel counts typical of a photon image.
    2. **Local versus neighbourhood** — compare the mean and variance in a small
       ``window`` against those in a larger ``neighbourhood`` centred on the same
       pixel, and drop pixels whose ratio falls outside the given folds.

    The fold tests are the substance. A bright aggregate has a local mean far
    above its surroundings (caught by ``intensity_fold_max``); an immobile
    speck has an anomalously *low* local variance (caught by
    ``variance_fold_min``); a noisy or saturated patch has an anomalously high
    one (``variance_fold_max``). None of those need be outliers in the image as
    a whole, which is why an absolute threshold alone misses them.

    Parameters
    ----------
    images : numpy.ndarray
        Image stack ``(n_frames, ny, nx)`` or a single 2-D frame.
    intensity_min, intensity_max : float, optional
        Absolute bounds on the frame-averaged intensity. ``None`` leaves that
        side open.
    window : int
        Edge length of the small (local) window, in pixels.
    neighbourhood : int
        Edge length of the large (context) window. Must exceed ``window`` for
        the fold tests to mean anything.
    intensity_fold_min, intensity_fold_max : float, optional
        Keep pixels with ``local_mean > neighbourhood_mean * fold_min`` and
        ``local_mean < neighbourhood_mean * fold_max``. Sensible values bracket
        1, e.g. ``0.5`` and ``2.0``.
    variance_fold_min, variance_fold_max : float, optional
        The same test applied to the local variance.
    median_filter : bool
        Apply a median filter of size ``window`` to the intensity mask, removing
        isolated single-pixel holes and specks.
    mode : str
        Boundary handling for the window filters.
    name : str
        Label for the returned region.

    Returns
    -------
    ROI
        A :class:`~chisurf.core.roi.MaskROI` over the frame shape, ready to
        combine with any other region.

    Raises
    ------
    ValueError
        If the stack is not 2- or 3-dimensional, or the windows are not ordered.

    Examples
    --------
    An image with one anomalously bright speck, rejected on its local contrast
    while the uniform background survives:

    >>> img = np.ones((32, 32)) * 10.0
    >>> img[16, 16] = 500.0
    >>> roi = arbitrary_region(img, window=3, neighbourhood=9,
    ...                        intensity_fold_max=2.0)
    >>> bool(roi.to_mask((32, 32))[16, 16])
    False
    >>> bool(roi.to_mask((32, 32))[4, 4])
    True
    """
    stack = np.asarray(images, dtype=float)
    if stack.ndim == 2:
        stack = stack[None, ...]
    if stack.ndim != 3:
        raise ValueError(f"expected a 2-D frame or a 3-D stack; got {stack.shape}")
    if int(neighbourhood) <= int(window):
        raise ValueError(f"neighbourhood ({neighbourhood}) must be larger than window ({window})")

    mean_image = stack.mean(axis=0)
    keep = np.ones(mean_image.shape, dtype=bool)

    # ── stage 1: absolute intensity on the frame average ──
    if intensity_min is not None:
        keep &= mean_image >= float(intensity_min)
    if intensity_max is not None:
        keep &= mean_image <= float(intensity_max)
    if median_filter:
        from scipy.ndimage import median_filter as _median

        keep = _median(keep.astype(np.uint8), size=int(window)).astype(bool)

    # ── stage 2: local versus neighbourhood, evaluated per frame ──
    folds = (
        intensity_fold_min,
        intensity_fold_max,
        variance_fold_min,
        variance_fold_max,
    )
    if any(f is not None for f in folds):
        for frame in stack:
            m_small, v_small = local_statistics(frame, int(window), mode)
            m_large, v_large = local_statistics(frame, int(neighbourhood), mode)
            if intensity_fold_min is not None:
                keep &= m_small > m_large * float(intensity_fold_min)
            if intensity_fold_max is not None:
                keep &= m_small < m_large * float(intensity_fold_max)
            if variance_fold_min is not None:
                keep &= v_small > v_large * float(variance_fold_min)
            if variance_fold_max is not None:
                keep &= v_small < v_large * float(variance_fold_max)

    return MaskROI(keep, name=name)
