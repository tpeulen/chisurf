"""A native reader-settings surface gets the *File parameters* height in the Qt main window.

Found walking the lifetime guide in the Qt shell (2026-10-11): the TCSPC *TXT/CSV* reader's
emtk settings report no size hint, so beside the expanding *Drop files here.* label they
collapsed to ~80 px -- the file field showed, header rows, bin width, repetition rate and
polarisation did not. The layout below mirrors ``gui.ui``: the reader layout inside a
container that shares a vertical box with the drop label.
"""

from types import SimpleNamespace

from qtpy import QtWidgets

from chisurf.core.experiments.tcspc import TCSPCReader
from chisurf.gui.main_helper import SetupMixin


def _panel(qtbot):
    panel = QtWidgets.QWidget()
    outer = QtWidgets.QVBoxLayout(panel)
    container = QtWidgets.QWidget()
    middle = QtWidgets.QVBoxLayout(container)
    inner = QtWidgets.QVBoxLayout()
    middle.addLayout(inner)
    outer.addWidget(container)
    drop = QtWidgets.QLabel("Drop files here.")
    drop.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Expanding)
    outer.addWidget(drop)
    qtbot.addWidget(panel)
    return panel, inner, drop


def _settle(panel):
    panel.resize(400, 800)
    panel.show()
    QtWidgets.QApplication.processEvents()


def test_the_native_reader_settings_take_the_height(qtbot):
    from emtk.qt_host import ControlHost

    from chisurf.emtk.reader_settings import ReaderSettingsApp

    panel, inner, drop = _panel(qtbot)
    host = ControlHost(ReaderSettingsApp(TCSPCReader(record_provenance=False)), parent=panel)
    inner.addWidget(host)
    SetupMixin._give_reader_settings_the_height(SimpleNamespace(layout_experiment_reader=inner), host)
    _settle(panel)
    assert host.height() > 500, host.height()
    assert drop.height() > 0, "the drop target stays visible"


def test_a_qt_reader_controller_keeps_its_natural_height(qtbot):
    panel, inner, drop = _panel(qtbot)
    controller = QtWidgets.QLabel("Mode")
    inner.addWidget(controller)
    SetupMixin._give_reader_settings_the_height(
        SimpleNamespace(layout_experiment_reader=inner), controller
    )
    _settle(panel)
    assert drop.height() > controller.height()
