"""The engine of the burst-MLE lifetime analysis (cards ML0 and ML1).

The steps of the analysis are functions of explicit inputs and a session object that
holds the state those widgets held (detectors, burst files, the micro-time window, the IRF / background patterns, the
fit settings). ``tests/test_mle_engine.py`` checks the session on the in-repository BH sample against what each
number must be by construction.

No GUI toolkit is imported here.
"""

from __future__ import annotations

import collections.abc
import copy
import dataclasses
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from chisurf.core.datastore import (
    column_names,
    concat_stores,
    numeric_column,
    row_count,
    set_constant,
    take_where,
)
from chisurf.core.fluorescence.channels import channel_mask
from chisurf.core.support.i18n import tr

from .fit_display import DecayCurves, TailFitResult, decay_curves
from .interpolate import interpolate_shift


# --------------------------------------------------------------------------------------------------------------------
# pure steps (the session composes these)
# --------------------------------------------------------------------------------------------------------------------
def _is_container(path: Any) -> bool:
    """Whether *path* names a ``.pto`` (or a run in one) rather than a ``.bur`` file."""
    from chisurf.core.fio.analysis_path import is_container_path

    return is_container_path(path)


def _burst_file_stem(path: Any) -> str:
    """The measurement stem a burst input stands for: the container's for a run in a ``.pto``, the file's otherwise."""
    if _is_container(path):
        from chisurf.core.fio.analysis_path import split_container_path

        container = split_container_path(path)[0]
        if container is not None:
            return container.stem
    return Path(path).stem


def read_burst_container(path: Any) -> tuple[Any, Path]:
    """Read one run of a measurement container into the burst table the session works on.

    The container twin of :func:`read_burst_analysis`: the bursts and the photons are both in the one ``.pto``, so
    there is no folder to search and the raw file *is* the container.

    Parameters
    ----------
    path : str or Path
        A ``.pto``, or a run in one (``m000.pto/<run>``); without a run the most recent burst search is read.

    Returns
    -------
    table : tttrlib.DataStore
        The bursts, tagged with ``burst_file`` and the resolved identities ``_burst_path`` (the path as given) and
        ``_measurement_path`` -- the *run* read (``m.pto/<run>``, named even when *path* named none), because that
        identity is what a fit result is written back under: two searches of one container are two measurements
        of burst grid, and the fits of each are derived from their own.
    container : Path
        The resolved container, which is also the measurement's photon source.
    """
    from chisurf.core.fio.analysis_path import split_container_path
    from chisurf.core.fio.fluorescence.burst import _read_burst_analysis_from_container
    from chisurf.core.fio.fluorescence.burst_tree import RUN_COLUMN

    found, _run = split_container_path(path)
    if found is None:
        raise ValueError(f"not a measurement container: {path}")
    table, _tttrs = _read_burst_analysis_from_container(Path(path))
    container = found.resolve()
    n = row_count(table)
    run = (
        split_container_path(str(np.asarray(table[RUN_COLUMN], dtype=object)[0]))[1] if n else _run
    )
    set_constant(table, "burst_file", Path(path).name)
    set_constant(table, "_burst_path", str(Path(path).resolve()))
    table["_measurement_path"] = [str(container / run) if run else str(container)] * n
    return table, container




def burst_photon_indices(df_bursts: Any, current_filename: str, *, as_array: bool = False):
    """Photon indices of every burst of the file *current_filename* (a ``.bur`` file), merged and ascending."""
    if not current_filename or df_bursts is None:
        return []
    # Read only: the table is shared with the fit's snapshot (computing the stems into a column of
    # it made every job copy the whole table first).
    if "stem" in column_names(df_bursts):
        stems = np.asarray(df_bursts["stem"], dtype=object)
    else:
        files = np.asarray(df_bursts["First File"], dtype=object)
        names, inverse = np.unique(files.astype(str), return_inverse=True)
        stems = np.asarray(
            [re.split(r"[\\/]", str(v))[-1].rsplit(".", 1)[0] for v in names], dtype=object
        )[inverse]
    curr_stem = _burst_file_stem(current_filename)
    mask = stems == curr_stem
    if not mask.any():
        return []
    starts = numeric_column(df_bursts, "First Photon")[mask].astype(np.int32)
    stops = numeric_column(df_bursts, "Last Photon")[mask].astype(np.int32)
    idxs = np.concatenate([starts, stops + 1])
    weights = np.concatenate(
        [np.ones_like(starts, dtype=np.int32), -np.ones_like(stops + 1, dtype=np.int32)]
    )
    events = np.bincount(idxs, weights, minlength=idxs.max() + 1)
    coverage = np.cumsum(events)[:-1] > 0
    found = np.nonzero(coverage)[0]
    return found if as_array else found.tolist()


def header_time_ns(tttr: Any, binning: int) -> tuple[float, float] | None:
    """``(dt_ns, period_ns)`` from a TTTR header: the channel width at *binning* and one excitation period."""
    if tttr is None:
        return None
    try:
        from chisurf.core.fio.micro_time import channels_per_period

        h = tttr.header
        micro_s = float(h.micro_time_resolution)
        # one excitation period -- not the TDC range the header names (32768 on a MultiHarp: a
        # 2.6 us "period" at 80 ps, where the laser runs at 40 ns)
        n_chan = float(channels_per_period(tttr))
    except Exception:
        return None
    if not (micro_s > 0.0 and n_chan > 0.0):
        return None
    return micro_s * 1e9 * max(1, int(binning)), n_chan * micro_s * 1e9


def effective_timing_ns(
    tttr: Any, binning: int, reading: dict
) -> tuple[float | None, float | None]:
    """Use per-file physical timing unless an explicit ps/ns calibration overrides it."""
    physical = header_time_ns(tttr, binning)
    dt, period = physical if physical is not None else (None, None)
    if reading.get("override_timing") or physical is None:
        micro = float(reading.get("micro_time_resolution", 0.0) or 0.0)
        macro = float(reading.get("macro_time_resolution", 0.0) or 0.0)
        if micro > 0.0:
            dt = micro * 1e-3 * max(1, int(binning))
        if macro > 0.0:
            period = macro
    return dt, period


def window_bins(
    detector_ranges: Any, micro_time_range: tuple[int, int], binning: int, n_channels: int = 1
) -> tuple[int, int, int, int]:
    """Per-polarisation ``(vv_start, vv_stop, vh_start, vh_stop)`` in binned channels.

    ``micro_time_ranges`` mean what they mean in the step-0 setup: the detector's gates, for all of its
    channels. The fit window is the window *micro_time_range* (Window start / stop, in bins) inside the
    first gate: the gate says which photons are the detector's (PIE), the window which of them are
    fitted, so narrowing it narrows the fit. Without gates the window alone applies. *n_channels* is
    accepted for call-site symmetry and not used.
    """
    sb, eb = int(micro_time_range[0]), int(micro_time_range[1])
    ranges = [r for r in (detector_ranges or []) if r is not None and len(r) >= 2]
    if not ranges:
        return (sb, eb, sb, eb)
    b = max(1, int(binning))
    lo, hi = int(ranges[0][0] // b), int(ranges[0][1] // b)
    if eb > sb:
        lo, hi = max(lo, sb), min(hi, eb)
        if hi <= lo:  # a window outside the gate: the gate (an empty fit says nothing)
            lo, hi = int(ranges[0][0] // b), int(ranges[0][1] // b)
    return (lo, hi, lo, hi)


def vv_vh_histogram(
    tttr: Any,
    detector_chs: list[int],
    micro_time_range: tuple[int, int],
    binning: int,
    *,
    detector_ranges: Any = None,
    shift: int = 0,
    threshold: Any = -1,
    normalize_counts: int = 1,
    apply_vh_shift: bool = True,
    cut: bool = True,
) -> np.ndarray:
    """The VV | VH micro-time histogram of *tttr*.

    *cut* zeroes everything outside the fit window and below the thresholds -- what is fitted;
    ``False`` keeps every channel -- what is shown."""
    vv_sb, vv_eb, vh_sb, vh_eb = window_bins(
        detector_ranges, micro_time_range, binning, len(detector_chs)
    )

    def photons(chs):
        return tttr[np.where(channel_mask(tttr.routing_channels, chs))[0]]

    if len(detector_chs) >= 2:
        tp, ts = photons(detector_chs[::2]), photons(detector_chs[1::2])
    else:
        tp = ts = photons(detector_chs)
    from chisurf.core.fio.micro_time import channels_per_period, period_histogram

    period = channels_per_period(tttr)  # one excitation period, whatever the header's TDC range
    cp = period_histogram(tp, binning, period=period)
    cs_hist = period_histogram(ts, binning, period=period)
    if apply_vh_shift and shift != 0:
        cs_hist = np.roll(cs_hist, shift)
    if apply_vh_shift and cut:
        if vv_sb > 0:
            cp[:vv_sb] = 0
        if vv_eb < cp.size:
            cp[vv_eb:] = 0
        if vh_sb > 0:
            cs_hist[:vh_sb] = 0
        if vh_eb < cs_hist.size:
            cs_hist[vh_eb:] = 0
        th_vv = th_vh = -1.0
        if isinstance(threshold, (tuple, list)) and len(threshold) >= 2:
            th_vv = float(threshold[0]) if threshold[0] is not None else -1.0
            th_vh = float(threshold[1]) if threshold[1] is not None else -1.0
        if th_vv > 0 and cp.size and cp.max() > 0:
            cp[cp < th_vv * cp.max()] = 0
        if th_vh > 0 and cs_hist.size and cs_hist.max() > 0:
            cs_hist[cs_hist < th_vh * cs_hist.max()] = 0
    if normalize_counts == 1:
        ct = (cp.sum() + cs_hist.sum()) / 2.0
        if ct > 0:
            cp /= ct
            cs_hist /= ct
    elif normalize_counts == 2:
        if cp.sum() > 0:
            cp = cp / cp.sum()
        if cs_hist.sum() > 0:
            cs_hist = cs_hist / cs_hist.sum()
    elif normalize_counts == 3:
        acquisition_time = (
            tttr.macro_times[-1] - tttr.macro_times[0]
        ) * tttr.header.macro_time_resolution
        if acquisition_time > 0:
            cs_hist /= acquisition_time
            cp /= acquisition_time
    return np.hstack([cp, cs_hist])


def process_irf(
    arr: np.ndarray | None,
    *,
    micro_time_range: tuple[int, int],
    binning: int,
    shift: float = 0.0,
    shift_sp: float = 0.0,
    shift_ss: float = 0.0,
    irf_start: int = -1,
    irf_stop: int = -1,
    threshold_vv: float = -1.0,
    threshold_vh: float = -1.0,
) -> np.ndarray:
    """The IRF as the fit sees it: VH rolled, sub-bin shifted, windowed and thresholded."""
    if arr is None:
        length = max(2, (micro_time_range[1] // binning) * 2)
        arr = np.zeros(length, dtype=np.float64)
        arr[0] = 1.0
        arr[length // 2] = 1.0
    half = len(arr) // 2
    sp = arr[:half].astype(np.float64)
    ss = arr[half:].astype(np.float64)
    if float(shift) != 0.0:
        ss = np.roll(ss, int(round(shift)))
    sp = interpolate_shift(sp, shift_sp)
    ss = interpolate_shift(ss, shift_ss)
    start, stop = int(irf_start), int(irf_stop)
    if start >= 0:
        sp[: max(0, start)] = 0
        ss[: max(0, start)] = 0
    if stop >= 0 and stop + 1 < sp.size:
        sp[stop + 1 :] = 0
    if stop >= 0 and stop + 1 < ss.size:
        ss[stop + 1 :] = 0
    if threshold_vv > 0 and sp.size and sp.max() > 0:
        sp[sp < threshold_vv * sp.max()] = 0
    if threshold_vh > 0 and ss.size and ss.max() > 0:
        ss[ss < threshold_vh * ss.max()] = 0
    return np.hstack([sp, ss])


def process_background(arr: np.ndarray | None, shift: int, like: np.ndarray) -> np.ndarray:
    """The background pattern with the VH half rolled by *shift* (zeros of the IRF's length when none is loaded)."""
    if arr is None:
        return np.zeros_like(like)
    arr = np.asarray(arr, dtype=np.float64)
    half = len(arr) // 2
    vv = arr[:half].copy()
    vh = arr[half:].copy()
    if shift != 0:
        vh = np.roll(vh, int(shift))
    return np.hstack([vv, vh])


def select_fit_range(decay: np.ndarray | None, lo_frac: float = 0.02) -> tuple[int, int] | None:
    """The filled region of a decay as a ``(start, stop)`` window in binned channels (``None`` when it is empty)."""
    if decay is None:
        return None
    d = np.asarray(decay, dtype=float)
    nb = d.size // 2
    if nb < 4:
        return None
    tot = d[:nb] + d[nb : 2 * nb]
    pk = float(tot.max()) if tot.size else 0.0
    if pk <= 0.0:
        return None
    filled = np.where(tot > lo_frac * pk)[0]
    if filled.size == 0:
        return None
    onset = int(max(0, int(filled[0]) - 1))
    last = int(min(nb, int(filled[-1]) + 2))
    if last - onset < 4:
        return None
    return onset, last


def irf_fwhm_channels(tttr: Any, chs: list[int], burst_idx: np.ndarray) -> int | None:
    """FWHM (raw channels) of the scatter prompt of the photons outside the bursts, or ``None``."""
    if tttr is None or not chs or np.asarray(burst_idx).size == 0:
        return None
    try:
        from chisurf.core.fio.micro_time import channels_per_period

        n_full = int(channels_per_period(tttr))
    except Exception:
        return None
    if n_full <= 0:
        return None
    non_burst = np.ones(len(tttr), dtype=bool)
    non_burst[np.asarray(burst_idx, dtype=int)] = False
    sel = non_burst & channel_mask(tttr.routing_channels, chs)
    micro = np.asarray(tttr.micro_times)[sel]
    micro = micro[(micro >= 0) & (micro < n_full)]
    if micro.size == 0:
        return None
    hist = np.bincount(micro, minlength=n_full)[:n_full].astype(float)
    return peak_fwhm_channels(hist)


def peak_fwhm_channels(hist: np.ndarray) -> int | None:
    """Width (channels) of the contiguous run above half maximum around the histogram's peak.

    The run may wrap round the period's end (a pulse at its last channels decays into the first).
    Measuring from the first to the last channel above half maximum anywhere -- as this did --
    spans the gap between two PIE pulses, or a pulse and its wrapped decay: the "IRF" came out
    thousands of channels wide, and the binning chosen from it left ~15 bins per period, so sparse
    bursts fitted to tau ~ 0.
    """
    hist = np.asarray(hist, dtype=float)
    n = hist.size
    if n == 0:
        return None
    peak = int(np.argmax(hist))
    half = 0.5 * hist[peak]
    if half <= 0:
        return None
    width = 1
    for step in (-1, 1):
        i = peak
        for _ in range(n - 1):
            i = (i + step) % n
            if hist[i] < half or width >= n:
                break
            width += 1
    return int(min(width, n))


def select_binning(
    tttr: Any,
    chs: list[int],
    burst_idx: np.ndarray,
    choices: list[int],
    *,
    target_counts_per_bin: float = 10.0,
    irf_oversample: float = 8.0,
) -> int | None:
    """A micro-time binning that is neither too fine (sparse bins) nor finer than the IRF resolves.

    Returns one of *choices*, or ``None`` when the photon count cannot be determined.
    """
    burst_idx = np.asarray(burst_idx, dtype=int)
    if tttr is None or not chs or burst_idx.size == 0:
        return None
    counts = int(
        channel_mask(np.asarray(tttr.routing_channels)[burst_idx], chs).sum()
    )
    try:
        from chisurf.core.fio.micro_time import channels_per_period

        n_full = int(channels_per_period(tttr))
    except Exception:
        return None
    if counts <= 0 or n_full <= 0:
        return None
    need_stat = target_counts_per_bin * 2.0 * n_full / counts
    fwhm = irf_fwhm_channels(tttr, chs, burst_idx)
    need_irf = (fwhm / irf_oversample) if (fwhm and irf_oversample > 0) else 0.0
    need = max(need_stat, need_irf)
    # Lifetimes need resolution: never fewer than MIN_BINS_PER_PERIOD bins across the laser period,
    # whatever the statistics ask for (a sparse decay is the fit's job, not the binning's).
    coarsest = max(1, n_full // MIN_BINS_PER_PERIOD)
    ordered = sorted(int(c) for c in choices)
    allowed = [c for c in ordered if c <= coarsest] or ordered[:1]
    for c in allowed:
        if c >= need:
            return c
    return allowed[-1]


#: The coarsest automatic binning keeps at least this many micro-time bins per laser period.
MIN_BINS_PER_PERIOD = 64


def burst_result_columns(color: str, model: str, param_names) -> list:
    """Per-detector export columns for ``model`` (matches the worker rows).

    ``fit23`` keeps its historical column order so the ``.b?4`` export is
    unchanged; other fit2x models write ``Tau`` (the best lifetime) followed
    by one column per registry free parameter, then the flags.
    """
    if model == "fit23":
        return [
            "Ng-p-all",
            "Ng-s-all",
            f"Number of Photons (fit window) ({color})",
            f"2I*  ({color})",
            f"Tau ({color})",
            f"gamma ({color})",
            f"r0 ({color})",
            f"rho ({color})",
            f"BIFL scatter? ({color})",
            f"2I*: P+2S? ({color})",
            f"r Scatter ({color})",
            f"r Experimental ({color})",
        ]
    cols = [
        "Ng-p-all",
        "Ng-s-all",
        f"Number of Photons (fit window) ({color})",
        f"2I*  ({color})",
        f"Tau ({color})",
    ]
    cols += [f"{nm} ({color})" for nm in param_names]
    cols += [f"{name} ({color})" for name in fit_result_names(model)]
    cols += [f"BIFL scatter? ({color})", f"2I*: P+2S? ({color})"]
    return cols


def state_result_columns(color: str, model: str, param_names, n_states: int) -> list:
    """The all-photon columns, then one suffixed block per state.

    A sub-population of a burst is a *column* of that burst's row: the burst
    table has one row per burst, and every companion is merged onto it by
    position. The suffixed names must not collide with the all-photon ones,
    because the merge drops a duplicate name and its data with it.
    """
    cols = burst_result_columns(color, model, param_names)
    for state in range(int(n_states)):
        sfx = f" S{state}"
        cols += [
            f"Ng-p{sfx}",
            f"Ng-s{sfx}",
            f"Number of Photons (fit window){sfx} ({color})",
            f"2I*{sfx} ({color})",
            f"Tau{sfx} ({color})",
        ]
        if model == "fit23":
            cols += [f"gamma{sfx} ({color})", f"r0{sfx} ({color})", f"rho{sfx} ({color})"]
        else:
            cols += [f"{nm}{sfx} ({color})" for nm in (param_names or ())]
            cols += [f"{name}{sfx} ({color})" for name in fit_result_names(model)]
        cols += [f"BIFL scatter?{sfx} ({color})", f"2I*: P+2S?{sfx} ({color})"]
        if model == "fit23":
            cols += [f"r Scatter{sfx} ({color})", f"r Experimental{sfx} ({color})"]
    return cols


def coerce_float(value) -> float:
    """*value* as a float, or ``nan`` for anything that is not one (a column a model did not emit)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def write_b4_tables(
    results, files_by_stem, det_meta, channel_settings, *, on_new_folder=None, tick=None
):
    """Write the ``b?4`` burst-fit tables (zero-interleaved, one per measurement and detector).

    Parameters
    ----------
    results : list of dict
        Batch rows carrying ``First Stem`` and ``Detector``.
    files_by_stem : mapping
        File stem -> the ``.bur`` file; the tables go to ``<analysis>/b<letter>4/<stem>.b<letter>4``.
    det_meta : mapping
        Detector -> ``(colour, letter, columns)``.
    channel_settings : mapping
        Written once per folder as ``channel_settings.json`` (the instrument description).
    on_new_folder : callable, optional
        Called with each output folder the first time it is written to.
    tick : callable, optional
        ``tick(done) -> bool``; ``True`` cancels (the function then returns ``None``).

    Returns
    -------
    tuple or None
        ``(files written, {stem: {detector: table}}, folder names)``, or ``None`` when cancelled.
    """
    import json

    from chisurf.core.datastore import store_from_arrays

    groups: dict[tuple, list[dict]] = {}
    for row in results:
        groups.setdefault((row["First Stem"], row.get("Detector")), []).append(row)
    written_dirs: set[str] = set()
    wrote_settings_for: set = set()
    written_files: list[Path] = []
    by_stem: dict[str, dict[str, Any]] = {}
    done = 0
    for (stem, det), rows_g in groups.items():
        meta = det_meta.get(det)
        file_path = files_by_stem.get(stem)
        if meta is None or file_path is None:
            done += 1
            if tick is not None and tick(done):
                return None
            continue
        color, letter, cols = meta
        out_dir = Path(file_path).parent.parent / f"b{letter}4"
        out_dir.mkdir(parents=True, exist_ok=True)
        written_dirs.add(out_dir.name)
        arr = np.array([[coerce_float(row.get(c)) for c in cols] for row in rows_g], dtype=float)
        by_stem.setdefault(stem, {})[det] = store_from_arrays(
            {c: arr[:, i] for i, c in enumerate(cols)}
        )
        out = np.zeros((arr.shape[0] * 2 + 1, arr.shape[1]), dtype=float)
        out[1::2] = arr
        out_file = out_dir / f"{Path(file_path).stem}.b{letter}4"
        written_files.append(out_file)
        with open(out_file, "w", newline="") as f:
            f.write("\t".join(cols) + "\t\n")  # the trailing tab and newline are part of the format
            np.savetxt(f, out, delimiter="\t", fmt="%.6f")
        if out_dir not in wrote_settings_for:
            with open(out_dir / "channel_settings.json", "w") as sf:
                json.dump(channel_settings, sf, indent=4, cls=NumpyEncoder)
            wrote_settings_for.add(out_dir)
            if on_new_folder is not None:
                on_new_folder(out_dir)
        done += 1
        if tick is not None and tick(done):
            return None
    return written_files, by_stem, written_dirs


def write_container_tables(
    results, det_meta, parameters, *, state_rows=None, experiment=None, tick=None
):
    """Write the per-burst fits of measurements that live in a ``.pto`` into that container.

    The container twin of :func:`write_b4_tables`: no ``b?4`` folder, no ``channel_settings.json`` -- one object per
    detector at burst grain (plus the pooled states and the IRF / background curves), in the container the bursts
    were read from.

    Parameters
    ----------
    results : list of dict
        Batch rows carrying ``First Stem`` (the container path) and ``Detector``.
    det_meta : mapping
        Detector -> ``(colour, letter, columns)``.
    parameters : mapping
        The fit settings; their hash is the identity of the run.
    state_rows, experiment : optional
        Forwarded to :func:`~.core.export.write_mle_container`.
    tick : callable, optional
        ``tick(done) -> bool``; ``True`` cancels (the function then returns ``None``).

    Returns
    -------
    list of Path or None
        The containers written, or ``None`` when cancelled.
    """
    from chisurf.core.datastore import store_from_arrays

    from .core.export import write_mle_container

    groups: dict[tuple, list[dict]] = {}
    for row in results:
        groups.setdefault((row["First Stem"], row.get("Detector")), []).append(row)
    tables: dict[str, dict[str, Any]] = {}
    done = 0
    for (container, det), rows_g in groups.items():
        meta = det_meta.get(det)
        if meta is not None:
            cols = meta[2]
            arr = np.array(
                [[coerce_float(row.get(c)) for c in cols] for row in rows_g], dtype=float
            )
            tables.setdefault(container, {})[det] = store_from_arrays(
                {c: arr[:, i] for i, c in enumerate(cols)}
            )
        done += 1
        if tick is not None and tick(done):
            return None
    return [
        Path(
            write_mle_container(
                container,
                by_det,
                state_rows=state_rows,
                experiment=experiment,
                parameters=parameters,
            )
        )
        for container, by_det in tables.items()
    ]


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that writes numpy arrays as lists."""

    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def burst_histogram(
    burst: Any, chs: list[int], micro_time_range: tuple[int, int], binning: int
) -> np.ndarray:
    """VV | VH micro-time histogram of one burst, zeroed outside the window (what the inspected-burst plot shows)."""
    pchs = chs[::2]
    schs = chs[1::2] if len(chs) > 1 else chs
    sb, eb = micro_time_range
    from chisurf.core.fio.micro_time import channels_per_period, period_histogram

    period = channels_per_period(burst)
    cp = period_histogram(burst[np.where(channel_mask(burst.routing_channels, pchs))[0]], binning, period=period)
    cs_hist = period_histogram(burst[np.where(channel_mask(burst.routing_channels, schs))[0]], binning, period=period)
    if sb > 0:
        cp[:sb] = 0
        cs_hist[:sb] = 0
    if eb < cp.size:
        cp[eb:] = 0
        cs_hist[eb:] = 0
    return np.hstack([cp, cs_hist])


#: Counts an IRF from a reference measurement needs in each polarisation to be used for a detector.
MIN_IRF_COUNTS = 500

#: The IRF models of the Auto IRF/background estimate: (value, label).
IRF_MODELS = [
    ("gaussian", "Gaussian"),
    ("skewed", "Skewed Gaussian"),
    ("experimental", "Experimental"),
]

#: The binnings the detector page offers.
BINNING_CHOICES = [1, 2, 4, 8, 16, 32, 64, 128, 256]


def read_burst_analysis(
    paris_path: Path, pattern: str = "**/*.bur"
) -> tuple[Any, dict[str, Path], dict | None]:
    """Read every ``.bur`` under *paris_path* into one burst table.

    Returns the table (tagged with ``burst_file``), the raw-file stem -> path map (raw files sit beside the analysis
    folder) and the ``setup_info`` of ``Info/photon_selection_parameters.json`` when it has one.
    """
    import json

    from chisurf.core.fio.fluorescence.burst import read_bur_file
    from chisurf.core.fio.fluorescence.burst_container import deinterleave_bursts

    paris_path = Path(paris_path)
    bur_files = sorted(paris_path.glob(pattern))
    if not bur_files:
        raise ValueError(f"No burst files found in {paris_path!s}")
    setup_info = None
    info = paris_path / "Info" / "photon_selection_parameters.json"
    if info.is_file():
        try:
            setup_info = (json.loads(info.read_text(encoding="utf-8")) or {}).get("setup_info")
        except (OSError, ValueError):
            setup_info = None
    # deinterleave each file on its own: the zero/data interleave is a per-file property
    tables = []
    for fn in bur_files:
        table = deinterleave_bursts(read_bur_file(fn))
        set_constant(table, "burst_file", str(fn.name))
        set_constant(table, "_burst_path", str(fn.resolve()))
        table["_measurement_path"] = [
            str((paris_path.parent / Path(str(name).replace("\\", "/")).name).resolve())
            for name in np.asarray(table["First File"], dtype=object)
        ]
        tables.append(table)
    df = concat_stores(tables)
    base_dir = paris_path.parent
    raw: dict[str, Path] = {}
    for name in dict.fromkeys(str(v) for v in np.asarray(df["First File"], dtype=object)):
        raw[Path(Path(name).name).stem] = base_dir / Path(name).name
    return df, raw, setup_info


# --------------------------------------------------------------------------------------------------------------------
# the session
# --------------------------------------------------------------------------------------------------------------------
#: Name of the multi-exponential tail fit: a different estimator family (``tttrlib.DecayFitNExp``), not a fit2x model.
#: Bump in the same change that alters what a batch fit computes: it is part of the reuse fingerprint, so a
#: corrected estimator makes every held result stale instead of "unchanged".
ALGORITHM_VERSION = 1

TAIL_MODEL = "tail"

#: Parameters of the tail fit: the first channel of the tail and two lifetimes (set both equal for a mono-exponential tail).
TAIL_SCHEMA: dict = {
    "properties": {
        "tail_start": {
            "title": "Tail start (ch.)",
            "default": 20.0,
            "minimum": 0.0,
            "maximum": 100000.0,
            "fixed_default": True,
            "description": "First channel of the tail; earlier channels (the rise and the prompt) are excluded.",
        },
        "tau1": {
            "title": "Lifetime tau1 (ns)",
            "default": 2.0,
            "minimum": 0.01,
            "maximum": 100.0,
            "fixed_default": False,
            "description": "First tail lifetime.",
        },
        "tau2": {
            "title": "Lifetime tau2 (ns)",
            "default": 0.5,
            "minimum": 0.01,
            "maximum": 100.0,
            "fixed_default": False,
            "description": "Second tail lifetime.",
        },
    },
    "required": ["tail_start", "tau1", "tau2"],
}


def fit_model_specs() -> dict[str, dict]:
    """Return registry models supported by the existing acquisition-input facade, plus the tail fit."""
    from chisurf.core.fluorescence.mle.fit2x import Fit2xModel
    from chisurf.core.fluorescence.mle.registry import fit_models

    supported = {model.value for model in Fit2xModel}
    specs = {name: spec for name, spec in fit_models().items() if name in supported}
    specs[TAIL_MODEL] = {
        "label": "Tail fit (multi-exp)",
        "params_schema": TAIL_SCHEMA,
        "description": "Multi-exponential fit of the decay tail only (no IRF deconvolution); preview of the current "
        "decay, not offered for the batch over every burst.",
    }
    return specs


def validate_fit_model(name: str) -> str:
    """Reject unknown models and models requiring inputs this workflow cannot supply."""
    if name not in fit_model_specs():
        raise ValueError(f"Model {name!r} is unavailable for IRF/background lifetime fitting.")
    return name


def model_availability() -> str:
    """Describe supported models and declare why other registry models are unavailable."""
    from chisurf.core.fluorescence.mle.registry import fit_models

    specs = fit_models()
    available = fit_model_specs()
    lines = []
    for name, spec in specs.items():
        if name not in available:
            if spec.get("n_patterns", 0):
                reason = str(tr("requires {count} reference patterns")).format(
                    count=spec["n_patterns"]
                )
            else:
                properties = spec.get("params_schema", {}).get("properties", {})
                inputs = [
                    str(tr(item.get("title", key)))
                    for key, item in properties.items()
                    if item.get("type") == "array"
                ]
                reason = str(tr("requires {inputs}")).format(inputs=" / ".join(inputs))
            lines.append(
                str(tr("{name}: unavailable here ({reason}).")).format(name=name, reason=reason)
            )
    return "\n".join(lines)


def fit_result_names(model: str) -> tuple[str, ...]:
    """Return declared derived outputs that add information beyond the parameter vector."""
    from chisurf.core.fluorescence.mle.registry import fit_models

    if model == TAIL_MODEL:
        return ()
    properties = fit_models()[model].get("results_schema", {}).get("properties", {})
    return tuple(name for name in properties if name == "selected_index")



def _tail_start_bin(rc_full, mt_bins, bursts, chs, sb, eb) -> int:
    """First bin of a tail fit: one after the peak of the detector's decay pooled over the
    bursts' photons (in the window ``[sb, eb)``)."""
    chs = np.asarray(list(chs), dtype=int)
    if not len(bursts) or chs.size == 0 or eb <= sb:
        return int(sb)
    first = np.asarray([int(a) for a, _b in bursts], dtype=np.int64)
    last = np.asarray([int(b) for _a, b in bursts], dtype=np.int64)
    lengths = last - first + 1
    keep = lengths > 0
    first, lengths = first[keep], lengths[keep]
    if not lengths.size:
        return int(sb)
    starts = np.repeat(first - np.concatenate(([0], np.cumsum(lengths)[:-1])), lengths)
    idx = np.arange(int(lengths.sum())) + starts
    idx = idx[idx < len(rc_full)]
    sel = channel_mask(np.asarray(rc_full)[idx], chs)
    micro = np.asarray(mt_bins)[idx][sel].astype(np.int64)
    micro = micro[(micro >= sb) & (micro < eb)]
    if not micro.size:
        return int(sb)
    hist = np.bincount(micro - int(sb), minlength=int(eb - sb))
    return int(sb) + int(np.argmax(hist)) + 1


class _Memo(dict):
    """A memo a copy of its owner starts without (it holds photon streams, which do not copy)."""

    def __deepcopy__(self, memo):
        return _Memo()

    def __copy__(self):
        return _Memo()

    def __reduce__(self):
        return (_Memo, ())


# -- the fit pool ------------------------------------------------------------------------------------ #
#: The worker processes of the burst fit, kept between fits: spawning them (a Python start and the
#: fit imports each) cost about a second per fit, longer than fitting a measurement's bursts.
_FIT_POOL: Any = None
_FIT_POOL_WORKERS = 0
#: Bursts per chunk at least: a smaller job is all overhead.
MIN_CHUNK_BURSTS = 200


def fit_workers() -> int:
    """Worker processes of the burst fit: every core but one (the UI's)."""
    import os

    return max(1, (os.cpu_count() or 2) - 1)


def fit_pool(workers: int | None = None):
    """The kept pool of *workers* fit processes, started on first use."""
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor

    global _FIT_POOL, _FIT_POOL_WORKERS
    workers = int(workers or fit_workers())
    if _FIT_POOL is None or _FIT_POOL_WORKERS != workers:
        _drop_fit_pool()
        _FIT_POOL = ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn"))
        _FIT_POOL_WORKERS = workers
        import atexit

        atexit.register(_drop_fit_pool)
    return _FIT_POOL


def warm_fit_pool() -> None:
    """Start the fit processes now (in the background), so the first fit does not wait for them."""
    from ._mp_worker import warm

    pool = fit_pool()
    for _ in range(_FIT_POOL_WORKERS):
        pool.submit(warm)


def warm_fit_pool_quietly() -> None:
    """:func:`warm_fit_pool` for a background thread: a failure only means the fit starts them."""
    try:
        warm_fit_pool()
    except Exception:  # noqa: BLE001
        pass


def _drop_fit_pool() -> None:
    global _FIT_POOL, _FIT_POOL_WORKERS
    pool, _FIT_POOL, _FIT_POOL_WORKERS = _FIT_POOL, None, 0
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def _chop_jobs(jobs: list[tuple], workers: int) -> list[tuple]:
    """*jobs* (one per file) with each file's bursts split into chunks, in burst order.

    About four chunks per worker over all files, so a slow chunk does not hold the batch; never
    below :data:`MIN_CHUNK_BURSTS` bursts a chunk.
    """
    total = sum(len(job[1]) for job in jobs)
    if not total:
        return jobs
    size = max(MIN_CHUNK_BURSTS, -(-total // max(1, 4 * int(workers))))
    chopped: list[tuple] = []
    for job in jobs:
        bursts = list(job[1])
        if len(bursts) <= size:
            chopped.append(job)
            continue
        for start in range(0, len(bursts), size):
            chopped.append((job[0], bursts[start : start + size], *job[2:]))
    return chopped

class LazyTTTRs(collections.abc.MutableMapping):
    """Canonical physical path -> lazily read TTTR; legacy stems resolve only when unique."""

    def __init__(self, paths: dict[str, Path], file_type: str = "auto", setup=None) -> None:
        self.paths = paths
        self._cache: dict[str, Any] = {}
        self.file_type = file_type
        self.read_kwargs: dict = {}
        self._read_signature = ""
        self.set_setup(setup or {})

    @property
    def file_type(self):
        """Return the selected reader routine."""
        return self._file_type

    @file_type.setter
    def file_type(self, value):
        """Invalidate cached photons when their reader routine changes."""
        if getattr(self, "_file_type", None) != value:
            self._cache.clear()
        self._file_type = value

    def set_setup(self, setup: dict) -> None:
        """Freeze explicit portable LUT/shift inputs, isolated from other apps' global context."""
        import json

        from chisurf.core.data_io.detector_setups import setup_lut_open_kwargs

        kwargs = copy.deepcopy(setup_lut_open_kwargs(setup))
        signature = json.dumps(kwargs, sort_keys=True, cls=NumpyEncoder)
        if signature != self._read_signature:
            self._cache.clear()
            self._read_signature = signature
        self.read_kwargs = kwargs

    def __getitem__(self, key: str):
        from chisurf.core.fio.staging import open_tttr

        if key not in self.paths:
            matches = [identity for identity, path in self.paths.items() if path.stem == key]
            if len(matches) != 1:
                raise KeyError(
                    f"Measurement {key!r} is missing or ambiguous; use its complete path."
                )
            key = matches[0]
        # Cached by the physical file: several runs of one container are several identities of one photon stream,
        # and reading it once per run would hold the same photons in memory twice.
        physical = str(self.paths[key])
        if physical not in self._cache:
            file_type = self.file_type
            if not file_type or str(file_type).lower() == "auto":
                file_type = None
            # The shared reading (read-only here): the burst search and every other step already
            # hold these photons, and a private read cost 0.3 s per 300 MB on the UI thread.
            self._cache[physical] = open_tttr(self.paths[key], file_type, **self.read_kwargs)
        return self._cache[physical]

    def __setitem__(self, key, value) -> None:
        self._cache[str(self.paths.get(key, key))] = value

    def __delitem__(self, key) -> None:
        self._cache.pop(str(self.paths.get(key, key)), None)
        self.paths.pop(key, None)

    def __iter__(self):
        return iter(self.paths)

    def __len__(self) -> int:
        return len(self.paths)


@dataclass
class MleSettings:
    """Everything the fit and the displayed IRF depend on (one per detector)."""

    model: str = "fit23"
    model_values: dict[str, dict[str, float]] = field(default_factory=dict)
    model_fixed: dict[str, dict[str, bool]] = field(default_factory=dict)
    tau: float = 4.0
    gamma: float = 0.1
    r0: float = 0.38
    rho: float = 1.22
    fix_tau: bool = False
    #: The scatter fraction is fitted: a fixed guess was the largest error of the summed-decay fit.
    fix_gamma: bool = False
    fix_r0: bool = True
    fix_rho: bool = True
    shift: int = 0
    shift_sp: float = 0.0
    shift_ss: float = 0.0
    irf_start: int = -1
    irf_stop: int = -1
    irf_threshold_vv: float = 0.02
    irf_threshold_vh: float = 0.02
    micro_time_start: int = 0
    micro_time_stop: int = 4096
    micro_time_binning: int = 1
    min_photons: int = 5
    p2s_twoIstar: bool = True
    BIFL_scatter: bool = False
    #: Shape of an IRF estimated from the photons outside the bursts (the last resort, see
    #: :meth:`MleSession.irf_pattern`): a skewed Gaussian follows the detector's slow edge.
    irf_model: str = "skewed"

    def parameter_state(self) -> tuple[list[str], np.ndarray, np.ndarray]:
        """Return free facade names, starts and fixed flags for this selected model."""
        from chisurf.core.fluorescence.mle.fit2x import parameter_names_of

        name = validate_fit_model(self.model)
        names = (
            list(TAIL_SCHEMA["properties"])
            if name == TAIL_MODEL
            else list(parameter_names_of(name))
        )
        if name == "fit23":
            values = [getattr(self, key) for key in names]
            fixed = [getattr(self, f"fix_{key}") for key in names]
        else:
            properties = fit_model_specs()[name]["params_schema"]["properties"]
            saved_values = self.model_values.setdefault(name, {})
            saved_fixed = self.model_fixed.setdefault(name, {})
            values = [saved_values.get(key, properties[key].get("default", 0.0)) for key in names]
            fixed = [
                saved_fixed.get(key, properties[key].get("fixed_default", False)) for key in names
            ]
            if name == "fit25":
                fixed = [
                    True if key.startswith("tau") else value for key, value in zip(names, fixed)
                ]
        return names, np.asarray(values, dtype=float), np.asarray(fixed, dtype=np.int32)

    def edit_parameter(self, name: str, value: Any, *, fixed: bool = False) -> None:
        """Update one declared free parameter without disturbing another model's starts."""
        names, _, _ = self.parameter_state()
        if name not in names:
            raise ValueError(f"Unknown free parameter {name!r} for {self.model}.")
        if fixed and self.model == "fit25" and name.startswith("tau") and not bool(value):
            raise ValueError("Fit25 lifetime candidates are always fixed.")
        if self.model == "fit23":
            setattr(self, f"fix_{name}" if fixed else name, bool(value) if fixed else float(value))
        elif fixed:
            self.model_fixed.setdefault(self.model, {})[name] = bool(value)
        else:
            spec = fit_model_specs()[self.model]["params_schema"]["properties"][name]
            value = float(value)
            if (
                not np.isfinite(value)
                or value < spec.get("minimum", -np.inf)
                or value > spec.get("maximum", np.inf)
            ):
                raise ValueError(f"Parameter {name!r} is outside its declared bounds.")
            self.model_values.setdefault(self.model, {})[name] = value


@dataclass
class FitOutcome:
    """The result of fitting one decay."""

    x: np.ndarray
    two_istar: float
    names: list[str]
    curves: DecayCurves
    model: np.ndarray
    data: np.ndarray
    result: Any = None


@dataclass
class MleSession:
    """Detectors, burst files, patterns and settings of a burst-MLE analysis."""

    detectors: dict = field(default_factory=dict)
    definition: dict = field(default_factory=dict)
    file_type: str = "auto"
    #: Start values for a detector nobody has set yet.
    template: MleSettings = field(default_factory=MleSettings)
    bur_files: list[Path] = field(default_factory=list)
    df_bursts: Any = None
    tttr_paths: dict[str, Path] = field(default_factory=dict)
    current_detector: str = ""
    current_index: int = 0
    irf_np: dict[str, np.ndarray] = field(default_factory=dict)
    bg_np: dict[str, np.ndarray] = field(default_factory=dict)
    decay: np.ndarray | None = None
    outcome: FitOutcome | None = None
    status: str = ""
    #: Fit every burst once more per H2MM state (``Tau S0 (G|G)`` ...), after a pooled fit of each state's decay.
    split_by_state: bool = False
    #: Photon floor of a per-state burst fit (a state sees far fewer photons than the whole burst).
    state_min_photons: int = 20
    #: Measured IRF / background files per detector (their summed histograms are the patterns of that detector).
    irf_files: dict[str, list[Path]] = field(default_factory=dict)
    bg_files: dict[str, list[Path]] = field(default_factory=dict)
    #: One list of IRF / background files serves every detector (each reads its own channels from the files).
    irf_one_for_all: bool = True
    bg_one_for_all: bool = True
    #: Write the VV | VH histogram of every IRF / background file beside it.
    save_vv_vhs: bool = False
    #: Where each detector's IRF came from, in words ("scatter H2O_1.ptu", "Rh110_1.ptu (Rh110,
    #: 4.0 ns)", "photons outside the bursts (skewed Gaussian)").
    irf_source: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tttrs = LazyTTTRs(self.tttr_paths, self.file_type, self.definition)
        self.det_settings: dict[str, MleSettings] = {}
        #: Rows of the last batch run, one mapping per burst and detector.
        self.burst_results: list[dict] = []
        #: Pooled per-state lifetimes of the last batch (one row per detector and state) and the state count.
        self.state_lifetimes: list[dict] = []
        self.n_states = 0
        self.batch_settings_snapshot: dict[str, dict] = {}
        self.batch_files_snapshot: dict[str, Path] = {}

    @property
    def settings(self) -> MleSettings:
        """The settings of the current detector (created from the template on first use)."""
        det = self.current_detector
        if det not in self.det_settings:
            self.det_settings[det] = copy.deepcopy(self.template)
        return self.det_settings[det]

    def settings_of(self, det: str) -> MleSettings:
        if det not in self.det_settings:
            self.det_settings[det] = copy.deepcopy(self.template)
        return self.det_settings[det]

    def set_model(self, name: str, det: str | None = None) -> None:
        """Select the model of detector *det* (every detector when ``None``), keeping each model's edits."""
        validate_fit_model(name)
        if det is not None:
            settings = self.settings_of(det)
            if settings.model != name:
                settings.model = name
                self.outcome = None
            return
        if self.template.model == name and all(
            st.model == name for st in self.det_settings.values()
        ):
            return
        self.template.model = name
        for settings in self.det_settings.values():
            settings.model = name
        self.outcome = None

    def default_models(self) -> dict[str, str]:
        """The model each detector starts with, from its role in the setup.

        The donor (``G|G``) is ``fit23`` (polarisation-resolved when it has a parallel and a
        perpendicular channel), and so is the acceptor under its own laser (``R|R``). The
        FRET-sensitised acceptor (``R|G``) sees a rise from the donor, then the acceptor's decay --
        where a deconvolution with the IRF does not apply: the tail fit. A detector whose name
        carries no role is judged by its place: the first is the donor, one gated on a later PIE
        window ``fit23``, any other the tail fit.
        """
        from chisurf.core.fluorescence.detector_names import role

        by_role = {"donor": "fit23", "acceptor_direct": "fit23", "acceptor": TAIL_MODEL}
        windows = [list(map(int, w)) for w in (self.definition.get("windows") or {}).values()
                   if isinstance(w, (list, tuple)) and len(w) >= 2]
        first_window = min(windows, key=lambda w: w[0]) if windows else None
        out = {}
        for index, (name, info) in enumerate(self.detectors.items()):
            gates = [r for r in (info.get("micro_time_ranges") or []) if len(r) >= 2]
            later_window = bool(
                first_window and gates and int(gates[0][0]) >= int(first_window[1]) - 1
            )
            by_place = "fit23" if index == 0 or later_window else TAIL_MODEL
            out[name] = by_role.get(role(name), by_place)
        return out

    def set_binning(self, binning: int) -> None:
        """The micro-time binning is global: every detector's histograms and IRF share it."""
        self.template.micro_time_binning = int(binning)
        for st in self.det_settings.values():
            st.micro_time_binning = int(binning)

    # -- inputs ------------------------------------------------------------------------------------------------ #
    def set_detectors(self, detectors: dict, file_type: str | None = None) -> None:
        self.detectors = {k: dict(v) for k, v in detectors.items()}
        if file_type:
            self.file_type = file_type
            self.tttrs.file_type = file_type
        if self.current_detector not in self.detectors:
            self.current_detector = next(iter(self.detectors), "")

    def set_definition(self, settings: dict) -> None:
        """Keep the complete portable setup, including undeclared future metadata."""
        self.definition = copy.deepcopy(settings)
        reading = settings.get("tttr_reading") or {}
        new = [d for d in (settings.get("detectors") or {}) if d not in self.det_settings]
        self.set_detectors(settings.get("detectors", self.detectors), reading.get("file_type"))
        self.tttrs.set_setup(self.definition)
        # a detector seen for the first time starts with the model its role calls for; a model the
        # user chose stays
        defaults = self.default_models()
        for det in new:
            if det in defaults:
                self.settings_of(det).model = defaults[det]

    def definition_payload(self) -> dict:
        """Return the portable setup with the current authoritative detector and reader state."""
        result = copy.deepcopy(self.definition)
        result["detectors"] = copy.deepcopy(self.detectors)
        result.setdefault("windows", {})
        result.setdefault("tttr_reading", {})["file_type"] = self.file_type
        return result

    def timing_ns(self, tttr: Any, binning: int) -> tuple[float | None, float | None]:
        """Return this file's effective timing without overwriting its physical header."""
        return effective_timing_ns(tttr, binning, self.definition.get("tttr_reading") or {})

    def add_burst_files(self, paths: collections.abc.Sequence[str | Path]) -> None:
        """Add ``.bur`` tables. The analysis folder of the first file is read whole: every ``.bur``
        under it (``<analysis>/<ending>/<stem>.bur``) becomes rows of the burst table."""
        for p in map(Path, paths):
            if p not in self.bur_files:
                self.bur_files.append(p)
        if not self.bur_files:
            self.df_bursts = None
            self.tttr_paths.clear()
            return
        tables = []
        raw_paths = {}
        setup_info = None
        roots = dict.fromkeys(
            path.parent.parent.resolve() for path in self.bur_files if not _is_container(path)
        )
        for index, root in enumerate(roots):
            table, raw, setup = read_burst_analysis(root)
            tables.append(table)
            raw_paths.update({str(path.resolve()): path.resolve() for path in raw.values()})
            if index == 0:
                setup_info = setup
        # A run in a container is its own burst table and its own photon source.
        for path in (p for p in self.bur_files if _is_container(p)):
            table, container = read_burst_container(path)
            tables.append(table)
            # Keyed by the run read; the photons are the container's, opened once however many runs name it.
            for identity in dict.fromkeys(
                str(v) for v in np.asarray(table["_measurement_path"], dtype=object)
            ):
                raw_paths[identity] = container
        self.df_bursts = concat_stores(tables)
        changed_paths = self.tttr_paths != raw_paths
        self.tttr_paths.clear()
        self.tttr_paths.update(raw_paths)
        if changed_paths:
            self.tttrs = LazyTTTRs(self.tttr_paths, self.file_type, self.definition)
        if setup_info and setup_info.get("detectors"):
            self.detectors = {k: dict(v) for k, v in setup_info["detectors"].items()}
        self.current_index = min(self.current_index, max(0, len(self.bur_files) - 1))

    @property
    def current_filename(self) -> str:
        return str(self.bur_files[self.current_index]) if self.bur_files else ""

    def _memo(self, name: str, compute):
        """*compute()*, kept until the bursts, the selected file or the loaded measurements change.

        The preview, the setup and the fit each ask for the selected file's photons and burst
        coverage; every answer went through the burst table's text columns (and a list of millions
        of photon indices) again -- 0.4 s on the UI thread per hand-over.
        """
        df = self.df_bursts
        key = (
            id(df),
            row_count(df) if df is not None else 0,
            str(self.current_filename),
            id(self.tttrs),
            tuple(self.tttrs.paths) if hasattr(self.tttrs, "paths") else len(self.tttrs or ()),
            # a new reading (a LUT, another setup's correction) is another photon stream
            repr(getattr(self.tttrs, "_read_signature", None)),
        )
        memo = self.__dict__.setdefault("_memo_cache", _Memo())
        if memo.get("key") != key:
            memo.clear()
            memo["key"] = key
        if name not in memo:
            memo[name] = compute()
        return memo[name]

    def current_tttr(self):
        """The TTTR behind the selected burst file (``None`` when nothing is loaded)."""
        return self._memo("current_tttr", self._current_tttr)

    def _current_tttr(self):
        if self.df_bursts is None or not self.tttrs:
            return None
        df = self.df_bursts
        curr = str(Path(self.current_filename).resolve()) if self.current_filename else None
        names = column_names(df)
        if "_burst_path" in names and curr:
            sub = take_where(df, np.asarray(df["_burst_path"]) == curr)
            if row_count(sub) > 0:
                df, names = sub, column_names(sub)
        if "First File" not in names or row_count(df) == 0:
            return None
        if "_measurement_path" in names:
            return self.tttrs.get(str(np.asarray(df["_measurement_path"], dtype=object)[0]))
        return self.tttrs.get(Path(str(np.asarray(df["First File"], dtype=object)[0])).stem)

    def burst_indices(self) -> list[int]:
        """Return inclusive burst coverage of the complete selected BUR identity."""
        return self._memo("burst_indices", lambda: self.burst_index_array().tolist())

    def burst_index_array(self) -> np.ndarray:
        """:meth:`burst_indices` as an array (read only, shared): the steps that index photons with
        it took a list of millions of indices and made an array of it again, each of them."""
        return self._memo("burst_index_array", self._burst_index_array)

    def _burst_index_array(self) -> np.ndarray:
        idx = np.asarray(self._burst_indices(), dtype=np.int64)
        idx.flags.writeable = False
        return idx

    def _burst_indices(self):
        table = self.df_bursts
        if table is not None and "_burst_path" in column_names(table) and self.current_filename:
            selected = str(Path(self.current_filename).resolve())
            table = take_where(table, np.asarray(table["_burst_path"], dtype=object) == selected)
        return burst_photon_indices(table, self.current_filename, as_array=True)

    def measurement_files(self) -> dict[str, Path]:
        """Associate each loaded physical measurement with its exact selected burst table."""
        if self.df_bursts is None or "_measurement_path" not in column_names(self.df_bursts):
            return {p.stem: p for p in self.bur_files}
        selected = {str(path.resolve()) for path in self.bur_files}
        return {
            str(raw): Path(burst)
            for raw, burst in zip(
                self.df_bursts["_measurement_path"], self.df_bursts["_burst_path"]
            )
            if str(burst) in selected
        }

    def state_arrays_by_measurement(self) -> tuple[dict, int, str]:
        """Resolve H2MM states within each analysis, then retain complete raw-file identities."""
        from . import state_split

        arrays, count, messages = {}, 0, []
        roots = dict.fromkeys(
            path.parent.parent.resolve() for path in self.bur_files if not _is_container(path)
        )
        for root in roots:
            selected = np.array(
                [Path(str(path)).parent.parent == root for path in self.df_bursts["_burst_path"]]
            )
            identities = dict.fromkeys(
                str(value)
                for value in np.asarray(self.df_bursts["_measurement_path"], dtype=object)[selected]
            )
            scoped = {Path(identity).stem: self.tttrs[identity] for identity in identities}
            states, n_states, message = state_split.load_state_arrays(root, scoped)
            for identity in identities:
                if Path(identity).stem in states:
                    arrays[identity] = states[Path(identity).stem]
            count = max(count, n_states)
            messages.append(message)
        # A container records its H2MM run beside the bursts: the states of its photons.
        from chisurf.core.fio.fluorescence.burst_states import container_state_array

        for identity, container in dict.fromkeys(
            (k, v) for k, v in self.tttr_paths.items() if _is_container(Path(str(v)))
        ):
            tttr = self.tttrs.get(identity)
            if tttr is None or identity in arrays:
                continue
            states, n_states = container_state_array(container, len(tttr))
            if states is None:
                messages.append(f"Split by state: {Path(str(container)).name} has no H2MM run.")
                continue
            arrays[identity] = states
            count = max(count, n_states)
            messages.append(
                f"Split by state: {n_states} states, {int((states >= 0).sum()):,} photons "
                f"labelled ({Path(str(container)).name})."
            )
        return arrays, count, "\n".join(messages)

    # -- derived ----------------------------------------------------------------------------------------------- #
    @property
    def detector(self) -> dict:
        return self.detectors.get(self.current_detector, {})

    @property
    def micro_time_range(self) -> tuple[int, int]:
        return self.settings.micro_time_start, self.settings.micro_time_stop

    def g_factor(self) -> float:
        return float(self.detector.get("g_factor", 1.0))

    def polarisation(self) -> tuple[float, float, float]:
        d = self.detector
        return float(d.get("g_factor", 1.0)), float(d.get("l1", 0.0)), float(d.get("l2", 0.0))

    def irf(self) -> np.ndarray:
        s = self.settings
        return process_irf(
            self.irf_np.get(self.current_detector),
            micro_time_range=self.micro_time_range,
            binning=s.micro_time_binning,
            shift=s.shift,
            shift_sp=s.shift_sp,
            shift_ss=s.shift_ss,
            irf_start=s.irf_start,
            irf_stop=s.irf_stop,
            threshold_vv=s.irf_threshold_vv,
            threshold_vh=s.irf_threshold_vh,
        )

    def background(self) -> np.ndarray:
        return process_background(
            self.bg_np.get(self.current_detector), self.settings.shift, self.irf()
        )

    def window_ranges(self) -> tuple[int, int, int, int]:
        return window_bins(
            self.detector.get("micro_time_ranges"),
            self.micro_time_range,
            self.settings.micro_time_binning,
            len(self.detector.get("chs", [])),
        )

    # -- decay ------------------------------------------------------------------------------------------------- #
    def build_decay(self) -> np.ndarray | None:
        """The decay of every burst photon of the current file and detector (``decay_of_current_file``)."""
        tttr = self.current_tttr()
        chs = self.detector.get("chs", [])
        idx = self.burst_index_array()
        if tttr is None or not chs or idx.size == 0:
            return None
        photons = self._memo("burst_tttr", lambda: tttr[idx])  # cut once per file
        kwargs = dict(
            detector_ranges=self.detector.get("micro_time_ranges"),
            shift=self.settings.shift,
            normalize_counts=-1,
        )
        binning = self.settings.micro_time_binning
        rows = vv_vh_histogram(photons, chs, self.micro_time_range, binning, **kwargs)
        self.decay = np.asarray(rows)
        #: The same decay with every channel (not cut to the fit window): what the plot shows,
        #: kept with the decay it belongs to.
        self._decay_all = (
            self.decay,
            np.asarray(vv_vh_histogram(photons, chs, self.micro_time_range, binning, cut=False, **kwargs)),
        )
        return self.decay

    def decay_all(self, decay: np.ndarray) -> np.ndarray | None:
        """*decay* with every channel (:meth:`build_decay`), ``None`` when it was not built here."""
        pair = getattr(self, "_decay_all", None)
        return pair[1] if pair is not None and pair[0] is decay else None

    # -- IRF / background -------------------------------------------------------------------------------------- #
    def auto_binning(self) -> int | None:
        tttr = self.current_tttr()
        return select_binning(
            tttr,
            self.detector.get("chs", []),
            self.burst_index_array(),
            BINNING_CHOICES,
        )

    def extract_irf_background(self) -> int:
        """IRF and background from the photons outside the bursts, at the current binning; returns the detectors done.

        A detector with a measured IRF keeps it. One with too few photons outside the bursts to
        show a prompt (:data:`MIN_IRF_COUNTS` in its gate) gets the blind estimate from its burst
        decay (:meth:`blind_irf`), the last resort.
        """
        from chisurf.core.fluorescence.burst import extract_mle_irf_background

        tttr = self.current_tttr()
        idx = self.burst_index_array()
        in_burst = np.zeros(len(tttr), dtype=bool)
        in_burst[idx] = True
        patterns = extract_mle_irf_background(
            tttr,
            self.detectors,
            micro_time_binning=self.settings.micro_time_binning,
            mask=~in_burst,
            min_photons=max(2, int(self.settings.min_photons)),
            irf_model=self.settings.irf_model,
        )
        n = 0
        label = dict(IRF_MODELS).get(self.settings.irf_model, self.settings.irf_model).lower()
        for det, pat in patterns.items():
            if det:
                if not self.irf_files.get(det):
                    irf = np.asarray(pat["irf"], dtype=float)
                    if self._background_prompt_photons(tttr, det, ~in_burst) >= MIN_IRF_COUNTS:
                        self.irf_np[det] = irf
                        self.irf_source[det] = f"photons outside the bursts ({label})"
                    else:  # too few to show a prompt: the last resort, the decay itself
                        self.irf_np[det] = self.blind_irf(det)
                        self.irf_source[det] = "the burst decay (blind estimate, skewed Gaussian)"
                if not self.bg_files.get(det):
                    self.bg_np[det] = np.asarray(pat["bg"], dtype=float)
                n += 1
        return n

    def _background_prompt_photons(self, tttr: Any, det: str, outside: np.ndarray) -> int:
        """Photons outside the bursts on *det*'s channels and in its gate: what the background
        estimate of its IRF stands on."""
        from tttrlib import micro_time_mask

        info = self.detectors[det]
        sel = outside & channel_mask(np.asarray(tttr.routing_channels), info.get("chs", []))
        gates = info.get("micro_time_ranges")
        if gates:
            sel &= micro_time_mask(np.asarray(tttr.micro_times), gates)
        return int(sel.sum())

    def blind_irf(self, det: str) -> np.ndarray:
        """The IRF of *det* estimated from the burst decay alone, the last resort.

        Blind estimation (truncated exponential fit + Richardson-Lucy deconvolution, as the IRF
        Estimation tool does it: :class:`~chisurf.core.fluorescence.tcspc.IRFEstimator`) on each
        polarisation of the detector's burst photons in its gate. What a multi-exponential sample
        leaves of its decay in that estimate is shed by fitting a skewed Gaussian to its prompt.
        Each polarisation sums to one; zeros when the decay is empty.
        """
        from chisurf.core.fluorescence.burst.irf_bg import gaussian_prompt
        from chisurf.core.fluorescence.tcspc import IRFEstimator

        info = self.detectors[det]
        tttr = self.current_tttr()
        binning = max(1, int(self.settings.micro_time_binning))
        photons = tttr[self.burst_index_array()]
        row = vv_vh_histogram(
            photons, info.get("chs", []), (0, 0), binning, normalize_counts=0, apply_vh_shift=False
        )
        half = row.size // 2
        gates = [r for r in (info.get("micro_time_ranges") or []) if r and len(r) >= 2]
        inside = np.ones(half, dtype=bool)
        if gates:
            inside[:] = False
            for lo, hi in gates:
                inside[int(lo) // binning : int(np.ceil(int(hi) / binning))] = True
        parts = []
        for decay in (row[:half], row[half:]):
            decay = np.where(inside, decay, 0.0)
            if decay.sum() <= 0:
                parts.append(np.zeros(half))
                continue
            lo, hi = int(np.flatnonzero(inside)[0]), int(np.flatnonzero(inside)[-1]) + 1
            estimate = np.zeros(half)
            estimate[lo:hi] = np.clip(IRFEstimator(decay[lo:hi].reshape(-1, 1), dt=1.0).run()[:, 0], 0.0, None)
            pulse = gaussian_prompt(estimate, 1.5)
            parts.append(pulse / pulse.sum() if pulse.sum() > 0 else pulse)
        return np.hstack(parts)

    # -- measured IRF / background files --------------------------------------------------------------------- #
    def _open_pattern_tttr(self, path: Path) -> Any:
        """Open one IRF / background measurement with the reader settings of the burst files."""
        from chisurf.core.fio.staging import open_tttr

        file_type: str | None = self.file_type
        if not file_type or str(file_type).lower() == "auto":
            file_type = None
        return open_tttr(Path(path), file_type, cache=False, **self.tttrs.read_kwargs)

    def pattern_histogram(self, det: str, paths: list[Path], normalize: int) -> np.ndarray:
        """Summed VV | VH histogram of *paths* on the channels of *det* at the current binning.

        ``normalize`` is 2 for an IRF (each polarisation sums to one) and 3 for a background (counts per second).
        """
        from chisurf.core.fio import write_vv_vh

        info = self.detectors[det]
        chs = info.get("chs", [])
        binning = int(self.settings.micro_time_binning)
        rows = []
        for path in paths:
            tttr = self._open_pattern_tttr(path)
            row = vv_vh_histogram(
                tttr,
                chs,
                (0, 0),
                binning,
                detector_ranges=info.get("micro_time_ranges"),
                normalize_counts=normalize,
                apply_vh_shift=False,
            )
            rows.append(row)
            if self.save_vv_vhs:
                half = row.size // 2
                name = f"{Path(path).with_suffix('').as_posix()}_{''.join(map(str, chs))}.dat"
                write_vv_vh(name, vv=row[:half], vh=row[half:])
        return np.sum(rows, axis=0)

    def _reference_counts(self, det: str, path: Path) -> tuple[np.ndarray, np.ndarray, float, float]:
        """VV and VH counts of one reference measurement on *det*'s channels, its acquisition time
        [s] and the width of one bin [ns]."""
        info = self.detectors[det]
        binning = int(self.settings.micro_time_binning)
        tttr = self._open_pattern_tttr(path)
        row = vv_vh_histogram(
            tttr, info.get("chs", []), (0, 0), binning, normalize_counts=0, apply_vh_shift=False
        )
        half = row.size // 2
        if self.save_vv_vhs:
            from chisurf.core.fio import write_vv_vh

            chs = "".join(map(str, info.get("chs", [])))
            write_vv_vh(f"{Path(path).with_suffix('').as_posix()}_{chs}.dat", vv=row[:half], vh=row[half:])
        header = tttr.header
        seconds = float((tttr.macro_times[-1] - tttr.macro_times[0]) * header.macro_time_resolution)
        dt_ns = float(header.micro_time_resolution) * 1e9 * binning
        return row[:half], row[half:], seconds, dt_ns

    def irf_pattern(self, det: str, paths: list[Path]) -> tuple[np.ndarray, str] | None:
        """The IRF of *det* from reference measurements, and where it came from; ``None`` when none
        of them shows the detector's response.

        A scatter measurement (water, Ludox) is the IRF itself; it is corrected for the background
        (a measured buffer of this detector, scaled to the scatter's time, then the flat floor).
        Without one, the decay of a reference dye (``reference_dyes.yaml``: Rh110, Alexa647, ...)
        gives the IRF by inverting the convolution with its exponential, whose lifetime is fitted to
        the dye's tail (the listed one when that fails); of
        several dyes the one with the most photons in the detector's gate is used (Rh110 for the
        green detectors, Alexa647 for the red ones of a PIE set-up). Each polarisation sums to one.
        """
        from chisurf.core.fio.reference_files import reference_dye
        from chisurf.core.fluorescence.tcspc.irf import (
            irf_from_reference_decay,
            reference_tail_lifetime,
            scatter_irf,
        )

        binning = max(1, int(self.settings.micro_time_binning))
        gates = [r for r in (self.detectors[det].get("micro_time_ranges") or []) if r and len(r) >= 2]
        window = (int(gates[0][0]) // binning, int(gates[0][1]) // binning) if gates else None
        scatter = [p for p in paths if reference_dye(p) is None]
        groups: dict[str, list[Path]] = {}
        for p in paths:
            dye = reference_dye(p)
            if dye is not None:
                groups.setdefault(dye["name"], []).append(p)
        buffer = None
        if self.bg_files.get(det) and det in self.bg_np:
            buffer = np.asarray(self.bg_np[det], dtype=float)  # counts per second, VV | VH

        candidates: list[tuple[float, np.ndarray, str]] = []
        if scatter:
            vv = vh = 0.0
            seconds = 0.0
            for p in scatter:
                a, b, t, _dt = self._reference_counts(det, p)
                vv, vh, seconds = vv + a, vh + b, seconds + t
            half = np.size(vv)
            bvv = bvh = None
            if buffer is not None and buffer.size == 2 * half:
                bvv, bvh = buffer[:half] * seconds, buffer[half:] * seconds
            parts = [
                scatter_irf(vv, buffer=bvv, window=window),
                scatter_irf(vh, buffer=bvh, window=window),
            ]
            corrected = "buffer-corrected" if bvv is not None else "floor-corrected"
            text = f"scatter {', '.join(p.name for p in scatter)} ({corrected})"
            candidates.append((np.inf, parts, text))  # a scatter wins over every dye
        for name, group in groups.items():
            listed = reference_dye(group[0])["tau_ns"]
            vv = vh = 0.0
            dt = 0.0
            for p in group:
                a, b, _t, dt = self._reference_counts(det, p)
                vv, vh = vv + a, vh + b
            # the dye's own lifetime, from its tail (magic angle); the listed one if that fails or
            # is far off (a tail that is mostly floor)
            tau = reference_tail_lifetime(vv + 2.0 * vh, dt, window=window)
            if tau is None or not 0.5 * listed < tau < 2.0 * listed:
                tau, how = listed, "listed"
            else:
                how = "from its tail"
            parts = [
                irf_from_reference_decay(vv, tau, dt, window=window),
                irf_from_reference_decay(vh, tau, dt, window=window),
            ]
            area = float(min(parts[0].sum(), parts[1].sum()))
            text = f"{', '.join(p.name for p in group)} ({name}, {tau:.2f} ns {how}, reconvolved)"
            candidates.append((area, parts, text))
        usable = [c for c in candidates if min(c[1][0].sum(), c[1][1].sum()) >= MIN_IRF_COUNTS]
        if not usable:
            return None
        _area, parts, text = max(usable, key=lambda c: c[0])
        return np.hstack([part / part.sum() for part in parts]), text

    def _pattern(self, kind: str, det: str, paths: list[Path]) -> tuple[np.ndarray, str] | None:
        if kind == "irf":
            return self.irf_pattern(det, paths)
        names = ", ".join(Path(p).name for p in paths)
        return self.pattern_histogram(det, paths, 3), f"measured {names}"

    def set_pattern_files(self, kind: str, det: str, paths: list[Path]) -> list[str]:
        """Use the measurements *paths* as the IRF (``kind="irf"``) or background (``"bg"``); returns the detectors set.

        With "one for all" the same files serve every detector. Each detector's pattern is computed from the files'
        histograms on its own channels, so a file measured on all detectors at once gives every detector its pattern.
        An IRF file that shows a detector nothing (a green dye on the red detector of the red pulse) leaves that
        detector to the estimate from the photons outside the bursts.
        """
        files, np_dict, _normalize, one = self._pattern_store(kind)
        paths = [Path(p) for p in paths]
        dets = list(self.detectors) if one else [det]
        done = []
        for d in dets:
            got = self._pattern(kind, d, paths)
            if got is None:
                continue
            files[d] = list(paths)
            np_dict[d] = got[0]
            if kind == "irf":
                self.irf_source[d] = got[1]
            done.append(d)
        self.outcome = None
        return done

    def clear_pattern_files(self, kind: str, det: str) -> list[str]:
        """Forget the measured files (and the pattern read from them) of *det*, or of every detector with "one for all"."""
        files, np_dict, _normalize, one = self._pattern_store(kind)
        dets = list(self.detectors) if one else [det]
        for d in dets:
            if files.pop(d, None) is not None:
                np_dict.pop(d, None)
                if kind == "irf":
                    self.irf_source.pop(d, None)
        self.outcome = None
        return dets

    def refresh_pattern_files(self) -> None:
        """Re-read every measured pattern at the current binning and channels (after either changed)."""
        for kind in ("bg", "irf"):  # the buffer first: a scatter IRF is corrected with it
            files, np_dict, _normalize, _one = self._pattern_store(kind)
            for det in [d for d in files if d in self.detectors and files[d]]:
                got = self._pattern(kind, det, files[det])
                if got is None:
                    files.pop(det)
                    np_dict.pop(det, None)
                    continue
                np_dict[det] = got[0]
                if kind == "irf":
                    self.irf_source[det] = got[1]

    def _pattern_store(self, kind: str):
        if kind == "irf":
            return self.irf_files, self.irf_np, 2, self.irf_one_for_all
        if kind == "bg":
            return self.bg_files, self.bg_np, 3, self.bg_one_for_all
        raise ValueError(f"Unknown pattern kind {kind!r}: use 'irf' or 'bg'.")

    def auto_extract(self) -> None:
        """One click: binning, IRF / background, fit window, fit."""
        tttr = self.current_tttr()
        if tttr is None:
            self.status = "Load bursts first: no data to extract an IRF from"
            return
        if not self.burst_index_array().size:
            self.status = "No burst photons found for the selected file"
            return
        pick = self.auto_binning()
        if pick is not None and int(pick) != int(self.settings.micro_time_binning):
            self.set_binning(int(pick))
            self.refresh_pattern_files()  # measured patterns read at the old binning
        self.extract_irf_background()
        self.build_decay()
        window = select_fit_range(self.decay)
        if window is not None:
            self.settings.micro_time_start, self.settings.micro_time_stop = window
        self.build_decay()
        self.fit()
        measured = sum(1 for d in self.detectors if self.irf_files.get(d))
        self.status = (
            f"Binning {self.settings.micro_time_binning}, window {list(self.micro_time_range)}"
            + (f"; {measured} detector(s) with a measured IRF." if measured else ".")
        )

    # -- fit --------------------------------------------------------------------------------------------------- #
    def parameter_vector(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the selected model's ordered free starts and fixed flags."""
        _, values, fixed = self.settings.parameter_state()
        return values, fixed

    def create_fit(self):
        """The ``Fit2x`` of the current detector, IRF and background."""
        from chisurf.core.fluorescence.mle.fit2x import Fit2x, Fit2xModel, Fit2xSettings

        tttr = self.current_tttr()
        dt, period = self.timing_ns(tttr, self.settings.micro_time_binning)
        gf, l1, l2 = self.polarisation()
        irf = self.irf().astype(np.float64, copy=True)
        bg = self.background().astype(np.float64, copy=True)
        total = float(bg.sum())
        if total > 0.0:
            bg = bg / total
        settings = Fit2xSettings(
            dt=dt,
            period=period,
            irf=irf,
            background=bg,
            g_factor=gf,
            l1=l1,
            l2=l2,
            p2s_twoIstar=self.settings.p2s_twoIstar,
            soft_bifl_scatter=self.settings.BIFL_scatter,
        )
        return Fit2x(settings, model=Fit2xModel(self.settings.model))

    def blocked_reason(self) -> str | None:
        det = self.current_detector
        if not det:
            return "no detector selected"
        if self.settings.model != TAIL_MODEL and (
            det not in self.irf_np or np.asarray(self.irf_np.get(det, [])).size == 0
        ):
            return f"no IRF for detector {det!r} (load or send an IRF)"
        if det not in self.bg_np or np.asarray(self.bg_np.get(det, [])).size == 0:
            return f"no background for detector {det!r}"
        if self.decay is None or np.asarray(self.decay).size == 0:
            return "no decay (load bursts / select a file)"
        return None

    def fit(self) -> FitOutcome | None:
        """Fit the current decay (``update_fit`` without the plots); ``None`` with the reason in :attr:`status`."""
        reason = self.blocked_reason()
        if reason is not None:
            self.status = f"Cannot fit: {reason}"
            return None
        x0, fixed = self.parameter_vector()
        d = np.asarray(self.decay, dtype=np.float64)
        irf_len = int(np.asarray(self.irf_np.get(self.current_detector, [])).size)
        if self.settings.model == TAIL_MODEL:
            return self._fit_tail(d, x0, fixed)
        if irf_len and len(d) != irf_len:
            self.status = f"Cannot fit: decay length {len(d)} != IRF length {irf_len} (rebuild IRF at the current binning)"
            return None
        fit = self.create_fit()
        res = fit.fit(data=d, initial_values=x0, fixed=fixed, include_model=True)
        model = (
            np.asarray(res.model_curve, dtype=float)
            if res.model_curve is not None
            else np.zeros_like(d)
        )
        diverged = float(res.twoIstar) < 0 or not np.isfinite(float(res.twoIstar))
        curves = decay_curves(
            d,
            model,
            self.irf(),
            self.background(),
            self.window_ranges(),
            tail=self.settings.model == "tail",
            diverged=diverged,
            irf_range=(self.settings.irf_start, self.settings.irf_stop),
            data_all=self.decay_all(self.decay),
        )
        self.outcome = FitOutcome(
            np.asarray(res.x, dtype=float),
            float(res.twoIstar),
            list(fit.parameter_names),
            curves,
            model,
            d,
            res,
        )
        self.status = "" if not diverged else "Fit diverged: invalid fit quality (2I* < 0)"
        return self.outcome

    def _fit_tail(self, d: np.ndarray, x0: np.ndarray, fixed: np.ndarray) -> FitOutcome | None:
        """Fit the tail of the total decay (VV + VH) with a sum of exponentials; no IRF is deconvolved.

        Each exponential decays from ``tail_start`` (a channel of the binned decay) and the rise and prompt before it
        are left out. The model is drawn on both polarisations in proportion to their photons in the window.
        """
        import tttrlib

        n = d.size // 2
        total = d[:n] + d[n:]
        bg = np.asarray(self.background(), dtype=np.float64)
        bg_total = bg[:n] + bg[n : 2 * n] if bg.size >= 2 * n else np.zeros(n)
        if bg_total.sum() > 0:
            bg_total = bg_total / bg_total.sum()
        tttr = self.current_tttr()
        dt, period = self.timing_ns(tttr, self.settings.micro_time_binning)
        if dt is None or period is None:
            self.status = "Cannot fit: the file has no timing (channel width, excitation period)."
            return None
        tail_start = int(round(float(x0[0])))
        lifetimes = [float(v) for v in x0[1:]]
        options = tttrlib.DecayFitNExpOptions()
        options.dt = float(dt)
        options.period = float(period)
        options.tail_start = tail_start
        options.include_model = True
        res = tttrlib.DecayFitNExp.fit(
            total.tolist(),
            [0.0] * n,
            bg_total.tolist(),
            lifetimes,
            [1.0 / len(lifetimes)] * len(lifetimes),
            [int(v) for v in np.asarray(fixed)[1:]],
            options,
        )
        model_total = np.asarray(res.model, dtype=float)
        if model_total.size != n:
            model_total = np.zeros(n)
        model_total[:tail_start] = 0.0  # before the tail the model is not defined
        share = float(d[:n].sum() / total.sum()) if total.sum() > 0 else 0.5
        model = np.hstack([model_total * share, model_total * (1.0 - share)])
        x = np.asarray([float(tail_start)] + [float(v) for v in res.lifetimes], dtype=float)
        score = float(res.negative_log_likelihood)
        irf = self.irf() if self.current_detector in self.irf_np else np.zeros_like(d)
        curves = decay_curves(
            d,
            model,
            irf,
            self.background(),
            self.window_ranges(),
            tail=True,
            diverged=False,
            data_all=self.decay_all(self.decay),
        )
        self.outcome = FitOutcome(x, score, list(TAIL_SCHEMA["properties"]), curves, model, d, res)
        self.status = "" if np.isfinite(score) else "Tail fit failed: non-finite score"
        return self.outcome

    # -- batch ------------------------------------------------------------------------------------------------- #
    def batch_config(self, det: str) -> dict:
        """The per-detector constants a worker needs: window, timing, polarisation, start values, IRF, background."""
        st = self.settings_of(det)
        info = self.detectors.get(det, {})
        tttr = self.current_tttr()
        dt, period = self.timing_ns(tttr, st.micro_time_binning)
        dt, period = (1.0 if dt is None else dt), (1.0 if period is None else period)
        sb, eb = st.micro_time_start, st.micro_time_stop
        if eb <= sb:
            sb, eb = self.micro_time_range
        irf = (
            process_irf(
                self.irf_np.get(det),
                micro_time_range=(sb, eb),
                binning=st.micro_time_binning,
                shift=st.shift,
                shift_sp=st.shift_sp,
                shift_ss=st.shift_ss,
                irf_start=st.irf_start,
                irf_stop=st.irf_stop,
                threshold_vv=st.irf_threshold_vv,
                threshold_vh=st.irf_threshold_vh,
            )
            if np.asarray(self.irf_np.get(det, [])).size
            else np.asarray(self.irf_np.get(det, np.array([])), dtype=float)
        )
        raw_bg = np.asarray(self.bg_np.get(det, np.array([])), dtype=float)
        bg = process_background(raw_bg, st.shift, irf) if raw_bg.size else raw_bg
        names, x0, fixed = st.parameter_state()
        # The setup's detector gates (step 0's PIE windows) bound the fit as they bound the preview decay.
        vv_sb, vv_eb, vh_sb, vh_eb = window_bins(
            info.get("micro_time_ranges"), (sb, eb), st.micro_time_binning, len(info.get("chs", []))
        )
        return {
            "sb": int(vv_sb),
            "eb": int(vv_eb),
            "vh_sb": int(vh_sb),
            "vh_eb": int(vh_eb),
            "dt": float(dt),
            "period": float(period),
            "g_factor": float(info.get("g_factor", 1.0)),
            "l1": float(info.get("l1", 0.0)),
            "l2": float(info.get("l2", 0.0)),
            "p2s_twoIstar": bool(st.p2s_twoIstar),
            "BIFL_scatter": bool(st.BIFL_scatter),
            "min_photons": int(st.min_photons),
            "state_min_photons": int(self.state_min_photons),
            "x0": x0,
            "fixed": fixed,
            "irf": np.asarray(irf, dtype=np.float64),
            "bg": np.asarray(bg, dtype=np.float64),
            "model": st.model,
            "param_names": names,
        }

    def batch_fingerprint(self) -> str:
        """Identify what :meth:`run_batch` would compute, so an unchanged request can be recognised.

        It covers the burst files (path, size, mtime), every detector's batch constants -- window, timing,
        polarisation, start values *and the IRF and background arrays themselves*, so a pattern sent over from the
        IRF & Background step counts as a change -- the split by state, the reading correction in force and the code
        that does the fitting (this tool's :data:`ALGORITHM_VERSION` plus the library builds).
        """
        from chisurf.core.runtime import analysis_cache

        params = {
            "detectors": {det: self.batch_config(det) for det in self.detectors},
            "split_by_state": bool(self.split_by_state),
            "reading": analysis_cache.photon_read_context(),
        }
        return analysis_cache.fingerprint(
            list(self.bur_files),
            params,
            extra=analysis_cache.algorithm_tag("burst_mle", ALGORITHM_VERSION, "fit2x", "tttrlib"),
        )

    def run_batch(
        self, progress=None, max_workers: int | None = None, should_stop=None
    ) -> list[dict]:
        """Fit every burst of every loaded file and detector in worker processes.

        The photon channels and micro times of each raw file go to the workers through shared memory; each worker
        returns one row per burst (``Tau (G|G)``, ``gamma (G|G)``, ...). Nothing is exported here: the rows are kept
        on :attr:`burst_results`.
        """
        import multiprocessing as mp
        import os
        from concurrent.futures import as_completed
        from concurrent.futures.process import BrokenProcessPool
        from multiprocessing import shared_memory

        from ._mp_worker import process_one_file_worker

        if self.df_bursts is None or not len(self.tttrs):
            raise ValueError("No burst data loaded.")
        det_order = list(self.detectors)
        binning = int(self.settings.micro_time_binning)
        configs = {det: self.batch_config(det) for det in det_order}
        # one polarisation's histogram length: the IRF's -- or, for a model without one (the tail
        # fit), one excitation period of the measurement at this binning
        from chisurf.core.fio.micro_time import channels_per_period

        first_tttr = self.current_tttr()
        period_bins = (
            -(-channels_per_period(first_tttr) // max(1, binning)) if first_tttr is not None else 1
        )
        for det, cfg in configs.items():
            cfg["half_len"] = max(1, cfg["irf"].size // 2) if cfg["irf"].size else max(1, period_bins)
        rc_max_seen = max(
            (int(np.max(info["chs"])) for info in self.detectors.values() if info.get("chs")),
            default=0,
        )
        identity_column = (
            "_measurement_path"
            if "_measurement_path" in column_names(self.df_bursts)
            else "First File"
        )
        first_file = np.array([str(v) for v in self.df_bursts[identity_column]], dtype=object)
        fp = numeric_column(self.df_bursts, "First Photon")
        lp = numeric_column(self.df_bursts, "Last Photon")
        groups: dict = {}
        for fname in dict.fromkeys(first_file.tolist()):
            mask = first_file == fname
            groups[fname] = list(zip(fp[mask].tolist(), lp[mask].tolist()))
        # Per-photon H2MM states, when the batch is split by state.
        state_arrays: dict[str, np.ndarray] = {}
        n_states = 0
        if self.split_by_state:
            from . import state_split

            state_arrays, n_states, self.status = self.state_arrays_by_measurement()
        self.n_states = int(n_states)
        blocks: list[shared_memory.SharedMemory] = []
        #: one worker argument tuple per measurement
        jobs: list[tuple] = []
        try:
            for fname, bursts in groups.items():
                tttr = self.tttrs.get(
                    fname if identity_column == "_measurement_path" else Path(fname).stem
                )
                if tttr is None:
                    jobs.append(
                        (
                            fname,
                            bursts,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            det_order,
                            {},
                            int(self.settings.shift or 0),
                            None,
                        )
                    )
                    continue
                rc_full = np.asarray(tttr.routing_channels)
                mt_full = np.asarray(tttr.micro_times)
                mt_bins = (
                    (mt_full // binning).astype(np.int32, copy=False)
                    if binning > 1
                    else mt_full.astype(np.int32, copy=True)
                )
                if rc_full.dtype != np.uint16 and int(rc_full.max(initial=0)) <= 65535:
                    rc_full = rc_full.astype(np.uint16, copy=False)
                if mt_bins.dtype != np.uint16 and int(mt_bins.max(initial=0)) <= 65535:
                    mt_bins = mt_bins.astype(np.uint16, copy=False)
                rc_shm = shared_memory.SharedMemory(create=True, size=rc_full.nbytes)
                np.ndarray(rc_full.shape, dtype=rc_full.dtype, buffer=rc_shm.buf)[:] = rc_full
                mt_shm = shared_memory.SharedMemory(create=True, size=mt_bins.nbytes)
                np.ndarray(mt_bins.shape, dtype=mt_bins.dtype, buffer=mt_shm.buf)[:] = mt_bins
                blocks.extend([rc_shm, mt_shm])
                # The per-photon state, indexed as the routing channels are, in a third shared block.
                state_info = None
                states_full = state_arrays.get(fname)
                if states_full is not None and n_states > 0:
                    states_full = np.ascontiguousarray(states_full, dtype=np.int8)
                    st_shm = shared_memory.SharedMemory(create=True, size=states_full.nbytes)
                    np.ndarray(states_full.shape, dtype=states_full.dtype, buffer=st_shm.buf)[:] = (
                        states_full
                    )
                    blocks.append(st_shm)
                    state_info = (
                        st_shm.name,
                        states_full.shape,
                        str(states_full.dtype),
                        int(n_states),
                    )
                rc_max = int(rc_full.max(initial=rc_max_seen)) if rc_full.size else rc_max_seen
                perdet = {}
                for det in det_order:
                    chs = self.detectors[det].get("chs", [])
                    # A one-channel detector has no polarisation: its photons are both halves (as in
                    # vv_vh_histogram, the preview), not all VH with an empty VV.
                    mirror = len(chs) < 2
                    pchs = np.asarray(chs if mirror else chs[::2], dtype=int)
                    schs = np.asarray([] if mirror else chs[1::2], dtype=int)
                    lut = np.full(rc_max + 1, -1, dtype=np.int8)
                    if pchs.size:
                        lut[pchs] = 0
                    if schs.size:
                        lut[schs] = 1
                    perdet[det] = dict(configs[det], class_lut=lut, mirror=mirror)
                    if configs[det].get("model") == TAIL_MODEL:
                        # where this detector's tail starts: after the peak of its decay, pooled
                        # over every burst photon of the file (a burst alone is too thin)
                        perdet[det]["tail_bin"] = _tail_start_bin(
                            rc_full, mt_bins, bursts, chs, configs[det]["sb"], configs[det]["eb"]
                        )
                    timing = self.timing_ns(tttr, binning)
                    if timing[0] is not None and timing[1] is not None:
                        perdet[det]["dt"], perdet[det]["period"] = timing
                jobs.append(
                    (
                        fname,
                        bursts,
                        rc_shm.name,
                        rc_full.shape,
                        str(rc_full.dtype),
                        mt_shm.name,
                        mt_bins.shape,
                        str(mt_bins.dtype),
                        det_order,
                        perdet,
                        int(self.settings.shift or 0),
                        state_info,
                    )
                )
            ctx = mp.get_context("spawn")
            workers = max_workers or fit_workers()
            # A file's bursts are independent: chopped into chunks, every core fits (one job per file
            # left one measurement -- the usual case -- on one core).
            jobs = _chop_jobs(jobs, workers)
            results: list[dict] = []
            total = int(row_count(self.df_bursts))
            done = 0
            # The pooled per-state fit comes first: its lifetimes are the numbers to quote and the start values of
            # every per-burst fit of that state.
            self.state_lifetimes = []
            if n_states > 0 and jobs:
                from . import state_split

                model = self.settings_of(det_order[0]).model if det_order else self.template.model
                self.state_lifetimes, _seeded, self.status = state_split.pooled_state_fits(
                    jobs,
                    det_order,
                    ctx,
                    workers,
                    model,
                    ["tau", "gamma", "r0", "rho"],
                    int(self.settings.shift or 0),
                    should_stop=should_stop,
                )
            ex = fit_pool(workers)
            futures = {ex.submit(process_one_file_worker, j): i for i, j in enumerate(jobs)}
            # in job order (files, then their chunks in burst order), whichever chunk finished first
            by_job: list[list[dict]] = [[] for _ in jobs]
            for fut in as_completed(futures):
                if should_stop is not None and should_stop():
                    for pending in futures:
                        pending.cancel()
                    raise InterruptedError("The burst fit was stopped.")
                index = futures[fut]
                try:
                    out, n = fut.result()
                except BrokenProcessPool:
                    _drop_fit_pool()
                    raise
                except Exception as exc:  # a chunk failed: name the file rather than export a short table
                    self.status = f"{jobs[index][0]} failed: {exc}"
                    out, n = [], 0
                by_job[index] = out
                done += n
                if progress is not None:
                    progress(min(done, total), total)
            for out in by_job:
                results.extend(out)
        finally:
            for block in blocks:
                try:
                    block.close()
                    block.unlink()
                except Exception:
                    pass
        self.burst_results = results
        self.batch_settings_snapshot = copy.deepcopy(self.channel_settings())
        self.batch_files_snapshot = self.measurement_files()
        return results

    # -- export and settings ----------------------------------------------------------------------------------- #
    def channel_settings(self) -> dict:
        """The per-detector state written beside the tables as ``channel_settings.json``."""
        return {det: dataclasses.asdict(self.settings_of(det)) for det in self.detectors}

    def export_results(self, tick=None) -> list[Path]:
        """Write the ``b?4`` tables of the last batch beside the burst folders."""
        files_by_stem = self.batch_files_snapshot or self.measurement_files()
        rows = []
        for row in self.burst_results:
            identity = str(row["First File"])
            stem = identity if identity in files_by_stem else Path(identity).stem
            if stem in files_by_stem:
                rows.append(dict(row, **{"First Stem": stem}))
        if not rows:
            raise ValueError("No burst-fit rows to save: run the batch first.")
        det_meta = {}
        settings = self.batch_settings_snapshot or self.channel_settings()
        for det, payload in settings.items():
            st = MleSettings(**payload)
            names, _, _ = st.parameter_state()
            from ._mp_worker import colour_of, letter_of

            color = colour_of(det)
            det_meta[det] = (
                color,
                letter_of(det),
                state_result_columns(color, st.model, names, self.n_states),
            )
        in_container = [r for r in rows if _is_container(files_by_stem[r["First Stem"]])]
        legacy = [r for r in rows if not _is_container(files_by_stem[r["First Stem"]])]
        paths: list[Path] = []
        if legacy:
            written = write_b4_tables(legacy, files_by_stem, det_meta, settings, tick=tick)
            paths = [] if written is None else list(written[0])
        if in_container:
            # `First Stem` of a container row is the container itself: one container is one measurement.
            containers = write_container_tables(
                [dict(r, **{"First Stem": r["First File"]}) for r in in_container],
                det_meta,
                settings,
                state_rows=self.state_lifetimes or None,
                experiment=self.experiment_payload(),
                tick=tick,
            )
            paths += containers or []
        if self.state_lifetimes:
            from . import state_split

            roots = {p.parent.parent for p in self.bur_files if not _is_container(p)}
            if roots:
                paths += state_split.write_state_lifetimes(self.state_lifetimes, roots)
        return paths

    def experiment_payload(self) -> dict:
        """The IRF and background each detector's fit used, in the layout the container writer takes."""
        detectors = {}
        for det in self.detectors:
            detectors[det] = {
                key: np.asarray(source.get(det, []), dtype=float).ravel().tolist()
                for key, source in (("irf", self.irf_np), ("background", self.bg_np))
            }
        return {"format": "chisurf-burst-experiment", "version": 1, "detectors": detectors}

    def settings_payload(self) -> dict:
        """Everything a settings file holds: the detector definition and every detector's settings."""
        return {
            "file_type": self.file_type,
            "detectors": self.detectors,
            "definition": self.definition_payload(),
            "micro_time_binning": int(self.template.micro_time_binning),
            "detector_settings": self.channel_settings(),
            "irf_files": {d: [str(p) for p in v] for d, v in self.irf_files.items()},
            "bg_files": {d: [str(p) for p in v] for d, v in self.bg_files.items()},
            "irf_one_for_all": bool(self.irf_one_for_all),
            "bg_one_for_all": bool(self.bg_one_for_all),
            "save_vv_vhs": bool(self.save_vv_vhs),
        }

    def apply_settings_payload(self, payload: dict) -> None:
        """Load a settings file written by :meth:`settings_payload`."""
        known = {f.name for f in dataclasses.fields(MleSettings)}
        restored = {}
        for det, values in (payload.get("detector_settings") or {}).items():
            settings = MleSettings(**copy.deepcopy({k: v for k, v in values.items() if k in known}))
            validate_fit_model(settings.model)
            restored[det] = settings
        if payload.get("detectors"):
            self.set_detectors(payload["detectors"], payload.get("file_type"))
        if payload.get("definition"):
            self.set_definition(payload["definition"])
        self.det_settings.update(restored)
        if payload.get("micro_time_binning"):
            self.set_binning(int(payload["micro_time_binning"]))
        self.irf_one_for_all = bool(payload.get("irf_one_for_all", self.irf_one_for_all))
        self.bg_one_for_all = bool(payload.get("bg_one_for_all", self.bg_one_for_all))
        self.save_vv_vhs = bool(payload.get("save_vv_vhs", self.save_vv_vhs))
        for kind, key in (("bg", "bg_files"), ("irf", "irf_files")):
            files, _np, _normalize, _one = self._pattern_store(kind)
            for det, paths in (payload.get(key) or {}).items():
                found = [Path(p) for p in paths if Path(p).is_file()]
                if det in self.detectors and found:
                    files[det] = found
        self.refresh_pattern_files()

    # -- inspected burst --------------------------------------------------------------------------------------- #
    def inspect_burst(self, idx: int) -> dict[str, np.ndarray]:
        """Per detector, the VV | VH histogram of burst *idx* of the table (``Last Photon`` is inclusive)."""
        if self.df_bursts is None or not len(self.tttrs):
            return {}
        n = int(row_count(self.df_bursts))
        if not 0 <= idx < n:
            return {}
        names = column_names(self.df_bursts)
        key = (
            str(self.df_bursts["_measurement_path"][idx])
            if "_measurement_path" in names
            else Path(str(self.df_bursts["First File"][idx])).stem
        )
        tttr = self.tttrs.get(key)
        if tttr is None:
            return {}
        first = int(numeric_column(self.df_bursts, "First Photon")[idx])
        last = int(numeric_column(self.df_bursts, "Last Photon")[idx])
        burst = tttr[first : last + 1]
        return {
            det: burst_histogram(
                burst, info.get("chs", []), self.micro_time_range, self.settings.micro_time_binning
            )
            for det, info in self.detectors.items()
        }
