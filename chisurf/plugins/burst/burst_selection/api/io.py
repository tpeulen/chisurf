"""Input/output helpers for the Burst Selection API."""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from pathlib import Path
import tttrlib

from chisurf.core.fio.fluorescence.burst_container import (
    deinterleave_bursts,
    write_burst_artifact,
)
from chisurf.core.fio.fluorescence.burst import (
    read_bur_file,
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


def read_bur(path: str | Path):
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


def write_bur(df, path: str | Path) -> None:
    """Write a burst summary DataFrame as a ChiSurf ``.bur`` file.

    Parameters
    ----------
    df : pandas.DataFrame or mapping of str to array
        Burst summary table.
    path : str or Path
        Output path.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_dataframe_to_bur(df, target)


def write_container(
    source: str | Path,
    df,
    *,
    parameters: dict | None = None,
    out_dir: str | Path | None = None,
    run: str = "",
) -> str:
    """Write the burst table into the measurement's own container.

    One measurement is one file: the instrument data stays where it is, and the
    bursts found in it become an artifact beside it rather than a `.bur` in a
    directory whose name encodes the parameters. Re-running with the same
    settings replaces that artifact in place; changing a setting adds one.

    Parameters
    ----------
    source : str or Path
        The instrument file the bursts were found in.
    df : pandas.DataFrame or mapping of str to array
        Burst summary table.
    parameters : dict, optional
        The analysis settings. Their hash is the identity of the run.
    out_dir : str or Path, optional
        Where the container goes. Defaults to beside *source*.
    run : str, optional
        Name of this analysis inside the container -- the same string the
        legacy layout uses for its directory. A container holds several
        analyses of one measurement and they are addressed the way a folder's
        are (``m000.pto/countrate_All 0.1500#60``); see
        :mod:`chisurf.core.fio.fluorescence.burst_tree`. Empty stores the table
        at the top level, which is what a container written before runs were
        named looks like.

    Returns
    -------
    str
        Path of the container written.
    """
    from chisurf.core.fio.analysis_path import bur_artifact_name

    return write_burst_artifact(
        source,
        df,
        # The name a `.bur` would have had in the folder, and the table exactly
        # as that file holds it -- interleave and all. A container mirrors the
        # tree it replaces, so unpacking reproduces the file and a reader that
        # has always applied the row stride keeps applying it.
        name=bur_artifact_name(run, Path(source).stem),
        deinterleave=False,
        artifact_kind="burst_table",
        operation_type="burst_selection",
        row_grain="burst",
        parameters=dict(parameters) if parameters else None,
        derived_from=(),
        out_dir=out_dir,
    )


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
