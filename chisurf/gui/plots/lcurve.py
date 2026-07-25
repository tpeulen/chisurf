"""Read-only L-curve plot for regularised model-free fits (e.g. DEER).

Plots the discrete L-curve — residual norm ``||K P - F||`` versus solution
roughness ``||L P||`` in log-log space — for a model that exposes a
``compute_lcurve()`` method returning ``{'rho', 'eta', 'corner', 'used'}``.
The automatically selected corner is highlighted. Purely diagnostic: it does
not modify the fit.
"""

from __future__ import annotations

import numpy as np

from chisurf.gui import chiplot as cp
from chisurf.gui.plots import plotbase


class LCurvePlot(plotbase.Plot):
    """L-curve diagnostic for regularisation-parameter selection."""

    name = "L-Curve"

    def __init__(self, fit, **kwargs):
        """Build the log-log L-curve plot with a highlighted corner marker."""
        super().__init__(fit=fit, **kwargs)
        self._pw = cp.Plot()
        self.layout.addWidget(self._pw)
        self._pw.set_log(x=True, y=True)
        self._pw.grid(x=True, y=True, alpha=0.3)
        self._pw.set_labels(bottom="residual ||K P - F||", left="roughness ||L P||")
        self._curve = self._pw.line(
            [], [], pen=cp.to_pen("#2f80ed", width=2),
            symbol="o", symbol_size=6, symbol_brush="#2f80ed", symbol_pen="w")
        self._corner = self._pw.scatter(
            [], [], symbol="x", size=16, brush="#ffd166", pen="#ffd166")

    def _model(self):
        """Return the selected fit's model, or ``None``."""
        fit = getattr(self.fit, "selected_fit", self.fit)
        return getattr(fit, "model", None)

    def update(self, *args, **kwargs) -> None:
        """Recompute and redraw the L-curve from the current model state."""
        model = self._model()
        fn = getattr(model, "compute_lcurve", None)
        if not callable(fn):
            return
        try:
            data = fn()
        except Exception:
            data = None
        if not data:
            self._curve.set_data([], [])
            self._corner.set_data([], [])
            return
        rho = np.asarray(data.get("rho"), dtype=float)
        eta = np.asarray(data.get("eta"), dtype=float)
        ok = np.isfinite(rho) & np.isfinite(eta) & (rho > 0) & (eta > 0)
        self._curve.set_data(rho[ok], eta[ok])
        c = data.get("corner")
        if c is not None and 0 <= int(c) < rho.size and ok[int(c)]:
            self._corner.set_data([rho[int(c)]], [eta[int(c)]])
        else:
            self._corner.set_data([], [])
