"""Pure MEM workflow, preserving lifetime/FRET, priors, sampling and exports."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

from ..api.helpers import build_distance_grid, build_tau_grid
from ..api.models import MEMSettings
from ..core.solver import solve_fret_mem, solve_lifetime_mem


def open_fits():
    import chisurf

    return [fit for group in chisurf.fits for fit in getattr(group, "grouped_fits", [group])]


def open_datasets():
    import chisurf
    from chisurf.core.data import DataGroup

    result = []

    def collect(data):
        if isinstance(data, (list, tuple, DataGroup)):
            for member in data:
                collect(member)
        elif hasattr(data, "x") and hasattr(data, "y"):
            result.append(data)

    for data in chisurf.imported_datasets:
        collect(data)
    return result


def solve_snapshot(snapshot, nu=None):
    p = snapshot["parameters"]
    s = p["settings"]
    kwargs = dict(
        decay=snapshot["decay"],
        lamp=snapshot["lamp"],
        dt=snapshot["dt"],
        timeshift=s["timeshift"],
        background=s["background"],
        lamp_scatter=s["lamp_scatter"],
        fitrange=snapshot["fitrange"],
        irf_background=s["irf_background"]
        if s["irf_background"] and s["irf_background"] > 0
        else None,
        fit_start_fraction=s["fit_start_fraction"],
        nu=s["nu"] if nu is None else nu,
        max_iter=s["max_iter"],
        tol=s["tol"],
        period=s["period"] if p["use_periodic"] else None,
        optimize_nuisance=s["optimize_nuisance"],
        nuisance_step_timeshift=0.0 if p["fix_timeshift"] else None,
        nuisance_step_background=0.0 if p["fix_background"] else None,
        nuisance_step_irf_background=0.0 if p["fix_irf_background"] else None,
    )
    if s["mode"] == "lifetime":
        axis = build_tau_grid(s["tau_min"], s["tau_max"], s["tau_bins"])
        result = solve_lifetime_mem(tau=axis, prior=snapshot["prior"], **kwargs)
    else:
        if snapshot["donor"] is None:
            raise ValueError("FRET mode requires a donor-only spectrum from a file or live fit.")
        axis = build_distance_grid(s["R0"], s["r_min_frac"], s["r_max_frac"], s["r_bins"])
        result = solve_fret_mem(
            R=axis,
            tau0=s["tau0"],
            R0=s["R0"],
            donly=snapshot["donor"],
            x_donly=s["x_donly"],
            prior=snapshot["prior"],
            nuisance_step_x_donly=0.0 if p["fix_x_donly"] else None,
            **kwargs,
        )
    return result


def execute_job(job, progress=None):
    snapshot = job["snapshot"]
    kind = job["kind"]
    if kind == "run":
        return solve_snapshot(snapshot)
    if kind == "lcurve":
        from ..backend.services import _lcurve_corner_index

        p = snapshot["parameters"]
        center = np.log10(p["settings"]["nu"])
        axis = np.linspace(center - p["lcurve_left"], center + p["lcurve_right"], 16)
        chi = []
        norm = []
        for index, value in enumerate(axis):
            result = solve_snapshot(snapshot, 10.0**value)
            chi.append(float(result["chisq"]))
            norm.append(float(np.linalg.norm(result["p"])))
            if progress:
                progress(index + 1, 16)
        return {
            "log10_nu": axis,
            "chi2r": np.asarray(chi),
            "sol_norm": np.asarray(norm),
            "corner_index": _lcurve_corner_index(chi, norm),
        }
    if kind == "sample":
        from ..core.sampling import sample_mem_distribution_mcmc

        p = snapshot["parameters"]
        folder = Path(job["folder"])
        folder.mkdir(parents=True, exist_ok=True)
        stats = sample_mem_distribution_mcmc(
            job["result"],
            filename=str(folder / "sampling.npz"),
            steps_total=p["sample_steps"],
            thin=p["sample_thin"],
            nwalkers=p["sample_walkers"] or None,
            substeps=p["sample_substeps"],
            nprocs=p["sample_nprocs"] or None,
            vectorized=p["sample_vectorized"],
            progress_cb=(lambda done, total: progress(done, total) or False) if progress else None,
        )
        metadata = {
            "schema": "chisurf.maxent_mem_sampling",
            "schema_version": 1,
            "mode": snapshot["parameters"]["settings"]["mode"],
            "mem": snapshot["parameters"],
            "sampling": {
                "hdf5_file": "sampling.npz",
                **{
                    key: stats.get(key)
                    for key in (
                        "nwalkers",
                        "steps_total",
                        "thin",
                        "substeps",
                        "ndim",
                        "vectorized",
                        "n_samples",
                    )
                },
            },
        }
        (folder / "sampling_project.json").write_text(json.dumps(metadata, indent=2))
        return stats
    raise ValueError(f"Unknown MEM job: {kind}")


class MEMModel:
    def __init__(self):
        self.settings = MEMSettings(R0=50.0, period=10.0)
        self.use_periodic = False
        self.fix_timeshift = False
        self.fix_background = False
        self.fix_irf_background = False
        self.fix_x_donly = False
        self.lcurve_left = 2.0
        self.lcurve_right = 2.0
        self.sample_steps = 500
        self.sample_thin = 5
        self.sample_walkers = 0
        self.sample_substeps = 50
        self.sample_nprocs = 0
        self.sample_vectorized = sys.platform.startswith("win")
        self.time = None
        self.decay = None
        self.irf = None
        self.dt = 1.0
        self.fit = None
        self.source = "No data loaded"
        self.irf_source = "Impulse IRF; choose a measured response or a live fit."
        self.fitrange = None
        self.priors = {"lifetime": None, "fret": None}
        self.donor = None
        self.result = None
        self.result_snapshot = None
        self.lcurve = None
        self.samples = None
        self.status = "Select a decay or use a live fit."

    def reset_results(self):
        self.result = None
        self.result_snapshot = None
        self.lcurve = None
        self.samples = None

    def set_data(self, time, decay, name="Dataset"):
        time = np.asarray(time, dtype=float).ravel()
        decay = np.asarray(decay, dtype=float).ravel()
        if (
            time.size != decay.size
            or time.size < 2
            or not np.isfinite(time).all()
            or not np.isfinite(decay).all()
            or np.any(np.diff(time) <= 0)
            or np.any(decay < 0)
        ):
            raise ValueError("A decay needs finite counts and a matching, increasing time axis.")
        self.time = time.copy()
        self.decay = decay.copy()
        self.dt = float(np.diff(time).mean())
        self.source = name
        self.fitrange = None
        self.fit = None
        self.status = f"Loaded {name} ({time.size} channels, {self.dt:.4g} ns per channel)."
        self.reset_results()

    def load_dataset(self, data):
        self.set_data(data.x, data.y, getattr(data, "name", "Dataset"))

    def load_fit(self, fit):
        self.load_dataset(fit.data)
        self.fit = fit
        self._after_refresh = True
        self.fitrange = (max(0, int(fit.xmin)), min(len(self.decay) - 1, int(fit.xmax)))
        convolve = getattr(fit.model, "convolve", None)
        if convolve is not None:
            irf = getattr(convolve, "unnormalized_irf", None)
            if irf is not None:
                self.select_irf(irf)
            for attr, target in (("timeshift", "timeshift"), ("lamp_background", "irf_background")):
                if hasattr(convolve, attr):
                    setattr(self.settings, target, float(getattr(convolve, attr)))
        generic = getattr(fit.model, "generic", None)
        if generic is not None and hasattr(generic, "background"):
            self.settings.background = float(generic.background)
        # what the Qt tool's Refresh did next: the smallest lifetime follows the IRF width, the period the time window
        fwhm = self.irf_fwhm()
        if fwhm:
            self.settings.tau_min = round(fwhm, 3)  # the Qt spin box shows three decimals
        span = float(self.time[-1] - self.time[0])
        if span > 0:
            self.settings.period = round(span, 2)  # and two for the period

    def irf_fwhm(self):
        """Half the width at half maximum of the IRF on the decay axis (the Qt tool's estimate), or None."""
        try:
            lamp = self.lamp()
        except ValueError:
            return None
        t, lamp = np.asarray(self.time, float), np.asarray(lamp, float)
        if t.size < 3 or not np.isfinite(lamp.max()) or lamp.max() <= 0:
            return None
        above = np.nonzero(lamp >= 0.5 * lamp.max())[0]
        if above.size < 2:
            return float(np.mean(np.diff(t))) or None
        fwhm = float(t[above[-1]] - t[above[0]]) / 2.0
        return fwhm if fwhm > 0 else float(np.mean(np.diff(t)))

    def load_file(self, path, irf=False):
        try:
            values = np.loadtxt(path, ndmin=2)
        except ValueError:
            values = np.loadtxt(path, ndmin=2, delimiter=",")
        if values.shape[1] < 2:
            raise ValueError("Files must contain time/count pairs.")
        if irf:
            from types import SimpleNamespace

            self.select_irf(SimpleNamespace(x=values[:, 0], y=values[:, 1], name=Path(path).name))
        else:
            self.set_data(values[:, 0], values[:, 1], Path(path).name)

    def select_irf(self, curve):
        x = np.asarray(curve.x, dtype=float).ravel()
        y = np.asarray(curve.y, dtype=float).ravel()
        if len(x) != len(y) or not len(y) or not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError("Invalid IRF curve.")
        order = np.argsort(x)
        self.irf = (x[order].copy(), y[order].copy())
        self.irf_source = getattr(curve, "name", "Measured IRF")
        self.reset_results()

    def clear_irf(self):
        self.irf = None
        self.irf_source = "Current fit response or impulse."
        self.reset_results()

    def lamp(self):
        if self.decay is None:
            raise ValueError("Select a measured decay first.")
        if self.irf is not None:
            return np.interp(self.time, *self.irf, left=0.0, right=0.0)
        if self.fit is not None:
            convolve = getattr(self.fit.model, "convolve", None)
            curve = getattr(convolve, "unnormalized_irf", None) if convolve is not None else None
            if curve is not None:
                return np.interp(
                    self.time, np.asarray(curve.x), np.asarray(curve.y), left=0.0, right=0.0
                )
        lamp = np.zeros(len(self.decay))
        lamp[0] = 1.0
        return lamp

    def grid(self):
        s = self.settings
        return (
            build_tau_grid(s.tau_min, s.tau_max, s.tau_bins)
            if s.mode == "lifetime"
            else build_distance_grid(s.R0, s.r_min_frac, s.r_max_frac, s.r_bins)
        )

    def load_prior(self, path):
        try:
            values = np.loadtxt(path, ndmin=1)
        except ValueError:
            values = np.loadtxt(path, ndmin=1, delimiter=",")
        if not np.isfinite(values).all() or not values.size:
            raise ValueError("Prior must contain finite values.")
        self.priors[self.settings.mode] = (
            (values[:, 0], values[:, 1])
            if values.ndim == 2 and values.shape[1] >= 2
            else values.ravel()
        )

    def prior(self):
        prior = self.priors[self.settings.mode]
        if prior is None:
            return None
        values = (
            np.interp(self.grid(), prior[0], prior[1], left=0.0, right=0.0)
            if isinstance(prior, tuple)
            else np.asarray(prior)
        )
        if len(values) != len(self.grid()) or np.any(values < 0) or values.sum() <= 0:
            raise ValueError("Prior must match the current grid and contain nonnegative mass.")
        return values

    def load_donor(self, path):
        try:
            values = np.loadtxt(path, ndmin=1)
        except ValueError:
            values = np.loadtxt(path, ndmin=1, delimiter=",")
        from chisurf.core.fluorescence.decay import validate_lifetime_spectrum

        flat = values[:, :2].reshape(-1) if values.ndim == 2 else values.ravel()
        self.donor = validate_lifetime_spectrum(flat)

    def donor_from_fit(self, fit):
        lifetimes = getattr(fit.model, "lifetimes", None)
        if lifetimes is None:
            raise ValueError("Selected fit has no lifetime spectrum.")
        parameters = lifetimes.parameters_all
        self.donor = np.asarray([parameter.value for parameter in parameters], dtype=float)
        if not len(self.donor) or len(self.donor) % 2:
            raise ValueError("Invalid donor-only lifetime spectrum.")

    def parameters(self):
        return {
            "settings": asdict(self.settings),
            **{
                key: getattr(self, key)
                for key in (
                    "use_periodic",
                    "fix_timeshift",
                    "fix_background",
                    "fix_irf_background",
                    "fix_x_donly",
                    "lcurve_left",
                    "lcurve_right",
                    "sample_steps",
                    "sample_thin",
                    "sample_walkers",
                    "sample_substeps",
                    "sample_nprocs",
                    "sample_vectorized",
                )
            },
        }

    def snapshot(self):
        return {
            "parameters": self.parameters(),
            "time": self.time.copy() if self.time is not None else None,
            "decay": self.decay.copy() if self.decay is not None else None,
            "dt": self.dt,
            "lamp": self.lamp().copy(),
            "fitrange": self.fitrange,
            "prior": self.prior(),
            "donor": None if self.donor is None else self.donor.copy(),
        }

    def run(self):
        snapshot = self.snapshot()
        self.result = solve_snapshot(snapshot)
        self.result_snapshot = snapshot
        return self.result

    def arrays(self):
        if self.result is None:
            return None
        r = self.result
        sp = self.result_snapshot
        first, last = r["fitrange"]
        fit = np.asarray(r["Fi"]) @ np.asarray(r["p"]) * np.asarray(r["sigma"]) + np.asarray(
            r["fit_additive"]
        )
        return {
            "axis": np.asarray(r.get("R", r.get("tau"))),
            "p": np.asarray(r["p"]),
            "time": sp["time"][first : last + 1],
            "fit": fit,
            "wres": (np.asarray(r["y"]) - fit) / np.asarray(r["sigma"]),
        }

    def export_result(self, folder):
        arrays = self.arrays()
        if arrays is None:
            raise ValueError("Run MEM before saving.")
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        snapshot = self.result_snapshot
        r = self.result
        np.savetxt(
            folder / "distribution.txt",
            np.column_stack((arrays["axis"], arrays["p"])),
            header="axis p",
        )
        full = np.zeros(len(snapshot["decay"]))
        first, last = r["fitrange"]
        full[first : last + 1] = arrays["fit"]
        np.savetxt(
            folder / "decay_fit.txt",
            np.column_stack((snapshot["time"], snapshot["decay"], full)),
            header="time decay mem_fit",
        )
        np.savetxt(
            folder / "irf.txt",
            np.column_stack((snapshot["time"], snapshot["lamp"])),
            header="time irf",
        )
        np.savetxt(
            folder / "wres.txt",
            np.column_stack((arrays["time"], arrays["wres"])),
            header="time wres",
        )
        metadata = {
            **snapshot["parameters"],
            "mode": "FRET" if "R" in r else "lifetime",
            "chisq": float(r["chisq"]),
            "S": float(r["S"]),
            "Q": float(r["Q"]),
            "fitrange": list(r["fitrange"]),
            "dt": snapshot["dt"],
            "nu": float(r["nu"]),
        }
        (folder / "meta.json").write_text(json.dumps(metadata, indent=2))
        return folder

    def restore_preferences(self, settings):
        if not settings:
            from chisurf.core.settings.path_utils import get_path

            path = Path(get_path("settings")) / "maxent_decay" / "settings.json"
            if path.is_file():
                try:
                    settings = json.loads(path.read_text())
                except (OSError, ValueError):
                    return
        if not isinstance(settings, dict):
            raise ValueError("MEM preferences must be a JSON object.")
        # Read the original Qt preferences without creating or rewriting them.
        grid = settings.get("tau_grid", {})
        for source, target in (("min", "tau_min"), ("max", "tau_max"), ("bins", "tau_bins")):
            if source in grid:
                setattr(self.settings, target, grid[source])
        for key, value in settings.get("fret", {}).items():
            if key == "use_periodic":
                self.use_periodic = bool(value)
            elif hasattr(self.settings, "period" if key == "period_ns" else key):
                setattr(self.settings, "period" if key == "period_ns" else key, value)
        for key, value in settings.get("lcurve_span_decades", {}).items():
            if key in ("left", "right"):
                setattr(self, "lcurve_" + key, value)
        sampling = {
            "steps_total": "sample_steps",
            "thin": "sample_thin",
            "walkers": "sample_walkers",
            "substeps": "sample_substeps",
            "nprocs": "sample_nprocs",
            "vectorized": "sample_vectorized",
        }
        for key, value in settings.get("sampling_defaults", {}).items():
            if key in sampling and value is not None:
                setattr(self, sampling[key], value)
        for key, value in settings.get("settings", {}).items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
        for key in self.parameters():
            if key != "settings" and key in settings:
                setattr(self, key, settings[key])


class MEMForm:
    """What a spec form sees: every setting of the MEM run and of the tool as plain attributes of one object.

    ``attr`` names resolve on :class:`~..api.models.MEMSettings` first, then on the model (``use_periodic``,
    the ``fix_*`` switches, the L-curve span and the sampling options). ``enabled`` greys what means nothing now.
    """

    def __init__(self, model):
        object.__setattr__(self, "_m", model)

    def __getattr__(self, name):
        m = object.__getattribute__(self, "_m")
        if name in MEMSettings.__slots__:
            value = getattr(m.settings, name)
            return 0.0 if value is None and name == "irf_background" else value
        return getattr(m, name)

    def __setattr__(self, name, value):
        m = object.__getattribute__(self, "_m")
        if name in MEMSettings.__slots__:
            setattr(m.settings, name, value)
            if name in ("mode",):
                m.reset_results()
        else:
            setattr(m, name, value)

    def enabled(self, name):
        m = object.__getattribute__(self, "_m")
        if getattr(m, "busy", False):
            return False
        if name == "period":
            return bool(m.use_periodic)
        if name in ("timeshift", "background", "irf_background"):
            return True
        return True
