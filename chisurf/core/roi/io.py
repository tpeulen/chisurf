"""Reading and writing regions of interest.

A region is only useful if it survives leaving the session, and if it can come
from somewhere other than ChiSurf. This module covers both:

* the **native** format — the region's own JSON, lossless for every shape
  including nested composites;
* **segmentation output** — a Cellpose ``_seg.npy`` or any integer label image,
  which becomes one region per object;
* **label images** — a round-trip through a TIFF that other tools can read.

The native format is a plain list of :meth:`~chisurf.core.roi.ROI.to_dict`
descriptions, so it is diffable and hand-editable, unlike the binary mask files
the reference implementation exports.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Iterable, List, Sequence

import numpy as np

from .roi import ROI, MaskROI, labels_to_rois, roi_from_dict, rois_to_labels, union_of

#: Marker written into native ROI files so a stray JSON is not mistaken for one.
FORMAT = "chisurf-roi"
VERSION = 1


def save_rois(rois: Iterable[ROI], path: str, metadata: dict | None = None) -> str:
    """Write regions to a native JSON file.

    Parameters
    ----------
    rois : iterable of ROI
        The regions to store.
    path : str
        Destination path.
    metadata : dict, optional
        Free-form extras stored alongside — the image the regions were drawn on,
        the analysis they belong to, and so on.

    Returns
    -------
    str
        The path written.
    """
    payload = {
        "format": FORMAT,
        "version": VERSION,
        "metadata": dict(metadata or {}),
        "rois": [r.to_dict() for r in rois],
    }
    out = pathlib.Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    return str(out)


def load_rois(path: str) -> List[ROI]:
    """Read regions from a native JSON file.

    Parameters
    ----------
    path : str
        File written by :func:`save_rois`.

    Returns
    -------
    list of ROI
        The stored regions.

    Raises
    ------
    ValueError
        If the file is not a ChiSurf ROI file.
    """
    data = json.loads(pathlib.Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a {FORMAT} file")
    if "entries" in data:
        # A file written by RegionCollection.save. Its regions must be readable
        # by every consumer that takes a plain region file, or the shared editor
        # would write something only the shared editor could open — the flags
        # and the combining rule are dropped here, and kept by
        # ``RegionCollection.load``.
        return [roi_from_dict(e["roi"]) for e in data.get("entries", [])]
    if data.get("format") != FORMAT:
        raise ValueError(f"{path} is not a {FORMAT} file")
    return [roi_from_dict(d) for d in data.get("rois", [])]


def load_roi_metadata(path: str) -> dict:
    """Return the metadata block of a native ROI file.

    Parameters
    ----------
    path : str
        File written by :func:`save_rois`.

    Returns
    -------
    dict
        The stored metadata, empty when absent.
    """
    data = json.loads(pathlib.Path(path).read_text())
    return dict(data.get("metadata", {})) if isinstance(data, dict) else {}


def rois_from_cellpose(path: str, crop: bool = True) -> List[ROI]:
    """Read a Cellpose segmentation into one region per object.

    Cellpose writes a ``*_seg.npy`` holding a pickled dictionary whose ``masks``
    entry is an integer label image — exactly what
    :func:`~chisurf.core.roi.labels_to_rois` consumes. Importing it turns a
    segmentation done in a dedicated tool into regions ChiSurf can gate,
    combine and store like any drawn one.

    Parameters
    ----------
    path : str
        Path to a ``_seg.npy`` file, or to a plain ``.npy`` holding a label
        image.
    crop : bool
        Store each region cropped to its bounding box.

    Returns
    -------
    list of ROI
        One region per label, named after its label value.

    Raises
    ------
    ValueError
        If the file holds neither a label image nor a dictionary with masks.
    """
    data = np.load(str(path), allow_pickle=True)

    labels = None
    if isinstance(data, np.ndarray) and data.dtype != object and data.ndim == 2:
        labels = data
    else:
        # A pickled dict arrives as a 0-d object array.
        item = data.item() if isinstance(data, np.ndarray) else data
        if isinstance(item, dict):
            for key in ("masks", "mask", "labels"):
                if key in item:
                    labels = np.asarray(item[key])
                    break

    if labels is None:
        raise ValueError(
            f"{path} holds no label image; expected a 2-D array or a dict with 'masks'"
        )
    if labels.ndim != 2:
        raise ValueError(f"the label image in {path} is {labels.ndim}-D, expected 2-D")
    return labels_to_rois(labels.astype(int), crop=crop)


def rois_from_label_image(path: str, crop: bool = True) -> List[ROI]:
    """Read an integer label image (TIFF or NumPy) into regions.

    Parameters
    ----------
    path : str
        Path to a label image.
    crop : bool
        Store each region cropped to its bounding box.

    Returns
    -------
    list of ROI
        One region per non-zero label.
    """
    p = pathlib.Path(path)
    if p.suffix.lower() in (".npy",):
        labels = np.load(str(p))
    else:
        import tifffile

        labels = np.asarray(tifffile.imread(str(p)))
    if labels.ndim != 2:
        raise ValueError(f"expected a 2-D label image; got shape {labels.shape}")
    return labels_to_rois(labels.astype(int), crop=crop)


def load_regions(path: str, crop: bool = True) -> List[ROI]:
    """Read regions from a file of any supported kind.

    The one entry point every consumer should use: it picks the reader from the
    file itself rather than making each caller re-implement the dispatch — and
    getting that dispatch subtly wrong is easy. A label image sent to the mask
    reader, for instance, comes back as *one* merged region instead of one per
    object, silently, because a label image is also a valid mask.

    Parameters
    ----------
    path : str
        A native ``.json`` region file, a Cellpose ``_seg.npy``, or an image
        (TIFF / ``.npy``) holding either a label image or a binary mask.
    crop : bool
        Store each region from a segmentation cropped to its bounding box.

    Returns
    -------
    list of ROI
        The regions in the file: several for a segmentation or a multi-region
        JSON, one for a binary mask.

    Raises
    ------
    ValueError
        If the file cannot be read as any of those.
    """
    p = pathlib.Path(path)
    suffix = p.suffix.lower()
    if suffix == ".json":
        return load_rois(str(p))
    if p.name.lower().endswith("_seg.npy"):
        return rois_from_cellpose(str(p), crop=crop)

    if suffix == ".npy":
        arr = np.asarray(np.load(str(p)))
    else:
        import tifffile

        arr = np.asarray(tifffile.imread(str(p)))
    if arr.ndim != 2:
        raise ValueError(f"expected a 2-D image; got shape {arr.shape}")

    # An integer image carrying more than one object is a labelling, not a
    # mask: reading it as a mask would merge every object into one region.
    if np.issubdtype(arr.dtype, np.integer) and len(np.unique(arr[arr != 0])) > 1:
        return labels_to_rois(arr.astype(int), crop=crop)
    return [MaskROI(arr != 0, name=p.stem)]


def load_region(path: str, crop: bool = True) -> ROI:
    """Read a file as a single region, combining several into their union.

    For callers that gate with one region — an analysis confined to "the cells",
    not to each cell in turn.

    Parameters
    ----------
    path : str
        As for :func:`load_regions`.
    crop : bool
        As for :func:`load_regions`.

    Returns
    -------
    ROI
        The single region, or the union of all of them.

    Raises
    ------
    ValueError
        If the file holds no region.
    """
    regions = load_regions(path, crop=crop)
    if not regions:
        raise ValueError(f"no region in {path}")
    return union_of(regions)


def save_label_image(
    rois: Sequence[ROI],
    shape: Sequence[int],
    path: str,
    extent: Any = None,
    image: np.ndarray | None = None,
) -> str:
    """Rasterise regions into a label image and write it.

    The interchange direction: other tools read a label TIFF even when they know
    nothing about ChiSurf's own format.

    Parameters
    ----------
    rois : sequence of ROI
        Regions to draw; the first gets label 1. Later regions overwrite
        earlier ones where they overlap.
    shape : sequence of int
        Output shape ``(ny, nx)``.
    path : str
        Destination path (``.npy`` or a TIFF).
    extent : tuple, optional
        Value span, for regions defined on value axes.
    image : numpy.ndarray, optional
        Image for any intensity-dependent regions.

    Returns
    -------
    str
        The path written.
    """
    labels = rois_to_labels(rois, shape, extent=extent, image=image)
    out = pathlib.Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".npy":
        np.save(str(out), labels)
    else:
        import tifffile

        tifffile.imwrite(str(out), labels.astype(np.uint16))
    return str(out)


def roi_from_mask_file(path: str, name: str = "") -> MaskROI:
    """Read a binary mask image as a single region.

    The shape the reference implementation exports: one boolean mask over the
    frame, with no per-object labelling.

    Parameters
    ----------
    path : str
        Path to a mask image (``.npy`` or a TIFF); any non-zero pixel is inside.
    name : str
        Label for the region.

    Returns
    -------
    MaskROI
        The region.
    """
    p = pathlib.Path(path)
    if p.suffix.lower() == ".npy":
        arr = np.load(str(p))
    else:
        import tifffile

        arr = np.asarray(tifffile.imread(str(p)))
    if arr.ndim != 2:
        raise ValueError(f"expected a 2-D mask; got shape {arr.shape}")
    return MaskROI(arr != 0, name=name or p.stem)
