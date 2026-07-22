import numpy as np
import pytest
from qtpy import QtWidgets


def test_rotate_translate_creation(qapp, qtbot):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_rotate_translate.widget import (
        RotateTranslateTrajectoryWidget,
    )

    widget = RotateTranslateTrajectoryWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    # AutoForm-backed: a Qt-free view-model drives a single AutoForm.
    assert hasattr(widget, "model")
    assert hasattr(widget, "auto_form")


def test_widget_properties_delegate_to_model(qapp, qtbot):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_rotate_translate.widget import (
        RotateTranslateTrajectoryWidget,
    )

    widget = RotateTranslateTrajectoryWidget()
    qtbot.addWidget(widget)

    widget.trajectory_filename = "/data/example.h5"
    widget.rotation_matrix = np.arange(9, dtype=np.float32).reshape(3, 3)
    widget.translation_vector = (1.0, 2.0, 3.0)
    widget.stride = 5

    assert widget.trajectory_filename == "/data/example.h5"
    assert widget.model.trajectory_filename == "/data/example.h5"
    np.testing.assert_array_equal(
        widget.rotation_matrix, np.arange(9, dtype=np.float32).reshape(3, 3)
    )
    np.testing.assert_array_equal(widget.translation_vector, np.array([1.0, 2.0, 3.0]))
    assert widget.stride == 5
