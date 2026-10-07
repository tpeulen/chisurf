"""Retained drag and Python source behavior survives Designer helper retirement."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.decorators import lineEdit_dragFile_injector
from chisurf.gui.devtools.source_jump import make_widget_resolver, resolve_widget_source
from chisurf.gui.widgets.code_badge import make_widget_source_resolver


class SourceWidget(QtWidgets.QWidget):
    """A real inspectable Python widget, rather than an invented XML source."""


@pytest.mark.parametrize("sort_paths", [True, False])
def test_real_drop_mutates_original_target_before_one_callback(qapp, tmp_path, sort_paths):
    """Real Qt MIME/drop delivery preserves supplied list identity and first-file display."""
    widget = QtWidgets.QLineEdit()
    target, notices = [], []
    injector = lineEdit_dragFile_injector(widget, target=target, sorted=sort_paths,
                                        call=lambda: notices.append(list(target)))
    paths = [tmp_path / "z.spc", tmp_path / "a.spc"]
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(path)) for path in paths])
    enter = QtGui.QDragEnterEvent(QtCore.QPoint(5, 5), QtCore.Qt.CopyAction, mime,
                                  QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    widget.dragEnterEvent(enter)
    assert enter.isAccepted()
    drop = QtGui.QDropEvent(QtCore.QPointF(5, 5), QtCore.Qt.CopyAction, mime,
                            QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    widget.dropEvent(drop)
    expected = sorted(map(str, paths)) if sort_paths else list(map(str, paths))
    assert injector.target is target and target == expected and notices == [expected]
    assert widget.text() == str(paths[0])
    widget.resize(600, 40)
    widget.show()
    qapp.processEvents()
    assert widget.grab().save(str(tmp_path / "drag-result.png"))
    widget.close()


def test_nonfile_drag_is_rejected(qapp):
    """HTTP URLs do not become local file drops."""
    widget = QtWidgets.QLineEdit()
    lineEdit_dragFile_injector(widget)
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl("https://example.invalid/data.spc")])
    event = QtGui.QDragEnterEvent(QtCore.QPoint(5, 5), QtCore.Qt.CopyAction, mime,
                                  QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    widget.dragEnterEvent(event)
    assert not event.isAccepted() and widget.text() == ""
    widget.close()


def test_python_source_wins_without_obsolete_xml_fallback(qapp, tmp_path):
    """All actual source resolver entry points return the Python class's source."""
    widget = SourceWidget()
    xml = tmp_path / "obsolete.ui"
    xml.write_text("<ui/>")
    widget._chisurf_ui_path = str(xml)
    expected = (inspect.getsourcefile(SourceWidget), inspect.getsourcelines(SourceWidget)[1])
    assert resolve_widget_source(widget) == expected
    assert make_widget_resolver(widget)() == expected
    assert make_widget_source_resolver(widget)() == expected
    widget.close()


def test_main_shell_has_explicit_runtime_package_data():
    """Setuptools selects the live shell UI through its exact package declaration."""
    from test.test_package_data_covers_shipped_files import ROOT, _build_command, _packaging_config

    data = _packaging_config()["package-data"]
    assert "*.ui" not in data["*"]
    assert "gui.ui" in data["chisurf.gui"]
    command = _build_command()
    # This exact package-data check has no VCS/egg-info manifest contribution.
    command.manifest_files = {}
    files = command.find_data_files("chisurf.gui", str(ROOT / "chisurf/gui"))
    assert any(Path(path).name == "gui.ui" for path in files)
