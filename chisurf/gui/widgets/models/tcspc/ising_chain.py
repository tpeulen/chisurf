from __future__ import annotations

from typing import TYPE_CHECKING

import chisurf as cs
from qtpy import QtWidgets, QtGui

import chisurf.gui.widgets.fitting

import chisurf.core.models.tcspc.fret as fret

from chisurf.gui.widgets.models.tcspc.lifetime import LifetimeWidget, LifetimeModelWidgetBase
from chisurf.gui.widgets.models.tcspc import plot_cls_dist_default
from chisurf.gui.widgets.models.tcspc import kappa2_helpers

if TYPE_CHECKING:
    from chisurf.core.fitting.fit import Fit


class IsingChainModelWidget(fret.IsingChainModel, LifetimeModelWidgetBase):
    """Widget for the Ising two-state chain FRET distance-distribution model."""

    plot_classes = plot_cls_dist_default

    def get_parameter_widgets(self):
        """Return all parameter widgets for this model."""
        widgets = super().get_parameter_widgets() if hasattr(super(), 'get_parameter_widgets') else []
        if hasattr(self, '_orientation_widget'):
            widgets.append(self._orientation_widget)
        widgets.append(self._fret_parameters_widget)
        return widgets

    def _show_kappa2_distribution(self):
        """Show the kappa^2 distribution plot dialog."""
        kappa2_helpers.show_kappa2_distribution_plot(
            parent=self,
            orientation_parameter=getattr(self, "orientation_parameter", None),
            fret_parameters=self.fret_parameters,
        )

    def _open_experimental_k2(self):
        """Open the experimental kappa^2 dialog."""
        kappa2_helpers.open_experimental_k2_dialog(parent=self, fret_model=self)

    def __init__(self, fit: "Fit", **kwargs):
        """Initialize the Ising-chain FRET widget."""
        self.donor = LifetimeWidget(parent=self, model=self, title='Donor(0)', name='donor')

        super().__init__(fit, **kwargs)

        layout = QtWidgets.QVBoxLayout()
        self.layout.addLayout(layout)

        self._fret_parameters_widget = cs.gui.widgets.fitting.widgets.make_fitting_parameter_group_widget(
            self.fret_parameters)
        layout.addWidget(self._fret_parameters_widget)

        # Shared κ² mode controls (dynamic vs static + distribution/experimental buttons)
        kappa2_helpers.setup_kappa2_controls(self, layout)

        self._orientation_widget = cs.gui.widgets.fitting.widgets.make_fitting_parameter_group_widget(
            self.orientation_parameter
        )
        layout.addWidget(self._orientation_widget)

        self.layout.addWidget(self.donor)

        # Ising two-state chain parameters.
        for p in (self._n_residues, self._b_structured, self._b_unstructured,
                  self._coupling, self._field):
            self.layout.addWidget(
                cs.gui.widgets.fitting.widgets.make_fitting_parameter_widget(p))

        self.icon = QtGui.QIcon(":/icons/icons/TCSPC.ico")
