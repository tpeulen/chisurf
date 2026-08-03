"""The MFD plot: data, model, and the analytic lines drawn over both.

Three panels sharing their axes — the measured 2D histogram, the model's, and the
proximity-ratio marginal underneath — with the static and dynamic FRET lines drawn
on top of each image. The lines are what an MFD plot is normally *read* by, so they
stay: what changes is that the model beneath them is now fitted rather than eyeballed.

Everything goes through :mod:`chisurf.gui.chiplot`. pyqtgraph is a backend behind
that seam and anything reaching past it falls through with a warning instead of
failing, so a passthrough is a silent parity bug rather than a loud one — which is
why the plugin test asserts this module produces none.
"""

from __future__ import annotations

import numpy as np

from chisurf.gui import QtWidgets
from chisurf.gui import chiplot as cp
from chisurf.gui.plots import plotbase

#: Colour map for the histograms. Perceptually ordered, so a ridge in the cloud is
#: a ridge rather than an artefact of the palette.
COLORMAP = "CET-L4"


def _payload(fit):
    """Return the MFD objects a fit's dataset carries, or ``None``."""
    data = getattr(fit, "data", None)
    if data is None:
        return None
    payload = getattr(data, "mfd", None)
    if payload is not None:
        return payload
    meta = getattr(data, "meta_data", None) or {}
    return meta.get("mfd_data")


class Mfd2DPlot(plotbase.Plot):
    """Measured and modelled MFD histograms, with the FRET lines over both."""

    name = "MFD 2D"

    def __init__(self, fit, parent=None, title: str = "MFD histogram", **kwargs):
        """Build the panels.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            The fit whose data and model are shown.
        parent : QtWidgets.QWidget, optional
            Parent widget.
        title : str
            Panel title.
        **kwargs
            Ignored; present for the plot-spec signature.
        """
        super().__init__(fit, parent=parent, **kwargs)
        self._title = title

        self.grid = cp.Grid()
        self.layout.addWidget(self.grid)

        self.data_plot = self.grid.add_plot(row=0, col=0)
        self.model_plot = self.grid.add_plot(row=0, col=1)
        self.marginal_plot = self.grid.add_plot(row=1, col=0, colspan=2)

        self.data_plot.set_title("measured")
        self.model_plot.set_title("model")
        for plot in (self.data_plot, self.model_plot):
            plot.set_labels(bottom="proximity ratio", left="⟨t⟩ / ns")
        self.marginal_plot.set_labels(bottom="proximity ratio", left="bursts")
        self.model_plot.link_x(self.data_plot)
        self.model_plot.link_y(self.data_plot)
        # The marginal is deliberately *not* x-linked to the images. A linked child
        # spans two columns here, so the link never took effect on it — and setting
        # its range knocked the parent image back into auto-range, which is how the
        # proximity axis came to stop at 0.43. Both panels get the same explicit
        # range in :meth:`_apply_ranges` instead, which is what the link was for.
        # A proximity ratio has no unit to prefix, so an automatic SI prefix
        # relabels a 0-to-1 axis as "(x0.001)" with ticks running to 400.
        for plot in (self.data_plot, self.model_plot, self.marginal_plot):
            plot.set_si_prefix(x=False)

        empty = np.zeros((1, 1))
        self.data_image = self.data_plot.image(
            empty, colormap=COLORMAP, axis_order="col-major"
        )
        self.model_image = self.model_plot.image(
            empty, colormap=COLORMAP, axis_order="col-major"
        )
        self.colorbar = self.grid.add_colorbar(
            self.data_image, colormap=COLORMAP, row=0, col=2
        )
        # Panels share the width equally by default, which turns the colour bar
        # into an unreadable sliver and squeezes both images. The marginal is a
        # supporting view, so it gets less height than the histograms.
        self.grid.set_column_stretch(0, 10)
        self.grid.set_column_stretch(1, 10)
        self.grid.set_column_stretch(2, 2)
        self.grid.set_row_stretch(0, 3)
        self.grid.set_row_stretch(1, 2)

        # The analytic lines, drawn after the images so they sit above them.
        self.static_lines = [
            plot.line([], [], pen=cp.to_pen("#ffffff", width=2), name="static")
            for plot in (self.data_plot, self.model_plot)
        ]
        self.dynamic_lines = [
            plot.line(
                [], [],
                pen=cp.to_pen("#ff6b6b", width=2, style=cp.LineStyle.DASH),
                name="dynamic",
            )
            for plot in (self.data_plot, self.model_plot)
        ]

        self.data_marginal = self.marginal_plot.line(
            [], [], pen=cp.to_pen("#8ab4f8", width=2), name="measured"
        )
        self.model_marginal = self.marginal_plot.line(
            [], [], pen=cp.to_pen("#f28b82", width=2), name="model"
        )
        self.marginal_plot.legend()

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        self.layout.addWidget(self.status)

    def _set_image(self, handle, counts, axes) -> None:
        """Place a histogram on an image handle, in data coordinates.

        Deliberately does **not** set the view range: every later ``set_data``
        re-triggers the renderer's auto-range, so a range set here is quietly
        overwritten by whichever curve is drawn last — which is how the proximity
        axis came to stop at 0.43. :meth:`_apply_ranges` does it, once, at the end.
        """
        handle.set_image(np.asarray(counts, dtype=float))
        x0 = float(axes.ratio_edges[0])
        y0 = float(axes.micro_time_edges[0])
        handle.set_rect(
            x0,
            y0,
            float(axes.ratio_edges[-1]) - x0,
            float(axes.micro_time_edges[-1]) - y0,
        )

    def _apply_ranges(self, axes) -> None:
        """Fix every panel to the axes the histogram was actually binned on."""
        x = (float(axes.ratio_edges[0]), float(axes.ratio_edges[-1]))
        y = (float(axes.micro_time_edges[0]), float(axes.micro_time_edges[-1]))
        # The link parent goes last: setting a linked child's range re-enables the
        # parent's auto-range, so fixing the parent first would be undone.
        self.marginal_plot.set_range(x=x, padding=0.0)
        self.model_plot.set_range(x=x, y=y, padding=0.0)
        self.data_plot.set_range(x=x, y=y, padding=0.0)

    def _fret_lines(self, model, axes):
        """Return the static and dynamic FRET lines in *raw* plot coordinates.

        The lines are conventionally drawn on corrected axes. These axes are raw, so
        the same corrections the forward model applies are applied to the line —
        otherwise it would be drawn through a cloud it does not belong to, and the
        deviation everyone reads off it would be the correction rather than the
        dynamics.
        """
        from chisurf.core.fluorescence.mfd.patterns import (
            FretState,
            red_probability,
            state_efficiency,
        )

        optics = model.optics
        response = None
        payload = _payload(self.fit)
        if payload is not None:
            response = payload.responses[payload.channels[0]]
        if response is None:
            return None, None

        from chisurf.core.fluorescence.mfd.patterns import (
            donor_lifetime_spectrum_of_state,
        )

        distances = np.linspace(15.0, 130.0, 60)
        ratio, micro = [], []
        for distance in distances:
            state = FretState(distance=float(distance))
            efficiency = state_efficiency(state, optics)
            amplitudes, lifetimes = donor_lifetime_spectrum_of_state(state, optics)
            mean, _ = response.signal_moments(amplitudes, lifetimes)
            ratio.append(float(red_probability(efficiency, optics)))
            micro.append(float(mean))
        static = (np.asarray(ratio), np.asarray(micro))

        # The dynamic line: mixtures of the model's two extreme states. It bows away
        # from the static line because the lifetime axis averages the *decay* while
        # the FRET axis averages the *efficiency*.
        dynamic = None
        states = getattr(model, "states", [])
        if len(states) >= 2:
            first, last = states[0], states[-1]
            fractions = np.linspace(0.0, 1.0, 40)
            p_a = state_efficiency(first, optics)
            p_b = state_efficiency(last, optics)
            a_amp, a_tau = donor_lifetime_spectrum_of_state(first, optics)
            b_amp, b_tau = donor_lifetime_spectrum_of_state(last, optics)
            ratio, micro = [], []
            for f in fractions:
                efficiency = f * p_a + (1.0 - f) * p_b
                mean, _ = response.signal_moments(
                    np.concatenate([f * a_amp, (1.0 - f) * b_amp]),
                    np.concatenate([a_tau, b_tau]),
                )
                ratio.append(float(red_probability(efficiency, optics)))
                micro.append(float(mean))
            dynamic = (np.asarray(ratio), np.asarray(micro))
        return static, dynamic

    def update_all(self, *args, **kwargs) -> None:
        """Redraw from the fit's current data and model."""
        payload = _payload(self.fit)
        if payload is None:
            self.status.setText("No MFD dataset.")
            return
        axes = payload.axes
        observed = np.asarray(payload.observed.counts, dtype=float)
        self._set_image(self.data_image, observed, axes)

        model = getattr(self.fit, "model", None)
        predicted = None
        if model is not None and getattr(model, "y", None) is not None:
            flat = np.asarray(model.y, dtype=float)
            if flat.size == observed.size:
                predicted = flat.reshape(observed.shape, order="C")
        if predicted is None:
            predicted = np.zeros_like(observed)
        self._set_image(self.model_image, predicted, axes)

        levels = (0.0, float(max(observed.max(), predicted.max(), 1.0)))
        self.data_image.set_levels(*levels)
        self.model_image.set_levels(*levels)
        self.colorbar.set_levels(*levels)

        centres = 0.5 * (axes.ratio_edges[:-1] + axes.ratio_edges[1:])
        self.data_marginal.set_data(centres, observed.sum(axis=1))
        self.model_marginal.set_data(centres, predicted.sum(axis=1))

        compute = getattr(model, "_compute_model", None)
        if compute is not None:
            try:
                static, dynamic = self._fret_lines(compute(), axes)
            except Exception:
                static, dynamic = None, None
            for handle in self.static_lines:
                handle.set_data(*(static if static else ([], [])))
            for handle in self.dynamic_lines:
                handle.set_data(*(dynamic if dynamic else ([], [])))

        # Last, so that no set_data after this can auto-range over the top of it.
        self._apply_ranges(axes)

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
