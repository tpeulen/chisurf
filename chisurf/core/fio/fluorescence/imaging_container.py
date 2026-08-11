"""Imaging results, written into the measurement's own container.

`<source>.imaging.h5` holds exactly one thing — a per-pixel table — so every
imaging result that is *not* one row per pixel had to become a file of its own
beside it: a `.corrected.tif` stack, a `_drift.csv` trajectory, an `_frc.csv`
curve, a `_intensity.tif` raster, a molecule `.tsv`. Five shapes, five
conventions, related to the measurement only by a filename prefix.

None of that is a missing feature of HDF5; it is a missing *statement*. A table
that cannot say what one of its rows is can only ever hold one grain, and the
grain it chose was the pixel.

Here each result says its grain and goes in the same file: a flow field is a
table at `pixel` grain, a drift trajectory at `frame`, a resolution curve at
`curve_point`, a track table at `track`, a molecule table at `molecule`. A
raster stays a TIFF and travels as cargo, because a scientific raster is worth
keeping in a format every other tool reads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = ["write_image", "write_imaging_table"]


def write_imaging_table(
    source: str | Path,
    table,
    *,
    name: str,
    artifact_kind: str,
    operation_type: str,
    row_grain: str,
    parameters: Mapping[str, Any] | None = None,
    derived_from: str | Sequence[str] = (),
    source_row_column: str = "",
    target_row_column: str = "",
    units: Mapping[str, str] | None = None,
    out_dir: str | Path | None = None,
) -> str:
    """Write one imaging result into the measurement's container.

    A thin naming layer over the shared burst writer — same seam, same
    replacement-on-re-run behaviour — so that an imaging plugin does not have to
    import something called ``burst_container`` to write a flow field.

    Parameters
    ----------
    source : str or Path
        The image or photon file, or the container itself.
    table : tttrlib.DataStore, pandas.DataFrame or mapping of str to array
        The result.
    name : str
        Label for the object. Must be distinct from the other objects this run
        writes: the identity of a result is (operation, kind, settings, name),
        and two results sharing all four replace each other.
    artifact_kind : str
        An ``_mmfdb_artifact.artifact_kind`` term.
    operation_type : str
        An ``_mmfdb_operation.operation_type`` term.
    row_grain : str
        An ``_mmfdb_artifact.row_grain`` term — what one row *is*.
    parameters : mapping, optional
        Settings. Their hash is the identity of the run.
    derived_from : str or sequence of str, optional
        Names of the objects this was computed from.
    source_row_column, target_row_column : str, optional
        The columns the parent and this table join on.
    units : mapping, optional
        ``{column: unit}``.
    out_dir : str or Path, optional

    Returns
    -------
    str
        Path of the container written.
    """
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact

    return write_burst_artifact(
        source, table,
        name=name,
        artifact_kind=artifact_kind,
        operation_type=operation_type,
        row_grain=row_grain,
        parameters=parameters,
        derived_from=derived_from,
        source_row_column=source_row_column,
        target_row_column=target_row_column,
        units=units,
        out_dir=out_dir,
    )


def write_image(
    source: str | Path,
    array,
    *,
    name: str,
    artifact_kind: str = "image_data",
    operation_type: str = "image_analysis",
    axes: str = "",
    parameters: Mapping[str, Any] | None = None,
    derived_from: str | Sequence[str] = (),
    out_dir: str | Path | None = None,
) -> str:
    """Write a raster into the measurement's container, as a TIFF.

    The raster stays a TIFF rather than becoming columns. A drift-corrected
    movie is worth keeping in a format every other tool opens, and a store is a
    2-D columnar table — an ``(t, c, y, x)`` stack has no shape in it. So the
    container carries the encoded bytes as cargo and says what they are.

    The axes are labelled on the way in, because a stack read back without them
    is guessed into channels whenever it has four frames or fewer — the trap
    :func:`chisurf.core.fio.image.imwrite` exists to close.

    Parameters
    ----------
    source : str or Path
        The image or photon file, or the container itself.
    array : numpy.ndarray
        The raster. ``(y, x)``, ``(t, y, x)`` or ``(t, c, y, x)``.
    name : str
        Label for the object.
    artifact_kind : str, optional
        An ``_mmfdb_artifact.artifact_kind`` term.
    operation_type : str, optional
        An ``_mmfdb_operation.operation_type`` term.
    axes : str, optional
        Axis labels, e.g. ``"TCYX"``. Derived from the array's rank when absent.
    parameters : mapping, optional
        Settings. Their hash is the identity of the run.
    derived_from : str or sequence of str, optional
        Names of the objects this was computed from.
    out_dir : str or Path, optional

    Returns
    -------
    str
        Path of the container written.
    """
    import tempfile

    import numpy as np

    from chisurf.core.fio.fluorescence.burst_container import open_measurement
    from chisurf.core.fio.image import imwrite

    data = np.asarray(array)
    if not axes:
        axes = {2: "YX", 3: "TYX", 4: "TCYX"}.get(data.ndim, "")

    # Encoded through the shared image seam rather than by hand: it is what
    # keeps a scientific raster out of 8-bit, and it is where the axis labels
    # are written. A temporary file because the encoder writes to a path.
    with tempfile.TemporaryDirectory() as scratch:
        staged = Path(scratch) / f"{name}.tif"
        if axes:
            imwrite(staged, data, axes=axes)
        else:
            imwrite(staged, data)
        payload = staged.read_bytes()

    wanted = [derived_from] if isinstance(derived_from, str) else list(derived_from)
    with open_measurement(source, out_dir) as m:
        parents = [uid for uid in (m._f.find(label) for label in wanted) if uid]
        m.put_blob(
            name, payload,
            artifact_kind=artifact_kind,
            data_format="tiff",
            operation_type=operation_type,
            parameters=parameters,
            derived_from=parents or m.instrument_uid,
            mime_type="image/tiff",
        )
        return str(m.path)
