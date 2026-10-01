"""Toolkit-free VV/VH anisotropy computation and exports."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from chisurf.core.fio import read_vv_vh
from chisurf.core.fio.vv_vh import write_vv_vh


def _channels(path):
    data = read_vv_vh(str(path), split=True)
    if isinstance(data, dict):
        vv, vh = data["VV"], data["VH"]
    else:
        vv, vh = data
    vv, vh = np.asarray(vv, dtype=float), np.asarray(vh, dtype=float)
    if len(vv) < 2 or len(vv) != len(vh):
        raise ValueError("VV/VH file needs at least two bins in each equally sized channel.")
    return vv, vh


BATCH_EXTENSIONS = (".dat", ".txt")
BATCH_COLUMNS = ("filename", "r_inf", "region_min", "region_max", "bg_vv", "bg_vh", "g_factor", "error")


class AnisotropyModel:
    """State and work of the VV/VH anisotropy tool; the window only shows and edits it."""

    def __init__(self):
        self.loaded_file = ""
        self.vv_raw = None
        self.vh_raw = None
        self.time_axis = None
        self.g_factor = 1.0
        self.apply_bg = True
        self.bg_vv = 0.0
        self.bg_vh = 0.0
        self.flip = False
        self.shift = 0.0
        self.region_bounds = [0.0, 1.0]
        self.r_t = None
        self.r_infty = float("nan")
        self.batch_files = []
        self.batch_results = []
        self.message = "No file loaded"
        #: a dialog the window should open: load, save, add_files, add_folder, save_batch, database
        self.request = ""
        #: whether the batch window is open, and the settings it was opened with (as the Qt window)
        self.batch_open = False
        self.batch_snapshot = None
        self.selected_batch_file = ""

    # -- the fields the window edits ---------------------------------------
    @property
    def region_start(self):
        return float(self.region_bounds[0])

    @region_start.setter
    def region_start(self, value):
        self.region_bounds[0] = float(value)

    @property
    def region_end(self):
        return float(self.region_bounds[1])

    @region_end.setter
    def region_end(self, value):
        self.region_bounds[1] = float(value)

    @property
    def region_min(self):
        """Lower bound of the r-infinity region (the Qt region was always ordered)."""
        return min(self.region_bounds)

    @property
    def region_max(self):
        """Upper bound of the r-infinity region."""
        return max(self.region_bounds)

    @property
    def r_infty_text(self):
        """The Qt tool's r-infinity read-out: five decimals, or N/A."""
        return f"{self.r_infty:.5f}" if np.isfinite(self.r_infty) else "N/A"

    @property
    def has_data(self):
        return self.vv_raw is not None

    @property
    def has_batch_files(self):
        return bool(self.batch_files)

    @property
    def has_batch_results(self):
        return bool(self.batch_results)

    def enabled(self, action):
        """Whether a button of the spec can act now (the window greys it otherwise)."""
        if action == "request_save":
            return self.has_data
        if action in ("run_batch", "clear_batch"):
            return self.has_batch_files
        if action == "remove_selected":
            return bool(self.selected_batch_file)
        if action == "request_save_batch":
            return self.has_batch_results
        return True

    # -- dialog requests (the window opens the file dialog) ------------------
    def recompute(self, _value=None):
        """The spec's ``call`` after a field changed: r(t) and r-infinity follow it."""
        self.compute()

    def request_load(self):
        self.request = "load"

    def request_save(self):
        self.request = "save"

    def request_add_files(self):
        self.request = "add_files"

    def request_add_folder(self):
        self.request = "add_folder"

    def request_database(self):
        self.request = "database"

    def request_save_batch(self):
        self.request = "save_batch"

    def open_batch(self):
        """Open the batch window with a snapshot of the current settings, as the Qt tool does."""
        self.batch_snapshot = self.snapshot()
        self.batch_open = True

    def close_batch(self):
        self.batch_open = False

    def load(self, path):
        """Load a VV/VH file; a file that cannot be read leaves the loaded data as it was."""
        try:
            vv, vh = _channels(path)
        except Exception as exc:
            self.message = f"Could not load {Path(str(path)).name}: {exc}"
            raise
        self.vv_raw, self.vh_raw = vv, vh
        self.time_axis = np.arange(len(vv), dtype=float)
        self.loaded_file = str(path)
        n = len(vv)
        self.region_bounds = [float(int(n * .7)), float(int(n * .9))]
        self.message = f"Loaded {Path(path).name}: {n} channels"
        self.compute()

    def channels(self):
        if self.vv_raw is None:
            return None, None
        return (self.vh_raw, self.vv_raw) if self.flip else (self.vv_raw, self.vh_raw)

    @staticmethod
    def shifted(y, shift):
        t = np.arange(len(y), dtype=float)
        if shift == 0:
            return y.astype(float).copy()
        result = np.full(len(y), np.nan)
        query = t - shift
        valid = (query >= 0) & (query <= t[-1])
        result[valid] = np.interp(query[valid], t, y)
        return result

    def corrected_channels(self):
        vv, vh = self.channels()
        if vv is None:
            return None, None
        vv, vh = vv.astype(float).copy(), vh.astype(float).copy()
        if self.apply_bg:
            vv -= self.bg_vv
            vh -= self.bg_vh
        return vv, vh

    def compute(self):
        vv, vh = self.corrected_channels()
        if vv is None:
            self.r_t, self.r_infty = None, float("nan")
            return
        shifted = self.shifted(vh, self.shift)
        denominator = vv + 2 * self.g_factor * shifted
        r = np.full(len(vv), np.nan)
        valid = np.isfinite(denominator) & (denominator > 0)
        r[valid] = (vv[valid] - self.g_factor * shifted[valid]) / denominator[valid]
        lo, hi = self.region_min, self.region_max
        left = int(np.argmin(abs(self.time_axis - lo)))
        right = int(np.argmin(abs(self.time_axis - hi)))
        if right <= left:
            right = min(len(r), left + 1)
        selection = r[left:right]
        selection = selection[np.isfinite(selection)]
        self.r_t = r
        self.r_infty = float(np.mean(selection)) if len(selection) else float("nan")

    def save(self, base_path):
        if self.r_t is None:
            raise ValueError("Load a VV/VH file before saving outputs.")
        self.compute()
        base = Path(base_path).with_suffix("")
        vv, vh = self.corrected_channels()
        vh = self.shifted(vh, self.shift)
        vv = np.where(np.isfinite(vv) & (vv > 0), vv, 0)
        vh = np.where(np.isfinite(vh) & (vh > 0), vh, 0)
        decay = base.with_name(base.name + "_shifted.dat")
        trace = base.with_name(base.name + "_anisotropy.txt")
        info = base.with_name(base.name + "_rinf.csv")
        write_vv_vh(decay, vv=vv, vh=vh)
        corrected = self.r_t - self.r_infty if np.isfinite(self.r_infty) else self.r_t.copy()
        np.savetxt(trace, np.column_stack((self.time_axis, self.r_t, corrected)),
                   header="channel\tr(t)\tr(t)-r_inf", comments="", delimiter="\t", fmt="%.10g")
        with info.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(("filename", "r_inf", "region_min", "region_max", "bg_vv", "bg_vh", "g_factor"))
            writer.writerow((Path(self.loaded_file).name, self.r_infty, self.region_min, self.region_max,
                             self.bg_vv, self.bg_vh, self.g_factor))
        self.message = f"Saved {decay.name}, {trace.name}, {info.name}"
        return decay, trace, info

    def snapshot(self):
        """The settings a batch run uses: what the main window shows when the batch window opens."""
        return {"apply_bg": self.apply_bg, "bg_vv": float(self.bg_vv), "bg_vh": float(self.bg_vh),
                "g": float(self.g_factor), "shift": float(self.shift), "flip": bool(self.flip),
                "region_min": float(self.region_min), "region_max": float(self.region_max)}

    def _batch_row(self, path, snap):
        """r-infinity of one file under *snap*: ``(name, r_inf, lo, hi, bg_vv, bg_vh, g, error)``."""
        lo, hi = snap["region_min"], snap["region_max"]
        scratch = AnisotropyModel()
        scratch.g_factor, scratch.apply_bg = snap["g"], snap["apply_bg"]
        scratch.bg_vv, scratch.bg_vh = snap["bg_vv"], snap["bg_vh"]
        scratch.flip, scratch.shift = snap["flip"], snap["shift"]
        try:
            scratch.load(path)
            last = float(len(scratch.time_axis) - 1)
            lo, hi = max(0.0, min(lo, last)), max(0.0, min(hi, last))
            if hi <= lo:
                hi = min(last, lo + 1.0)
            scratch.region_bounds = [lo, hi]
            scratch.compute()
            result, error = scratch.r_infty, ""
        except Exception as exc:
            result, error = float("nan"), str(exc)
            lo, hi = snap["region_min"], snap["region_max"]
        return (Path(path).name, result, lo, hi, snap["bg_vv"], snap["bg_vh"], snap["g"], error)

    def run_batch(self):
        """r-infinity for every queued file under the snapshot; a file that cannot be read is a row with its error."""
        if not self.batch_files:
            self.batch_results = []
            self.message = "No files to process."
            return []
        snap = self.batch_snapshot or self.snapshot()
        rows = [self._batch_row(path, snap) for path in self.batch_files]
        self.batch_results = rows
        failed = sum(1 for row in rows if row[-1])
        self.message = f"Processed {len(rows)} file(s)" + (f", {failed} failed." if failed else ".")
        return rows

    @property
    def batch_file_rows(self):
        return [{"path": path, "name": Path(path).name} for path in self.batch_files]

    @property
    def batch_result_rows(self):
        return [dict(zip(BATCH_COLUMNS, row)) for row in self.batch_results]

    def add_batch_paths(self, paths):
        """Queue .dat/.txt files, and the ones found in dropped folders; returns how many were new."""
        found = []
        for path in paths or []:
            p = Path(str(path))
            found.extend(sorted(q for q in p.rglob("*") if q.is_file()) if p.is_dir()
                         else [p] if p.is_file() else [])
        added = 0
        for p in found:
            if p.suffix.lower() in BATCH_EXTENSIONS and str(p) not in self.batch_files:
                self.batch_files.append(str(p))
                added += 1
        if added:
            self.message = f"Queued {added} file(s) for the batch."
        else:
            self.message = "Nothing to queue: choose .dat or .txt VV/VH files."
        return added

    def select_batch_file(self, record):
        """The file table's ``selected_call`` (``None`` clears the selection)."""
        self.selected_batch_file = record.get("path", "") if isinstance(record, dict) else ""

    def remove_selected(self, _record=None):
        """Take the selected file off the batch queue; results go when the queue empties (as the Qt list)."""
        path = self.selected_batch_file
        if path in self.batch_files:
            self.batch_files.remove(path)
        self.selected_batch_file = ""
        if not self.batch_files:
            self.batch_results = []

    def clear_batch(self):
        """Empty the batch queue and its results."""
        self.batch_files = []
        self.batch_results = []
        self.selected_batch_file = ""

    def save_batch(self, path):
        if not self.batch_results:
            raise ValueError("Run batch before saving CSV.")
        with Path(path).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(BATCH_COLUMNS)
            writer.writerows(self.batch_results)
        self.message = f"Saved {Path(path).name}"

    def export_settings(self):
        return {key: getattr(self, key) for key in (
            "g_factor", "apply_bg", "bg_vv", "bg_vh", "flip", "shift",
            "region_bounds", "loaded_file", "batch_files")}

    def restore_settings(self, state):
        for key in ("g_factor", "apply_bg", "bg_vv", "bg_vh", "flip", "shift", "batch_files"):
            if key in state:
                setattr(self, key, state[key])
        path = state.get("loaded_file")
        if path and Path(path).is_file():
            self.load(path)
        if "region_bounds" in state:
            self.region_bounds = list(map(float, state["region_bounds"]))
        self.compute()
