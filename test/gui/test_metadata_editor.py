"""Headless GUI tests for the shared metadata editor's key completer.

The key list is the whole mmCIF dictionary (~9,400 entries) rather than the 37
hard-coded fall-backs it silently degraded to, which makes three properties
worth pinning: the list is shared by every row instead of copied into it, a key
typed into one row does not leak into the others, and the dropdown shows a key
in full instead of eliding exactly the part that distinguishes it.
"""

import pytest
from qtpy import QtGui, QtWidgets
from qtpy.QtCore import Qt

from chisurf.gui.widgets.metadata_editor import ALL_METADATA_KEYS, MetadataEditor


@pytest.fixture
def editor(qtbot):
    """Build a three-column metadata editor with two rows of realistic content."""
    widget = MetadataEditor(columns=3)
    qtbot.addWidget(widget)
    widget.set_data(
        [
            {"key": "_flr_sample.entity_assembly_id", "value": "1", "details": "labelled"},
            {"key": "pH", "value": "7.4", "details": "phosphate buffer"},
        ]
    )
    return widget


def test_the_dictionary_reaches_the_key_completer(editor):
    """Every row offers the full dictionary, not just the hard-coded keys."""
    assert len(ALL_METADATA_KEYS) > 5000
    combo = editor.table.cellWidget(0, 0)
    assert combo.count() == len(ALL_METADATA_KEYS)
    keys = {combo.itemText(i) for i in range(combo.count())}
    assert "_flr_sample.entity_assembly_id" in keys
    assert "pH" in keys


def test_rows_share_one_key_model(editor):
    """Thousands of keys are held once per editor, not once per row."""
    first = editor.table.cellWidget(0, 0)
    second = editor.table.cellWidget(1, 0)
    assert first.model() is second.model()


def test_a_key_typed_in_one_row_does_not_leak_into_the_others(editor):
    """A shared model must not grow an entry when a row is edited."""
    combo = editor.table.cellWidget(0, 0)
    before = combo.count()
    combo.setCurrentText("_not_a_dictionary.key")
    combo.lineEdit().returnPressed.emit()
    assert combo.count() == before
    assert editor.table.cellWidget(1, 0).count() == before
    assert editor.get_data()[0]["key"] == "_not_a_dictionary.key"


def test_unknown_loaded_keys_stay_selectable(editor):
    """A key a stored record carries but the dictionary does not is still offered."""
    editor.set_data([{"key": "_home_grown.key", "value": "x", "details": ""}])
    combo = editor.table.cellWidget(0, 0)
    keys = {combo.itemText(i) for i in range(combo.count())}
    assert "_home_grown.key" in keys
    assert combo.count() == len(ALL_METADATA_KEYS) + 1


def test_the_dropdown_is_wide_enough_for_a_whole_key(editor, qtbot):
    """A long mmCIF key must be readable in the popup, not elided mid-name."""
    combo = editor.table.cellWidget(0, 0)
    combo.resize(120, combo.height())
    combo.showPopup()
    view = combo.view()
    try:
        assert view.textElideMode() == Qt.ElideNone
        widest = max(
            QtGui.QFontMetrics(view.font()).horizontalAdvance(combo.itemText(i))
            for i in range(combo.count())
        )
        assert view.minimumWidth() >= widest
    finally:
        combo.hidePopup()


def test_a_described_key_carries_its_description_as_a_tooltip(editor):
    """The dictionary description rides along on the dropdown item."""
    combo = editor.table.cellWidget(0, 0)
    index = combo.findText("_atom_site.label_entity_id")
    assert index >= 0
    assert "entity" in combo.itemData(index, Qt.UserRole + 1).lower()


def test_the_key_completer_matches_anywhere_in_the_name(editor):
    """Keys are long and prefixed, so a prefix-only completer would be useless."""
    combo = editor.table.cellWidget(0, 0)
    completer = combo.completer()
    assert completer is not None
    assert completer.filterMode() == Qt.MatchContains
    assert completer.caseSensitivity() == Qt.CaseInsensitive


def test_a_new_row_starts_empty(editor):
    """An added row must not silently claim the first key in the list."""
    editor._on_add_empty_row()
    combo = editor.table.cellWidget(editor.table.rowCount() - 1, 0)
    assert isinstance(combo, QtWidgets.QComboBox)
    assert combo.currentText() == ""
