"""The Qt-free engine of the burst-MLE lifetime analysis (cards ML0 and ML1).

What the (retired) Qt wizard did with its widgets is here as functions of explicit inputs and a session object that
holds the state those widgets held (detectors, burst files, the micro-time window, the IRF / background patterns, the
fit settings). ``tests/test_mle_engine.py`` compares the session with the numbers the wizard gave on the
in-repository BH sample (``tests/qt_reference.json``).

No Qt and no emtk are imported here.
"""

from __future__ import annotations

import collections.abc
import copy
import dataclasses
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
from chisurf.core.support.i18n import tr

from .fit_display import DecayCurves, TailFitResult, decay_curves
from .interpolate import interpolate_shift


# --------------------------------------------------------------------------------------------------------------------
# pure steps (the wizard calls these)
# --------------------------------------------------------------------------------------------------------------------
def _is_container(path: Any) -> bool:
    """Whether *path* names a ``.pto`` (or a run in one) rather than a ``.bur`` file."""
    from chisurf.core.fio.analysis_path import is_container_path

    return is_container_path(path)


def _burst_file_stem(path: Any) -> str:
    """The measurement stem a burst input stands for: the container's for a run in a ``.pto``, the file's otherwise."""
    if _is_container(path):
        from chisurf.core.fio.analysis_path import split_container_path

        return split_container_path(path)[0].stem
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
        The bursts, tagged with ``burst_file`` and the resolved identities ``_burst_path`` (the run) and
        ``_measurement_path`` (the container).
    container : Path
        The resolved container, which is also the measurement's photon source.
    """
    from chisurf.core.fio.analysis_path import split_container_path
    from chisurf.core.fio.fluorescence.burst import _read_burst_analysis_from_container

    container, _run = split_container_path(path)
    table, _tttrs = _read_burst_analysis_from_container(Path(path))
    container = container.resolve()
    n = row_count(table)
    set_constant(table, "burst_file", Path(path).name)
    set_constant(table, "_burst_path", str(Path(path).resolve()))
    table["_measurement_path"] = [str(container)] * n
    return table, container


def burst_photon_indices(df_bursts: Any, current_filename: str) -> list[int]:
    """Photon indices of every burst of the file *current_filename* (a ``.bur`` file), merged and ascending."""
    if not current_filename or df_bursts is None:
        return []
    if "stem" not in column_names(df_bursts):
        first_file_vals = np.asarray(df_bursts["First File"], dtype=object)
        df_bursts["stem"] = [
            re.split(r"[\\/]", str(v))[-1].rsplit(".", 1)[0] for v in first_file_vals
        ]
    curr_stem = _burst_file_stem(current_filename)
    mask = np.asarray(df_bursts["stem"], dtype=object) == curr_stem
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
    return np.nonzero(coverage)[0].tolist()


def header_time_ns(tttr: Any, binning: int) -> tuple[float, float] | None:
    """``(dt_ns, period_ns)`` from a TTTR header: the channel width at *binning* and one excitation period."""
    if tttr is None:
        return None
    try:
        h = tttr.header
        micro_s = float(h.micro_time_resolution)
        n_chan = float(h.number_of_micro_time_channels)
    except Exception:
        return None
    if not (micro_s > 0.0 and n_chan > 0.0):
        return None
    return micro_s * 1e9 * max(1, int(binning)), n_chan * micro_s * 1e9


def effective_timing_ns(tttr: Any, binning: int, reading: dict) -> tuple[float | None, float | None]:
    """Use per-file physical timing unless an explicit ps/ns calibration overrides it."""
    physical = header_time_ns(tttr, binning)
    dt, period = physical if physical is not None else (None, None)
    if reading.get("override_timing") or physical is None:
        micro = float(reading.get("micro_time_resolution", 0.) or 0.)
        macro = float(reading.get("macro_time_resolution", 0.) or 0.)
        if micro > 0.:
            dt = micro * 1e-3 * max(1, int(binning))
        if macro > 0.:
            period = macro
    return dt, period


def window_bins(
    detector_ranges: Any, micro_time_range: tuple[int, int], binning: int
) -> tuple[int, int, int, int]:
    """Per-polarisation ``(vv_start, vv_stop, vh_start, vh_stop)`` in binned channels.

    The detector's own raw micro-time ranges (two of them: VV, VH) win; otherwise the global window applies to both.
    """
    sb, eb = micro_time_range
    out = (sb, eb, sb, eb)
    if detector_ranges and len(detector_ranges) >= 2:
        b = max(1, int(binning))
        raw_vv, raw_vh = detector_ranges[0], detector_ranges[1]
        out = (int(raw_vv[0] // b), int(raw_vv[1] // b), int(raw_vh[0] // b), int(raw_vh[1] // b))
    return out


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
) -> np.ndarray:
    """The VV | VH micro-time histogram of *tttr* (one row of the wizard's ``make_vv_vh``)."""
    vv_sb, vv_eb, vh_sb, vh_eb = window_bins(detector_ranges, micro_time_range, binning)

    def photons(chs):
        return tttr[np.where(np.isin(tttr.routing_channels, chs))[0]]

    if len(detector_chs) >= 2:
        tp, ts = photons(detector_chs[::2]), photons(detector_chs[1::2])
    else:
        tp = ts = photons(detector_chs)
    cp = tp.get_microtime_histogram(binning)[0].astype(np.float64, copy=False)
    cs_hist = ts.get_microtime_histogram(binning)[0].astype(np.float64, copy=False)
    if apply_vh_shift and shift != 0:
        cs_hist = np.roll(cs_hist, shift)
    if apply_vh_shift:
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
    """The IRF as the fit sees it: VH rolled, sub-bin shifted, windowed and thresholded (the wizard's ``irf``)."""
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
        n_full = int(tttr.header.number_of_micro_time_channels)
    except Exception:
        return None
    if n_full <= 0:
        return None
    non_burst = np.ones(len(tttr), dtype=bool)
    non_burst[np.asarray(burst_idx, dtype=int)] = False
    sel = non_burst & np.isin(np.asarray(tttr.routing_channels), np.asarray(chs, dtype=int))
    micro = np.asarray(tttr.micro_times)[sel]
    micro = micro[(micro >= 0) & (micro < n_full)]
    if micro.size == 0:
        return None
    hist = np.bincount(micro, minlength=n_full)[:n_full].astype(float)
    pk = hist.max()
    if pk <= 0:
        return None
    above = np.where(hist >= 0.5 * pk)[0]
    if above.size == 0:
        return None
    return int(above[-1] - above[0] + 1)


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
        np.isin(np.asarray(tttr.routing_channels)[burst_idx], np.asarray(chs, dtype=int)).sum()
    )
    try:
        n_full = int(tttr.header.number_of_micro_time_channels)
    except Exception:
        return None
    if counts <= 0 or n_full <= 0:
        return None
    need_stat = target_counts_per_bin * 2.0 * n_full / counts
    fwhm = irf_fwhm_channels(tttr, chs, burst_idx)
    need_irf = (fwhm / irf_oversample) if (fwhm and irf_oversample > 0) else 0.0
    need = max(need_stat, need_irf)
    ordered = sorted(int(c) for c in choices)
    for c in ordered:
        if c >= need:
            return c
    return ordered[-1]


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


def write_container_tables(results, det_meta, parameters, *, state_rows=None, experiment=None, tick=None):
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
            arr = np.array([[coerce_float(row.get(c)) for c in cols] for row in rows_g], dtype=float)
            tables.setdefault(container, {})[det] = store_from_arrays(
                {c: arr[:, i] for i, c in enumerate(cols)}
            )
        done += 1
        if tick is not None and tick(done):
            return None
    return [
        Path(
            write_mle_container(
                container, by_det, state_rows=state_rows, experiment=experiment, parameters=parameters
            )
        )
        for container, by_det in tables.items()
    ]


class NumpyEncoder(__import__("json").JSONEncoder):
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
    cp = (
        burst[np.where(np.isin(burst.routing_channels, pchs))[0]]
        .get_microtime_histogram(binning)[0]
        .astype(np.float64, copy=False)
    )
    cs_hist = (
        burst[np.where(np.isin(burst.routing_channels, schs))[0]]
        .get_microtime_histogram(binning)[0]
        .astype(np.float64, copy=False)
    )
    if sb > 0:
        cp[:sb] = 0
        cs_hist[:sb] = 0
    if eb < cp.size:
        cp[eb:] = 0
        cs_hist[eb:] = 0
    return np.hstack([cp, cs_hist])


#: The IRF models of the Auto IRF/background estimate: (value, label).
IRF_MODELS = [
    ("gaussian", "Gaussian"),
    ("skewed", "Skewed"),
    ("experimental", "Experimental"),
]

#: The binnings the detector page offers (the Qt combo's items).
BINNING_CHOICES = [1, 2, 4, 8, 16, 32, 64, 128, 256]


def read_burst_analysis(
    paris_path: Path, pattern: str = "**/*.bur"
) -> tuple[Any, dict[str, Path], dict | None]:
    """Read every ``.bur`` under *paris_path* into one burst table (the wizard's ``read_burst_analysis``).

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
                reason = str(tr("requires {count} reference patterns")).format(count=spec["n_patterns"])
            else:
                properties = spec.get("params_schema", {}).get("properties", {})
                inputs = [str(tr(item.get("title", key))) for key, item in properties.items()
                          if item.get("type") == "array"]
                reason = str(tr("requires {inputs}")).format(inputs=" / ".join(inputs))
            lines.append(str(tr("{name}: unavailable here ({reason}).")).format(name=name, reason=reason))
    return "\n".join(lines)


def fit_result_names(model: str) -> tuple[str, ...]:
    """Return declared derived outputs that add information beyond the parameter vector."""
    from chisurf.core.fluorescence.mle.registry import fit_models

    if model == TAIL_MODEL:
        return ()
    properties = fit_models()[model].get("results_schema", {}).get("properties", {})
    return tuple(name for name in properties if name == "selected_index")


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
                raise KeyError(f"Measurement {key!r} is missing or ambiguous; use its complete path.")
            key = matches[0]
        if key not in self._cache:
            path = self.paths[key]
            file_type = self.file_type
            if not file_type or str(file_type).lower() == "auto":
                file_type = None
            self._cache[key] = open_tttr(path, file_type, cache=False, **self.read_kwargs)
        return self._cache[key]

    def __setitem__(self, key, value) -> None:
        self._cache[key] = value

    def __delitem__(self, key) -> None:
        self._cache.pop(key, None)
        self.paths.pop(key, None)

    def __iter__(self):
        return iter(self.paths)

    def __len__(self) -> int:
        return len(self.paths)


@dataclass
class MleSettings:
    """Everything the fit and the displayed IRF depend on (the wizard's spin boxes and check boxes)."""

    model: str = "fit23"
    model_values: dict[str, dict[str, float]] = field(default_factory=dict)
    model_fixed: dict[str, dict[str, bool]] = field(default_factory=dict)
    tau: float = 4.0
    gamma: float = 0.1
    r0: float = 0.38
    rho: float = 1.22
    fix_tau: bool = False
    fix_gamma: bool = True
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
    min_photons: int = 10
    p2s_twoIstar: bool = True
    BIFL_scatter: bool = False
    irf_model: str = "gaussian"

    def parameter_state(self) -> tuple[list[str], np.ndarray, np.ndarray]:
        """Return free facade names, starts and fixed flags for this selected model."""
        from chisurf.core.fluorescence.mle.fit2x import parameter_names_of

        name = validate_fit_model(self.model)
        names = list(TAIL_SCHEMA["properties"]) if name == TAIL_MODEL else list(parameter_names_of(name))
        if name == "fit23":
            values = [getattr(self, key) for key in names]
            fixed = [getattr(self, f"fix_{key}") for key in names]
        else:
            properties = fit_model_specs()[name]["params_schema"]["properties"]
            saved_values = self.model_values.setdefault(name, {})
            saved_fixed = self.model_fixed.setdefault(name, {})
            values = [saved_values.get(key, properties[key].get("default", 0.)) for key in names]
            fixed = [saved_fixed.get(key, properties[key].get("fixed_default", False)) for key in names]
            if name == "fit25":
                fixed = [True if key.startswith("tau") else value for key, value in zip(names, fixed)]
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
            if not np.isfinite(value) or value < spec.get("minimum", -np.inf) or value > spec.get("maximum", np.inf):
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
    """Detectors, burst files, patterns and settings of a burst-MLE analysis; the wizard's state without Qt."""

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
    #: Fit every burst once more per H2MM state (``Tau S0 (green)`` ...), after a pooled fit of each state's decay.
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

    def set_model(self, name: str) -> None:
        """Select one validated model for all detectors, retaining each model's edits."""
        validate_fit_model(name)
        if self.template.model == name and all(st.model == name for st in self.det_settings.values()):
            return
        self.template.model = name
        for settings in self.det_settings.values():
            settings.model = name
        self.outcome = None

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
        self.set_detectors(settings.get("detectors", self.detectors), reading.get("file_type"))
        self.tttrs.set_setup(self.definition)

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

    def add_burst_files(self, paths: list[str | Path]) -> None:
        """Add ``.bur`` tables. As in the wizard, the analysis folder of the first file is read whole: every ``.bur``
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
            raw_paths[str(container)] = container
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

    def current_tttr(self):
        """The TTTR behind the selected burst file (``None`` when nothing is loaded)."""
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
        table = self.df_bursts
        if table is not None and "_burst_path" in column_names(table) and self.current_filename:
            selected = str(Path(self.current_filename).resolve())
            table = take_where(table, np.asarray(table["_burst_path"], dtype=object) == selected)
        return burst_photon_indices(table, self.current_filename)

    def measurement_files(self) -> dict[str, Path]:
        """Associate each loaded physical measurement with its exact selected burst table."""
        if self.df_bursts is None or "_measurement_path" not in column_names(self.df_bursts):
            return {p.stem: p for p in self.bur_files}
        selected = {str(path.resolve()) for path in self.bur_files}
        return {str(raw): Path(burst) for raw, burst in zip(
            self.df_bursts["_measurement_path"], self.df_bursts["_burst_path"]
        ) if str(burst) in selected}

    def state_arrays_by_measurement(self) -> tuple[dict, int, str]:
        """Resolve H2MM states within each analysis, then retain complete raw-file identities."""
        from . import state_split

        arrays, count, messages = {}, 0, []
        roots = dict.fromkeys(
            path.parent.parent.resolve() for path in self.bur_files if not _is_container(path)
        )
        for root in roots:
            selected = np.array([Path(str(path)).parent.parent == root
                                 for path in self.df_bursts["_burst_path"]])
            identities = dict.fromkeys(str(value) for value in np.asarray(
                self.df_bursts["_measurement_path"], dtype=object)[selected])
            scoped = {Path(identity).stem: self.tttrs[identity] for identity in identities}
            states, n_states, message = state_split.load_state_arrays(root, scoped)
            for identity in identities:
                if Path(identity).stem in states:
                    arrays[identity] = states[Path(identity).stem]
            count = max(count, n_states)
            messages.append(message)
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
        )

    # -- decay ------------------------------------------------------------------------------------------------- #
    def build_decay(self) -> np.ndarray | None:
        """The decay of every burst photon of the current file and detector (``decay_of_current_file``)."""
        tttr = self.current_tttr()
        chs = self.detector.get("chs", [])
        idx = np.asarray(self.burst_indices(), dtype=int)
        if tttr is None or not chs or idx.size == 0:
            return None
        rows = vv_vh_histogram(
            tttr[idx],
            chs,
            self.micro_time_range,
            self.settings.micro_time_binning,
            detector_ranges=self.detector.get("micro_time_ranges"),
            shift=self.settings.shift,
            normalize_counts=-1,
        )
        self.decay = np.asarray(rows)
        return self.decay

    # -- IRF / background -------------------------------------------------------------------------------------- #
    def auto_binning(self) -> int | None:
        tttr = self.current_tttr()
        return select_binning(
            tttr,
            self.detector.get("chs", []),
            np.asarray(self.burst_indices(), dtype=int),
            BINNING_CHOICES,
        )

    def extract_irf_background(self) -> int:
        """IRF and background from the photons outside the bursts, at the current binning; returns the detectors done."""
        from chisurf.core.fluorescence.burst import extract_mle_irf_background

        tttr = self.current_tttr()
        idx = np.asarray(self.burst_indices(), dtype=int)
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
        for det, pat in patterns.items():
            if det:
                if not self.irf_files.get(det):
                    self.irf_np[det] = np.asarray(pat["irf"], dtype=float)
                if not self.bg_files.get(det):
                    self.bg_np[det] = np.asarray(pat["bg"], dtype=float)
                n += 1
        return n

    # -- measured IRF / background files --------------------------------------------------------------------- #
    def _open_pattern_tttr(self, path: Path) -> Any:
        """Open one IRF / background measurement with the reader settings of the burst files."""
        from chisurf.core.fio.staging import open_tttr

        file_type = self.file_type
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

    def set_pattern_files(self, kind: str, det: str, paths: list[Path]) -> list[str]:
        """Use the measurements *paths* as the IRF (``kind="irf"``) or background (``"bg"``); returns the detectors set.

        With "one for all" the same files serve every detector. Each detector's pattern is the sum of the files'
        histograms on its own channels, so a file measured on all detectors at once gives every detector its pattern.
        """
        files, np_dict, normalize, one = self._pattern_store(kind)
        paths = [Path(p) for p in paths]
        dets = list(self.detectors) if one else [det]
        for d in dets:
            files[d] = list(paths)
            np_dict[d] = self.pattern_histogram(d, paths, normalize)
        self.outcome = None
        return dets

    def clear_pattern_files(self, kind: str, det: str) -> list[str]:
        """Forget the measured files (and the pattern read from them) of *det*, or of every detector with "one for all"."""
        files, np_dict, _normalize, one = self._pattern_store(kind)
        dets = list(self.detectors) if one else [det]
        for d in dets:
            if files.pop(d, None) is not None:
                np_dict.pop(d, None)
        self.outcome = None
        return dets

    def refresh_pattern_files(self) -> None:
        """Re-read every measured pattern at the current binning and channels (after either changed)."""
        for kind in ("irf", "bg"):
            files, np_dict, normalize, _one = self._pattern_store(kind)
            for det in [d for d in files if d in self.detectors and files[d]]:
                np_dict[det] = self.pattern_histogram(det, files[det], normalize)

    def _pattern_store(self, kind: str):
        if kind == "irf":
            return self.irf_files, self.irf_np, 2, self.irf_one_for_all
        if kind == "bg":
            return self.bg_files, self.bg_np, 3, self.bg_one_for_all
        raise ValueError(f"Unknown pattern kind {kind!r}: use 'irf' or 'bg'.")

    def auto_extract(self) -> None:
        """One click: binning, IRF / background, fit window, fit (the wizard's ``auto_extract_irf_bg``)."""
        tttr = self.current_tttr()
        if tttr is None:
            self.status = "Load bursts first: no data to extract an IRF from"
            return
        if not self.burst_indices():
            self.status = "No burst photons found for the selected file"
            return
        pick = self.auto_binning()
        if pick is not None:
            self.set_binning(int(pick))
        n = self.extract_irf_background()
        self.build_decay()
        window = select_fit_range(self.decay)
        if window is not None:
            self.settings.micro_time_start, self.settings.micro_time_stop = window
        self.build_decay()
        self.fit()
        self.status = (
            f"Auto IRF/background estimated from non-burst photons for {n} detector(s) (binning "
            f"{self.settings.micro_time_binning}, window {list(self.micro_time_range)})."
        )

    # -- fit --------------------------------------------------------------------------------------------------- #
    def parameter_vector(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the selected model's ordered free starts and fixed flags."""
        _, values, fixed = self.settings.parameter_state()
        return values, fixed

    def create_fit(self):
        """The ``Fit2x`` of the current detector, IRF and background (the wizard's ``create_fit_instance``)."""
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

    def _fit_tail(self, d: np.ndarray, x0: np.ndarray, fixed: np.ndarray) -> FitOutcome:
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
            d, model, irf, self.background(), self.window_ranges(), tail=True, diverged=False
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
        return {
            "sb": int(sb),
            "eb": int(eb),
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

    def run_batch(
        self, progress=None, max_workers: int | None = None, should_stop=None
    ) -> list[dict]:
        """Fit every burst of every loaded file and detector in worker processes (the wizard's ``process_bursts``).

        The photon channels and micro times of each raw file go to the workers through shared memory; each worker
        returns one row per burst (``Tau (green)``, ``gamma (green)``, ...). Nothing is exported here: the rows are kept
        on :attr:`burst_results`.
        """
        import multiprocessing as mp
        import os
        from concurrent.futures import ProcessPoolExecutor, as_completed
        from multiprocessing import shared_memory

        from ._mp_worker import process_one_file_worker

        if self.df_bursts is None or not len(self.tttrs):
            raise ValueError("No burst data loaded.")
        if self.settings.model == TAIL_MODEL:
            raise ValueError(
                "The tail fit previews the current decay; choose a Fit2x model to fit every burst."
            )
        det_order = list(self.detectors)
        binning = int(self.settings.micro_time_binning)
        configs = {det: self.batch_config(det) for det in det_order}
        for det, cfg in configs.items():
            cfg["half_len"] = max(1, cfg["irf"].size // 2)
        rc_max_seen = max(
            (int(np.max(info["chs"])) for info in self.detectors.values() if info.get("chs")),
            default=0,
        )
        identity_column = ("_measurement_path" if "_measurement_path" in column_names(self.df_bursts)
                           else "First File")
        first_file = np.array([str(v) for v in self.df_bursts[identity_column]], dtype=object)
        fp = numeric_column(self.df_bursts, "First Photon")
        lp = numeric_column(self.df_bursts, "Last Photon")
        groups: dict = {}
        for fname in dict.fromkeys(first_file.tolist()):
            mask = first_file == fname
            groups[fname] = list(zip(fp[mask].tolist(), lp[mask].tolist()))
        # Per-photon H2MM states, when the batch is split by state (the wizard's ``_load_state_arrays``).
        state_arrays, n_states = {}, 0
        if self.split_by_state and any(not _is_container(p) for p in self.bur_files):
            from . import state_split

            state_arrays, n_states, self.status = self.state_arrays_by_measurement()
        self.n_states = int(n_states)
        blocks, jobs = [], []
        try:
            for fname, bursts in groups.items():
                tttr = self.tttrs.get(fname if identity_column == "_measurement_path" else Path(fname).stem)
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
                    np.ndarray(states_full.shape, dtype=states_full.dtype, buffer=st_shm.buf)[:] = states_full
                    blocks.append(st_shm)
                    state_info = (st_shm.name, states_full.shape, str(states_full.dtype), int(n_states))
                rc_max = int(rc_full.max(initial=rc_max_seen)) if rc_full.size else rc_max_seen
                perdet = {}
                for det in det_order:
                    chs = self.detectors[det].get("chs", [])
                    pchs = np.asarray(chs[::2] if len(chs) >= 2 else chs, dtype=int)
                    schs = np.asarray(chs[1::2] if len(chs) >= 2 else chs, dtype=int)
                    lut = np.full(rc_max + 1, -1, dtype=np.int8)
                    if pchs.size:
                        lut[pchs] = 0
                    if schs.size:
                        lut[schs] = 1
                    perdet[det] = dict(configs[det], class_lut=lut)
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
            workers = max_workers or max(1, min(os.cpu_count() or 8, len(jobs)) - 1)
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
            with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as ex:
                futures = {ex.submit(process_one_file_worker, j): str(j[0]) for j in jobs}
                for fut in as_completed(futures):
                    if should_stop is not None and should_stop():
                        for pending in futures:
                            pending.cancel()
                        raise InterruptedError("The burst fit was stopped.")
                    try:
                        out, n = fut.result()
                    except (
                        Exception
                    ) as exc:  # a whole file failed: name it rather than export a short table
                        self.status = f"{futures[fut]} failed: {exc}"
                        out, n = [], 0
                    results.extend(out)
                    done += n
                    if progress is not None:
                        progress(min(done, total), total)
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
        """Write the ``b?4`` tables of the last batch beside the burst folders (the wizard's export, without the dialogs)."""
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
            color = det.lower()
            det_meta[det] = (
                color,
                color[0],
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
        for kind, key in (("irf", "irf_files"), ("bg", "bg_files")):
            files, np_dict, normalize, _one = self._pattern_store(kind)
            for det, paths in (payload.get(key) or {}).items():
                found = [Path(p) for p in paths if Path(p).is_file()]
                if det in self.detectors and found:
                    files[det] = found
                    np_dict[det] = self.pattern_histogram(det, found, normalize)

    # -- inspected burst --------------------------------------------------------------------------------------- #
    def inspect_burst(self, idx: int) -> dict[str, np.ndarray]:
        """Per detector, the VV | VH histogram of burst *idx* of the table (``Last Photon`` is inclusive)."""
        if self.df_bursts is None or not len(self.tttrs):
            return {}
        n = int(row_count(self.df_bursts))
        if not 0 <= idx < n:
            return {}
        names = column_names(self.df_bursts)
        key = (str(self.df_bursts["_measurement_path"][idx]) if "_measurement_path" in names
               else Path(str(self.df_bursts["First File"][idx])).stem)
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
