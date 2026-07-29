"""Lazy import of the Qt/ChiSurf stack the MaxEnt GUI mixins need.

The mixins are imported by headless code paths too, so the Qt widgets and the
ChiSurf globals are resolved on first use rather than at import time. Plotting
goes through :mod:`chisurf.gui.chiplot`, which the plot widgets themselves
carry, so no rendering library is resolved here.
"""

from __future__ import annotations

chisurf = None
QtWidgets = None
QtCore = None
ExperimentalDataSelector = None


def ensure_qt_stack():
    """Import the Qt/ChiSurf stack once and return it.

    Returns
    -------
    tuple
        ``(QtWidgets, QtCore, chisurf, ExperimentalDataSelector)``.
    """
    global chisurf, QtWidgets, QtCore, ExperimentalDataSelector

    if QtWidgets is None or QtCore is None:
        from qtpy import QtWidgets as _QtWidgets, QtCore as _QtCore  # type: ignore

        QtWidgets = _QtWidgets
        QtCore = _QtCore

    if chisurf is None:
        import chisurf as _chisurf  # type: ignore

        chisurf = _chisurf

    if ExperimentalDataSelector is None:
        from chisurf.gui.widgets.experiments import (
            ExperimentalDataSelector as _ExperimentalDataSelector,
        )  # type: ignore

        ExperimentalDataSelector = _ExperimentalDataSelector

    return QtWidgets, QtCore, chisurf, ExperimentalDataSelector
