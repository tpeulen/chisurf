import pytest
from qtpy import QtWidgets


def test_tags_editor_creation(qapp, qtbot):
    pytest.importorskip("tttrlib")
    from chisurf.plugins.tttr.tttr_header_edit.gui.tool import TagsEditor

    widget = TagsEditor()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    assert hasattr(widget.auto_form, "sync_fields")
    assert hasattr(widget.model, "tags")
