"""Toolkit-free G-factor, FP mixing, sample anisotropy and batch workflows."""

from __future__ import annotations

import csv
import json
from copy import deepcopy
from pathlib import Path

import numpy as np

from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.fio import read_vv_vh
from chisurf.core.fio.vv_vh import write_vv_vh

from ..core.calculations import (
    calculate_g_factor_core,
    compute_background_levels,
    compute_r_infinity,
    compute_rt,
    compute_steady_state_anisotropy,
    estimate_lifetime_first_moment,
    perrin_steady_state_anisotropy,
    shift_interp_on_axis,
    solve_linked_l_from_steady_state,
)


def _bound(index: int, attr: str) -> property:
    """Expose one region coordinate without copying the model's mutable list."""

    def get(model: GFactorModel) -> float:
        """Read the coordinate as the scalar form value."""
        return float(getattr(model, attr)[index])

    def put(model: GFactorModel, value: float) -> None:
        """Update the existing region list through the scalar form value."""
        getattr(model, attr)[index] = float(value)

    return property(get, put)


BATCH_EXTENSIONS = (".dat", ".txt", ".csv")
BATCH_COLUMNS = (
    "file",
    "r_inf",
    "region_start",
    "region_stop",
    "bg_vv",
    "bg_vh",
    "g_factor",
    "error",
)


class GFactorModel:
    """Unified VV/VH G-factor, polarization mixing (l1, l2) and anisotropy calculator."""

    def __init__(self):
        self.fast_file = ""
        self.slow_file = ""
        self.sample_file = ""
        self.fast = None
        self.slow = None
        self.sample = None
        self.region = [0.0, 100.0]
        self.background_region = [0.0, 100.0]
        self.sample_region = [0.0, 100.0]
        self.shift = 0.0
        self.background = False
        self.flip = False
        self.manual_g = False
        self.g_override = 1.0
        self.result = {}
        self.fp_dt_ns = 1.0
        self.fp_rho_ns = 16.0
        self.fp_r0 = 0.38
        self.manual_tau = False
        self.tau_override = 0.0
        self.manual_rs = False
        self.rs_override = 0.0
        self.manual_l = False
        self.link_l1_l2 = True
        self.l1_override = 0.0
        self.l2_override = 0.0
        self.fp_result = {}
        self.sample_r_t = None
        self.sample_r_infty = float("nan")
        self.sample_r_ss = float("nan")
        self.batch_files = []
        self.batch_results = []
        self.batch_open = False
        self.selected_batch_file = ""
        self.selected_batch_files = []
        self._selected_batch_records = []
        self.forget_selection = False
        self.decays = []
        self.selected_decay_idx = 0
        self.selected_reference_idx = 0
        self.message = ""
        self.busy = False

        self._init_fitting_parameters()

    def _init_fitting_parameters(self) -> None:
        self.parameters = FittingParameterGroup(name="VV/VH Calibration")
        self.param_g = FittingParameter(name="G", value=1.0, fixed=False)
        self.param_l1 = FittingParameter(name="l1", value=0.0, fixed=False)
        self.param_l2 = FittingParameter(name="l2", value=0.0, fixed=False)
        self.param_tau = FittingParameter(name="tau", value=4.0, fixed=True)
        self.param_rho = FittingParameter(name="rho", value=16.0, fixed=True)
        self.param_r0 = FittingParameter(name="r0", value=0.38, fixed=True)
        self.param_dt = FittingParameter(name="dt", value=0.05, fixed=True)
        self.param_tail_start = FittingParameter(name="Tail start", value=2000.0, fixed=True)
        self.param_tail_stop = FittingParameter(name="Tail stop", value=3000.0, fixed=True)
        self.param_bg_start = FittingParameter(name="BG start", value=50.0, fixed=True)
        self.param_bg_stop = FittingParameter(name="BG stop", value=200.0, fixed=True)
        self.param_shift = FittingParameter(name="VH shift", value=0.0, fixed=True)
        self.param_rs = FittingParameter(name="Target rS", value=0.3, fixed=True)

        self.parameters.g = self.param_g
        self.parameters.l1 = self.param_l1
        self.parameters.l2 = self.param_l2
        self.parameters.tau = self.param_tau
        self.parameters.rho = self.param_rho
        self.parameters.r0 = self.param_r0
        self.parameters.dt = self.param_dt
        self.parameters.tail_start = self.param_tail_start
        self.parameters.tail_stop = self.param_tail_stop
        self.parameters.bg_start = self.param_bg_start
        self.parameters.bg_stop = self.param_bg_stop
        self.parameters.shift = self.param_shift
        self.parameters.rs = self.param_rs

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        skipped = {
            "parameters",
            "param_g",
            "param_l1",
            "param_l2",
            "param_tail_start",
            "param_tail_stop",
            "param_bg_start",
            "param_bg_stop",
            "param_shift",
            "param_dt",
            "param_r0",
            "param_tau",
            "param_rho",
            "param_rs",
            "_on_used",
        }
        for k, v in self.__dict__.items():
            if k in skipped:
                continue
            setattr(result, k, deepcopy(v, memo))
        result._on_used = getattr(self, "_on_used", None)
        result._init_fitting_parameters()
        result.update_fitting_parameters()
        return result

    def update_fitting_parameters(self) -> None:
        """Synchronize model state into live FittingParameter objects."""
        if not hasattr(self, "parameters"):
            return
        # G factor
        if self.manual_g:
            self.param_g.value = float(self.g_override)
            self.param_g.fixed = True
            self.param_g.error_estimate = float("nan")
        else:
            self.param_g.value = float(self.g_factor) if self.g_factor is not None else 1.0
            self.param_g.fixed = False
            g_std = self.g_factor_std
            self.param_g.error_estimate = float(g_std) if (g_std is not None and np.isfinite(g_std)) else float("nan")

        # Polarization mixing l1, l2
        l1_val = self.l1
        l2_val = self.l2
        l_sd = self.fp_result.get("l_sd") if self.fp_result else None
        self.param_l1.value = float(l1_val) if (l1_val is not None and np.isfinite(l1_val)) else 0.0
        self.param_l1.fixed = bool(self.manual_l)
        self.param_l1.error_estimate = float(l_sd) if (l_sd is not None and np.isfinite(l_sd) and not self.manual_l) else float("nan")

        self.param_l2.value = float(l2_val) if (l2_val is not None and np.isfinite(l2_val)) else 0.0
        self.param_l2.fixed = bool(self.manual_l)
        self.param_l2.error_estimate = float(l_sd) if (l_sd is not None and np.isfinite(l_sd) and not self.manual_l) else float("nan")

        # Lifetime tau
        if self.manual_tau:
            self.param_tau.value = float(self.tau_override)
            self.param_tau.fixed = True
        else:
            self.param_tau.value = float(self.fp_result.get("tau_used_ns", self.tau_override))
            self.param_tau.fixed = False

        # Steady-state anisotropy rS
        self.param_rs.value = float(self.fp_result.get("r_expected", self.rs_override))
        self.param_rs.fixed = bool(self.manual_rs)

        # Regions and setup
        self.param_tail_start.value = float(self.tail_start)
        self.param_tail_stop.value = float(self.tail_stop)
        self.param_bg_start.value = float(self.background_start)
        self.param_bg_stop.value = float(self.background_stop)
        self.param_shift.value = float(self.shift)
        self.param_dt.value = float(self.fp_dt_ns)
        self.param_r0.value = float(self.fp_r0)
        self.param_rho.value = float(self.fp_rho_ns)

    def snapshot(self):
        return deepcopy(self)

    # -- scalar views of the region lists, for the form ----------------------------------------- #
    tail_start = _bound(0, "region")
    tail_stop = _bound(1, "region")
    background_start = _bound(0, "background_region")
    background_stop = _bound(1, "background_region")
    sample_region_start = _bound(0, "sample_region")
    sample_region_stop = _bound(1, "sample_region")

    # -- compatibility properties for legacy anisotropy callers --------------------------------- #
    @property
    def region_bounds(self) -> list[float]:
        return self.sample_region if self.sample is not None else self.region

    @region_bounds.setter
    def region_bounds(self, val: list[float] | tuple[float, float]) -> None:
        bounds = [float(val[0]), float(val[1])]
        self.sample_region = list(bounds)
        if self.fast is None and self.sample is not None:
            self.region = list(bounds)

    @property
    def region_start(self) -> float:
        return float(self.region_bounds[0])

    @region_start.setter
    def region_start(self, val: float) -> None:
        self.region_bounds[0] = float(val)

    @property
    def region_end(self) -> float:
        return float(self.region_bounds[1])

    @region_end.setter
    def region_end(self, val: float) -> None:
        self.region_bounds[1] = float(val)

    @property
    def region_min(self) -> float:
        return min(self.region_bounds)

    @property
    def region_max(self) -> float:
        return max(self.region_bounds)

    @property
    def loaded_file(self) -> str:
        return self.sample_file or self.fast_file

    @loaded_file.setter
    def loaded_file(self, val: str) -> None:
        self.sample_file = str(val)

    @property
    def r_t(self) -> np.ndarray | None:
        if self.sample_r_t is not None:
            return self.sample_r_t
        if self.fast is not None:
            series = self.decay_series(slow=False)
            return series.get("r_corrected") if series else None
        return None

    @r_t.setter
    def r_t(self, val: np.ndarray | None) -> None:
        self.sample_r_t = val

    @property
    def r_infty(self) -> float:
        if np.isfinite(self.sample_r_infty):
            return self.sample_r_infty
        if self.fast is not None:
            r = self.r_t
            if r is not None:
                return compute_r_infinity(np.arange(len(r), dtype=float), r, self.region)
        return float("nan")

    @r_infty.setter
    def r_infty(self, val: float) -> None:
        self.sample_r_infty = float(val)

    @property
    def r_infty_text(self) -> str:
        val = self.r_infty
        return f"{val:.5f}" if np.isfinite(val) else "N/A"

    @property
    def sample_r_infty_text(self) -> str:
        val = self.sample_r_infty
        return f"{val:.5f}" if np.isfinite(val) else "N/A"

    @property
    def sample_r_ss_text(self) -> str:
        val = self.sample_r_ss
        return f"{val:.5f}" if np.isfinite(val) else "N/A"

    @property
    def apply_bg(self) -> bool:
        return self.background

    @apply_bg.setter
    def apply_bg(self, val: bool) -> None:
        self.background = bool(val)

    @property
    def bg_vv(self) -> float:
        if self.background and self.result:
            return float(self.result.get("bg_parallel_avg", 0.0))
        return 0.0

    @bg_vv.setter
    def bg_vv(self, val: float) -> None:
        pass

    @property
    def bg_vh(self) -> float:
        if self.background and self.result:
            return float(self.result.get("bg_perpendicular_avg", 0.0))
        return 0.0

    @bg_vh.setter
    def bg_vh(self, val: float) -> None:
        pass

    @property
    def has_data(self) -> bool:
        return self.sample is not None or self.fast is not None

    @property
    def has_sample_data(self) -> bool:
        return self.sample is not None

    @property
    def has_batch_files(self) -> bool:
        return bool(self.batch_files)

    @property
    def has_batch_results(self) -> bool:
        return bool(self.batch_results)

    @property
    def batch_file_rows(self) -> list[dict[str, str]]:
        return [{"path": p, "name": Path(p).name} for p in self.batch_files]

    @property
    def batch_result_rows(self) -> list[dict[str, object]]:
        return self.batch_rows()

    # -- G and mixing properties ---------------------------------------------------------------- #
    @property
    def g_factor(self) -> float | None:
        return float(self.g_override) if self.manual_g else self.result.get("g_factor")

    @g_factor.setter
    def g_factor(self, value: float) -> None:
        self.manual_g = True
        self.g_override = float(value)

    @property
    def g_factor_std(self) -> float | None:
        key = "g_factor_stddev_corrected" if self.background else "g_factor_stddev_uncorrected"
        val = self.result.get(key)
        return float(val) if val is not None and np.isfinite(val) else None

    @property
    def l_override(self) -> float:
        return float(self.l1_override)

    @l_override.setter
    def l_override(self, val: float) -> None:
        self.l1_override = float(val)
        if self.link_l1_l2:
            self.l2_override = float(val)

    @property
    def l1(self) -> float:
        if self.manual_l:
            return float(self.l1_override)
        val = self.fp_result.get("l1")
        return float(val) if val is not None and np.isfinite(val) else 0.0

    @property
    def l2(self) -> float:
        if self.manual_l:
            return float(self.l2_override if not self.link_l1_l2 else self.l1_override)
        val = self.fp_result.get("l2")
        return float(val) if val is not None and np.isfinite(val) else 0.0

    @property
    def applied_g_text(self) -> str:
        return f"{self.g_factor:.5f}" if self.g_factor is not None else "1.00000"

    @property
    def applied_l1_text(self) -> str:
        return f"{self.l1:.5f}" if self.l1 is not None and np.isfinite(self.l1) else "0.00000"

    @property
    def applied_l2_text(self) -> str:
        return f"{self.l2:.5f}" if self.l2 is not None and np.isfinite(self.l2) else "0.00000"

    def enabled(self, name: str) -> bool:
        """Whether the control *name* means something now (no idle controls)."""
        if self.busy:
            return False
        if name in ("background_start", "background_stop"):
            return self.background
        if name in ("g_override",):
            return self.manual_g
        if name == "tau_override":
            return self.manual_tau
        if name == "rs_override":
            return self.manual_rs
        if name in ("l_override", "l1_override", "link_l1_l2"):
            return self.manual_l
        if name == "l2_override":
            return self.manual_l and not self.link_l1_l2
        if (
            name
            in (
                "tail_start",
                "tail_stop",
                "shift",
                "flip",
                "background",
                "manual_g",
                "manual_tau",
                "manual_rs",
                "manual_l",
            )
            and self.fast is None
        ):
            return False
        if name in ("fp_dt_ns", "fp_rho_ns", "fp_r0"):
            return self.slow is not None
        if name in ("sample_region_start", "sample_region_stop"):
            return self.sample is not None or self.fast is not None
        return True

    def remove_batch(self, record: dict | None = None) -> None:
        """Drop the queued file of *record* (and its result row)."""
        path = (record or {}).get("path") or (record or {}).get("file")
        if path:
            if path in self.batch_files:
                self.batch_files.remove(path)
            else:
                for f in list(self.batch_files):
                    if Path(f).name == path or f == path:
                        self.batch_files.remove(f)
            self.batch_results = [
                r for r in self.batch_results
                if r.get("file") != path and Path(r.get("file", "")).name != Path(path).name
            ]

    def clear_batch(self) -> None:
        """Empty the batch queue and results."""
        self.batch_files = []
        self.batch_results = []

    @property
    def has_batch_rows(self) -> bool:
        return bool(self.batch_files) or bool(self.batch_results)

    def open_batch(self) -> None:
        """Open the modal batch window."""
        self.batch_open = True

    def close_batch(self) -> None:
        """Close the modal batch window."""
        self.batch_open = False

    def request_save_batch(self) -> None:
        self.request = "save_batch"

    def set_decay_role(self, index: int, role: str) -> None:
        """Assign role ('fast', 'slow', 'sample') to decay at index."""
        if not 0 <= index < len(self.decays):
            return
        d = self.decays[index]
        d["role"] = role
        if role == "fast":
            self.fast = d["data"]
            self.fast_file = d["path"]
            self.compute()
        elif role == "slow":
            self.slow = d["data"]
            self.slow_file = d["path"]
            self.fp_rho_ns = float(d.get("rho_ns", 16.0))
            if d.get("tau_ns") is not None:
                self.manual_tau = True
                self.tau_override = float(d["tau_ns"])
            if self.fast is not None:
                self.compute()
        elif role == "sample":
            self.sample = d["data"]
            self.sample_file = d["path"]
            self.sample_region = list(d.get("region", self.region))
            self.compute_sample()

    def set_decay_rho(self, index: int, rho_ns: float) -> None:
        """Update rotational correlation time for decay at index."""
        if not 0 <= index < len(self.decays):
            return
        d = self.decays[index]
        d["rho_ns"] = float(rho_ns)
        if d["role"] == "slow" or d["path"] == self.slow_file:
            self.fp_rho_ns = float(rho_ns)
            if self.fast is not None:
                self.estimate_mixing()

    def set_decay_tau(self, index: int, tau_ns: float) -> None:
        """Update lifetime for decay at index."""
        if not 0 <= index < len(self.decays):
            return
        d = self.decays[index]
        d["tau_ns"] = float(tau_ns)
        if d["role"] == "slow" or d["path"] == self.slow_file:
            self.manual_tau = True
            self.tau_override = float(tau_ns)
            if self.fast is not None:
                self.estimate_mixing()

    def remove_decay(self, index: int) -> None:
        """Remove decay at index from multi-decay manager."""
        if not 0 <= index < len(self.decays):
            return
        d = self.decays.pop(index)
        if self.fast_file == d["path"]:
            self.fast = None
            self.fast_file = ""
        if self.slow_file == d["path"]:
            self.slow = None
            self.slow_file = ""
        if self.sample_file == d["path"]:
            self.sample = None
            self.sample_file = ""
            self.sample_r_t = None
            self.sample_r_infty = float("nan")
            self.sample_r_ss = float("nan")

    def reference_rows(self) -> list[dict[str, object]]:
        """The loaded reference standard decays as table rows."""
        rows = []
        ref_decays = [d for d in self.decays if d.get("role") != "sample"]
        for i, d in enumerate(ref_decays):
            rho = d.get("rho_ns")
            tau = d.get("tau_ns") or d.get("tau_estimate_ns")
            r0 = d.get("r0", self.fp_r0)
            target_rs = d.get("r_expected")
            l_est = d.get("l_estimate")
            bg_vv = d.get("bg_vv", 0.0)
            bg_vh = d.get("bg_vh", 0.0)
            is_g = d.get("use_for_g", False) or (self.fast_file == d.get("path"))
            rows.append({
                "index": i,
                "file": Path(d.get("path", d.get("name", ""))).name,
                "path": str(d.get("path", "")),
                "rho_ns": round(float(rho), 2) if rho is not None else 0.2,
                "tau_ns": round(float(tau), 2) if tau is not None else 4.0,
                "r0": round(float(r0), 3) if r0 is not None else 0.38,
                "bg_vv": round(float(bg_vv), 2) if bg_vv is not None else 0.0,
                "bg_vh": round(float(bg_vh), 2) if bg_vh is not None else 0.0,
                "tail_match": bool(is_g),
                "r_expected": f"{float(target_rs):.4f}" if target_rs is not None and np.isfinite(target_rs) else "",
                "l_estimate": f"{float(l_est):.4f}" if l_est is not None and np.isfinite(l_est) else "",
            })
        return rows

    def set_reference_tail_match(self, index: int) -> None:
        """Assign reference at index as the tail-matching standard for G-factor calibration."""
        ref_decays = [d for d in self.decays if d.get("role") != "sample"]
        if not 0 <= index < len(ref_decays):
            return
        target = ref_decays[index]
        for d in self.decays:
            if d.get("role") != "sample":
                d["use_for_g"] = (d == target)
                if d == target:
                    d["role"] = "fast"
                elif d["role"] == "fast":
                    d["role"] = "slow"
        self.fast = target["data"]
        self.fast_file = target["path"]
        self.compute()

    def remove_reference(self, record: dict | None = None) -> None:
        """Drop the reference file in record, or the currently selected reference."""
        path = (record or {}).get("path")
        if not path and hasattr(self, "selected_reference_idx"):
            ref_decays = [d for d in self.decays if d.get("role") != "sample"]
            if 0 <= self.selected_reference_idx < len(ref_decays):
                path = ref_decays[self.selected_reference_idx].get("path")
        idx = next((i for i, d in enumerate(self.decays) if d.get("path") == path), None)
        if idx is not None:
            self.remove_decay(idx)

    def clear_references(self, *args, **kwargs) -> None:
        """Clear all reference standard decays from list."""
        self.decays = [d for d in self.decays if d.get("role") == "sample"]
        self.fast = None
        self.fast_file = None
        self.slow = None
        self.slow_file = None
        self.result = {}
        self.fp_result = {}
        self.message = "All reference standards cleared."
        self.update_fitting_parameters()

    def set_tail_match_from_menu(self, record: dict | None = None, *args, **kwargs) -> None:
        """Set the clicked reference as the tail matching standard."""
        if not record:
            return
        idx = record.get("index")
        if idx is not None:
            self.set_reference_tail_match(int(idx))

    @property
    def has_references(self) -> bool:
        return any(d.get("role") != "sample" for d in self.decays)

    def select_reference(self, record: dict | None = None) -> None:
        """Set the active reference standard from table selection."""
        if not record:
            return
        path = record.get("path")
        ref_decays = [d for d in self.decays if d.get("role") != "sample"]
        idx = next((i for i, d in enumerate(ref_decays) if d.get("path") == path), None)
        if idx is not None:
            self.selected_reference_idx = idx

    @property
    def selected_batch_records(self) -> list[dict]:
        return getattr(self, "_selected_batch_records", [])

    @selected_batch_records.setter
    def selected_batch_records(self, records: list[dict] | None) -> None:
        self._selected_batch_records = records or []
        if self._selected_batch_records:
            paths = []
            for r in self._selected_batch_records:
                p = r.get("path") or r.get("file")
                if p:
                    full = next((f for f in self.batch_files if f == p or Path(f).name == Path(p).name), p)
                    paths.append(str(full))
            self.selected_batch_files = paths
            if paths:
                self.selected_batch_file = paths[0]
                self.select_batch(self._selected_batch_records[0])

    def select_batch(self, record: dict | None = None) -> None:
        """Set the active batch sample decay from table selection."""
        if not record:
            return
        path = record.get("path") or record.get("file")
        if not path:
            return
        full_path = next((f for f in self.batch_files if f == path or Path(f).name == Path(path).name), path)
        self.selected_batch_file = str(full_path)
        if str(full_path) not in self.selected_batch_files:
            self.selected_batch_files = [str(full_path)]
        self.sample_file = str(full_path)
        if Path(full_path).is_file():
            try:
                vv, vh = read_vv_vh(str(full_path), split=True)
                vv = np.asarray(vv, dtype=float)
                vh = np.asarray(vh, dtype=float)
                n = min(len(vv), len(vh))
                self.sample = (vv[:n], vh[:n])
                self.sample_region = list(self.region)
                self.compute_sample()
            except Exception:
                pass


    def edit_reference(self, record: dict | None, key: str, value: Any) -> None:
        """Handle in-place editing of reference standard table cells."""
        if not record:
            return
        path = record.get("path")
        d = next((item for item in self.decays if item.get("path") == path), None)
        if not d:
            return
        try:
            if key == "rho_ns":
                new_rho = float(value)
                if new_rho > 0:
                    d["rho_ns"] = new_rho
                    if d.get("role") == "slow" or d.get("path") == self.slow_file:
                        self.fp_rho_ns = new_rho
                    if self.fast is not None:
                        self.compute()
            elif key == "tau_ns":
                new_tau = float(value)
                if new_tau > 0:
                    d["tau_ns"] = new_tau
                    if d.get("role") == "slow" or d.get("path") == self.slow_file:
                        self.manual_tau = True
                        self.tau_override = new_tau
                    if self.fast is not None:
                        self.compute()
            elif key == "r0":
                new_r0 = min(0.4, max(-0.2, float(value)))
                d["r0"] = new_r0
                if d.get("role") == "slow" or d.get("path") == self.slow_file:
                    self.fp_r0 = new_r0
                if self.fast is not None:
                    self.compute()
            elif key in ("bg_vv", "bg_vh"):
                d[key] = float(value)
                if self.fast is not None:
                    self.compute()
            elif key in ("r_expected", "rs_override"):
                new_rs = float(value)
                d["r_expected"] = new_rs
                self.manual_rs = True
                self.rs_override = new_rs
                if self.fast is not None:
                    self.compute()
            elif key == "tail_match":
                bool_val = bool(value) if isinstance(value, bool) else (str(value).strip().lower() in ("true", "1", "yes", "★ yes"))
                if bool_val:
                    ref_decays = [x for x in self.decays if x.get("role") != "sample"]
                    idx = next((i for i, x in enumerate(ref_decays) if x.get("path") == path), None)
                    if idx is not None:
                        self.set_reference_tail_match(idx)
        except (ValueError, TypeError):
            pass

    def parameter_rows(self) -> list[dict[str, object]]:
        """The instrumental calibration parameters as standard fitting parameter table rows."""
        self.update_fitting_parameters()
        rows = [
            {
                "key": "g",
                "parameter": "G",
                "name": "G",
                "value": float(self.param_g.value),
                "fixed": bool(self.param_g.fixed),
                "error": f"± {self.param_g.error_estimate:.4g}" if (self.param_g.error_estimate is not None and np.isfinite(self.param_g.error_estimate)) else "",
                "_parameter": self.param_g,
            },
            {
                "key": "l1",
                "parameter": "l1",
                "name": "l1",
                "value": float(self.param_l1.value),
                "fixed": bool(self.param_l1.fixed),
                "error": f"± {self.param_l1.error_estimate:.4g}" if (self.param_l1.error_estimate is not None and np.isfinite(self.param_l1.error_estimate)) else "",
                "_parameter": self.param_l1,
            },
            {
                "key": "l2",
                "parameter": "l2",
                "name": "l2",
                "value": float(self.param_l2.value),
                "fixed": bool(self.param_l2.fixed),
                "error": f"± {self.param_l2.error_estimate:.4g}" if (self.param_l2.error_estimate is not None and np.isfinite(self.param_l2.error_estimate)) else "",
                "_parameter": self.param_l2,
            },
            {
                "key": "fp_dt_ns",
                "parameter": "dt",
                "name": "dt",
                "value": float(self.param_dt.value),
                "fixed": True,
                "error": "",
                "_parameter": self.param_dt,
            },
            {
                "key": "tail_start",
                "parameter": "Tail start",
                "name": "Tail start",
                "value": float(self.param_tail_start.value),
                "fixed": True,
                "error": "",
                "_parameter": self.param_tail_start,
            },
            {
                "key": "tail_stop",
                "parameter": "Tail stop",
                "name": "Tail stop",
                "value": float(self.param_tail_stop.value),
                "fixed": True,
                "error": "",
                "_parameter": self.param_tail_stop,
            },
            {
                "key": "background_start",
                "parameter": "BG start",
                "name": "BG start",
                "value": float(self.param_bg_start.value),
                "fixed": True,
                "error": "",
                "_parameter": self.param_bg_start,
            },
            {
                "key": "background_stop",
                "parameter": "BG stop",
                "name": "BG stop",
                "value": float(self.param_bg_stop.value),
                "fixed": True,
                "error": "",
                "_parameter": self.param_bg_stop,
            },
            {
                "key": "shift",
                "parameter": "Shift",
                "name": "Shift",
                "value": float(self.param_shift.value),
                "fixed": True,
                "error": "",
                "_parameter": self.param_shift,
            },
            {
                "key": "background",
                "parameter": "BG sub",
                "name": "BG sub",
                "value": bool(self.background),
                "fixed": True,
                "error": "",
                "_parameter": None,
            },
            {
                "key": "flip",
                "parameter": "Flip",
                "name": "Flip",
                "value": bool(self.flip),
                "fixed": True,
                "error": "",
                "_parameter": None,
            },
        ]
        return rows

    def edit_parameter(self, record: dict | None, key: str, value: Any) -> None:
        """Update calibration parameter from table edit."""
        if not record:
            return
        param_key = record.get("key")
        if not param_key:
            return
        try:
            if key == "fixed":
                val = bool(value) if isinstance(value, bool) else (str(value).strip().lower() in ("true", "1", "yes", "t"))
                if param_key in ("g", "g_override"):
                    self.manual_g = val
                elif param_key in ("l1", "l2", "l_override", "manual_l"):
                    self.manual_l = val
                elif param_key in ("tau_override", "manual_tau"):
                    self.manual_tau = val
                elif param_key in ("rs_override", "manual_rs"):
                    self.manual_rs = val
                if self.fast is not None:
                    self.compute()
                elif self.sample is not None:
                    self.compute_sample()
                return

            if key != "value":
                return

            if param_key in ("g", "g_override"):
                float_val = max(0.001, float(value))
                self.manual_g = True
                self.g_override = float_val
            elif param_key == "l1":
                self.manual_l = True
                self.l1_override = max(0.0, float(value))
                if self.link_l1_l2:
                    self.l2_override = self.l1_override
            elif param_key == "l2":
                self.manual_l = True
                self.l2_override = max(0.0, float(value))
            elif param_key in ("background", "flip", "manual_g", "manual_tau", "manual_rs", "manual_l", "link_l1_l2"):
                bool_val = bool(value) if isinstance(value, bool) else (str(value).strip().lower() in ("true", "1", "yes", "t"))
                setattr(self, param_key, bool_val)
            else:
                float_val = float(value)
                if param_key == "fp_r0":
                    float_val = min(0.4, max(-0.2, float_val))
                setattr(self, param_key, float_val)
                if param_key == "fp_rho_ns":
                    for d in self.decays:
                        if d.get("role") == "slow" or d.get("path") == self.slow_file:
                            d["rho_ns"] = float_val
                elif param_key == "tau_override":
                    self.manual_tau = True
                    for d in self.decays:
                        if d.get("role") == "slow" or d.get("path") == self.slow_file:
                            d["tau_ns"] = float_val
                elif param_key == "rs_override":
                    self.manual_rs = True
                elif param_key == "fp_r0":
                    for d in self.decays:
                        if d.get("role") == "slow" or d.get("path") == self.slow_file:
                            d["r0"] = float_val
            if self.fast is not None:
                self.compute()
            elif self.sample is not None:
                self.compute_sample()
            if hasattr(self, "_on_used") and callable(self._on_used):
                self._on_used(param_key)
        except (ValueError, TypeError):
            pass

    def result_rows(self) -> list[dict[str, str]]:
        """The G-factor and mixing results as ``{quantity, value, tooltip}`` rows."""
        rows = []
        g_raw = self.result.get("g_factor_uncorrected")
        g_raw_sd = self.result.get("g_factor_stddev_uncorrected")
        if g_raw is not None:
            raw_val = f"{float(g_raw):.5f}"
            if g_raw_sd is not None and np.isfinite(g_raw_sd):
                raw_val += f" ± {float(g_raw_sd):.5f}"
            rows.append({
                "quantity": "G raw",
                "value": raw_val,
                "tooltip": "Detector sensitivity ratio VV/VH without background subtraction (mean ± SD).",
            })
        if self.background:
            g_corr = self.result.get("g_factor_corrected")
            g_corr_sd = self.result.get("g_factor_stddev_corrected")
            if g_corr is not None:
                corr_val = f"{float(g_corr):.5f}"
                if g_corr_sd is not None and np.isfinite(g_corr_sd):
                    corr_val += f" ± {float(g_corr_sd):.5f}"
                rows.append({
                    "quantity": "G corrected",
                    "value": corr_val,
                    "tooltip": "Detector sensitivity ratio VV/VH after subtracting pre-pulse background (mean ± SD).",
                })
            rows.append({
                "quantity": "Background VV",
                "value": f"{float(self.result.get('bg_parallel_avg', 0.0)):.5g}",
                "tooltip": "Mean background counts per bin in parallel channel.",
            })
            rows.append({
                "quantity": "Background VH",
                "value": f"{float(self.result.get('bg_perpendicular_avg', 0.0)):.5g}",
                "tooltip": "Mean background counts per bin in perpendicular channel.",
            })
        if self.manual_g:
            rows.append({
                "quantity": "G used (manual)",
                "value": f"{float(self.g_override):.5f}",
                "tooltip": "Manual override of the detector G-factor.",
            })
        if self.l1 is not None and np.isfinite(self.l1):
            l_sd = self.fp_result.get("l_sd") if self.fp_result else None
            l1_val = f"{float(self.l1):.5f}"
            if l_sd is not None and np.isfinite(l_sd) and not self.manual_l:
                l1_val += f" ± {float(l_sd):.5f}"
            l2_val = f"{float(self.l2):.5f}"
            if l_sd is not None and np.isfinite(l_sd) and not self.manual_l:
                l2_val += f" ± {float(l_sd):.5f}"
            mix_tip = (
                f"Polarization mixing factor l1 = {float(self.l1):.5g}. "
                f"Fit-free estimate from Perrin relation "
                f"(tau = {self.fp_result.get('tau_used_ns', 0):.2f} ns, target rS = {self.fp_result.get('r_expected', 0):.3f})."
                if self.fp_result
                else "Polarization mixing factor (objective depolarization correction)."
            )
            rows.append({
                "quantity": "l1",
                "value": l1_val,
                "tooltip": mix_tip,
            })
            rows.append({
                "quantity": "l2",
                "value": l2_val,
                "tooltip": mix_tip,
            })
        return rows

    def mixing_rows(self) -> list[dict[str, str]]:
        rows = []
        for label, key in (
            ("Lifetime estimate (ns)", "tau_estimate_ns"),
            ("Lifetime used (ns)", "tau_used_ns"),
            ("Expected steady anisotropy", "r_expected"),
            ("Linked l1", "l1"),
            ("Linked l2", "l2"),
        ):
            value = self.fp_result.get(key) if self.fp_result else None
            rows.append(
                {"quantity": label, "value": f"{float(value):.6g}" if value is not None else "none"}
            )
        if self.manual_l:
            rows.append({"quantity": "Manual l1", "value": f"{float(self.l1):.6g}"})
            rows.append({"quantity": "Manual l2", "value": f"{float(self.l2):.6g}"})
        rows.append({"quantity": "Applied l1", "value": f"{float(self.l1):.6g}"})
        rows.append({"quantity": "Applied l2", "value": f"{float(self.l2):.6g}"})
        return rows

    def batch_rows(self) -> list[dict[str, object]]:
        done = {r["file"]: r for r in self.batch_results}
        rows = []
        for path in self.batch_files:
            r = done.get(path, {})
            r_ss = r.get("r_ss")
            r_inf = r.get("r_inf")
            reg = ""
            if "region_start" in r and "region_stop" in r:
                reg = f"{r['region_start']}-{r['region_stop']}"
            elif "region_min" in r and "region_max" in r:
                reg = f"{r['region_min']:.1f}-{r['region_max']:.1f}"
            rows.append(
                {
                    "file": Path(path).name,
                    "filename": Path(path).name,
                    "path": path,
                    "r_ss": f"{r_ss:.5f}" if (r_ss is not None and np.isfinite(r_ss)) else ("" if not r else "failed"),
                    "r_inf": f"{r_inf:.5g}" if (r_inf is not None and np.isfinite(r_inf)) else ("" if not r else "failed"),
                    "region": reg,
                    "region_min": r.get("region_start", r.get("region_min", 0.0)),
                    "region_max": r.get("region_stop", r.get("region_max", 0.0)),
                    "g_factor": f"{r['g_factor']:.5g}" if r.get("g_factor") is not None else "",
                    "l1": f"{r['l1']:.4g}" if r.get("l1") is not None else "",
                    "l2": f"{r['l2']:.4g}" if r.get("l2") is not None else "",
                    "bg_vv": f"{r['bg_vv']:.6g}" if r.get("bg_vv") is not None else "",
                    "bg_vh": f"{r['bg_vh']:.6g}" if r.get("bg_vh") is not None else "",
                    "error": r.get("error", ""),
                }
            )
        return rows

    def load(
        self,
        path: str | Path,
        slow: bool = False,
        sample: bool = False,
        role: str | None = None,
        rho_ns: float | None = None,
        tau_ns: float | None = None,
    ) -> None:
        """Load a VV/VH file into the requested slot (fast reference, slow reference, or sample)."""
        vv, vh = read_vv_vh(str(path), split=True)
        vv = np.asarray(vv, dtype=float)
        vh = np.asarray(vh, dtype=float)
        n = min(len(vv), len(vh))
        if n < 3 or not np.all(np.isfinite(vv[:n])) or not np.all(np.isfinite(vh[:n])):
            raise ValueError("VV/VH input requires at least three finite bins in each channel.")

        if role is None:
            role = "sample" if sample else ("slow" if slow else "fast")

        decay_rho = float(rho_ns) if rho_ns is not None else (self.fp_rho_ns if role == "slow" else 0.2)
        decay_tau = float(tau_ns) if tau_ns is not None else (self.tau_override if self.manual_tau else 4.0)

        entry = next((d for d in self.decays if d["path"] == str(path)), None)
        is_first_ref = not any(d.get("role") != "sample" for d in self.decays)
        use_g = (role == "fast") or (is_first_ref and role != "sample")
        if entry is None:
            entry = {
                "name": Path(path).name,
                "path": str(path),
                "data": (vv[:n], vh[:n]),
                "role": role,
                "use_for_g": use_g,
                "rho_ns": decay_rho,
                "tau_ns": decay_tau,
                "r0": float(self.fp_r0),
                "dt_ns": float(self.fp_dt_ns),
                "region": [float(int(n * 0.7)), float(min(n - 1, int(n * 0.9)))],
            }
            self.decays.append(entry)
        else:
            entry["data"] = (vv[:n], vh[:n])
            entry["role"] = role
            entry["use_for_g"] = use_g
            if rho_ns is not None:
                entry["rho_ns"] = decay_rho
            if tau_ns is not None:
                entry["tau_ns"] = decay_tau

        if role == "sample":
            self.sample = (vv[:n], vh[:n])
            self.sample_file = str(path)
            self.sample_region = [float(int(n * 0.7)), float(min(n - 1, int(n * 0.9)))]
            self.compute_sample()
            self.message = f"Loaded sample {Path(path).name}: {n} channels"
        elif role == "slow":
            self.slow = (vv[:n], vh[:n])
            self.slow_file = str(path)
            if rho_ns is not None:
                self.fp_rho_ns = float(rho_ns)
            if tau_ns is not None:
                self.manual_tau = True
                self.tau_override = float(tau_ns)
            if self.fast is not None:
                self.compute()
            else:
                self.message = "Loaded slow reference; load a fast reference to determine G."
        else:
            self.fast = (vv[:n], vh[:n])
            self.fast_file = str(path)
            self.region = [float(int(n * 0.7)), float(min(n - 1, int(n * 0.9)))]
            self.background_region = [float(int(n * 0.05)), float(int(n * 0.15))]
            self.compute()

    def load_file(self, path: str | Path) -> bool:
        """Unified loader for sample VV/VH decay (and fallback fast reference)."""
        self.load(path, sample=True)
        if self.fast is None:
            self.fast = self.sample
            self.fast_file = str(path)
            n = len(self.fast[0])
            self.region = [float(int(n * 0.7)), float(min(n - 1, int(n * 0.9)))]
            self.background_region = [float(int(n * 0.05)), float(int(n * 0.15))]
            try:
                self.compute()
            except Exception:
                pass
        return True

    def load_reference(
        self,
        path: str | Path,
        rho_ns: float | None = None,
        tau_ns: float | None = None,
        r0: float | None = None,
        use_for_g: bool | None = None,
    ) -> None:
        """Load a reference standard decay into the calibration table."""
        existing_refs = [d for d in self.decays if d.get("role") != "sample"]
        if rho_ns is None:
            rho_val = 0.2 if not existing_refs else self.fp_rho_ns
        else:
            rho_val = float(rho_ns)

        if use_for_g is None:
            use_for_g = not existing_refs or rho_val < min(d.get("rho_ns", 1e9) for d in existing_refs)

        role = "fast" if use_for_g else "slow"
        self.load(path, role=role, rho_ns=rho_val, tau_ns=tau_ns)
        entry = next((d for d in self.decays if d["path"] == str(path)), None)
        if entry:
            entry["use_for_g"] = bool(use_for_g)
            if r0 is not None:
                entry["r0"] = float(r0)
        if use_for_g and entry:
            self.fast_file = str(path)
            self.fast = entry["data"]
            self.compute()

    def load_example(self, folder: str | Path | None = None, client: object | None = None) -> None:
        """Load simulated references (known G = 1.2) for demonstrations and testing."""
        from ..demo import DEMO, make_demo

        files = make_demo(folder)
        self.fp_dt_ns = float(DEMO["dt_ns"])
        self.fp_r0 = float(DEMO["r0"])
        self.fp_rho_ns = float(dict((k, rho) for k, rho, _ in DEMO["decays"])["slow"])
        self.manual_tau, self.tau_override = True, float(DEMO["tau_ns"])
        self.background = True
        self.link_l1_l2 = False
        self.load(files["fast"], role="fast", rho_ns=0.2, tau_ns=float(DEMO["tau_ns"]))
        self.region = [200.0, 350.0]
        self.compute()
        self.load(files["batch1"], role="slow", rho_ns=float(DEMO["decays"][2][1]), tau_ns=float(DEMO["tau_ns"]))
        self.load(files["batch2"], role="slow", rho_ns=float(DEMO["decays"][3][1]), tau_ns=float(DEMO["tau_ns"]))
        self.load(files["slow"], role="slow", rho_ns=float(DEMO["decays"][1][1]), tau_ns=float(DEMO["tau_ns"]))
        if "batch1" in files:
            self.load(files["batch1"], role="sample")
        else:
            self.load(files["fast"], role="sample")
        for key in ("batch1", "batch2"):
            if str(files[key]) not in self.batch_files:
                self.batch_files.append(str(files[key]))
        if client is not None:
            self.compute(client)
        self.message = f"Example loaded (simulated, true G = {DEMO['g_factor']}, l1 = {DEMO.get('l1', 0.0)}, l2 = {DEMO.get('l2', 0.0)}): {self.message}"

    def channels(
        self, slow: bool = False, sample: bool = False, entry: dict | None = None
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        if entry is not None:
            pair = entry.get("data")
        elif sample:
            pair = self.sample
        elif slow:
            pair = self.slow
        else:
            pair = self.fast
        if pair is None:
            return None, None
        return pair[::-1] if self.flip else pair

    def compute(self, client: object | None = None) -> None:
        """Calculate G-factor from fast reference and polarization mixing from slow reference."""
        if self.fast is None:
            if self.sample is not None:
                self.fast = self.sample
                self.fast_file = self.sample_file
                n = len(self.fast[0])
                self.region = [float(int(n * 0.7)), float(min(n - 1, int(n * 0.9)))]
                self.background_region = [float(int(n * 0.05)), float(int(n * 0.15))]
            else:
                raise ValueError("Load the fast-rotating reference dye VV/VH decay first.")
        par, perp = self.channels()
        self.region = sorted(map(float, self.region))
        self.background_region = sorted(map(float, self.background_region))
        params = dict(
            parallel_data=par,
            perpendicular_data=perp,
            region_bounds=self.region,
            decay_shift=self.shift,
            use_bg=self.background,
            bg_region_bounds=self.background_region,
            flip=False,
        )
        if client:
            params["parallel_data"] = par.tolist()
            params["perpendicular_data"] = perp.tolist()
            self.result = client.calculate(**params)
        else:
            self.result = calculate_g_factor_core(**params)
        fast_bp = float(self.result.get("bg_parallel_avg", 0.0))
        fast_bs = float(self.result.get("bg_perpendicular_avg", 0.0))
        for d in self.decays:
            if d.get("role") == "fast" or d.get("path") == self.fast_file:
                d["bg_vv"] = fast_bp
                d["bg_vh"] = fast_bs
        if self.manual_g and (not np.isfinite(self.g_override) or self.g_override <= 0):
            raise ValueError("Manual G-factor must be positive and finite.")
        self.estimate_mixing(client)
        self.compute_sample()
        self.message = (
            f"G = {self.g_factor:.6g}"
            if self.g_factor is not None
            else "Tail matching did not produce a finite G-factor."
        )

    def recompute(self, _value: object = None) -> None:
        """Callback for view spec changes."""
        self.compute()

    def recompute_sample(self, _value: object = None) -> None:
        self.compute_sample()

    def estimate_mixing(self, client: object | None = None) -> None:
        """Estimate linked l1=l2 mixing parameter from slow reference(s) and Perrin relation."""
        g = self.g_factor
        self.fp_result = {}
        if g is None or not np.isfinite(g) or g <= 0:
            return

        slow_entries = [d for d in self.decays if d.get("role") == "slow"]
        if not slow_entries and self.slow is not None:
            slow_entries = [{
                "data": self.slow,
                "rho_ns": float(self.fp_rho_ns),
                "tau_ns": float(self.tau_override) if self.manual_tau else None,
                "name": Path(self.slow_file).name if self.slow_file else "slow",
            }]
        if not slow_entries:
            return

        estimates = []
        tau_ests = []
        taus_used = []
        r_expecteds = []

        for entry in slow_entries:
            pair = entry.get("data")
            if pair is None:
                continue
            par_e, perp_e = pair[::-1] if self.flip else pair
            n_e = min(len(par_e), len(perp_e))
            if n_e < 3:
                continue
            time_e = np.arange(n_e, dtype=float)
            shifted_e = time_e + self.shift
            interp_e = np.interp(time_e, shifted_e, perp_e, left=0.0, right=0.0)
            bp_e, bs_e = compute_background_levels(par_e, perp_e, time_e, shifted_e, self.background_region)
            entry["bg_vv"] = float(bp_e)
            entry["bg_vh"] = float(bs_e)
            if not self.background:
                bp_e, bs_e = (0.0, 0.0)
            p_e = np.clip(par_e[:n_e] - bp_e, 0, None)
            s_e = np.clip(interp_e[:n_e] - bs_e, 0, None)
            t_est = estimate_lifetime_first_moment(time_e, p_e + 2 * g * s_e) * self.fp_dt_ns
            if self.manual_tau:
                tau_e = self.tau_override
            elif len(slow_entries) > 1 and entry.get("tau_ns") is not None:
                tau_e = entry["tau_ns"]
            else:
                tau_e = t_est

            if len(slow_entries) == 1:
                rho_e = self.fp_rho_ns
                r0_e = self.fp_r0
            else:
                rho_e = entry.get("rho_ns") if entry.get("rho_ns") is not None else self.fp_rho_ns
                r0_e = entry.get("r0") if entry.get("r0") is not None else self.fp_r0

            exp_e = (
                client.perrin_steady_state(tau_ns=tau_e, rho_ns=rho_e, r0=r0_e)
                if client
                else perrin_steady_state_anisotropy(tau_ns=tau_e, rho_ns=rho_e, r0=r0_e)
            )
            if self.manual_rs and len(slow_entries) == 1:
                exp_e = self.rs_override
            l_val = (
                client.solve_linked_l(
                    sp=float(p_e.sum()), ss=float(s_e.sum()), g_factor=g, r_target=exp_e
                )
                if client
                else solve_linked_l_from_steady_state(
                    sp=float(p_e.sum()), ss=float(s_e.sum()), g_factor=g, r_target=exp_e
                )
            )
            entry["l_estimate"] = float(l_val) if np.isfinite(l_val) else None
            entry["r_expected"] = float(exp_e) if np.isfinite(exp_e) else None
            entry["tau_estimate_ns"] = float(t_est)
            tau_ests.append(float(t_est))
            taus_used.append(float(tau_e))
            r_expecteds.append(float(exp_e))
            estimates.append((l_val, float(p_e.sum()), float(s_e.sum()), float(exp_e)))

        # Also compute Perrin target and l for all other reference standards so table is complete
        for d in self.decays:
            if d.get("role") != "sample" and d not in slow_entries:
                pair = d.get("data")
                if pair is None:
                    continue
                par_d, perp_d = pair[::-1] if self.flip else pair
                n_d = min(len(par_d), len(perp_d))
                if n_d < 3:
                    continue
                time_d = np.arange(n_d, dtype=float)
                shifted_d = time_d + self.shift
                interp_d = np.interp(time_d, shifted_d, perp_d, left=0.0, right=0.0)
                bp_d, bs_d = compute_background_levels(par_d, perp_d, time_d, shifted_d, self.background_region)
                d["bg_vv"] = float(bp_d)
                d["bg_vh"] = float(bs_d)
                if not self.background:
                    bp_d, bs_d = (0.0, 0.0)
                p_d = np.clip(par_d[:n_d] - bp_d, 0, None)
                s_d = np.clip(interp_d[:n_d] - bs_d, 0, None)
                t_est_d = estimate_lifetime_first_moment(time_d, p_d + 2 * g * s_d) * self.fp_dt_ns
                tau_d = d.get("tau_ns") or t_est_d
                rho_d = d.get("rho_ns", 0.2)
                r0_d = d.get("r0", self.fp_r0)
                exp_d = perrin_steady_state_anisotropy(tau_ns=tau_d, rho_ns=rho_d, r0=r0_d)
                l_val_d = solve_linked_l_from_steady_state(
                    sp=float(p_d.sum()), ss=float(s_d.sum()), g_factor=g, r_target=exp_d
                )
                d["l_estimate"] = float(l_val_d) if np.isfinite(l_val_d) else None
                d["r_expected"] = float(exp_d) if np.isfinite(exp_d) else None
                d["tau_estimate_ns"] = float(t_est_d)

        if not estimates:
            return

        if len(slow_entries) == 1:
            l, sp_val, ss_val, expected = estimates[0]
            tau_est = tau_ests[0]
            tau = taus_used[0]
        else:
            valid_ls = [e[0] for e in estimates if np.isfinite(e[0]) and 0 <= e[0] <= 0.5]
            l = float(np.mean(valid_ls)) if valid_ls else estimates[0][0]
            sp_val = float(np.mean([e[1] for e in estimates]))
            ss_val = float(np.mean([e[2] for e in estimates]))
            expected = float(np.mean(r_expecteds))
            tau_est = float(np.mean(tau_ests))
            tau = float(np.mean(taus_used))

        if self.manual_rs and len(slow_entries) == 1:
            expected = self.rs_override
        elif np.isfinite(expected):
            self.rs_override = float(expected)
        if not self.manual_tau and np.isfinite(tau_est):
            self.tau_override = float(tau_est)

        warning = "One steady-state observable determines only the linked estimate l1 = l2."
        l1_val: float | None = None
        l2_val: float | None = None

        if not self.link_l1_l2 and len(slow_entries) >= 2:
            A_sys, b_sys = [], []
            for entry in slow_entries:
                pair = entry.get("data")
                if pair is None:
                    continue
                par_e, perp_e = pair[::-1] if self.flip else pair
                n_e = min(len(par_e), len(perp_e))
                time_e = np.arange(n_e, dtype=float)
                shifted_e = time_e + self.shift
                interp_e = np.interp(time_e, shifted_e, perp_e, left=0.0, right=0.0)
                bp_e, bs_e = (
                    compute_background_levels(par_e, perp_e, time_e, shifted_e, self.background_region)
                    if self.background
                    else (0.0, 0.0)
                )
                p_e = np.clip(par_e[:n_e] - bp_e, 0, None)
                s_e = np.clip(interp_e[:n_e] - bs_e, 0, None)
                sp_e = float(p_e.sum())
                ss_e = float(s_e.sum())
                rho_e = entry.get("rho_ns", self.fp_rho_ns)
                tau_e = entry.get("tau_ns") or self.tau_override
                r0_e = entry.get("r0", self.fp_r0)
                r_e = perrin_steady_state_anisotropy(tau_ns=tau_e, rho_ns=rho_e, r0=r0_e)
                if r_e > 0 and sp_e > 0 and ss_e > 0:
                    row = [g * ss_e, sp_e]
                    val = (1.0 / 3.0) * (sp_e + 2.0 * g * ss_e - (sp_e - g * ss_e) / r_e)
                    norm = row[0] + row[1]
                    if norm > 0:
                        A_sys.append([row[0] / norm, row[1] / norm])
                        b_sys.append(val / norm)
            if len(A_sys) >= 2:
                sol, _, _, _ = np.linalg.lstsq(A_sys, b_sys, rcond=None)
                if 0 <= sol[0] <= 0.5 and 0 <= sol[1] <= 0.5:
                    l1_val = float(sol[0])
                    l2_val = float(sol[1])
                    l = float((sol[0] + sol[1]) / 2.0)
                    self.l1_override = l1_val
                    self.l2_override = l2_val
                    self.l_override = l
                    warning = f"Estimated independent mixing factors l1 = {l1_val:.4f}, l2 = {l2_val:.4f}."

        if self.manual_l:
            l = self.l_override
            l1_val = float(self.l1_override)
            l2_val = float(self.l2_override if not self.link_l1_l2 else self.l1_override)
            warning = "Manual linked l1/l2 override is active."
        elif l1_val is None or l2_val is None:
            if not np.isfinite(l) or not 0 <= l <= 0.5:
                warning = (
                    f"Linked mixing estimate {l:g} is outside the physical [0, 0.5] range; not applied."
                )
                l = np.nan
                l1_val = None
                l2_val = None
            else:
                self.l_override = float(l)
                self.l1_override = float(l)
                self.l2_override = float(l)
                l1_val = float(l)
                l2_val = float(l)

        l_sd = None
        if l1_val is not None and np.isfinite(l1_val) and 0 <= l1_val <= 0.5:
            if len(slow_entries) > 1 and len(valid_ls) > 1:
                l_sd = float(np.std(valid_ls, ddof=1) / np.sqrt(len(valid_ls)))
            elif sp_val > 0 and ss_val > 0 and expected > 0:
                u = sp_val
                v = g * ss_val
                denom = 3.0 * (u + v) ** 2
                if denom > 0:
                    scale = (1.0 + 2.0 / expected) / denom
                    dl_du = -v * scale
                    dl_dv = u * scale
                    var_l = (dl_du ** 2) * sp_val + (dl_dv ** 2) * (g ** 2) * ss_val
                    l_sd = float(np.sqrt(max(var_l, 0.0)))

        self.fp_result = {
            "tau_estimate_ns": float(tau_est),
            "tau_used_ns": float(tau),
            "r_expected": float(expected),
            "l1": l1_val,
            "l2": l2_val,
            "l_sd": l_sd,
            "warning": warning,
        }

    def compute_sample(self) -> None:
        """Compute time-resolved anisotropy r(t), r-infinity and r(SS) for the sample decay."""
        if self.sample is None:
            if self.fast is not None:
                self.sample = self.fast
                self.sample_file = self.fast_file
                self.sample_region = list(self.region)
            else:
                self.sample_r_t, self.sample_r_infty = None, float("nan")
                self.sample_r_ss = float("nan")
                return
        par, perp = self.channels(sample=True)
        if par is None:
            self.sample_r_t, self.sample_r_infty = None, float("nan")
            self.sample_r_ss = float("nan")
            return
        n = min(len(par), len(perp))
        time = np.arange(n, dtype=float)
        shifted = time + self.shift
        bp, bs = (
            compute_background_levels(par, perp, time, shifted, self.background_region)
            if self.background
            else (0.0, 0.0)
        )
        p = np.maximum(par[:n] - bp, 0.0)
        s = np.maximum(perp[:n] - bs, 0.0)
        corrected_perp = shift_interp_on_axis(time, s, self.shift)
        g = self.g_factor
        g_val = float(g) if (g is not None and np.isfinite(g) and g > 0) else np.nan
        r_t = compute_rt(p, corrected_perp, g_val, l1=self.l1, l2=self.l2)
        self.sample_r_t = r_t
        self.sample_r_infty = compute_r_infinity(time, r_t, self.sample_region)
        sp = float(np.sum(p))
        valid_s = corrected_perp[np.isfinite(corrected_perp)]
        ss = float(np.sum(np.maximum(valid_s, 0.0)))
        self.sample_r_ss = compute_steady_state_anisotropy(sp, ss, g_val, l1=self.l1, l2=self.l2)

    def decay_series(
        self, slow: bool = False, sample: bool = False, entry: dict | None = None
    ) -> dict[str, np.ndarray]:
        """Produce plotted vectors for the decays and time-resolved anisotropy."""
        par, perp = self.channels(slow=slow, sample=sample, entry=entry)
        if par is None:
            return {}
        time = np.arange(len(par), dtype=float)
        shifted = time + self.shift
        bg = (
            compute_background_levels(par, perp, time, shifted, self.background_region)
            if self.background
            else (0.0, 0.0)
        )
        p = np.maximum(par - bg[0], 0.0)
        s = np.maximum(perp - bg[1], 0.0)
        g = self.g_factor
        g_val = float(g) if g is not None and np.isfinite(g) and g > 0 else np.nan
        l1 = self.l1
        l2 = self.l2
        corrected = shift_interp_on_axis(time, s, self.shift)
        with np.errstate(divide="ignore", invalid="ignore"):
            raw_shifted_vh = shift_interp_on_axis(time, perp, self.shift) if len(perp) == len(time) else perp
            ratio_raw = np.where(raw_shifted_vh > 0, par / raw_shifted_vh, np.nan)
            ratio_corr = np.where(corrected > 0, p / corrected, np.nan)
        return {
            "time": time,
            "shifted_time": shifted,
            "vv_raw": par,
            "vh_raw": perp,
            "vv_corrected": p,
            "vh_corrected": s * g_val,
            "ratio_raw": np.clip(ratio_raw, -1.0, 50.0),
            "ratio_corrected": np.clip(ratio_corr, -1.0, 50.0),
            "r_raw": np.clip(
                compute_rt(par, perp, self.result.get("g_factor_uncorrected") or g_val), -0.5, 1.5
            ),
            "r_corrected": np.clip(compute_rt(p, corrected, g_val, l1=l1, l2=l2), -0.5, 1.5),
        }

    def batch_snapshot(self) -> dict[str, object]:
        g = self.g_factor
        if g is None or not np.isfinite(g) or g <= 0:
            raise ValueError("Determine G before applying batch anisotropy analysis.")
        bp, bs = (0.0, 0.0)
        par, perp = self.channels()
        if par is not None:
            time = np.arange(len(par), dtype=float)
            bp, bs = compute_background_levels(par, perp, time, time + self.shift, self.background_region)
        region = list(self.sample_region if self.sample is not None else self.region)
        return {
            "g_factor": float(g),
            "l1": float(self.l1),
            "l2": float(self.l2),
            "shift": self.shift,
            "flip": self.flip,
            "background": self.background,
            "background_levels": (bp, bs),
            "region": region,
        }

    def compute_batch(self, cancel_cb: object | None = None) -> list[dict]:
        params = self.batch_snapshot()
        rows = []
        for filename in self.batch_files:
            if cancel_cb and cancel_cb():
                raise RuntimeError("Batch stopped between decay files.")
            try:
                par, perp = read_vv_vh(filename, split=True)
                par = np.asarray(par, float)
                perp = np.asarray(perp, float)
                if params["flip"]:
                    par, perp = perp, par
                n = min(len(par), len(perp))
                time = np.arange(n, dtype=float)
                bp, bs = params["background_levels"] if params["background"] else (0.0, 0.0)
                p = np.maximum(par[:n] - bp, 0.0)
                s = np.maximum(perp[:n] - bs, 0.0)
                shifted_perp = shift_interp_on_axis(time, s, params["shift"])
                anisotropy = compute_rt(
                    p,
                    shifted_perp,
                    params["g_factor"],
                    l1=params["l1"],
                    l2=params["l2"],
                )
                start, stop = sorted(params["region"])
                start = max(0, min(n - 1, int(round(start))))
                stop = max(start + 1, min(n, int(round(stop))))
                values = anisotropy[start:stop]
                values = values[np.isfinite(values)]
                r_inf = float(np.mean(values)) if len(values) else None

                sp = float(np.sum(p))
                valid_s = shifted_perp[np.isfinite(shifted_perp)]
                ss = float(np.sum(np.maximum(valid_s, 0.0)))
                r_ss = compute_steady_state_anisotropy(
                    sp=sp,
                    ss=ss,
                    g_factor=params["g_factor"],
                    l1=params["l1"],
                    l2=params["l2"],
                )

                rows.append(
                    {
                        "file": filename,
                        "r_ss": r_ss if np.isfinite(r_ss) else None,
                        "r_inf": r_inf,
                        "region_start": start,
                        "region_stop": stop,
                        "region_min": float(start),
                        "region_max": float(stop),
                        "bg_vv": bp,
                        "bg_vh": bs,
                        "g_factor": params["g_factor"],
                        "l1": params["l1"],
                        "l2": params["l2"],
                        "error": "",
                    }
                )
            except Exception as exc:
                rows.append({"file": filename, "r_ss": None, "r_inf": None, "error": str(exc)})
        self.batch_results = rows
        self.message = f"Processed {len(rows)} batch decays."
        return rows

    run_batch = compute_batch

    def export_batch(self, path: str | Path) -> None:
        if not self.batch_results:
            raise ValueError("Run batch analysis before exporting.")
        columns = [
            "file",
            "r_ss",
            "r_inf",
            "region_start",
            "region_stop",
            "bg_vv",
            "bg_vh",
            "g_factor",
            "l1",
            "l2",
            "error",
        ]
        with Path(path).open("w") as stream:
            stream.write("\t".join(columns) + "\n")
            for row in self.batch_results:
                stream.write(
                    "\t".join(
                        str(row.get(key, "") if row.get(key) is not None else "nan")
                        for key in columns
                    )
                    + "\n"
                )
        self.message = f"Saved {Path(path).name}"

    def export_batch_csv(self, path: str | Path) -> None:
        """Export all summary columns (including G, l1, l2) to a CSV file."""
        if not self.batch_results:
            raise ValueError("Run batch analysis before exporting.")
        columns = [
            "file",
            "r_ss",
            "r_inf",
            "region_start",
            "region_stop",
            "g_factor",
            "l1",
            "l2",
            "bg_vv",
            "bg_vh",
            "error",
        ]
        with Path(path).open("w") as stream:
            stream.write(",".join(columns) + "\n")
            for row in self.batch_results:
                stream.write(
                    ",".join(
                        str(row.get(key, "") if row.get(key) is not None else "")
                        for key in columns
                    )
                    + "\n"
                )
        self.message = f"Saved CSV to {Path(path).name}"

    save_batch = export_batch

    def get_decay_series(self, file_path: str | Path | None = None) -> dict[str, np.ndarray]:
        """Compute plotted vectors for a specific file or active sample."""
        target = str(file_path) if file_path else (self.selected_batch_file or (self.batch_files[0] if self.batch_files else None))
        if target and Path(target).is_file():
            par, perp = read_vv_vh(target, split=True)
            par = np.asarray(par, dtype=float)
            perp = np.asarray(perp, dtype=float)
            if self.flip:
                par, perp = perp, par
            n = min(len(par), len(perp))
            time = np.arange(n, dtype=float)
            shifted = time + self.shift
            bp, bs = (
                compute_background_levels(par, perp, time, shifted, self.background_region)
                if self.background
                else (0.0, 0.0)
            )
            p = np.maximum(par[:n] - bp, 0.0)
            s = np.maximum(perp[:n] - bs, 0.0)
            g = self.g_factor
            g_val = float(g) if g is not None and np.isfinite(g) and g > 0 else np.nan
            corrected = shift_interp_on_axis(time, s, self.shift)
            with np.errstate(divide="ignore", invalid="ignore"):
                raw_shifted_vh = shift_interp_on_axis(time, perp[:n], self.shift) if len(perp) >= n else perp[:n]
                ratio_raw = np.where(raw_shifted_vh > 0, par[:n] / raw_shifted_vh, np.nan)
                ratio_corr = np.where(corrected > 0, p / corrected, np.nan)
            return {
                "time": time,
                "shifted_time": shifted,
                "vv_raw": par[:n],
                "vh_raw": perp[:n],
                "vv_corrected": p,
                "vh_corrected": s * g_val,
                "ratio_raw": np.clip(ratio_raw, -1.0, 50.0),
                "ratio_corrected": np.clip(ratio_corr, -1.0, 50.0),
                "r_raw": np.clip(
                    compute_rt(par[:n], perp[:n], self.result.get("g_factor_uncorrected") or g_val),
                    -0.5,
                    1.5,
                ),
                "r_corrected": np.clip(compute_rt(p, corrected, g_val, l1=self.l1, l2=self.l2), -0.5, 1.5),
            }
        return self.decay_series()

    def export_active_decay(self, target_path: str | Path, file_path: str | Path | None = None) -> None:
        """Export time, raw VV, raw VH, corrected VV, and corrected VH to a CSV file."""
        series = self.get_decay_series(file_path=file_path)
        if not series or "time" not in series:
            raise ValueError("No decay data available to export.")
        columns = ["time", "vv_raw", "vh_raw", "vv_corrected", "vh_corrected"]
        with Path(target_path).open("w") as f:
            f.write(",".join(columns) + "\n")
            for t, vr, hr, vc, hc in zip(
                series["time"],
                series["vv_raw"],
                series["vh_raw"],
                series["vv_corrected"],
                series["vh_corrected"],
            ):
                f.write(f"{t:.4f},{vr:.2f},{hr:.2f},{vc:.2f},{hc:.2f}\n")
        self.message = f"Exported decays to {Path(target_path).name}"

    def export_active_rt(self, target_path: str | Path, file_path: str | Path | None = None) -> None:
        """Export time, raw r(t), and corrected r(t) to a CSV file."""
        series = self.get_decay_series(file_path=file_path)
        if not series or "time" not in series:
            raise ValueError("No anisotropy data available to export.")
        columns = ["time", "r_raw", "r_corrected"]
        with Path(target_path).open("w") as f:
            f.write(",".join(columns) + "\n")
            for t, rr, rc in zip(series["time"], series["r_raw"], series["r_corrected"]):
                f.write(f"{t:.4f},{rr:.6f},{rc:.6f}\n")
        self.message = f"Exported anisotropy r(t) to {Path(target_path).name}"

    def export_active_ratio(self, target_path: str | Path, file_path: str | Path | None = None) -> None:
        """Export time, raw VV/VH ratio, and corrected VV/VH ratio to a CSV file."""
        series = self.get_decay_series(file_path=file_path)
        if not series or "time" not in series:
            raise ValueError("No ratio data available to export.")
        columns = ["time", "ratio_raw", "ratio_corrected"]
        with Path(target_path).open("w") as f:
            f.write(",".join(columns) + "\n")
            for t, rr, rc in zip(series["time"], series.get("ratio_raw", []), series.get("ratio_corrected", [])):
                f.write(f"{t:.4f},{rr:.6f},{rc:.6f}\n")
        self.message = f"Exported VV/VH ratio to {Path(target_path).name}"

    def export_all_rt(self, target_path: str | Path) -> None:
        """Export time-resolved anisotropy r(t) curves for all queued batch files into a CSV."""
        if not self.batch_files:
            raise ValueError("No unknown files queued.")
        g = self.g_factor
        if g is None or not np.isfinite(g) or g <= 0:
            raise ValueError("Determine G before exporting anisotropy.")
        all_curves = {}
        max_len = 0
        for path in self.batch_files:
            try:
                par, perp = read_vv_vh(path, split=True)
                par = np.asarray(par, float)
                perp = np.asarray(perp, float)
                if self.flip:
                    par, perp = perp, par
                n = min(len(par), len(perp))
                time = np.arange(n, dtype=float)
                bp, bs = (
                    compute_background_levels(par, perp, time, time + self.shift, self.background_region)
                    if self.background
                    else (0.0, 0.0)
                )
                p = np.maximum(par[:n] - bp, 0.0)
                s = np.maximum(perp[:n] - bs, 0.0)
                r_corr = compute_rt(
                    p,
                    shift_interp_on_axis(time, s, self.shift),
                    float(g),
                    l1=self.l1,
                    l2=self.l2,
                )
                all_curves[Path(path).name] = r_corr
                max_len = max(max_len, n)
            except Exception:
                pass
        if not all_curves:
            raise ValueError("Could not compute anisotropy for queued files.")
        headers = ["time_ns"] + list(all_curves.keys())
        time = np.arange(max_len, dtype=float) * self.fp_dt_ns
        with Path(target_path).open("w") as f:
            f.write(",".join(headers) + "\n")
            for i in range(max_len):
                row = [f"{time[i]:.4f}"]
                for name, curve in all_curves.items():
                    val = f"{curve[i]:.6f}" if i < len(curve) and np.isfinite(curve[i]) else "nan"
                    row.append(val)
                f.write(",".join(row) + "\n")
        self.message = f"Exported {len(all_curves)} anisotropy curves to {Path(target_path).name}"

    def add_batch_paths(self, paths: list[str | Path]) -> int:
        """Queue .dat/.txt/.csv files and folders recursively into the batch."""
        found = []
        for path in paths or []:
            p = Path(str(path))
            found.extend(
                sorted(q for q in p.rglob("*") if q.is_file())
                if p.is_dir()
                else [p]
                if p.is_file()
                else []
            )
        added = 0
        for p in found:
            if p.suffix.lower() in BATCH_EXTENSIONS and str(p) not in self.batch_files:
                self.batch_files.append(str(p))
                added += 1
        if added:
            self.message = f"Queued {added} file(s) for the batch."
        else:
            self.message = "Nothing to queue: choose .dat, .txt or .csv VV/VH files."
        return added

    def save_sample_outputs(self, base_path: str | Path) -> tuple[Path, Path, Path]:
        """Save shifted decays, anisotropy trace, and summary CSV."""
        if self.sample is None and self.fast is None:
            raise ValueError("Load a VV/VH decay file before saving outputs.")
        if self.sample is None:
            self.sample = self.fast
            self.sample_file = self.fast_file
            self.sample_region = list(self.region)
        self.compute_sample()
        base = Path(base_path).with_suffix("")
        par, perp = self.channels(sample=True)
        time = np.arange(len(par), dtype=float)
        shifted = time + self.shift
        bp, bs = (
            compute_background_levels(par, perp, time, shifted, self.background_region)
            if self.background
            else (0.0, 0.0)
        )
        p = np.maximum(par - bp, 0.0)
        s = np.maximum(perp - bs, 0.0)
        vh_shifted = shift_interp_on_axis(time, s, self.shift)
        p = np.where(np.isfinite(p) & (p > 0), p, 0.0)
        vh_shifted = np.where(np.isfinite(vh_shifted) & (vh_shifted > 0), vh_shifted, 0.0)

        decay_file = base.with_name(base.name + "_shifted.dat")
        trace_file = base.with_name(base.name + "_anisotropy.txt")
        info_file = base.with_name(base.name + "_rinf.csv")

        write_vv_vh(decay_file, vv=p, vh=vh_shifted)
        r_t = self.sample_r_t
        r_inf = self.sample_r_infty
        corrected = r_t - r_inf if (r_t is not None and np.isfinite(r_inf)) else (r_t.copy() if r_t is not None else np.zeros_like(time))
        np.savetxt(
            trace_file,
            np.column_stack((time, r_t if r_t is not None else np.zeros_like(time), corrected)),
            header="channel\tr(t)\tr(t)-r_inf",
            comments="",
            delimiter="\t",
            fmt="%.10g",
        )
        with info_file.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(
                ("filename", "r_ss", "r_inf", "region_min", "region_max", "bg_vv", "bg_vh", "g_factor", "l1", "l2")
            )
            writer.writerow(
                (
                    Path(self.sample_file).name,
                    self.sample_r_ss,
                    r_inf,
                    min(self.sample_region),
                    max(self.sample_region),
                    bp,
                    bs,
                    self.g_factor,
                    self.l1,
                    self.l2,
                )
            )
        self.message = f"Saved {decay_file.name}, {trace_file.name}, {info_file.name}"
        return decay_file, trace_file, info_file

    save = save_sample_outputs

    def archive_parameters(self) -> dict[str, object]:
        if self.g_factor is None:
            raise ValueError("Determine a G-factor before archival.")
        return {
            "g_factor": self.g_factor,
            "g_factor_stddev": self.result.get(
                "g_factor_stddev_corrected" if self.background else "g_factor_stddev_uncorrected"
            ),
            "l1": self.l1,
            "l2": self.l2,
            "decay_shift": self.shift,
            "use_bg": self.background,
            "flip": self.flip,
            "region_min": min(self.region),
            "region_max": max(self.region),
            "bg_region_min": min(self.background_region),
            "bg_region_max": max(self.background_region),
            "fp_file_path": self.slow_file,
            "fp_dt_ns": self.fp_dt_ns,
            "fp_rho_ns": self.fp_rho_ns,
            "fp_r0": self.fp_r0,
            "fp_tau_ns": self.fp_result.get("tau_used_ns"),
            "fp_r_s_expected": self.fp_result.get("r_expected"),
        }

    def detector_parameters(
        self, prior_l1: float = 0.0, prior_l2: float = 0.0, micro_time_resolution: float | None = None
    ) -> dict[str, object]:
        """Return the measured calibration plus detector-context mixing fallbacks."""
        parameters = self.archive_parameters()
        parameters["l1"] = float(self.l1) if np.isfinite(self.l1) else float(prior_l1)
        parameters["l2"] = float(self.l2) if np.isfinite(self.l2) else float(prior_l2)
        parameters.update(
            g_factor_uncorrected=self.result.get("g_factor_uncorrected"),
            g_factor_corrected=self.result.get("g_factor_corrected"),
            bg_vv=self.result.get("bg_parallel_avg", 0.0) if self.background else 0.0,
            bg_vh=self.result.get("bg_perpendicular_avg", 0.0) if self.background else 0.0,
            bg_region_bounds=list(self.background_region),
            micro_time_resolution=micro_time_resolution,
        )
        return parameters

    def export_settings(self) -> dict[str, object]:
        names = (
            "fast_file",
            "slow_file",
            "sample_file",
            "region",
            "background_region",
            "sample_region",
            "shift",
            "background",
            "flip",
            "manual_g",
            "g_override",
            "fp_dt_ns",
            "fp_rho_ns",
            "fp_r0",
            "manual_tau",
            "tau_override",
            "manual_rs",
            "rs_override",
            "manual_l",
            "link_l1_l2",
            "l1_override",
            "l2_override",
            "batch_files",
        )
        out = {name: deepcopy(getattr(self, name)) for name in names}
        out["batch_open"] = self.batch_open
        out["decays"] = [
            {
                "name": d["name"],
                "path": d["path"],
                "role": d["role"],
                "rho_ns": d["rho_ns"],
                "tau_ns": d["tau_ns"],
                "r0": d["r0"],
                "dt_ns": d["dt_ns"],
                "region": d["region"],
            }
            for d in self.decays
        ]
        return out

    def restore_settings(self, state: dict[str, object]) -> None:
        for name, value in state.items():
            if name in self.export_settings():
                setattr(self, name, deepcopy(value))
        if "batch_open" in state:
            self.batch_open = bool(state["batch_open"])

    def save_results(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(
                {
                    "settings": self.export_settings(),
                    "g_result": self.result,
                    "fp_result": self.fp_result,
                    "sample": {
                        "file": self.sample_file,
                        "r_ss": self.sample_r_ss,
                        "r_inf": self.sample_r_infty,
                        "region": self.sample_region,
                        "l1": self.l1,
                        "l2": self.l2,
                        "g": self.g_factor,
                    },
                },
                indent=2,
            )
        )
