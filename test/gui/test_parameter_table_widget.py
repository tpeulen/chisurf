"""Offscreen-Qt tests for the parameter-group table widget (PRD-44).

Verifies that :class:`ParameterGroupTableWidget` renders, displays data, and
writes edits back through to the :class:`FittingParameter` objects, including
edge cases such as linked followers and bounds-conditional column editability.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:
        pytest.skip(f"qtpy unavailable: {exc}")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return app


def _make_params():
    from chisurf.core.fitting.parameter import FittingParameter

    return [
        FittingParameter(name="tau_1", value=3.5, lb=0.1, ub=10.0, bounds_on=True),
        FittingParameter(name="amp_1", value=0.5, fixed=True),
        FittingParameter(name="tau_2", value=1.2, lb=0.0, ub=5.0),
        FittingParameter(name="amp_2", value=0.5),
    ]


# ── model tests (no widget) ────────────────────────────────────────────

def test_model_counts():
    from chisurf.gui.autoform.sections.parameter_table import (
        ParameterGroupTableModel,
        COLUMN_META,
    )

    params = _make_params()
    model = ParameterGroupTableModel(params)
    assert model.rowCount() == 4
    assert model.columnCount() == len(COLUMN_META)


def test_model_display_values():
    from chisurf.gui.autoform.sections.parameter_table import (
        ParameterGroupTableModel,
        COL_NAME,
        COL_VALUE,
        COL_FIXED,
        COL_BOUNDS_LO,
        COL_ERROR,
    )

    params = _make_params()
    model = ParameterGroupTableModel(params)

    # name column
    assert model.data(model.index(0, COL_NAME)) == "tau_1"
    # value
    assert model.data(model.index(0, COL_VALUE)) == "3.5"
    # fixed
    assert model.data(model.index(1, COL_FIXED)) == "True"
    # bounds_lo (only shown when bounds_on)
    assert model.data(model.index(0, COL_BOUNDS_LO)) == "0.1"
    # bounds_lo (empty when bounds_on=False)
    assert model.data(model.index(2, COL_BOUNDS_LO)) == ""
    # error (empty when no error_estimate)
    assert model.data(model.index(0, COL_ERROR)) == ""


def test_model_edit_value():
    from chisurf.gui.autoform.sections.parameter_table import (
        ParameterGroupTableModel,
        COL_VALUE,
    )

    params = _make_params()
    model = ParameterGroupTableModel(params)
    idx = model.index(0, COL_VALUE)

    assert model.setData(idx, 4.2)
    assert params[0].value == 4.2


def test_model_edit_fixed():
    from chisurf.gui.autoform.sections.parameter_table import (
        ParameterGroupTableModel,
        COL_FIXED,
    )

    params = _make_params()
    model = ParameterGroupTableModel(params)

    # release fixed
    idx = model.index(1, COL_FIXED)
    assert model.setData(idx, "False")
    assert params[1].fixed is False

    # re-fix
    assert model.setData(idx, "True")
    assert params[1].fixed is True


def test_model_edit_bounds():
    from chisurf.gui.autoform.sections.parameter_table import (
        ParameterGroupTableModel,
        COL_BOUNDS_LO,
        COL_BOUNDS_HI,
    )

    params = _make_params()
    model = ParameterGroupTableModel(params)

    idx_lo = model.index(0, COL_BOUNDS_LO)
    assert model.setData(idx_lo, 0.5)
    assert params[0].bounds[0] == 0.5

    idx_hi = model.index(0, COL_BOUNDS_HI)
    assert model.setData(idx_hi, 8.0)
    assert params[0].bounds[1] == 8.0


def test_model_edit_bounds_on():
    from chisurf.gui.autoform.sections.parameter_table import (
        ParameterGroupTableModel,
        COL_BOUNDS_ON,
    )

    params = _make_params()
    model = ParameterGroupTableModel(params)
    idx = model.index(2, COL_BOUNDS_ON)
    assert model.setData(idx, "True")
    assert params[2].bounds_on is True


def test_linked_follower_value_not_editable():
    from qtpy import QtCore
    from chisurf.gui.autoform.sections.parameter_table import (
        ParameterGroupTableModel,
        COL_VALUE,
    )

    master = _make_params()[0]
    follower = _make_params()[1]
    follower.link = master

    model = ParameterGroupTableModel([follower])
    idx = model.index(0, COL_VALUE)
    flags = model.flags(idx)
    assert not (flags & QtCore.Qt.ItemIsEditable)
    assert flags & QtCore.Qt.ItemIsEnabled
    # setData on a linked follower must be rejected
    assert not model.setData(idx, 99.0)


def test_bounds_columns_editable_only_when_bounds_on():
    from qtpy import QtCore
    from chisurf.gui.autoform.sections.parameter_table import (
        ParameterGroupTableModel,
        COL_BOUNDS_LO,
        COL_BOUNDS_HI,
    )

    params = _make_params()
    # param[2] has bounds_on=False (lb/ub are set but not active)
    p = params[2]  # tau_2
    assert p.bounds_on is False

    model = ParameterGroupTableModel([p])
    idx_lo = model.index(0, COL_BOUNDS_LO)
    idx_hi = model.index(0, COL_BOUNDS_HI)
    assert not (model.flags(idx_lo) & QtCore.Qt.ItemIsEditable)
    assert not (model.flags(idx_hi) & QtCore.Qt.ItemIsEditable)

    p.bounds_on = True
    assert model.flags(idx_lo) & QtCore.Qt.ItemIsEditable
    assert model.flags(idx_hi) & QtCore.Qt.ItemIsEditable


# ── widget tests (need QApp) ───────────────────────────────────────────

def test_widget_column_visibility(qapp):
    from chisurf.core.dataspec import ParameterGroupTableSection
    from chisurf.gui.autoform.sections.parameter_table import (
        ParameterGroupTableWidget,
        COLUMN_META,
    )

    params = _make_params()
    section = ParameterGroupTableSection(
        target="test",
        columns=("name", "value", "fixed", "error"),
    )
    widget = ParameterGroupTableWidget(params=params, section=section)
    visible = [
        COLUMN_META[i][0]
        for i in range(len(COLUMN_META))
        if not widget.table_view.isColumnHidden(i)
    ]
    assert visible == ["name", "value", "fixed", "error"]


def test_widget_all_columns_when_empty(qapp):
    from chisurf.core.dataspec import ParameterGroupTableSection
    from chisurf.gui.autoform.sections.parameter_table import (
        ParameterGroupTableWidget,
        COLUMN_META,
    )

    params = _make_params()
    section = ParameterGroupTableSection(target="test", columns=())
    widget = ParameterGroupTableWidget(params=params, section=section)
    visible = sum(
        1 for i in range(len(COLUMN_META))
        if not widget.table_view.isColumnHidden(i)
    )
    assert visible == len(COLUMN_META)


def test_widget_sync(qapp):
    from chisurf.gui.autoform.sections.parameter_table import (
        ParameterGroupTableWidget,
    )

    params = _make_params()
    widget = ParameterGroupTableWidget(params=params)
    # sync must not raise
    widget.sync()


def test_widget_on_change_called(qapp):
    from chisurf.gui.autoform.sections.parameter_table import (
        ParameterGroupTableWidget,
    )

    params = _make_params()
    calls = []
    widget = ParameterGroupTableWidget(
        params=params,
        on_change=lambda: calls.append(1),
    )
    # edit triggers callback
    model = widget.table_model
    model.setData(model.index(0, 1), 99.0)
    assert len(calls) == 1

    # second edit triggers another
    model.setData(model.index(1, 1), 0.1)
    assert len(calls) == 2


# ── AutoForm integration tests ─────────────────────────────────────────

def test_autoform_dispatch_exists():
    """The AutoForm._build_section dispatch must recognise the new type."""
    from chisurf.core.dataspec import _SECTION_TYPES

    assert "parameter_group_table" in _SECTION_TYPES


def test_autoform_renders_table_from_view_json(qapp, monkeypatch):
    """AutoForm renders a ParameterGroupTableWidget for a section declared
    in a view spec (synthetic model with a resolvable target)."""
    from chisurf.core import dataspec as ds
    from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.parameter_table import ParameterGroupTableWidget

    group = FittingParameterGroup(
        name="test_group",
        parameters=[
            FittingParameter(name="k1", value=1.0),
            FittingParameter(name="k2", value=2.0),
        ],
    )

    class _Model:
        """Minimal model with a view_spec that contains a parameter_group_table."""
        test_group = group

        def view_spec(self):
            return ds.ModelView(
                sections=(
                    ds.ParameterGroupTableSection(
                        target="test_group",
                        columns=("name", "value", "fixed"),
                    ),
                ),
            )

    w = AutoForm(_Model())
    tables = w.findChildren(ParameterGroupTableWidget)
    assert len(tables) == 1
    tw = tables[0]
    assert tw.table_model.rowCount() == 2
    assert tw.table_model.data(tw.table_model.index(0, 1)) == "1"
    # edit through the table must propagate to the backing parameter
    tw.table_model.setData(tw.table_model.index(0, 1), 5.0)
    assert group.parameters[0].value == 5.0


def test_autoform_table_collapsible_when_set(qapp):
    """When collapsible=True (default), AutoForm wraps the table in a
    CollapsibleBox with the group's name as title."""
    from chisurf.core import dataspec as ds
    from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.widgets.collapsible_box import CollapsibleBox

    group = FittingParameterGroup(
        name="kinetics",
        parameters=[FittingParameter(name="k1", value=1.0)],
    )

    class _Model:
        test_group = group

        def view_spec(self):
            return ds.ModelView(
                sections=(
                    ds.ParameterGroupTableSection(target="test_group"),
                ),
            )

    w = AutoForm(_Model())
    boxes = w.findChildren(CollapsibleBox)
    assert len(boxes) >= 1
    titles = [b.title() for b in boxes]
    assert any("kinetics" in t for t in titles)


def test_autoform_table_non_collapsible_no_box(qapp):
    """When collapsible=False, no CollapsibleBox is wrapped around the table."""
    from chisurf.core import dataspec as ds
    from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.widgets.collapsible_box import CollapsibleBox

    group = FittingParameterGroup(
        name="kinetics",
        parameters=[FittingParameter(name="k1", value=1.0)],
    )

    class _Model:
        test_group = group

        def view_spec(self):
            return ds.ModelView(
                sections=(
                    ds.ParameterGroupTableSection(
                        target="test_group",
                        collapsible=False,
                    ),
                ),
            )

    w = AutoForm(_Model())
    boxes = w.findChildren(CollapsibleBox)
    # the CollapsibleBox may also appear from other sources, but none should
    # have "kinetics" as its title
    titles = [b.title() for b in boxes]
    assert all("kinetics" not in t for t in titles)


def test_widget_sizes_to_content_no_scroll(qapp):
    from qtpy import QtCore
    from chisurf.gui.autoform.sections.parameter_table import ParameterGroupTableWidget

    params = _make_params()
    widget = ParameterGroupTableWidget(params=params)
    # No internal vertical scrollbar, and height fits header + the four rows
    # (no big empty area below the last row).
    assert widget.table_view.verticalScrollBarPolicy() == QtCore.Qt.ScrollBarAlwaysOff
    assert widget.table_view.height() < 22 + widget._row_h * len(params) + 12


def test_name_column_renders_html_labels(qapp):
    from qtpy import QtCore
    from chisurf.gui.autoform.sections.parameter_table import (
        ParameterGroupTableWidget, _RichTextDelegate, COL_NAME,
    )

    params = _make_params()
    params[0].__dict__["label_text"] = "n<sub>0</sub>"
    widget = ParameterGroupTableWidget(params=params)
    assert isinstance(widget.table_view.itemDelegateForColumn(COL_NAME), _RichTextDelegate)
    # the model exposes the HTML label; the delegate renders it as rich text
    assert widget.table_model.index(0, COL_NAME).data(QtCore.Qt.DisplayRole) == "n<sub>0</sub>"


def test_copy_paste_values(qapp):
    from qtpy import QtCore, QtWidgets
    from chisurf.gui.autoform.sections.parameter_table import (
        ParameterGroupTableWidget, COL_VALUE,
    )

    params = _make_params()
    widget = ParameterGroupTableWidget(params=params)
    m = widget.table_model
    sel = widget.table_view.selectionModel()
    sel.select(m.index(0, COL_VALUE), QtCore.QItemSelectionModel.Select)
    widget._copy_selection()
    assert QtWidgets.QApplication.clipboard().text().strip() != ""
    # paste a scalar into another parameter's value
    QtWidgets.QApplication.clipboard().setText("7.25")
    widget.table_view.clearSelection()
    sel.select(m.index(2, COL_VALUE), QtCore.QItemSelectionModel.Select)
    widget._paste_selection()
    assert params[2].value == 7.25


def test_table_font_is_monospace(qapp):
    from qtpy import QtGui
    from chisurf.gui.autoform.sections.parameter_table import ParameterGroupTableWidget

    widget = ParameterGroupTableWidget(params=_make_params())
    # Matches the log/console styling: monospace family + Monospace style hint by
    # default (the actual resolved fixed-pitch depends on the installed fonts).
    font = widget.table_view.font()
    fixed_family = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont).family()
    assert font.styleHint() == QtGui.QFont.Monospace
    assert font.family() == fixed_family
