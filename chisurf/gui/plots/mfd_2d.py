"""The 1D marginals of an MFD fit, data and model overlaid.

The 2D maps live in the AutoForm ``image`` dock on the model panel, which brings a
colormap selector, a channel selector, real-world axes and a rectangle gate with no
code here — so this plot is what the maps cannot show: the two **marginals**, with
the measurement and the model drawn on the same axes rather than side by side.

A side-by-side pair of images is a poor comparison. Two curves on one axis is a good
one: a systematic offset, a width mismatch or a missing population is obvious in a
way that two heat maps at 40% width each never make it.

Everything goes through :mod:`chisurf.gui.chiplot`. pyqtgraph is a backend behind
that seam and anything reaching past it falls through with a warning rather than
failing, so a passthrough is a silent parity bug — which is why the tests assert
this module produces none.
"""

from __future__ import annotations

import numpy as np

from chisurf.gui import QtWidgets
from chisurf.gui import chiplot as cp
from chisurf.gui.plots import plotbase

#: Measurement and model, in the two colours the rest of the application uses for
#: "what was seen" and "what is claimed".
DATA_PEN = "#8ab4f8"
MODEL_PEN = "#f28b82"


def _payload(fit):
    """Return the MFD objects a fit's dataset carries, or ``None``."""
    data = getattr(fit, "data", None)
    if data is None:
        return None
    payload = getattr(data, "mfd", None)
    if payload is not None:
        return payload
    meta = getattr(data, "meta_data", None) or {}
    payload = meta.get("mfd_data")
    if payload is not None:
        return payload
    if isinstance(data, list):
        for member in data:
            payload = getattr(member, "mfd", None)
            if payload is not None:
                return payload
    return None


class MfdMarginalPlot(plotbase.Plot):
    """Proximity-ratio and mean-micro-time marginals, measurement against model."""

    name = "MFD marginals"

    def __init__(self, fit, parent=None, **kwargs):
        """Build the two marginal panels.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            The fit whose data and model are shown.
        parent : QtWidgets.QWidget, optional
            Parent widget.
        **kwargs
            Ignored; present for the plot-spec signature.
        """
        super().__init__(fit, parent=parent, **kwargs)

        self.grid = cp.Grid()
        self.layout.addWidget(self.grid)

        self.ratio_plot = self.grid.add_plot(row=0, col=0)
        self.micro_plot = self.grid.add_plot(row=1, col=0)
        self.ratio_plot.set_title("proximity ratio")
        self.micro_plot.set_title("mean micro time")
        self.ratio_plot.set_labels(bottom="N_R / (N_G + N_R)", left="bursts")
        self.micro_plot.set_labels(bottom="⟨t⟩ / ns", left="bursts")
        for plot in (self.ratio_plot, self.micro_plot):
            # A ratio and a nanosecond have no unit to prefix, so an automatic SI
            # prefix relabels the axis "(x0.001)" with ticks running to 400.
            plot.set_si_prefix(x=False)
            plot.grid(x=True, y=True, alpha=0.15)

        self.ratio_data = self.ratio_plot.line(
            [], [], pen=cp.to_pen(DATA_PEN, width=2), name="measured"
        )
        self.ratio_model = self.ratio_plot.line(
            [], [], pen=cp.to_pen(MODEL_PEN, width=2), name="model"
        )
        self.micro_data = self.micro_plot.line(
            [], [], pen=cp.to_pen(DATA_PEN, width=2), name="measured"
        )
        self.micro_model = self.micro_plot.line(
            [], [], pen=cp.to_pen(MODEL_PEN, width=2), name="model"
        )
        self.ratio_plot.legend()

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        self.layout.addWidget(self.status)

    def update_all(self, *args, **kwargs) -> None:
        """Redraw both marginals from the fit's current data and model."""
        payload = _payload(self.fit)
        if payload is None:
            self.status.setText("No MFD dataset.")
            return

        axes = payload.axes
        observed = np.asarray(payload.observed.counts, dtype=float)
        model = getattr(self.fit, "model", None)
        flat = getattr(model, "y", None) if model is not None else None
        if flat is not None and np.asarray(flat).size == observed.size:
            predicted = np.asarray(flat, dtype=float).reshape(
                observed.shape, order="C"
            )
        else:
            predicted = np.zeros_like(observed)

        ratio = 0.5 * (axes.ratio_edges[:-1] + axes.ratio_edges[1:])
        micro = 0.5 * (axes.micro_time_edges[:-1] + axes.micro_time_edges[1:])

        self.ratio_data.set_data(ratio, observed.sum(axis=1))
        self.ratio_model.set_data(ratio, predicted.sum(axis=1))
        self.micro_data.set_data(micro, observed.sum(axis=0))
        self.micro_model.set_data(micro, predicted.sum(axis=0))

        # Ranges last: every ``set_data`` re-triggers the renderer's auto-range, so
        # a range set earlier is replaced by whichever curve was drawn last.
        self.ratio_plot.set_range(
            x=(float(axes.ratio_edges[0]), float(axes.ratio_edges[-1])), padding=0.0
        )
        self.micro_plot.set_range(
            x=(float(axes.micro_time_edges[0]), float(axes.micro_time_edges[-1])),
            padding=0.0,
        )

        summary = payload.observed.summary
        self.status.setText(
            f"{summary['n_used']} / {summary['n_input']} bursts, "
            f"{summary['excluded_fraction']:.1%} excluded at "
            f"{summary['min_green_photons']} donor photons — a cut that removes "
            "high-FRET bursts preferentially, so these are not population fractions."
        )

    def update(self, *args, **kwargs) -> None:
        """Redraw, then run the base-class update."""
        self.update_all()
        super().update(*args, **kwargs)


#: Kept so a view spec naming the old key still resolves to something drawable.
Mfd2DPlot = MfdMarginalPlot
