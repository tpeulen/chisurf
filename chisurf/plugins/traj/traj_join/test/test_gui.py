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


def test_form_renders_with_live_log(qapp, qtbot):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_join.widget import JoinTrajectoriesWidget

    widget = JoinTrajectoriesWidget()
    qtbot.addWidget(widget)
    widget.resize(460, 320)
    widget.show()
    qapp.processEvents()

    # The AutoForm built a non-trivial section tree...
    assert widget.auto_form.findChildren(QtWidgets.QWidget)
    # ...including the custom picker section's browse/action tool buttons...
    assert widget.auto_form.findChildren(QtWidgets.QToolButton)
    # ...and the live log (info section bound to log_html) shows the initial entry.
    browsers = widget.auto_form.findChildren(QtWidgets.QTextBrowser)
    assert browsers
    assert any("Ready" in b.toPlainText() for b in browsers)

    # The whole widget paints headlessly without Qt errors.
    pixmap = widget.grab()
    assert not pixmap.isNull()
    assert pixmap.width() > 0 and pixmap.height() > 0
