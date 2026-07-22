import pytest
from qtpy import QtWidgets


def test_save_topology_creation(qapp, qtbot):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_save_topology.widget import SaveTopology

    widget = SaveTopology()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    # AutoForm-backed: a Qt-free view-model drives a single AutoForm.
    assert hasattr(widget, "model")
    assert hasattr(widget, "auto_form")
    assert hasattr(widget, "trajectory_filename")


def test_trajectory_filename_roundtrips_through_model(qapp, qtbot):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_save_topology.widget import SaveTopology

    widget = SaveTopology()
    qtbot.addWidget(widget)
    widget.trajectory_filename = "/data/example.h5"
    assert widget.trajectory_filename == "/data/example.h5"
    assert widget.model.trajectory_filename == "/data/example.h5"
