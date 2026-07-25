"""One loader for multi-channel microscopy images (TIFF stacks and TTTR/PTU).

Colocalization — and any other multi-channel pixel analysis — needs the same
thing from very different files: a ``(frame, channel, y, x)`` intensity stack
with named channels. This module is that single seam.

* **Camera / TIFF images** (``.tif``, ``.tiff``, and anything imageio reads) are
  read with their axis order taken from the file (ImageJ hyperstack metadata or
  the TIFF series axes) rather than guessed.
* **Photon streams** (``.ptu``, ``.ht3``, …) are turned into images by filling a
  confocal-scan image from the marker records, one channel per detector routing
  channel (or per named detector window when a setup provides them).

Both paths return the same :class:`ImageStack`, so downstream analyses never
branch on the file format.
"""

from __future__ import annotations

import dataclasses
import pathlib

import numpy as np

__all__ = ["ImageStack", "TTTR_SUFFIXES", "is_photon_stream", "load_image_stack"]

#: File suffixes read as photon streams (confocal scan) rather than as images.
TTTR_SUFFIXES = frozenset({".ptu", ".ht3", ".pt3", ".pt2", ".t3r", ".spc", ".hdf", ".ht2"})


@dataclasses.dataclass
class ImageStack:
    """A multi-channel image stack with named channels.

    Attributes
    ----------
    data : numpy.ndarray
        Intensities shaped ``(n_frames, n_channels, ny, nx)``.
    channel_names : list of str
        One name per channel (``"ch0"`` … or the detector-window names).
    source : str
        Path the stack was read from.
    kind : str
        ``"image"`` for TIFF-like files, ``"tttr"`` for photon streams.
    metadata : dict
        Reader-specific extras (axis order, header fields, …).
    """

    data: np.ndarray
    channel_names: list[str]
    source: str = ""
    kind: str = "image"
    metadata: dict = dataclasses.field(default_factory=dict)

    @property
    def n_frames(self) -> int:
        """Return the number of frames in the stack."""
        return int(self.data.shape[0])

    @property
    def n_channels(self) -> int:
        """Return the number of channels in the stack."""
        return int(self.data.shape[1])

    @property
    def frame_shape(self) -> tuple[int, int]:
        """Return the ``(ny, nx)`` shape of a single frame."""
        return int(self.data.shape[2]), int(self.data.shape[3])

    def channel_index(self, channel) -> int:
        """Return the integer index of *channel* given as an index or a name.

        Parameters
        ----------
        channel : int or str
            Channel index, or one of :attr:`channel_names`.

        Returns
        -------
        int
            The channel index.
        """
        if isinstance(channel, str):
            if channel not in self.channel_names:
                raise KeyError(f"unknown channel {channel!r}; have {self.channel_names}")
            return self.channel_names.index(channel)
        return int(channel)

    def image(self, channel, frame: int | None = None) -> np.ndarray:
        """Return a 2-D map for *channel*, summed over frames unless *frame* is given.

        Parameters
        ----------
        channel : int or str
            Channel index or name.
        frame : int, optional
            Single frame to return; ``None`` sums the whole stack.

        Returns
        -------
        numpy.ndarray
            2-D ``(ny, nx)`` intensity map.
        """
        idx = self.channel_index(channel)
        if frame is None:
            return np.asarray(self.data[:, idx].sum(axis=0), dtype=float)
        return np.asarray(self.data[int(frame), idx], dtype=float)

    def frames(self, channel) -> np.ndarray:
        """Return the ``(n_frames, ny, nx)`` stack of *channel* (movie source)."""
        return np.asarray(self.data[:, self.channel_index(channel)], dtype=float)


def is_photon_stream(path) -> bool:
    """Return whether *path* is read as a photon stream rather than as an image."""
    return pathlib.Path(path).suffix.lower() in TTTR_SUFFIXES


# --- TIFF / camera images ----------------------------------------------------


def _axes_from_tifffile(path: str) -> tuple[np.ndarray, str] | None:
    """Return ``(array, axes)`` from tifffile, or ``None`` when unreadable."""
    try:
        import tifffile
    except ImportError:  # pragma: no cover - optional dependency
        return None
    try:
        with tifffile.TiffFile(str(path)) as tif:
            series = tif.series[0]
            return np.asarray(series.asarray()), str(series.axes)
    except Exception:
        return None


def _read_image_array(path: str) -> tuple[np.ndarray, str]:
    """Read an image file into ``(array, axes)``; falls back to imageio."""
    result = _axes_from_tifffile(path)
    if result is not None:
        return result
    try:
        import imageio.v2 as imageio
    except ImportError:  # pragma: no cover - optional dependency
        import imageio  # type: ignore[no-redef]
    arr = None
    for reader, kwargs in (
        (getattr(imageio, "mimread", None), {"memtest": False}),
        (getattr(imageio, "volread", None), {}),
        (imageio.imread, {}),
    ):
        if reader is None:
            continue
        try:
            arr = np.asarray(reader(str(path), **kwargs))
            break
        except Exception:
            arr = None
    if arr is None:
        raise OSError(f"Could not read image: {path}")
    # imageio gives no axis labels: label the trailing two as Y/X and treat a
    # 3-channel trailing axis as RGB samples, everything else as a leading index.
    if arr.ndim == 2:
        return arr, "YX"
    if arr.ndim == 3 and arr.shape[-1] in (3, 4):
        return arr, "YXS"
    if arr.ndim == 3:
        return arr, "QYX"
    return arr, "Q" * (arr.ndim - 2) + "YX"


def _stack_from_axes(arr: np.ndarray, axes: str, channel_axis) -> tuple[np.ndarray, dict]:
    """Reshape a labelled array to ``(frame, channel, y, x)``.

    ``axes`` is a tifffile-style label string (``"TCYX"``, ``"ZYX"``, ``"YXS"``,
    ``"Q…"`` for unlabelled). ``C``/``S`` axes become channels, ``T``/``Z``/``I``
    frames. A single unlabelled axis is ambiguous — it is taken as channels when
    it is short (≤ 4 planes, the usual two/three-colour image) and as frames
    otherwise; *channel_axis* overrides that guess.
    """
    axes = axes.upper()
    if len(axes) != arr.ndim:
        axes = "Q" * (arr.ndim - 2) + "YX"
    if "Y" not in axes or "X" not in axes:
        raise ValueError(f"image axes {axes!r} carry no Y/X plane")

    unlabelled = [i for i, a in enumerate(axes) if a in "QI"]
    channel_axes = [i for i, a in enumerate(axes) if a in "CS"]
    frame_axes = [i for i, a in enumerate(axes) if a in "TZ"]
    if channel_axis is not None:
        forced = (
            axes.index(str(channel_axis).upper())
            if isinstance(channel_axis, str)
            else int(channel_axis)
        )
        channel_axes = [forced]
        frame_axes = [i for i in range(arr.ndim) if i not in channel_axes and axes[i] not in "YX"]
        unlabelled = []
    elif not channel_axes and unlabelled:
        guess = unlabelled[0]
        if arr.shape[guess] <= 4:
            channel_axes = [guess]
            unlabelled = unlabelled[1:]
        else:
            frame_axes = frame_axes + [guess]
            unlabelled = unlabelled[1:]
    frame_axes = frame_axes + unlabelled

    y_axis = axes.index("Y")
    x_axis = axes.index("X")
    order = frame_axes + channel_axes + [y_axis, x_axis]
    moved = np.transpose(arr, order)
    n_frames = int(np.prod([arr.shape[i] for i in frame_axes])) if frame_axes else 1
    n_channels = int(np.prod([arr.shape[i] for i in channel_axes])) if channel_axes else 1
    stack = moved.reshape(n_frames, n_channels, arr.shape[y_axis], arr.shape[x_axis])
    return np.asarray(stack, dtype=np.float32), {"axes": axes}


# --- photon streams ----------------------------------------------------------


def _stack_from_tttr(path: str, channels, windows) -> tuple[np.ndarray, list[str], dict]:
    """Fill a confocal-scan image stack from a photon-stream file.

    One image channel per detector routing channel, or per named detector window
    when *windows* (``{name: {"chs": [...], "micro_time_ranges": [...]}}``) is
    given — so a PIE/micro-time-gated window is a "colour" like any other.
    """
    from .pixel_maps import build_clsm_windowed, get_tttr

    tttr = get_tttr(str(path))
    if windows:
        specs = [
            (name, list(det.get("chs", [0]) or [0]), list(det.get("micro_time_ranges") or []))
            for name, det in windows.items()
        ]
    else:
        if channels is None:
            used = [int(c) for c in np.unique(np.asarray(tttr.get_routing_channel()))]
        else:
            used = [int(c) for c in channels]
        specs = [(f"ch{c}", [c], []) for c in used]
    if not specs:
        raise ValueError(f"no detector channels found in {path}")

    planes = []
    names = []
    for name, chs, mtr in specs:
        clsm = build_clsm_windowed(tttr, chs, mtr)
        intensity = np.asarray(clsm.get_intensity(), dtype=np.float32)
        if intensity.ndim == 2:
            intensity = intensity[np.newaxis]
        planes.append(intensity)
        names.append(name)
    n_frames = min(p.shape[0] for p in planes)
    stack = np.stack([p[:n_frames] for p in planes], axis=1)
    return stack, names, {"n_photons": int(len(tttr))}


def load_image_stack(
    path,
    *,
    channels=None,
    windows=None,
    channel_axis=None,
    channel_names=None,
) -> ImageStack:
    """Load *path* into a ``(frame, channel, y, x)`` :class:`ImageStack`.

    Dispatches on the file suffix: photon streams (``.ptu``, ``.ht3``, …) are
    reconstructed into a confocal-scan image, everything else is read as a TIFF /
    camera image with the axis order the file declares.

    Parameters
    ----------
    path : str or pathlib.Path
        Image or photon-stream file.
    channels : sequence of int, optional
        Photon streams only: detector routing channels to fill (default: every
        channel present in the file).
    windows : dict, optional
        Photon streams only: named detector windows
        (``{name: {"chs": [...], "micro_time_ranges": [...]}}``) used as image
        channels instead of raw routing channels.
    channel_axis : int or str, optional
        Images only: force which array axis holds the channels, overriding the
        axis labels / the short-axis heuristic.
    channel_names : sequence of str, optional
        Override the generated channel names.

    Returns
    -------
    ImageStack
        The loaded stack.
    """
    path = str(path)
    if is_photon_stream(path):
        data, names, meta = _stack_from_tttr(path, channels, windows)
        kind = "tttr"
    else:
        arr, axes = _read_image_array(path)
        data, meta = _stack_from_axes(arr, axes, channel_axis)
        names = [f"ch{i}" for i in range(data.shape[1])]
        kind = "image"
    if channel_names:
        names = [str(n) for n in channel_names][: data.shape[1]]
        names += [f"ch{i}" for i in range(len(names), data.shape[1])]
    return ImageStack(data=data, channel_names=list(names), source=path, kind=kind, metadata=meta)
