"""Input/output helpers for the Burst Selection API."""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from pathlib import Path

import pandas as pd
import tttrlib

from chisurf.core.fio.fluorescence.burst import (
    read_bur_file,
    write_burst_hdf5,
    write_dataframe_to_bur,
)


def load_tttr(
    path: str | Path,
    filetype: str | None = None,
    *,
    channel_luts: dict | None = None,
    channel_shifts: dict | None = None,
    apply_lut: bool = False,
) -> tttrlib.TTTR:
    """Load a TTTR file, applying the associated setup's LUT/shift when given.

    Routes through :func:`chisurf.core.fio.staging.open_tttr` so that, when the
    caller passes the selected detector-setup's per-routing-channel LUTs/shifts
    (typically via :func:`chisurf.core.data_io.detector_setups.setup_lut_open_kwargs`),
    the burst read is LUT-aware. With no correction it is equivalent to a plain
    ``tttrlib.TTTR`` open.

    Parameters
    ----------
    path : str or Path
        TTTR file path.
    filetype : str, optional
        Explicit TTTR file type passed to ``tttrlib``.
    channel_luts : dict, optional
        ``{routing_channel: NTAC_fract}`` TAC-linearization LUTs (applied only
        when *apply_lut* is set).
    channel_shifts : dict, optional
        ``{routing_channel: int}`` photon-level wrapping micro-time shifts.
    apply_lut : bool
        Master gate for LUT linearization.

    Returns
    -------
    tttrlib.TTTR
        Loaded (and, when requested, LUT-corrected) TTTR object.
    """
    from chisurf.core.fio.staging import open_tttr

    return open_tttr(
        str(path),
        filetype or None,
        channel_luts=channel_luts,
        channel_shifts=channel_shifts,
        apply_lut=apply_lut,
    )


def read_bur(path: str | Path) -> pd.DataFrame:
    """Read a ChiSurf ``.bur`` file into a pandas DataFrame.

    Parameters
    ----------
    path : str or Path
        Path to the ``.bur`` file.

    Returns
    -------
    pandas.DataFrame
        Burst summary table.
    """
    return read_bur_file(path)


def write_bur(df: pd.DataFrame, path: str | Path) -> None:
    """Write a burst summary DataFrame as a ChiSurf ``.bur`` file.

    Parameters
    ----------
    df : pandas.DataFrame
        Burst summary table.
    path : str or Path
        Output path.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_dataframe_to_bur(df, target)


def deinterleave_bursts(df: pd.DataFrame) -> pd.DataFrame:
    """Return the real bursts from a frame carrying the ``.bur`` interleave.

    The legacy format writes ``2N+1`` physical rows — a zero row, a burst, a
    zero row, … — because it is merged with its companions **by position** and
    needs a fixed grid to count against. That is a property of the file, and it
    has leaked into the in-memory frame: the blank trailing column exists only
    to produce the trailing tab the header needs.

    Neither belongs in a container, where relations are declared keys rather
    than row positions, so a skipped burst is an absent row and a placeholder
    would destroy that information. See [the profile](/specs/pto-mfdb.md).

    The layout is documented rather than guessed at: data on odd indices, an odd
    total row count. A frame that does not look interleaved is returned as it
    is, so this is safe to call on anything.

    Parameters
    ----------
    df : pandas.DataFrame
        Burst summary table, interleaved or not.

    Returns
    -------
    pandas.DataFrame
        One row per burst, with any unnamed column dropped and the index reset.
    """
    out = df
    interleaved = len(out) >= 3 and len(out) % 2 == 1
    if interleaved:
        numeric = out.select_dtypes(include="number")
        if not numeric.empty and (numeric.iloc[0::2] == 0).all().all():
            out = out.iloc[1::2]
    blank = [c for c in out.columns if not str(c).strip()]
    if blank:
        out = out.drop(columns=blank)
    return out.reset_index(drop=True)


def write_container(
    source: str | Path,
    df: pd.DataFrame,
    *,
    parameters: dict | None = None,
    out_dir: str | Path | None = None,
) -> str:
    """Write the burst table into the measurement's own container.

    One measurement is one file: the instrument data stays where it is, and the
    bursts found in it become an artifact beside it rather than a `.bur` in a
    directory whose name encodes the parameters. Re-running with the same
    settings replaces that artifact in place; changing a setting adds one. See
    [the profile](/specs/pto-mfdb.md).

    Parameters
    ----------
    source : str or Path
        The instrument file the bursts were found in.
    df : pandas.DataFrame
        Burst summary table, one row per burst.
    parameters : dict, optional
        The analysis settings. Their hash is the identity of the run, which is
        what makes a recomputation replace rather than accumulate.
    out_dir : str or Path, optional
        Where the container goes. Defaults to beside *source*.

    Returns
    -------
    str
        Path of the container written.
    """
    from chisurf.core.fio.pto import Measurement, is_measurement

    src = Path(source)
    target = (Path(out_dir) if out_dir is not None else src.parent) / (src.stem + ".pto")

    if is_measurement(target):
        container = Measurement.open(target, writable=True)
    else:
        container = Measurement.create(src, out_dir=out_dir)

    with container as m:
        m.put_table(
            "bursts",
            deinterleave_bursts(df),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters=parameters,
            derived_from=m.instrument_uid,
        )
    return str(target)


def get_unique_folder_path(base_path: Path) -> Path:
    """Return a path unique w.r.t. both the directory and a sibling ``.zip``.

    If *base_path* exists or a sibling ``{base_path.name}.zip`` exists,
    numeric suffixes (``_0``, ``_1``, …) are tried until a free name is found.

    Parameters
    ----------
    base_path : Path
        Desired output directory path.

    Returns
    -------
    Path
        Unique directory path.
    """

    def _name_taken(p: Path) -> bool:
        return p.exists() or (p.parent / f"{p.name}.zip").exists()

    if not _name_taken(base_path):
        return base_path
    counter = 0
    while True:
        candidate = base_path.parent / f"{base_path.name}_{counter}"
        if not _name_taken(candidate):
            return candidate
        counter += 1


def write_hdf5(
    dataframes: Sequence[pd.DataFrame],
    path: str | Path,
    complib: str | None = None,
) -> None:
    """Write one or more burst DataFrames to a columnar HDF5 file.

    One dataset per column, in the column's own dtype, with a text column stored
    as its dictionary codes and labels. That replaces the hand-rolled encoding
    this used to do -- ``int32`` category codes plus a ``category_map`` JSON
    attribute -- with the same thing done by the container, so ``Source File``
    and ``First File`` come back as file names rather than as integers whose key
    nothing in this tree ever read.

    Parameters
    ----------
    dataframes : sequence of pandas.DataFrame
        Burst summary tables to combine.
    path : str or Path
        Output ``.h5`` path.
    complib : str, optional
        Ignored, and kept so callers do not have to change. These files are
        written once per analysis and read repeatedly, and compressing them
        costs roughly thirty times the write to save eight percent of the size.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_burst_hdf5(dataframes, target)


def zip_output_folder(output_folder: Path, zip_path: str | Path | None = None) -> Path:
    """Zip an output folder preserving relative paths, matching legacy format.

    Parameters
    ----------
    output_folder : Path
        Directory to zip.
    zip_path : str or Path, optional
        Desired zip path. If not given, ``{output_folder}.zip`` is
        used (with ``_N`` suffix if that name is taken).

    Returns
    -------
    Path
        Path to the created zip file.
    """
    if not output_folder.exists() or not output_folder.is_dir():
        raise FileNotFoundError(f"Output folder not found: {output_folder}")

    if zip_path is None:
        zip_path = get_unique_folder_path(output_folder).parent / f"{output_folder.name}.zip"

    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in sorted(output_folder.rglob("*")):
            if entry.is_file():
                rel = entry.relative_to(output_folder)
                zf.write(entry, str(rel))

    return zip_path
