"""The experimental-k2 dialog hosts the emtk calculator and applies its mean to the FRET model."""

from types import SimpleNamespace

import pytest

pytest.importorskip("qtpy.QtWidgets")


def test_dialog_applies_the_calculator_mean_to_the_model(qapp):
    from qtpy import QtCore, QtWidgets

    from chisurf.gui.widgets.models.tcspc import kappa2_helpers as helpers

    parameters = SimpleNamespace(kappa2=0.5)
    model = SimpleNamespace(fret_parameters=parameters, orientation_parameter=None)
    QtCore.QTimer.singleShot(
        1000,
        lambda: [
            w.accept()
            for w in QtWidgets.QApplication.topLevelWidgets()
            if isinstance(w, QtWidgets.QDialog)
        ],
    )
    helpers.open_experimental_k2_dialog(None, model)
    assert parameters.kappa2 == pytest.approx(2.0 / 3.0, abs=0.03)
