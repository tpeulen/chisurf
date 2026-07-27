"""The general ``state_table`` AutoForm section: rows are states, columns properties.

The rectangular sibling of ``rate_matrix``. These tests use a plain view-model
rather than a real plugin, because the point of the section is that it does not
know what a "state" is — a species, a conformer, a detector — only that there
are N of them and that each carries some numbers.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    """Return the shared application instance."""
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _Model:
    """Two per-state properties, one of them stored in a strided flat list."""

    def __init__(self, n=2):
        self.n = n
        self.weight = [1.0, 2.0]
        # Two slots per state, of which the table shows both.
        self.pair = [10.0, 11.0, 20.0, 21.0]
        self.floor = 0.5

    def view_spec(self):
        """Return the spec binding the table to this model."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec({
            "sections": [
                {"type": "custom", "key": "state_table",
                 "options": {
                     "size_attr": "n",
                     "columns": [
                         {"attr": "weight", "label": "w", "default": 7.0},
                         {"attr": "pair", "label": "a", "stride": 2, "slot": 0},
                         {"attr": "pair", "label": "b", "stride": 2, "slot": 1},
                     ],
                     "trailing_rows_source": "trailing",
                 }},
            ]
        })

    def trailing(self):
        """Return one extra row whose only live cell is a scalar attribute."""
        return [{"label": "BG", "cells": [None, {"attr": "floor"}, None]}]


def _table(model, qapp):
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.state_table_section import StateTableWidget

    form = AutoForm(model)
    return form, form.findChild(StateTableWidget)


def test_rows_are_states_and_columns_are_properties(qapp):
    """The grid's shape comes from the size attribute and the column specs."""
    model = _Model()
    _, table = _table(model, qapp)
    assert table.table.rowCount() == 3          # 2 states + the trailing row
    assert table.table.columnCount() == 3
    assert [table.table.horizontalHeaderItem(i).text() for i in range(3)] == ["w", "a", "b"]
    assert table._cells[(0, 0)].value() == pytest.approx(1.0)
    assert table._cells[(1, 0)].value() == pytest.approx(2.0)


def test_a_strided_store_addresses_its_own_slot(qapp):
    """Two columns over one flat list must not read the same cell.

    This is the case that makes hand-rolled tables go wrong: several properties
    packed into one list, addressed by ``row * stride + slot``.
    """
    model = _Model()
    _, table = _table(model, qapp)
    assert table._cells[(0, 1)].value() == pytest.approx(10.0)
    assert table._cells[(0, 2)].value() == pytest.approx(11.0)
    assert table._cells[(1, 1)].value() == pytest.approx(20.0)
    assert table._cells[(1, 2)].value() == pytest.approx(21.0)

    table._cells[(1, 2)].setValue(99.0)
    assert model.pair == pytest.approx([10.0, 11.0, 20.0, 99.0])


def test_editing_writes_through_to_the_model(qapp):
    """A cell edit lands in the backing list, not in a copy."""
    model = _Model()
    _, table = _table(model, qapp)
    table._cells[(0, 0)].setValue(5.0)
    assert model.weight[0] == pytest.approx(5.0)


def test_growing_the_count_extends_the_stores(qapp):
    """A new state gets its cells, filled with the column's declared default.

    The lists are the model's, and a state the user just added has no values
    yet — growing them is the widget's job, not an error to report.
    """
    model = _Model()
    _, table = _table(model, qapp)
    model.n = 4
    table.refresh()
    assert table.table.rowCount() == 5           # 4 states + trailing
    assert model.weight == pytest.approx([1.0, 2.0, 7.0, 7.0])
    assert len(model.pair) == 8
    assert table._cells[(3, 0)].value() == pytest.approx(7.0)


def test_a_trailing_row_edits_a_scalar_not_a_state(qapp):
    """The trailing row's cells bind to plain attributes, and blanks stay blank."""
    model = _Model()
    _, table = _table(model, qapp)
    row = 2
    assert (row, 0) not in table._cells          # declared as None -> not editable
    assert table.table.item(row, 0).text() == "—"
    assert table._cells[(row, 1)].value() == pytest.approx(0.5)
    table._cells[(row, 1)].setValue(0.25)
    assert model.floor == pytest.approx(0.25)
    assert model.weight == pytest.approx([1.0, 2.0])   # untouched by the BG row


def test_the_last_row_is_visible(qapp):
    """The table is tall enough for every row it holds.

    A guessed row height silently hides the *last* row, which is where a
    trailing row such as a background sits — present in the model and invisible
    on screen, which is the one failure a construction test cannot see.
    """
    model = _Model(n=5)
    model.weight = [1.0] * 5
    model.pair = [0.0] * 10
    form, table = _table(model, qapp)
    form.resize(300, 400)            # narrow enough to need a horizontal scrollbar
    qapp.processEvents()
    last = table.table.rowCount() - 1
    bottom = table.table.rowViewportPosition(last) + table.table.rowHeight(last)
    assert bottom <= table.table.viewport().height()


def test_columns_can_come_from_the_model(qapp):
    """``columns_source`` lets the model decide what its states carry."""
    from chisurf.core.dataspec import load_view_spec

    class _Dynamic(_Model):
        def __init__(self):
            super().__init__()
            self.show_b = False

        def columns(self):
            cols = [{"attr": "weight", "label": "w"}]
            if self.show_b:
                cols.append({"attr": "pair", "label": "b", "stride": 2, "slot": 1})
            return cols

        def view_spec(self):
            return load_view_spec({
                "sections": [
                    {"type": "custom", "key": "state_table",
                     "options": {"size_attr": "n", "columns_source": "columns"}},
                ]
            })

    model = _Dynamic()
    _, table = _table(model, qapp)
    assert table.table.columnCount() == 1
    model.show_b = True
    table.refresh()
    assert table.table.columnCount() == 2
    assert table._cells[(0, 1)].value() == pytest.approx(11.0)


def test_an_action_column_is_a_button_per_row(qapp):
    """A property too big for a cell becomes a per-row button.

    The row is then the selector: a sub-editor opened this way already knows
    which state it is editing, so there is no second control that can disagree
    with the table about which one is current.
    """
    from qtpy import QtWidgets

    from chisurf.core.dataspec import load_view_spec

    class _WithAction(_Model):
        def __init__(self):
            super().__init__()
            self.opened = []

        def edit(self, row):
            self.opened.append(int(row))
            self.weight[row] = 42.0          # an action may change the row

        def view_spec(self):
            return load_view_spec({
                "sections": [
                    {"type": "custom", "key": "state_table",
                     "options": {"size_attr": "n", "columns": [
                         {"attr": "weight", "label": "w"},
                         {"action": "edit", "label": "Edit", "text": "…",
                          "description": "Open the editor for this state."},
                     ]}},
                ]
            })

    model = _WithAction()
    _, table = _table(model, qapp)
    button = table.table.cellWidget(1, 1)
    assert isinstance(button, QtWidgets.QToolButton)
    assert button.toolTip() == "Open the editor for this state."
    # An action column has no backing store, so it must not be treated as one.
    assert (1, 1) not in table._cells

    button.click()
    assert model.opened == [1]
    # The table re-reads afterwards, because the action usually changes the row.
    assert table._cells[(1, 0)].value() == pytest.approx(42.0)


def test_bool_readonly_and_per_row_bounds(qapp):
    """The three things a parameter row needs: a value, a flag, a result.

    Rows are not always interchangeable — a lifetime and a fraction share the
    value column but not its range — so bounds may come per row. A read-only
    column is the estimator's answer, which the user reads and does not type.
    """
    from qtpy import QtWidgets

    from chisurf.core.dataspec import load_view_spec

    class _Params:
        def __init__(self):
            self.labels = ["tau", "gamma"]
            self.values = [3.2, 0.02]
            self.fixed = [0.0, 1.0]
            self.results = [3.15, 0.02]
            self.lo = [0.01, -1.0]
            self.hi = [20.0, 1.0]

        @property
        def n(self):
            return len(self.labels)

        def view_spec(self):
            return load_view_spec({
                "sections": [
                    {"type": "custom", "key": "state_table",
                     "options": {"size_attr": "n", "row_labels_attr": "labels",
                                 "columns": [
                                     {"attr": "values", "label": "v",
                                      "minimum_attr": "lo", "maximum_attr": "hi"},
                                     {"attr": "fixed", "label": "F", "kind": "bool"},
                                     {"attr": "results", "label": "Fit",
                                      "kind": "readonly", "minimum": -1e9, "maximum": 1e9},
                                 ]}},
                ]
            })

    model = _Params()
    _, table = _table(model, qapp)

    # Per-row bounds: each row gets its own range from the named lists.
    assert table._cells[(0, 0)].minimum() == pytest.approx(0.01)
    assert table._cells[(0, 0)].maximum() == pytest.approx(20.0)
    assert table._cells[(1, 0)].minimum() == pytest.approx(-1.0)
    assert table._cells[(1, 0)].maximum() == pytest.approx(1.0)

    # A bool column is a checkbox, and it writes through as 0/1.
    flag = table._cells[(0, 1)]
    assert isinstance(flag.checkbox, QtWidgets.QCheckBox)
    assert flag.checkbox.isChecked() is False
    flag.checkbox.setChecked(True)
    assert model.fixed[0] == pytest.approx(1.0)

    # A read-only column shows a value and refuses to take one.
    result = table._cells[(0, 2)]
    assert result.isReadOnly()
    assert result.value() == pytest.approx(3.15)

    # The model writing a result reaches the table on refresh.
    model.results[0] = 9.9
    table.refresh()
    assert table._cells[(0, 2)].value() == pytest.approx(9.9)
    assert table._cells[(0, 1)].checkbox.isChecked() is True
