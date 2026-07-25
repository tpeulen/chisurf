"""Qt-free compute for the drift-correction plugin.

Loads a TIFF stack or a photon stream through the shared image-source seam,
measures the inter-frame drift, and removes it. The GUI, the CLI and the tests
all call the functions here.

The two source kinds are corrected differently, and the difference matters:

* A **TIFF stack** is an array of intensities, so correcting it means shifting
  numbers.
* A **photon stream** reconstructs into a confocal image whose pixels hold
  *photon lists*, so correcting it means moving photons between pixels
  (:func:`~chisurf.core.fluorescence.imaging.drift.correct_clsm_drift`). Doing
  it that way keeps micro-times, lifetimes and correlations valid afterwards —
  shifting a rendered intensity image would throw the photon-level information
  away.

The estimator itself is the same in both cases, and follows PAM's MIA: FFT
cross-correlation against a reference frame, smoothed before the peak search.
"""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Any

import numpy as np

from chisurf.core.fluorescence.imaging import load_image_stack
from chisurf.core.fluorescence.imaging.drift import (
    apply_drift,
    correct_clsm_drift,
    estimate_drift,
)
from chisurf.core.fluorescence.imaging.image_source import is_photon_stream
from chisurf.core.roi import as_roi


@dataclasses.dataclass
class DriftResult:
    """Outcome of a drift measurement.

    Attributes
    ----------
    shifts : numpy.ndarray
        ``(n_frames, 2)`` measured ``(dy, dx)`` displacement per frame.
    before : numpy.ndarray
        Frame-summed image of the channel the drift was measured on, before
        correction.
    after : numpy.ndarray
        The same projection after correction. Drift shows up as a blurred
        ``before`` sharpening in ``after`` — the quickest visual check there is.
    channel_names : list of str
        Channel names of the source.
    kind : str
        ``'image'`` for TIFF-like sources, ``'tttr'`` for photon streams.
    source : str
        The file the stack came from.
    """

    shifts: np.ndarray
    before: np.ndarray
    after: np.ndarray
    channel_names: list[str]
    kind: str = "image"
    source: str = ""

    @property
    def n_frames(self) -> int:
        """Number of frames measured."""
        return int(np.asarray(self.shifts).shape[0])

    @property
    def total_drift(self) -> float:
        """Largest displacement from the origin, in pixels.

        The single number worth looking at: if it is a fraction of a pixel the
        correction changes nothing, and if it exceeds the beam waist any
        frame-lag analysis of the uncorrected data was compromised.
        """
        sh = np.asarray(self.shifts, dtype=float)
        return float(np.hypot(sh[:, 0], sh[:, 1]).max()) if sh.size else 0.0

    def to_dict(self) -> dict:
        """Return a JSON-friendly summary (without the preview images)."""
        return {
            "source": self.source,
            "kind": self.kind,
            "n_frames": self.n_frames,
            "channel_names": list(self.channel_names),
            "total_drift_px": self.total_drift,
            "shifts": np.asarray(self.shifts, dtype=float).tolist(),
        }


def measure_drift(
    filename: str,
    channel: Any = 0,
    *,
    reference: str = "first",
    roi: Any = None,
    smooth: float = 2.0,
    subpixel: bool = False,
    mode: str = "wrap",
    windows: dict | None = None,
    channel_axis: Any = None,
) -> DriftResult:
    """Measure and remove the drift of one file, returning both projections.

    Parameters
    ----------
    filename : str
        A TIFF-like image stack or a photon stream.
    channel : int or str
        Channel the drift is measured on. As in PAM, one channel drives the
        estimate; a bright structured channel gives the sharpest peak.
    reference : str
        ``'first'``, ``'previous'`` or ``'mean'``.
    roi : ROI or dict, optional
        Restrict the estimate to a region.
    smooth : float
        Gaussian smoothing of the correlation before the peak search, in pixels.
    subpixel : bool
        Refine each peak by parabolic interpolation.
    mode : str
        ``'wrap'`` conserves every photon; ``'constant'`` drops what leaves the
        frame.
    windows : dict, optional
        Detector/micro-time windows for photon streams.
    channel_axis : int or str, optional
        Channel axis override for TIFF stacks.

    Returns
    -------
    DriftResult
        The shifts and the before/after projections.

    Raises
    ------
    ValueError
        If the source has fewer than two frames, which leaves nothing to align.
    """
    stack = load_image_stack(filename, windows=windows, channel_axis=channel_axis)
    if stack.n_frames < 2:
        raise ValueError(
            f"{filename} has {stack.n_frames} frame(s); drift needs at least two"
        )

    frames = stack.frames(channel)
    shifts = estimate_drift(
        frames, reference=reference, roi=as_roi(roi), smooth=smooth, subpixel=subpixel
    )
    corrected = apply_drift(frames, shifts, mode=mode)
    return DriftResult(
        shifts=shifts,
        before=frames.sum(axis=0),
        after=corrected.sum(axis=0),
        channel_names=list(stack.channel_names),
        kind=stack.kind,
        source=str(filename),
    )


def corrected_stack(
    filename: str,
    channel: Any = 0,
    *,
    shifts: np.ndarray | None = None,
    mode: str = "wrap",
    windows: dict | None = None,
    channel_axis: Any = None,
    **kwargs: Any,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the whole multi-channel stack with the drift removed.

    The drift is measured on one channel and applied to all of them, as PAM
    does: the sample moves as a whole, so a per-channel estimate would only add
    noise.

    Parameters
    ----------
    filename : str
        Source file.
    channel : int or str
        Channel the drift is measured on.
    shifts : numpy.ndarray, optional
        Pre-measured displacements; measured from the file when omitted.
    mode : str
        ``'wrap'`` or ``'constant'``.
    windows, channel_axis
        Passed to the loader.
    **kwargs
        Passed to :func:`measure_drift` when *shifts* is not supplied.

    Returns
    -------
    tuple of numpy.ndarray
        ``(data, shifts)`` with data shaped ``(n_frames, n_channels, ny, nx)``.
    """
    stack = load_image_stack(filename, windows=windows, channel_axis=channel_axis)
    if shifts is None:
        shifts = measure_drift(
            filename, channel, mode=mode, windows=windows,
            channel_axis=channel_axis, **kwargs
        ).shifts

    out = np.empty_like(np.asarray(stack.data, dtype=float))
    for ch in range(stack.n_channels):
        out[:, ch] = apply_drift(
            np.asarray(stack.data[:, ch], dtype=float), shifts, mode=mode
        )
    return out, np.asarray(shifts)


def correct_photon_image(
    filename: str,
    channels: list[int] | None = None,
    *,
    reference: str = "first",
    roi: Any = None,
    smooth: float = 2.0,
    subpixel: bool = False,
    mode: str = "wrap",
    reading_routine: str | None = None,
):
    """Reconstruct a photon stream and correct its drift **photon by photon**.

    This is the path that makes drift correction meaningful for confocal data:
    the photons are moved between pixels, so the returned image can still be
    used for lifetime fitting, correlation or decay extraction. Shifting a
    rendered intensity image could not.

    Parameters
    ----------
    filename : str
        Photon-stream file.
    channels : list of int, optional
        Routing channels to reconstruct; defaults to ``[0]``.
    reference, roi, smooth, subpixel, mode
        As for :func:`measure_drift`.
    reading_routine : str, optional
        Container type override for the reader.

    Returns
    -------
    tuple
        ``(clsm_image, shifts)`` — the corrected image and the displacements
        that were removed.

    Raises
    ------
    ValueError
        If the file is not a photon stream.
    """
    import tttrlib

    if not is_photon_stream(filename):
        raise ValueError(f"{filename} is not a photon stream")

    tttr = (
        tttrlib.TTTR(str(filename), reading_routine)
        if reading_routine
        else tttrlib.TTTR(str(filename))
    )
    clsm = tttrlib.CLSMImage(
        tttr_data=tttr, channels=list(channels or [0]), fill=True
    )
    shifts = correct_clsm_drift(
        clsm, reference=reference, roi=as_roi(roi),
        smooth=smooth, subpixel=subpixel, mode=mode,
    )
    return clsm, shifts


def write_shifts_csv(shifts: np.ndarray, path: str) -> str:
    """Write the per-frame displacements to a CSV file.

    Parameters
    ----------
    shifts : numpy.ndarray
        ``(n_frames, 2)`` displacements.
    path : str
        Output path.

    Returns
    -------
    str
        The path written.
    """
    sh = np.asarray(shifts, dtype=float)
    frames = np.arange(len(sh))
    out = pathlib.Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(
        out,
        np.column_stack([frames, sh[:, 1], sh[:, 0], np.hypot(sh[:, 0], sh[:, 1])]),
        delimiter=",",
        header="frame,dx_px,dy_px,magnitude_px",
        comments="",
        fmt="%.4f",
    )
    return str(out)


def write_stack_tiff(data: np.ndarray, path: str) -> str:
    """Write a corrected stack to a multi-page TIFF.

    Parameters
    ----------
    data : numpy.ndarray
        ``(n_frames, n_channels, ny, nx)`` or ``(n_frames, ny, nx)``.
    path : str
        Output path.

    Returns
    -------
    str
        The path written.
    """
    import tifffile

    arr = np.asarray(data)
    if arr.ndim == 4 and arr.shape[1] == 1:
        arr = arr[:, 0]
    out = pathlib.Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(str(out), arr.astype(np.float32))
    return str(out)
