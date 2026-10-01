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


class AnisotropyModel:
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

    def load(self, path):
        vv, vh = _channels(path)
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
        lo, hi = self.region_bounds
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
            writer = csv.writer(stream)
            writer.writerow(("filename", "r_inf", "region_min", "region_max", "bg_vv", "bg_vh", "g_factor"))
            writer.writerow((Path(self.loaded_file).name, self.r_infty, *self.region_bounds,
                             self.bg_vv, self.bg_vh, self.g_factor))
        self.message = f"Saved {decay.name}, {trace.name}, {info.name}"
        return decay, trace, info

    def run_batch(self):
        original = (self.loaded_file, self.vv_raw, self.vh_raw, self.time_axis,
                    list(self.region_bounds), self.r_t, self.r_infty, self.message)
        bounds = list(self.region_bounds)
        rows = []
        for path in self.batch_files:
            try:
                vv, vh = _channels(path)
                self.vv_raw, self.vh_raw = vv, vh
                self.time_axis = np.arange(len(vv), dtype=float)
                lo = max(0.0, min(float(bounds[0]), float(len(vv) - 1)))
                hi = max(0.0, min(float(bounds[1]), float(len(vv) - 1)))
                if hi <= lo:
                    hi = min(float(len(vv) - 1), lo + 1.0)
                self.region_bounds = [lo, hi]
                self.compute()
                result = self.r_infty
                error = ""
            except Exception as exc:
                result, error = float("nan"), str(exc)
                lo, hi = bounds
            rows.append((Path(path).name, result, lo, hi, self.bg_vv,
                         self.bg_vh, self.g_factor, error))
        (self.loaded_file, self.vv_raw, self.vh_raw, self.time_axis,
         self.region_bounds, self.r_t, self.r_infty, self.message) = original
        self.batch_results = rows
        self.message = f"Processed {len(rows)} file(s)"
        return rows

    def save_batch(self, path):
        if not self.batch_results:
            raise ValueError("Run batch before saving CSV.")
        with Path(path).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(("filename", "r_inf", "region_min", "region_max", "bg_vv", "bg_vh", "g_factor", "error"))
            writer.writerows(self.batch_results)

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
