import pytest
from qtpy import QtWidgets


def test_md_converter_creation(qapp, qtbot):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_convert.widget import MDConverter

    widget = MDConverter()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    # AutoForm-backed: a Qt-free view-model drives a single AutoForm.
    assert hasattr(widget, "model")
    assert hasattr(widget, "auto_form")
    assert widget.name == "MC-Converter"


def test_widget_properties_delegate_to_model(qapp, qtbot):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_convert.widget import MDConverter

    widget = MDConverter()
    qtbot.addWidget(widget)
    widget.trajectory = "/data/example.h5"
    widget.target_directory = "/data/out"
    widget.model.use_folder = True
    widget.model.first_frame = 2
    widget.model.last_frame = 9
    widget.model.stride = 3
    widget.model.filename = "conv"
    widget.model.ending = ".pdb"
    widget.model.split = True
    assert widget.trajectory == "/data/example.h5"
    assert widget.target_directory == "/data/out"
    assert widget.use_folder is True
    assert widget.first_frame == 2
    assert widget.last_frame == 9
    assert widget.stride == 3
    assert widget.filename == "conv"
    assert widget.ending == ".pdb"
    assert widget.split is True


def test_topology_file_setter_none_for_missing(qapp, qtbot):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_convert.widget import MDConverter

    widget = MDConverter()
    qtbot.addWidget(widget)
    widget.topology_file = "/nope/missing.pdb"
    assert widget.topology_file is None
    assert widget.model.topology_path == "/nope/missing.pdb"


def test_form_renders_with_live_log(qapp, qtbot):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_convert.widget import MDConverter

    widget = MDConverter()
    qtbot.addWidget(widget)
    widget.resize(520, 420)
    widget.show()
    qapp.processEvents()

    # The AutoForm built a non-trivial section tree...
    assert widget.auto_form.findChildren(QtWidgets.QWidget)
    # ...including the custom picker/run sections' browse/action tool buttons...
    assert widget.auto_form.findChildren(QtWidgets.QToolButton)
    # ...and the live log (info section bound to log_html) shows the initial entry.
    browsers = widget.auto_form.findChildren(QtWidgets.QTextBrowser)
    assert browsers
    assert any("Ready" in b.toPlainText() for b in browsers)

    # The whole widget paints headlessly without Qt errors.
    pixmap = widget.grab()
    assert not pixmap.isNull()
    assert pixmap.width() > 0 and pixmap.height() > 0
