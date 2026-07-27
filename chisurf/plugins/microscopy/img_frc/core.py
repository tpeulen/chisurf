"""Qt-free compute for the FRC resolution calculator.

Reads a TIFF stack or a photon stream through the shared image-source seam,
splits it into two statistically independent halves, correlates them ring by
ring (:mod:`chisurf.core.fluorescence.imaging.frc`) and reports the frequency at
which the correlation falls through the chosen threshold — the resolution the
image actually achieved.

The whole point is the *split*: the FRC measures reproducibility between two
independent measurements of the same object. Correlating an image with itself,
or with a filtered copy of itself, returns the filter and not the resolution, so
every split offered here produces two genuinely independent halves:

* **even/odd frames** — the default, and insensitive to slow drift because both
  halves span the whole acquisition;
* **first/second half** — for detectors whose consecutive frames are *not*
  independent;
* **two channels** — two detectors that saw the same object;
* **two files** — two repeated acquisitions.

The GUI, the CLI, the RPC services and the tests all call the functions here.
"""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Any

import numpy as np

from chisurf.core.fluorescence.imaging import frc as frc_mod
from chisurf.core.fluorescence.imaging import load_image_stack

#: How the one acquisition is cut into two independent halves.
SPLITS = ("even_odd", "halves", "channels", "two_files")


@dataclasses.dataclass
class FrcAnalysis:
    """One resolution measurement, everything a caller might display or save.

    Attributes
    ----------
    frequency : numpy.ndarray
        Ring frequency, in 1/nm when a pixel size was given, else cycles/pixel.
    correlation : numpy.ndarray
        The FRC curve.
    threshold : numpy.ndarray
        The threshold curve it was read against.
    counts : numpy.ndarray
        Fourier pixels per ring.
    resolution : float
        Resolution in nm (or in pixels without a pixel size); ``nan`` when the
        curve never crosses.
    crossing : float
        Frequency of the crossing; ``nan`` when there is none.
    crossed : bool
        Whether a crossing was found. ``False`` is a real answer, not a failure:
        either the image is resolved past what the sampling can show, or the two
        halves never correlate at all.
    criterion : str
        Threshold convention used. A resolution without it means nothing.
    unit : str
        ``"nm"`` or ``"px"`` — which of the two the numbers are in.
    half_1, half_2 : numpy.ndarray
        The two half images the curve came from, for display.
    channel_names : list of str
        Channel names of the source.
    kind : str
        ``"image"`` for TIFF-like sources, ``"tttr"`` for photon streams.
    source : str
        File (or files) the halves came from.
    n_frames : int
        Frames in the source stack.
    """

    frequency: np.ndarray
    correlation: np.ndarray
    threshold: np.ndarray
    counts: np.ndarray
    resolution: float
    crossing: float
    crossed: bool
    criterion: str
    unit: str
    half_1: np.ndarray
    half_2: np.ndarray
    channel_names: list[str]
    kind: str
    source: str
    n_frames: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe summary (curves included, images not).

        The half images are deliberately left out: they are megabytes of pixels
        and an RPC caller asking for a resolution does not want them on the
        wire.
        """
        return {
            "frequency": [float(v) for v in self.frequency],
            "correlation": [float(v) for v in np.nan_to_num(self.correlation)],
            "threshold": [float(v) for v in self.threshold],
            "counts": [int(v) for v in self.counts],
            "resolution": None if not np.isfinite(self.resolution) else float(self.resolution),
            "crossing": None if not np.isfinite(self.crossing) else float(self.crossing),
            "crossed": bool(self.crossed),
            "criterion": self.criterion,
            "unit": self.unit,
            "channel_names": list(self.channel_names),
            "kind": self.kind,
            "source": self.source,
            "n_frames": int(self.n_frames),
        }


#: How a 3-D TIFF's leading axis is interpreted.
AXIS_ORDERS = ("auto", "frames", "channels")


def channel_axis_for(axis_order: str):
    """Translate an :data:`AXIS_ORDERS` choice into a ``load_image_stack`` argument.

    The default heuristic reads a short leading axis as channels, which is right
    for an RGB image and wrong for a four-frame time series — and getting it
    wrong here is fatal rather than cosmetic, since a frame split then has one
    frame to work with.
    """
    if axis_order in (None, "", "auto"):
        return None
    if axis_order == "frames":
        return "none"
    if axis_order == "channels":
        return 0
    raise ValueError(f"unknown axis order {axis_order!r}; expected one of {AXIS_ORDERS}")


def _stack(filename: str, channels=None, windows=None, axis_order: str = "auto"):
    """Load *filename* into an :class:`ImageStack` (TIFF or photon stream)."""
    if not pathlib.Path(filename).is_file():
        raise FileNotFoundError(f"no such file: {filename}")
    return load_image_stack(
        filename,
        channels=channels,
        windows=windows,
        channel_axis=channel_axis_for(axis_order),
    )


def halves(
    filename: str,
    *,
    split: str = "even_odd",
    channel: int | str = 0,
    channel_2: int | str | None = None,
    second_filename: str | None = None,
    channels=None,
    windows=None,
    axis_order: str = "auto",
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Return the two independent half images, and what they came from.

    Parameters
    ----------
    filename : str
        TIFF stack or photon stream (``.ptu``, ``.ht3``, …).
    split : str
        One of :data:`SPLITS`.
    channel : int or str
        Channel to measure, by index or name.
    channel_2 : int or str, optional
        Second channel, for ``split="channels"``. Defaults to *channel* + 1.
    second_filename : str, optional
        Second acquisition, required by ``split="two_files"``.
    channels, windows : optional
        Photon streams only: routing channels / named detector windows to fill
        (see :func:`~chisurf.core.fluorescence.imaging.load_image_stack`).
    axis_order : str
        TIFF only: how to read the leading axis of a 3-D file — ``"auto"``,
        ``"frames"`` or ``"channels"`` (:data:`AXIS_ORDERS`).

    Returns
    -------
    tuple
        ``(half_1, half_2, info)`` where *info* carries the channel names, the
        source kind and the frame count.

    Raises
    ------
    ValueError
        If *split* is unknown, or the split cannot be made from this source (one
        frame for a frame split, one channel for a channel split, a missing
        second file).
    """
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}; expected one of {SPLITS}")

    stack = _stack(filename, channels, windows, axis_order)
    index = stack.channel_index(channel)
    info = {
        "channel_names": list(stack.channel_names),
        "kind": stack.kind,
        "source": stack.source or str(filename),
        "n_frames": stack.n_frames,
    }

    if split in ("even_odd", "halves"):
        frames = np.asarray(stack.data[:, index], dtype=np.float64)
        if frames.shape[0] < 2:
            raise ValueError(
                "a frame split needs at least two frames; this source has "
                f"{frames.shape[0]} — use a channel split or a second file"
            )
        a, b = frc_mod.split_frames(frames, split)
        return a, b, info

    if split == "channels":
        other = index + 1 if channel_2 is None else stack.channel_index(channel_2)
        if stack.n_channels < 2:
            raise ValueError("a channel split needs at least two channels")
        if other == index:
            raise ValueError("the two channels of a channel split must differ")
        if other >= stack.n_channels:
            raise ValueError(
                f"channel {other} is out of range; the source has {stack.n_channels}"
            )
        info["channel_names"] = list(stack.channel_names)
        return (
            np.asarray(stack.image(index), dtype=np.float64),
            np.asarray(stack.image(other), dtype=np.float64),
            info,
        )

    # two_files
    if not second_filename:
        raise ValueError("split='two_files' needs a second file")
    other_stack = _stack(second_filename, channels, windows, axis_order)
    info["source"] = f"{info['source']} + {other_stack.source or second_filename}"
    return (
        np.asarray(stack.image(index), dtype=np.float64),
        np.asarray(other_stack.image(other_stack.channel_index(channel)), dtype=np.float64),
        info,
    )


def analyse(
    filename: str,
    *,
    split: str = "even_odd",
    channel: int | str = 0,
    channel_2: int | str | None = None,
    second_filename: str | None = None,
    pixel_size_nm: float | None = None,
    criterion: str = "fixed_1/7",
    bin_width: float | None = None,
    smooth: int = 3,
    channels=None,
    windows=None,
    axis_order: str = "auto",
) -> FrcAnalysis:
    """Measure the resolution of an image by Fourier ring correlation.

    Parameters
    ----------
    filename : str
        TIFF stack or photon stream.
    split, channel, channel_2, second_filename, channels, windows, axis_order
        Passed to :func:`halves`.
    pixel_size_nm : float, optional
        Physical pixel size in nm. Without it the answer is in pixels, which is
        still a resolution — just not one to quote in a figure.
    criterion : str
        Threshold convention, see
        :func:`~chisurf.core.fluorescence.imaging.frc.threshold_curve`.
    bin_width : float, optional
        Ring width in cycles per pixel; defaults to one Fourier pixel.
    smooth : int
        Rings averaged before the crossing search.

    Returns
    -------
    FrcAnalysis
        The curve, the threshold and the resolution.
    """
    half_1, half_2, info = halves(
        filename,
        split=split,
        channel=channel,
        channel_2=channel_2,
        second_filename=second_filename,
        channels=channels,
        windows=windows,
        axis_order=axis_order,
    )
    curve = frc_mod.frc_curve(
        half_1, half_2, bin_width=bin_width, pixel_size=pixel_size_nm
    )
    result = frc_mod.resolve(curve, criterion, smooth=smooth)
    return FrcAnalysis(
        frequency=curve.frequency,
        correlation=curve.correlation,
        threshold=result.threshold,
        counts=curve.counts,
        resolution=result.resolution,
        crossing=result.frequency,
        crossed=result.crossed,
        criterion=criterion,
        unit="nm" if pixel_size_nm else "px",
        half_1=half_1,
        half_2=half_2,
        channel_names=info["channel_names"],
        kind=info["kind"],
        source=info["source"],
        n_frames=info["n_frames"],
    )


def write_csv(analysis: FrcAnalysis, path: str) -> str:
    """Write the curve, its threshold and the ring counts to *path* as CSV."""
    unit = "1/nm" if analysis.unit == "nm" else "1/px"
    rows = np.vstack(
        [
            analysis.frequency,
            np.nan_to_num(analysis.correlation),
            analysis.threshold,
            analysis.counts,
        ]
    ).T
    np.savetxt(
        path,
        rows,
        delimiter=",",
        header=f"frequency_{unit},correlation,threshold,ring_pixels",
        comments="",
        fmt="%.8g",
    )
    return str(path)


__all__ = [
    "AXIS_ORDERS",
    "SPLITS",
    "FrcAnalysis",
    "analyse",
    "channel_axis_for",
    "halves",
    "write_csv",
]
