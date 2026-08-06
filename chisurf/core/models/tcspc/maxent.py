"""MaxEnt TCSPC fitting models."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

import chisurf as cs
import chisurf.core.math.datatools
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.tcspc.fret import FRETModel
from chisurf.core.models.tcspc.lifetime import LifetimeModel
from chisurf.plugins.fluorescence_decay.maxent_decay.api.helpers import build_distance_grid, build_tau_grid
from chisurf.plugins.fluorescence_decay.maxent_decay.core.solver import solve_fret_mem, solve_lifetime_mem

if TYPE_CHECKING:
    from chisurf.core.fitting.fit import Fit


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(getattr(value, "value", value))
    except Exception:
        return default


def _data_x(fit: Fit) -> np.ndarray:
    data = getattr(fit, "data", None)
    x = getattr(data, "x", None)
    y = np.asarray(getattr(data, "y", []), dtype=float).ravel()
    if x is None or np.asarray(x).size != y.size:
        return np.arange(y.size, dtype=float)
    return np.asarray(x, dtype=float).ravel()


def _data_dt(fit: Fit) -> float:
    data = getattr(fit, "data", None)
    dx = getattr(data, "dx", None)
    if dx is not None:
        try:
            return float(np.asarray(dx).ravel()[0])
        except Exception:
            pass
    x = _data_x(fit)
    if x.size > 1:
        return float(np.mean(np.diff(x)))
    return 1.0


def _fitrange(fit: Fit, n_points: int) -> tuple[int, int] | None:
    if n_points <= 0:
        return None
    xmin = int(getattr(fit, "xmin", 0))
    xmax = int(getattr(fit, "xmax", n_points - 1))
    xmin = max(0, min(xmin, n_points - 1))
    xmax = max(xmin, min(xmax, n_points - 1))
    return xmin, xmax


def _irf_like_decay(model: LifetimeModel, n_points: int) -> np.ndarray:
    convolve = getattr(model, "convolve", None)
    irf = None
    if convolve is not None:
        irf = getattr(convolve, "unnormalized_irf", None) or getattr(convolve, "irf", None)
    if irf is None:
        irf = np.zeros(n_points, dtype=float)
        if n_points:
            irf[0] = 1.0
        return irf
    y = np.asarray(getattr(irf, "y", []), dtype=float).ravel()
    if y.size == 0:
        y = np.zeros(n_points, dtype=float)
        if n_points:
            y[0] = 1.0
    if y.size == n_points:
        return y.astype(float, copy=False)
    return np.resize(y, n_points).astype(float)


class MaxEntLifetimeModel(LifetimeModel):
    """Lifetime model backed by a MaxEnt lifetime distribution."""

    name = "MaxEnt Lifetime MEM"
    view_spec_file = "maxent_lifetime.view.json"

    def __init__(self, fit: Fit, **kwargs):
        """Initialize the MaxEnt lifetime MEM model."""
        self._nu_log10 = FittingParameter(
            name="mem_nu_log10",
            label_text="log&#8321;&#8320;(&nu;)",
            value=-3.0,
            lb=-8.0,
            ub=3.0,
            bounds_on=True,
            fixed=True,
        )
        self._tau_min = FittingParameter(
            name="mem_tau_min",
            label_text="&tau;<sub>min</sub>",
            value=0.01,
            lb=1e-6,
            ub=float("inf"),
            bounds_on=True,
            fixed=True,
        )
        self._tau_max = FittingParameter(
            name="mem_tau_max",
            label_text="&tau;<sub>max</sub>",
            value=6.0,
            lb=1e-6,
            ub=float("inf"),
            bounds_on=True,
            fixed=True,
        )
        self._tau_bins = FittingParameter(
            name="mem_tau_bins",
            label_text="&tau; bins",
            value=192,
            lb=2,
            ub=10000,
            bounds_on=True,
            fixed=True,
        )
        super().__init__(fit, **kwargs)
        self._cached_lifetime_spectrum = np.array([1.0, 4.0], dtype=float)
        self._last_result = None
        self.find_parameters()

    @property
    def nu(self) -> float:
        """Regularization parameter nu."""
        return 10.0 ** float(self._nu_log10.value)

    @property
    def tau_grid(self) -> np.ndarray:
        """Lifetime grid used by the MaxEnt solver."""
        return build_tau_grid(
            tau_min=float(self._tau_min.value),
            tau_max=float(self._tau_max.value),
            tau_bins=int(self._tau_bins.value),
        )

    @property
    def last_result(self) -> dict | None:
        """Return the last MaxEnt solver result."""
        return self._last_result

    @property
    def lifetime_spectrum(self) -> np.ndarray:
        """Interleaved MaxEnt amplitude/lifetime spectrum."""
        return self._cached_lifetime_spectrum

    def _mem_parameter_rows(self) -> list:
        """Return the maximum-entropy settings for the editor's table.

        Returns
        -------
        list
            The entropy weight followed by the inversion grid parameters.
        """
        return [self._nu_log10, self._tau_min, self._tau_max, self._tau_bins]

    @property
    def l_curve(self) -> "cs.core.math.regularization.LCurveData | None":
        """The cached regularization sweep as the shared L-curve data model.

        `compute_l_curve` caches the sweep in private arrays; this exposes them in
        the form every L-curve view consumes, so the corner the model already
        detected is visible instead of only being used internally. Returns None
        until a sweep has been run.

        Returns
        -------
        chisurf.core.math.regularization.LCurveData or None
            Weights, misfit norm, solution norm and the detected corner.
        """
        chi2 = getattr(self, "_l_curve_chi2", None)
        sol = getattr(self, "_l_curve_sol_norm", None)
        if chi2 is None or sol is None or len(chi2) == 0:
            return None
        log10_nu = getattr(self, "_l_curve_log10_nu", None)
        reg = (
            10.0 ** np.asarray(log10_nu, dtype=float)
            if log10_nu is not None and len(log10_nu) == len(chi2)
            else np.arange(len(chi2), dtype=float)
        )
        return cs.core.math.regularization.LCurveData(
            reg=reg,
            residual_norm=np.asarray(chi2, dtype=float),
            solution_norm=np.asarray(sol, dtype=float),
            corner_index=getattr(self, "_l_curve_corner_index", None),
        )

    def compute_l_curve(
        self,
        n_points: int = 16,
        log10_min: float | None = None,
        log10_max: float | None = None,
    ) -> None:
        """Sweep regularization and cache L-curve data."""
        data = self.fit.data
        decay = np.asarray(getattr(data, "y", []), dtype=float).ravel()
        if decay.size == 0:
            self._l_curve_log10_nu = np.array([], dtype=float)
            self._l_curve_chi2 = np.array([], dtype=float)
            self._l_curve_sol_norm = np.array([], dtype=float)
            self._l_curve_corner_index = None
            return
        center = float(self._nu_log10.value)
        if log10_min is None:
            log10_min = max(-8.0, center - 2.0)
        if log10_max is None:
            log10_max = min(3.0, center + 2.0)
        if log10_min >= log10_max:
            log10_min, log10_max = center - 2.0, center + 2.0
        nu_grid = np.geomspace(10.0 ** log10_min, 10.0 ** log10_max, max(2, int(n_points)))
        irf = _irf_like_decay(self, decay.size)
        chi2: list[float] = []
        sol: list[float] = []
        for nu_val in nu_grid:
            result = solve_lifetime_mem(
                decay=decay,
                lamp=irf,
                dt=_data_dt(self.fit),
                tau=self.tau_grid,
                timeshift=_as_float(getattr(self.convolve, "timeshift", None)),
                background=_as_float(getattr(self.generic, "background", None)),
                lamp_scatter=_as_float(getattr(self.generic, "scatter", None)),
                fitrange=_fitrange(self.fit, decay.size),
                irf_background=_as_float(getattr(self.convolve, "lamp_background", None)),
                nu=float(nu_val),
                max_iter=80,
            )
            chi2.append(float(result.get("chisq", np.nan)))
            p = np.asarray(result.get("p", []), dtype=float).ravel()
            sol.append(float(np.linalg.norm(p)) if p.size else float("nan"))
        self._l_curve_log10_nu = np.log10(nu_grid)
        self._l_curve_chi2 = np.asarray(chi2, dtype=float)
        self._l_curve_sol_norm = np.asarray(sol, dtype=float)
        try:
            mask = np.isfinite(self._l_curve_chi2) & np.isfinite(self._l_curve_sol_norm)
            self._l_curve_corner_index = int(cs.core.math.regularization.discrete_lcurve_corner(self._l_curve_chi2[mask], self._l_curve_sol_norm[mask]))
        except Exception:
            self._l_curve_corner_index = None

    def update_model(self, **kwargs) -> None:
        """Run MaxEnt lifetime inversion and update the model curve."""
        data = getattr(self.fit, "data", None)
        decay = np.asarray(getattr(data, "y", []), dtype=float).ravel()
        if decay.size == 0:
            self.x = np.array([], dtype=float)
            self.y = np.array([], dtype=float)
            self._last_result = None
            return
        irf = _irf_like_decay(self, decay.size)
        self._last_result = solve_lifetime_mem(
            decay=decay,
            lamp=irf,
            dt=_data_dt(self.fit),
            tau=self.tau_grid,
            timeshift=_as_float(getattr(self.convolve, "timeshift", None)),
            background=_as_float(getattr(self.generic, "background", None)),
            lamp_scatter=_as_float(getattr(self.generic, "scatter", None)),
            fitrange=_fitrange(self.fit, decay.size),
            irf_background=_as_float(getattr(self.convolve, "lamp_background", None)),
            nu=self.nu,
            max_iter=int(self._last_result.get("niter", 200)) if self._last_result else 200,
        )
        fitrange = self._last_result.get("fitrange")
        if fitrange is not None:
            fitstart, fitstop = fitrange
            Fi = self._last_result.get("Fi")
            p = np.asarray(self._last_result.get("p", []), dtype=float).ravel()
            sigma = np.asarray(self._last_result.get("sigma", []), dtype=float).ravel()
            fit_additive = np.asarray(self._last_result.get("fit_additive", []), dtype=float).ravel()
            if Fi is not None and p.size > 0 and sigma.size > 0:
                model_seg = Fi @ p * sigma + fit_additive
                fit_curve = np.zeros(decay.size, dtype=float)
                seg_len = min(model_seg.size, fitstop - fitstart + 1)
                fit_curve[fitstart:fitstart + seg_len] = model_seg[:seg_len]
            else:
                fit_curve = np.zeros_like(decay)
        else:
            fit_curve = np.zeros_like(decay)
        self.x = _data_x(self.fit)
        self.y = np.maximum(fit_curve, 0.0)
        p = np.asarray(self._last_result.get("p", []), dtype=float).ravel()
        if p.size:
            p = p / np.sum(p)
        self._cached_lifetime_spectrum = np.column_stack([p, self.tau_grid]).ravel()


class MaxEntFRETModel(FRETModel):
    """FRET model backed by a MaxEnt distance distribution."""

    name = "MaxEnt FRET Distance MEM"
    view_spec_file = "maxent_fret.view.json"

    def __init__(self, fit: Fit, **kwargs):
        """Initialize the MaxEnt FRET MEM model."""
        self._nu_log10 = FittingParameter(
            name="mem_fret_nu_log10",
            label_text="log&#8321;&#8320;(&nu;)",
            value=-3.0,
            lb=-8.0,
            ub=3.0,
            bounds_on=True,
            fixed=True,
        )
        self._r_min_frac = FittingParameter(
            name="mem_r_min_frac",
            label_text="r<sub>min</sub>/R<sub>0</sub>",
            value=0.1,
            lb=1e-6,
            ub=10.0,
            bounds_on=True,
            fixed=True,
        )
        self._r_max_frac = FittingParameter(
            name="mem_r_max_frac",
            label_text="r<sub>max</sub>/R<sub>0</sub>",
            value=3.0,
            lb=1e-6,
            ub=10.0,
            bounds_on=True,
            fixed=True,
        )
        self._r_bins = FittingParameter(
            name="mem_r_bins",
            label_text="r bins",
            value=96,
            lb=2,
            ub=10000,
            bounds_on=True,
            fixed=True,
        )
        super().__init__(fit, **kwargs)
        self._last_result = None
        self.find_parameters()

    @property
    def nu(self) -> float:
        """Regularization parameter nu."""
        return 10.0 ** float(self._nu_log10.value)

    @property
    def distance_grid(self) -> np.ndarray:
        """Distance grid used by the MaxEnt FRET solver."""
        return build_distance_grid(
            R0=float(self.fret_parameters.forster_radius),
            r_min_frac=float(self._r_min_frac.value),
            r_max_frac=float(self._r_max_frac.value),
            r_bins=int(self._r_bins.value),
        )

    @property
    def last_result(self) -> dict | None:
        """Return the last MaxEnt FRET solver result."""
        return self._last_result

    @property
    def distance_distribution(self) -> np.ndarray:
        """Normalized MaxEnt distance distribution as ``(1, 2, n)``."""
        if self._last_result is None:
            p = np.ones_like(self.distance_grid, dtype=float)
        else:
            p = np.asarray(self._last_result.get("p", []), dtype=float).ravel()
            if p.size == 0:
                p = np.ones_like(self.distance_grid, dtype=float)
        p = p / np.sum(p) if np.sum(p) > 0.0 else p
        return np.array([p, self.distance_grid], dtype=float).reshape(1, 2, p.size)

    def _mem_parameter_rows(self) -> list:
        """Return the maximum-entropy settings for the editor's table.

        Returns
        -------
        list
            The entropy weight followed by the inversion grid parameters.
        """
        return [self._nu_log10, self._r_min_frac, self._r_max_frac, self._r_bins]

    @property
    def l_curve(self) -> "cs.core.math.regularization.LCurveData | None":
        """The cached regularization sweep as the shared L-curve data model.

        `compute_l_curve` caches the sweep in private arrays; this exposes them in
        the form every L-curve view consumes, so the corner the model already
        detected is visible instead of only being used internally. Returns None
        until a sweep has been run.

        Returns
        -------
        chisurf.core.math.regularization.LCurveData or None
            Weights, misfit norm, solution norm and the detected corner.
        """
        chi2 = getattr(self, "_l_curve_chi2", None)
        sol = getattr(self, "_l_curve_sol_norm", None)
        if chi2 is None or sol is None or len(chi2) == 0:
            return None
        log10_nu = getattr(self, "_l_curve_log10_nu", None)
        reg = (
            10.0 ** np.asarray(log10_nu, dtype=float)
            if log10_nu is not None and len(log10_nu) == len(chi2)
            else np.arange(len(chi2), dtype=float)
        )
        return cs.core.math.regularization.LCurveData(
            reg=reg,
            residual_norm=np.asarray(chi2, dtype=float),
            solution_norm=np.asarray(sol, dtype=float),
            corner_index=getattr(self, "_l_curve_corner_index", None),
        )

    def compute_l_curve(
        self,
        n_points: int = 16,
        log10_min: float | None = None,
        log10_max: float | None = None,
    ) -> None:
        """Sweep regularization and cache L-curve data."""
        data = self.fit.data
        decay = np.asarray(getattr(data, "y", []), dtype=float).ravel()
        if decay.size == 0:
            self._l_curve_log10_nu = np.array([], dtype=float)
            self._l_curve_chi2 = np.array([], dtype=float)
            self._l_curve_sol_norm = np.array([], dtype=float)
            self._l_curve_corner_index = None
            return
        center = float(self._nu_log10.value)
        if log10_min is None:
            log10_min = max(-8.0, center - 2.0)
        if log10_max is None:
            log10_max = min(3.0, center + 2.0)
        if log10_min >= log10_max:
            log10_min, log10_max = center - 2.0, center + 2.0
        nu_grid = np.geomspace(10.0 ** log10_min, 10.0 ** log10_max, max(2, int(n_points)))
        irf = _irf_like_decay(self, decay.size)
        chi2: list[float] = []
        sol: list[float] = []
        for nu_val in nu_grid:
            result = solve_fret_mem(
                decay=decay,
                lamp=irf,
                dt=_data_dt(self.fit),
                R=self.distance_grid,
                tau0=float(self.fret_parameters.tauD0),
                R0=float(self.fret_parameters.forster_radius),
                donly=np.asarray(self.donor_lifetime_spectrum, dtype=float).ravel(),
                x_donly=float(self.fret_parameters.xDOnly),
                timeshift=_as_float(getattr(self.convolve, "timeshift", None)),
                background=_as_float(getattr(self.generic, "background", None)),
                lamp_scatter=_as_float(getattr(self.generic, "scatter", None)),
                fitrange=_fitrange(self.fit, decay.size),
                irf_background=_as_float(getattr(self.convolve, "lamp_background", None)),
                nu=float(nu_val),
                max_iter=80,
            )
            chi2.append(float(result.get("chisq", np.nan)))
            p = np.asarray(result.get("p", []), dtype=float).ravel()
            sol.append(float(np.linalg.norm(p)) if p.size else float("nan"))
        self._l_curve_log10_nu = np.log10(nu_grid)
        self._l_curve_chi2 = np.asarray(chi2, dtype=float)
        self._l_curve_sol_norm = np.asarray(sol, dtype=float)
        try:
            mask = np.isfinite(self._l_curve_chi2) & np.isfinite(self._l_curve_sol_norm)
            self._l_curve_corner_index = int(cs.core.math.regularization.discrete_lcurve_corner(self._l_curve_chi2[mask], self._l_curve_sol_norm[mask]))
        except Exception:
            self._l_curve_corner_index = None

    def update_model(self, **kwargs) -> None:
        """Run MaxEnt FRET inversion and update the model curve."""
        data = getattr(self.fit, "data", None)
        decay = np.asarray(getattr(data, "y", []), dtype=float).ravel()
        if decay.size == 0:
            self.x = np.array([], dtype=float)
            self.y = np.array([], dtype=float)
            self._last_result = None
            return
        irf = _irf_like_decay(self, decay.size)
        self._last_result = solve_fret_mem(
            decay=decay,
            lamp=irf,
            dt=_data_dt(self.fit),
            R=self.distance_grid,
            tau0=float(self.fret_parameters.tauD0),
            R0=float(self.fret_parameters.forster_radius),
            donly=np.asarray(self.donor_lifetime_spectrum, dtype=float).ravel(),
            x_donly=float(self.fret_parameters.xDOnly),
            timeshift=_as_float(getattr(self.convolve, "timeshift", None)),
            background=_as_float(getattr(self.generic, "background", None)),
            lamp_scatter=_as_float(getattr(self.generic, "scatter", None)),
            fitrange=_fitrange(self.fit, decay.size),
            irf_background=_as_float(getattr(self.convolve, "lamp_background", None)),
            nu=self.nu,
            max_iter=200,
        )
        fitrange = self._last_result.get("fitrange")
        if fitrange is not None:
            fitstart, fitstop = fitrange
            Fi = self._last_result.get("Fi")
            p = np.asarray(self._last_result.get("p", []), dtype=float).ravel()
            sigma = np.asarray(self._last_result.get("sigma", []), dtype=float).ravel()
            fit_additive = np.asarray(self._last_result.get("fit_additive", []), dtype=float).ravel()
            if Fi is not None and p.size > 0 and sigma.size > 0:
                model_seg = Fi @ p * sigma + fit_additive
                fit_curve = np.zeros(decay.size, dtype=float)
                seg_len = min(model_seg.size, fitstop - fitstart + 1)
                fit_curve[fitstart:fitstart + seg_len] = model_seg[:seg_len]
            else:
                fit_curve = np.zeros_like(decay)
        else:
            fit_curve = np.zeros_like(decay)
        self.x = _data_x(self.fit)
        self.y = np.maximum(fit_curve, 0.0)
