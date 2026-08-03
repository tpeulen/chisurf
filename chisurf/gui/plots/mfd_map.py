"""The MFD 2D map, as a *plot* — hosting the shared AutoForm image widget.

The map belongs with the other plots, not in the analysis dock beside the
parameters: it is what you look at while fitting, it wants the room a plot tab
gives it, and the dock is for controls.

That does not mean writing another image widget. :class:`ImageMapWidget` is the
application's one image dock — colormap selector, channel selector, real-world
axes, click-picking, rectangle gate — and it is a plain ``QWidget`` bound to a
model attribute, so it drops into a plot as readily as into a form. This module is
the twenty lines that put it there, and nothing else.

The channel selector is what makes one map enough: measured, model, residual and
difference on the *same* axes and the same colour scale. Two heat maps side by side
at 40% width each compare worse than one that flips.
"""

from __future__ import annotations

from chisurf.gui.plots import plotbase


class MfdMapPlot(plotbase.Plot):
    """The 2D MFD histogram, hosted in a plot tab.

    Parameters are taken from the view spec's plot options and forwarded to
    :class:`~chisurf.gui.autoform.sections.builtin.ImageMapWidget` unchanged, so the
    map is configured in exactly the same vocabulary whether it is declared as a
    form section or as a plot.
    """

    name = "MFD map"

    def __init__(self, fit, parent=None, target: str = "mfd_image", **options):
        """Embed the shared image widget, bound to the fit's model.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            The fit whose model supplies the map.
        parent : QtWidgets.QWidget, optional
            Parent widget.
        target : str
            Model method returning the 2D array.
        **options
            Forwarded to :class:`ImageMapWidget` (``colormap``, ``extent_source``,
            ``channel_source``, …).
        """
        super().__init__(fit, parent=parent)
        from chisurf.gui.autoform.sections.builtin import ImageMapWidget

        model = getattr(fit, "model", None)
        self.image_widget = ImageMapWidget(model, target, **options)
        self.layout.addWidget(self.image_widget)

    def update_all(self, *args, **kwargs) -> None:
        """Re-read the map from the model."""
        try:
            self.image_widget.refresh()
        except Exception:
            # A map that cannot be read must not take the fit window down with it;
            # the widget keeps whatever it last drew.
            pass

    def update(self, *args, **kwargs) -> None:
        """Redraw, then run the base-class update."""
        self.update_all()
        super().update(*args, **kwargs)
