"""Number & Brightness (N&B) analysis of image stacks.

Qt-free estimators for the moment analysis of Digman et al. (2008): the
per-pixel mean and variance over the frame (time) axis of an image stack give
an *apparent* brightness ``B = σ²/⟨k⟩`` and number ``N = ⟨k⟩²/σ²``, and — after
removing the detector's own noise floor — the *true* molecular brightness ε and
molecule number n.

Everything a stack needs on the way there lives here too:

- :func:`dead_time_correct` — the per-pixel dead-time correction applied to the
  counts before the moments are taken;
- :func:`correct_stack` — the stack corrections of the image-correlation tools
  (subtract a frame / pixel mean or a sliding box average, add a mean back,
  subtract a constant background);
- :func:`detrend_segmented` — segmented per-pixel linear detrending with mean
  restoration (bleaching removal that leaves ``⟨k⟩`` intact, which ``B = σ²/⟨k⟩``
  requires);
- :func:`nb_maps` / :func:`ccnb_maps` — auto and cross N&B, photon-counting and
  analog detectors, with the optional moment smoothing and median filter;
- :func:`gaussian_filter_nan` — map smoothing that does not leak across a NaN
  mask;
- :func:`nb_threshold_mask`, :func:`nb_gate_mask`, :func:`nb_histogram_2d` and
  :func:`nb_default_ranges` — gating a population on the parameter plane
  (e.g. B versus intensity) and back-mapping it onto pixels;
- :func:`photon_counting_histogram` — the counts-per-pixel histogram (PCH) of
  the corrected stack.

Stacks are ``(n_frames, n_lines, n_pixels)`` throughout; maps are
``(n_lines, n_pixels)``.

The estimators, filter kernels and boundary handling reproduce the N&B of the
PAM package (Schrimpf et al. 2018) where its behaviour is well defined; the
deliberate differences are documented per function and recorded in the
imaging-correlation theory concept of the knowledge base.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

#: γ shape factor of a 3-D Gaussian observation volume, ``2^(-3/2) = 1/√8``.
GAMMA_3D_GAUSSIAN = 2.0**-1.5

#: Spatial smoothing kinds accepted by :func:`nb_maps` / :func:`smoothing_kernel`.
SMOOTHING_KINDS = ("none", "average", "disk", "gaussian")


# --------------------------------------------------------------------------- stacks
def as_stack(intensity: Any) -> np.ndarray:
    """Return an image or image stack as a float ``(n_frames, ny, nx)`` array.

    Parameters
    ----------
    intensity : array_like
        A 2-D image (one frame) or a 3-D ``(n_frames, ny, nx)`` stack.

    Returns
    -------
    numpy.ndarray
        Float64 stack; a 2-D input gains a leading frame axis of length 1.
    """
    arr = np.asarray(intensity, dtype=float)
    if arr.ndim == 2:
        return arr[None, ...]
    if arr.ndim == 3:
        return arr
    raise ValueError(f"Unsupported intensity shape {arr.shape!r}; expected 2D or 3D")


def dead_time_correct(stack: Any, dead_time: float, pixel_dwell: float) -> np.ndarray:
    """Correct per-pixel counts for detector dead time.

    A pixel that recorded ``k`` counts in a dwell ``T`` saw an observed rate
    ``k/T``; a non-paralysable detector with dead time ``τ`` then had a true rate
    ``(k/T)/(1 − kτ/T)``, so::

        k_corr = k / (1 − k·τ/T)

    Parameters
    ----------
    stack : array_like
        Counts per pixel per frame.
    dead_time, pixel_dwell : float
        Dead time ``τ`` and pixel dwell time ``T`` in the **same** unit. A
        non-positive ``dead_time`` or ``pixel_dwell`` returns the counts unchanged.

    Returns
    -------
    numpy.ndarray
        The corrected counts (float).
    """
    counts = np.asarray(stack, dtype=float)
    if dead_time is None or pixel_dwell is None or dead_time <= 0.0 or pixel_dwell <= 0.0:
        return counts.copy()
    return counts / (1.0 - counts * (float(dead_time) / float(pixel_dwell)))


def _matlab_origin(size: int) -> int:
    """Origin shift that centres an even-sized window like MATLAB/Octave filters do.

    MATLAB-style filters put the kernel centre at ``floor((n + 1) / 2)`` (1-based),
    i.e. one sample *before* the middle for an even ``n``; scipy.ndimage puts it
    at ``n // 2`` (0-based). The difference is ``-1`` for even sizes, ``0`` for odd.
    """
    return (size - 1) // 2 - size // 2


def moving_average(stack: Any, box_pixels: int, box_frames: int) -> np.ndarray:
    """Sliding box average over ``(frames, lines, pixels)`` with edge replication.

    The box is ``box_frames × box_pixels × box_pixels``; sizes are clipped into
    ``[1, axis length]``. Edges replicate the border sample and an even box is
    centred one sample early, as the reference image-correlation corrections do.

    Parameters
    ----------
    stack : array_like
        ``(n_frames, ny, nx)`` stack.
    box_pixels, box_frames : int
        Spatial (both lateral axes) and temporal box lengths.

    Returns
    -------
    numpy.ndarray
        The box-averaged stack, same shape.
    """
    from scipy.ndimage import uniform_filter

    data = as_stack(stack)
    size = [
        int(min(max(1, round(box_frames)), data.shape[0])),
        int(min(max(1, round(box_pixels)), data.shape[1])),
        int(min(max(1, round(box_pixels)), data.shape[2])),
    ]
    return uniform_filter(data, size=size, mode="nearest", origin=[_matlab_origin(s) for s in size])


def correct_stack(
    stack: Any,
    *,
    subtract: str = "none",
    add: str = "none",
    subtract_box: tuple[int, int] = (3, 3),
    add_box: tuple[int, int] = (3, 3),
    background: float = 0.0,
) -> np.ndarray:
    """Apply the image-correlation stack corrections: add, subtract, background.

    The order is that of the reference implementation: the **add** term is
    computed from the stack and added first, the **subtract** term is computed
    from the *uncorrected* stack and subtracted, NaNs are zeroed and a constant
    ``background`` is removed. The common N&B / RICS use is
    ``subtract="moving_average"`` with ``add="total_mean"`` or
    ``add="pixel_mean"``: slow drifts and immobile structure go, the mean
    intensity (which ``B = σ²/⟨k⟩`` divides by) stays.

    Parameters
    ----------
    stack : array_like
        ``(n_frames, ny, nx)`` stack.
    subtract : {"none", "frame_mean", "pixel_mean", "moving_average"}
        Frame mean (one value per frame), pixel mean (one value per pixel, over
        frames) or a sliding box average (``subtract_box``).
    add : {"none", "total_mean", "frame_mean", "pixel_mean", "moving_average"}
        What is added back (``add_box`` for the moving average).
    subtract_box, add_box : (int, int)
        ``(box_pixels, box_frames)`` of the respective moving average.
    background : float
        Constant subtracted from every sample at the end.

    Returns
    -------
    numpy.ndarray
        The corrected stack (float).
    """
    raw = as_stack(stack)
    out = raw.copy()
    if add == "total_mean":
        out = out + np.nanmean(raw)
    elif add == "frame_mean":
        out = out + np.nanmean(raw, axis=(1, 2), keepdims=True)
    elif add == "pixel_mean":
        out = out + np.nanmean(raw, axis=0, keepdims=True)
    elif add == "moving_average":
        out = out + moving_average(raw, add_box[0], add_box[1])
    elif add != "none":
        raise ValueError(f"unknown add correction {add!r}")

    if subtract == "frame_mean":
        out = out - np.nanmean(raw, axis=(1, 2), keepdims=True)
    elif subtract == "pixel_mean":
        out = out - np.nanmean(raw, axis=0, keepdims=True)
    elif subtract == "moving_average":
        out = out - moving_average(raw, subtract_box[0], subtract_box[1])
    elif subtract != "none":
        raise ValueError(f"unknown subtract correction {subtract!r}")

    out[np.isnan(out)] = 0.0
    return out - float(background)


def stack_trends(stack: Any) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel least-squares line through a stack, in closed form.

    Fits ``k(t) = slope·t + intercept`` with ``t = 0 … n−1`` for every pixel at
    once — the normal equations over the whole stack, no per-pixel loop.

    Parameters
    ----------
    stack : array_like
        ``(n_frames, ny, nx)`` stack with ``n_frames ≥ 2``.

    Returns
    -------
    slopes, intercepts : numpy.ndarray
        ``(ny, nx)`` maps.
    """
    data = as_stack(stack)
    n = data.shape[0]
    t = np.arange(n, dtype=float)
    t_sum = t.sum()
    t_sq_sum = (t * t).sum()
    y_sum = data.sum(axis=0)
    ty_sum = np.tensordot(t, data, axes=(0, 0))
    divisor = t_sq_sum * n - t_sum * t_sum
    slopes = (ty_sum * n - y_sum * t_sum) / divisor
    intercepts = (y_sum * t_sq_sum - ty_sum * t_sum) / divisor
    return slopes, intercepts


def detrend_segment_count(n_frames: int, segments: int) -> int:
    """Number of segments :func:`detrend_segmented` actually uses for ``n_frames``.

    Clipped to ``[1, n_frames // 2]`` so every segment keeps at least two frames.
    """
    return int(max(1, min(int(segments), n_frames // 2 if n_frames >= 2 else 1)))


def detrend_segmented(stack: Any, segments: int = 1, maintain_intensity: bool = True) -> np.ndarray:
    """Remove a per-pixel linear trend within each of ``segments`` time chunks.

    The stack is cut into ``segments`` consecutive chunks of ``n_frames //
    segments`` frames (the last chunk takes the remainder); within each chunk a
    line is fitted to every pixel (:func:`stack_trends`) and subtracted. Several
    short lines follow a bleaching curve that one line cannot.

    ``maintain_intensity`` adds the per-pixel mean of the *original* stack back.
    It is not cosmetic: the fit residuals have zero mean, and ``B = σ²/⟨k⟩``
    divides by the mean — detrending without restoring it destroys ``B``. Nor is
    this interchangeable with an immobile-structure filter: it removes a slow
    trend per pixel and keeps each pixel's own mean.

    Parameters
    ----------
    stack : array_like
        ``(n_frames, ny, nx)`` stack.
    segments : int
        Number of time chunks (``1`` = one line per pixel). Clipped so every
        chunk has at least two frames.
    maintain_intensity : bool
        Add the per-pixel mean back (default ``True``).

    Returns
    -------
    numpy.ndarray
        The detrended stack.
    """
    data = as_stack(stack)
    n = data.shape[0]
    segments = detrend_segment_count(n, segments)
    if n < 2:
        return data.copy()
    seg_len = n // segments
    out = np.empty_like(data)
    for i in range(segments):
        start = i * seg_len
        end = n if i == segments - 1 else start + seg_len
        chunk = data[start:end]
        slopes, intercepts = stack_trends(chunk)
        t = np.arange(end - start, dtype=float)[:, None, None]
        out[start:end] = chunk - (slopes[None] * t + intercepts[None])
    if maintain_intensity:
        out += data.mean(axis=0)
    return out


# --------------------------------------------------------------------------- smoothing
def _disk_overlap_1q(a: float, b: float, c: float, d: float, r: float) -> float:
    """Area of ``[a,b]×[c,d]`` (first quadrant, ``0 ≤ a ≤ b``, ``0 ≤ c ≤ d``) inside a disk of radius ``r``."""

    def antiderivative(t: float) -> float:
        # ∫ sqrt(r² − t²) dt
        t = min(max(t, 0.0), r)
        return 0.5 * (t * np.sqrt(max(r * r - t * t, 0.0)) + r * r * np.arcsin(t / r))

    if c >= r or a >= r or b <= a or d <= c:
        return 0.0
    t_c = np.sqrt(r * r - c * c)  # circle meets the bottom edge
    t_d = np.sqrt(r * r - d * d) if d < r else 0.0  # circle leaves the top edge
    full = (d - c) * max(min(b, t_d) - a, 0.0)  # columns entirely under the arc
    lo, hi = max(a, t_d), min(b, t_c)
    arc = antiderivative(hi) - antiderivative(lo) - c * (hi - lo) if hi > lo else 0.0
    return full + arc


def _abs_pieces(lo: float, hi: float) -> list[tuple[float, float]]:
    """Split ``[lo, hi]`` into non-negative intervals of ``|t|``."""
    if lo >= 0.0:
        return [(lo, hi)]
    if hi <= 0.0:
        return [(-hi, -lo)]
    return [(0.0, -lo), (0.0, hi)]


def _disk_kernel(r: float) -> np.ndarray:
    """Pillbox kernel: exact area of each pixel inside a centred disk of radius ``r``."""
    crad = int(np.ceil(r - 0.5))
    size = 2 * crad + 1
    kernel = np.zeros((size, size))
    for i in range(size):
        for j in range(size):
            y, x = i - crad, j - crad
            kernel[i, j] = sum(
                _disk_overlap_1q(xa, xb, ya, yb, r)
                for xa, xb in _abs_pieces(x - 0.5, x + 0.5)
                for ya, yb in _abs_pieces(y - 0.5, y + 0.5)
            )
    return kernel / kernel.sum()


def smoothing_kernel(kind: str, radius: float) -> np.ndarray:
    """Return the 2-D smoothing kernel for the N&B moment filter.

    The kinds and their sizes follow the reference N&B:

    ``"none"``
        ``[[1]]``.
    ``"average"``
        ``round(radius) × round(radius)`` box of equal weights.
    ``"disk"``
        Pillbox of radius ``radius − 1``: each weight is the exact area of the
        pixel inside the disk, normalised to sum 1.
    ``"gaussian"``
        ``2·radius × 2·radius`` Gaussian with ``σ = radius/2`` sampled at the
        pixel centres (half-integer offsets for an even size), normalised.

    A ``radius ≤ 1`` selects ``"none"`` whatever ``kind`` says.

    Parameters
    ----------
    kind : {"none", "average", "disk", "gaussian"}
    radius : float

    Returns
    -------
    numpy.ndarray
        The normalised kernel.
    """
    if kind not in SMOOTHING_KINDS:
        raise ValueError(f"unknown smoothing kind {kind!r}; expected one of {SMOOTHING_KINDS}")
    radius = float(radius)
    if kind == "none" or radius <= 1.0:
        return np.ones((1, 1))
    if kind == "average":
        n = int(round(radius))
        return np.full((n, n), 1.0 / (n * n))
    if kind == "gaussian":
        n = int(round(2 * radius))
        sigma = radius / 2.0
        pos = np.arange(n, dtype=float) - (n - 1) / 2.0
        kernel = np.exp(-(pos[:, None] ** 2 + pos[None, :] ** 2) / (2.0 * sigma * sigma))
        return kernel / kernel.sum()
    r = radius - 1.0
    if r <= 0.0:
        return np.ones((1, 1))
    return _disk_kernel(r)


def smooth_map(image: Any, kind: str = "none", radius: float = 3.0) -> np.ndarray:
    """Correlate a map with :func:`smoothing_kernel` under mirrored boundaries.

    Mirrors the border sample (``d c b a | a b c d | d c b a``) and centres an
    even kernel one sample early, as MATLAB-style image filters do.

    Parameters
    ----------
    image : array_like
        2-D map.
    kind, radius
        See :func:`smoothing_kernel`.

    Returns
    -------
    numpy.ndarray
        Smoothed map (same shape; complex input stays complex).
    """
    from scipy.ndimage import correlate

    kernel = smoothing_kernel(kind, radius)
    arr = np.asarray(image)
    if kernel.size == 1:
        return arr.astype(np.result_type(arr, float), copy=True)
    origin = [_matlab_origin(s) for s in kernel.shape]
    if np.iscomplexobj(arr):
        return correlate(arr.real, kernel, mode="reflect", origin=origin) + 1j * correlate(
            arr.imag, kernel, mode="reflect", origin=origin
        )
    return correlate(arr.astype(float), kernel, mode="reflect", origin=origin)


def median_filter_3x3(image: Any) -> np.ndarray:
    """3×3 median filter with zero padding (the edge pixels see zeros)."""
    from scipy.ndimage import median_filter

    return median_filter(np.asarray(image, dtype=float), size=3, mode="constant", cval=0.0)


def gaussian_filter_nan(image: Any, sigma: float) -> np.ndarray:
    """Gaussian-smooth a map that carries NaN (masked) pixels, keeping them NaN.

    A plain Gaussian filter spreads one NaN over its whole footprint, and
    zero-filling first darkens every pixel near the mask edge. This weights by
    the valid fraction instead — ``G*(x·valid) / G*valid`` — so background
    outside a threshold mask does not leak into the map, and restores NaN where
    the input was NaN.

    Parameters
    ----------
    image : array_like
        2-D map with NaN for masked pixels.
    sigma : float
        Gaussian standard deviation in pixels; ``≤ 0`` returns a copy.

    Returns
    -------
    numpy.ndarray
        Smoothed map with the input's NaN pattern.
    """
    from scipy.ndimage import gaussian_filter

    arr = np.asarray(image, dtype=float)
    if sigma is None or sigma <= 0.0:
        return arr.copy()
    valid = np.isfinite(arr)
    num = gaussian_filter(np.where(valid, arr, 0.0), sigma)
    den = gaussian_filter(valid.astype(float), sigma)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = num / den
    out[~valid] = np.nan
    return out


# --------------------------------------------------------------------------- estimators
def _moments(data: np.ndarray, ddof: int) -> tuple[np.ndarray, np.ndarray]:
    """NaN-aware per-pixel mean and variance over the frame axis."""
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.nanmean(data, axis=0) if np.isnan(data).any() else data.mean(axis=0)
        if data.shape[0] <= ddof:
            return mean, np.zeros_like(mean)
        if np.isnan(data).any():
            var = np.nanvar(data, axis=0, ddof=ddof)
        else:
            var = data.var(axis=0, ddof=ddof)
    return mean, var


def nb_maps(
    intensity_stack: Any,
    *,
    ddof: int = 1,
    gamma: float = 1.0,
    dead_time: float = 0.0,
    pixel_dwell: float = 0.0,
    smoothing: str = "none",
    radius: float = 3.0,
    median: bool = False,
    gain: float = 1.0,
    offset: float = 0.0,
    read_variance: float = 0.0,
) -> dict[str, np.ndarray]:
    """Per-pixel Number & Brightness maps of an image stack.

    Over the frame axis each pixel gives ``⟨k⟩`` and ``σ²``. With a detector of
    gain ``S``, offset ``k₀`` and read-noise variance ``σ₀²`` (photon counting:
    ``S = 1``, ``k₀ = 0``, ``σ₀² = 0``) write ``I = ⟨k⟩ − k₀`` and
    ``V = σ² − σ₀²``; then

    ============  ===============================  ==================================
    key           formula                          meaning
    ============  ===============================  ==================================
    ``mean``      ``⟨k⟩``                          mean counts per pixel dwell
    ``variance``  ``σ²``                           variance over frames
    ``B``         ``V / I``                        apparent brightness
    ``N``         ``I² / V``                       apparent number
    ``epsilon``   ``(V − S·I) / (S·I) / γ``        molecular brightness (per dwell)
    ``n``         ``γ · I² / (V − S·I)``           molecule number
    ============  ===============================  ==================================

    Photon counting reduces ε to ``(B − 1)/γ`` and n to ``γ⟨k⟩/(B − 1)``: the
    ``−1`` removes the shot-noise floor, so an immobile or Poisson-only pixel has
    ``B = 1`` and ``ε = 0``. For an analog detector ``S`` and ``k₀`` come from a
    calibration (:func:`analog_calibration`), not from a guess.

    ``gamma`` is the shape factor of the observation volume: ``1`` (the default)
    reports ε and n as Digman et al. define them; :data:`GAMMA_3D_GAUSSIAN`
    (``1/√8``) gives the γ-corrected values the reference N&B reports.

    Before the ratios are formed the counts can be dead-time corrected and the
    **mean and standard-deviation** maps smoothed (``smoothing``/``radius``,
    :func:`smooth_map`) — the reference smooths σ, not σ², and so does this.
    ``median`` finally passes ε and n through a 3×3 median filter.

    Parameters
    ----------
    intensity_stack : array_like
        ``(n_frames, ny, nx)`` counts (or a single frame, which gives zero
        variance).
    ddof : int
        Delta degrees of freedom of the variance. ``1`` (default) is the
        unbiased sample variance; ``0`` the population variance, which
        underestimates B by a factor ``(K−1)/K`` for ``K`` frames.
    gamma : float
        Observation-volume shape factor.
    dead_time, pixel_dwell : float
        Dead-time correction (:func:`dead_time_correct`), same time unit.
    smoothing, radius
        Moment smoothing (:func:`smoothing_kernel`).
    median : bool
        3×3 median filter on ε and n.
    gain, offset, read_variance : float
        Analog detector calibration ``S``, ``k₀``, ``σ₀²``.

    Returns
    -------
    dict of numpy.ndarray
        ``mean``, ``variance``, ``B``, ``N``, ``epsilon``, ``n``. Pixels where a
        ratio is undefined (zero intensity or variance) carry ``0`` in ``B``,
        ``N``, ``epsilon`` and ``n`` so the maps stay finite for display and
        storage; use ``mean > 0`` to mask them.
    """
    data = dead_time_correct(as_stack(intensity_stack), dead_time, pixel_dwell)
    mean, variance = _moments(data, ddof)
    if smoothing != "none":
        mean = smooth_map(mean, smoothing, radius)
        variance = smooth_map(np.sqrt(np.maximum(variance, 0.0)), smoothing, radius) ** 2
    S = float(gain) if gain else 1.0
    intensity = mean - float(offset)
    excess_variance = variance - float(read_variance)
    with np.errstate(divide="ignore", invalid="ignore"):
        B = np.where(intensity != 0.0, excess_variance / intensity, 0.0)
        N = np.where(excess_variance != 0.0, intensity * intensity / excess_variance, 0.0)
        excess = excess_variance - S * intensity
        epsilon = np.where(intensity != 0.0, excess / (S * intensity) / gamma, 0.0)
        n = np.where(excess != 0.0, gamma * intensity * intensity / excess, 0.0)
    if median:
        epsilon = median_filter_3x3(epsilon)
        n = median_filter_3x3(n)
    return {
        "mean": np.nan_to_num(mean),
        "variance": np.nan_to_num(variance),
        "B": np.nan_to_num(B),
        "N": np.nan_to_num(N),
        "epsilon": np.nan_to_num(epsilon),
        "n": np.nan_to_num(n),
    }


def ccnb_maps(
    stack_a: Any,
    stack_b: Any,
    *,
    ddof: int = 1,
    dead_time: float = 0.0,
    pixel_dwell: float = 0.0,
    smoothing: str = "none",
    radius: float = 3.0,
) -> dict[str, np.ndarray]:
    """Cross Number & Brightness (ccN&B) of two channels of the same stack.

    With the per-pixel covariance ``C = ⟨k_a k_b⟩ − ⟨k_a⟩⟨k_b⟩`` and the
    geometric mean ``M = √(⟨k_a⟩⟨k_b⟩)``::

        B_cross = C / M          (no −1)
        N_cross = M² / C

    There is **no** ``−1``: shot noise is uncorrelated between two detectors, so
    unlike the auto brightness the cross term has no noise floor to remove.
    Copying the auto formula here biases every value by −1. ``B_cross > 0``
    means species carrying both labels move together.

    Parameters
    ----------
    stack_a, stack_b : array_like
        Two ``(n_frames, ny, nx)`` stacks of identical shape.
    ddof : int
        Delta degrees of freedom of the covariance (``1`` unbiased).
    dead_time, pixel_dwell : float
        Dead-time correction applied to both channels.
    smoothing, radius
        Smoothing of ``M`` and ``C`` (:func:`smooth_map`).

    Returns
    -------
    dict of numpy.ndarray
        ``mean`` (= M), ``mean_a``, ``mean_b``, ``covariance``, ``B_cross``,
        ``N_cross``; undefined ratios carry ``0``.
    """
    a = dead_time_correct(as_stack(stack_a), dead_time, pixel_dwell)
    b = dead_time_correct(as_stack(stack_b), dead_time, pixel_dwell)
    if a.shape != b.shape:
        raise ValueError(f"channel stacks differ in shape: {a.shape} vs {b.shape}")
    k = a.shape[0]
    mean_a = a.mean(axis=0)
    mean_b = b.mean(axis=0)
    if k <= ddof:
        cov = np.zeros_like(mean_a)
    else:
        cov = ((a - mean_a) * (b - mean_b)).sum(axis=0) / (k - ddof)
    geo = np.sqrt(np.maximum(mean_a * mean_b, 0.0))
    if smoothing != "none":
        geo = smooth_map(geo, smoothing, radius)
        cov = smooth_map(cov, smoothing, radius)
    with np.errstate(divide="ignore", invalid="ignore"):
        b_cross = np.where(geo > 0.0, cov / geo, 0.0)
        n_cross = np.where(cov != 0.0, geo * geo / cov, 0.0)
    return {
        "mean": geo,
        "mean_a": mean_a,
        "mean_b": mean_b,
        "covariance": cov,
        "B_cross": np.nan_to_num(b_cross),
        "N_cross": np.nan_to_num(n_cross),
    }


def analog_calibration(mean: Any, variance: Any, read_variance: float = 0.0) -> dict[str, float]:
    """Gain ``S`` and offset ``k₀`` of an analog detector from a static gradient.

    Image something that does **not** fluctuate but spans a range of
    intensities (a fluorescent slide with an illumination gradient, a dried
    dye film). Every pixel then carries only detector noise, which for an analog
    detector is ``σ² = S·(⟨k⟩ − k₀) + σ₀²``. A straight line through the
    per-pixel ``(⟨k⟩, σ²)`` cloud gives the slope ``S`` and, with the read-noise
    variance ``σ₀²`` measured in the dark, the offset ``k₀``.

    Parameters
    ----------
    mean, variance : array_like
        Per-pixel mean and variance of the calibration stack (e.g. from
        :func:`nb_maps`); non-finite pixels are ignored.
    read_variance : float
        Dark read-noise variance ``σ₀²``.

    Returns
    -------
    dict
        ``gain`` (S), ``offset`` (k₀), ``intercept`` (of the fitted line) and
        ``r2`` (coefficient of determination).
    """
    x = np.asarray(mean, dtype=float).ravel()
    y = np.asarray(variance, dtype=float).ravel()
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if x.size < 2 or np.ptp(x) == 0.0:
        raise ValueError("the calibration needs pixels spanning a range of intensities")
    slope, intercept = np.polyfit(x, y, 1)
    fit = slope * x + intercept
    ss_res = float(((y - fit) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    offset = (float(read_variance) - intercept) / slope
    return {
        "gain": float(slope),
        "offset": float(offset),
        "intercept": float(intercept),
        "r2": 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0,
    }


# --------------------------------------------------------------------------- histograms and gating
def photon_counting_histogram(stack: Any) -> np.ndarray:
    """Counts-per-pixel histogram of every sample of a (corrected) stack.

    Bin ``i`` counts samples with ``i ≤ k < i+1``; the last bin holds the
    samples equal to ``ceil(max)``. Dead-time corrected (non-integer) counts
    therefore fall into the bin of their integer part.

    Returns
    -------
    numpy.ndarray
        Integer histogram of length ``ceil(max(k)) + 1``.
    """
    values = np.asarray(stack, dtype=float).ravel()
    values = values[np.isfinite(values)]
    if values.size == 0:
        return np.zeros(1, dtype=np.int64)
    top = int(np.ceil(values.max()))
    edges = np.arange(0, top + 1, dtype=float)
    idx = np.floor(values).astype(np.int64)
    idx = idx[(values >= 0.0) & (idx <= top)]
    hist = np.bincount(idx, minlength=edges.size)
    return hist[: edges.size]


def nb_threshold_mask(
    maps: Mapping[str, np.ndarray], ranges: Mapping[str, tuple[float, float]]
) -> np.ndarray:
    """Pixels whose every listed map lies inside its ``[lo, hi]`` range.

    The rectangular gate of the reference N&B: one closed interval per quantity
    (intensity, number, brightness), each switched on by being listed.

    Parameters
    ----------
    maps : mapping of str to numpy.ndarray
        Maps of identical shape, e.g. the output of :func:`nb_maps`.
    ranges : mapping of str to (float, float)
        Closed interval per map key; keys not present in ``ranges`` do not gate.

    Returns
    -------
    numpy.ndarray
        Boolean mask; all ``True`` when ``ranges`` is empty.
    """
    shape = np.asarray(next(iter(maps.values()))).shape
    mask = np.ones(shape, dtype=bool)
    for key, (lo, hi) in ranges.items():
        values = np.asarray(maps[key], dtype=float)
        mask &= (values >= lo) & (values <= hi)
    return mask


def nb_gate_mask(x_map: Any, y_map: Any, roi: Any, base_mask: Any = None) -> np.ndarray:
    """Back-map a region drawn on a parameter plane onto the image pixels.

    A population picked out on, say, the brightness-versus-intensity histogram
    answers *which pixels* carry that oligomeric state: every pixel whose
    ``(x, y)`` pair lies inside ``roi`` is selected.

    Parameters
    ----------
    x_map, y_map : array_like
        The two maps spanning the plane (identical shapes).
    roi : object with ``contains(points)``
        A :class:`chisurf.core.roi.ROI` in ``(x, y)`` plane coordinates, or
        ``None`` to select every pixel.
    base_mask : array_like of bool, optional
        Pixels eligible at all (e.g. :func:`nb_threshold_mask`).

    Returns
    -------
    numpy.ndarray
        Boolean mask shaped like ``x_map``.
    """
    x = np.asarray(x_map, dtype=float)
    y = np.asarray(y_map, dtype=float)
    if roi is None:
        mask = np.ones(x.shape, dtype=bool)
    else:
        points = np.column_stack([x.ravel(), y.ravel()])
        mask = np.asarray(roi.contains(points), dtype=bool).reshape(x.shape)
    mask &= np.isfinite(x) & np.isfinite(y)
    if base_mask is not None:
        mask &= np.asarray(base_mask, dtype=bool)
    return mask


def nb_histogram_2d(
    x_map: Any,
    y_map: Any,
    x_range: Sequence[float],
    y_range: Sequence[float],
    bins: int | Sequence[int] = 64,
    mask: Any = None,
) -> np.ndarray:
    """2-D histogram of two maps over the selected pixels.

    Returned row-major — axis 0 is ``y``, axis 1 is ``x`` — which is how images
    are drawn, so ``x`` runs horizontally.

    Returns
    -------
    numpy.ndarray
        ``(y_bins, x_bins)`` counts.
    """
    x = np.asarray(x_map, dtype=float).ravel()
    y = np.asarray(y_map, dtype=float).ravel()
    ok = np.isfinite(x) & np.isfinite(y)
    if mask is not None:
        ok &= np.asarray(mask, dtype=bool).ravel()
    bx, by = (bins, bins) if np.isscalar(bins) else tuple(bins)
    hist, _, _ = np.histogram2d(
        x[ok],
        y[ok],
        bins=[int(bx), int(by)],
        range=[[float(x_range[0]), float(x_range[1])], [float(y_range[0]), float(y_range[1])]],
    )
    return hist.T


def nb_default_ranges(
    maps: Mapping[str, np.ndarray], keys: Sequence[str] = ("mean", "N", "B", "epsilon", "n")
) -> dict[str, tuple[float, float]]:
    """Display/gating ranges that exclude outliers, one per map.

    The reference N&B's starting thresholds: for the intensity,
    ``[max(min, ⟨mean⟩ − 3⟨σ⟩), min(max, ⟨mean⟩ + 3⟨σ⟩)]``; for every other map,
    mean ± 3 standard deviations of the values between the 5th and 95th
    percentile. Only pixels with a positive mean contribute.

    Returns
    -------
    dict
        ``key -> (lo, hi)`` for the keys present in ``maps``.
    """
    out: dict[str, tuple[float, float]] = {}
    mean = np.asarray(maps.get("mean"), dtype=float) if "mean" in maps else None
    valid = (mean > 0.0) if mean is not None else None
    for key in keys:
        if key not in maps:
            continue
        values = np.asarray(maps[key], dtype=float)
        sel = values[valid] if valid is not None and valid.any() else values.ravel()
        sel = sel[np.isfinite(sel)]
        if sel.size == 0:
            out[key] = (0.0, 1.0)
            continue
        if key == "mean" and "variance" in maps:
            std = np.sqrt(np.maximum(np.asarray(maps["variance"], dtype=float), 0.0))
            s = std[valid].mean() if valid is not None and valid.any() else std.mean()
            lo = max(sel.min(), sel.mean() - 3.0 * s)
            hi = min(sel.max(), sel.mean() + 3.0 * s)
        else:
            ordered = np.sort(sel)
            # 1-based [round(0.05·n), round(0.95·n)], rounding half away from zero
            first = max(int(np.floor(0.05 * ordered.size + 0.5)), 1) - 1
            last = int(np.floor(0.95 * ordered.size + 0.5))
            trimmed = ordered[first:last]
            m, s = trimmed.mean(), trimmed.std(ddof=1) if trimmed.size > 1 else 0.0
            lo, hi = m - 3.0 * s, m + 3.0 * s
        if not hi > lo:
            lo, hi = lo - 0.5, hi + 0.5
        out[key] = (float(lo), float(hi))
    return out


#: Default settings of :func:`nb_pipeline` (the GUI/CLI parameter vocabulary).
NB_PIPELINE_DEFAULTS: dict[str, Any] = {
    "subtract": "none",
    "add": "none",
    "box_pixels": 3,
    "box_frames": 3,
    "background": 0.0,
    "detrend_segments": 0,
    "dead_time": 0.0,
    "pixel_dwell": 0.0,
    "smoothing": "none",
    "radius": 3.0,
    "median": False,
    "gamma": 1.0,
    "gain": 1.0,
    "offset": 0.0,
    "read_variance": 0.0,
    "ddof": 1,
}


def prepare_stack(stack: Any, params: Mapping[str, Any] | None = None) -> np.ndarray:
    """Apply the stack corrections and detrending an N&B run is configured with.

    ``params`` uses the :data:`NB_PIPELINE_DEFAULTS` keys: ``subtract`` / ``add``
    with one ``(box_pixels, box_frames)`` box for both moving averages,
    ``background``, then ``detrend_segments`` (``0`` = off) with mean
    restoration. Unknown keys are ignored.

    Returns
    -------
    numpy.ndarray
        The prepared ``(n_frames, ny, nx)`` stack.
    """
    p = {**NB_PIPELINE_DEFAULTS, **dict(params or {})}
    data = as_stack(stack)
    box = (int(p["box_pixels"]), int(p["box_frames"]))
    if p["subtract"] != "none" or p["add"] != "none" or float(p["background"]) != 0.0:
        data = correct_stack(
            data,
            subtract=p["subtract"],
            add=p["add"],
            subtract_box=box,
            add_box=box,
            background=float(p["background"]),
        )
    if int(p["detrend_segments"]) > 0:
        data = detrend_segmented(data, int(p["detrend_segments"]), maintain_intensity=True)
    return data


def nb_pipeline(stack: Any, params: Mapping[str, Any] | None = None) -> dict[str, np.ndarray]:
    """Prepare a stack (:func:`prepare_stack`) and compute :func:`nb_maps` on it.

    With detrending on, the variance divides by ``K − 2·segments`` instead of
    ``K − 1``: each segment's fitted line removes two degrees of freedom from the
    residuals, and ignoring that biases B low by ``(K − 2·segments)/(K − 1)`` —
    about 20 % for ten-frame segments.

    Returns
    -------
    dict of numpy.ndarray
        The :func:`nb_maps` result.
    """
    p = {**NB_PIPELINE_DEFAULTS, **dict(params or {})}
    data = prepare_stack(stack, p)
    ddof = int(p["ddof"])
    if int(p["detrend_segments"]) > 0:
        # every segment's line takes two degrees of freedom out of the residuals;
        # dividing by K − 1 would bias σ² (and B) low by (K − 2·segments)/(K − 1)
        ddof = max(ddof, 2 * detrend_segment_count(data.shape[0], int(p["detrend_segments"])))
    return nb_maps(
        data,
        ddof=ddof,
        gamma=float(p["gamma"]),
        dead_time=float(p["dead_time"]),
        pixel_dwell=float(p["pixel_dwell"]),
        smoothing=str(p["smoothing"]),
        radius=float(p["radius"]),
        median=bool(p["median"]),
        gain=float(p["gain"]),
        offset=float(p["offset"]),
        read_variance=float(p["read_variance"]),
    )


__all__ = [
    "NB_PIPELINE_DEFAULTS",
    "GAMMA_3D_GAUSSIAN",
    "SMOOTHING_KINDS",
    "analog_calibration",
    "as_stack",
    "ccnb_maps",
    "correct_stack",
    "dead_time_correct",
    "detrend_segment_count",
    "detrend_segmented",
    "gaussian_filter_nan",
    "median_filter_3x3",
    "moving_average",
    "nb_default_ranges",
    "nb_gate_mask",
    "nb_histogram_2d",
    "nb_maps",
    "nb_pipeline",
    "nb_threshold_mask",
    "photon_counting_histogram",
    "prepare_stack",
    "smooth_map",
    "smoothing_kernel",
    "stack_trends",
]
