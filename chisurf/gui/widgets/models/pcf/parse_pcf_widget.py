from __future__ import annotations

import pathlib

from qtpy import QtGui

import chisurf as cs
from chisurf.gui.widgets.models.parse.widget import ParseModelWidget


class ParsePCFWidget(ParseModelWidget):
    """Equation-catalogue widget for the PCF (pair-correlation) experiment type.

    A thin :class:`ParseModelWidget` that loads the PCF distribution catalogue
    (``chisurf/core/models/pcf/models.yaml``). The distribution equations are
    plain functions of the lag ``x`` and fit the same 1D-curve machinery as FCS.
    """

    name = "PCF Model"

    def __init__(self, fit, icon: QtGui.QIcon = None, **kwargs):
        """Initialize the PCF parse-model widget.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.FitGroup
            The fit group this widget belongs to.
        icon : QtGui.QIcon, optional
            Icon for the model tab.
        **kwargs
            Additional keyword arguments forwarded to the base class.
        """
        if icon is None:
            icon = QtGui.QIcon(":/icons/icons/fcs.png")
        self.icon = icon
        model_file = pathlib.Path(cs.__file__).parent / "core" / "models" / "pcf" / "models.yaml"
        super().__init__(fit=fit, model_file=model_file, **kwargs)
