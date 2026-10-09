"""
BID → Analysis Converter

This plugin reads burst ID (BID) files containing start/stop photon indices
and generates a burstwise analysis folder next to the corresponding TTTR data.

Workflow per BID file:
- Infer the TTTR file from the BID file name (same stem, common TTTR extensions)
- Load TTTR via tttrlib
- Compute burst summary using cs.core.fio.fluorescence.burst.generate_burst_dataframe
- Write a BUR file to analysis/bi4_bur/<stem>.bur
- Update/create analysis/Info/*.mti with total measurement time

The plugin exposes a simple GUI file dialog when launched from the Plugins menu.
It can also be called programmatically via convert_bid_file(pathlike).
"""

from __future__ import annotations

import json
import os
import pathlib
import time
import zipfile
from collections.abc import Iterable
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

import chisurf as cs
import chisurf.core.fio as io
from chisurf import logging
from chisurf.core.datastore import (
    concat_stores,
    read_csv_table,
    row_count,
    take_rows,
    write_csv_table,
)
from chisurf.core.datastore import (
    set_constant as _set_constant,
)

try:
    import tttrlib
except Exception:  # pragma: no cover
    tttrlib = None  # type: ignore

from chisurf.core.fio.fluorescence.burst import (
    generate_burst_dataframe,
    write_dataframe_to_bur,
    write_mti_summary,
)
from chisurf.core.fluorescence.burst.utils import create_array_with_ones

# Plugin name in menu
name = "Tools:Converter:BID→Analysis"

# Aggregated into the File tools hub (tttr/filetools); hidden as a top-level
# menu entry but still importable and standalone-launchable.
menu_hidden = True

# Optional icon exposed for the plugin manager/UI
icon = "🔗"

# Supported TTTR extensions mapped to tttrlib file types
#: TTTR extensions this tool recognises when hunting for a measurement file.
#:
#: These are *extensions*, not container types. They used to be a
#: ``{extension: container_type}`` map whose values -- "SPC", "PHU", "HT2",
#: "PT3", "T3R", "HDF5" -- are not names ``tttrlib`` accepts, and passing one
#: does not raise: the library prints to stderr and hands back an object with
#: zero photons. The container is detected from the file instead, which is what
#: ``tttrlib`` is good at, so nothing needs to be guessed from a suffix.
from chisurf.core.fio.staging import TTTR_EXTENSIONS as _TTTR_EXTENSIONS


def _find_tttr_by_stem(start_dir: pathlib.Path, bid_stem: str) -> pathlib.Path | None:
    """Find TTTR file matching a BID stem by searching up the directory tree.

    Searches up to 4 levels up from start_dir.

    More permissive matching:
    - exact stem match (stem.ext)
    - files that start with the BID stem (stem*ext)
    - BID stem starts with the TTTR stem (to allow BID suffixes like "_state1")
    Preference order: exact > candidate.stem startswith(BID) > BID startswith(candidate.stem) > substring fallback.
    """

    def _score(candidate: pathlib.Path) -> tuple:
        cstem = candidate.stem
        if cstem == bid_stem:
            return (0, -len(cstem))
        if cstem.startswith(bid_stem):
            return (1, -len(cstem))
        if bid_stem.startswith(cstem):
            # Prefer longer candidate stems when BID has extra suffix
            return (2, -len(cstem))
        if cstem in bid_stem:
            return (3, -len(cstem))
        return (9, len(cstem))  # non-match

    current_dir = start_dir
    for _ in range(4):  # Search current dir and 3 parents
        if not current_dir.exists():
            # Go to the next parent if the current one doesn't exist
            if current_dir.parent == current_dir:
                break  # Reached root
            current_dir = current_dir.parent
            continue

        # Collect all TTTR files in this base folder
        files: list[pathlib.Path] = []
        for ext in _TTTR_EXTENSIONS:
            files.extend(current_dir.glob(f"*{ext}"))

        if files:
            # Score and select best match in this directory
            scored = [(_score(p), p) for p in files]
            matched = [(s, p) for s, p in scored if s[0] < 9]
            if matched:
                # Sort by score, then by secondary metric (longer stem preferred via negative length), then by filename length
                matched.sort(key=lambda sp: (sp[0][0], sp[0][1], len(sp[1].name)))
                return matched[0][1]

        # Move to the parent directory for the next iteration
        if current_dir.parent == current_dir:
            break  # Reached the root of the filesystem
        current_dir = current_dir.parent

    return None


def _load_tttr(tttr_path: pathlib.Path) -> tttrlib.TTTR:
    if tttrlib is None:
        raise RuntimeError("tttrlib is not available; cannot load TTTR files")
    ext = tttr_path.suffix.lower()
    if ext not in _TTTR_EXTENSIONS:
        raise ValueError(f"Unsupported TTTR file extension: {ext}")
    # Through the shared seam, which detects the container and applies staging
    # and any channel LUTs.
    from chisurf.core.fio.staging import open_tttr

    return open_tttr(tttr_path)


def _default_windows_detectors(tttr: tttrlib.TTTR) -> tuple[dict, dict]:
    """Create simple default windows and detectors covering the full range.

    - windows: one window 'All' covering full micro-time range
    - detectors: one entry per routing channel, full micro-time range
    """
    micro = tttr.micro_times
    rout = tttr.routing_channel
    max_micro = int(micro.max()) if len(micro) else 0
    # Half-open intervals [start, end) used in generate_burst_dataframe
    windows = {"All": (0, max_micro + 1)}

    unique_chs = np.unique(rout) if len(rout) else np.array([0], dtype=int)
    detectors = {}
    for ch in unique_chs.tolist():
        detectors[f"ch{int(ch)}"] = {
            "chs": [int(ch)],
            "micro_time_ranges": [(0, max_micro + 1)],
        }
    return windows, detectors


def _read_bid_start_stop(bid_path: pathlib.Path) -> list[tuple[int, int]]:
    """Read BID file assumed to contain two integer columns: start stop (inclusive or exclusive stop).

    The file is interpreted as start and stop indices. If stop <= start, the row is ignored later.
    """
    arr = np.loadtxt(str(bid_path), dtype=np.int64)
    if arr.ndim == 1 and arr.size >= 2:
        arr = arr.reshape(1, -1)
    if arr.size == 0:
        return []
    # Normalize to list of tuples
    start_stop = [(int(s), int(e)) for s, e in arr[:, :2]]
    return start_stop


def _get_unique_folder_path(base_path: pathlib.Path) -> pathlib.Path:
    """Return a unique folder path by appending -NNN if needed (like the wizard)."""

    def name_taken(p: pathlib.Path) -> bool:
        return p.exists()

    if not name_taken(base_path):
        return base_path
    # try suffixes -001, -002, ... -999
    for i in range(1, 1000):
        s = f"{base_path.name}-{i:03d}"
        p = base_path.parent / s
        if not name_taken(p):
            return p
    # fallback timestamp
    ts = time.strftime("%Y%m%d-%H%M%S")
    return base_path.parent / f"{base_path.name}-{ts}"


def _prepare_output_dir(
    base_dir: pathlib.Path, target_folder_name: str, unique_folder: bool
) -> pathlib.Path:
    logging.debug(
        f"_prepare_output_dir called with: base_dir={base_dir}, target_folder_name={target_folder_name}, unique_folder={unique_folder}"
    )
    out_dir = base_dir / target_folder_name
    logging.debug(f"Initial out_dir: {out_dir}")
    if unique_folder:
        out_dir = _get_unique_folder_path(out_dir)
        logging.debug(f"Unique out_dir: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    logging.debug(f"Ensured output directory exists: {out_dir}")
    return out_dir


def _infer_windows_detectors(
    tttr: tttrlib.TTTR, windows: dict | None, detectors: dict | None
) -> tuple[dict, dict]:
    if windows is None or detectors is None:
        w, d = _default_windows_detectors(tttr)
        if windows is None:
            windows = w
        if detectors is None:
            detectors = d
    return windows, detectors


def _write_info_files(
    output_dir: pathlib.Path,
    files: list[pathlib.Path],
    detectors: dict,
    windows: dict,
    selected_setup: str | None = None,
    bid_files: list[pathlib.Path] | None = None,
) -> None:
    info_dir = output_dir / "Info"
    info_dir.mkdir(parents=True, exist_ok=True)

    # Derive channels and microtime ranges from detectors
    channels = []
    microtime_ranges = []
    for det in detectors.values():
        chs = det.get("chs", [])
        channels.extend(int(x) for x in chs)
        mts = det.get("micro_time_ranges", [])
        for r in mts:
            if r not in microtime_ranges:
                microtime_ranges.append(r)
    params = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "selected_setup": (selected_setup or "BID"),
        "channels": sorted(set(channels)),
        "decay_coarse": None,
        "microtime_ranges": microtime_ranges,
        "files": [p.name for p in files],
        "filter_mode": "bid",
        "filter_active": False,
        "use_gap_fill": False,
        "max_gap": 0,
    }
    with open(info_dir / "photon_selection_parameters.json", "w") as f:
        json.dump(params, f, indent=4)
    with open(info_dir / "datetime.txt", "w") as f:
        now = time.strftime("%Y-%m-%d"), time.strftime("%H:%M:%S")
        f.write(f"Date: {now[0]}\nTime: {now[1]}\n")

    if bid_files:
        with open(info_dir / "burst_files.txt", "w") as f:
            for p in bid_files:
                f.write(f"{p.name}\n")


def _write_sl5(
    output_dir: pathlib.Path, tttr_path: pathlib.Path, filetype: str, selected_mask: np.ndarray
) -> None:
    sl5_dir = output_dir / "sl5"
    sl5_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "filename": os.path.relpath(tttr_path, output_dir),
        "filetype": filetype,
        "count_rate_filter": {},
        "delta_macro_time_filter": {},
        "filter": io.compress_numpy_array(selected_mask.astype(np.uint8)),
    }
    out_file = sl5_dir / f"{tttr_path.stem}.json.gz"
    with io.open_maybe_zipped(out_file, "w") as f:
        f.write(json.dumps(data))


def _write_hdf5_combined(output_dir: pathlib.Path, dataframes: list) -> None:
    """Write the combined burst tables to one columnar HDF5 file.

    The encoding this used to build by hand -- integers downcast, floats
    narrowed, every text column replaced by ``int32`` codes with the labels in a
    JSON attribute -- lives in
    :func:`chisurf.core.fio.fluorescence.burst.write_burst_hdf5`, which is also
    what the burst-selection API and the photon-filter wizard call. There were
    three copies of it.

    Parameters
    ----------
    output_dir : pathlib.Path
        Analysis output folder; the file goes in its ``hdf5`` subfolder.
    dataframes : list of tttrlib.DataStore
        Per-measurement burst tables.
    """
    from chisurf.core.fio.fluorescence.burst import write_burst_hdf5

    if not dataframes:
        return
    hdf5_dir = output_dir / "hdf5"
    hdf5_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    write_burst_hdf5(dataframes, hdf5_dir / f"burst_data_{timestamp}.h5")


def zip_output_folder(output_folder: pathlib.Path) -> pathlib.Path | None:
    """Zip the output folder to a unique .zip next to it; return zip path."""

    def unique_zip_path(base: pathlib.Path) -> pathlib.Path:
        p = base.with_suffix(".zip")
        if not p.exists():
            return p
        for i in range(1, 1000):
            p2 = base.parent / f"{base.name}-{i:03d}.zip"
            if not p2.exists():
                return p2
        ts = time.strftime("%Y%m%d-%H%M%S")
        return base.parent / f"{base.name}-{ts}.zip"

    output_folder = pathlib.Path(output_folder)
    zip_path = unique_zip_path(output_folder)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(output_folder):
            root_path = pathlib.Path(root)
            for f in files:
                fp = root_path / f
                arc = fp.relative_to(output_folder)
                zf.write(str(fp), arcname=str(arc))
    return zip_path


def _per_file_process(
    bid_path: pathlib.Path,
    output_dir: pathlib.Path,
    windows: dict | None,
    detectors: dict | None,
    output_types: set[str],
    bid_index: int = 1,
) -> tuple[pathlib.Path, tttrlib.TTTR, dict, dict, tttrlib.DataStore, np.ndarray]:
    bid_path = pathlib.Path(bid_path)
    stem = bid_path.stem
    tttr_path = _find_tttr_by_stem(bid_path.parent, stem)
    if tttr_path is None:
        raise FileNotFoundError(
            f"Could not locate TTTR file for BID '{bid_path.name}' (stem='{stem}')"
        )
    tttr = _load_tttr(tttr_path)

    windows, detectors = _infer_windows_detectors(tttr, windows, detectors)

    start_stop = _read_bid_start_stop(bid_path)
    df = generate_burst_dataframe(
        start_stop=start_stop,
        filename=str(tttr_path),
        tttr=tttr,
        windows=windows,
        detectors=detectors,
        include_interleaved_zeros=("bur" in output_types),
    )

    # Tag bursts with BID origin information.
    #
    # Spelled out per row rather than assigned as a scalar: `df` is a store now,
    # and a store's __setitem__ takes an array where a frame broadcast a scalar.
    # The assignment used to sit inside a bare `except Exception: pass`, so
    # after the migration it raised on the first line and both columns silently
    # stopped being written -- a burst table that no longer said which BID file
    # produced it, and nothing to notice by.
    _set_constant(df, "BID File", bid_path.name)
    _set_constant(df, "BID Index", int(bid_index))

    # BUR output
    bur_path = None
    if "bur" in output_types:
        bur_dir = output_dir / "bi4_bur"
        bur_dir.mkdir(parents=True, exist_ok=True)
        bur_path = bur_dir / f"{tttr_path.stem}.bur"
        # If a BUR for this TTTR already exists, append new bursts instead of overwriting
        try:
            include_zeros = True  # we used include_interleaved_zeros when creating df
            if bur_path.exists():
                existing_store = read_csv_table(bur_path, delimiter="\t")
                # Avoid duplicate leading zero-row when appending: drop first row of the new df
                df_to_append = (
                    take_rows(df, np.arange(1, row_count(df)))
                    if include_zeros and row_count(df) > 0
                    else df
                )
                if existing_store is not None:
                    combined = concat_stores([existing_store, df_to_append])
                    write_csv_table(bur_path, combined)
                else:
                    write_dataframe_to_bur(df_to_append, str(bur_path))
            else:
                write_dataframe_to_bur(df, str(bur_path))
        except Exception as _append_exc:
            # Fallback to simple write if anything went wrong during append logic
            write_dataframe_to_bur(df, str(bur_path))
        # MTI summary
        try:
            max_macro_time_s = float(tttr.macro_times[-1]) * float(
                tttr.header.macro_time_resolution
            )
        except Exception:
            max_macro_time_s = 0.0
        write_mti_summary(tttr_path, output_dir, max_macro_time_s, append=True)

    if "pto" in output_types:
        _write_container(
            tttr_path,
            bid_path,
            df,
            bid_index,
            interleaved=("bur" in output_types),
        )

    # SL5 output
    selected = None
    if "sl5" in output_types:
        n = len(tttr)
        selected = create_array_with_ones(np.array(start_stop, dtype=int), n).astype(np.uint8)
        _write_sl5(output_dir, tttr_path, tttr_path.suffix.lower().lstrip("."), selected)

    # For HDF5 collection
    if df is not None:
        df_copy = df.copy()
        _set_constant(df_copy, "Source File", str(tttr_path))
    else:
        df_copy = df

    return bur_path, tttr, detectors, windows, df_copy, selected


def _write_container(
    tttr_path: pathlib.Path,
    bid_path: pathlib.Path,
    df,
    bid_index: int,
    *,
    interleaved: bool = False,
) -> None:
    """Write the imported bursts, and the `.bid` they were imported from.

    A BID selection is not a burst search: the burst boundaries were decided by
    another program and this reads them in. So the `.bid` goes into the
    container as a blob, and the burst table is derived from it — the container
    then holds everything needed to say where these bursts came from, which a
    `bi4_bur/` folder beside an unmentioned `.bid` never did.

    Parameters
    ----------
    tttr_path : pathlib.Path
        The instrument file the bursts index into.
    bid_path : pathlib.Path
        The burst-ID file that defined them.
    df : tttrlib.DataStore or None
        The burst table.
    bid_index : int
        Which selection within the BID file this is.
    interleaved : bool
        Whether *df* still carries the ``.bur`` padding rows.

        Stated rather than detected. :func:`deinterleave_bursts` recognises the
        layout by finding zeros on the even rows, and the BID columns tagged
        onto this table are constant over *every* row — padding included — so
        the padding is not all-zero and the heuristic correctly concludes the
        table is not padded. The caller knows, because it asked for the padding
        in the first place.
    """
    from chisurf.core.datastore import row_count, take_rows
    from chisurf.core.fio.fluorescence.burst_container import (
        open_measurement,
        units_for,
    )

    if df is None or not row_count(df):
        return
    table = take_rows(df, np.arange(1, row_count(df), 2)) if interleaved else df
    try:
        with open_measurement(tttr_path) as m:
            source = m.put_blob(
                bid_path.name,
                bid_path.read_bytes(),
                artifact_kind="burst_selection",
                data_format="bin",
            )
            m.put_table(
                "bursts",
                table,
                artifact_kind="burst_table",
                operation_type="import",
                row_grain="burst",
                parameters={"bid_file": bid_path.name, "bid_index": int(bid_index)},
                derived_from=source,
                units=units_for(table),
            )
    except Exception as exc:
        logging.warning(f"Could not write the container for {tttr_path}: {exc}")


def convert_bid_file(
    bid_path: os.PathLike | str,
    analysis_folder: os.PathLike | str | None = None,
    *,
    output_types: set[str] | None = None,
    windows: dict | None = None,
    detectors: dict | None = None,
    target_path: str = "analysis",
    unique_folder: bool = False,
    zip_output: bool = False,
    remove_folder: bool = False,
    selected_setup: str | None = None,
    bid_index: int = 1,
) -> pathlib.Path:
    """Convert a single BID file into an analysis folder.

    By default writes BUR + MTI. Optional outputs: SL5 and combined HDF5.

    Returns the path to the produced BUR file (if BUR was requested), else the output directory.
    """
    bid_path = pathlib.Path(bid_path)
    if not bid_path.exists():
        raise FileNotFoundError(bid_path)

    # Determine output directory
    # If analysis_folder provided, use as-is (no unique suffix unless unique_folder=True)
    # else create under TTTR parent / target_path
    # We need tttr_path to decide default; locate it first without loading
    stem = bid_path.stem
    tttr_path = _find_tttr_by_stem(bid_path.parent, stem)
    if tttr_path is None:
        raise FileNotFoundError(
            f"Could not locate TTTR file for BID '{bid_path.name}' (stem='{stem}')"
        )
    output_dir = (
        _prepare_output_dir(
            pathlib.Path(analysis_folder).parent, pathlib.Path(analysis_folder).name, unique_folder
        )
        if analysis_folder is not None
        else _prepare_output_dir(
            tttr_path.parent,
            bid_path.stem if target_path == "analysis" else target_path,
            unique_folder,
        )
    )

    # Default outputs
    if output_types is None:
        output_types = {"pto"}

    # Process this single file
    bur_path, tttr, dets, wins, df, selected = _per_file_process(
        bid_path, output_dir, windows, detectors, output_types, bid_index=bid_index
    )

    # Info files
    _write_info_files(output_dir, [tttr_path], dets, wins, selected_setup=selected_setup)

    # Combined HDF5: for single file, just write immediately
    if "hdf5" in output_types and df is not None:
        _write_hdf5_combined(output_dir, [df])

    # Zip handling
    if zip_output:
        zip_name = zip_output_folder(output_dir)  # define below
        if remove_folder and zip_name:
            import shutil

            shutil.rmtree(output_dir, ignore_errors=True)

    return bur_path if ("bur" in output_types and bur_path is not None) else output_dir


def convert_many(
    bid_paths: Iterable[os.PathLike | str],
    analysis_folder: os.PathLike | str | None = None,
    *,
    output_types: set[str] | None = None,
    windows: dict | None = None,
    detectors: dict | None = None,
    target_path: str = "analysis",
    unique_folder: bool = True,
    zip_output: bool = False,
    remove_folder: bool = False,
    selected_setup: str | None = None,
) -> list[pathlib.Path]:
    bid_paths = [pathlib.Path(p) for p in bid_paths]
    if not bid_paths:
        return []

    # Resolve output directory using first file's TTTR
    first_tttr = _find_tttr_by_stem(bid_paths[0].parent, bid_paths[0].stem)
    if first_tttr is None:
        raise FileNotFoundError(f"Could not locate TTTR file for BID '{bid_paths[0].name}'")
    output_dir = (
        _prepare_output_dir(
            pathlib.Path(analysis_folder).parent, pathlib.Path(analysis_folder).name, unique_folder
        )
        if analysis_folder is not None
        else _prepare_output_dir(first_tttr.parent, target_path, unique_folder)
    )

    if output_types is None:
        output_types = {"pto"}

    bur_paths: list[pathlib.Path] = []
    dfs_for_hdf5: list = []
    tttr_paths_for_info: list[pathlib.Path] = []

    for i, p in enumerate(bid_paths, start=1):
        try:
            bur_path, tttr, dets, wins, df, selected = _per_file_process(
                p, output_dir, windows, detectors, output_types, bid_index=i
            )
            if bur_path is not None:
                bur_paths.append(bur_path)
            if df is not None:
                dfs_for_hdf5.append(df)
            # track tttr path for info listing
            tttr_paths_for_info.append(_find_tttr_by_stem(p.parent, p.stem))
        except Exception as exc:
            logging.error(f"Failed to convert {p}: {exc}")

    # Write info once including all files
    if tttr_paths_for_info:
        # Use the last computed detectors/windows if provided; else default values using first tttr
        if detectors is None or windows is None:
            tmp_tttr = _load_tttr(first_tttr)
            w, d = _infer_windows_detectors(tmp_tttr, windows, detectors)
        else:
            w, d = windows, detectors
        _write_info_files(
            output_dir,
            [pathlib.Path(tp) for tp in tttr_paths_for_info if tp],
            d,
            w,
            selected_setup=selected_setup,
        )

    if "hdf5" in output_types and dfs_for_hdf5:
        _write_hdf5_combined(output_dir, dfs_for_hdf5)

    if zip_output:
        zip_name = zip_output_folder(output_dir)
        if remove_folder and zip_name:
            import shutil

            shutil.rmtree(output_dir, ignore_errors=True)

    return bur_paths


def __getattr__(name):
    if name == "BidToAnalysisGUI":
        from .gui.legacy import BidToAnalysisGUI

        return BidToAnalysisGUI
    raise AttributeError(name)


if __name__ == "plugin":
    from chisurf.plugins.burst.bid_to_analysis.gui.legacy import BidToAnalysisGUI

    window = BidToAnalysisGUI()
    window.show()
