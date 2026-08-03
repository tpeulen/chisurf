"""Readers and writers for the ``.bur`` burst tables.

One column name in this format does not mean what it says, and it means the
same wrong thing in both writers here, so it is inherited rather than a slip:

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
from collections import OrderedDict

import numpy as np
import pandas as pd
import tttrlib

import chisurf as cs

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
        filename: pathlib.Path,
        analysis_dir: pathlib.Path,
        max_macro_time,
        append: bool = True
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
    parent_directory = analysis_dir / 'Info'
    parent_directory.mkdir(exist_ok=True, parents=True)

    # Search for any existing .mti files in the 'Info' folder
    existing_mti_files = list(parent_directory.glob("*.mti"))

    # If there are any existing .mti files, append to the first one found
    if existing_mti_files and append:
        mti_filename = existing_mti_files[0]
        mode = 'a'
    else:
        # If no .mti files are found or append is False, create a new file based on the filename
        mti_filename = parent_directory / f"{filename.stem}.mti"
        mode = 'w'

    # Write the filename and max_macro_time to the .mti file
    with open(mti_filename, mode) as mti_file:
        mti_file.write(f"{filename}\t{max_macro_time:.6f}\n")


def write_bv4_analysis(df: pd.DataFrame, analysis_folder: str = "analysis"):
    """
    Writes Burst Variance Analysis (BVA) results to .bv4 files in a 'bv4' subfolder inside the
    specified analysis folder. Each TTTR file will have a corresponding .bv4 file containing
    the mean and standard deviation of the proximity ratio for each burst.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame containing burst data with columns 'First File', 'Proximity Ratio Mean',
        and 'Proximity Ratio Std'.
    analysis_folder : str, optional
        The path to the folder where the 'bv4' subfolder will be created. Default is 'analysis'.
    """
    # Use pathlib to create the analysis/bv4 folder if it doesn't exist
    bv4_folder = pathlib.Path(analysis_folder) / "bv4"
    bv4_folder.mkdir(parents=True, exist_ok=True)

    # Iterate through the DataFrame and write results to individual .bv4 files
    for _, row in df.iterrows():
        # Create the corresponding .bv4 file name based on the 'First File' column
        tttr_stem = pathlib.Path(row['First File']).stem
        bv4_filename = bv4_folder / f"{tttr_stem}.bv4"

        # Prepare a mini DataFrame with the required columns for the .bv4 file
        data = {
            'Mean Proximity Ratio': [row['Proximity Ratio Mean']],
            'Standard Deviation': [row['Proximity Ratio Std']]  # Standard deviation
        }
        bv4_df = pd.DataFrame(data)

        # Write the mini DataFrame to a .bv4 file using tab as the separator
        bv4_df.to_csv(bv4_filename, sep='\t', index=False)

    cs.logging.info(f"BVA results have been written to .bv4 files in the '{bv4_folder}' directory.")


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


def write_bur_file_old(bur_filename, start_stop, filename, tttr, windows, detectors):
    """
    Write burst summary information to a TSV file (tab-separated),
    using a vectorized approach for efficiency.

    Modified to match a format where zero rows are interleaved between
    the computed rows and an extra (empty) column is added at the end.
    Ensures that even if there are no bursts, the output file contains
    a header row with the expected columns.

    :param bur_filename: Output filename for the TSV summary.
    :param start_stop: List of tuples (start_index, stop_index) defining bursts,
                       with stop_index the burst's last photon (inclusive).
    :param filename: String representing the file name.
    :param tttr: A TTTR-like object with:
                 - macro_times
                 - micro_times
                 - routing_channel
                 - header.macro_time_resolution
    :param windows: Dictionary {window_name: (r_start, r_stop)}
    :param detectors: Dictionary {det_name: {"chs": [...], "micro_time_ranges": [(mt_start, mt_stop), ...]}}
    """
    import numpy as np
    import pandas as pd

    # Unpack arrays and resolution
    n_ph = len(tttr)
    macro_times = tttr.macro_times
    micro_times = tttr.micro_times
    routing_channels = tttr.routing_channel
    res = tttr.header.macro_time_resolution

    # ---------------------------------------------------------
    # Precompute the full list of column headers
    # ---------------------------------------------------------
    static_cols = [
        "First Photon", "Last Photon", "Duration (ms)", "Mean Macro Time (ms)",
        "Number of Photons", "Count Rate (KHz)", "First File", "Last File"
    ]
    det_cols = []
    for det_name in detectors:
        det_cols += [
            f"First Photon ({det_name})", f"Last Photon ({det_name})",
            f"Duration ({det_name}) (ms)", f"Mean Macrotime ({det_name}) (ms)",
            f"Number of Photons ({det_name})", f"{det_name.capitalize()} Count Rate (KHz)"
        ]
    window_cols = []
    for window_name, (r_start, r_stop) in windows.items():
        for det_name in detectors:
            window_cols.append(
                f"S {window_name} {det_name} (kHz) | {r_start}-{r_stop}"
            )
    # Mean micro time per detector, appended after every pre-existing column and
    # before the trailing blank: a reader keying on leading positions is not
    # shifted, and ndX's trailing-blank strip still finds the blank.
    micro_cols = [f"Mean Microtime ({det_name}) (ns)" for det_name in detectors]
    micro_ns = micro_time_resolution_ns(tttr)
    # extra empty column
    header_keys = static_cols + det_cols + window_cols + micro_cols + [""]

    summary_rows = []

    # Helper: create a zero row dict
    def create_zero_row(keys):
        """Create a zero-filled OrderedDict row.

        Parameters
        ----------
        keys : list
            Column keys.

        Returns
        -------
        OrderedDict
        """
        row = OrderedDict()
        for key in keys:
            row[key] = "" if key == "" else 0
        return row

    # ---------------------------------------------------------
    # Iterate and build rows
    # ---------------------------------------------------------
    for start_idx, stop_idx in start_stop:
        # ``stop_idx`` is the burst's last photon (inclusive), so it must be a
        # valid index and every slice runs to ``stop_idx + 1``.
        if stop_idx >= n_ph or stop_idx < 0:
            continue

        burst_macro = macro_times[start_idx:stop_idx + 1]
        burst_micro = micro_times[start_idx:stop_idx + 1]
        burst_rout = routing_channels[start_idx:stop_idx + 1]

        if stop_idx <= start_idx:
            duration = mean_macro_time = n_photons = 0
        else:
            duration = (macro_times[stop_idx] - macro_times[start_idx]) * res
            mean_macro_time = ((macro_times[stop_idx] + macro_times[start_idx]) / 2.0) * res
            n_photons = stop_idx - start_idx + 1
        count_rate = (n_photons / duration) if duration > 0 else np.nan

        # base row data
        row_data = OrderedDict([
            ("First Photon", start_idx),
            ("Last Photon", stop_idx),
            ("Duration (ms)", duration * 1e3),
            ("Mean Macro Time (ms)", mean_macro_time * 1e3),
            ("Number of Photons", n_photons),
            ("Count Rate (KHz)", count_rate / 1e3),
            ("First File", filename),
            ("Last File", filename),
        ])

        # detector masks and per-detector stats
        detector_masks = {}
        for det_name, det_info in detectors.items():
            ch_mask = np.isin(burst_rout, det_info["chs"])
            detector_masks[det_name] = ch_mask & _micro_time_mask(
                burst_micro, det_info["micro_time_ranges"]
            )

        for det_name, mask in detector_masks.items():
            idxs = np.nonzero(mask)[0]
            if len(idxs) == 0:
                row_data.update({
                    f"First Photon ({det_name})": -1,
                    f"Last Photon ({det_name})": -1,
                    f"Duration ({det_name}) (ms)": -1.0,
                    f"Mean Macrotime ({det_name}) (ms)": -1.0,
                    f"Number of Photons ({det_name})": 0,
                    f"{det_name.capitalize()} Count Rate (KHz)": -1.0,
                })
            else:
                first_i, last_i = idxs[0], idxs[-1]
                dur_ms = (burst_macro[last_i] - burst_macro[first_i]) * res * 1e3
                mean_mt_ms = ((burst_macro[last_i] + burst_macro[first_i]) / 2.0) * res * 1e3
                rate_khz = (len(idxs) / dur_ms) if dur_ms > 0 else np.nan
                row_data.update({
                    f"First Photon ({det_name})": start_idx + first_i,
                    f"Last Photon ({det_name})": start_idx + last_i,
                    f"Duration ({det_name}) (ms)": dur_ms,
                    f"Mean Macrotime ({det_name}) (ms)": mean_mt_ms,
                    f"Number of Photons ({det_name})": len(idxs),
                    f"{det_name.capitalize()} Count Rate (KHz)": rate_khz,
                })

        # per-window, per-detector stats
        for window_name, (r_start, r_stop) in windows.items():
            w_mask = (burst_micro >= r_start) & (burst_micro < r_stop)
            for det_name in detectors:
                combined = detector_masks[det_name] & w_mask
                idxs = np.nonzero(combined)[0]
                key = f"S {window_name} {det_name} (kHz) | {r_start}-{r_stop}"
                if len(idxs) == 0:
                    row_data[key] = -1.0
                else:
                    dur_win_ms = (burst_macro[idxs[-1]] - burst_macro[idxs[0]]) * res * 1e3
                    row_data[key] = (len(idxs) / dur_win_ms) if dur_win_ms > 0 else np.nan

        # mean micro time per detector — inserted here so the dict's insertion
        # order matches ``header_keys`` (the frame takes its columns from the
        # rows, not from that list)
        for det_name, mask in detector_masks.items():
            row_data[f"Mean Microtime ({det_name}) (ns)"] = mean_micro_time_ns(
                burst_micro, np.nonzero(mask)[0], micro_ns
            )

        # append empty column
        row_data[""] = ""

        # interleave zero rows
        if not summary_rows:
            summary_rows.append(create_zero_row(header_keys))
        summary_rows.append(row_data)
        summary_rows.append(create_zero_row(header_keys))

    # ---------------------------------------------------------
    # Build DataFrame and write TSV, ensuring header is always present
    # ---------------------------------------------------------
    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
    else:
        summary_df = pd.DataFrame(columns=header_keys)
    summary_df.to_csv(bur_filename, sep='\t', index=False)


def generate_burst_dataframe(
        start_stop,
        filename,
        tttr,
        windows,
        detectors,
        include_interleaved_zeros=True,
        macro_time_resolution=None
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
    pd.DataFrame
        DataFrame containing burst summary information.
    """
    file_name_only = pathlib.Path(filename).name

    # unpack
    macro = tttr.macro_times
    micro = tttr.micro_times
    rout  = tttr.routing_channel
    res   = tttr.header.macro_time_resolution if macro_time_resolution is None else float(macro_time_resolution)
    n_ph  = len(tttr)

    # build column list
    static_cols = [
        "First Photon", "Last Photon", "Duration (ms)", "Mean Macro Time (ms)",
        "Number of Photons", "Count Rate (KHz)", "Confidence (sigma)",
        "First File", "Last File",
    ]
    det_cols = []
    for d in detectors:
        det_cols += [
            f"First Photon ({d})", f"Last Photon ({d})",
            f"Duration ({d}) (ms)", f"Mean Macrotime ({d}) (ms)",
            f"Number of Photons ({d})", f"{d.capitalize()} Count Rate (KHz)",
        ]
    win_cols = []
    for w,(r0,r1) in windows.items():
        for d in detectors:
            win_cols.append(f"S {w} {d} (kHz) | {r0}-{r1}")
    # Mean micro time per detector, appended last (see write_bur_file_old)
    micro_cols = [f"Mean Microtime ({d}) (ns)" for d in detectors]
    micro_ns = micro_time_resolution_ns(tttr)
    # extra blank column
    cols = static_cols + det_cols + win_cols + micro_cols + [""]

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

    # map col→index for fast assignment
    idx = {c:i for i,c in enumerate(cols)}
    n_cols = len(cols)

    # precompute global masks so we don't remake them per-burst
    # Detector/window micro-time ranges are always expressed in raw micro-time
    # channels (the same units as ``micro``); micro-time binning is a display-only
    # concern and never rescales these ranges.
    det_global = {}
    for d,info in detectors.items():
        chm = np.isin(rout, info["chs"])
        det_global[d] = chm & _micro_time_mask(micro, info["micro_time_ranges"])

    win_global = {
        w: (micro >= r0) & (micro < r1)
        for w,(r0,r1) in windows.items()
    }

    # helper zero-row
    zero_row = [0]*n_cols
    zero_row[-1] = ""  # last col blank string

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
        if stop <= start or stop>=n_ph or start<0:
            continue

        # allocate a fresh row
        row = zero_row.copy()

        # static stats — ``stop`` is the burst's last photon (inclusive), so the
        # photon at ``stop`` counts and every slice below runs to ``stop + 1``.
        dur   = (macro[stop] - macro[start]) * res * 1e3
        meanm = ((macro[stop] + macro[start]) / 2) * res * 1e3
        npix  = stop - start + 1
        # ``dur`` is milliseconds, so photons-per-``dur`` is already kHz — the
        # unit the "Count Rate (KHz)" header and the per-detector rates below
        # are written in. Do not scale again.
        crate = (npix / dur) if dur>0 else np.nan

        row[idx["First Photon"]]          = start
        row[idx["Last Photon"]]           = stop
        row[idx["Duration (ms)"]]         = dur
        row[idx["Mean Macro Time (ms)"]]  = meanm
        row[idx["Number of Photons"]]     = npix
        row[idx["Count Rate (KHz)"]]      = crate
        # Indexed by position in start_stop, not by output row: skipped bursts
        # never reach here, so the two would otherwise drift apart.
        if confidence is not None and burst_index < confidence.size:
            row[idx["Confidence (sigma)"]] = confidence[burst_index]
        row[idx["First File"]]            = file_name_only
        row[idx["Last File"]]             = file_name_only

        # slice views
        sl = slice(start, stop + 1)
        micro_sl = micro[sl]
        for d in detectors:
            mask = det_global[d][sl]
            idxs = np.nonzero(mask)[0]
            row[idx[f"Mean Microtime ({d}) (ns)"]] = mean_micro_time_ns(
                micro_sl, idxs, micro_ns
            )
            col0 = f"First Photon ({d})"
            if idxs.size == 0:
                # these get -1 or 0 per your original logic
                row[idx[col0]]                             = -1
                row[idx[f"Last Photon ({d})"]]            = -1
                row[idx[f"Duration ({d}) (ms)"]]           = -1.0
                row[idx[f"Mean Macrotime ({d}) (ms)"]]     = -1.0
                row[idx[f"Number of Photons ({d})"]]       = 0
                row[idx[f"{d.capitalize()} Count Rate (KHz)"]] = -1.0
            else:
                i0, i1 = idxs[0], idxs[-1]
                abs0, abs1 = start + i0, start + i1
                d_ms = (macro[abs1] - macro[abs0]) * res * 1e3
                m_ms = ((macro[abs1] + macro[abs0]) / 2) * res * 1e3
                rate = (idxs.size / d_ms) if d_ms>0 else np.nan

                row[idx[col0]]                             = abs0
                row[idx[f"Last Photon ({d})"]]            = abs1
                row[idx[f"Duration ({d}) (ms)"]]           = d_ms
                row[idx[f"Mean Macrotime ({d}) (ms)"]]     = m_ms
                row[idx[f"Number of Photons ({d})"]]       = idxs.size
                row[idx[f"{d.capitalize()} Count Rate (KHz)"]] = rate

        # now per-window, per-detector
        for w in windows:
            wmask = win_global[w][sl]
            for d in detectors:
                combined = det_global[d][sl] & wmask
                idxs = np.nonzero(combined)[0]
                key = f"S {w} {d} (kHz) | {windows[w][0]}-{windows[w][1]}"
                if idxs.size == 0:
                    row[idx[key]] = -1.0
                else:
                    abs0, abs1 = start+idxs[0], start+idxs[-1]
                    d_ms = (macro[abs1] - macro[abs0]) * res * 1e3
                    row[idx[key]] = (idxs.size / d_ms) if d_ms>0 else np.nan

        # blank column already set to ""
        out.append(row)
        # Only add trailing zero row if interleaved zeros are requested
        if include_interleaved_zeros:
            out.append(zero_row.copy())

    # build DataFrame
    return pd.DataFrame(out, columns=cols)


def write_dataframe_to_bur(df, bur_filename):
    """
    Write a DataFrame to a .bur file (tab-separated values).
    
    Parameters
    -----------
    df : pd.DataFrame
        DataFrame containing burst summary information.
    bur_filename : str or pathlib.Path
        Path to the output .bur file.
    """
    df.to_csv(bur_filename, sep="\t", index=False)


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

def read_burst_analysis(
        paris_path: pathlib.Path,
        tttr_file_type: str,
        pattern: str = 'b*4*',
        row_stride: int = 1
) -> (pd.DataFrame, dict[str, tttrlib.TTTR]):
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
    Tuple[pd.DataFrame, Dict[str, tttrlib.TTTR]]
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
        """Load TTTR files not yet in the cache dictionary.

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
        for ff, fl in zip(df['First File'], df['Last File']):
            try:
                tttr = tttrs[ff]
            except KeyError:
                fn = str(data_path / ff)
                tttr = tttrlib.TTTR(fn, tttr_file_type)
                tttrs[ff] = tttr
        return tttrs

    info_path = paris_path / 'Info'
    data_path = paris_path.parent

    dfs = list()
    is_first_file = True  # Flag to track the first file
    for path in paris_path.glob(pattern):
        frames = list()
        for fn in sorted(path.glob('*')):
            with open(fn) as f:
                t = f.readlines()
                t = [line.rstrip('\n') for line in t]  # Remove trailing newlines
                h = t[0].split('\t')
                d = [[x for x in l.split('\t')] for l in t[2::row_stride]]
                frames.append(pd.DataFrame(d, columns=h))
        dfs.append(pd.concat(frames))
    df = pd.concat(dfs, axis=1)

    # Loop through each column and attempt to convert to numeric
    for column in df.columns:
        try:
            df[column] = pd.to_numeric(df[column])
        except ValueError:
            if not is_first_file:  # Ignore conversion errors only for the first file
                cs.logging.warning(f"read_burst_analysis: Could not convert {column} to numeric")
        is_first_file = False  # After processing the first file, set flag to False

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
    pd.DataFrame
        DataFrame containing the burst data.
    """
    bur_path = pathlib.Path(bur_path)
    if not bur_path.exists():
        raise FileNotFoundError(bur_path)
    return pd.read_csv(bur_path, sep="\t")


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


def _read_companion_table(path: pathlib.Path) -> pd.DataFrame:
    """Read one ``…4`` companion file as a plain per-row table.

    ``.bur`` files and their ``…4`` companions share the same Seidel/PARIS
    ``2n+1`` interleaved layout (a header then alternating zero/value rows), so a
    companion is read the *same way* as the ``.bur`` (all rows) and aligned to it
    by position — the zero rows line up. Empty/unnamed trailing columns are
    dropped and values are coerced to numeric.
    """
    frame = pd.read_csv(path, sep="\t")
    keep = [
        c for c in frame.columns
        if str(c).strip() and not str(c).startswith("Unnamed")
    ]
    frame = frame[keep]
    return frame.apply(pd.to_numeric, errors="coerce")


def read_bur_with_companions(bur_path, endings=None) -> pd.DataFrame:
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
        if len(extra) != len(df):
            continue
        for col in extra.columns:
            if col and col not in df.columns:
                df[col] = extra[col].values
    return df
