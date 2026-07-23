"""Enderlein Gauss--Lorentz MDF FCS model (non-parse, numerically computed).

Unlike the formula-string ``ParseFCSWidget`` models, this is a Python-computed
:class:`~chisurf.core.models.model.ModelCurve` that evaluates the diffusion
autocorrelation of the Enderlein molecule-detection function (MDF) by numerical
integration (see :mod:`chisurf.core.fluorescence.fcs.enderlein`).  It yields an
accurate effective volume — hence an absolute concentration — without the 3-D
Gaussian approximation, and is the basis for two-focus / dual-focus calibration.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from qtpy import QtWidgets, QtCore, QtGui

import chisurf as cs
import chisurf.core.fitting
from chisurf.core.models.model import ModelCurve
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.fluorescence.fcs import enderlein
from chisurf.gui import plots
from chisurf.gui.widgets.models.model_widget import ModelWidget
import chisurf.gui.widgets.fitting.widgets as fitting_widgets

# Avogadro constant for the concentration output (1/mol).
_NA = 6.02214076e23


class MdfFCSModel(ModelCurve):
    """Enderlein Gauss--Lorentz MDF diffusion FCS model.

    Fitting parameters
    ------------------
    N : particle number in the effective volume (amplitude ``1/N``).
    D : translational diffusion coefficient (µm²/s).
    w0 : lateral 1/e² excitation beam radius at focus (nm).
    R0 : emission-beam waist parameter at focus (nm).
    b : constant baseline offset.

    Optical parameters (fixed by default): excitation/emission wavelength (nm),
    refractive index, pinhole diameter (µm), magnification.

    Output parameters
    -----------------
    Veff : effective detection volume (fL).
    conc : concentration ``N / (Veff · NA)`` (nM).
    tauD : lateral diffusion time ``w0² / (4D)`` (ms).

    The correlation lag ``data.x`` is taken in **milliseconds** (matching the
    other ChiSurf FCS models) and converted to seconds internally.
    """

    name = "FCS MDF (Gauss-Lorentz)"

    def __init__(self, fit: "cs.core.fitting.fit.Fit", **kwargs):
        super().__init__(fit, **kwargs)

        self._N = FittingParameter(name="N", value=1.0, lb=1e-6, ub=1e9, fixed=False)
        self._D = FittingParameter(name="D", value=300.0, lb=1e-3, ub=1e5, fixed=False)
        self._w0 = FittingParameter(name="w0", value=250.0, lb=10.0, ub=5000.0, fixed=False)
        self._R0 = FittingParameter(name="R0", value=250.0, lb=10.0, ub=5000.0, fixed=False)
        self._b = FittingParameter(name="b", value=0.0, lb=-10.0, ub=10.0, fixed=False)

        # Optical parameters (fixed by default; expose so a known setup is edited).
        self._lam_ex = FittingParameter(name="lam_ex", value=485.0, lb=200.0, ub=1200.0, fixed=True)
        self._lam_em = FittingParameter(name="lam_em", value=520.0, lb=200.0, ub=1200.0, fixed=True)
        self._n = FittingParameter(name="n", value=1.33, lb=1.0, ub=2.0, fixed=True)
        self._pinhole = FittingParameter(name="pinhole", value=50.0, lb=1.0, ub=1000.0, fixed=True)
        self._mag = FittingParameter(name="mag", value=60.0, lb=1.0, ub=1000.0, fixed=True)
        # Two-focus inter-focus distance (nm); 0 = single-focus auto-correlation.
        # A known, fixed separation yields an ABSOLUTE diffusion coefficient.
        self._diam = FittingParameter(name="diam", value=0.0, lb=0.0, ub=5000.0, fixed=True)

        # Derived outputs.
        self._Veff = FittingParameter(name="Veff", value=float("nan"), fixed=True, is_output=True)
        self._conc = FittingParameter(name="conc", value=float("nan"), fixed=True, is_output=True)
        self._tauD = FittingParameter(name="tauD", value=float("nan"), fixed=True, is_output=True)

        self.find_parameters()

    def _optics(self) -> enderlein.Optics:
        """Build an :class:`~...enderlein.Optics` from the fixed optical params."""
        return enderlein.Optics(
            excitation_wavelength=float(self._lam_ex.value) * 1e-3,   # nm -> µm
            emission_wavelength=float(self._lam_em.value) * 1e-3,
            refractive_index=float(self._n.value),
            pinhole=float(self._pinhole.value),
            magnification=float(self._mag.value),
        )

    def update_model(self, **kwargs) -> None:
        """Evaluate the Enderlein-MDF diffusion autocorrelation into ``self.y``."""
        data = self.fit.data
        tau_ms = np.asarray(data.x, dtype=float).ravel()
        if tau_ms.size == 0:
            self.x = np.array([], dtype=float)
            self.y = np.array([], dtype=float)
            return

        w0 = float(self._w0.value) * 1e-3   # nm -> µm
        R0 = float(self._R0.value) * 1e-3
        D = float(self._D.value)            # µm²/s
        N = float(self._N.value)
        b = float(self._b.value)
        optics = self._optics()

        if not (math.isfinite(w0) and w0 > 0 and math.isfinite(R0) and R0 > 0
                and math.isfinite(D) and D > 0 and math.isfinite(N) and N != 0):
            self.x = tau_ms
            self.y = np.full_like(tau_ms, float("nan"))
            return

        tau_s = tau_ms * 1e-3
        separation = float(self._diam.value) * 1e-3   # nm -> µm
        y = enderlein.acf(tau_s, N, D, w0, R0, offset=b, optics=optics,
                          n_grid=121, span=30.0, separation=separation)

        # Derived outputs (Veff in µm³ -> fL is 1:1; conc in nM; tauD in ms).
        veff_um3 = enderlein.effective_volume(w0, R0, optics)
        conc_nM = (N / (veff_um3 * 1e-15 * _NA)) * 1e9 if veff_um3 > 0 else float("nan")
        tauD_ms = (w0 * w0) / (4.0 * D) * 1e3
        self._set_output(self._Veff, veff_um3)
        self._set_output(self._conc, conc_nM)
        self._set_output(self._tauD, tauD_ms)

        self.x = tau_ms
        self.y = y

    def _set_output(self, param: FittingParameter, value: float) -> None:
        """Write a derived output parameter (value + keep fixed) via the client."""
        try:
            param.value = value
        except Exception:
            pass
        try:
            from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

            fc = get_fitting_client()
            if fc is not None:
                fit_idx = getattr(self.fit, "fit_idx", None)
                fc.set_parameter_value(parameter_name=str(param.name), value=float(value), fit_index=fit_idx)
                fc.set_parameter_fixed(parameter_name=str(param.name), fixed=True, fit_index=fit_idx)
        except Exception:
            pass


class MdfFCSWidget(ModelWidget, MdfFCSModel):
    """Qt widget wrapping :class:`MdfFCSModel`."""

    name = "FCS MDF (Gauss-Lorentz)"

    plot_classes = [
        (
            plots.LinePlot,
            {
                "scale_x": "log", "d_scaley": "lin", "r_scaley": "lin",
                "x_label": "t_c (ms)", "y_label": "G_c(t_c)",
            },
        ),
        (plots.FitTablePlot, {}),
        (plots.FitInfo, {}),
        (plots.ParameterScanPlot, {}),
        (cs.gui.plots.ResidualPlot, {}),
    ]

    def __init__(
        self,
        fit: "cs.core.fitting.fit.FitGroup",
        icon: Optional[QtGui.QIcon] = None,
        **kwargs,
    ):
        if icon is None:
            icon = QtGui.QIcon(":/icons/icons/fcs.png")
        super().__init__(fit=fit, icon=icon, **kwargs)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignTop)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        params_layout = QtWidgets.QVBoxLayout()
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setSpacing(0)

        mfw = fitting_widgets.make_fitting_parameter_widget
        widgets = [
            mfw(self._N),
            mfw(self._D, suffix=" µm²/s"),
            mfw(self._w0, label_text="w<sub>0</sub>", suffix=" nm"),
            mfw(self._R0, label_text="R<sub>0</sub>", suffix=" nm"),
            mfw(self._b),
            mfw(self._lam_ex, label_text="&lambda;<sub>ex</sub>", suffix=" nm"),
            mfw(self._lam_em, label_text="&lambda;<sub>em</sub>", suffix=" nm"),
            mfw(self._n),
            mfw(self._pinhole, suffix=" µm"),
            mfw(self._mag),
            mfw(self._diam, label_text="d<sub>foci</sub>", suffix=" nm"),
            mfw(self._Veff, suffix=" fL"),
            mfw(self._conc, suffix=" nM"),
            mfw(self._tauD, label_text="&tau;<sub>D</sub>", suffix=" ms"),
        ]
        for w in widgets:
            params_layout.addWidget(w)

        layout.addLayout(params_layout)
        self.setLayout(layout)
        self.layout = layout
