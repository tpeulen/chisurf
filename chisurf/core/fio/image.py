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
  array together with a label string (``"TCYX"``, ``"ZYX"``, ``"YXS"``, ``"I"``
  for an unlabelled page index).

TIFF goes through the TTTR library's bundled libtiff, which also carries ImageJ
hyperstack metadata, so a ``(frame, channel, y, x)`` stack survives a round-trip
with its axes intact. Anything else -- PNG, JPEG, and the RGB TIFFs the array
reader declines because they pack several samples into one page -- falls back to
Pillow.

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

#: Suffixes read through the TTTR library's array TIFF reader.
TIFF_SUFFIXES = frozenset({".tif", ".tiff", ".ome.tif", ".ome.tiff", ".lsm", ".stk"})


def _is_tiff(path) -> bool:
    """Return whether *path* names a file to try the array TIFF reader on."""
    name = pathlib.Path(path).name.lower()
    return any(name.endswith(suffix) for suffix in TIFF_SUFFIXES)


def _read_pillow(path) -> tuple[np.ndarray, str]:
    """Read *path* with Pillow, returning ``(array, axes)``.

    Covers what the array TIFF reader does not: single-file formats such as PNG
    and JPEG, and TIFFs whose pages carry several samples per pixel (RGB), which
    it rejects rather than silently flattening.
    """
    from PIL import Image, ImageSequence

    with Image.open(str(path)) as handle:
        frames = [np.asarray(frame) for frame in ImageSequence.Iterator(handle)]
    if not frames:
        raise OSError(f"no frames could be read from {path}")
    if len(frames) == 1:
        plane = frames[0]
        # A trailing 3/4-sized axis on a single plane is RGB(A) samples, not a
        # third spatial dimension.
        return plane, "YXS" if plane.ndim == 3 else "YX"
    stack = np.asarray(frames)
    return stack, "IYXS" if stack.ndim == 4 else "IYX"


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
        ``S`` colour samples, ``I`` an unlabelled page index, and ``Y``/``X``
        the image plane. A TIFF without ImageJ metadata reports its pages as
        ``I`` -- the file does not say what they are.

    Raises
    ------
    OSError
        If the file cannot be read by either reader.
    """
    if _is_tiff(path):
        try:
            import tttrlib

            metadata = tttrlib.tiff_metadata(path)
            return tttrlib.imread(path), str(metadata["axes"])
        except Exception:
            # Multi-sample (RGB) pages and exotic codecs are Pillow's job.
            pass
    try:
        return _read_pillow(path)
    except OSError:
        raise
    except Exception as error:
        raise OSError(f"could not read image: {path}") from error


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

    A single-page file gives a 2-D ``(y, x)`` array (or ``(y, x, samples)`` for
    RGB); a multi-page file gives ``(pages, y, x)``; an ImageJ hyperstack keeps
    the dimensions its metadata declares. Use :func:`read_labelled` when you
    need to know which axis is which.

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
    """
    import tttrlib

    tttrlib.imwrite(
        path,
        np.asarray(data),
        compression=compression,
        axes=axes,
        resolution=resolution,
        metadata=metadata,
    )
