"""Toolkit-free microtime histograms, burst gates and polarization exports."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

import numpy as np

from chisurf.core.data_io.detector_setups import setup_lut_open_kwargs
from chisurf.core.fio.staging import TTTR_EXTENSIONS, open_tttr


def read_burst_ranges(path):
    lines = Path(path).read_text().splitlines()
    if not lines:
        return []
    first = lines[0].split("\t")
    normalized = [re.sub(r"[^a-z]", "", value.lower()) for value in first]
    first_column = next(
        (
            i
            for i, key in enumerate(normalized)
            if key in {"firstphoton", "startphoton", "startidx"}
        ),
        None,
    )
    last_column = next(
        (i for i, key in enumerate(normalized) if key in {"lastphoton", "stopphoton", "stopidx"}),
        None,
    )
    ranges = []
    for line in lines[1:] if first_column is not None else lines:
        if not line.strip() or line.lstrip().startswith(("#", "//")):
            continue
        fields = line.replace(",", "\t").split()
        try:
            start = int(fields[first_column or 0])
            stop = int(fields[last_column if last_column is not None else 1])
        except (ValueError, IndexError):
            continue
        if start >= 0 and stop >= start:
            ranges.append((start, stop))
    return ranges


def burst_mask(count, ranges):
    delta = np.zeros(count + 1, dtype=np.int64)
    for first, last in ranges:
        first = max(0, min(count, int(first)))
        stop = max(first, min(count, int(last) + 1))
        if first < stop:
            delta[first] += 1
            delta[stop] -= 1
    return np.cumsum(delta[:-1]) > 0


def shift_histogram(values, offset):
    values = np.asarray(values)
    out = np.zeros_like(values)
    offset = int(offset)
    if abs(offset) >= len(values):
        return out
    if offset > 0:
        out[offset:] = values[:-offset]
    elif offset < 0:
        out[:offset] = values[-offset:]
    else:
        out[:] = values
    return out



def gap_selection(selected, macro_times, gap_ticks, invert=False):
    """Narrow *selected* to the photons whose next selected photon follows within *gap_ticks*.

    The inter-photon filter of a decay: the photons of bright stretches (single-molecule
    bursts) when not inverted, the isolated photons between them (a background decay from
    the same measurement) when inverted. The last selected photon is dropped either way,
    because it has no successor to test.

    Parameters
    ----------
    selected : numpy.ndarray of bool
        Photons chosen by the detector, window and burst masks.
    macro_times : numpy.ndarray of int
        Macro time of every photon, in ticks.
    gap_ticks : int
        Largest gap to the next selected photon that keeps a photon.
    invert : bool, optional
        Keep the photons whose next selected photon is at least *gap_ticks* away instead.

    Returns
    -------
    numpy.ndarray of bool
        The narrowed selection, same length as *selected*.
    """
    index = np.flatnonzero(selected)
    out = np.zeros(len(selected), dtype=bool)
    if len(index) < 2:
        return out
    gaps = np.diff(macro_times[index])
    keep = gaps >= int(gap_ticks) if invert else gaps <= int(gap_ticks)
    out[index[:-1][keep]] = True
    return out

class HistogramModel:
    def __init__(self):
        self.files = []
        self.enabled = {}
        self.bid_files = []
        self.bid_enabled = {}
        self.setup = {"detectors": {}, "windows": {}, "tttr_reading": {}}
        self.detector = ""
        self.parallel = [0]
        self.perpendicular = [1]
        self.polarized = True
        self.window = "All windows"
        self.filetype = "Auto"
        self.binning = 1
        #: Inter-photon filter: keep a photon only when the next selected photon follows within
        #: ``gap_ticks`` macro-time ticks (the photons of bright stretches, such as bursts), or with
        #: ``gap_invert`` only when it does not (the isolated photons between them: a background decay).
        self.gap_filter = False
        self.gap_ticks = 200000
        self.gap_invert = False
        self.dt_ns = 0.016
        self.dt_manual = False
        self.g_factor = 1.0
        self.vv_shift = 0
        self.vh_shift = 0
        self.polarization = "vm"
        self.original_histograms = {}
        self.cumulative_parallel = None
        self.cumulative_perpendicular = None
        self.cumulative_ps = None
        self.combined = None
        self.fwhm_bins = 0
        self.fwhm_ns = 0
        self.output = ""
        self.auto_save = True
        self.message = ""

    def invalidate(self):
        self.original_histograms = {}
        self.cumulative_parallel = self.cumulative_perpendicular = self.cumulative_ps = (
            self.combined
        ) = None
        self.fwhm_bins = self.fwhm_ns = 0

    def snapshot(self):
        return deepcopy(self)

    def set_setup(self, setup):
        self.setup = deepcopy(setup)
        self.polarized = bool(setup.get("polarization_resolved", True))
        reading = setup.get("tttr_reading") or {}
        self.filetype = str(reading.get("file_type") or "Auto")
        self.binning = max(1, int(reading.get("micro_time_binning", self.binning)))
        if self.detector not in setup.get("detectors", {}):
            self.detector = next(iter(setup.get("detectors", {})), "")
        self.select_detector(self.detector)

    def select_detector(self, name):
        self.detector = name
        config = self.setup.get("detectors", {}).get(name, {})
        routing = list(config.get("chs") or [])
        if routing:
            self.parallel = routing[::2] if self.polarized else routing
            self.perpendicular = routing[1::2] if self.polarized else []
        if config.get("g_factor") is not None:
            self.g_factor = float(config["g_factor"])
        self.original_histograms = {}
        self.cumulative_ps = None
        self.cumulative_parallel = self.cumulative_perpendicular = self.combined = None
        self.fwhm_bins = self.fwhm_ns = 0
        self.update_output_filename()

    def update_output_filename(self):
        files = self.selected_files()
        if not files:
            return
        stem = re.sub(r"_\d{2,4}$", "", Path(files[0]).stem)
        p = ",".join(map(str, self.parallel)) or "all"
        s = ",".join(map(str, self.perpendicular)) or "all"
        directory = (
            Path(self.selected_bids()[0]).parent if self.selected_bids() else Path(files[0]).parent
        )
        self.output = str(
            directory / f"{stem}{'_' + self.detector if self.detector else ''}_({p})-({s}).dat"
        )

    def selected_files(self):
        return [Path(path) for path in self.files if self.enabled.get(str(path), True)]

    def selected_bids(self):
        return [Path(path) for path in self.bid_files if self.bid_enabled.get(str(path), True)]

    def add_paths(self, paths, bids=False):
        target = self.bid_files if bids else self.files
        for path in paths:
            p = Path(path)
            candidates = sorted(p.rglob("*")) if p.is_dir() else [p]
            for candidate in candidates:
                candidate = candidate.resolve()
                extensions = (".bst", ".bur") if bids else TTTR_EXTENSIONS
                if (
                    candidate.is_file()
                    and candidate.suffix.lower() in extensions
                    and str(candidate) not in target
                ):
                    target.append(str(candidate))
        self.update_output_filename()

    @staticmethod
    def base_name(path):
        stem = Path(path).stem
        return re.sub(r"_\d+$", "", stem) if Path(path).suffix.lower() == ".bur" else stem

    def find_corresponding_files(self):
        found = []
        for bid in self.selected_bids():
            stem = self.base_name(bid)
            for directory in [bid.parent, *list(bid.parents)[1:4]]:
                candidates = [
                    path
                    for path in directory.glob(stem + "*")
                    if path.is_file() and path.suffix.lower() in TTTR_EXTENSIONS
                ]
                if candidates:
                    found.extend(candidates)
                    break
        self.files = []
        self.enabled = {}
        self.add_paths(found)
        if not found:
            raise ValueError("No corresponding TTTR source files found within four parent folders.")

    def compute(self, reader=None, cancel_cb=None, progress_cb=None):
        files = self.selected_files()
        if not files:
            raise ValueError("Queue and select TTTR photon files first.")
        if not self.parallel:
            raise ValueError("Define at least one detector routing channel.")
        if self.binning < 1:
            raise ValueError("Binning factor must be positive.")
        bursts = {self.base_name(path): read_burst_ranges(path) for path in self.selected_bids()}
        histograms = {}
        resolution = None
        reading = setup_lut_open_kwargs(self.setup)
        config = self.setup.get("detectors", {}).get(self.detector, {})
        for index, path in enumerate(files):
            if cancel_cb and cancel_cb():
                raise RuntimeError("Histogram calculation stopped between files.")
            if progress_cb:
                progress_cb(index, len(files))
            if path.suffix.lower() == ".spc" and self.filetype in {"Auto", "auto", ""}:
                raise ValueError(
                    "Choose the SPC container subtype before reading headerless SPC data."
                )
            stream = (
                reader(path)
                if reader
                else open_tttr(
                    path,
                    None if self.filetype in {"auto", "Auto", ""} else self.filetype,
                    cancel_cb=cancel_cb,
                    **reading,
                )
            )
            micro = np.asarray(stream.micro_times, dtype=np.int64)
            routing = np.asarray(stream.routing_channels)
            macro = np.asarray(stream.macro_times, dtype=np.int64) if self.gap_filter else None
            mask = np.ones(len(micro), dtype=bool)
            if bursts:
                key = next(
                    (
                        name
                        for name in (path.stem, re.sub(r"_\d+$", "", path.stem), path.name)
                        if name in bursts
                    ),
                    None,
                )
                if key is None or not bursts[key]:
                    continue
                mask &= burst_mask(len(micro), bursts[key])
            gates = config.get("micro_time_ranges") or []
            if gates:
                gate_mask = np.zeros(len(micro), dtype=bool)
                for gate in gates:
                    if gate is None:
                        gate_mask[:] = True
                    else:
                        gate_mask |= (micro >= int(gate[0])) & (micro <= int(gate[1]))
                mask &= gate_mask
            window = self.setup.get("windows", {}).get(self.window)
            if window is not None:
                mask &= (micro >= int(window[0])) & (micro <= int(window[1]))
            binned = micro // int(self.binning)
            n_raw = int(stream.header.get_effective_number_of_micro_time_channels())
            bins = max(1, (n_raw + self.binning - 1) // self.binning)
            y = []
            vv_channels = (
                self.parallel
                if self.polarized
                else list(dict.fromkeys(self.parallel + self.perpendicular))
            )
            for channels in (vv_channels, self.perpendicular if self.polarized else []):
                selected = mask & np.isin(routing, channels) if channels else np.zeros(len(micro), bool)
                if macro is not None:
                    selected = gap_selection(selected, macro, self.gap_ticks, self.gap_invert)
                indices = binned[selected]
                y.append(np.bincount(indices, minlength=bins))
            histograms[str(path)] = {"parallel": y[0], "perpendicular": y[1]}
            timing = self.setup.get("tttr_reading") or {}
            dt = float(getattr(stream.header, "micro_time_resolution", 0) or 0) * 1e9 * self.binning
            if (
                timing.get("override_timing")
                and float(timing.get("micro_time_resolution", 0) or 0) > 0
            ):
                dt = float(timing["micro_time_resolution"]) * 1e-3 * self.binning
            if dt <= 0:
                dt = (
                    float(
                        (self.setup.get("tttr_reading") or {}).get("micro_time_resolution", 0) or 0
                    )
                    * 1e-3
                    * self.binning
                )
            if dt > 0 and not self.dt_manual:
                if resolution is not None and not np.isclose(dt, resolution):
                    raise ValueError("Selected files have incompatible micro-time resolutions.")
                resolution = dt
        if not histograms:
            raise ValueError("No selected photons or matching burst-index sources were read.")
        self.original_histograms = histograms
        if resolution:
            self.dt_ns = resolution
        self.update_timeshifts()
        if self.auto_save and self.output:
            self.save(self.output)
        self.message = f"Computed {len(histograms)} file(s)."

    def update_timeshifts(self):
        if not self.original_histograms:
            return
        maximum = max(
            len(values[channel])
            for values in self.original_histograms.values()
            for channel in ("parallel", "perpendicular")
        )
        self.cumulative_parallel = np.zeros(maximum, dtype=np.int64)
        self.cumulative_perpendicular = np.zeros(maximum, dtype=np.int64)
        for values in self.original_histograms.values():
            for name, target, shift in (
                ("parallel", self.cumulative_parallel, self.vv_shift),
                ("perpendicular", self.cumulative_perpendicular, self.vh_shift),
            ):
                vector = shift_histogram(values[name], shift)
                target[: len(vector)] += vector
        self.cumulative_ps = (
            np.concatenate([self.cumulative_parallel, self.cumulative_perpendicular])
            if self.polarized
            else self.cumulative_parallel.copy()
        )
        self.combined = self.cumulative_parallel + 2 * self.g_factor * self.cumulative_perpendicular
        peak = int(np.argmax(self.combined))
        half = float(np.max(self.combined)) * 0.5
        left = np.flatnonzero(self.combined[:peak] <= half)
        right = np.flatnonzero(self.combined[peak:] <= half)
        self.fwhm_bins = (peak + int(right[0]) if len(right) else len(self.combined) - 1) - (
            int(left[-1]) if len(left) else 0
        )
        self.fwhm_ns = self.fwhm_bins * self.dt_ns

    def save(self, path):
        if self.cumulative_ps is None:
            raise ValueError("Compute a histogram before saving.")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savetxt(path, self.cumulative_ps.astype(np.int64), fmt="%d")

    def export_settings(self):
        return {
            key: deepcopy(getattr(self, key))
            for key in (
                "files",
                "enabled",
                "bid_files",
                "bid_enabled",
                "setup",
                "detector",
                "parallel",
                "perpendicular",
                "polarized",
                "window",
                "filetype",
                "binning",
                "gap_filter",
                "gap_ticks",
                "gap_invert",
                "dt_ns",
                "dt_manual",
                "g_factor",
                "vv_shift",
                "vh_shift",
                "polarization",
                "output",
                "auto_save",
            )
        }

    def restore_settings(self, state):
        for key, value in state.items():
            if key in self.export_settings():
                setattr(self, key, deepcopy(value))
