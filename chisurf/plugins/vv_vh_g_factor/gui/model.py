"""Toolkit-free G-factor, FP mixing and anisotropy batch workflows."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import numpy as np

from chisurf.core.fio import read_vv_vh

from ..core.calculations import (
    calculate_g_factor_core,
    compute_background_levels,
    compute_rt,
    estimate_lifetime_first_moment,
    perrin_steady_state_anisotropy,
    shift_interp_on_axis,
    solve_linked_l_from_steady_state,
)


class GFactorModel:
    def __init__(self):
        self.fast_file = ""
        self.slow_file = ""
        self.fast = None
        self.slow = None
        self.region = [0.0, 100.0]
        self.background_region = [0.0, 100.0]
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
        self.l_override = 0.0
        self.fp_result = {}
        self.batch_files = []
        self.batch_results = []
        self.message = ""

    def snapshot(self):
        return deepcopy(self)

    def load(self, path, slow=False):
        vv, vh = read_vv_vh(str(path), split=True)
        vv = np.asarray(vv, dtype=float)
        vh = np.asarray(vh, dtype=float)
        n = min(len(vv), len(vh))
        if n < 3 or not np.all(np.isfinite(vv[:n])) or not np.all(np.isfinite(vh[:n])):
            raise ValueError("VV/VH input requires at least three finite bins in each channel.")
        if slow:
            self.slow = (vv[:n], vh[:n])
            self.slow_file = str(path)
        else:
            self.fast = (vv[:n], vh[:n])
            self.fast_file = str(path)
            self.region = [float(int(n * 0.7)), float(min(n - 1, int(n * 0.9)))]
            self.background_region = [float(int(n * 0.05)), float(int(n * 0.15))]
        if self.fast is not None:
            self.compute()
        else:
            self.message = "Loaded slow reference; load a fast reference to determine G."

    @property
    def g_factor(self):
        return float(self.g_override) if self.manual_g else self.result.get("g_factor")

    def channels(self, slow=False):
        channels = self.slow if slow else self.fast
        if channels is None:
            return None, None
        return channels[::-1] if self.flip else channels

    def compute(self, client=None):
        if self.fast is None:
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
        if self.manual_g and (not np.isfinite(self.g_override) or self.g_override <= 0):
            raise ValueError("Manual G-factor must be positive and finite.")
        self.estimate_mixing(client)
        self.message = (
            f"G = {self.g_factor:.6g}"
            if self.g_factor is not None
            else "Tail matching did not produce a finite G-factor."
        )

    def estimate_mixing(self, client=None):
        par, perp = self.channels(slow=True)
        self.fp_result = {}
        g = self.g_factor
        if par is None or g is None or not np.isfinite(g) or g <= 0:
            return
        n = min(len(par), len(perp))
        time = np.arange(n, dtype=float)
        shifted = time + self.shift
        interp = np.interp(time, shifted, perp, left=0.0, right=0.0)
        bp, bs = (
            compute_background_levels(par, perp, time, shifted, self.background_region)
            if self.background
            else (0.0, 0.0)
        )
        p = np.clip(par - bp, 0, None)
        s = np.clip(interp - bs, 0, None)
        tau_est = estimate_lifetime_first_moment(time, p + 2 * g * s) * self.fp_dt_ns
        tau = self.tau_override if self.manual_tau else tau_est
        expected = (
            client.perrin_steady_state(tau_ns=tau, rho_ns=self.fp_rho_ns, r0=self.fp_r0)
            if client
            else perrin_steady_state_anisotropy(tau_ns=tau, rho_ns=self.fp_rho_ns, r0=self.fp_r0)
        )
        if self.manual_rs:
            expected = self.rs_override
        l = (
            client.solve_linked_l(
                sp=float(p.sum()), ss=float(s.sum()), g_factor=g, r_target=expected
            )
            if client
            else solve_linked_l_from_steady_state(
                sp=float(p.sum()), ss=float(s.sum()), g_factor=g, r_target=expected
            )
        )
        warning = "One steady-state observable determines only the linked estimate l1 = l2."
        if self.manual_l:
            l = self.l_override
            warning = "Manual linked l1/l2 override is active."
        elif not np.isfinite(l) or not 0 <= l <= 0.5:
            warning = (
                f"Linked mixing estimate {l:g} is outside the physical [0, 0.5] range; not applied."
            )
            l = np.nan
        self.fp_result = {
            "tau_estimate_ns": float(tau_est),
            "tau_used_ns": float(tau),
            "r_expected": float(expected),
            "l1": float(l) if np.isfinite(l) else None,
            "l2": float(l) if np.isfinite(l) else None,
            "warning": warning,
        }

    def decay_series(self, slow=False):
        par, perp = self.channels(slow)
        if par is None:
            return {}
        time = np.arange(len(par), dtype=float)
        shifted = time + self.shift
        bg = (
            compute_background_levels(par, perp, time, shifted, self.background_region)
            if self.background
            else (0.0, 0.0)
        )
        p = np.maximum(par - bg[0], 0)
        s = np.maximum(perp - bg[1], 0)
        g = self.g_factor
        g = float(g) if g is not None and np.isfinite(g) and g > 0 else np.nan
        l1 = float(self.fp_result.get("l1") or 0)
        l2 = float(self.fp_result.get("l2") or 0)
        corrected = shift_interp_on_axis(time, s, self.shift)
        return {
            "time": time,
            "shifted_time": shifted,
            "vv_raw": par,
            "vh_raw": perp,
            "vv_corrected": p,
            "vh_corrected": s * g,
            "r_raw": np.clip(
                compute_rt(par, perp, self.result.get("g_factor_uncorrected") or g), -0.5, 1.5
            ),
            "r_corrected": np.clip(compute_rt(p, corrected, g, l1=l1, l2=l2), -0.5, 1.5),
        }

    def batch_snapshot(self):
        par, perp = self.channels()
        if par is None or self.g_factor is None:
            raise ValueError("Determine G before applying batch anisotropy analysis.")
        time = np.arange(len(par), dtype=float)
        bg = compute_background_levels(par, perp, time, time + self.shift, self.background_region)
        return {
            "g_factor": float(self.g_factor),
            "l1": float(self.fp_result.get("l1") or 0),
            "l2": float(self.fp_result.get("l2") or 0),
            "shift": self.shift,
            "flip": self.flip,
            "background": self.background,
            "background_levels": bg,
            "region": list(self.region),
        }

    def compute_batch(self, cancel_cb=None):
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
                p = np.maximum(par[:n] - bp, 0)
                s = np.maximum(perp[:n] - bs, 0)
                anisotropy = compute_rt(
                    p,
                    shift_interp_on_axis(time, s, params["shift"]),
                    params["g_factor"],
                    l1=params["l1"],
                    l2=params["l2"],
                )
                start, stop = sorted(params["region"])
                start = max(0, min(n - 1, int(round(start))))
                stop = max(start + 1, min(n, int(round(stop))))
                values = anisotropy[start:stop]
                values = values[np.isfinite(values)]
                rows.append(
                    {
                        "file": filename,
                        "r_inf": float(np.mean(values)) if len(values) else None,
                        "region_start": start,
                        "region_stop": stop,
                        "bg_vv": bp,
                        "bg_vh": bs,
                        "g_factor": params["g_factor"],
                        "error": "",
                    }
                )
            except Exception as exc:
                rows.append({"file": filename, "r_inf": None, "error": str(exc)})
        self.batch_results = rows
        self.message = f"Processed {len(rows)} batch decays."

    def export_batch(self, path):
        if not self.batch_results:
            raise ValueError("Run batch analysis before exporting.")
        columns = [
            "file",
            "r_inf",
            "region_start",
            "region_stop",
            "bg_vv",
            "bg_vh",
            "g_factor",
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

    def archive_parameters(self):
        if self.g_factor is None:
            raise ValueError("Determine a G-factor before archival.")
        return {
            "g_factor": self.g_factor,
            "g_factor_stddev": self.result.get(
                "g_factor_stddev_corrected" if self.background else "g_factor_stddev_uncorrected"
            ),
            "l1": self.fp_result.get("l1") or 0.0,
            "l2": self.fp_result.get("l2") or 0.0,
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

    def export_settings(self):
        names = (
            "fast_file",
            "slow_file",
            "region",
            "background_region",
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
            "l_override",
            "batch_files",
        )
        return {name: deepcopy(getattr(self, name)) for name in names}

    def restore_settings(self, state):
        for name, value in state.items():
            if name in self.export_settings():
                setattr(self, name, deepcopy(value))

    def save_results(self, path):
        Path(path).write_text(
            json.dumps(
                {
                    "settings": self.export_settings(),
                    "g_result": self.result,
                    "fp_result": self.fp_result,
                },
                indent=2,
            )
        )
