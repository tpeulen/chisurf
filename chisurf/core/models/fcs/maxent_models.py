"""Maximum-entropy FCS models: distributions of diffusion time and of size.

Both models invert one correlation curve into a *distribution* rather than a
handful of components, so the quantity that decides the answer is the
regularization weight — too little and the distribution fits the noise, too much
and every peak merges. That is what the L-curve is for, and why both models
sample it themselves (:meth:`compute_l_curve`) and expose the result as the
shared :class:`chisurf.core.math.regularization.LCurveData` the reusable
``lcurve`` view renders.

The numerics live in :mod:`chisurf.core.models.fcs.maxent`; these classes only
adapt the model parameters and the fit window to it.
"""
from __future__ import annotations

import logging

import numpy as np

import chisurf.core.fitting
import chisurf.core.math.regularization
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.fcs.maxent import (
    compute_fcs_maxent_l_curve,
    compute_fcs_maxent_rh_l_curve,
    fcs_maxent,
    fcs_maxent_rh,
)
from chisurf.core.models.model import ModelCurve


class _MaxEntFCSBase(ModelCurve):
    """Shared L-curve bookkeeping for the two MaxEnt FCS models.

    Both models sweep the same scalar (``log10`` of the entropy weight) and cache
    the sweep in the same private arrays; only the solver they call and the grid
    they recover the distribution on differ.
    """

    def _init_l_curve_state(self) -> None:
        """Reset the cached sweep. Called at the end of each subclass ``__init__``."""
        self._result = None
        self._l_curve_log10_reg = None
        self._l_curve_chi2 = None
        self._l_curve_solution_norm = None
        self._l_curve_corner_index = None

    @property
    def last_result(self) -> dict | None:
        """The last MaxEnt result dictionary, or ``None`` before the first update."""
        return self._result

    @property
    def l_curve_log10_reg(self) -> np.ndarray:
        """The ``log10(reg)`` grid the sweep was evaluated on (empty before a sweep)."""
        if self._l_curve_log10_reg is None:
            return np.array([], dtype=float)
        return np.asarray(self._l_curve_log10_reg, dtype=float)

    @property
    def l_curve_reg(self) -> np.ndarray:
        """The sweep's regularization weights on a linear scale."""
        vals = self.l_curve_log10_reg
        return vals if vals.size == 0 else 10.0 ** vals

    @property
    def l_curve_chi2(self) -> np.ndarray:
        r"""Reduced :math:`\chi^2` at each swept weight (the L-curve x-axis)."""
        if self._l_curve_chi2 is None:
            return np.array([], dtype=float)
        return np.asarray(self._l_curve_chi2, dtype=float)

    @property
    def l_curve_solution_norm(self) -> np.ndarray:
        """Norm of the recovered distribution at each swept weight (the y-axis)."""
        if self._l_curve_solution_norm is None:
            return np.array([], dtype=float)
        return np.asarray(self._l_curve_solution_norm, dtype=float)

    @property
    def l_curve(self) -> chisurf.core.math.regularization.LCurveData | None:
        """The cached sweep as the shared L-curve data model.

        Returns ``None`` until :meth:`compute_l_curve` has run. This is the
        ``target`` of the ``lcurve`` view section, so the sweep the model already
        performs is finally visible instead of being used only internally.
        """
        chi2 = self.l_curve_chi2
        sol = self.l_curve_solution_norm
        if chi2.size == 0 or sol.size == 0:
            return None
        return chisurf.core.math.regularization.LCurveData(
            reg=self.l_curve_reg,
            residual_norm=chi2,
            solution_norm=sol,
            corner_index=self.l_curve_corner_index(),
        )

    def _l_curve_window(
        self,
        n_points: int | None,
        log10_min: float | None,
        log10_max: float | None,
    ) -> tuple[int, float, float] | None:
        """Resolve the sweep window from the arguments and the current weight.

        Parameters
        ----------
        n_points : int or None
            Requested number of grid points; at least two are used.
        log10_min, log10_max : float or None
            Requested ``log10(reg)`` bounds. When omitted, the current weight
            ± 2 decades, clipped to the parameter's own bounds.

        Returns
        -------
        tuple or None
            ``(n_points, log10_min, log10_max)``, or ``None`` when the data are
            empty — in which case the cached sweep has been cleared.
        """
        data = self.fit.data
        if np.asarray(data.x).size == 0 or np.asarray(data.y).size == 0:
            self._l_curve_log10_reg = np.array([], dtype=float)
            self._l_curve_chi2 = np.array([], dtype=float)
            self._l_curve_solution_norm = np.array([], dtype=float)
            self._l_curve_corner_index = None
            return None

        n_points = 2 if n_points is None or int(n_points) <= 1 else int(n_points)
        current_log10 = float(self._reg.value)
        try:
            lb, ub = [float(b) for b in self._reg.bounds]
        except (TypeError, ValueError):
            lb, ub = float("-inf"), float("inf")
        if log10_min is None:
            log10_min = max(lb, current_log10 - 2.0)
        if log10_max is None:
            log10_max = min(ub, current_log10 + 2.0)
        if log10_min > log10_max:
            log10_min, log10_max = log10_max, log10_min
        return n_points, float(log10_min), float(log10_max)

    def _store_l_curve(self, result) -> None:
        """Cache a sweep result and recompute the model at the current weight."""
        self._l_curve_log10_reg = result.log10_reg
        self._l_curve_chi2 = result.chi2r
        self._l_curve_solution_norm = result.solution_norm
        self._l_curve_corner_index = result.corner_index
        self.update_model()

    def l_curve_corner_index(self) -> int | None:
        """Index of the automatically detected L-curve corner, or ``None``.

        The index refers to the cached sweep arrays (:attr:`l_curve_log10_reg`
        and friends).
        """
        if self._l_curve_corner_index is not None:
            return int(self._l_curve_corner_index)
        rho = self.l_curve_chi2
        eta = self.l_curve_solution_norm
        if rho.size < 3 or eta.size < 3:
            return None
        idx = chisurf.core.math.regularization.discrete_lcurve_corner(rho, eta)
        if idx is None:
            return None
        self._l_curve_corner_index = int(idx)
        return int(idx)

    def set_reg_from_lcurve_index(self, idx: int) -> None:
        """Adopt the regularization weight at a swept L-curve point.

        Writes the parameter directly; the parameter's own controller binding
        repaints the editor. The hand-written version published this through the
        GUI fitting client, so clicking the L-curve did nothing whenever that
        client was absent.

        Parameters
        ----------
        idx : int
            Index into the cached sweep arrays.
        """
        vals = self.l_curve_log10_reg
        if vals.size == 0 or idx < 0 or idx >= vals.size:
            return
        self._reg.value = float(vals[idx])
        self.update()

    def use_l_curve_corner(self) -> None:
        """Adopt the weight at the detected corner (a zero-arg button action)."""
        idx = self.l_curve_corner_index()
        if idx is not None:
            self.set_reg_from_lcurve_index(int(idx))

    def on_auto_fit_range_completed(self) -> None:
        """Sweep the L-curve and adopt its corner after an auto fit-range sweep."""
        try:
            self.compute_l_curve(n_points=32, log10_min=-3.0, log10_max=3.0)
            self.use_l_curve_corner()
        except Exception as exc:
            logging.warning(f"{type(self).__name__}: auto L-curve sweep failed: {exc}")

    def _fit_window(self) -> tuple[int, int | None]:
        """Return the fit window as ``(xmin, xmax)``, an unset window meaning all.

        ``Fit`` starts with ``xmax == 0``: an empty window, not a full one. The
        misfit norm of an empty window is NaN, so the whole L-curve came back
        NaN — no corner, nothing drawn — for any fit whose range had not been set
        yet, which is every fit the moment this model is opened.
        """
        xmin = int(getattr(self.fit, "xmin", 0) or 0)
        xmax = getattr(self.fit, "xmax", None)
        if xmax is None or int(xmax) <= xmin:
            return xmin, None
        return xmin, int(xmax)

    def _data_weights(self) -> np.ndarray | None:
        """Return ``1/sigma`` weights from the data's ``ey``, or ``None``."""
        data = self.fit.data
        ey = getattr(data, "ey", None)
        if ey is None:
            return None
        ey_arr = np.asarray(ey, dtype=float).ravel()
        if ey_arr.size != np.asarray(data.y, dtype=float).ravel().size:
            return None
        return 1.0 / np.maximum(ey_arr, 1e-12)


class MaxEntFCSModel(_MaxEntFCSBase):
    """FCS model recovering a *distribution of diffusion times* by MaxEnt.

    The correlation curve is inverted onto a log-spaced grid of diffusion times
    ``td_min … td_max``; the recovered distribution is what the model is for, and
    the reconstructed curve is what the fit is scored against.
    """

    name = "FCS MaxEnt"
    view_spec_file = "maxent_fcs.view.json"

    def __init__(self, fit: chisurf.core.fitting.fit.Fit, **kwargs):
        """Initialize the MaxEnt diffusion-time model.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            The fit this model belongs to.
        **kwargs
            Additional keyword arguments forwarded to the base class.
        """
        super().__init__(fit, **kwargs)

        # The entropy weight is carried as log10 for stability: it spans decades
        # and the L-curve is swept on that scale.
        self._reg = FittingParameter(
            name="reg", label_text="reg", value=-3.0, lb=-6.0, ub=3.0,
            bounds_on=True, fixed=True,
        )
        self._td_min = FittingParameter(
            name="td_min", label_text="t<sub>d,min</sub>[ms]", value=1.0e-4,
            lb=0.0, ub=float("inf"), bounds_on=True, fixed=True,
        )
        self._td_max = FittingParameter(
            name="td_max", label_text="t<sub>d,max</sub>[ms]", value=20.0,
            lb=0.0, ub=float("inf"), bounds_on=True, fixed=True,
        )
        self._n_td = FittingParameter(
            name="n_td", label_text="n<sub>td</sub>", value=64.0, lb=10.0, ub=400.0,
            bounds_on=True, fixed=True,
        )
        self._s = FittingParameter(
            name="s", label_text="s", value=3.5, lb=0.1, ub=20.0,
            bounds_on=True, fixed=True,
        )
        self._b = FittingParameter(
            name="b", label_text="b", value=1.0, lb=-10.0, ub=10.0,
            bounds_on=True, fixed=True,
        )

        self.find_parameters()
        self._init_l_curve_state()

    def _maxent_parameter_rows(self) -> list:
        """Return the entropy weight and the diffusion-time grid, in order."""
        return [self._reg, self._td_min, self._td_max, self._n_td, self._s, self._b]

    @property
    def maxent_tauD_distribution(self):
        """The recovered distribution as ``(p, td_grid)``, empty before the first update."""
        if self._result is None:
            return np.array([], dtype=float), np.array([], dtype=float)
        return (
            np.asarray(self._result["p"], dtype=float),
            np.asarray(self._result["td_grid"], dtype=float),
        )

    def compute_l_curve(
        self,
        n_points: int = 32,
        log10_min: float | None = None,
        log10_max: float | None = None,
    ) -> None:
        """Sweep the entropy weight and cache the L-curve.

        Parameters
        ----------
        n_points : int, optional
            Number of grid points.
        log10_min, log10_max : float, optional
            ``log10(reg)`` range. Defaults to the current weight ± 2 decades.
        """
        window = self._l_curve_window(n_points, log10_min, log10_max)
        if window is None:
            return
        n_points, log10_min, log10_max = window
        xmin, xmax = self._fit_window()
        data = self.fit.data
        self._store_l_curve(
            compute_fcs_maxent_l_curve(
                tau=np.asarray(data.x, dtype=float).ravel(),
                g=np.asarray(data.y, dtype=float).ravel(),
                y_error=getattr(data, "ey", None),
                log10_min=log10_min,
                log10_max=log10_max,
                n_points=n_points,
                xmin=xmin,
                xmax=xmax,
                mask=getattr(self.fit, "mask", None),
                n_free=int(self.n_free),
                td_min=float(self._td_min.value) if float(self._td_min.value) > 0.0 else None,
                td_max=float(self._td_max.value) if float(self._td_max.value) > 0.0 else None,
                n_td=int(self._n_td.value) if int(self._n_td.value) > 0 else 80,
                s=float(self._s.value),
                baseline=float(self._b.value),
                num_iter=60,
            )
        )

    def update_model(self, **kwargs) -> None:
        """Run the MaxEnt inversion and store the reconstructed correlation curve.

        Parameters
        ----------
        **kwargs
            Additional keyword arguments accepted for signature compatibility.
        """
        data = self.fit.data
        tau = np.asarray(data.x, dtype=float).ravel()
        g = np.asarray(data.y, dtype=float).ravel()
        if tau.size == 0 or g.size == 0:
            self.x = np.array([], dtype=float)
            self.y = np.array([], dtype=float)
            self._result = None
            return

        td_min = float(self._td_min.value) if float(self._td_min.value) > 0.0 else None
        td_max = float(self._td_max.value) if float(self._td_max.value) > 0.0 else None
        n_td = int(self._n_td.value) if float(self._n_td.value) > 0.0 else 80
        s_val = float(self._s.value) if float(self._s.value) > 0.0 else 3.5

        self._result = fcs_maxent(
            tau=tau,
            g=g,
            td_min=td_min,
            td_max=td_max,
            n_td=n_td,
            s=s_val,
            baseline=float(self._b.value),
            reg=10.0 ** float(self._reg.value),
            weights=self._data_weights(),
        )
        self.x = self._result["tau"]
        self.y = self._result["g_fit"]


class MaxEntRHModel(_MaxEntFCSBase):
    """FCS model recovering a *distribution of hydrodynamic radii* by MaxEnt.

    The same inversion as :class:`MaxEntFCSModel`, but the grid is a size axis:
    the diffusion time of each radius follows from the beam waist ``w0`` and the
    Stokes-Einstein relation at the sample temperature, so the recovered
    distribution reads directly in nanometres.
    """

    name = "FCS MaxEnt rH"
    view_spec_file = "maxent_rh.view.json"

    def __init__(self, fit: chisurf.core.fitting.fit.Fit, **kwargs):
        """Initialize the MaxEnt hydrodynamic-radius model.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            The fit this model belongs to.
        **kwargs
            Additional keyword arguments forwarded to the base class.
        """
        super().__init__(fit, **kwargs)

        self._reg = FittingParameter(
            name="reg", label_text="reg", value=-4.0, lb=-6.0, ub=3.0,
            bounds_on=True, fixed=True,
        )
        self._rh_min = FittingParameter(
            name="rh_min", label_text="r<sub>h,min</sub>[nm]", value=0.01,
            lb=0.001, ub=1000.0, bounds_on=True, fixed=True,
        )
        self._rh_max = FittingParameter(
            name="rh_max", label_text="r<sub>h,max</sub>[nm]", value=500.0,
            lb=0.01, ub=1000.0, bounds_on=True, fixed=True,
        )
        self._n_rh = FittingParameter(
            name="n_rh", label_text="n<sub>rh</sub>", value=128.0, lb=10.0, ub=400.0,
            bounds_on=True, fixed=True,
        )
        self._s = FittingParameter(
            name="s", label_text="s", value=3.5, lb=0.1, ub=20.0,
            bounds_on=True, fixed=True,
        )
        self._b = FittingParameter(
            name="b", label_text="b", value=1.0, lb=-10.0, ub=10.0,
            bounds_on=True, fixed=True,
        )
        # Beam waist in nanometres for the UI; the solver takes micrometres.
        self._w0 = FittingParameter(
            name="w0", label_text="w<sub>0</sub>[nm]", value=350.0, lb=10.0, ub=5000.0,
            bounds_on=True, fixed=True,
        )
        self._temp = FittingParameter(
            name="temp", label_text="temp[°C]", value=20.0, lb=-50.0, ub=200.0,
            bounds_on=True, fixed=True,
        )

        self.find_parameters()
        self._init_l_curve_state()

    def _maxent_parameter_rows(self) -> list:
        """Return the entropy weight and the radius grid, in order."""
        return [self._reg, self._rh_min, self._rh_max, self._n_rh, self._s, self._b]

    def _optics_parameter_rows(self) -> list:
        """Return the quantities that turn a diffusion time into a radius."""
        return [self._w0, self._temp]

    @property
    def maxent_rH_distribution(self):
        """The recovered distribution as ``(p, rh_grid)``, empty before the first update."""
        if self._result is None:
            return np.array([], dtype=float), np.array([], dtype=float)
        return (
            np.asarray(self._result["p"], dtype=float),
            np.asarray(self._result["rh_grid"], dtype=float),
        )

    def compute_l_curve(
        self,
        n_points: int = 32,
        log10_min: float | None = None,
        log10_max: float | None = None,
    ) -> None:
        """Sweep the entropy weight and cache the L-curve.

        Parameters
        ----------
        n_points : int, optional
            Number of grid points.
        log10_min, log10_max : float, optional
            ``log10(reg)`` range. Defaults to the current weight ± 2 decades.
        """
        window = self._l_curve_window(n_points, log10_min, log10_max)
        if window is None:
            return
        n_points, log10_min, log10_max = window
        xmin, xmax = self._fit_window()
        data = self.fit.data
        self._store_l_curve(
            compute_fcs_maxent_rh_l_curve(
                tau=np.asarray(data.x, dtype=float).ravel(),
                g=np.asarray(data.y, dtype=float).ravel(),
                y_error=getattr(data, "ey", None),
                log10_min=log10_min,
                log10_max=log10_max,
                n_points=n_points,
                xmin=xmin,
                xmax=xmax,
                mask=getattr(self.fit, "mask", None),
                n_free=int(self.n_free),
                rh_min=float(self._rh_min.value),
                rh_max=float(self._rh_max.value),
                n_rh=int(self._n_rh.value) if int(self._n_rh.value) > 0 else 80,
                w0=float(self._w0.value) * 1.0e-3,
                s=float(self._s.value),
                baseline=float(self._b.value),
                temperature=float(self._temp.value) + 273.15,
                num_iter=60,
            )
        )

    def update_model(self, **kwargs) -> None:
        """Run the MaxEnt inversion in radius space and store the model curve.

        Parameters
        ----------
        **kwargs
            Additional keyword arguments accepted for signature compatibility.
        """
        data = self.fit.data
        tau = np.asarray(data.x, dtype=float).ravel()
        g = np.asarray(data.y, dtype=float).ravel()
        if tau.size == 0 or g.size == 0:
            self.x = np.array([], dtype=float)
            self.y = np.array([], dtype=float)
            self._result = None
            return

        rh_min = max(float(self._rh_min.value), 1.0e-3)
        rh_max = max(float(self._rh_max.value), rh_min * 1.001)
        n_rh = int(self._n_rh.value) if float(self._n_rh.value) > 0.0 else 80
        s_val = float(self._s.value) if float(self._s.value) > 0.0 else 3.5

        self._result = fcs_maxent_rh(
            tau=tau,
            g=g,
            rh_min=rh_min,
            rh_max=rh_max,
            n_rh=n_rh,
            w0=float(self._w0.value) * 1.0e-3,
            s=s_val,
            baseline=float(self._b.value),
            reg=10.0 ** float(self._reg.value),
            temperature=float(self._temp.value) + 273.15,
            weights=self._data_weights(),
        )
        self.x = self._result["tau"]
        self.y = self._result["g_fit"]
