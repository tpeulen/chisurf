from __future__ import annotations

import numpy as np

import chisurf.core.fitting
from chisurf.gui import chiplot as cp
from chisurf.gui.plots import plotbase

color_scheme = chisurf.core.settings.colors


def _member_fits(fit):
    """Return the member fits of *fit* as a list.

    A :class:`~chisurf.core.fitting.fit.FitGroup` iterates over its members, but
    a plain :class:`~chisurf.core.fitting.fit.Fit` is not iterable -- so
    constructing this plot with a single Fit raised
    ``TypeError: 'Fit' object is not iterable``. A lone fit is simply a group of
    one.
    """
    try:
        return list(fit)
    except TypeError:
        return [fit]


class ResidualPlot(plotbase.Plot):

    name = "Residuals"

    def __init__(self, fit: chisurf.core.fitting.fit.FitGroup, *args, **kwargs):
        super().__init__(*args, fit=fit, **kwargs)
        self.data_x, self.data_y = None, None

        curves = list()
        lw = chisurf.core.settings.gui['plot']['line_width']

        p = cp.Plot()
        self.layout.addWidget(p)

        try:
            p.set_labels(left='w.res.')
        except Exception:
            pass

        for i, f in enumerate(_member_fits(fit)):
            color = chisurf.core.settings.colors[i % len(chisurf.core.settings.colors)]['hex']
            c = p.line([], [], pen=cp.to_pen(color, width=lw), name=f.data.name)
            curves.append(c)
        self.curves = curves

    def update(self, *args, **kwargs) -> None:
        super().update(*args, **kwargs)
        # Get parameters from plot-control. Each member's residuals are stacked
        # by a constant vertical offset (i*6), applied to the y-data (equivalent
        # to the former per-item setPos, without needing an item-offset API).
        fits = _member_fits(self.fit)
        for i, (ci, fi) in enumerate(zip(self.curves, fits)):
            w_res = fi.model.weighted_residuals
            x = np.arange(len(w_res))
            ci.set_data(x, w_res + i * 6)
