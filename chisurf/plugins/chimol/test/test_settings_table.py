"""The settings table: every registered setting, findable and editable.

ChiMOL has 85 registered settings, and until this the only way to reach one was
to know its name and type ``set`` -- a command language pretending to be an
interface. The design is PyMOL's (``modules/pmg_qt/advanced_settings_gui.py``),
which is the reference for the GUI and the UX.

What is pinned here is the property that keeps it honest: the table writes
through the **same** ``set_setting`` the ``set`` command uses, so it is a window
onto one store rather than a second one. A table with its own copy of the values
would drift the moment a preset, a command or another widget changed something.
"""
from __future__ import annotations

import pytest

pytest.importorskip("qtpy")

from chimol.core.settings.registry import get_setting, set_setting


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def table(qapp):
    from chimol.hosts.qt.settings_table import SettingsTable

    widget = SettingsTable()
    widget.resize(820, 560)
    widget.show()
    for _ in range(3):
        qapp.processEvents()
    yield widget, qapp
    widget.close()


def _row(widget, name: str):
    for row in widget._rows:
        if row.name == name:
            return row
    raise AssertionError(f"{name} is not in the table")


def test_every_registered_setting_is_listed(table):
    from chimol.core.settings.registry import setting_names

    widget, _qapp = table
    assert len(widget._rows) == len(setting_names())
    assert widget.table.total_row_count() == len(widget._rows)


def test_the_value_shown_is_read_from_the_config_not_cached(table):
    """A command, a preset or another widget can change a setting while this is
    open, and a cached copy would show what it was when the window was built."""
    widget, _qapp = table
    row = _row(widget, "fog_start")
    before = row.value
    try:
        set_setting("fog_start", 0.8)
        assert row.value == pytest.approx(0.8)
    finally:
        set_setting("fog_start", before)


def test_editing_a_cell_writes_through_the_same_path_as_set(table):
    """The property that stops the table becoming a second store."""
    widget, _qapp = table
    row = _row(widget, "fog_start")
    before = get_setting("fog_start")
    try:
        assert widget._write(row, "value", 0.7)
        assert get_setting("fog_start") == pytest.approx(0.7)
    finally:
        set_setting("fog_start", before)


def test_a_rejected_value_is_refused_rather_than_stored(table):
    """`set` refuses a value that will not coerce, and so must the table.

    Storing it would put the config into a state no command could have produced.
    """
    widget, _qapp = table
    row = _row(widget, "depth_cue")
    before = get_setting("depth_cue")
    try:
        assert widget._write(row, "value", "banana") is False
        assert get_setting("depth_cue") == before
    finally:
        set_setting("depth_cue", before)


def test_a_change_asks_the_viewer_to_redraw(qapp):
    """A setting that takes effect only on the next unrelated repaint reads as
    one that did nothing."""
    from chimol.hosts.qt.settings_table import SettingsTable

    calls: list[int] = []
    widget = SettingsTable(on_changed=lambda: calls.append(1))
    try:
        row = _row(widget, "fog_start")
        before = get_setting("fog_start")
        widget._write(row, "value", 0.6)
        assert calls == [1]
        set_setting("fog_start", before)
    finally:
        widget.close()


def test_the_filter_narrows_by_name_and_by_description(table):
    """Searching the description is why it is shown: someone looking for the
    depth cue does not know it is spelled `fog_start`."""
    widget, _qapp = table
    total = widget.table.total_row_count()

    narrowed = widget.filter_settings("cartoon")
    assert 0 < narrowed < total

    by_description = widget.filter_settings("silhouette")
    assert by_description > 0

    assert widget.filter_settings("") == total
