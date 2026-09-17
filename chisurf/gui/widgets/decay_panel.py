"""The two-panel decay view: weighted residuals above, decay below.

One widget for every VV/VH single-lifetime fit in the tree — a burst, a region,
anything else that produces a stack and a model. It draws a
:class:`~chisurf.core.fluorescence.mle.display.DecayCurves` and nothing else:
what to draw was decided without a screen, in
:mod:`chisurf.core.fluorescence.mle.display`, which is what makes the awkward
parts of it testable.

The layout is the one the burst tool arrived at and is worth keeping: residuals
on top at a third of the height, sharing the time axis with the decay below, so
a systematic deviation lines up with the channel that caused it. The decay is
log-scaled because a decay is exponential and a linear axis shows only its first
nanosecond.
"""

from __future__ import annotations

from qtpy import QtWidgets

from chisurf.gui import chiplot

__all__ = ["DecayPanel"]

#: Pens for the four overlaid curves. Named here rather than at each call so a
#: burst decay and a region decay are the same picture in the same colours.
DATA_PEN = (60, 60, 60)
MODEL_PEN = "g"
IRF_PEN = "r"
BACKGROUND_PEN = "b"
RESIDUAL_PEN = (200, 20, 20)


class DecayPanel(QtWidgets.QWidget):
    """Residuals over a decay, x-linked, drawing one :class:`DecayCurves`.

    Parameters
    ----------
    parent : QWidget, optional
    title : str, optional
        Group-box title; empty for no box, which is what an embedded panel in a
        dock area wants.
    x_label : str, optional
        Label for the shared time axis.
    """

    def __init__(self, parent=None, *, title: str = "", x_label: str = "Time (ch.)"):
        super().__init__(parent)

        self.residual_plot = chiplot.Plot()
        self.decay_plot = chiplot.Plot()

        self.residual_plot.set_labels(left="Weighted residuals")
        self.residual_plot.grid(x=True, y=True)
        # Linked so panning the decay pans the residuals: a residual is *about*
        # a channel, and reading it against a different x-range is worse than
        # not showing it.
        self.residual_plot.link_x(self.decay_plot)

        self.decay_plot.set_labels(bottom=x_label, left="Intensity")
        self.decay_plot.set_log(y=True)
        # Counts: chiplot takes data units and converts for the log axis.
        self.decay_plot.set_ylim(0.1, 1.0e5)

        inner = QtWidgets.QVBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)
        inner.addWidget(self.residual_plot, 1)
        inner.addWidget(self.decay_plot, 3)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        if title:
            box = QtWidgets.QGroupBox(title)
            box.setLayout(inner)
            outer.addWidget(box)
        else:
            outer.addLayout(inner)

        self._legend()

    def _legend(self) -> None:
        """(Re-)create the legend box.

        Asked for again after every ``clear()``: the legend survives clearing,
        so without this the rows accumulate a fresh set per fit until the box
        covers the data it is labelling.
        """
        self.decay_plot.legend(offset=(10, 10))

    def clear(self) -> None:
        """Empty both panels, keeping one legend."""
        self.decay_plot.clear()
        self.residual_plot.clear()
        self._legend()

    def set_curves(self, curves) -> None:
        """Draw one fit.

        Parameters
        ----------
        curves : chisurf.core.fluorescence.mle.display.DecayCurves
            Everything to draw, already windowed, scaled and range-pinned.
            ``None`` clears the panel, which is what "no region selected"
            should look like rather than the previous region's decay.
        """
        self.clear()
        if curves is None:
            return

        self.decay_plot.scatter(curves.channels, curves.data, size=3, name="Data (VV|VH)")
        self.decay_plot.line(curves.channels, curves.model, pen=MODEL_PEN, name="Model (fit)")
        if curves.irf is not None:
            self.decay_plot.line(range(len(curves.irf)), curves.irf, pen=IRF_PEN, name="IRF")
        if curves.background is not None:
            self.decay_plot.line(
                range(len(curves.background)),
                curves.background,
                pen=BACKGROUND_PEN,
                name="Background",
            )

        self.residual_plot.line(
            range(len(curves.residuals)),
            curves.residuals,
            pen=chiplot.to_pen(RESIDUAL_PEN, width=1),
            symbol="o",
            symbol_size=3,
        )

        # The ranges come with the curves: pinning them is a display decision
        # taken where the numbers are, not re-derived per widget.
        self.decay_plot.set_ylim(*curves.decay_ylim, padding=0.0)
        self.residual_plot.set_ylim(*curves.residual_ylim, padding=0.05)

    def set_fit(self, data, model, **kwargs) -> None:
        """Draw a fit from its raw stacks.

        The convenience form, for a caller holding the estimator's own arrays.

        Parameters
        ----------
        data, model : array-like
            Full VV|VH stacks.
        **kwargs
            Passed to
            :func:`~chisurf.core.fluorescence.mle.display.decay_curves`
            (``irf``, ``background``, ``vv``, ``vh``, ``deconvolved``,
            ``diverged``).
        """
        from chisurf.core.fluorescence.mle.display import decay_curves

        self.set_curves(decay_curves(data, model, **kwargs))
