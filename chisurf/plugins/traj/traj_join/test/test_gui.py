import pytest
from qtpy import QtWidgets


def test_join_trajectories_widget_creation(qapp, qtbot):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_join.widget import JoinTrajectoriesWidget

    widget = JoinTrajectoriesWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    # AutoForm-backed: a Qt-free view-model drives a single AutoForm.
    assert hasattr(widget, "model")
    assert hasattr(widget, "auto_form")


def test_widget_properties_delegate_to_model(qapp, qtbot):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_join.widget import JoinTrajectoriesWidget

    widget = JoinTrajectoriesWidget()
    qtbot.addWidget(widget)
    widget.trajectory_filename_1 = "/data/a.h5"
    widget.trajectory_filename_2 = "/data/b.h5"
    widget.model.join_mode = "atoms"
    widget.model.reverse_traj_1 = True
    widget.model.reverse_traj_2 = True
    widget.model.chunk_size = 500
    assert widget.trajectory_filename_1 == "/data/a.h5"
    assert widget.trajectory_filename_2 == "/data/b.h5"
    assert widget.join_mode == "atoms"
    assert widget.reverse_traj_1 is True
    assert widget.reverse_traj_2 is True
    assert widget.chunk_size == 500
