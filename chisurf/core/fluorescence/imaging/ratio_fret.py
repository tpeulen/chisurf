"""Ratiometric FRET from two-channel image series.

The cheapest FRET readout there is: divide the acceptor channel by the donor
channel. No lifetimes, no anisotropy, no correction factors — just a number per
pixel, or per frame, that moves when the sensor does.

**A/D is not E.** The ratio is not a FRET efficiency and cannot be converted to
one without the leakage, direct-excitation and detection-efficiency corrections
(see :mod:`chisurf.core.fluorescence.fret.accurate`). Treating it as an
efficiency will give a number that is wrong by a factor nobody can reconstruct
later. What the ratio *is* good for is **change**: a sensor responding to a
stimulus, a translocation, a titration — anything where the same field is
compared with itself over time. That is why the trace below is normalised to a
baseline window by default: it reports fold-change from rest, which is
meaningful, rather than an absolute ratio, which is not.

Dividing two noisy channels amplifies noise badly — the variance of a ratio
blows up wherever the denominator approaches zero — so both the per-channel
images and the resulting map are median filtered, and dark pixels are excluded
rather than divided.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional, Sequence, Tuple

import numpy as np


@dataclasses.dataclass
class RatioTrace:
    """An acceptor/donor ratio followed over time.

    Attributes
    ----------
    time : numpy.ndarray
        Frame times in seconds.
    ratio : numpy.ndarray
        Acceptor/donor ratio per frame, normalised if a baseline was given.
    donor, acceptor : numpy.ndarray
        The per-frame mean intensities the ratio came from, kept because a
        ratio that moves is meaningless until you know which channel moved.
    normalisation : float
        The baseline ratio divided out (1.0 when unnormalised).
    """

    time: np.ndarray
    ratio: np.ndarray
    donor: np.ndarray
    acceptor: np.ndarray
    normalisation: float = 1.0

    @property
    def response(self) -> float:
        """Return the largest fractional excursion from the baseline.

        The single number a sensor experiment is usually after.
        """
        r = np.asarray(self.ratio, dtype=float)
        finite = r[np.isfinite(r)]
        if finite.size == 0:
            return float("nan")
        return float(np.max(np.abs(finite - 1.0))) if self.normalisation != 1.0 else float(
            np.max(finite) / np.min(finite) - 1.0
        )

    def to_dict(self) -> dict:
        """Return the trace as a JSON-friendly dictionary."""
        return {
            "time": np.asarray(self.time, dtype=float).tolist(),
            "ratio": np.asarray(self.ratio, dtype=float).tolist(),
            "normalisation": float(self.normalisation),
            "response": float(self.response),
        }


def _region_mean(stack: np.ndarray, roi: Any) -> np.ndarray:
    """Return the per-frame mean of a stack inside a region.

    Parameters
    ----------
    stack : numpy.ndarray
        ``(n_frames, ny, nx)``.
    roi : ROI or numpy.ndarray or None
        Region to average over; ``None`` uses the whole frame.

    Returns
    -------
    numpy.ndarray
        One mean per frame.
    """
    if roi is None:
        return stack.reshape(stack.shape[0], -1).mean(axis=1)

    from chisurf.core.roi import ROI

    mask = roi.to_mask(stack.shape[1:], image=stack) if isinstance(roi, ROI) else np.asarray(roi, bool)
    if mask.shape != stack.shape[1:]:
        raise ValueError("the region must match the frame shape")
    if not mask.any():
        raise ValueError("the region selects no pixel")
    return stack[:, mask].mean(axis=1)


def ratio_trace(
    donor: np.ndarray,
    acceptor: np.ndarray,
    roi: Any = None,
    *,
    baseline: Optional[Sequence[int]] = None,
    frame_time: float = 1.0,
) -> RatioTrace:
    """Follow the acceptor/donor ratio of a region over time.

    Parameters
    ----------
    donor, acceptor : numpy.ndarray
        Image stacks ``(n_frames, ny, nx)`` of the two channels.
    roi : ROI or numpy.ndarray, optional
        Region to average over — a cell, a compartment, the illuminated patch.
        Defaults to the whole frame.
    baseline : sequence of int, optional
        Frame indices defining the resting state, as ``(start, stop)`` or an
        explicit index list. The mean ratio there is divided out, so the trace
        reads as fold-change from rest. Omit to leave the raw ratio.
    frame_time : float
        Seconds per frame.

    Returns
    -------
    RatioTrace
        The trace, its two source channels, and the normalisation applied.

    Raises
    ------
    ValueError
        If the two stacks disagree, or the baseline selects no usable frame.

    Examples
    --------
    A sensor whose acceptor doubles halfway through, normalised to the first
    three frames, reads 1.0 at rest and 2.0 after:

    >>> d = np.ones((6, 4, 4))
    >>> a = np.ones((6, 4, 4)); a[3:] = 2.0
    >>> t = ratio_trace(d, a, baseline=(0, 3), frame_time=0.5)
    >>> t.ratio.round(3).tolist()
    [1.0, 1.0, 1.0, 2.0, 2.0, 2.0]
    >>> t.time.tolist()
    [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
    """
    d = np.asarray(donor, dtype=float)
    a = np.asarray(acceptor, dtype=float)
    if d.ndim != 3 or a.ndim != 3:
        raise ValueError(f"expected two (n_frames, ny, nx) stacks; got {d.shape}, {a.shape}")
    if d.shape != a.shape:
        raise ValueError(f"the channels differ in shape: {d.shape} vs {a.shape}")

    d_mean = _region_mean(d, roi)
    a_mean = _region_mean(a, roi)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = a_mean / d_mean

    norm = 1.0
    if baseline is not None:
        idx = (
            np.arange(int(baseline[0]), int(baseline[1]))
            if len(baseline) == 2 and int(baseline[1]) > int(baseline[0]) + 1
            else np.asarray(baseline, dtype=int)
        )
        idx = idx[(idx >= 0) & (idx < len(ratio))]
        values = ratio[idx]
        values = values[np.isfinite(values)]
        if values.size == 0:
            raise ValueError("the baseline window contains no usable frame")
        norm = float(values.mean())
        if norm == 0:
            raise ValueError("the baseline ratio is zero; cannot normalise")
        ratio = ratio / norm

    return RatioTrace(
        time=np.arange(len(ratio), dtype=float) * float(frame_time),
        ratio=ratio,
        donor=d_mean,
        acceptor=a_mean,
        normalisation=norm,
    )


def ratio_image(
    donor: np.ndarray,
    acceptor: np.ndarray,
    frames: Optional[Sequence[int]] = None,
    *,
    donor_roi: Any = None,
    acceptor_roi: Any = None,
    normalisation: float = 1.0,
    channel_median: int = 3,
    ratio_median: int = 5,
    minimum_donor: float = 0.0,
) -> np.ndarray:
    """Return a per-pixel acceptor/donor ratio map.

    The filtering is not cosmetic. A ratio of two shot-noise-limited channels
    has a variance that diverges as the denominator approaches zero, so a raw
    ``A/D`` map is dominated by speckle wherever the donor is dim. Each channel
    is median filtered before the division, the map is median filtered after it,
    and pixels below *minimum_donor* are excluded outright rather than divided.

    Parameters
    ----------
    donor, acceptor : numpy.ndarray
        Image stacks ``(n_frames, ny, nx)``.
    frames : sequence of int, optional
        Frame indices to average before dividing, as ``(start, stop)`` or an
        explicit list. Defaults to every frame.
    donor_roi, acceptor_roi : ROI or numpy.ndarray, optional
        Per-channel regions; pixels outside are excluded from the map.
    normalisation : float
        Divide the map by this — pass the trace's normalisation to put the map
        on the same fold-change scale.
    channel_median : int
        Median-filter size applied to each averaged channel. 0 disables.
    ratio_median : int
        Median-filter size applied to the ratio map. 0 disables.
    minimum_donor : float
        Donor intensity below which a pixel yields NaN instead of a ratio.

    Returns
    -------
    numpy.ndarray
        The ratio map, NaN where it is not defined.

    Raises
    ------
    ValueError
        If the two stacks disagree in shape.
    """
    from scipy.ndimage import median_filter

    d = np.asarray(donor, dtype=float)
    a = np.asarray(acceptor, dtype=float)
    if d.shape != a.shape or d.ndim != 3:
        raise ValueError(f"expected two matching stacks; got {d.shape} and {a.shape}")

    if frames is None:
        idx = np.arange(d.shape[0])
    elif len(frames) == 2 and int(frames[1]) > int(frames[0]) + 1:
        idx = np.arange(int(frames[0]), int(frames[1]))
    else:
        idx = np.asarray(frames, dtype=int)
    idx = idx[(idx >= 0) & (idx < d.shape[0])]
    if idx.size == 0:
        raise ValueError("no valid frame selected")

    d_img = d[idx].mean(axis=0)
    a_img = a[idx].mean(axis=0)
    if channel_median and channel_median > 1:
        d_img = median_filter(d_img, size=int(channel_median), mode="nearest")
        a_img = median_filter(a_img, size=int(channel_median), mode="nearest")

    # Background subtraction can push pixels negative; a negative intensity is
    # not a measurement, and it would flip the sign of the ratio.
    d_img = np.clip(d_img, 0.0, None)
    a_img = np.clip(a_img, 0.0, None)

    from chisurf.core.roi import ROI

    keep = np.ones(d_img.shape, dtype=bool)
    for roi, image in ((donor_roi, d), (acceptor_roi, a)):
        if roi is None:
            continue
        mask = roi.to_mask(d_img.shape, image=image) if isinstance(roi, ROI) else np.asarray(roi, bool)
        keep &= mask

    keep &= d_img > float(minimum_donor)

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(keep, a_img / d_img, np.nan)
    if normalisation and normalisation != 1.0:
        ratio = ratio / float(normalisation)

    if ratio_median and ratio_median > 1:
        # Median-filter only the defined pixels; NaNs would otherwise spread.
        filled = np.where(np.isfinite(ratio), ratio, np.nanmedian(ratio))
        smoothed = median_filter(filled, size=int(ratio_median), mode="nearest")
        ratio = np.where(np.isfinite(ratio), smoothed, np.nan)
    return ratio
