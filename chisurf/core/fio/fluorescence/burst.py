"""Readers and writers for the ``.bur`` burst tables.

**The column set is declared, not coded**: ``burst_features.yaml`` beside
this module names every computed feature, its header and its order, and
``generate_burst_dataframe`` instantiates that declaration over the detector
setup. Add, rename, reorder or drop a column in the YAML — no code change
(the general rule: analysis I/O and computed features live in settings). The
quantity vocabulary the declaration draws from is
:func:`_static_burst_features` / :func:`_span_features`.

One column name in this format does not mean what it says, and it is
inherited from the reference format rather than a slip:

``Mean Macro Time (ms)`` and ``Mean Macrotime (<detector>) (ms)`` are the
**midpoint of the burst's first and last photon**, ``(t_first + t_last) / 2`` —
not the mean of its photon macro times. The two agree only when a burst's
photons are symmetrically distributed in time, which is exactly what fails near
the edges of a transit. Anything using the column as a burst centre of mass
(drift correction, time-trace placement, macro-time gating) is using a midpoint.

It is left as it is on purpose: the value is what the reference format and the
tools reading these files expect, and silently changing a shipped column would
move every downstream result that ever consumed it. Compute the true mean from
the photons if that is what is wanted.

By contrast ``Duration (<detector>) (ms)`` is exactly what it says —
``t_last − t_first`` over that detector's photons in the burst — and detectors a
burst has no photons in carry ``-1.0`` duration and ``0`` counts rather than
being omitted.
"""

import pathlib

import numpy as np
import tttrlib

from chisurf.core.datastore import (
    column_names,
    concat_stores,
    new_store,
    numeric_column,
    row_count,
    store_from_arrays,
    write_csv_table,
)

#: Sentinel written for a per-detector column a burst has no photons in. Matches
#: the ``-1.0`` the duration and rate columns already use, so a reader that
#: filters one filters them all.
DETECTOR_SENTINEL = -1.0


def micro_time_resolution_ns(tttr, override: float = None) -> float:
    """Nanoseconds per micro-time channel, or ``0.0`` if the file does not say.

    The mean micro time is written in nanoseconds rather than raw channels so
    the column survives a change of micro-time resolution — a raw-channel value
    is meaningless without the header that produced it.

    Parameters
    ----------
    tttr : object
        TTTR-like object with ``header.micro_time_resolution`` in seconds.
    override : float, optional
        Resolution in seconds, used instead of the header when given.

    Returns
    -------
    float
        Nanoseconds per channel, or ``0.0`` when no positive resolution is
        available — callers then write :data:`DETECTOR_SENTINEL` rather than a
        number in unknown units.
    """
    if override is not None:
        resolution = float(override)
    else:
        resolution = float(getattr(tttr.header, "micro_time_resolution", 0.0) or 0.0)
    return resolution * 1e9 if resolution > 0.0 else 0.0


def mean_micro_time_ns(micro_times, indices, ns_per_channel: float) -> float:
    """Mean micro time of selected photons, in nanoseconds.

    Parameters
    ----------
    micro_times : numpy.ndarray
        Micro times, in raw channels.
    indices : numpy.ndarray
        Positions within *micro_times* to average over.
    ns_per_channel : float
        From :func:`micro_time_resolution_ns`; ``0.0`` disables the conversion.

    Returns
    -------
    float
        The mean in nanoseconds, or :data:`DETECTOR_SENTINEL` when there is
        nothing to average or the resolution is unknown.
    """
    if ns_per_channel <= 0.0 or len(indices) == 0:
        return DETECTOR_SENTINEL
    return float(np.mean(micro_times[indices])) * ns_per_channel


def _micro_time_mask(micro_times, ranges) -> np.ndarray:
    """Return the photons a detector's micro-time windows accept.

    **No windows means every micro time**, which is the reading
    :class:`~chisurf.core.fluorescence.burst.photons.StreamDef` documents and the
    only one that makes sense: a detector defined by its routing channels alone is
    ungated, not empty. Accumulating an empty list of windows into a zeroed mask —
    which is what both writer paths used to do — silently produced an all-zero
    column for *every* per-detector quantity, so a setup configured without a
    micro-time gate wrote a burst table in which no detector had ever seen a photon.

    Parameters
    ----------
    micro_times : numpy.ndarray
        Micro times, in raw channels.
    ranges : sequence of tuple
        Half-open ``(start, stop)`` windows. Empty accepts everything.

    Returns
    -------
    numpy.ndarray
        Boolean mask over *micro_times*.
    """
    if not ranges:
        return np.ones(len(micro_times), dtype=bool)
    mask = np.zeros(len(micro_times), dtype=bool)
    for start, stop in ranges:
        mask |= (micro_times >= start) & (micro_times < stop)
    return mask


def write_mti_summary(
    filename: pathlib.Path, analysis_dir: pathlib.Path, max_macro_time, append: bool = True
):
    """
    Creates or appends to an MTI file in the 'Info' folder. If any MTI file exists, appends to it;
    otherwise, creates a new one based on the given filename.

    Args:
        filename (pathlib.Path): Path to the original file (e.g., '.ht3').
        analysis_dir (pathlib.Path): Directory where the 'Info' folder will be created if missing.
        max_macro_time: The maximum macro time (last photon time) to log.
        append (bool): If True, appends to the first existing MTI file found, otherwise creates a new file.

    Example:
        Creates or appends to an MTI file in:
        c:/analysis_directory/Info/Split_60_132_tween0p00001-0000.mti
        With entry:
        c:/data/Split_60_132_tween0p00001-0000.ht3   74860.905977
    """
    # Create the 'Info' directory if it doesn't exist
    parent_directory = analysis_dir / "Info"
    parent_directory.mkdir(exist_ok=True, parents=True)

    # Search for any existing .mti files in the 'Info' folder
    existing_mti_files = list(parent_directory.glob("*.mti"))

    # If there are any existing .mti files, append to the first one found
    if existing_mti_files and append:
        mti_filename = existing_mti_files[0]
        mode = "a"
    else:
        # If no .mti files are found or append is False, create a new file based on the filename
        mti_filename = parent_directory / f"{filename.stem}.mti"
        mode = "w"

    # Write the filename and max_macro_time to the .mti file
    with open(mti_filename, mode) as mti_file:
        mti_file.write(f"{filename}\t{max_macro_time:.6f}\n")


def get_indices_in_ranges(rout, mt, chs, micro_time_ranges):
    """Find photon indices matching routing channels and micro-time ranges.

    Parameters
    ----------
    rout : np.ndarray
        Routing channel numbers.
    mt : np.ndarray
        Micro-time values.
    chs : list of int
        Allowed routing channels.
    micro_time_ranges : list of tuple
        (start, end) micro-time range pairs.

    Returns
    -------
    list of int
        Matching photon indices.
    """
    # Create a boolean mask for the rout values in chs
    rout_mask = np.isin(rout, chs)

    # Create a boolean mask for the mt values in micro_time_ranges
    mt_mask = np.zeros(mt.shape, dtype=bool)
    for start, end in micro_time_ranges:
        mt_mask |= (mt >= start) & (mt <= end)

    # Get indices where both masks are true
    indices = np.where(rout_mask & mt_mask)[0]

    return indices.tolist()


#: Loaded once; the file is the schema authority (see its own header).
_BURST_FEATURES_DECLARATION = None


def burst_feature_declaration() -> dict:
    """Return the declared burst-summary schema (``burst_features.yaml``).

    The declaration names every computed feature of a burst analysis, its
    column header and its order -- the general rule: analysis I/O and
    computed features live in a settings file so they can change without a
    code change. The ``source`` vocabulary the entries may use is defined
    by :func:`_static_burst_features` and :func:`_span_features`.

    Returns
    -------
    dict
        ``{"groups": [{"scope": ..., "columns": [...]}, ...],
        "trailing_blank": bool}``.
    """
    global _BURST_FEATURES_DECLARATION
    if _BURST_FEATURES_DECLARATION is None:
        import yaml

        path = pathlib.Path(__file__).with_name("burst_features.yaml")
        with open(path, encoding="utf-8") as fh:
            _BURST_FEATURES_DECLARATION = yaml.safe_load(fh)
    return _BURST_FEATURES_DECLARATION


def _static_burst_features(
    sources, start, stop, macro, res, confidence, burst_index, file_name
) -> dict:
    """Whole-burst quantities, by declared ``source`` name.

    This is the ``static``-scope vocabulary of ``burst_features.yaml``; a
    new whole-burst feature is one ``elif`` here plus its declaration line.
    """
    dur = (macro[stop] - macro[start]) * res * 1e3
    out = {}
    for s in sources:
        if s == "first_photon":
            out[s] = start
        elif s == "last_photon":
            out[s] = stop
        elif s == "duration_ms":
            out[s] = dur
        elif s == "mean_macro_time_ms":
            out[s] = ((macro[stop] + macro[start]) / 2) * res * 1e3
        elif s == "n_photons":
            out[s] = stop - start + 1
        elif s == "count_rate_khz":
            # ``dur`` is milliseconds, so photons-per-``dur`` is already
            # kHz -- the unit every rate column is written in.
            npix = stop - start + 1
            out[s] = (npix / dur) if dur > 0 else np.nan
        elif s == "confidence_sigma":
            # Indexed by position in start_stop, not by output row: skipped
            # bursts never reach the filler, so the two would otherwise
            # drift apart. Unavailable (old engine) stays 0 -- the layout
            # must not depend on the tttrlib version.
            out[s] = (
                float(confidence[burst_index])
                if confidence is not None and burst_index < confidence.size
                else 0
            )
        elif s == "file_name":
            out[s] = file_name
        else:
            raise ValueError(f"burst_features.yaml: unknown static source {s!r}")
    return out


#: What a span quantity reads when its detector/window saw no photon.
#: Sentinel values, not omissions -- one row per burst, always (the
#: companion contract), so an empty selection is a value, never a hole.
_SPAN_EMPTY = {
    "first_photon": -1,
    "last_photon": -1,
    "duration_ms": -1.0,
    "mean_macro_time_ms": -1.0,
    "n_photons": 0,
    "count_rate_khz": -1.0,
}


def _span_features(sources, idxs, start, macro, res, micro_sl, micro_ns) -> dict:
    """Photon-span quantities, by declared ``source`` name.

    The shared vocabulary of the ``detector`` and ``window_detector``
    scopes of ``burst_features.yaml``: quantities over the selected photons
    of one burst (a detector's, or a detector's within a PIE window).

    Parameters
    ----------
    sources : set of str
        Which quantities the declaration asks for.
    idxs : numpy.ndarray
        Indices of the selected photons, relative to the burst slice.
    start : int
        The burst's first photon, absolute.
    macro : numpy.ndarray
        Macro times of the whole measurement.
    res : float
        Macro-time resolution in seconds.
    micro_sl : numpy.ndarray
        The burst's micro times.
    micro_ns : float
        Micro-time resolution in nanoseconds.

    Returns
    -------
    dict
        ``source`` name -> value, empty spans filled from ``_SPAN_EMPTY``.
    """
    out = {}
    if idxs.size == 0:
        for s in sources:
            if s == "mean_micro_time_ns":
                out[s] = mean_micro_time_ns(micro_sl, idxs, micro_ns)
            else:
                out[s] = _SPAN_EMPTY[s]
        return out
    abs0, abs1 = start + idxs[0], start + idxs[-1]
    d_ms = (macro[abs1] - macro[abs0]) * res * 1e3
    for s in sources:
        if s == "first_photon":
            out[s] = abs0
        elif s == "last_photon":
            out[s] = abs1
        elif s == "duration_ms":
            out[s] = d_ms
        elif s == "mean_macro_time_ms":
            out[s] = ((macro[abs1] + macro[abs0]) / 2) * res * 1e3
        elif s == "n_photons":
            out[s] = idxs.size
        elif s == "count_rate_khz":
            out[s] = (idxs.size / d_ms) if d_ms > 0 else np.nan
        elif s == "mean_micro_time_ns":
            out[s] = mean_micro_time_ns(micro_sl, idxs, micro_ns)
        else:
            raise ValueError(f"burst_features.yaml: unknown span source {s!r}")
    return out


def generate_burst_dataframe(
    start_stop,
    filename,
    tttr,
    windows,
    detectors,
    include_interleaved_zeros=True,
    macro_time_resolution=None,
):
    """
    Generate a DataFrame with burst summary information.

    This function processes burst data and returns a DataFrame with various statistics for each burst.
    It is optimized for speed by:
    1) precomputing global detector/window masks,
    2) building fixed-length lists instead of OrderedDict,
    3) appending to a list of lists and dumping to pandas once.

    Parameters
    -----------
    start_stop : list of tuples
        List of (start_index, stop_index) tuples defining bursts. ``stop_index``
        is the index of the burst's *last* photon (inclusive), the convention of
        :func:`chisurf.core.math.signal.find_bursts` and of the .bur
        "Last Photon" column.
    filename : str or pathlib.Path
        Path to the TTTR file.
    tttr : object
        TTTR object with macro_times, micro_times, routing_channel, and header.macro_time_resolution.
    windows : dict
        Dictionary {window_name: (r_start, r_stop)}.
    detectors : dict
        Dictionary {det_name: {"chs": [...], "micro_time_ranges": [(mt_start, mt_stop), ...]}}.
    include_interleaved_zeros : bool, optional
        Whether to include interleaved zero rows in the output DataFrame.
        Default is True for backward compatibility with BUR format.
        Set to False when saving to HDF5 format where interleaved zeros are not necessary.
    macro_time_resolution : float, optional
        Macro-time resolution override. If omitted, uses
        ``tttr.header.macro_time_resolution``.

    Returns
    --------
    tttrlib.DataStore
        DataFrame containing burst summary information.
    """
    file_name_only = pathlib.Path(filename).name

    # unpack
    macro = tttr.macro_times
    micro = tttr.micro_times
    rout = tttr.routing_channel
    res = (
        tttr.header.macro_time_resolution
        if macro_time_resolution is None
        else float(macro_time_resolution)
    )
    n_ph = len(tttr)
    micro_ns = micro_time_resolution_ns(tttr)

    # The column set is DECLARED, not coded: `burst_features.yaml` beside
    # this module names every computed feature, its header and its order
    # (the general rule -- analysis I/O drifts in settings, not in code).
    # This function instantiates the declared families over the detector
    # setup and fills each column from its `source` quantity.
    declaration = burst_feature_declaration()
    cols = []  # header, in declared order
    fills = []  # one (scope, source, instance-key) per column
    for group in declaration["groups"]:
        scope = group["scope"]
        entries = [(e["column"], e["source"]) for e in group["columns"]]
        # Instances outer, declared entries inner -- the historical layout
        # groups a detector's (or window-pair's) columns consecutively.
        if scope == "static":
            for template, source in entries:
                cols.append(template)
                fills.append((scope, source, None))
        elif scope == "detector":
            for d in detectors:
                for template, source in entries:
                    cols.append(template.format(detector=d, Detector=str(d).capitalize()))
                    fills.append((scope, source, d))
        elif scope == "window_detector":
            for w, (r0, r1) in windows.items():
                for d in detectors:
                    for template, source in entries:
                        cols.append(
                            template.format(
                                window=w, detector=d, Detector=str(d).capitalize(), r0=r0, r1=r1
                            )
                        )
                        fills.append((scope, source, (w, d)))
        else:
            raise ValueError(f"burst_features.yaml: unknown scope {scope!r}")
    if declaration.get("trailing_blank", False):
        cols.append("")
        fills.append(("blank", "", None))
    # Which quantities each scope actually has to compute for this schema.
    wanted = {
        s: {src for sc, src, _ in fills if sc == s}
        for s in ("static", "detector", "window_detector")
    }

    # Per-burst confidence: the significance of the burst's photon excess over
    # the background measured around it, in sigma. tttrlib computes it from the
    # burst boundaries rather than inside a particular search, so the number
    # means the same thing whichever search produced these bursts, and bursts
    # from different searches stay comparable. Written into the .bur so a
    # marginal detection can be told from an unambiguous one downstream (e.g. in
    # ndxplorer) instead of filtering on photon count, which is not the same
    # thing. Older tttrlib builds do not provide it; the column is then left at 0
    # rather than dropped, so the file layout does not depend on the tttrlib
    # version.
    confidence = None
    _confidence_of = getattr(tttr, "burst_confidence", None)
    if _confidence_of is not None and len(start_stop):
        try:
            _flat = [int(v) for pair in start_stop for v in pair[:2]]
            confidence = np.asarray(_confidence_of(_flat), dtype=float)
        except Exception:
            confidence = None

    # precompute global masks so we don't remake them per-burst
    # Detector/window micro-time ranges are always expressed in raw micro-time
    # channels (the same units as ``micro``); micro-time binning is a display-only
    # concern and never rescales these ranges.
    det_global = {}
    for d, info in detectors.items():
        chm = np.isin(rout, info["chs"])
        det_global[d] = chm & _micro_time_mask(micro, info["micro_time_ranges"])

    win_global = {w: (micro >= r0) & (micro < r1) for w, (r0, r1) in windows.items()}

    # helper zero-row: 0 for every declared column, "" for the blank one
    zero_row = ["" if scope == "blank" else 0 for scope, _, _ in fills]

    out = []
    # only add the leading zero‐row when there's at least one burst and interleaved zeros are requested
    try:
        has_bursts = len(start_stop) > 0
    except TypeError:
        # fallback if start_stop isn’t sized like a sequence
        has_bursts = bool(start_stop)
    if has_bursts and include_interleaved_zeros:
        out.append(zero_row.copy())

    for burst_index, (start, stop) in enumerate(start_stop):
        if stop <= start or stop >= n_ph or start < 0:
            continue

        # ``stop`` is the burst's last photon (inclusive), so the photon at
        # ``stop`` counts and every slice runs to ``stop + 1``.
        sl = slice(start, stop + 1)
        micro_sl = micro[sl]

        static_q = _static_burst_features(
            wanted["static"], start, stop, macro, res, confidence, burst_index, file_name_only
        )

        # Per-instance quantities, computed lazily -- once per detector /
        # window pair per burst, however many declared columns read them.
        det_q: dict = {}
        win_q: dict = {}
        row = []
        for scope, source, key in fills:
            if scope == "static":
                row.append(static_q[source])
            elif scope == "detector":
                q = det_q.get(key)
                if q is None:
                    idxs = np.nonzero(det_global[key][sl])[0]
                    q = det_q[key] = _span_features(
                        wanted["detector"], idxs, start, macro, res, micro_sl, micro_ns
                    )
                row.append(q[source])
            elif scope == "window_detector":
                q = win_q.get(key)
                if q is None:
                    w, d = key
                    idxs = np.nonzero(det_global[d][sl] & win_global[w][sl])[0]
                    q = win_q[key] = _span_features(
                        wanted["window_detector"], idxs, start, macro, res, micro_sl, micro_ns
                    )
                row.append(q[source])
            else:  # the trailing blank
                row.append("")

        out.append(row)
        # Only add trailing zero row if interleaved zeros are requested
        if include_interleaved_zeros:
            out.append(zero_row.copy())

    # Rows in, columns out: the store is column-oriented, and transposing here
    # is what keeps every column its own dtype instead of one object array.
    values = list(zip(*out)) if out else [()] * len(cols)
    return store_from_arrays(
        {
            name: np.array(column, dtype=object)
            if any(isinstance(v, str) for v in column)
            else np.asarray(column)
            for name, column in zip(cols, values)
        }
    )


def write_dataframe_to_bur(df, bur_filename):
    """
    Write a DataFrame to a .bur file (tab-separated values).

    Parameters
    -----------
    df : tttrlib.DataStore
        DataFrame containing burst summary information.
    bur_filename : str or pathlib.Path
        Path to the output .bur file.
    """
    write_csv_table(bur_filename, df)


def write_bur_file_fast(bur_filename, start_stop, filename, tttr, windows, detectors):
    """
    Write burst summary information to a TSV file (tab-separated).

    This is a wrapper function that calls generate_burst_dataframe and write_dataframe_to_bur.

    Parameters
    -----------
    bur_filename : str or pathlib.Path
        Path to the output .bur file.
    start_stop : list of tuples
        List of (start_index, stop_index) tuples defining bursts. ``stop_index``
        is the index of the burst's *last* photon (inclusive), the convention of
        :func:`chisurf.core.math.signal.find_bursts` and of the .bur
        "Last Photon" column.
    filename : str or pathlib.Path
        Path to the TTTR file.
    tttr : object
        TTTR object with macro_times, micro_times, routing_channel, and header.macro_time_resolution.
    windows : dict
        Dictionary {window_name: (r_start, r_stop)}.
    detectors : dict
        Dictionary {det_name: {"chs": [...], "micro_time_ranges": [(mt_start, mt_stop), ...]}}.
    """
    df = generate_burst_dataframe(start_stop, filename, tttr, windows, detectors)
    write_dataframe_to_bur(df, bur_filename)


write_bur_file = write_bur_file_fast


def _read_burst_analysis_from_container(path: pathlib.Path) -> tuple:
    """Return ``(bursts, {name: TTTR})`` for one analysis in a `.pto`.

    The container equivalent of reading a burstwise folder, so every downstream
    burst analysis (BVA, 2CDE, H2MM, the MLEs) reaches the bursts through the
    call it already makes. Without it those steps could only open a directory,
    which is why the burst workflow was writing a `burst_analysis_handoff/`
    folder of `.bur` files to hand one over — a second copy of results that
    already existed in the file the photons came from, and one that went stale
    the moment the selection was re-run.

    The *path* handling is not here: which container, which run, and what a
    missing run should say are one scheme for every analysis and live in
    :mod:`chisurf.core.fio.analysis_path`. What is here is the burst-shaped
    part — that the companions join the search side by side, and that a caller
    indexing ``tttrs[row["First File"]]`` has to resolve.

    Parameters
    ----------
    path : pathlib.Path
        A `.pto`, or one analysis inside it
        (``m000.pto/countrate_All 0.2000#60``). Without a run the most recent
        analysis is taken.

    Returns
    -------
    tuple
        ``(store, tttrs)``.

    Raises
    ------
    FileNotFoundError
        If the container holds no burst table, or none under the named run.
    """
    from chisurf.core.fio.analysis_path import read_tables, split_container_path
    from chisurf.core.fio.fluorescence.burst_container import deinterleave_bursts
    from chisurf.core.fio.fluorescence.burst_tree import OPERATION, TABLE
    from chisurf.core.fio.staging import open_tttr

    container, _run = split_container_path(path)
    tables = read_tables(path, operation=OPERATION)
    # The container stores the `.bur` as that file holds it, interleave and all,
    # so the padding comes off here -- the same stride the folder reader applies
    # to the same rows. Storing the file 1:1 is what makes the two layouts
    # interchangeable; a table that had been trimmed on the way in could not
    # reproduce the file on the way out.
    df = None
    for name, table in tables.items():
        if name.endswith(".bur") or name == TABLE:
            df = deinterleave_bursts(table)
            break
    if df is None:
        # A run whose only tables are companions: nothing to hang them on.
        raise FileNotFoundError(
            f"{pathlib.Path(path).name} holds no burst table: run a burst "
            "search first, or point this at an analysis folder if one exists."
        )

    # Per-burst results computed from that search join it side by side — the
    # container's answer to the `…4` companions, matched on row count because
    # that is the contract those companions are written under.
    for name, companion in tables.items():
        if name.endswith(".bur") or name == TABLE:
            continue
        companion = deinterleave_bursts(companion)
        if row_count(companion) != row_count(df):
            continue
        df.append_columns(companion, tttrlib.DataStore.OnDuplicate_KeepFirst)

    # One container is one measurement, however many vendor files were packed
    # into it, so every burst points at the same photon stream. Keyed by each
    # distinct `First File` value so a caller's lookup resolves whichever name
    # the search recorded.
    tttr = open_tttr(str(container))
    names = set()
    if "First File" in column_names(df):
        names = {str(v) for v in np.asarray(df["First File"]).tolist()}
    names.add(container.name)
    return df, {name: tttr for name in names}


def read_burst_analysis(
    paris_path: pathlib.Path, tttr_file_type: str, pattern: str = "b*4*", row_stride: int = 1
) -> tuple:
    """
    Reads and processes burst analysis data files from a specified directory,
    constructs a pandas DataFrame with the concatenated data, and populates a
    dictionary containing TTTR (Time Tagging and Time Resolved) data.

    This function supports TTTR file types as defined by the tttrlib library and
    allows for flexible reading of files based on a specified glob pattern. It
    handles data from multiple files and can accommodate files generated by
    Seidel software, which may require skipping additional rows.

    Parameters
    ----------
    paris_path : pathlib.Path
        The path to the directory containing the burst analysis data files.
    tttr_file_type : str
        The file type for TTTR processing (e.g., 'PTU', 'HDF5', etc.), as supported by tttrlib.
    pattern : str, optional
        A glob pattern to match files in the directory. The default is 'b*4*',
        which will match files that start with 'b', contain '4', and have any extension.
    row_stride : int, optional
        The number of rows to skip between reads. The default is 1.
        If the data files are created by Seidel software (e.g., PARIS software),
        set `row_stride` to 2 to account for additional header rows that need to be skipped.

    Returns
    -------
    tuple
        A tuple containing:
        - A pandas DataFrame with the concatenated data from all matched files.
        - A dictionary with keys as filenames (from the 'First File' column) and values
          as TTTR data objects corresponding to those files.

    Raises
    ------
    FileNotFoundError
        If the specified `paris_path` does not exist or is not a directory.
    ValueError
        If any conversion to numeric fails for columns after the first file is processed.

    Examples
    --------
    >>> df, tttrs = read_burst_analysis(pathlib.Path('/path/to/data'), 'PTU', pattern='data*')  # doctest: +SKIP
    >>> print(df.head())  # doctest: +SKIP
    >>> print(tttrs.keys())  # doctest: +SKIP
    """

    def update_tttr_dict(data_path, tttrs: dict[str, tttrlib.TTTR] = dict()):
        """Load the TTTR file each distinct ``First File`` value names.

        One pass over the *distinct* names rather than over the burst rows: a
        measurement of 20 000 bursts names one file 20 000 times, and only the
        first of those is a load.

        Sentinel rows are skipped. A ``.bur`` table is ``2n+1`` interleaved and
        every other row carries ``"0"`` instead of a measurement name; tttrlib
        does not raise on the resulting non-existent path -- it prints a note and
        returns an *empty* object whose header reports a negative macro-time
        resolution. Caching that under the key ``"0"`` puts an empty measurement
        into a mapping whose whole purpose is to answer "which photons does this
        burst refer to".

        Parameters
        ----------
        data_path : Path
            Directory containing TTTR files.
        tttrs : dict
            Cache of {filename: tttrlib.TTTR}.

        Returns
        -------
        dict
            Updated cache dictionary.
        """
        from chisurf.core.fluorescence.burst.photons import is_sentinel_file_reference

        # dict.fromkeys, not set(): first-appearance order, so the first entry
        # is the first real measurement of the table.
        for ff in dict.fromkeys(np.asarray(df["First File"]).tolist()):
            if ff in tttrs or is_sentinel_file_reference(ff):
                continue
            tttrs[ff] = tttrlib.TTTR(str(data_path / str(ff)), tttr_file_type)
        return tttrs

    from chisurf.core.fio.fluorescence.burst_tree import is_container_path

    paris_path = pathlib.Path(paris_path)
    # A `.pto` is addressed like a folder, so the path may name a run inside it
    # ('m000.pto/countrate_All 0.2000#60') and is not a file on disk. Asking
    # `is_file()` therefore answers about the wrong thing.
    if is_container_path(paris_path):
        return _read_burst_analysis_from_container(paris_path)

    paris_path / "Info"
    data_path = paris_path.parent

    dfs = list()
    for path in paris_path.glob(pattern):
        stacked = list()
        for fn in sorted(path.glob("*")):
            with open(fn) as f:
                t = [line.rstrip("\n") for line in f.readlines()]
            header = t[0].split("\t")
            rows = [line.split("\t") for line in t[2::row_stride]]
            columns = list(zip(*rows)) if rows else [()] * len(header)
            stacked.append(
                store_from_arrays(
                    {name: np.array(col, dtype=object) for name, col in zip(header, columns)}
                )
            )
        dfs.append(concat_stores(stacked))
    # Each directory describes the SAME bursts, so they go side by side.
    df = dfs[0] if dfs else new_store()
    for other in dfs[1:]:
        df.append_columns(other, tttrlib.DataStore.OnDuplicate_KeepFirst)

    # Everything arrived as text; a column that is numeric becomes numeric, and
    # one that is not stays as it is rather than failing the whole read.
    typed = new_store()
    for name in column_names(df):
        values = np.asarray(df[name])
        numbers = numeric_column(df, name)
        typed.add(name, values if np.isnan(numbers).all() and values.size else numbers)
    typed.set_n_rows(row_count(df))
    df = typed

    tttrs = dict()
    update_tttr_dict(data_path, tttrs)
    return df, tttrs


def read_bur_file(bur_path):
    """Read a .bur file into a pandas DataFrame.

    Parameters
    ----------
    bur_path : str or Path
        Path to the .bur file.

    Returns
    -------
    tttrlib.DataStore
        One column per field, in the column's own dtype, with the text columns
        dictionary-encoded. Read the columns with
        :func:`chisurf.core.datastore.numeric_column` (or ``np.asarray`` for a
        text one); ask :func:`~chisurf.core.datastore.row_count` for the number
        of bursts, because ``len()`` does not answer that for a store.
    """
    from chisurf.core.datastore import read_csv_table

    bur_path = pathlib.Path(bur_path)
    if not bur_path.exists():
        raise FileNotFoundError(bur_path)
    store = read_csv_table(bur_path, delimiter="\t")
    if store is None:
        raise OSError(f"{bur_path} is not a tab-delimited burst table")
    return store


#: Per-burst companion files in the ``…4`` family, keyed to each ``.bur`` by stem:
#: ``bg4``/``br4``/``by4`` (background/red/yellow), ``bv4`` (BVA), ``td4`` (time
#: differences), ``2c4`` (2CDE). Same set ndX merges.
BURST_COMPANION_ENDINGS = ["bg4", "br4", "by4", "bv4", "td4", "2c4"]


def _companion_base(bur_path: pathlib.Path) -> pathlib.Path:
    """Return the analysis folder holding the ``…4`` companion subfolders.

    Companions live at ``<analysis>/<ending>/<stem>.<ending>`` beside the burst
    directory, so for ``<analysis>/bi4_bur/<stem>.bur`` the base is the parent of
    ``bi4_bur`` (``bur``); for a loose ``.bur`` it is the file's own directory.
    """
    parent = bur_path.parent
    return parent.parent if parent.name.lower() in ("bi4_bur", "bur") else parent


def _read_companion_table(path: pathlib.Path):
    """Read one ``…4`` companion file as a plain per-row table.

    ``.bur`` files and their ``…4`` companions share the same Seidel/PARIS
    ``2n+1`` interleaved layout (a header then alternating zero/value rows), so a
    companion is read the *same way* as the ``.bur`` (all rows) and aligned to it
    by position — the zero rows line up. Empty/unnamed trailing columns are
    dropped and values are coerced to numeric.
    """
    from chisurf.core.datastore import (
        column_names,
        numeric_column,
        read_csv_table,
        store_from_arrays,
    )

    store = read_csv_table(path, delimiter="\t")
    if store is None:
        raise OSError(f"{path} is not a tab-delimited companion table")
    return store_from_arrays(
        {
            name: numeric_column(store, name)
            for name in column_names(store)
            if name.strip() and not name.startswith("Unnamed")
        }
    )


def read_bur_with_companions(bur_path, endings=None):
    """Read a ``.bur`` file and column-merge its ``…4`` companions by stem.

    For a burst table ``<analysis>/bi4_bur/<stem>.bur`` this joins any
    ``<analysis>/<ending>/<stem>.<ending>`` companion (BVA ``bv4``, 2CDE ``2c4``,
    …) row-for-row, so consumers (the burst browser, headless analysis) see one
    per-burst table carrying the BVA/2CDE columns without a separate read. The
    ``.bur`` and its companions share the same ``2n+1`` interleaved layout, so
    they align by position. Missing or unreadable companions are skipped; new
    columns only are added (the ``.bur`` values win on name clashes); a companion
    is joined only when its row count matches the ``.bur``.

    Parameters
    ----------
    bur_path : str or Path
        Path to the ``.bur`` file.
    endings : list of str, optional
        Companion endings to look for. Defaults to the known ``…4`` family
        (:data:`BURST_COMPANION_ENDINGS`) unioned with any sibling directory whose
        name ends in ``4`` (so future companions merge with no code change).
    """
    from chisurf.core.datastore import column_names, row_count, take_columns

    bur_path = pathlib.Path(bur_path)
    df = read_bur_file(bur_path)
    base = _companion_base(bur_path)
    stem = bur_path.stem
    if endings is None:
        endings = list(BURST_COMPANION_ENDINGS)
        try:
            for child in base.iterdir():
                name = child.name.lower()
                if child.is_dir() and name.endswith("4") and name not in endings:
                    endings.append(name)
        except OSError:
            pass
    for ending in endings:
        companion = base / ending / f"{stem}.{ending}"
        if not companion.exists():
            continue
        try:
            extra = _read_companion_table(companion)
        except Exception:
            continue
        if row_count(extra) != row_count(df):
            continue
        # New columns only: the .bur's own values win a name clash.
        fresh = [c for c in column_names(extra) if c and c not in column_names(df)]
        if fresh:
            df.append_columns(take_columns(extra, fresh))
    return df


def write_burst_hdf5(dataframes, path) -> None:
    """Write one or more burst tables to a single columnar HDF5 file.

    One writer for what used to be three near-identical copies (the burst
    selection API, the BID-to-analysis converter and the photon-filter wizard),
    each of which built the same thing by hand: all-empty columns dropped,
    integers downcast, floats narrowed to ``float32``, and every text column
    replaced by ``int32`` category codes with the labels kept off to one side in
    a JSON attribute.

    That last step is what a store does natively — a text column *is* a
    dictionary and a code array — so the encoding is not built here at all, and
    the labels stay attached to the column instead of living in an attribute
    nothing in this tree ever read back. A reader therefore now sees
    ``First File`` as the file names rather than as integers it has no key for.

    Parameters
    ----------
    dataframes : sequence of tttrlib.DataStore
        Burst summary tables. They are concatenated; an empty sequence writes an
        empty table rather than failing, which is what a run that selected
        nothing produces.
    path : str or pathlib.Path
        Target ``.h5`` file.
    """
    from chisurf.core.datastore import write_table

    combined = concat_stores(list(dataframes))
    out = new_store()
    for name in column_names(combined):
        # A burst table ends in an UNNAMED column -- the trailing separator of
        # the `.bur` format read as a field. HDF5 cannot name a dataset that,
        # and nothing can ask for the column anyway.
        if not name.strip():
            continue
        values = np.asarray(combined[name])
        if values.dtype.kind == "f":
            # An all-empty column carries nothing and costs a dataset.
            if not np.isfinite(values).any():
                continue
            values = values.astype(np.float32)
        elif values.dtype.kind in "iu":
            values = values.astype(np.uint32 if (values >= 0).all() else np.int32)
        out.add(name, values)
    out.set_n_rows(row_count(combined))
    write_table(path, out)
