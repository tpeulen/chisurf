"""The Qt-free engine of the burst-MLE lifetime analysis (cards ML0 and ML1).

What the wizard did with its widgets is here as functions of explicit inputs and a session object that holds the
state those widgets held (detectors, burst files, the micro-time window, the IRF / background patterns, the fit
settings). The wizard delegates its pure steps to the module functions below, so both front ends compute the same
numbers; ``tests/test_mle_engine.py`` compares the session with the wizard on the in-repository BH sample.

No Qt and no emtk are imported here.
"""

from __future__ import annotations

import collections.abc
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

from .fit_display import DecayCurves, TailFitResult, decay_curves
from .interpolate import interpolate_shift


# --------------------------------------------------------------------------------------------------------------------
# pure steps (the wizard calls these)
# --------------------------------------------------------------------------------------------------------------------
def burst_photon_indices(df_bursts: Any, current_filename: str) -> list[int]:
    """Photon indices of every burst of the file *current_filename* (a ``.bur`` file), merged and ascending."""
    if not current_filename or df_bursts is None:
        return []
    if "stem" not in column_names(df_bursts):
        first_file_vals = np.asarray(df_bursts["First File"], dtype=object)
        df_bursts["stem"] = [re.split(r"[\\/]", str(v))[-1].rsplit(".", 1)[0] for v in first_file_vals]
    curr_stem = Path(current_filename).stem
    mask = np.asarray(df_bursts["stem"], dtype=object) == curr_stem
    if not mask.any():
        return []
    starts = numeric_column(df_bursts, "First Photon")[mask].astype(np.int32)
    stops = numeric_column(df_bursts, "Last Photon")[mask].astype(np.int32)
    idxs = np.concatenate([starts, stops + 1])
    weights = np.concatenate([np.ones_like(starts, dtype=np.int32), -np.ones_like(stops + 1, dtype=np.int32)])
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
        acquisition_time = (tttr.macro_times[-1] - tttr.macro_times[0]) * tttr.header.macro_time_resolution
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
    counts = int(np.isin(np.asarray(tttr.routing_channels)[burst_idx], np.asarray(chs, dtype=int)).sum())
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


def write_b4_tables(results, files_by_stem, det_meta, channel_settings, *, on_new_folder=None, tick=None):
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
        by_stem.setdefault(stem, {})[det] = store_from_arrays({c: arr[:, i] for i, c in enumerate(cols)})
        out = np.zeros((arr.shape[0] * 2 + 1, arr.shape[1]), dtype=float)
        out[1::2] = arr
        out_file = out_dir / f"{stem}.b{letter}4"
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


class NumpyEncoder(__import__("json").JSONEncoder):
    """JSON encoder that writes numpy arrays as lists."""

    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


#: The binnings the detector page offers (the Qt combo's items).
BINNING_CHOICES = [1, 2, 4, 8, 16, 32, 64, 128, 256]


def read_burst_analysis(paris_path: Path, pattern: str = "**/*.bur") -> tuple[Any, dict[str, Path], dict | None]:
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
class LazyTTTRs(collections.abc.MutableMapping):
    """File stem -> ``tttrlib.TTTR``, opened on first use."""

    def __init__(self, paths: dict[str, Path], file_type: str = "auto") -> None:
        self.paths = paths
        self.file_type = file_type
        self._cache: dict[str, Any] = {}

    def __getitem__(self, key: str):
        import tttrlib

        if key not in self.paths:
            raise KeyError(key)
        if key not in self._cache:
            path = self.paths[key]
            file_type = self.file_type
            if not file_type or str(file_type).lower() == "auto":
                file_type = tttrlib.inferTTTRFileType(str(path))
            self._cache[key] = tttrlib.TTTR(str(path), file_type)
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

    def __post_init__(self) -> None:
        self.tttrs = LazyTTTRs(self.tttr_paths, self.file_type)
        self.det_settings: dict[str, MleSettings] = {}
        #: Rows of the last batch run, one mapping per burst and detector.
        self.burst_results: list[dict] = []

    @property
    def settings(self) -> MleSettings:
        """The settings of the current detector (created from the template on first use)."""
        det = self.current_detector
        if det not in self.det_settings:
            self.det_settings[det] = dataclasses.replace(self.template)
        return self.det_settings[det]

    def settings_of(self, det: str) -> MleSettings:
        if det not in self.det_settings:
            self.det_settings[det] = dataclasses.replace(self.template)
        return self.det_settings[det]

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
        table, raw_paths, setup_info = read_burst_analysis(self.bur_files[0].parent.parent)
        self.df_bursts = table
        self.tttr_paths.clear()
        self.tttr_paths.update(raw_paths)
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
        curr = Path(self.current_filename).name if self.current_filename else None
        names = column_names(df)
        if "burst_file" in names and curr:
            sub = take_where(df, np.asarray(df["burst_file"]) == curr)
            if row_count(sub) > 0:
                df, names = sub, column_names(sub)
        if "First File" not in names or row_count(df) == 0:
            return None
        return self.tttrs.get(Path(str(np.asarray(df["First File"], dtype=object)[0])).stem)

    def burst_indices(self) -> list[int]:
        return burst_photon_indices(self.df_bursts, self.current_filename)

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
            self.irf_np.get(self.current_detector), micro_time_range=self.micro_time_range, binning=s.micro_time_binning,
            shift=s.shift, shift_sp=s.shift_sp, shift_ss=s.shift_ss, irf_start=s.irf_start, irf_stop=s.irf_stop,
            threshold_vv=s.irf_threshold_vv, threshold_vh=s.irf_threshold_vh,
        )

    def background(self) -> np.ndarray:
        return process_background(self.bg_np.get(self.current_detector), self.settings.shift, self.irf())

    def window_ranges(self) -> tuple[int, int, int, int]:
        return window_bins(self.detector.get("micro_time_ranges"), self.micro_time_range, self.settings.micro_time_binning)

    # -- decay ------------------------------------------------------------------------------------------------- #
    def build_decay(self) -> np.ndarray | None:
        """The decay of every burst photon of the current file and detector (``decay_of_current_file``)."""
        tttr = self.current_tttr()
        chs = self.detector.get("chs", [])
        idx = np.asarray(self.burst_indices(), dtype=int)
        if tttr is None or not chs or idx.size == 0:
            return None
        rows = vv_vh_histogram(
            tttr[idx], chs, self.micro_time_range, self.settings.micro_time_binning,
            detector_ranges=self.detector.get("micro_time_ranges"), shift=self.settings.shift, normalize_counts=-1,
        )
        self.decay = np.asarray(rows)
        return self.decay

    # -- IRF / background -------------------------------------------------------------------------------------- #
    def auto_binning(self) -> int | None:
        tttr = self.current_tttr()
        return select_binning(tttr, self.detector.get("chs", []), np.asarray(self.burst_indices(), dtype=int), BINNING_CHOICES)

    def extract_irf_background(self) -> int:
        """IRF and background from the photons outside the bursts, at the current binning; returns the detectors done."""
        from chisurf.core.fluorescence.burst import extract_mle_irf_background

        tttr = self.current_tttr()
        idx = np.asarray(self.burst_indices(), dtype=int)
        in_burst = np.zeros(len(tttr), dtype=bool)
        in_burst[idx] = True
        patterns = extract_mle_irf_background(
            tttr, self.detectors, micro_time_binning=self.settings.micro_time_binning, mask=~in_burst,
            min_photons=max(2, int(self.settings.min_photons)), irf_model=self.settings.irf_model,
        )
        n = 0
        for det, pat in patterns.items():
            if det:
                self.irf_np[det] = np.asarray(pat["irf"], dtype=float)
                self.bg_np[det] = np.asarray(pat["bg"], dtype=float)
                n += 1
        return n

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
        s = self.settings
        return (np.array([s.tau, s.gamma, s.r0, s.rho]),
                np.array([int(s.fix_tau), int(s.fix_gamma), int(s.fix_r0), int(s.fix_rho)]))

    def create_fit(self):
        """The ``Fit2x`` of the current detector, IRF and background (the wizard's ``create_fit_instance``)."""
        from chisurf.core.fluorescence.mle.fit2x import Fit2x, Fit2xModel, Fit2xSettings

        tttr = self.current_tttr()
        header = header_time_ns(tttr, self.settings.micro_time_binning)
        dt, period = header if header is not None else (None, None)
        gf, l1, l2 = self.polarisation()
        irf = self.irf().astype(np.float64, copy=True)
        bg = self.background().astype(np.float64, copy=True)
        total = float(bg.sum())
        if total > 0.0:
            bg = bg / total
        settings = Fit2xSettings(
            dt=dt, period=period, irf=irf, background=bg, g_factor=gf, l1=l1, l2=l2,
            p2s_twoIstar=self.settings.p2s_twoIstar, soft_bifl_scatter=self.settings.BIFL_scatter,
        )
        return Fit2x(settings, model=Fit2xModel(self.settings.model))

    def blocked_reason(self) -> str | None:
        det = self.current_detector
        if not det:
            return "no detector selected"
        if det not in self.irf_np or np.asarray(self.irf_np.get(det, [])).size == 0:
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
        if irf_len and len(d) != irf_len:
            self.status = f"Cannot fit: decay length {len(d)} != IRF length {irf_len} (rebuild IRF at the current binning)"
            return None
        fit = self.create_fit()
        res = fit.fit(data=d, initial_values=x0, fixed=fixed, include_model=True)
        model = np.asarray(res.model_curve, dtype=float) if res.model_curve is not None else np.zeros_like(d)
        diverged = float(res.twoIstar) < 0 or not np.isfinite(float(res.twoIstar))
        curves = decay_curves(d, model, self.irf(), self.background(), self.window_ranges(),
                              tail=self.settings.model == "tail", diverged=diverged)
        self.outcome = FitOutcome(np.asarray(res.x, dtype=float), float(res.twoIstar), list(fit.parameter_names), curves,
                                  model, d, res)
        self.status = "" if not diverged else "Fit diverged: invalid fit quality (2I* < 0)"
        return self.outcome


    # -- batch ------------------------------------------------------------------------------------------------- #
    def batch_config(self, det: str) -> dict:
        """The per-detector constants a worker needs: window, timing, polarisation, start values, IRF, background."""
        st = self.settings_of(det)
        info = self.detectors.get(det, {})
        tttr = self.current_tttr()
        header = header_time_ns(tttr, st.micro_time_binning)
        dt, period = header if header is not None else (1.0, 1.0)
        sb, eb = st.micro_time_start, st.micro_time_stop
        if eb <= sb:
            sb, eb = self.micro_time_range
        irf = process_irf(
            self.irf_np.get(det), micro_time_range=(sb, eb), binning=st.micro_time_binning, shift=st.shift,
            shift_sp=st.shift_sp, shift_ss=st.shift_ss, irf_start=st.irf_start, irf_stop=st.irf_stop,
            threshold_vv=st.irf_threshold_vv, threshold_vh=st.irf_threshold_vh,
        ) if np.asarray(self.irf_np.get(det, [])).size else np.asarray(self.irf_np.get(det, np.array([])), dtype=float)
        raw_bg = np.asarray(self.bg_np.get(det, np.array([])), dtype=float)
        bg = process_background(raw_bg, st.shift, irf) if raw_bg.size else raw_bg
        x0 = np.array([st.tau, st.gamma, st.r0, st.rho], dtype=np.float64)
        fixed = np.array([int(st.fix_tau), int(st.fix_gamma), int(st.fix_r0), int(st.fix_rho)], dtype=np.int32)
        return {
            "sb": int(sb), "eb": int(eb), "dt": float(dt), "period": float(period),
            "g_factor": float(info.get("g_factor", 1.0)), "l1": float(info.get("l1", 0.0)), "l2": float(info.get("l2", 0.0)),
            "p2s_twoIstar": bool(st.p2s_twoIstar), "BIFL_scatter": bool(st.BIFL_scatter), "min_photons": int(st.min_photons),
            "state_min_photons": 5, "x0": x0, "fixed": fixed, "irf": np.asarray(irf, dtype=np.float64),
            "bg": np.asarray(bg, dtype=np.float64), "model": st.model,
            "param_names": ["tau", "gamma", "r0", "rho"] if st.model == "fit23" else [],
        }

    def run_batch(self, progress=None, max_workers: int | None = None, should_stop=None) -> list[dict]:
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
        det_order = list(self.detectors)
        binning = int(self.settings.micro_time_binning)
        configs = {det: self.batch_config(det) for det in det_order}
        for det, cfg in configs.items():
            cfg["half_len"] = max(1, cfg["irf"].size // 2)
        rc_max_seen = max((int(np.max(info["chs"])) for info in self.detectors.values() if info.get("chs")), default=0)
        first_file = np.array([str(v) for v in np.asarray(self.df_bursts["First File"], dtype=object)], dtype=object)
        fp = numeric_column(self.df_bursts, "First Photon")
        lp = numeric_column(self.df_bursts, "Last Photon")
        groups: dict = {}
        for fname in dict.fromkeys(first_file.tolist()):
            mask = first_file == fname
            groups[fname] = list(zip(fp[mask].tolist(), lp[mask].tolist()))
        blocks, jobs = [], []
        try:
            for fname, bursts in groups.items():
                tttr = self.tttrs.get(Path(fname).stem)
                if tttr is None:
                    jobs.append((fname, bursts, None, None, None, None, None, None, det_order, {}, int(self.settings.shift or 0), None))
                    continue
                rc_full = np.asarray(tttr.routing_channels)
                mt_full = np.asarray(tttr.micro_times)
                mt_bins = (mt_full // binning).astype(np.int32, copy=False) if binning > 1 else mt_full.astype(np.int32, copy=True)
                if rc_full.dtype != np.uint16 and int(rc_full.max(initial=0)) <= 65535:
                    rc_full = rc_full.astype(np.uint16, copy=False)
                if mt_bins.dtype != np.uint16 and int(mt_bins.max(initial=0)) <= 65535:
                    mt_bins = mt_bins.astype(np.uint16, copy=False)
                rc_shm = shared_memory.SharedMemory(create=True, size=rc_full.nbytes)
                np.ndarray(rc_full.shape, dtype=rc_full.dtype, buffer=rc_shm.buf)[:] = rc_full
                mt_shm = shared_memory.SharedMemory(create=True, size=mt_bins.nbytes)
                np.ndarray(mt_bins.shape, dtype=mt_bins.dtype, buffer=mt_shm.buf)[:] = mt_bins
                blocks.extend([rc_shm, mt_shm])
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
                jobs.append((fname, bursts, rc_shm.name, rc_full.shape, str(rc_full.dtype), mt_shm.name, mt_bins.shape,
                             str(mt_bins.dtype), det_order, perdet, int(self.settings.shift or 0), None))
            ctx = mp.get_context("spawn")
            workers = max_workers or max(1, min(os.cpu_count() or 8, len(jobs)) - 1)
            results: list[dict] = []
            total = int(row_count(self.df_bursts))
            done = 0
            with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as ex:
                futures = {ex.submit(process_one_file_worker, j): str(j[0]) for j in jobs}
                for fut in as_completed(futures):
                    if should_stop is not None and should_stop():
                        for pending in futures:
                            pending.cancel()
                        raise InterruptedError("The burst fit was stopped.")
                    try:
                        out, n = fut.result()
                    except Exception as exc:  # a whole file failed: name it rather than export a short table
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
        return results


    # -- export and settings ----------------------------------------------------------------------------------- #
    def channel_settings(self) -> dict:
        """The per-detector state written beside the tables as ``channel_settings.json``."""
        return {det: dataclasses.asdict(self.settings_of(det)) for det in self.detectors}

    def export_results(self, tick=None) -> list[Path]:
        """Write the ``b?4`` tables of the last batch beside the burst folders (the wizard's export, without the dialogs)."""
        files_by_stem = {p.stem: p for p in self.bur_files}
        rows = []
        for row in self.burst_results:
            stem = Path(row["First File"]).stem
            if stem in files_by_stem:
                rows.append(dict(row, **{"First Stem": stem}))
        if not rows:
            raise ValueError("No burst-fit rows to save: run the batch first.")
        det_meta = {}
        names = ["tau", "gamma", "r0", "rho"]
        for det in self.detectors:
            color = det.lower()
            det_meta[det] = (color, color[0], state_result_columns(color, self.settings_of(det).model, names, 0))
        written = write_b4_tables(rows, files_by_stem, det_meta, self.channel_settings(), tick=tick)
        return [] if written is None else written[0]

    def settings_payload(self) -> dict:
        """Everything a settings file holds: the detector definition and every detector's settings."""
        return {
            "file_type": self.file_type,
            "detectors": self.detectors,
            "micro_time_binning": int(self.template.micro_time_binning),
            "detector_settings": self.channel_settings(),
        }

    def apply_settings_payload(self, payload: dict) -> None:
        """Load a settings file written by :meth:`settings_payload`."""
        if payload.get("detectors"):
            self.set_detectors(payload["detectors"], payload.get("file_type"))
        known = {f.name for f in dataclasses.fields(MleSettings)}
        for det, values in (payload.get("detector_settings") or {}).items():
            self.det_settings[det] = MleSettings(**{k: v for k, v in values.items() if k in known})
        if payload.get("micro_time_binning"):
            self.set_binning(int(payload["micro_time_binning"]))
