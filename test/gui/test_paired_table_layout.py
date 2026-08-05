"""What a component table does when its host cannot give it the room it wants.

A ``PairedParameterTableWidget`` sizes itself to *all* its rows and shares out
spare width between its value columns. Both are right inside a scrolled model
editor and wrong in a dock of fixed height and modest width, which is where
nDXplorer's Gaussians put it: rows fall off the bottom, and stretched value
columns elide the numbers they exist to show. These are the guards for the two
answers — ``set_scrollable`` and the measured column policy.
"""

from __future__ import annotations

import pytest
from qtpy import QtCore, QtWidgets

from chisurf.core.dataspec import DynamicGroupSection
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.gui.autoform.sections.parameter_table import PairedParameterTableWidget

WIDTH = 2


def _params(n: int, value: float = 0.5):
    out = []
    for i in range(n):
        out.append(FittingParameter(name=f"x_{i}", value=value, label_text=f"x<sub>{i}</sub>"))
        out.append(FittingParameter(name=f"t_{i}", value=value, label_text=f"&tau;<sub>{i}</sub>"))
    return out


@pytest.fixture
def table(qtbot):
    def build(n_components=8, section=None, width=600):
        w = PairedParameterTableWidget(_params(n_components), width=WIDTH, section=section)
        qtbot.addWidget(w)
        w.resize(width, 400)
        w.show()
        qtbot.waitExposed(w)
        return w

    return build


def test_by_default_the_table_shows_every_row(table):
    w = table(n_components=8)
    view = w.table_view
    assert view.verticalScrollBarPolicy() == QtCore.Qt.ScrollBarAlwaysOff
    # Sized to content: header plus eight rows.
    assert view.height() >= 8 * view.rowHeight(0)


def test_a_bounded_host_gets_a_scrolling_table_instead_of_lost_rows(table):
    w = table(n_components=8)
    w.set_scrollable(3)
    view = w.table_view
    assert view.verticalScrollBarPolicy() == QtCore.Qt.ScrollBarAsNeeded
    # It asks for three rows...
    assert view.minimumHeight() <= 4 * view.rowHeight(0) + view.horizontalHeader().height()
    # ...and will still grow to all eight if its host has the room.
    assert view.maximumHeight() >= 8 * view.rowHeight(0)
    assert w.table_model.rowCount() == 8


def test_a_wide_table_hugs_its_numbers_rather_than_eliding_them(table):
    """Narrow host: the value columns must not be squeezed below their content."""
    w = table(n_components=3, width=180)
    view = w.table_view
    for column in w._value_columns():
        assert view.columnWidth(column) >= view.sizeHintForColumn(column)


def test_a_roomy_table_shares_out_the_spare_width(table):
    w = table(n_components=3, width=900)
    header = w.table_view.horizontalHeader()
    assert header.sectionResizeMode(w._value_columns()[0]) == QtWidgets.QHeaderView.Stretch


def test_the_section_decides_which_columns_are_shown(table):
    section = DynamicGroupSection(target="g", columns=("value", "fixed"))
    w = table(n_components=2, section=section)
    hidden = {
        w.table_model.column_id(c)
        for c in range(w.table_model.columnCount())
        if w.table_view.isColumnHidden(c)
    }
    assert "error" in hidden
    assert not w.has_bounds_columns()
    # ...and the bounds toggle cannot bring back what the whitelist left out.
    w.set_bounds_visible(True)
    assert all(w.table_view.isColumnHidden(c) for c in w._bounds_columns())


def test_slot_titles_can_be_declared_for_a_table_that_starts_empty(qtbot):
    w = PairedParameterTableWidget([], width=WIDTH, slot_labels=("A", "B"))
    qtbot.addWidget(w)
    model = w.table_model
    titles = [
        model.headerData(c, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole)
        for c in range(model.columnCount())
    ]
    assert "A" in titles and "B" in titles
