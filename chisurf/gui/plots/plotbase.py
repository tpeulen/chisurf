from __future__ import annotations

from qtpy import QtWidgets

import chisurf.core.fitting
import chisurf.gui
import chisurf.gui.widgets
from chisurf.gui.widgets.general import View


class Plot(View):
    def __init__(
        self,
        fit: chisurf.core.fitting.fit.Fit,
        parent=None,
        plot_controller: QtWidgets.QWidget = None,
        **kwargs,
    ):
        super().__init__()
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.parent = parent
        self.fit = fit
        if plot_controller is None:
            self.plot_controller = QtWidgets.QWidget()
        else:
            self.plot_controller = plot_controller
        self.widgets = list()
        #: ``(chiplot.Panel, stretch)`` in order: what the fit window's emtk
        #: surface draws for this page, stacked top to bottom (see add_panel).
        self.emtk_panels: list = []

    def add_panel(self, panel=None, stretch: float = 1.0):
        """Declare a chiplot panel of this page, below the ones before it.

        A :class:`chisurf.gui.chiplot.Panel` is not a widget: the fit window
        draws its canvas on its emtk surface, sharing the height by *stretch*.
        Called without a panel, a new one is made. Returns the panel.
        """
        if panel is None:
            from chisurf.gui import chiplot as cp

            panel = cp.Panel()
        self.emtk_panels.append((panel, float(stretch)))
        return panel

    def update(self, *args, **kwargs) -> None:
        super().update(*args, **kwargs)

    def close(self):
        QtWidgets.QWidget.close(self)
        if isinstance(self.plot_controller, QtWidgets.QWidget):
            self.plot_controller.close()
