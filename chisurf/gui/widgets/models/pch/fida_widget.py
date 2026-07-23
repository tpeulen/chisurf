"""FIDA fit model for the PCH experiment (Fluorescence-Intensity Distribution Analysis).

A photon-counting-histogram fit model that, unlike ``PchMultiComponentModel``,
computes the histogram through the FIDA probability generating function with an
explicit spatial brightness profile (see
:mod:`chisurf.core.models.pch.fida`).  It recovers per-species molecular
brightness ``q`` and mean number ``N`` (Kask et al., PNAS 1999).
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from qtpy import QtWidgets, QtCore, QtGui

import chisurf as cs
import chisurf.core.fitting
from chisurf.core.models.model import ModelCurve
from chisurf.core.models.pch import fida
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.gui import plots
from chisurf.gui.widgets.models.model_widget import ModelWidget
import chisurf.gui.widgets.fitting.widgets as fitting_widgets


class FidaModel(ModelCurve):
    """FIDA photon-counting-histogram model (up to three species + background)."""

    name = "FIDA"

    def __init__(self, fit: "cs.core.fitting.fit.Fit", *args: Any, **kwargs: Any) -> None:
        super().__init__(fit, *args, **kwargs)

        def _p(name, value, fixed=False, lb=0.0, ub=1.0e6):
            return FittingParameter(name=name, value=value, lb=lb, ub=ub,
                                    bounds_on=False, fixed=fixed, registry_id=f"fida.{name}")

        self._q1 = _p("q1", 2.0)
        self._N1 = _p("N1", 2.0)
        self._q2 = _p("q2", 0.0)
        self._N2 = _p("N2", 0.0)
        self._q3 = _p("q3", 0.0)
        self._N3 = _p("N3", 0.0)
        self._bg = _p("bg", 0.0)
        # Derived: total mean count per bin (output only).
        self._mean = FittingParameter(name="mean", value=float("nan"),
                                      fixed=True, is_output=True)

        try:
            self.find_parameters()
        except Exception:
            pass

    def update_model(self, **kwargs: Any) -> None:  # type: ignore[override]
        fit = getattr(self.fit, "selected_fit", self.fit)
        data = getattr(fit, "data", None)
        meta = getattr(data, "meta_data", {}) or {}
        k_vals = (meta.get("pch", {}) or {}).get("k_vals", getattr(data, "x", None))
        try:
            k = np.asarray(k_vals, dtype=float)
        except Exception:
            k = np.array([], dtype=float)

        if k.size == 0:
            self.x = np.array([], dtype=float)
            self.y = np.array([], dtype=float)
            return

        q = np.array([self._q1.value, self._q2.value, self._q3.value], dtype=float)
        n = np.array([self._N1.value, self._N2.value, self._N3.value], dtype=float)
        mask = (q > 0.0) & (n > 0.0)
        species = list(zip(q[mask], n[mask]))
        bg = float(self._bg.value)

        k_max = int(round(float(k.max())))
        if not species and bg <= 0.0:
            y = np.zeros(k_max + 1, dtype=float)
            y[0] = 1.0
        else:
            y = fida.fida_pch(k_max, species, background=max(bg, 0.0))

        # Map P(0..k_max) onto the data's k grid (k_vals are integer photon counts).
        idx = np.clip(np.round(k).astype(int), 0, y.size - 1)
        y_model = y[idx]

        self._set_mean(float((np.arange(y.size) * y).sum()))
        self.x = k
        self.y = y_model

    def _set_mean(self, value: float) -> None:
        try:
            self._mean.value = value
            from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

            fc = get_fitting_client()
            if fc is not None:
                fit_idx = getattr(self.fit, "fit_idx", None)
                fc.set_parameter_value(parameter_name="mean", value=value, fit_index=fit_idx)
                fc.set_parameter_fixed(parameter_name="mean", fixed=True, fit_index=fit_idx)
        except Exception:
            pass


class FidaModelWidget(ModelWidget, FidaModel):
    """Qt widget wrapping :class:`FidaModel`."""

    name = "FIDA"

    plot_classes = [
        (
            plots.LinePlot,
            {"scale_x": "lin", "d_scaley": "log", "r_scaley": "lin",
             "x_label": "photons / bin", "y_label": "frequency"},
        ),
        (plots.FitTablePlot, {}),
        (plots.FitInfo, {}),
        (cs.gui.plots.ResidualPlot, {}),
    ]

    def __init__(
        self,
        fit: "cs.core.fitting.fit.FitGroup",
        icon: Optional[QtGui.QIcon] = None,
        **kwargs,
    ):
        if icon is None:
            icon = QtGui.QIcon(":/icons/icons/pch.png")
        super().__init__(fit=fit, icon=icon, **kwargs)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignTop)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        mfw = fitting_widgets.make_fitting_parameter_widget
        for p, lbl in [
            (self._q1, "q<sub>1</sub>"), (self._N1, "N<sub>1</sub>"),
            (self._q2, "q<sub>2</sub>"), (self._N2, "N<sub>2</sub>"),
            (self._q3, "q<sub>3</sub>"), (self._N3, "N<sub>3</sub>"),
            (self._bg, "bg"), (self._mean, "mean"),
        ]:
            layout.addWidget(mfw(p, label_text=lbl))
        self.setLayout(layout)
        self.layout = layout
