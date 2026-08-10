"""Detected regions, written into the measurement's own container.

A segmentation is two things, and only one of them is a table. The measurements
— area, centroid, eccentricity — are one row per region and belong in a store.
Which *pixels* each region owns is a raster, and it is the half that decides
whether the regions can be analysed later at all: an analysis that reads photons
out of a region reaches them through the pixel list, so a table of scalars is a
table a person can read and a machine cannot fit.

So a detection is written as a **pair** — an ``image_data`` label raster and a
``region_table`` measuring it — joined by the ``label`` column, which is the
raster's own pixel value. The two are written and read together; a table whose
raster is missing is a table of measurements, and this module refuses to
pretend otherwise.

The row rule is the one the burst companions learned the expensive way
(:mod:`chisurf.core.fio.fluorescence.burst_companion`): **one row per detected
region, always**, including regions a later analysis skips. A skipped region is
a sentinel row, never a missing row, because the alternative fails silently —
a shorter table still merges, one region's numbers landing on another's.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

__all__ = [
    "REGION_COLUMN_UNITS",
    "RegionSet",
    "list_region_sets",
    "read_regions",
    "region_table",
    "write_regions",
]

#: Artifact vocabulary. `row_grain` is what makes the join resolvable: a fit
#: table at `region` grain joins this one by `label`, not by position.
ARTIFACT_KIND = "region_table"
RASTER_KIND = "image_data"
OPERATION_TYPE = "region_detection"
ROW_GRAIN = "region"

#: The suffixes the pair is named with, under one caller-chosen stem.
TABLE_SUFFIX = "regions"
RASTER_SUFFIX = "labels"

#: Units of the columns :func:`region_table` writes. Pixels are the unit a
#: detection is measured in — a conversion to length belongs at the boundary
#: where the pixel size is known, not in the file.
REGION_COLUMN_UNITS: dict[str, str] = {
    "region.area": "pixels",
    "region.area_convex": "pixels",
    "region.area_filled": "pixels",
    "region.perimeter": "pixels",
    "region.axis_major_length": "pixels",
    "region.axis_minor_length": "pixels",
    "region.equivalent_diameter": "pixels",
    "region.feret_diameter_max": "pixels",
    "region.orientation": "radians",
}

#: ``(column, attribute)`` of every measurement written, in order. Namespaced by
#: origin so a fit table can be written into the same container without a
#: collision, and so a reader can tell which stage produced a column.
_SCALAR_COLUMNS: tuple[tuple[str, str], ...] = (
    ("region.area", "area"),
    ("region.area_convex", "area_convex"),
    ("region.area_filled", "area_filled"),
    ("region.perimeter", "perimeter"),
    ("region.circularity", "circularity"),
    ("region.eccentricity", "eccentricity"),
    ("region.solidity", "solidity"),
    ("region.extent", "extent"),
    ("region.axis_major_length", "axis_major_length"),
    ("region.axis_minor_length", "axis_minor_length"),
    ("region.equivalent_diameter", "equivalent_diameter_area"),
    ("region.orientation", "orientation"),
    ("region.euler_number", "euler_number"),
)

_INTENSITY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("region.intensity_sum", "intensity_sum"),
    ("region.intensity_mean", "intensity_mean"),
    ("region.intensity_min", "intensity_min"),
    ("region.intensity_max", "intensity_max"),
    ("region.intensity_std", "intensity_std"),
)


@dataclasses.dataclass
class RegionSet:
    """One detection: a label raster and the table measuring it.

    Parameters
    ----------
    labels : numpy.ndarray
        ``(y, x)`` integer label image. ``0`` is background; region labels are
        contiguous from ``1``, which :func:`write_regions` enforces.
    table : tttrlib.DataStore
        One row per region, ``label`` first, in label order.
    name : str
        Stem the pair was written under.
    source : str
        Path of the container it came from, when it was read from one.
    """

    labels: np.ndarray
    table: Any
    name: str = "spots"
    source: str = ""

    @property
    def n_regions(self) -> int:
        """Number of regions — rows in the table, which is also ``labels.max()``."""
        from chisurf.core.datastore import row_count

        return int(row_count(self.table))

    def properties(self, intensity=None) -> list:
        """Re-measure the regions, optionally against an intensity image.

        The table carries the scalars a detection is judged on; this gives the
        full :class:`~chisurf.core.roi.RegionProperties` set (moments, hull,
        pixel coordinates) that an analysis needs and a file should not carry.

        Parameters
        ----------
        intensity : numpy.ndarray, optional
            Image to weight the measurements by.

        Returns
        -------
        list of chisurf.core.roi.RegionProperties
        """
        from chisurf.core.roi import regionprops

        return regionprops(self.labels, intensity)

    def rois(self) -> list:
        """Return each region as a :class:`~chisurf.core.roi.MaskROI`."""
        return [prop.to_roi() for prop in self.properties()]

    def mask(self) -> np.ndarray:
        """Return the foreground mask — every pixel owned by some region."""
        return np.asarray(self.labels) > 0


def region_table(
    labels,
    intensity=None,
    *,
    frame: int = 0,
    extra: Mapping[str, Any] | None = None,
) -> Any:
    """Measure *labels* into the table half of the contract.

    Parameters
    ----------
    labels : numpy.ndarray
        Label image. Assumed contiguous from 1 — :func:`write_regions` relabels
        before calling this, and a caller that does not will write a row for a
        label that owns no pixel.
    intensity : numpy.ndarray, optional
        Image the intensity columns are measured against. Without it those
        columns are absent rather than zero, because a detection made on a mask
        has no brightness and should not claim one.
    frame : int, optional
        Frame the regions were detected in. ``0`` for a projected field. One
        column now is what stops a per-frame detector needing a second format.
    extra : mapping, optional
        Detector-specific columns, ``{name: sequence}``, one value per region.
        Namespace them (``spot.sigma_x``) — the table is merged with others.

    Returns
    -------
    tttrlib.DataStore
        One row per region, ``label`` first, in label order.
    """
    from chisurf.core.datastore import store_from_arrays, take_columns
    from chisurf.core.roi import regionprops

    props = regionprops(labels, intensity)
    n = len(props)

    columns: dict[str, np.ndarray] = {
        "label": np.asarray([int(p.label) for p in props], dtype=np.int64),
        "frame": np.full(n, int(frame), dtype=np.int64),
    }
    centroids = np.asarray([p.centroid for p in props], dtype=float).reshape(n, 2)
    columns["region.centroid_y"] = centroids[:, 0]
    columns["region.centroid_x"] = centroids[:, 1]
    if intensity is not None:
        # The unweighted centroid is the shape's centre and the weighted one is
        # where the molecule is. Both are written because a consumer that picks
        # the wrong one is wrong by a sub-pixel amount that nothing catches.
        weighted = np.asarray(
            [p.centroid_weighted for p in props], dtype=float
        ).reshape(n, 2)
        columns["region.centroid_weighted_y"] = weighted[:, 0]
        columns["region.centroid_weighted_x"] = weighted[:, 1]

    boxes = np.asarray([p.bbox for p in props], dtype=np.int64).reshape(n, 4)
    for i, edge in enumerate(("min_row", "min_col", "max_row", "max_col")):
        columns[f"region.bbox_{edge}"] = boxes[:, i]

    wanted = list(_SCALAR_COLUMNS)
    if intensity is not None:
        wanted += list(_INTENSITY_COLUMNS)
    for column, attribute in wanted:
        columns[column] = np.asarray(
            [float(getattr(p, attribute)) for p in props], dtype=float
        )

    for name, values in (extra or {}).items():
        values = np.asarray(values)
        if values.shape[0] != n:
            raise ValueError(
                f"extra column {name!r} has {values.shape[0]} values for "
                f"{n} regions — one row per region, always"
            )
        columns[str(name)] = values

    order = ["label", "frame", *[c for c in columns if c not in ("label", "frame")]]
    return take_columns(store_from_arrays(columns), order)


def write_regions(
    source: str | Path,
    labels,
    intensity=None,
    *,
    name: str = "spots",
    frame: int = 0,
    extra: Mapping[str, Any] | None = None,
    table: Any = None,
    parameters: Mapping[str, Any] | None = None,
    operation_type: str = OPERATION_TYPE,
    derived_from: str | Sequence[str] = (),
    out_dir: str | Path | None = None,
) -> str:
    """Write a detection into the measurement's container, as a pair.

    The raster goes first and the table names it as its parent, so the lineage
    reads *photons → labels → regions* and a reader that finds the table can
    always find the pixels.

    The labels are made contiguous from 1 on the way in. Deleting labels — which
    every filtering step does — leaves gaps, and every consumer that reads a
    label image as "1 to max" then reports regions owning no pixel. Doing it
    here means the *file* cannot carry that bug, whoever wrote the segmentation.

    Parameters
    ----------
    source : str or Path
        The image or photon file the regions were found in, or the container.
    labels : numpy.ndarray
        Label image, ``0`` background.
    intensity : numpy.ndarray, optional
        Image the intensity columns are measured against.
    name : str, optional
        Stem for the pair — ``<name>.labels`` and ``<name>.regions``.
    frame, extra
        Passed to :func:`region_table`.
    table : tttrlib.DataStore, optional
        A table to write instead of measuring one. It must already satisfy the
        contract (one row per region, ``label`` first); use this when the
        detector has measurements of its own to add and has already built it.
    parameters : mapping, optional
        Detection settings. Their hash is the identity of the run, so re-running
        with the same settings replaces rather than accumulates.
    operation_type : str, optional
        An ``_mmfdb_operation.operation_type`` term.
    derived_from : str or sequence of str, optional
        Objects the raster was computed from. Empty means the primary data.
    out_dir : str or Path, optional
        Directory the container lives in. Defaults to beside *source*.

    Returns
    -------
    str
        Path of the container written.
    """
    from chisurf.core.fio.fluorescence.imaging_container import (
        write_image,
        write_imaging_table,
    )
    from chisurf.core.roi.segmentation import relabel_sequential

    labels = np.ascontiguousarray(np.asarray(labels))
    if labels.ndim != 2:
        raise ValueError(f"labels must be a 2-D label image, got shape {labels.shape}")
    labels, _forward, _inverse = relabel_sequential(labels)
    labels = labels.astype(np.int32, copy=False)

    if table is None:
        table = region_table(labels, intensity, frame=frame, extra=extra)

    raster_name = f"{name}.{RASTER_SUFFIX}"
    table_name = f"{name}.{TABLE_SUFFIX}"

    write_image(
        source,
        labels,
        name=raster_name,
        artifact_kind=RASTER_KIND,
        operation_type=operation_type,
        axes="YX",
        parameters=parameters,
        derived_from=derived_from,
        out_dir=out_dir,
    )
    # The table's parent is the raster, and the two join on `label`. Position is
    # still the fallback for a reader that ignores the key, which is why the
    # row rule holds regardless.
    return write_imaging_table(
        source,
        table,
        name=table_name,
        artifact_kind=ARTIFACT_KIND,
        operation_type=operation_type,
        row_grain=ROW_GRAIN,
        parameters=parameters,
        derived_from=(raster_name,),
        source_row_column="label",
        target_row_column="label",
        units=REGION_COLUMN_UNITS,
        out_dir=out_dir,
    )


def read_regions(source: str | Path, *, name: str = "spots") -> RegionSet:
    """Read back a detection written by :func:`write_regions`.

    Parameters
    ----------
    source : str or Path
        The container, or any file beside it that resolves to one.
    name : str, optional
        Stem the pair was written under.

    Returns
    -------
    RegionSet

    Raises
    ------
    FileNotFoundError
        If either half is missing — naming which, and listing the detections the
        container does hold, because "not found" without a listing is the
        unhelpful half of an error. A table without its raster is refused
        rather than returned: it cannot be analysed, and a caller that got one
        would discover that much later.
    """
    from chisurf.core.fio.fluorescence.burst_container import container_for
    from chisurf.core.fio.fluorescence.imaging_container import read_image
    from chisurf.core.fio.pto import Measurement

    container = container_for(source)
    if not Path(container).exists():
        raise FileNotFoundError(f"{source} resolves to no container ({container})")

    raster_name = f"{name}.{RASTER_SUFFIX}"
    table_name = f"{name}.{TABLE_SUFFIX}"

    with Measurement.open(container, writable=False) as measurement:
        present = {obj.name for obj in measurement.artifacts()}
        missing = [n for n in (raster_name, table_name) if n not in present]
        if missing:
            available = list_region_sets(container) or ["(none)"]
            raise FileNotFoundError(
                f"{Path(container).name} holds no detection named {name!r} "
                f"(missing {', '.join(missing)}); it holds: "
                + ", ".join(available)
            )
        table = measurement.get_store(table_name)

    labels = read_image(container, name=raster_name)
    return RegionSet(
        labels=np.asarray(labels),
        table=table,
        name=name,
        source=str(container),
    )


def list_region_sets(source: str | Path) -> list[str]:
    """Return the stems of every *complete* detection in the container.

    Complete means both halves are there. A stem whose raster was written and
    whose table was not is not a detection anything can use, and listing it
    would only move the failure later.

    Parameters
    ----------
    source : str or Path
        The container, or any file beside it that resolves to one.

    Returns
    -------
    list of str
    """
    from chisurf.core.fio.fluorescence.burst_container import container_for
    from chisurf.core.fio.pto import Measurement

    container = container_for(source)
    if not Path(container).exists():
        return []

    with Measurement.open(container, writable=False) as measurement:
        names = {obj.name for obj in measurement.artifacts()}

    rasters = {n[: -len(RASTER_SUFFIX) - 1] for n in names if n.endswith(f".{RASTER_SUFFIX}")}
    tables = {n[: -len(TABLE_SUFFIX) - 1] for n in names if n.endswith(f".{TABLE_SUFFIX}")}
    return sorted(rasters & tables)
