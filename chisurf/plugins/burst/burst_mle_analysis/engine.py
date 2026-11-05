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
import functools
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
    channels. The fit window *micro_time_range* (Window start / stop, in bins) is what is fitted, as the
    user set it: it may reach past the gate. A window not set (``stop <= start``, the default
    ``(-1, -1)``) is the first gate, and without gates every channel. *n_channels* is accepted for
    call-site symmetry and not used.
    """
    sb, eb = int(micro_time_range[0]), int(micro_time_range[1])
    if eb > sb >= 0:
        return (sb, eb, sb, eb)
    ranges = [r for r in (detector_ranges or []) if r is not None and len(r) >= 2]
    if not ranges:
        return (0, ALL_BINS, 0, ALL_BINS)
    b = max(1, int(binning))
    lo, hi = int(ranges[0][0] // b), int(ranges[0][1] // b)
    return (lo, hi, lo, hi)


#: The stop of a window that keeps every channel (histograms clip it to their length).
ALL_BINS = 1 << 30


def fit_window(ranges: tuple[int, int, int, int], n: int) -> tuple[int, int] | None:
    """The ``(start, stop)`` the estimator fits (``Fit2xSettings.fit_window``) from the
    per-polarisation windows :func:`window_bins` gives: the bins both halves cover, ``None``
    when that is every bin. Fit2x normalises its model over the bins it is given, so zeroing the
    data outside the window is not a window -- it scores those zeros."""
    start = max(0, min(int(ranges[0]), int(ranges[2])))
    stop = min(int(n), max(int(ranges[1]), int(ranges[3])))
    if stop <= start or (start == 0 and stop >= n):
        return None
    return start, stop


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
    """The IRF as the fit sees it: VH rolled, sub-bin shifted, clipped and its background level taken off."""
    if arr is None:
        stop = int(micro_time_range[1]) if int(micro_time_range[1]) > 0 else 4096
        length = max(2, (stop // max(1, int(binning))) * 2)
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
    # The thresholds are each polarisation's background level, a fraction of its peak: what lies
    # at or below it is background, so it is taken off every bin (not only the bins under it,
    # which left the floor under the prompt and a step at its foot).
    for part, level in ((sp, threshold_vv), (ss, threshold_vh)):
        if level > 0 and part.size and part.max() > 0:
            part -= level * part.max()
            np.clip(part, 0.0, None, out=part)
    return np.hstack([sp, ss])


def single_molecule(macro_s: np.ndarray, bin_s: float = 1e-3) -> bool:
    """Whether a measurement is at single-molecule conditions: in 1 ms bins its count rate sits
    near the background most of the time and bursts stand far above it (the median bin under a
    fifth of the 99.5th percentile); a bulk solution is bright all the time (its median is about
    its mean). What tells a reference dye measured like the sample (same count rates, same
    pile-up) from a bulk one."""
    macro_s = np.asarray(macro_s, dtype=float)
    if macro_s.size < 1000:
        return False
    counts = np.bincount(((macro_s - macro_s[0]) / bin_s).astype(np.int64))
    if counts.size < 100:
        return False
    return bool(np.median(counts) < 0.2 * np.percentile(counts, 99.5))


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


#: Bins kept clear of the IRF's onset when the floor of a decay is read before its prompt.
FLOOR_MARGIN_BINS = 3
#: Fewest bins before the prompt a floor is read from: fewer leave it to the background rate.
MIN_FLOOR_BINS = 8


def decay_floor(
    decay: np.ndarray, irf: np.ndarray | None, gate: tuple[int, int] | None
) -> tuple[float, float, int] | None:
    """The flat floor of a VV | VH decay, counts per bin of each polarisation: the mean of the
    bins of the gate before its prompt (before the IRF rises above a thousandth of its peak,
    less :data:`FLOOR_MARGIN_BINS`). There nothing of this pulse has arrived and the previous
    pulse's fluorescence has decayed, so what is left is constant over the period: detector dark
    counts, afterpulsing (a share of the detected signal, so higher inside bursts than outside)
    and uncorrelated light. ``(vv, vh, bins)``; ``None`` with fewer than :data:`MIN_FLOOR_BINS`
    such bins (a prompt at the gate's start)."""
    decay = np.asarray(decay, dtype=float)
    n = decay.size // 2
    if n < MIN_FLOOR_BINS:
        return None
    lo, hi = gate if gate is not None else (0, n)
    lo, hi = max(0, int(lo)), min(n, int(hi))
    irf = np.asarray(irf, dtype=float) if irf is not None else np.zeros(0)
    floors = []
    for half in (0, 1):
        stop = hi
        if irf.size == 2 * n:
            part = irf[half * n : (half + 1) * n][lo:hi]
            if part.size and part.max() > 0:
                stop = lo + int(np.flatnonzero(part > 1e-3 * part.max())[0]) - FLOOR_MARGIN_BINS
        if stop - lo < MIN_FLOOR_BINS:
            return None
        floors.append((float(decay[half * n + lo : half * n + stop].mean()), stop - lo))
    return floors[0][0], floors[1][0], min(floors[0][1], floors[1][1])


def with_floor(
    pattern: np.ndarray, floor: tuple[float, float], gate: tuple[int, int] | None,
    reference: tuple[float, float] | None = None,
) -> np.ndarray:
    """*pattern* (a background in counts, VV | VH) with its flat part replaced by *floor*
    (counts per bin, each polarisation, inside the *gate*): what lies above the pattern's own
    flat level *reference* (its scatter) is kept. *reference* ``None``: the pattern's own floor
    is taken as zero (it is all scatter)."""
    pattern = np.asarray(pattern, dtype=float)
    n = pattern.size // 2
    lo, hi = gate if gate is not None else (0, n)
    out = np.zeros_like(pattern)
    for half in (0, 1):
        part = pattern[half * n : (half + 1) * n]
        own = float(reference[half]) if reference is not None else 0.0
        excess = np.clip(part - own, 0.0, None)
        flat = np.zeros(n)
        flat[max(0, lo) : min(n, hi)] = float(floor[half])
        out[half * n : (half + 1) * n] = flat + excess
    return out


def flat_scatter_background(*args, **kwargs):
    """The flat + scatter background of a histogram of background photons: the burst
    background estimator's (:func:`chisurf.core.fluorescence.burst.irf_bg.flat_scatter_background`),
    imported when used."""
    from chisurf.core.fluorescence.burst.irf_bg import flat_scatter_background as estimate

    return estimate(*args, **kwargs)


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
    results, det_meta, parameters, *, state_rows=None, experiment=None, tick=None, background=None
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
    state_rows, experiment, background : optional
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
                background=background,
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

#: The time shifts of a detector, as the Fit parameters table names them: ``(setting, label)``.
#: ``shift_sp`` / ``shift_ss``: the IRF against the VV / VH data (bins, sub-bin); ``shift``: the VH
#: decay against the VV decay (whole bins, the VH half of the data rolled).
SHIFT_PARAMETERS = (
    ("shift_sp", "IRF shift VV"),
    ("shift_ss", "IRF shift VH"),
    ("shift", "Shift VV/VH"),
)
#: How far an unfixed shift is refined from its start by the decay fit, bins.
SHIFT_BOUNDS = {"shift_sp": 0.5, "shift_ss": 0.5, "shift": 1}

#: The IRF models of the Auto IRF/background estimate: (value, label).
#: Where Burst MLE takes a detector's IRF from: (key, the selector's label). Every one is the IRF
#: Estimation tool's extraction (``irf_estimator/core/extraction.py``).
IRF_CHOICES = [
    ("auto", "Auto"),
    ("measurement", "IRF measurement"),
    ("reference", "Reference dye"),
    ("outside", "Outside the bursts"),
    ("estimate", "Estimate from the data"),
]

#: The IRF tool's source kinds (:data:`...extraction.AUTO_ORDER`) as Burst MLE's choices.
_CHOICE_OF_SOURCE = {"reference": "reference", "scatter": "measurement", "non_burst": "outside", "blind": "estimate"}

IRF_MODELS = [
    ("gaussian", "Gaussian"),
    ("skewed", "Skewed Gaussian"),
    ("experimental", "Experimental"),
]

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
ALGORITHM_VERSION = 2

TAIL_MODEL = "tail"

#: The largest share of a strict background selection's photons that may be fluorescence (the
#: flat + scatter + exponentials fit of :func:`flat_scatter_background`) for its histogram to be
#: the fit's background as it is; above it the selection still holds molecules and the flat +
#: scatter model of it is taken.
MAX_FLUORESCENCE_SHARE = 0.1

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


# -- the fit threads and the batch pool ------------------------------------------------------------ #
#: The worker processes of More samples (``more_samples.batch_pool``: each analyses a sample),
#: kept between batches: spawning them (a Python start and the imports each) costs about a second.
#: The burst fit itself runs on threads (:meth:`MleSession.run_batch`), not here.
_FIT_POOL: Any = None
_FIT_POOL_WORKERS = 0


#: Resident memory of one pool process at its peak, measured on DNA13bp_3.ptu (12 M photons,
#: 22 000 bursts, ssh home): a fit worker 0.08-0.13 GB, the More samples worker that searches and
#: analyses a whole sample 0.75 GB -- the largest any use of this pool makes. The pool may claim
#: half of the memory available at start.
FIT_WORKER_GB = 0.75
FIT_POOL_MEMORY_SHARE = 0.5


def fit_workers() -> int:
    """Workers of the burst fit -- its threads (:meth:`MleSession.run_batch`) and the processes of
    the More samples pool (:func:`fit_pool`): every core but one (the UI's), as many as memory allows.

    Counting cores alone started 7 spawned processes per ChiSurf on an 8-core, 16 GB laptop and
    kept them; a few ChiSurf processes at once (a second window, a batch, tests) took 87 Python
    processes and 34 GB, and macOS ran out of memory. ``CHISURF_FIT_WORKERS`` overrides the count.
    """
    import os

    override = os.environ.get("CHISURF_FIT_WORKERS", "").strip()
    if override.isdigit() and int(override) > 0:
        return int(override)
    cores = max(1, (os.cpu_count() or 2) - 1)
    try:
        import psutil

        available_gb = psutil.virtual_memory().available / 1e9
    except Exception:  # noqa: BLE001 - no psutil: one worker per two cores, at most four
        return max(1, min(cores // 2, 4))
    by_memory = int(available_gb * FIT_POOL_MEMORY_SHARE / FIT_WORKER_GB)
    return max(1, min(cores, by_memory))


def fit_pool(workers: int | None = None):
    """The kept pool of *workers* processes (More samples' batch pool): started on first use, shut down after a minute
    without a fit (``CHISURF_POOL_IDLE_S``) and started again by the next
    (:class:`chisurf.core.runtime.idle_pool.IdlePool`): kept for the life of the window, the
    processes of a few ChiSurf windows held memory nobody used."""
    from chisurf.core.runtime.idle_pool import IdlePool

    global _FIT_POOL, _FIT_POOL_WORKERS
    workers = int(workers or fit_workers())
    if _FIT_POOL is None or _FIT_POOL_WORKERS != workers:
        _drop_fit_pool()
        _FIT_POOL = IdlePool(workers, name="burst-fit")
        _FIT_POOL_WORKERS = workers
        import atexit

        atexit.register(_drop_fit_pool)
    return _FIT_POOL


def warm_fit_pool() -> None:
    """Start the pool's processes now (in the background), so the first batch does not wait for them."""
    from ._mp_worker import warm

    pool = fit_pool()
    for _ in range(_FIT_POOL_WORKERS):
        pool.submit(warm)


def warm_fit_pool_quietly() -> None:
    """:func:`warm_fit_pool` for a background thread: a failure only means the batch starts them.

    Not under pytest: every test process opening Burst MLE started a pool of its own.
    """
    import os

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        warm_fit_pool()
    except Exception:  # noqa: BLE001
        pass


def _drop_fit_pool() -> None:
    global _FIT_POOL, _FIT_POOL_WORKERS
    pool, _FIT_POOL, _FIT_POOL_WORKERS = _FIT_POOL, None, 0
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


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
    #: The rotation is fitted: fit23 takes it from each decay's steady-state anisotropy (Perrin,
    #: corrected for the background fraction), so a free rho costs no stability; a fixed 1.22 ns
    #: described no dye (Rh110 rotates in 0.17 ns).
    fix_rho: bool = False
    #: The relative shift of the VH decay against VV, whole bins: the VH half of the data (and of
    #: the IRF and background with it) is rolled by it.
    shift: int = 0
    #: The IRF's time shift against the VV and the VH data, bins (sub-bin, linear interpolation).
    shift_sp: float = 0.0
    shift_ss: float = 0.0
    #: The three shifts are held at their start (the calibration, or a value set by hand) unless
    #: unfixed: then the decay fit refines them within :data:`SHIFT_BOUNDS` of the start.
    fix_shift_sp: bool = True
    fix_shift_ss: bool = True
    fix_shift: bool = True
    irf_start: int = -1
    irf_stop: int = -1
    #: Background levels taken off the IRF (a fraction of each polarisation's peak). Zero: every
    #: IRF source (the IRF Estimation tool's extraction) is already free of its background, and
    #: 0.02 cut a deconvolved IRF's tail at 2 % of its peak (a reference dye then fitted at chi2_r
    #: 4.1 instead of 1.5).
    irf_threshold_vv: float = 0.0
    irf_threshold_vh: float = 0.0
    #: The fit window in bins; ``-1, -1``: not set, the detector's gate (:func:`window_bins`).
    micro_time_start: int = -1
    micro_time_stop: int = -1
    micro_time_binning: int = 1
    min_photons: int = 5
    #: The fit's flat background is the burst decay's own floor before the prompt
    #: (:func:`decay_floor`: dark counts, afterpulsing, uncorrelated light); off: the background
    #: rate times the time in the bursts alone, which misses the afterpulsing of the burst
    #: photons and left the summed decay's tail under its floor.
    floor_from_bursts: bool = True
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
    #: The key of the search ahead whose bursts these are, not written to a run yet
    #: (:meth:`take_ahead`); ``""`` for bursts read from a run on disk.
    ahead_key: str = ""
    tttr_paths: dict[str, Path] = field(default_factory=dict)
    current_detector: str = ""
    current_index: int = 0
    irf_np: dict[str, np.ndarray] = field(default_factory=dict)
    #: The photons outside the bursts of the measurement (the reverse burst selection), VV | VH
    #: counts: what the fit background is estimated from when there is no buffer
    #: (:meth:`background_of`: their flat and scatter part, never their decay).
    bg_np: dict[str, np.ndarray] = field(default_factory=dict)
    #: Measured buffer histograms (the background files, counts per second): they correct a scatter
    #: IRF for its background (:meth:`irf_pattern`) and are the fit's background when there is one
    #: (:meth:`background_of`).
    buffer_np: dict[str, np.ndarray] = field(default_factory=dict)
    #: What each detector's fit background was made of (:meth:`background_of`): ``source``
    #: (``buffer`` / ``strict`` / ``model``), the flat levels and scatter amounts, the rate [kHz].
    background_info: dict[str, dict] = field(default_factory=dict)
    #: The strict background selection's histograms (VV | VH counts, :meth:`select_background`):
    #: the photons of the measurement at the background's level, not merely outside a burst.
    bg_strict_np: dict[str, np.ndarray] = field(default_factory=dict)
    #: What the strict selection kept: ``seconds``, ``total_seconds``, ``fraction``,
    #: ``rate_khz``, ``threshold_khz``, ``iterations``, ``photons``, ``warning``.
    strict_background: dict = field(default_factory=dict)
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
    #: What each measured IRF was extracted from (the histograms the IRF Estimation tool was
    #: given: ``kind``, ``vv``, ``vh``, ``dt_ns``, ``window``, ...), so the tool can show and
    #: tune the same extraction.
    irf_inputs: dict[str, dict] = field(default_factory=dict)
    #: Where each detector's IRF is taken from (:data:`IRF_CHOICES`): ``auto`` (the IRF tool's
    #: order: a reference dye, else a measured IRF, else the photons outside the bursts, else an
    #: estimate from the decay), or one of them; ``tuned`` once the IRF tool sent one back.
    irf_choice: dict[str, str] = field(default_factory=dict)
    #: What each source gave, per detector: ``{choice: (irf, text, inputs)}`` -- the IRF tool's
    #: extractions, kept so a choice is switched without reading the files again.
    irf_candidates: dict[str, dict] = field(default_factory=dict)
    #: The reference-dye measurements each detector sees: ``[{"path", "dye", "vv", "vh", "dt_ns",
    #: "window", "single_molecule", "tau_ns", "tau_source"}]`` -- what the IRF's time shifts are
    #: calibrated against (:meth:`calibrate_shift`).
    reference_records: dict[str, list] = field(default_factory=dict)
    #: The IRF time shifts of each detector as calibrated (:meth:`calibrate_shift`): VV, VH in
    #: bins, the dye, its lifetime and where it came from; also what the calibration report keeps.
    shift_calibration: dict[str, dict] = field(default_factory=dict)
    #: Shifts set by hand for a detector -- in Burst MLE's IRF tab or the IRF tool:
    #: ``{"shift_vv", "shift_vh" (bins, sub-bin), "shift" (VH roll, whole bins), "source"}``,
    #: any of the three. They replace the calibrated values until reset (:meth:`reset_shifts`).
    shift_edits: dict[str, dict] = field(default_factory=dict)
    #: Fixed flags of the shifts (``{detector: {"fix_shift_sp": bool, ...}}``) restored before the
    #: detector was defined: applied when the setup brings it (:meth:`set_definition`).
    pending_shift_fixed: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tttrs = LazyTTTRs(self.tttr_paths, self.file_type, self.definition)
        self.det_settings: dict[str, MleSettings] = {}
        #: Rows of the last batch run, one mapping per burst and detector.
        self.burst_results: list[dict] = []
        #: Pooled per-state lifetimes of the last batch (one row per detector and state) and the state count.
        self.state_lifetimes: list[dict] = []
        self.n_states = 0
        self.batch_settings_snapshot: dict[str, dict] = {}
        self._single_molecule: dict[str, bool] = {}
        self._count_rate_khz: dict[tuple, float] = {}
        self.batch_files_snapshot: dict[str, Path] = {}
        #: Shift calibrations by what they were computed from: the detectors of one detection
        #: pair (``R|G``, ``R|R``) calibrated on the same dye with the same IRF share one fit.
        self._shift_cache: dict[tuple, Any] = {}
        #: Each detector's shifts before any calibration or edit (the template's, or the setup's
        #: saved MLE settings): the start of a shift with neither, and what a reset of it restores.
        self._shift_base: dict[str, dict] = {}

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
        """The micro-time binning is global: every detector's histograms and IRF share it.

        A window set in bins of another binning no longer says where it was: it goes back to the
        detector's gate (until it is set again)."""
        binning = int(binning)
        self.template.micro_time_binning = binning
        for st in self.det_settings.values():
            if int(st.micro_time_binning) != binning:
                st.micro_time_start, st.micro_time_stop = -1, -1
            st.micro_time_binning = binning

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
        # the micro-time binning is the setup's (Detector setup), as in Burst Selection
        self.set_binning(max(1, int(reading.get("micro_time_binning") or 1)))
        self.tttrs.set_setup(self.definition)
        # a detector seen for the first time starts with the model its role calls for; a model the
        # user chose stays
        defaults = self.default_models()
        for det in new:
            if det in defaults:
                self.settings_of(det).model = defaults[det]
        for det in [d for d in self.pending_shift_fixed if d in self.detectors]:
            settings = self.settings_of(det)
            for key, value in self.pending_shift_fixed.pop(det).items():
                if hasattr(settings, key):
                    setattr(settings, key, bool(value))

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

    def take_ahead(self, tables: dict, key: str, setup: dict | None = None) -> None:
        """Bursts a search found ahead of time, not written to a run yet: *tables* is
        ``{photon file: burst table}`` (the in-process search result), *key* the search's
        identity (:attr:`ahead_key`). Each file is its own measurement, its photons read from
        the file itself (the shared reading every step holds, not a copy). Everything a run on
        disk allows works -- the decays, the IRF and background, the fits -- except writing the
        results: there is no run to write them into until :meth:`attach_run`.
        """
        from chisurf.core.fio.fluorescence.burst_container import deinterleave_bursts

        self.bur_files, tables_in, raw_paths = [], [], {}
        for photons, table in tables.items():
            if table is None or not row_count(table):
                continue
            path = Path(photons).resolve()
            # one row per burst, as a run is read (the search's table carries the .bur zero
            # rows), and a table of our own: the step's stays as it is
            table = concat_stores([deinterleave_bursts(table)])
            set_constant(table, "burst_file", path.name)
            set_constant(table, "_burst_path", str(path))
            table["_measurement_path"] = [str(path)] * row_count(table)
            tables_in.append(table)
            raw_paths[str(path)] = path
            self.bur_files.append(path)
        self.df_bursts = concat_stores(tables_in) if tables_in else None
        if self.tttr_paths != raw_paths:
            self.tttr_paths.clear()
            self.tttr_paths.update(raw_paths)
            self.tttrs = LazyTTTRs(self.tttr_paths, self.file_type, self.definition)
        self.ahead_key = str(key)
        self.burst_results = []
        self.current_index = 0
        if setup:
            self.set_definition(setup)

    def attach_run(self, runs: collections.abc.Sequence[str | Path]) -> bool:
        """The bursts of the search ahead were written (*runs*, ``m.pto/<run>`` per measurement):
        from now on they are those runs' bursts -- the identities, the burst files and the rows
        fitted ahead name the runs, so the results go into them. Nothing is computed again: the
        photons stay those already read (by their file, a container is not read a second time)
        and every cached decay, background and fit is kept. ``False`` when *runs* are not the
        runs of these bursts (another measurement, other burst counts): then take them as usual.
        """
        from chisurf.core.fio.analysis_path import split_container_path

        if not self.ahead_key or self.df_bursts is None:
            return False
        by_stem = {}
        for run in map(Path, runs):
            box, name = split_container_path(run)
            if box is None or not name:
                return False
            by_stem[Path(box).stem] = (Path(box).resolve(), name, run)
        if set(by_stem) != {p.stem for p in self.bur_files}:
            return False
        key = self._memo_key()
        # a table of its own: the one a job's copy shares with the window is never written into
        self.df_bursts = concat_stores([self.df_bursts])
        identities = np.asarray(self.df_bursts["_measurement_path"], dtype=object)
        new_identity, new_burst, renamed = identities.copy(), identities.copy(), {}
        for photons in self.bur_files:
            box, name, run = by_stem[photons.stem]
            mask = identities == str(photons)
            new_identity[mask] = str(box / name)
            new_burst[mask] = str(Path(run).resolve())
            renamed[str(photons)] = str(box / name)
        self.df_bursts["_measurement_path"] = new_identity.tolist()
        self.df_bursts["_burst_path"] = new_burst.tolist()
        self.df_bursts["burst_file"] = [Path(str(v)).name for v in new_burst]
        paths = {renamed[k]: v for k, v in self.tttr_paths.items()}
        self.tttr_paths.clear()
        self.tttr_paths.update(paths)  # the same LazyTTTRs: its photons are cached by file
        self.bur_files = [by_stem[p.stem][2] for p in self.bur_files]
        for row in self.burst_results:
            if str(row.get("First File")) in renamed:
                row["First File"] = renamed[str(row["First File"])]
        if self.burst_results:
            self.batch_files_snapshot = self.measurement_files()
        self.ahead_key = ""
        memo = self.__dict__.get("_memo_cache")
        if memo is not None and memo.get("key") == key:
            memo["key"] = self._memo_key()  # the same bursts and photons under their run's name
        return True

    @property
    def current_filename(self) -> str:
        return str(self.bur_files[self.current_index]) if self.bur_files else ""

    def _memo(self, name: str, compute):
        """*compute()*, kept until the bursts, the selected file or the loaded measurements change.

        The preview, the setup and the fit each ask for the selected file's photons and burst
        coverage; every answer went through the burst table's text columns (and a list of millions
        of photon indices) again -- 0.4 s on the UI thread per hand-over.
        """
        key = self._memo_key()
        memo = self.__dict__.setdefault("_memo_cache", _Memo())
        if memo.get("key") != key:
            memo.clear()
            memo["key"] = key
        if name not in memo:
            memo[name] = compute()
        return memo[name]

    def _memo_key(self) -> tuple:
        """What :meth:`_memo`'s answers are valid for."""
        df = self.df_bursts
        return (
            id(df),
            row_count(df) if df is not None else 0,
            str(self.current_filename),
            id(self.tttrs),
            tuple(self.tttrs.paths) if hasattr(self.tttrs, "paths") else len(self.tttrs or ()),
            # a new reading (a LUT, another setup's correction) is another photon stream
            repr(getattr(self.tttrs, "_read_signature", None)),
        )

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
        """The current detector's background as the fit takes it (:meth:`background_of`): the
        counts it adds to the burst decay, VV | VH, the VH half rolled with the decay's."""
        return process_background(
            self.background_of(self.current_detector), self.settings.shift, self.irf()
        )

    def background_of(self, det: str) -> np.ndarray | None:
        """The background of *det*'s burst decay, in counts expected inside the bursts (``None``:
        none yet); what it was made of is kept on :attr:`background_info`.

        The photons outside the bursts are not a buffer: molecules below the burst threshold and
        the flanks of every burst are among them, so their histogram is a fluorescence decay and
        their rate several times the background's. In this order:

        1. a **buffer** measurement of Data Selection: its histogram is the shape, its rate the
           rate;
        2. the **strict background selection** of the measurement (:attr:`bg_strict_np`,
           :func:`~chisurf.core.fluorescence.burst.irf_bg.strict_background_mask`: the bursts
           widened by margins, then only the stretches whose local count rate stays at the
           background level), when it kept enough time and its histogram is background-shaped
           (flat + scatter, under :data:`MAX_FLUORESCENCE_SHARE` fluorescence): its histogram and
           its photons over its time;
        3. else a **flat + scatter model** (:func:`flat_scatter_background`: the flat level
           before the prompt, the scatter in the IRF's shape) of the strict selection's
           histogram, or of all photons outside the bursts when the strict one kept too little,
           over that selection's time -- never their decay.

        The rate times the time inside the bursts is the count the fit's background adds."""
        outside = self.bg_np.get(det)
        strict = self.bg_strict_np.get(det)
        selection = self.strict_background or {}
        buffer = self.buffer_np.get(det) if self.bg_files.get(det) else None
        times = self.time_in_bursts()
        irf = self.irf_np.get(det)
        key = (det, id(outside), id(strict), id(buffer), id(irf), times,
               int(self.settings_of(det).micro_time_binning),
               bool(self.settings_of(det).floor_from_bursts))
        cache = self.__dict__.setdefault("_background_cache", {})
        if cache.get(det, (None,))[0] == key:
            return cache[det][1]
        inside = times[0] if times is not None and times[1] > times[0] else None
        info: dict = {}
        if buffer is not None and np.asarray(buffer).size:
            rate = np.asarray(buffer, dtype=float)  # counts per second and bin
            names = ", ".join(Path(p).name for p in self.bg_files.get(det, []))
            info = {"source": "buffer", "files": names}
        elif outside is not None and np.asarray(outside).size:
            tttr = self.current_tttr()
            dt, _period = (
                self.timing_ns(tttr, self.settings_of(det).micro_time_binning)
                if tttr is not None else (None, None)
            )
            enough = strict is not None and np.sum(strict) > 0 and not selection.get("warning")
            # the kept photons over the kept time, corrected for the background's own fast
            # fluctuations the local-rate cut dropped (StrictBackground.rate_scale)
            counts, seconds = (
                (np.asarray(strict, dtype=float),
                 float(selection["seconds"]) / float(selection.get("rate_scale") or 1.0))
                if enough
                else (np.asarray(outside, dtype=float),
                      (times[1] - times[0]) if inside is not None else 1.0)
            )
            irf_raw = np.asarray(irf, dtype=float) if irf is not None else np.zeros_like(counts)
            pattern, parts = flat_scatter_background(
                counts, irf_raw, float(dt or 1.0), self._gate_window(det, counts.size // 2)
            )
            share = float(sum(parts["fluorescence"])) / max(float(counts.sum()), 1e-12)
            info = {"flat": parts["flat"], "scatter": parts["scatter"], "fluorescence_share": share,
                    "outside_khz": float(np.sum(outside)) / max(
                        (times[1] - times[0]) if inside is not None else 1.0, 1e-12) / 1e3,
                    "selection": dict(selection)}
            if enough and share <= MAX_FLUORESCENCE_SHARE:
                rate = counts / max(seconds, 1e-12)
                info["source"] = "strict"
            else:
                rate = pattern / max(seconds, 1e-12)
                info["source"] = "model"
                info["reason"] = (
                    f"the strict selection holds fluorescence ({share:.0%} of its photons)"
                    if enough else (selection.get("warning") or "no strict selection")
                )
                info["model_of"] = "strict" if enough else "outside"
                if inside is not None:
                    # in counts of the burst decay: what the background adds per bin / as scatter
                    scale = inside / max(seconds, 1e-12)
                    info["flat_bursts"] = tuple(v * scale for v in info["flat"])
                    info["scatter_bursts"] = tuple(v * scale for v in info["scatter"])
        else:
            cache[det] = (key, None)
            return None
        info["rate_khz"] = float(rate.sum()) / 1e3
        info["seconds_inside"] = inside
        counts = rate * inside if inside is not None else rate
        counts = self._floor_of_bursts(det, counts, info)
        self.background_info[det] = info
        cache[det] = (key, counts)
        return counts

    def burst_decay_of(self, det: str) -> np.ndarray | None:
        """*det*'s decay of every burst photon of the current file, every channel (not cut to a
        window, the VH half not rolled): what its floor is read from (:func:`decay_floor`)."""
        tttr = self.current_tttr()
        idx = self.burst_index_array()
        chs = self.detectors.get(det, {}).get("chs", [])
        if tttr is None or not chs or idx.size == 0:
            return None
        binning = max(1, int(self.settings_of(det).micro_time_binning))
        photons = self._memo("burst_tttr", lambda: tttr[idx])
        return self._memo(
            f"burst_decay_all{det}{binning}",
            lambda: np.asarray(vv_vh_histogram(
                photons, chs, (0, 0), binning, normalize_counts=0, apply_vh_shift=False
            ), dtype=float),
        )

    def _floor_of_bursts(self, det: str, counts: np.ndarray, info: dict) -> np.ndarray:
        """*counts* (the background inside the bursts, from the background rate) with its flat
        part replaced by the burst decay's own floor (:func:`decay_floor`, when
        ``floor_from_bursts``): the rate counts the dark counts and the uncorrelated light over
        the bursts' time but not the afterpulsing of the burst photons, so the decay's tail stayed
        above the model's floor. What it was, and what the rate alone gave, go to *info*."""
        if not self.settings_of(det).floor_from_bursts:
            return counts
        decay = self.burst_decay_of(det)
        irf = self.irf_np.get(det)
        if decay is None or irf is None or np.asarray(decay).size != np.asarray(counts).size:
            return counts
        gate = self._gate_window(det, decay.size // 2)
        floor = decay_floor(decay, irf, gate)
        if floor is None:
            return counts
        own = decay_floor(counts, irf, gate)
        info["floor_bursts"] = (floor[0], floor[1])
        info["floor_rate"] = (own[0], own[1]) if own is not None else None
        info["floor_bins"] = floor[2]
        return with_floor(counts, floor[:2], gate, own[:2] if own is not None else None)

    def time_in_bursts(self) -> tuple[float, float] | None:
        """``(seconds inside the bursts, seconds of the measurement)`` of the current file."""
        return self._memo("time_in_bursts", self._time_in_bursts)

    def _time_in_bursts(self) -> tuple[float, float] | None:
        tttr = self.current_tttr()
        idx = self.burst_index_array()
        if tttr is None or idx.size == 0:
            return None
        macro = np.asarray(tttr.macro_times, dtype=np.float64) * float(tttr.header.macro_time_resolution)
        breaks = np.flatnonzero(np.diff(idx) != 1)
        starts = np.r_[idx[0], idx[breaks + 1]]
        ends = np.r_[idx[breaks], idx[-1]]
        return float(np.sum(macro[ends] - macro[starts])), float(macro[-1] - macro[0])

    def background_in_bursts(self) -> np.ndarray:
        """The background as the burst decay holds it (the counts it adds to the decay shown):
        :meth:`background`, whose rate is already scaled to the time inside the bursts."""
        return self.background()

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
    def select_background(self, detectors: collections.abc.Iterable[str] | None = None) -> dict:
        """The strict background selection of the current measurement (the burst background
        estimator, :func:`~chisurf.core.fluorescence.burst.irf_bg.strict_background_mask`, judged
        on every detector's photons): its histogram per detector goes to :attr:`bg_strict_np`,
        what it kept to :attr:`strict_background` (returned). Once per measurement."""
        from chisurf.core.fluorescence.burst import extract_mle_irf_background
        from chisurf.core.fluorescence.burst.irf_bg import strict_background_mask

        tttr = self.current_tttr()
        if tttr is None or not self.burst_index_array().size:
            return {}

        from chisurf.core.fluorescence.burst import fused_pipeline

        fused = fused_pipeline.enabled()

        def select():
            if fused:  # natively, histograms instead of a photon mask
                return fused_pipeline.session_strict_background(self, tttr)
            in_burst = np.zeros(len(tttr), dtype=bool)
            in_burst[self.burst_index_array()] = True
            chs = sorted({int(c) for d in self.detectors.values() for c in d.get("chs", [])})
            return strict_background_mask(
                tttr, in_burst, channels=chs or None, accept=self._background_shaped(tttr)
            )

        strict = self._memo(f"strict_background{self._strict_key()}", select)
        self.strict_background = {
            "seconds": strict.seconds, "total_seconds": strict.total_seconds,
            "fraction": strict.fraction, "rate_khz": strict.rate_khz,
            "threshold_khz": strict.threshold_khz, "iterations": strict.iterations,
            "photons": strict.photons, "warning": strict.warning, "rate_scale": strict.rate_scale,
        }
        dets = list(detectors) if detectors is not None else list(self.detectors)
        if strict.photons and isinstance(strict, fused_pipeline.StrictBackground):
            for det, bg in fused_pipeline.session_background_patterns(self, tttr, strict, dets).items():
                self.bg_strict_np[det] = np.asarray(bg, dtype=float)
        elif strict.photons:
            patterns = extract_mle_irf_background(
                tttr, {d: self.detectors[d] for d in dets},
                micro_time_binning=self.settings.micro_time_binning, mask=strict.mask,
                irf_model="experimental",
            )
            for det, pat in patterns.items():
                self.bg_strict_np[det] = np.asarray(pat["bg"], dtype=float)
        else:
            for det in dets:
                self.bg_strict_np.pop(det, None)
        return self.strict_background

    def _strict_key(self) -> tuple:
        """What the strict selection depends on besides the photons and bursts (the memo's own
        key): the binning, each detector's channels and gate, and the content of each IRF it is
        judged by (:meth:`_background_shaped`) -- not the IRF arrays' identity: an IRF taken
        again from the same source is a new array with the same numbers."""
        import hashlib

        parts = [int(self.settings.micro_time_binning)]
        for det in self.detectors:
            irf = np.ascontiguousarray(self.irf_np.get(det, []), dtype=float)
            judged = bool(irf.size and np.any(irf))
            parts.append((
                det, tuple(int(c) for c in self.detectors[det].get("chs", [])),
                self._gate_window(det, irf.size // 2 if judged else None),
                hashlib.sha1(irf.tobytes()).hexdigest() if judged else "",
            ))
        return tuple(parts)

    def _background_shaped(self, tttr: Any):
        """``accept(mask)`` for the strict selection: whether the kept photons of every detector
        with an IRF have a background's histogram -- flat + scatter, at most
        :data:`MAX_FLUORESCENCE_SHARE` of them fluorescence (:func:`flat_scatter_background`);
        ``None`` without an IRF to judge by."""
        binning = max(1, int(self.settings.micro_time_binning))
        routing = np.asarray(tttr.routing_channels)
        micro = np.asarray(tttr.micro_times) // binning
        dt, _period = self.timing_ns(tttr, binning)
        judged = {d: np.asarray(self.irf_np[d], dtype=float) for d in self.detectors
                  if np.asarray(self.irf_np.get(d, [])).size and np.any(self.irf_np[d])}
        if not judged:
            return None

        def accept(mask: np.ndarray) -> bool:
            for det, irf in judged.items():
                chs = self.detectors[det].get("chs", [])
                half = irf.size // 2
                parts = [chs[::2], chs[1::2]] if len(chs) > 1 else [chs, chs]
                hist = np.hstack([
                    np.bincount(np.clip(micro[mask & channel_mask(routing, p)], 0, half - 1),
                                minlength=half)[:half].astype(float)
                    for p in parts
                ])
                if hist.sum() <= 0:
                    continue
                _, found = flat_scatter_background(hist, irf, float(dt or 1.0), self._gate_window(det, half))
                if sum(found["fluorescence"]) > MAX_FLUORESCENCE_SHARE * hist.sum():
                    return False
            return True

        return accept

    def extract_irf_background(self) -> int:
        """IRF and background from the photons outside the bursts, at the current binning; returns the detectors done.

        A detector with a measured IRF keeps it. One with too few photons outside the bursts to
        show a prompt (:data:`MIN_IRF_COUNTS` in its gate) gets the blind estimate from its burst
        decay (:meth:`blind_irf`), the last resort.
        """
        from chisurf.core.fluorescence.burst import extract_mle_irf_background

        tttr = self.current_tttr()
        from chisurf.core.fluorescence.burst import fused_pipeline

        if fused_pipeline.enabled():  # histograms of the photons outside the bursts, natively
            patterns = fused_pipeline.session_outside_patterns(
                self, tttr, self.detectors, irf_model=self.settings.irf_model)
        else:
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
                irf = np.asarray(pat["irf"], dtype=float)
                bg = np.asarray(pat["bg"], dtype=float)
                half = bg.size // 2
                candidates = self.irf_candidates.setdefault(det, {})
                photons = self._background_prompt_photons(tttr, det, ~in_burst)
                if photons > 0 and irf.any():
                    candidates["outside"] = (
                        irf,
                        f"photons outside the bursts ({label})",
                        {
                            "kind": "non_burst", "vv": bg[:half], "vh": bg[half:],
                            "model": self.settings.irf_model, "baseline_quantile": 0.2,
                            "window": self._gate_window(det, half),
                            "name": "photons outside the bursts",
                            "dt_ns": float(tttr.header.micro_time_resolution) * 1e9
                            * max(1, int(self.settings.micro_time_binning)),
                        },
                        photons,
                    )
                else:
                    candidates.pop("outside", None)
                candidates.pop("estimate", None)  # estimated when it is chosen (or the last resort)
                # the photons outside the bursts; the fit's background is the strict selection
                # of them, or a flat + scatter model (background_of)
                self.bg_np[det] = bg
                self.apply_irf_choice(det)
                n += 1
        self.select_background()
        return n

    def irf_options(self, det: str) -> list[tuple[str, str, bool, str]]:
        """``(key, label, available, why not)`` of every IRF source of *det* (:data:`IRF_CHOICES`)."""
        candidates = self.irf_candidates.get(det, {})
        have_bursts = self.current_tttr() is not None and bool(self.burst_index_array().size)
        reasons = {
            "auto": (True, ""),
            "measurement": (
                "measurement" in candidates,
                "No IRF measurement (water, Ludox) of this detector in Data Selection.",
            ),
            "reference": (
                "reference" in candidates,
                "No reference dye of known lifetime seen by this detector in Data Selection.",
            ),
            "outside": ("outside" in candidates, "No photons outside the bursts in this detector's gate."),
            "estimate": (have_bursts, "No bursts loaded."),
        }
        return [(key, label, *reasons[key]) for key, label in IRF_CHOICES]

    def apply_irf_choice(self, det: str) -> str:
        """Take *det*'s IRF from its :attr:`irf_choice` (``auto`` when unset or unavailable); returns
        the source used. Auto: the IRF tool's ``AUTO_ORDER`` -- a reference dye, else a measured
        IRF, else the photons outside the bursts (at least :data:`MIN_IRF_COUNTS` in the gate), else the estimate from the decay."""
        choice = self.irf_choice.get(det, "auto")
        candidates = self.irf_candidates.get(det, {})
        if choice == "tuned" and "tuned" in candidates:
            order = ["tuned"]
        elif choice in ("measurement", "reference", "outside", "estimate"):
            order = [choice]
        else:
            order = []
        # Auto follows the IRF tool's one order (reference dye, scatter, outside, estimate)
        from chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction import AUTO_ORDER

        outside = candidates.get("outside")
        enough = outside is not None and outside[3] >= MIN_IRF_COUNTS
        order += [
            key for key in (_CHOICE_OF_SOURCE[kind] for kind in AUTO_ORDER)
            if key != "outside" or enough
        ]
        for key in order:
            if key == "estimate" and key not in candidates:
                if self.current_tttr() is None or not self.burst_index_array().size:
                    continue
                candidates["estimate"] = self._blind_candidate(det)
            got = candidates.get(key)
            if got is None:
                continue
            self.irf_np[det] = np.asarray(got[0], dtype=float)
            self.irf_source[det] = got[1]
            if got[2] is not None:
                self.irf_inputs[det] = got[2]
            else:
                self.irf_inputs.pop(det, None)
            self.calibrate_shift(det)
            self.outcome = None
            return key
        return ""

    def burst_count_rate_khz(self, det: str) -> float | None:
        """The mean count rate of *det* inside the bursts of the current file [kHz] (``None``:
        no bursts): what a reference measurement's rate is compared with."""
        tttr = self.current_tttr()
        idx = self.burst_index_array()
        times = self.time_in_bursts()
        if tttr is None or not idx.size or times is None or times[0] <= 0:
            return None
        chs = self.detectors[det].get("chs", [])
        photons = int(channel_mask(np.asarray(tttr.routing_channels)[idx], chs).sum())
        return photons / times[0] / 1e3

    def detection_siblings(self, det: str) -> list[str]:
        """The detectors on *det*'s channels (itself included): ``R|G`` and ``R|R`` are one red
        detector pair under two PIE windows. The G factor, the IRF's shape and the detectors'
        timing are properties of the detection side, so one reference calibrates them all."""
        chs = [int(c) for c in self.detectors.get(det, {}).get("chs", [])]
        return [d for d, info in self.detectors.items() if [int(c) for c in info.get("chs", [])] == chs]

    def window_offset(self, det: str, source: str) -> int:
        """Bins from *source*'s PIE window to *det*'s (at the current binning): where *det*'s
        excitation pulse sits relative to *source*'s, from the setup's windows (0 without gates)."""
        a, b = self._gate_window(det), self._gate_window(source)
        if a is None or b is None:
            return 0
        return int(a[0] - b[0])

    def _reference_source(self, det: str, vv: np.ndarray, vh: np.ndarray) -> str:
        """The detector of *det*'s detection pair whose window sees a reference dye best (most
        photons in its gate): ``R|R`` for Alexa 647 -- red-excited, on the red detectors."""
        n = int(np.size(vv))

        def gated(d: str) -> float:
            lo, hi = self._gate_window(d, n) or (0, n)
            return float(np.sum(vv[lo:hi]) + np.sum(vh[lo:hi]))

        return max(self.detection_siblings(det), key=lambda d: (gated(d), d == det))

    def calibrate_shift(self, det: str) -> dict | None:
        """The time shift of *det*'s IRF, VV and VH: calibrated against a reference dye before
        any fit, then any value set by hand on top (:attr:`shift_edits`).

        The calibration (the IRF Estimation tool's :func:`calibrate_shifts`): the dye's decay
        fitted with the IRF, the shifts free, its lifetime fixed to the dye database's (fitted
        where it has none). A dye measured at single-molecule conditions (:func:`single_molecule`)
        is preferred: SPAD timing moves with the count rate, so a reference at the bursts' rates
        has their timing offset, a bulk one at a high rate is shifted (the count rates of both
        are recorded; a bulk reference at more than three times the bursts' rate is warned of).

        The detectors of one detection pair (``R|G``, ``R|R``) are calibrated once, on the
        window that sees the dye (:meth:`_reference_source`), with that detector's G, l1, l2:
        the shifts are the detectors' timing. *det*'s IRF is taken to the calibrating window by
        the PIE window offset (:meth:`window_offset`) and the shifts it gets there are *det*'s.

        The shifts are this detector's ``shift_sp`` (VV) and ``shift_ss`` (VH), fixed in the fit;
        Opt refines them within half a bin. The record keeps the calibrated values
        (``calibrated_vv`` / ``calibrated_vh``) beside those used (``shift_vv`` / ``shift_vh``)
        and what was edited (``edited``). ``None`` (shifts left as they are) without a reference
        dye and without an edit."""
        settings = self.settings_of(det)
        edits = dict(self.shift_edits.get(det) or {})
        base = self.shift_base(det)
        found = self._calibrated_shift(det)
        if found is None and not edits:
            self.shift_calibration.pop(det, None)
            settings.shift_sp, settings.shift_ss = float(base["shift_sp"]), float(base["shift_ss"])
            settings.shift = int(base["shift"])
            return None
        entry = dict(found or {"source": "", "dye": "", "single_molecule": False, "warning": ""})
        calibrated = (entry.get("shift_vv"), entry.get("shift_vh")) if found else (None, None)
        entry["calibrated_vv"], entry["calibrated_vh"] = calibrated
        entry["calibrated_shift"] = int(base["shift"])
        vv = edits.get("shift_vv", calibrated[0] if calibrated[0] is not None else base["shift_sp"])
        vh = edits.get("shift_vh", calibrated[1] if calibrated[1] is not None else base["shift_ss"])
        settings.shift_sp, settings.shift_ss = float(vv), float(vh)
        settings.shift = int(edits.get("shift", base["shift"]))
        entry.update({"shift_vv": float(vv), "shift_vh": float(vh), "shift": int(settings.shift)})
        entry["edited"] = sorted(k for k in ("shift_vv", "shift_vh", "shift") if k in edits)
        if entry["edited"]:
            entry["edit_source"] = str(edits.get("source") or "edited")
            if not found:
                entry["source"] = entry["edit_source"]
            self._fit_at_used_shifts(det, entry)
        self.shift_calibration[det] = entry
        return entry

    def _calibrated_shift(self, det: str) -> dict | None:
        """The calibration of :meth:`calibrate_shift` alone (no edits): ``None`` without a
        reference dye of *det*'s detection pair or without an IRF."""
        records = [r for r in self.reference_records.get(det, []) if np.sum(r["vv"]) > 0]
        irf = np.asarray(self.irf_np.get(det, []), dtype=float)
        if not records or irf.size < 4:
            return None
        sm = [r for r in records if r["single_molecule"]]
        chosen = sm or records
        by_dye: dict[str, list] = {}
        for r in chosen:
            by_dye.setdefault(r["dye"], []).append(r)
        dye, group = max(by_dye.items(), key=lambda kv: sum(np.sum(r["vv"]) for r in kv[1]))
        vv = np.sum([r["vv"] for r in group], axis=0)
        vh = np.sum([r["vh"] for r in group], axis=0)
        if vv.size * 2 != irf.size:
            return None
        from chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction import (
            R0,
            calibrate_shifts,
            reference_rotation,
            reference_tail_lifetime,
        )

        settings = self.settings_of(det)
        source = str(group[0].get("detector") or det)
        if source not in self.detectors:
            source = det
        offset = int(group[0].get("offset_bins") or 0)
        dt, window = group[0]["dt_ns"], group[0]["window"]
        tau = group[0]["tau_ns"]
        two = len(self.detectors[det].get("chs", [])) > 1
        clean = process_irf(
            irf, micro_time_range=(settings.micro_time_start, settings.micro_time_stop),
            binning=settings.micro_time_binning, irf_start=settings.irf_start,
            irf_stop=settings.irf_stop, threshold_vv=settings.irf_threshold_vv,
            threshold_vh=settings.irf_threshold_vh,
        )
        half = clean.size // 2
        if offset:  # the IRF of det's window, taken to the window it is calibrated in
            clean = np.hstack([np.roll(clean[:half], -offset), np.roll(clean[half:], -offset)])
        names = ", ".join(Path(r["path"]).name for r in group)
        # the polarisation factors of the detection side: the calibrating detector's
        g, l1, l2 = (float(self.detectors[source].get(k, d)) for k, d in (("g_factor", 1.0), ("l1", 0.0), ("l2", 0.0)))
        rho = None
        r0 = float(group[0].get("r0") or R0)
        if two:
            # the rotation (and initial anisotropy) the IRF was deconvolved with: one description
            # of the dye for the IRF, the shifts and the reference fit
            rho = group[0].get("rho_ns")
            if rho is None:
                guess = tau or reference_tail_lifetime(vv + 2.0 * vh, dt, window=window) or 4.0
                rho = reference_rotation(vv, vh, dt, guess, window=window, r0=r0)
        import hashlib

        key = (dye, names, hashlib.sha1(clean.tobytes()).hexdigest(), tuple(window or ()), g, l1, l2, tau, rho, r0)
        found = self._shift_cache.get(key)
        if found is None:
            found = calibrate_shifts(
                [vv, vh] if two else [vv], [clean[:half], clean[half:]] if two else [clean[:half]],
                dt, tau_ns=tau, rho_ns=rho, window=window, name=names, g_factor=g, l1=l1, l2=l2, r0=r0,
            )
            if len(self._shift_cache) > 32:
                self._shift_cache.clear()
            self._shift_cache[key] = found
        #: what the shifts were calibrated from, for a fit at shifts set by hand
        self._shift_inputs = getattr(self, "_shift_inputs", {})
        self._shift_inputs[det] = {
            "parts": [vv, vh] if two else [vv], "irfs": [clean[:half], clean[half:]] if two else [clean[:half]],
            "dt": dt, "tau": found.tau_ns, "rho": rho, "r0": r0, "window": window, "g": g, "l1": l1, "l2": l2,
        }
        rates = [r.get("rate_khz") for r in group if r.get("rate_khz") is not None]
        reference_rate = float(np.mean(rates)) if rates else None
        burst_rate = self.burst_count_rate_khz(det)
        warnings = []
        if not sm and reference_rate and burst_rate and reference_rate > 3.0 * burst_rate:
            warnings.append(
                f"only a bulk reference at {reference_rate:.0f} kHz, {reference_rate / burst_rate:.0f}x "
                f"the bursts' {burst_rate:.0f} kHz: SPAD timing moves with the count rate, so the "
                "shift may be off; measure the dye at single-molecule conditions"
            )
        tau_info = dict(group[0].get("tau_info") or {})
        if tau_info and not tau_info.get("consistent", True):
            warnings.append(
                f"{dye}'s tail gives {tau_info['tail']:.2f} ns, the dye database {tau_info['listed']:.2f} ns: "
                f"the database's lifetime does not describe this measurement, {tau_info['tail']:.2f} ns is used"
            )
        anisotropy = None
        if two:
            from chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction import (
                reference_anisotropy,
            )

            anisotropy = reference_anisotropy(vv, vh, g, window=window)
            if anisotropy < -0.05:
                warnings.append(
                    f"VV and VH look swapped on {source}: the reference's anisotropy at its peak is "
                    f"{anisotropy:+.2f} (a free dye's is positive); swap the order of its channels in "
                    "the detector setup (step 0) -- G and the rotation are wrong until then"
                )
        warning = "; ".join(warnings)
        entry = {
            "reference_rate_khz": reference_rate, "burst_rate_khz": burst_rate, "warning": warning,
            "shift_vv": found.shift_vv, "shift_vh": found.shift_vh, "dye": dye, "files": names,
            "single_molecule": bool(sm), "tau_ns": found.tau_ns, "tau_known": found.tau_known,
            "tau_source": group[0]["tau_source"], "rho_ns": rho, "text": found.text,
            "tau_listed_ns": tau_info.get("listed"), "tau_tail_ns": tau_info.get("tail"),
            "tau_consistent": tau_info.get("consistent", True), "anisotropy_peak": anisotropy,
            "r0": r0,
            "source": "single-molecule reference dye" if sm else "reference dye",
            # the detector whose window saw the dye, and how far det's window is from it
            "calibrated_on": source, "offset_bins": offset,
        }
        fit = found.fit
        if fit is not None:
            #: the dye fitted with the burst model at these shifts (the IRF tool's reference_fit):
            #: the data, model and weighted residuals the IRF tab, the IRF tool and the
            #: calibration report show, and the G the reference asks for
            entry.update({
                "fit_chi2r": fit.chi2r, "fit_g": fit.g_factor, "fit_g_fitted": fit.g_fitted,
                "fit_chi2r_g_free": fit.chi2r_g_free, "fit_window": fit.window,
                "fit_data": fit.data, "fit_model": fit.model, "fit_residuals": fit.residuals,
                "fit_text": fit.text,
            })
            if abs(fit.g_fitted - fit.g_factor) > 0.05 * fit.g_fitted and fit.chi2r > 2.0 * fit.chi2r_g_free:
                g_warning = (
                    f"the reference asks for G {fit.g_fitted:.3f}, the setup has {fit.g_factor:.3f} "
                    f"(chi2_r {fit.chi2r:.1f} against {fit.chi2r_g_free:.2f}): apply the G of Data Selection"
                )
                entry["warning"] = "; ".join(w for w in (warning, g_warning) if w)
        return entry

    def _fit_at_used_shifts(self, det: str, entry: dict) -> None:
        """The reference fit at the shifts in use (edited): its chi2_r is ``used_fit_chi2r``."""
        inputs = getattr(self, "_shift_inputs", {}).get(det)
        if not inputs or "fit_chi2r" not in entry:
            return
        from chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction import R0, reference_fit

        try:
            fit = reference_fit(
                inputs["parts"], inputs["irfs"], inputs["dt"], tau_ns=inputs["tau"],
                rho_ns=inputs["rho"] if len(inputs["parts"]) > 1 else None, g_factor=inputs["g"],
                l1=inputs["l1"], l2=inputs["l2"], window=inputs["window"], r0=inputs.get("r0", R0),
                shifts=(entry["shift_vv"], entry["shift_vh"]), hold_shifts=True,
            )
        except Exception:  # noqa: BLE001 - the calibrated fit stays the record
            return
        entry["used_fit_chi2r"] = float(fit.chi2r)

    def set_shift(self, det: str, key: str, value: float) -> dict | None:
        """Set *det*'s ``shift_vv`` / ``shift_vh`` (bins) or ``shift`` (VH roll, whole bins) by
        hand: it replaces the calibrated value until :meth:`reset_shifts`."""
        if key not in ("shift_vv", "shift_vh", "shift"):
            raise ValueError(f"Unknown shift {key!r}: use 'shift_vv', 'shift_vh' or 'shift'.")
        edits = self.shift_edits.setdefault(det, {})
        edits[key] = int(round(value)) if key == "shift" else float(value)
        edits.setdefault("source", "edited")
        self.outcome = None
        return self.calibrate_shift(det)

    def reset_shifts(self, det: str, keys=None) -> dict | None:
        """Back to the calibrated shifts of *det* (*keys*: only those; default all)."""
        edits = self.shift_edits.get(det) or {}
        for key in keys or ("shift_vv", "shift_vh", "shift"):
            edits.pop(key, None)
        if not any(k in edits for k in ("shift_vv", "shift_vh", "shift")):
            self.shift_edits.pop(det, None)
        self.outcome = None
        return self.calibrate_shift(det)

    def shift_base(self, det: str) -> dict:
        """*det*'s shifts before any calibration or edit (kept from the first time asked)."""
        settings = self.settings_of(det)
        return self._shift_base.setdefault(
            det, {"shift_sp": float(settings.shift_sp), "shift_ss": float(settings.shift_ss),
                  "shift": int(settings.shift)},
        )

    def shift_starts(self, det: str) -> dict:
        """The start of each of *det*'s shifts (:data:`SHIFT_PARAMETERS`): the value set by hand,
        else the calibrated one, else :meth:`shift_base` -- what the fit holds them at when fixed."""
        entry = self.shift_calibration.get(det)
        if entry:
            return {"shift_sp": float(entry["shift_vv"]), "shift_ss": float(entry["shift_vh"]),
                    "shift": int(entry.get("shift", self.shift_base(det)["shift"]))}
        return dict(self.shift_base(det))

    def _refine_shifts(self) -> dict:
        """Refine the current detector's unfixed shifts within :data:`SHIFT_BOUNDS` of their
        starts, for the lowest 2I* of the decay fit (the whole-bin VH shift by trying its
        neighbours, the sub-bin IRF shifts by golden section); the fixed ones are held at
        their starts. Returns the values the fit then uses."""
        det = self.current_detector
        settings = self.settings
        starts = self.shift_starts(det)
        free = [k for k, _label in SHIFT_PARAMETERS if not getattr(settings, f"fix_{k}")]
        for key, value in starts.items():
            setattr(settings, key, int(value) if key == "shift" else float(value))
        if not free or settings.model == TAIL_MODEL:
            return starts

        def score() -> float:
            out = self._fit_once()
            return float(out.two_istar) if out is not None and np.isfinite(out.two_istar) else np.inf

        if "shift" in free:
            best = (np.inf, int(starts["shift"]))
            bound = int(SHIFT_BOUNDS["shift"])
            for value in range(int(starts["shift"]) - bound, int(starts["shift"]) + bound + 1):
                settings.shift = value
                self.build_decay()
                got = score()
                if got < best[0]:
                    best = (got, value)
            settings.shift = best[1]
            self.build_decay()
        for key in ("shift_sp", "shift_ss"):
            if key not in free:
                continue
            lo, hi = starts[key] - SHIFT_BOUNDS[key], starts[key] + SHIFT_BOUNDS[key]

            def at(value: float, _key=key) -> float:
                setattr(settings, _key, float(value))
                return score()

            phi = (np.sqrt(5.0) - 1.0) / 2.0
            a, b = lo, hi
            c, d = b - phi * (b - a), a + phi * (b - a)
            fc, fd = at(c), at(d)
            while b - a > 0.02:
                if fc < fd:
                    b, d, fd = d, c, fc
                    c = b - phi * (b - a)
                    fc = at(c)
                else:
                    a, c, fc = c, d, fd
                    d = a + phi * (b - a)
                    fd = at(d)
            candidates = [(fc, c), (fd, d), (at(starts[key]), starts[key])]
            setattr(settings, key, float(min(candidates)[1]))
        return {k: getattr(settings, k) for k, _label in SHIFT_PARAMETERS}

    def recalibrate_shifts(self) -> None:
        """Calibrate every detector's shifts again (the setup's G, l1 or l2 changed)."""
        for det in list(self.detectors):
            if self.reference_records.get(det) or self.shift_edits.get(det):
                self.calibrate_shift(det)

    def take_tuned_irf(self, det: str, irf: np.ndarray, text: str, inputs: dict | None = None) -> bool:
        """The IRF the IRF tool computed for *det* (sent back from its window): used from now on
        (:attr:`irf_choice` ``tuned``) until another source is chosen. ``False`` when it does not
        fit this detector's decay (another binning)."""
        irf = np.asarray(irf, dtype=float)
        current = np.asarray(self.irf_np.get(det, []))
        if current.size and irf.size != current.size:
            return False
        source = inputs or self.irf_inputs.get(det)
        offset = int((source or {}).get("offset_bins") or 0)
        if offset:  # extracted in the window of the detection pair that saw the dye: to det's
            half = irf.size // 2
            irf = np.hstack([np.roll(irf[:half], offset), np.roll(irf[half:], offset)])
        self.irf_candidates.setdefault(det, {})["tuned"] = (irf, f"IRF tool (tuned): {text}", source)
        self.irf_choice[det] = "tuned"
        self.apply_irf_choice(det)
        return True

    def choose_irf(self, det: str, choice: str) -> str:
        """Take *det*'s IRF from *choice* (a key of :data:`IRF_CHOICES`); a tuned IRF is dropped."""
        if choice not in dict(IRF_CHOICES):
            raise ValueError(f"unknown IRF source {choice!r}")
        self.irf_candidates.get(det, {}).pop("tuned", None)
        if (self.shift_edits.get(det) or {}).get("source") == "IRF tool":
            self.shift_edits.pop(det, None)  # the tool's shifts went with its IRF
        self.irf_choice[det] = choice
        return self.apply_irf_choice(det)

    def ensure_background(self) -> list[str]:
        """The photons outside the bursts of every detector that has none yet, and the strict
        background selection of them (:meth:`select_background`), what the fit's background is
        made of (:meth:`background_of`) whatever the IRF came from. Returns the detectors given
        one."""
        from chisurf.core.fluorescence.burst import extract_mle_irf_background

        missing = [d for d in self.detectors if np.asarray(self.bg_np.get(d, [])).size == 0]
        tttr = self.current_tttr()
        if not missing or tttr is None or not self.burst_index_array().size:
            return []
        from chisurf.core.fluorescence.burst import fused_pipeline

        if fused_pipeline.enabled():  # histograms of the photons outside the bursts, natively
            patterns = fused_pipeline.session_outside_patterns(
                self, tttr, {d: self.detectors[d] for d in missing}, irf_model=self.settings.irf_model)
        else:
            in_burst = np.zeros(len(tttr), dtype=bool)
            in_burst[self.burst_index_array()] = True
            patterns = extract_mle_irf_background(
                tttr,
                {d: self.detectors[d] for d in missing},
                micro_time_binning=self.settings.micro_time_binning,
                mask=~in_burst,
                min_photons=max(2, int(self.settings.min_photons)),
                irf_model=self.settings.irf_model,
            )
        done = []
        for det, pat in patterns.items():
            if det in missing:
                self.bg_np[det] = np.asarray(pat["bg"], dtype=float)
                done.append(det)
        if done:
            self.select_background(done)
        return done

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

    def _blind_candidate(self, det: str) -> tuple:
        """``(irf, text, inputs)`` of the blind estimate of *det* (:meth:`blind_irf`), its inputs
        the burst decay the IRF tool estimates the same IRF from."""
        info = self.detectors[det]
        binning = max(1, int(self.settings.micro_time_binning))
        tttr = self.current_tttr()
        row = vv_vh_histogram(
            tttr[self.burst_index_array()], info.get("chs", []), (0, 0), binning,
            normalize_counts=0, apply_vh_shift=False,
        )
        half = row.size // 2
        dt = float(tttr.header.micro_time_resolution) * 1e9 * binning
        inputs = {
            "kind": "blind", "vv": row[:half], "vh": row[half:], "dt_ns": dt,
            "window": self._gate_window(det, half), "name": "the burst decay",
        }
        return self.blind_irf(det), "the burst decay (blind estimate, skewed Gaussian)", inputs

    def blind_irf(self, det: str) -> np.ndarray:
        """The IRF of *det* estimated from the burst decay alone, the last resort.

        The burst photons of the detector, VV and VH in its gate, go to the IRF Estimation tool's
        blind extraction (:func:`~chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction.irf_from_decay`:
        truncated exponential + Richardson-Lucy, trimmed by a skewed Gaussian). Each polarisation
        sums to one; zeros when the decay is empty.
        """
        from chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction import irf_from_decay

        info = self.detectors[det]
        binning = max(1, int(self.settings.micro_time_binning))
        photons = self.current_tttr()[self.burst_index_array()]
        row = vv_vh_histogram(
            photons, info.get("chs", []), (0, 0), binning, normalize_counts=0, apply_vh_shift=False
        )
        half = row.size // 2
        return irf_from_decay([row[:half], row[half:]], window=self._gate_window(det, half)).irf

    def _gate_window(self, det: str, n_bins: int | None = None) -> tuple[int, int] | None:
        """The ``[start, stop)`` bins of *det*'s gate at the current binning (``None``: no gate)."""
        binning = max(1, int(self.settings.micro_time_binning))
        gates = [r for r in (self.detectors[det].get("micro_time_ranges") or []) if r and len(r) >= 2]
        if not gates:
            return None
        lo, hi = int(gates[0][0]) // binning, int(np.ceil(int(gates[0][1]) / binning))
        return (lo, min(hi, n_bins) if n_bins else hi)

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
        # rates (counts per second) of several buffer files are averaged: their sum is no rate
        return np.mean(rows, axis=0) if normalize == 3 else np.sum(rows, axis=0)

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
        macro = np.asarray(tttr.macro_times, dtype=np.float64) * float(header.macro_time_resolution)
        seconds = float(macro[-1] - macro[0]) if macro.size else 0.0
        dt_ns = float(header.micro_time_resolution) * 1e9 * binning
        self._single_molecule[str(path)] = single_molecule(macro)
        # the detector's count rate in this measurement: SPAD timing moves with it
        self._count_rate_khz[(str(path), det)] = float(row.sum()) / max(seconds, 1e-9) / 1e3
        return row[:half], row[half:], seconds, dt_ns

    def irf_pattern(self, det: str, paths: list[Path]) -> tuple[np.ndarray, str] | None:
        """The IRF of *det* from reference measurements, and where it came from; ``None`` when none
        of them shows the detector's response.

        The measurements are histogrammed here (the burst files' reader settings, the
        detector's channels, the current binning) and handed to the IRF Estimation tool, which
        extracts the IRF (:mod:`~chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction`):
        a scatter (water, Ludox) is the IRF itself after its background (a measured buffer of
        this detector, scaled to the scatter's time, then the flat floor); the decay of a
        reference dye (``reference_dyes.yaml``: Rh110, Alexa647, ...) gives it by deconvolving
        the dye's polarised exponential, its lifetime fitted to the dye's tail and its rotation
        to its two polarisations. In the tool's order (``best_irf``, ``AUTO_ORDER``): a reference
        dye first, measured in the same conditions as the sample, then a scatter; of several dyes
        the one with the most photons in the detector's gate (Rh110 for the green detectors, Alexa647 for the red ones of a PIE
        set-up). Each polarisation sums to one.
        """
        from chisurf.core.fio.reference_files import reference_dye
        from chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction import (
            best_irf,
            irf_from_reference,
            irf_from_scatter,
            reference_lifetime,
        )

        scatter = [p for p in paths if reference_dye(p) is None]
        groups: dict[str, list[Path]] = {}
        for p in paths:
            dye = reference_dye(p)
            if dye is not None:
                groups.setdefault(dye["name"], []).append(p)
        buffer = None
        if self.bg_files.get(det) and det in self.buffer_np:
            buffer = np.asarray(self.buffer_np[det], dtype=float)  # counts per second, VV | VH

        found = []
        sources: dict[str, dict] = {}
        if scatter:
            vv = vh = 0.0
            seconds = 0.0
            for p in scatter:
                a, b, t, dt = self._reference_counts(det, p)
                vv, vh, seconds = vv + a, vh + b, seconds + t
            half = np.size(vv)
            window = self._gate_window(det, half)
            scaled = None
            if buffer is not None and buffer.size == 2 * half:
                scaled = [buffer[:half] * seconds, buffer[half:] * seconds]
            names = ", ".join(p.name for p in scatter)
            found.append(irf_from_scatter([vv, vh], buffer=scaled, window=window, name=names))
            sources[found[-1].text] = {
                "kind": "scatter", "vv": vv, "vh": vh, "dt_ns": dt, "window": window, "name": names,
                "buffer": scaled,
            }
        records = []
        for name, group in groups.items():
            counts = [self._reference_counts(det, p) for p in group]
            vv = np.sum([c[0] for c in counts], axis=0)
            vh = np.sum([c[1] for c in counts], axis=0)
            dt = counts[-1][3]
            # The detectors of one detection pair (R|G, R|R) share the IRF's shape and timing: the
            # dye is read in the window that sees it (Alexa 647: R|R's), and the IRF placed at
            # det's window by the setup's PIE offset -- never fitted in a window it barely reaches.
            source = self._reference_source(det, vv, vh)
            offset = self.window_offset(det, source) if source != det else 0
            window = self._gate_window(source, np.size(vv))
            lo, hi = window or (0, np.size(vv))
            if float(np.sum(vv[lo:hi]) + np.sum(vh[lo:hi])) <= 0:
                continue  # a dye these detectors do not see (Alexa 647 on the green ones)
            names = ", ".join(p.name for p in group)
            listed = reference_dye(group[0])["tau_ns"]
            one = len(self.detectors[det].get("chs", [])) < 2  # one channel: no rotation to see
            # one lifetime for the IRF's deconvolution and the shift calibration: the database's
            # unless the dye's tail clearly says otherwise (then the tail's, and that is said)
            tau, tau_info = reference_lifetime(vv, None if one else vh, dt, listed, window=window)
            for p, (a, b, _t, _dt) in zip(group, counts):
                dye_entry = reference_dye(p)
                records.append({
                    "path": str(p), "dye": name, "vv": a, "vh": b, "dt_ns": dt, "window": window,
                    "single_molecule": self._single_molecule.get(str(p), False),
                    "rate_khz": self._count_rate_khz.get((str(p), det)),
                    "tau_ns": tau, "tau_info": tau_info,
                    "tau_source": dye_entry.get("tau_source") or {},
                    "detector": source, "offset_bins": offset,
                })
            # the detector pair's G, once computed (Data Selection's tail ratio; 1 is "not yet"):
            # with it the dye's initial anisotropy is taken from the data when the ideal one fails
            g_pair = float(self.detectors[source].get("g_factor", 1.0) or 1.0)
            got = irf_from_reference(
                vv, None if one else vh, dt, tau_ns=tau, listed_tau_ns=listed, window=window,
                name=names, dye=name, g_factor=None if g_pair == 1.0 else g_pair,
                tau_how=tau_info.get("how") or "given",
            )
            for record in records[-len(group):]:  # the rotation the IRF was deconvolved with
                record["rho_ns"], record["r0"] = got.info.get("rho_ns"), got.info.get("r0")
            if offset:
                got = dataclasses.replace(
                    got,
                    irf=np.hstack([np.roll(h, offset) for h in got.halves]),
                    text=f"{got.text}; calibrated on {source}, placed at the {det} window ({offset:+d} bins)",
                    info=dict(got.info, calibrated_on=source, offset_bins=offset),
                )
            found.append(got)
            sources[found[-1].text] = {
                "kind": "reference", "vv": vv, "vh": vh, "dt_ns": dt, "window": window,
                "name": names, "dye": name, "listed_tau_ns": listed,
                "calibrated_on": source, "offset_bins": offset,
                # the dye as the IRF was deconvolved with it: the IRF tool extracts the same
                "tau_ns": tau, "tau_how": tau_info.get("how"), "r0": got.info.get("r0"),
            }
        self.reference_records[det] = records
        candidates = self.irf_candidates.setdefault(det, {})
        for kind, choice in (("scatter", "measurement"), ("reference", "reference")):
            mine = best_irf([r for r in found if r.source == kind], MIN_IRF_COUNTS)
            if mine is not None:
                candidates[choice] = (mine.irf, mine.text, sources[mine.text])
            else:
                candidates.pop(choice, None)
        best = best_irf(found, MIN_IRF_COUNTS)
        if best is None:
            return None
        #: what the IRF was extracted from, per detector: the IRF Estimation tool shows and
        #: tunes the same extraction from it (``Open in IRF Estimation``)
        self.irf_inputs[det] = sources[best.text]
        return best.irf, best.text

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
                self.apply_irf_choice(d)  # the measured IRF, unless another source was chosen
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
                    self.irf_inputs.pop(d, None)
                    self.reference_records.pop(d, None)  # no dye left to calibrate on
                    for key in ("measurement", "reference"):
                        self.irf_candidates.get(d, {}).pop(key, None)
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
                    self.apply_irf_choice(det)

    def _pattern_store(self, kind: str):
        if kind == "irf":
            return self.irf_files, self.irf_np, 2, self.irf_one_for_all
        if kind == "bg":
            return self.bg_files, self.buffer_np, 3, self.bg_one_for_all
        raise ValueError(f"Unknown pattern kind {kind!r}: use 'irf' or 'bg'.")

    def auto_extract(self) -> None:
        """One click: IRF / background, fit window, fit (the binning is the setup's)."""
        tttr = self.current_tttr()
        if tttr is None:
            self.status = "Load bursts first: no data to extract an IRF from"
            return
        if not self.burst_index_array().size:
            self.status = "No burst photons found for the selected file"
            return
        self.extract_irf_background()
        # the window is picked on the decay in the detector's gate, not in the window it replaces
        self.settings.micro_time_start, self.settings.micro_time_stop = -1, -1
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
            fit_window=fit_window(self.window_ranges(), irf.size // 2),
        )
        return Fit2x(settings, model=Fit2xModel(self.settings.model))

    def _irf_missing(self) -> str | None:
        """Why the current detector cannot be fitted for want of an IRF (``None``: it has one,
        or its model needs none)."""
        det = self.current_detector
        if not det:
            return "no detector selected"
        if self.settings.model != TAIL_MODEL and (
            det not in self.irf_np or np.asarray(self.irf_np.get(det, [])).size == 0
        ):
            return f"no IRF for detector {det!r} (load or send an IRF)"
        return None

    def blocked_reason(self) -> str | None:
        det = self.current_detector
        missing = self._irf_missing()
        if missing is not None:
            return missing
        if det not in self.bg_np or np.asarray(self.bg_np.get(det, [])).size == 0:
            return f"no background for detector {det!r}"
        if self.decay is None or np.asarray(self.decay).size == 0:
            return "no decay (load bursts / select a file)"
        return None

    def fit(self) -> FitOutcome | None:
        """Fit the current decay (``update_fit`` without the plots); ``None`` with the reason in
        :attr:`status`. The detector's time shifts are held at their starts, or refined first
        where unfixed (:meth:`_refine_shifts`)."""
        if self.decay is not None and self.current_detector in self.detectors:
            before = int(self.settings.shift)
            self._refine_shifts()
            if int(self.settings.shift) != before:
                self.build_decay()
        return self._fit_once()

    def _fit_once(self) -> FitOutcome | None:
        """One fit of the current decay at the current settings (:meth:`fit`)."""
        if self._irf_missing() is None:
            # the background's strict selection is judged by the IRFs: made before they are
            # there it is made again once they are (the hand-over set the setup, and fitted,
            # before the references gave the IRFs: two selections of ~10 s, the first unused)
            self.ensure_background()
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
        # 2I* of the P+2S objective is relative to the data's own (its W0): a fit at the noise
        # lands a hair below zero (-0.002 on the BH sample with the window honoured), not diverged
        diverged = float(res.twoIstar) < -0.05 or not np.isfinite(float(res.twoIstar))
        curves = decay_curves(
            d,
            model,
            self.irf(),
            self.fitted_background(d, res, list(fit.parameter_names)),
            self.window_ranges(),
            tail=self.settings.model == "tail",
            diverged=diverged,
            irf_range=(self.settings.irf_start, self.settings.irf_stop),
            data_all=self.decay_all(self.decay),
            background_counts=True,
            n_free=int(np.count_nonzero(~np.asarray(fixed, dtype=bool))),
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

    def fitted_background(self, d: np.ndarray, res: Any, names: list[str]) -> np.ndarray:
        """The background the fit put into its model, in counts of the decay *d*: the pattern
        (shaped as :meth:`background`), its share of the window's photons the fitted ``gamma``
        -- what Fit2x adds -- so the line drawn is the model's own background, not the expected
        one beside it (that was drawn at the floor while the model's ran under it). Without a
        ``gamma`` the expected background (:meth:`background_in_bursts`)."""
        expected = self.background_in_bursts()
        if "gamma" not in names:
            return expected
        gamma = float(np.asarray(res.x, dtype=float)[names.index("gamma")])
        pattern = np.asarray(expected, dtype=float)
        n = pattern.size // 2
        window = fit_window(self.window_ranges(), n)
        lo, hi = window if window is not None else (0, n)
        inside = np.zeros_like(pattern)
        inside[lo:hi] = pattern[lo:hi]
        inside[n + lo : n + hi] = pattern[n + lo : n + hi]
        total = float(inside.sum())
        if not np.isfinite(gamma) or total <= 0.0:
            return expected
        counts = float(np.sum(d[lo:hi]) + np.sum(d[n + lo : n + hi]))
        return pattern / total * gamma * counts

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
            self.background_in_bursts(),
            self.window_ranges(),
            tail=True,
            diverged=False,
            data_all=self.decay_all(self.decay),
            background_counts=True,
            n_free=int(np.count_nonzero(~np.asarray(fixed, dtype=bool))),
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
        raw_bg = self.background_of(det)
        raw_bg = np.asarray(raw_bg if raw_bg is not None else np.array([]), dtype=float)
        bg = process_background(raw_bg, st.shift, irf) if raw_bg.size else raw_bg
        names, x0, fixed = st.parameter_state()
        # The setup's detector gates (step 0's PIE windows) bound the fit as they bound the preview decay.
        vv_sb, vv_eb, vh_sb, vh_eb = window_bins(
            info.get("micro_time_ranges"), (sb, eb), st.micro_time_binning, len(info.get("chs", []))
        )
        return {
            "fit_window": fit_window((vv_sb, vv_eb, vh_sb, vh_eb), irf.size // 2),
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
        """Fit every burst of every loaded file and detector, in this process.

        One ``Fit2x.fit_many`` call per chunk of bursts (:func:`._mp_worker.fit_jobs`) on
        *max_workers* threads (``fit_workers()`` by default): the call releases the GIL and fits
        in C++, so threads give the throughput worker processes gave, without their memory, the
        photons' shared-memory copies or pickling. Each burst gives one row per detector
        (``Tau (G|G)``, ``gamma (G|G)``, ...). Nothing is exported here: the rows are kept on
        :attr:`burst_results`. *should_stop* is read as each chunk finishes; *progress(done,
        total)* counts bursts.
        """
        from ._mp_worker import BurstJob, fit_jobs

        if self.df_bursts is None or not len(self.tttrs):
            raise ValueError("No burst data loaded.")
        det_order = list(self.detectors)
        binning = int(self.settings.micro_time_binning)
        self.ensure_background()
        # unfixed time shifts are refined on each detector's summed decay before its bursts are
        # fitted with them (the current detector's were, by its last fit)
        current = self.current_detector
        for det in det_order:
            st = self.settings_of(det)
            if det != current and not all(getattr(st, f"fix_{k}") for k, _l in SHIFT_PARAMETERS):
                self.current_detector = det
                self.build_decay()
                self.fit()
        if self.current_detector != current:
            self.current_detector = current
            self.build_decay()
            self.fit()
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
        from chisurf.core.fluorescence.burst import fused_pipeline

        if fused_pipeline.enabled():
            # decays and fits of every burst natively, from the photons in place
            # (okf/architecture/fused-burst-pipeline.md); None: a split by state, the path below
            results = fused_pipeline.fit_session(
                self, configs, det_order, binning, threads=max_workers or fit_workers(),
                should_stop=should_stop, progress=progress,
            )
            if results is not None:
                self.state_lifetimes = []
                self.n_states = 0
                self.burst_results = results
                self.batch_settings_snapshot = copy.deepcopy(self.channel_settings())
                self.batch_files_snapshot = self.measurement_files()
                return results
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
            state_arrays, n_states, self.status = self.state_arrays_by_measurement()
        self.n_states = int(n_states)
        shift = int(self.settings.shift or 0)
        jobs: list[BurstJob] = []
        for fname, bursts in groups.items():
            tttr = self.tttrs.get(
                fname if identity_column == "_measurement_path" else Path(fname).stem
            )
            if tttr is None:  # every burst gets the no-data row
                jobs.append(BurstJob(fname, bursts, None, None, det_order, configs, shift))
                continue
            rc_full = np.asarray(tttr.routing_channels)
            mt_full = np.asarray(tttr.micro_times)
            mt_bins = mt_full // binning if binning > 1 else mt_full
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
            states_full = state_arrays.get(fname) if n_states > 0 else None
            jobs.append(BurstJob(fname, bursts, rc_full, mt_bins, det_order, perdet, shift,
                                 states_full, int(n_states) if states_full is not None else 0))
        # The pooled per-state fit comes first: its lifetimes are the numbers to quote and the
        # start values of every per-burst fit of that state.
        self.state_lifetimes = []
        if n_states > 0 and jobs:
            from . import state_split

            model = self.settings_of(det_order[0]).model if det_order else self.template.model
            self.state_lifetimes, _seeded, self.status = state_split.pooled_state_fits(
                jobs, det_order, model, ["tau", "gamma", "r0", "rho"], shift,
                should_stop=should_stop,
            )
        errors: list[str] = []
        results = fit_jobs(jobs, max_workers or fit_workers(), should_stop=should_stop,
                           progress=progress, errors=errors)
        if errors:  # a chunk failed: named, its bursts kept as rejected rows
            self.status = "; ".join(errors[:3])
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
        if self.ahead_key:
            raise ValueError("The bursts were searched ahead: there is no run to write into yet.")
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
        # once per measurement, not per burst: parsing a path per row took 2.6 s of a 5.5 k-burst
        # export, on the thread every other sample of a batch waits for
        boxed = {stem: _is_container(path) for stem, path in files_by_stem.items()}
        in_container = [r for r in rows if boxed[r["First Stem"]]]
        legacy = [r for r in rows if not boxed[r["First Stem"]]]
        paths: list[Path] = []
        if legacy:
            written = write_b4_tables(legacy, files_by_stem, det_meta, settings, tick=tick)
            paths = [] if written is None else list(written[0])
        if in_container:
            # `First Stem` of a container row is the container itself: one container is one
            # measurement -- addressed as the run its bursts were read from (``m.pto/<run>``), so
            # the fits become members of that run, not of whichever search is newest.
            from chisurf.core.fio.analysis_path import split_container_path

            run_of = {}
            for path in self.bur_files:
                box, run = split_container_path(path)
                if box is not None and run:
                    run_of.setdefault(str(Path(box).resolve()), str(path))

            @functools.lru_cache(maxsize=None)
            def address(first: str) -> str:
                box = split_container_path(first)[0]
                key = str(Path(box if box is not None else first).resolve())
                return run_of.get(key, first)

            containers = write_container_tables(
                [dict(r, **{"First Stem": address(str(r["First File"]))}) for r in in_container],
                det_meta,
                settings,
                state_rows=self.state_lifetimes or None,
                experiment=self.experiment_payload(),
                background=self.background_rates(),
                tick=tick,
            )
            paths += containers or []
        if self.state_lifetimes:
            from . import state_split

            roots = {p.parent.parent for p in self.bur_files if not _is_container(p)}
            if roots:
                paths += state_split.write_state_lifetimes(self.state_lifetimes, roots)
        return paths

    def background_rates(self) -> dict[str, dict]:
        """``{detector: {"rate_khz", "source", "seconds"}}``: the background rate each detector's
        fit is corrected with (:meth:`background_of`: the buffer, else the strict selection, else
        the flat + scatter model of the photons outside the bursts), as the run records it."""
        names = {"buffer": "buffer", "strict": "strict selection", "model": "model"}
        out = {}
        for det in self.detectors:
            try:
                self.background_of(det)
            except Exception:  # noqa: BLE001 - a detector without a background has no rate
                continue
            info = self.background_info.get(det) or {}
            if info.get("rate_khz") is None:
                continue
            seconds = (self.strict_background or {}).get("seconds") if info.get("source") == "strict" else None
            out[det] = {"rate_khz": float(info["rate_khz"]), "source": names.get(info.get("source"), ""),
                        "seconds": seconds}
        return out

    def experiment_payload(self) -> dict:
        """The IRF and background each detector's fit used, in the layout the container writer takes."""
        detectors = {}
        for det in self.detectors:
            detectors[det] = {
                key: np.asarray(source.get(det, []), dtype=float).ravel().tolist()
                for key, source in (
                    ("irf", self.irf_np),
                    ("background", {d: self.background_of(d) for d in self.detectors
                                    if self.background_of(d) is not None}),
                )
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
            # shifts set by hand: they stay over the calibration until reset
            "shift_edits": {d: dict(v) for d, v in self.shift_edits.items() if v},
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
        self.shift_edits = {
            str(d): dict(v) for d, v in (payload.get("shift_edits") or {}).items() if isinstance(v, dict)
        }
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
                burst,
                info.get("chs", []),
                window_bins(
                    info.get("micro_time_ranges"),
                    (self.settings_of(det).micro_time_start, self.settings_of(det).micro_time_stop),
                    self.settings_of(det).micro_time_binning,
                )[:2],
                self.settings_of(det).micro_time_binning,
            )
            for det, info in self.detectors.items()
        }
