"""P(r) distance-distribution plot with a bootstrap confidence band (DEER).

Draws the fitted distance distribution ``P(r)`` as a line with a shaded
pointwise confidence band, for a model exposing ``compute_uncertainty()`` that
returns ``(r, p_best, p_lo, p_hi)``. Diagnostic only; recomputed on demand.
"""

from __future__ import annotations

import numpy as np

from chisurf.gui import chiplot as cp
from chisurf.gui.plots import plotbase


class DeerPrCIPlot(plotbase.Plot):
    """Distance distribution with a shaded 95% confidence band."""

    name = "P(r) 95% CI"

    def __init__(self, fit, n_boot: int = 60, **kwargs):
        """Build the P(r) plot with a fill-between confidence band."""
        super().__init__(fit=fit, **kwargs)
        self._n_boot = int(n_boot)
        self._pw = self.add_panel()
        self._pw.set_labels(bottom="r (Å)", left="P(r)")
        self._pw.grid(x=True, y=True, alpha=0.3)
        self._lo = self._pw.line([], [], pen=(47, 128, 237, 90))
        self._hi = self._pw.line([], [], pen=(47, 128, 237, 90))
        self._band = self._pw.fill_between(self._lo, self._hi, brush=(47, 128, 237, 70))
        self._best = self._pw.line([], [], pen=cp.to_pen("#2f80ed", width=2))

    def _model(self):
        """Return the selected fit's model, or ``None``."""
        fit = getattr(self.fit, "selected_fit", self.fit)
        return getattr(fit, "model", None)

    def update(self, *args, **kwargs) -> None:
        """Mark the band stale; it is recomputed when the page is next drawn.

        The bootstrap is expensive, so it must not re-run on every fit iteration
        while this tab is out of view and stall the fit. A page that is drawn is
        in view, so drawing is where the band is brought up to date.
        """
        self._stale = True
        self.request_redraw()

    def emtk_draw(self, box) -> None:
        """Bring the band up to date if the fit changed, then draw the panel."""
        from emtk import im

        from chisurf.gui.plots.emtk_page import PanelItem

        if getattr(self, "_stale", True):
            self.recompute()
        if not getattr(self, "panel_items", None):
            self.panel_items = [PanelItem(self._pw, self._pw.control())]
        width, height = im.get_content_region_avail()
        im.host_control("##deer-pr-ci", self.panel_items[0], (width, height))

    def recompute(self) -> None:
        """Run the bootstrap and set the band."""
        self._stale = False
        model = self._model()
        fn = getattr(model, "compute_uncertainty", None)
        if not callable(fn):
            return
        try:
            out = fn(n_boot=self._n_boot)
        except Exception:
            out = None
        if not out:
            self._best.set_data([], [])
            self._lo.set_data([], [])
            self._hi.set_data([], [])
            return
        r, best, lo, hi = (np.asarray(a, dtype=float) for a in out)
        self._best.set_data(r, best)
        self._lo.set_data(r, lo)
        self._hi.set_data(r, hi)
