import pytest
from qtpy import QtWidgets


def test_remove_clashes_creation(qapp, qtbot):
    pytest.importorskip("mdtraj")
    pytest.importorskip("numba")
    from chisurf.plugins.traj.traj_remove_clashes.widget import RemoveClashedFrames

    widget = RemoveClashedFrames()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    # AutoForm-backed: a Qt-free view-model drives a single AutoForm.
    assert hasattr(widget, "model")
    assert hasattr(widget, "auto_form")
    assert hasattr(widget, "trajectory_filename")


def test_widget_properties_delegate_to_model(qapp, qtbot):
    pytest.importorskip("mdtraj")
    pytest.importorskip("numba")
    from chisurf.plugins.traj.traj_remove_clashes.widget import RemoveClashedFrames

    widget = RemoveClashedFrames()
    qtbot.addWidget(widget)
    widget.trajectory_filename = "/data/example.h5"
    widget.model.atom_selection = "name CA"
    widget.model.stride = 4
    widget.model.min_distance = 2.85
    assert widget.trajectory_filename == "/data/example.h5"
    assert widget.model.trajectory_filename == "/data/example.h5"
    assert widget.atom_list == "name CA"
    assert widget.stride == 4
    assert widget.min_distance == pytest.approx(0.285)
