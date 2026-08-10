r"""Fourier Ring Correlation: how fine a detail an image actually resolves.

The resolution of a real image is not the pixel size and not the diffraction
limit — it is where the *signal* stops rising above the *noise*. The FRC
measures that directly, from the data alone: split one acquisition into two
statistically independent halves, correlate them ring by ring in Fourier space,

.. math::

   \mathrm{FRC}(q) = \frac{\sum_{|\mathbf{q}| \in q}
   F_1(\mathbf{q}) \, F_2^{*}(\mathbf{q})}
   {\sqrt{\sum |F_1(\mathbf{q})|^2 \sum |F_2(\mathbf{q})|^2}}

and read the frequency at which the correlation falls through a threshold. Below
that frequency the two halves agree — the structure is reproducible; above it
they do not — what is there is noise. The resolution is the inverse of the
crossing frequency.

Which threshold is a matter of convention and the three in use here disagree by
a few tens of per cent, so a quoted number is meaningless without the criterion
beside it (see :func:`threshold_curve`).

References
----------
* M. van Heel, M. Schatz, *Fourier shell correlation threshold criteria*,
  J. Struct. Biol. 151 (2005) 250-262 — the ½-bit and σ criteria.
* R. P. J. Nieuwenhuizen et al., *Measuring image resolution in optical
  nanoscopy*, Nat. Methods 10 (2013) 557-562 — the fixed 1/7 criterion for
  fluorescence images.
"""

from __future__ import annotations

import dataclasses

import numpy as np

#: Threshold criteria understood by :func:`threshold_curve` and :func:`resolve`.
CRITERIA = ("fixed_1/7", "half_bit", "two_sigma")


@dataclasses.dataclass
class FrcCurve:
    """One Fourier-ring-correlation curve.

    Parameters
    ----------
    frequency : numpy.ndarray
        Spatial frequency of each ring, in cycles per pixel when *pixel_size* is
        ``None`` and in cycles per unit length (1/nm for a pixel size in nm)
        otherwise.
    correlation : numpy.ndarray
        FRC value of each ring: 1 where the two halves agree perfectly, 0 where
        they are uncorrelated.
    counts : numpy.ndarray
        Number of Fourier pixels contributing to each ring. The ½-bit and σ
        thresholds are functions of this — a ring holding few pixels is a noisy
        estimate and its threshold has to be higher.
    pixel_size : float or None
        Pixel size the frequency axis was scaled with, if any.
    """

    frequency: np.ndarray
    correlation: np.ndarray
    counts: np.ndarray
    pixel_size: float | None = None


@dataclasses.dataclass
class FrcResolution:
    """Where a curve crosses its threshold, and what that means in length units.

    Parameters
    ----------
    criterion : str
        Threshold used, one of :data:`CRITERIA`.
    frequency : float
        Crossing frequency, ``nan`` when the curve never crosses.
    resolution : float
        ``1 / frequency`` — in pixels when the curve carried no pixel size, in
        the pixel-size unit otherwise. ``nan`` when there is no crossing.
    threshold : numpy.ndarray
        The threshold curve the crossing was taken against, per ring.
    crossed : bool
        Whether a crossing was found at all. ``False`` means the answer is *not*
        the last frequency of the axis: it means the image is either resolved
        beyond what this sampling can show, or too noisy to correlate anywhere.
    """

    criterion: str
    frequency: float
    resolution: float
    threshold: np.ndarray
    crossed: bool


def _ring_sums(f1f2, f12, f22, nx, ny, n_bins, bin_width):
    """Accumulate the per-ring sums of one FRC (auxiliary for :func:`frc_curve`).

    Rings are binned on the **normalised** radius ``sqrt((x/nx)^2 + (y/ny)^2)``
    in cycles per pixel, so a non-square image is binned by physical frequency
    rather than by array index — on a 512x64 stack the two axes reach their
    Nyquist limit at completely different index radii.

    The frequency runs are ``-(n // 2) .. (n + 1) // 2``, i.e. the ``n`` indices
    :func:`numpy.fft.fftfreq` enumerates. Stopping at ``n // 2`` instead would
    drop the highest *positive* frequency of every odd axis — 129 of the 4225
    pixels of a 65x65 spectrum, concentrated in the outermost rings, which is
    where the crossing lives.
    """
    # The two ranges are the fftfreq index order, and they carry negative
    # values on purpose: indexing the spectra with them wraps, which is what
    # pairs each index with its own frequency. Fancy-indexing wraps identically,
    # so the gather below is the same set of pixels the loop visited.
    xi = np.arange(-(nx // 2), (nx + 1) // 2)
    yi = np.arange(-(ny // 2), (ny + 1) // 2)
    fx = xi / nx
    fy = yi / ny

    radius = np.sqrt(fx[:, None] ** 2 + fy[None, :] ** 2)
    index = (radius / bin_width).astype(np.int64)  # radius >= 0, so trunc == floor
    inside = index < n_bins
    flat = index[inside]

    rows = np.broadcast_to(xi[:, None], radius.shape)[inside]
    cols = np.broadcast_to(yi[None, :], radius.shape)[inside]

    s12 = np.bincount(flat, weights=f1f2[rows, cols], minlength=n_bins)
    s11 = np.bincount(flat, weights=f12[rows, cols], minlength=n_bins)
    s22 = np.bincount(flat, weights=f22[rows, cols], minlength=n_bins)
    counts = np.bincount(flat, minlength=n_bins).astype(np.int64)
    return s12, s11, s22, counts


def frc_curve(
    image_1: np.ndarray,
    image_2: np.ndarray,
    *,
    bin_width: float | None = None,
    pixel_size: float | None = None,
) -> FrcCurve:
    """Correlate two images ring by ring in Fourier space.

    Parameters
    ----------
    image_1, image_2 : numpy.ndarray
        The two 2-D halves of one measurement — even and odd frames, two
        detectors, or two repeated acquisitions. They must be the same shape and
        must be *statistically independent*: correlating an image with a
        smoothed copy of itself measures the smoothing, not the resolution.
    bin_width : float, optional
        Ring width in cycles per pixel. Defaults to one Fourier pixel of the
        longer axis, which is the finest binning the sampling supports.
    pixel_size : float, optional
        Physical pixel size. When given, the frequency axis is divided by it, so
        the resolution comes out in the same unit.

    Returns
    -------
    FrcCurve
        The curve and the ring occupancies behind it.

    Raises
    ------
    ValueError
        If the images differ in shape, are not 2-D, or the pixel size is not
        positive.
    """
    a = np.asarray(image_1, dtype=np.float64)
    b = np.asarray(image_2, dtype=np.float64)
    if a.ndim != 2 or b.ndim != 2:
        raise ValueError("FRC needs two 2-D images")
    if a.shape != b.shape:
        raise ValueError(f"the two halves differ in shape: {a.shape} vs {b.shape}")
    if pixel_size is not None and not pixel_size > 0:
        raise ValueError("pixel_size must be positive")

    nx, ny = a.shape
    if bin_width is None:
        bin_width = 1.0 / max(nx, ny)
    if not bin_width > 0:
        raise ValueError("bin_width must be positive")

    f1 = np.fft.fft2(a)
    f2 = np.fft.fft2(b)
    f1f2 = np.real(f1 * np.conjugate(f2))
    f12, f22 = np.abs(f1) ** 2, np.abs(f2) ** 2

    # Rings run out to the Nyquist frequency of the *better sampled* axis.
    n_bins = int(np.sqrt(0.5**2 + 0.5**2) / bin_width) + 1
    s12, s11, s22, counts = _ring_sums(f1f2, f12, f22, nx, ny, n_bins, bin_width)

    denominator = np.sqrt(s11 * s22)
    correlation = np.divide(s12, denominator, out=np.zeros_like(s12), where=denominator > 0)
    frequency = (np.arange(n_bins) + 0.5) * bin_width
    # Rings beyond the Nyquist frequency exist only in the corners of the
    # Fourier square: they are partial, anisotropic, and not a resolution the
    # sampling can report. Drop them rather than let a crossing land there.
    keep = (counts > 0) & (frequency <= 0.5)
    if pixel_size is not None:
        frequency = frequency / float(pixel_size)
    return FrcCurve(
        frequency=frequency[keep],
        correlation=correlation[keep],
        counts=counts[keep],
        pixel_size=pixel_size,
    )


def threshold_curve(criterion: str, counts: np.ndarray) -> np.ndarray:
    """Return the threshold the FRC has to fall through, ring by ring.

    Parameters
    ----------
    criterion : str
        ``"fixed_1/7"`` — the constant 0.1428 of Nieuwenhuizen et al., the usual
        choice for fluorescence images, and the only one that does not depend on
        how the rings were binned. ``"half_bit"`` — van Heel & Schatz's ½-bit
        curve, the frequency at which the accumulated information is enough to
        interpret the structure. ``"two_sigma"`` — twice the expected
        correlation of pure noise. Which of the count-dependent two is the
        stricter depends on the image, not on the convention: both start at 1 on
        the innermost rings and fall as the rings fill, ``half_bit`` towards
        0.172 and ``two_sigma`` without limit, so ``two_sigma`` sits *above* the
        fixed 1/7 until a ring holds ~400 Fourier pixels and below it after.
        That is why the criterion belongs beside any quoted number.
    counts : numpy.ndarray
        Fourier pixels per ring (:attr:`FrcCurve.counts`).

    Returns
    -------
    numpy.ndarray
        Threshold per ring.

    Raises
    ------
    ValueError
        If *criterion* is not one of :data:`CRITERIA`.
    """
    n = np.asarray(counts, dtype=np.float64)
    n = np.maximum(n, 1.0)
    if criterion == "fixed_1/7":
        return np.full(n.shape, 1.0 / 7.0)
    if criterion == "half_bit":
        root = np.sqrt(n)
        curve = (0.2071 + 1.9102 / root) / (1.2071 + 0.9102 / root)
    elif criterion == "two_sigma":
        curve = 2.0 / np.sqrt(n / 2.0)
    else:
        raise ValueError(f"unknown criterion {criterion!r}; expected one of {CRITERIA}")
    # Both count-dependent curves exceed 1 on the innermost rings, which hold a
    # handful of Fourier pixels each. An FRC cannot exceed 1, so a threshold
    # above it is not a criterion but an artefact of the ring occupancy; it is
    # clipped here and skipped by the crossing search in :func:`resolve`.
    return np.minimum(curve, 1.0)


def _smoothed(values: np.ndarray, window: int) -> np.ndarray:
    """Return *values* boxcar-smoothed over an odd *window* of rings."""
    window = int(window)
    if window <= 1:
        return np.asarray(values, dtype=np.float64)
    if window % 2 == 0:
        window += 1
    padded = np.pad(np.asarray(values, dtype=np.float64), window // 2, mode="edge")
    kernel = np.ones(window) / window
    return np.convolve(padded, kernel, mode="valid")


def resolve(
    curve: FrcCurve,
    criterion: str = "fixed_1/7",
    *,
    smooth: int = 3,
) -> FrcResolution:
    """Find where *curve* falls through its threshold, and invert the frequency.

    The crossing is the **first** downward one, interpolated linearly between
    the two rings that bracket it. Taking the first matters: an FRC that has
    already decayed into the noise wanders back and forth across the threshold,
    and every later crossing is that wander, not a resolution.

    Parameters
    ----------
    curve : FrcCurve
        The measured curve.
    criterion : str
        Threshold criterion, see :func:`threshold_curve`.
    smooth : int
        Width (in rings) of a boxcar smoothing applied before the search. The
        raw curve is noisy ring to ring, and an unsmoothed crossing can land a
        ring or two early on a single dip.

    Returns
    -------
    FrcResolution
        The crossing, with ``crossed=False`` when there is none.
    """
    threshold = threshold_curve(criterion, curve.counts)
    values = _smoothed(curve.correlation, smooth)
    frequency = np.asarray(curve.frequency, dtype=np.float64)

    below = values < threshold
    # Start past the innermost rings: the first is the DC term (always 1, and 0
    # for a blank image, which would "cross" immediately), and the count-based
    # thresholds saturate at 1 there — with a threshold of 1 every ring is
    # nominally below it, and the σ criterion would report the field of view as
    # the resolution of any image at all.
    start = 1
    while start < threshold.size and threshold[start] >= 1.0:
        start += 1
    # A crossing is a *downward* one, so the ring before it has to sit above its
    # own threshold: only then do the two rings bracket the crossing and only
    # then is the interpolation below an interpolation. Taking the first ring
    # that is merely below the line extrapolates instead — from the ring the
    # `start` loop deliberately skipped, or from an innermost ring that was
    # already below — and the crossing then lands outside the bracket, at a
    # frequency finer than the sampling or at a negative one. A curve that never
    # rises above its threshold has no crossing at all: nothing is resolved.
    index = None
    for i in range(start, below.size):
        if below[i] and not below[i - 1]:
            index = i
            break
    if index is None:
        return FrcResolution(criterion, float("nan"), float("nan"), threshold, False)

    previous = index - 1
    gap_now = values[index] - threshold[index]
    gap_before = values[previous] - threshold[previous]
    # ``gap_before >= 0 > gap_now`` by the search above, so the denominator is
    # strictly positive and the weight lies in [0, 1]: the crossing cannot leave
    # the bracket ``[frequency[previous], frequency[index]]``.
    weight = gap_before / (gap_before - gap_now)
    crossing = float(frequency[previous] + weight * (frequency[index] - frequency[previous]))
    resolution = float("inf") if crossing == 0 else 1.0 / crossing
    return FrcResolution(criterion, crossing, resolution, threshold, True)


def split_frames(stack: np.ndarray, mode: str = "even_odd") -> tuple[np.ndarray, np.ndarray]:
    """Split a frame stack into the two independent halves the FRC needs.

    Parameters
    ----------
    stack : numpy.ndarray
        3-D ``(frame, y, x)`` stack. A 2-D array is rejected: a single frame
        holds no independent second measurement, and correlating it with itself
        returns 1 at every frequency.
    mode : str
        ``"even_odd"`` sums the even and the odd frames — the standard split,
        and the one that is insensitive to drift over the acquisition. ``"halves"``
        sums the first and the second half of the stack, which is what to use
        when consecutive frames are *not* independent (a slow detector, or an
        exposure carried across frames).

    Returns
    -------
    tuple of numpy.ndarray
        The two 2-D half images.

    Raises
    ------
    ValueError
        If the stack is not 3-D or holds fewer than two frames.
    """
    data = np.asarray(stack, dtype=np.float64)
    if data.ndim != 3:
        raise ValueError("a frame stack (frame, y, x) is needed to split")
    if data.shape[0] < 2:
        raise ValueError("at least two frames are needed for an FRC")
    if mode == "even_odd":
        return data[0::2].sum(axis=0), data[1::2].sum(axis=0)
    if mode == "halves":
        middle = data.shape[0] // 2
        return data[:middle].sum(axis=0), data[middle:].sum(axis=0)
    raise ValueError(f"unknown split mode {mode!r}; expected 'even_odd' or 'halves'")


__all__ = [
    "CRITERIA",
    "FrcCurve",
    "FrcResolution",
    "frc_curve",
    "resolve",
    "split_frames",
    "threshold_curve",
]
