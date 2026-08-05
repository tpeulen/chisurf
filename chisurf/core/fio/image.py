"""One seam for reading and writing image files (TIFF stacks and friends).

Every image analysis in the tree -- colocalization, drift, FRC, flow, PSF
determination, ROI masks, ICS carpets -- starts by turning a file on disk into a
NumPy array, and each of them used to reach for whichever of ``tifffile``,
``imageio`` or Pillow the author happened to know. That is three ways to answer
the same question, three sets of quirks, and three dependencies for a job the
TTTR library already does with a bundled libtiff.

This module is that single answer:

* :func:`imread` / :func:`imwrite` for the common case -- an array in, an array
  out, dtype preserved.
* :func:`read_labelled` when the *meaning* of the axes matters, returning the
  array together with a label string (``"TCYX"``, ``"ZYX"``, ``"I"`` for an
  unlabelled page index).

Everything goes through the TTTR library's bundled libtiff, which also carries
ImageJ hyperstack metadata, so a ``(frame, channel, y, x)`` stack survives a
round-trip with its axes intact.

**TIFF is the only format, in both directions.** Measurement images are TIFF:
it stores the integer and floating-point pixel types instruments actually
produce, at full depth, losslessly, with the axis and voxel-size metadata that
makes a stack interpretable. The consumer formats store 8-bit colour, and
writing a 16-bit photon count or a float lifetime map into one silently
discards the measurement -- so this module will not do it, and an image that is
not a TIFF raises rather than being read through a second reader with different
conventions.

Notes
-----
A TIFF is a flat sequence of pages, so the page count alone cannot say whether
six pages are six frames or two frames in three colours. Only ImageJ metadata
carries that; a file without it reports its pages as the unlabelled ``"I"`` axis
and the caller decides what they mean.
"""

from __future__ import annotations

import pathlib

import numpy as np

__all__ = ["TIFF_SUFFIXES", "imread", "imwrite", "metadata", "read_labelled"]

#: Suffixes this module reads and writes. TIFF and its instrument dialects only.
TIFF_SUFFIXES = frozenset({".tif", ".tiff", ".ome.tif", ".ome.tiff", ".lsm", ".stk"})


def _check_suffix(path) -> None:
    """Raise unless *path* names a TIFF.

    Refusing early gives a better error than libtiff's, and keeps the reason
    visible: a measurement image is a TIFF, and a PNG or JPEG in this position
    means data has already been flattened to 8-bit colour somewhere upstream.
    """
    name = pathlib.Path(path).name.lower()
    if not any(name.endswith(suffix) for suffix in TIFF_SUFFIXES):
        raise ValueError(
            f"{path}: images are read and written as TIFF only "
            f"(expected one of {', '.join(sorted(TIFF_SUFFIXES))}). The consumer "
            f"formats store 8-bit colour and would discard the measurement."
        )


def read_labelled(path) -> tuple[np.ndarray, str]:
    """Read an image file into an array and a label per axis.

    Parameters
    ----------
    path : str or os.PathLike
        Image file to read.

    Returns
    -------
    numpy.ndarray
        The image data, in the file's own dtype.
    str
        One label per dimension: ``T`` frames, ``Z`` slices, ``C`` channels,
        ``I`` an unlabelled page index, and ``Y``/``X`` the image plane. A TIFF
        without ImageJ metadata reports its pages as ``I`` -- the file does not
        say what they are.

    Raises
    ------
    ValueError
        If *path* is not a TIFF.
    OSError
        If the file cannot be read.
    """
    import tttrlib

    _check_suffix(path)
    try:
        return tttrlib.imread(path), str(tttrlib.tiff_metadata(path)["axes"])
    except Exception as error:
        raise OSError(f"could not read image: {path}: {error}") from error


def metadata(path) -> dict:
    """Describe a TIFF file without decoding its pixels.

    Parameters
    ----------
    path : str or os.PathLike
        TIFF file to inspect.

    Returns
    -------
    dict
        ``axes``, ``shape``, ``dtype``, the raw ``description`` tag,
        ``resolution`` as an ``(x, y)`` pair in pixels per unit (``None`` when
        the file carries none) and ``imagej``, the description parsed into
        fields (empty for a file ImageJ did not label).
    """
    import tttrlib

    return dict(tttrlib.tiff_metadata(path))


def imread(path) -> np.ndarray:
    """Read an image file into a NumPy array, preserving its dtype.

    A single-page file gives a 2-D ``(y, x)`` array; a multi-page file gives
    ``(pages, y, x)``; an ImageJ hyperstack keeps the dimensions its metadata
    declares. Use :func:`read_labelled` when you need to know which axis is
    which.

    Parameters
    ----------
    path : str or os.PathLike
        Image file to read.

    Returns
    -------
    numpy.ndarray
        The image data.
    """
    return read_labelled(path)[0]


def imwrite(
    path,
    data,
    *,
    axes: str | None = None,
    compression: str = "lzw",
    resolution: tuple[float, float] | None = None,
    metadata: dict | None = None,
) -> None:
    """Write an array to a TIFF file.

    Parameters
    ----------
    path : str or os.PathLike
        Destination file.
    data : array_like
        2-D image or N-D stack. The dtype selects the on-disk pixel type;
        dtypes TIFF cannot store are promoted to the nearest lossless one.
    axes : str, optional
        Label per dimension, ending in ``"YX"`` and using ``T`` for frames,
        ``Z`` for slices and ``C`` for channels -- for example ``"TCYX"``. This
        is stored as ImageJ hyperstack metadata, which is the only thing that
        lets :func:`read_labelled` tell frames from channels afterwards, and it
        is what makes the file open as a hyperstack in ImageJ/Fiji. Without it,
        an array of more than three dimensions is labelled from the trailing end
        of ``"TZCYX"``.
    compression : str, optional
        ``"none"``, ``"lzw"`` (default), ``"packbits"`` or ``"deflate"``.
    resolution : tuple of float, optional
        ``(x, y)`` in *pixels per unit* -- the reciprocal of the pixel size.
    metadata : dict, optional
        Further ImageJ fields. ``{"spacing": z_step, "unit": "um"}`` alongside
        *resolution* is what gives a stack a physical voxel size; ImageJ needs
        both halves and ignores either one on its own.

    Raises
    ------
    ValueError
        If *path* is not a TIFF.
    """
    import tttrlib

    _check_suffix(path)
    tttrlib.imwrite(
        path,
        np.asarray(data),
        compression=compression,
        axes=axes,
        resolution=resolution,
        metadata=metadata,
    )
