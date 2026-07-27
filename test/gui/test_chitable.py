"""Offscreen-Qt tests for the chitable table family.

Covers the three sources, the model's formatting/paging/edit rules, vectorised
filtering and sorting, the value-colour ramp, and the container widget's column
picker / hide-empty / copy / export behaviour.

Two tests are explicit regressions for defects the previous, item-based table
editor carried: a crash on pandas extension dtypes, and edits landing on the
wrong source row while a filter was active.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtCore, QtWidgets  # noqa: E402

from chisurf.gui.widgets.chitable import (  # noqa: E402
    ArraySource,
    ChiTableModel,
    ChiTableWidget,
    ColumnFilter,
    ColumnSpec,
    DataFrameSource,
    FilterSpec,
    RecordSource,
    ValueColorScheme,
    edit_dataframe,
    is_valid_format,
)
from chisurf.gui.widgets.chitable.model import LARGE_ROWS, ROWS_TO_LOAD  # noqa: E402


@pytest.fixture
def frame():
    """Return a small mixed-dtype frame used across the tests.

    Returns
    -------
    pandas.DataFrame
    """
    return pd.DataFrame(
        {
            "name": ["alpha", "beta", "gamma", "delta"],
            "value": [1.0, 20.0, 300.0, np.nan],
            "count": [1, 2, 3, 4],
            "flag": [True, False, True, False],
            "note": ["", "", "", ""],
        }
    )


# ── sources ──────────────────────────────────────────────────────────────


def test_dataframe_source_infers_kinds(frame):
    src = DataFrameSource(frame)
    kinds = {s.key: s.kind for s in src.column_specs()}
    assert kinds == {
        "name": "str",
        "value": "float",
        "count": "int",
        "flag": "bool",
        "note": "str",
    }
    assert src.row_count() == 4
    assert src.value(1, 0) == "beta"


def test_dataframe_source_handles_extension_dtypes():
    """Regression: nullable pandas dtypes must not raise.

    The previous editor tested numeric-ness with ``np.issubdtype``, which raises
    ``TypeError`` on ``Float64``/``Int64`` — exactly the dtypes the pyarrow
    reader produces for burst data.
    """
    df = pd.DataFrame(
        {
            "a": pd.array([1.5, None, 3.5], dtype="Float64"),
            "b": pd.array([1, 2, None], dtype="Int64"),
            "c": pd.array(["x", None, "z"], dtype="string"),
        }
    )
    src = DataFrameSource(df)
    kinds = [s.kind for s in src.column_specs()]
    assert kinds == ["float", "int", "str"]

    arr = src.column_array(0)
    assert arr.dtype == np.float64
    assert np.isnan(arr[1])

    model = ChiTableModel(src)
    assert model.data(model.index(0, 0), QtCore.Qt.DisplayRole) == "1.5"
    assert model.data(model.index(1, 0), QtCore.Qt.DisplayRole) == ""


def test_array_source_pads_short_columns():
    src = ArraySource(
        {"x": np.arange(5.0), "model": np.arange(3.0)},
        editable_keys=("x",),
    )
    assert src.row_count() == 5
    assert np.isnan(src.value(4, 1))
    assert src.is_editable(0, 0) is True
    assert src.is_editable(0, 1) is False
    padded = src.column_array(1)
    assert padded.shape == (5,)
    assert np.isnan(padded[3:]).all()


def test_array_source_notifies_on_set():
    seen = []
    src = ArraySource(
        {"x": np.zeros(3)},
        editable_keys=("x",),
        on_set=lambda key, row, value: seen.append((key, row, value)),
    )
    assert src.set_value(1, 0, 7.0)
    assert src.value(1, 0) == 7.0
    assert seen == [("x", 1, 7.0)]


class _Row:
    """Minimal record object for :class:`RecordSource` tests."""

    def __init__(self, name, value, fixed):
        self.name = name
        self.value = value
        self.fixed = fixed


def test_record_source_reads_and_writes_through_setter():
    rows = [_Row("a", 1.0, False), _Row("b", 2.0, True)]
    specs = [
        ColumnSpec(key="name", label="Name", kind="str"),
        ColumnSpec(key="value", label="Value", kind="float", editable=True),
        ColumnSpec(key="fixed", label="Fixed", kind="bool", editable=True),
    ]
    written = []

    def setter(obj, key, value):
        written.append((obj.name, key, value))
        setattr(obj, key, value)
        return True

    src = RecordSource(rows, specs, setter=setter)
    assert src.row_count() == 2
    assert src.value(1, 0) == "b"
    assert src.set_value(0, 1, 9.0)
    assert rows[0].value == 9.0
    assert written == [("a", "value", 9.0)]
    assert src.column_array(1).tolist() == [9.0, 2.0]


# ── model ────────────────────────────────────────────────────────────────


def test_model_formats_and_aligns(frame):
    model = ChiTableModel(DataFrameSource(frame))
    assert model.rowCount() == 4
    assert model.columnCount() == 5
    assert model.data(model.index(2, 1), QtCore.Qt.DisplayRole) == "300"
    assert model.data(model.index(3, 1), QtCore.Qt.DisplayRole) == ""
    right = int(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
    assert model.data(model.index(0, 1), QtCore.Qt.TextAlignmentRole) == right
    left = int(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
    assert model.data(model.index(0, 0), QtCore.Qt.TextAlignmentRole) == left
    assert model.data(model.index(0, 3), QtCore.Qt.TextAlignmentRole) == int(QtCore.Qt.AlignCenter)


def test_model_default_format_is_validated(frame):
    model = ChiTableModel(DataFrameSource(frame))
    assert is_valid_format("%.3f")
    assert not is_valid_format("nonsense")
    assert model.set_default_format("%.2f")
    assert model.data(model.index(0, 1), QtCore.Qt.DisplayRole) == "1.00"
    assert not model.set_default_format("nope")
    assert model.data(model.index(0, 1), QtCore.Qt.DisplayRole) == "1.00"


def test_model_edit_flags_follow_source(frame):
    model = ChiTableModel(DataFrameSource(frame, editable=True, readonly_columns=("name",)))
    assert not (model.flags(model.index(0, 0)) & QtCore.Qt.ItemIsEditable)
    assert model.flags(model.index(0, 1)) & QtCore.Qt.ItemIsEditable
    assert model.setData(model.index(0, 1), "42", QtCore.Qt.EditRole)
    assert frame.iat[0, 1] == 42.0
    assert not model.setData(model.index(0, 0), "nope", QtCore.Qt.EditRole)


def test_model_pages_large_tables():
    df = pd.DataFrame({"x": np.arange(LARGE_ROWS + 10, dtype=float)})
    model = ChiTableModel(DataFrameSource(df))
    assert model.total_row_count() == LARGE_ROWS + 10
    assert model.rowCount() == ROWS_TO_LOAD
    assert model.can_fetch_more()
    model.fetch_more()
    assert model.rowCount() == 2 * ROWS_TO_LOAD
    model.fetch_all()
    assert model.rowCount() == LARGE_ROWS + 10
    assert not model.can_fetch_more()


def test_model_empty_columns(frame):
    model = ChiTableModel(DataFrameSource(frame))
    assert model.column_index("note") in model.empty_columns()
    assert model.column_index("name") not in model.empty_columns()


def test_model_column_range_ignores_nan(frame):
    model = ChiTableModel(DataFrameSource(frame))
    assert model.column_range(model.column_index("value")) == (1.0, 300.0)


def test_model_staged_edits_commit_and_rollback(frame):
    src = DataFrameSource(frame, editable=True)
    model = ChiTableModel(src, staged=True)
    model.setData(model.index(0, 1), "5", QtCore.Qt.EditRole)
    assert model.data(model.index(0, 1), QtCore.Qt.DisplayRole) == "5"
    assert frame.iat[0, 1] == 1.0  # not written through yet
    model.rollback()
    assert model.data(model.index(0, 1), QtCore.Qt.DisplayRole) == "1"

    model.setData(model.index(0, 1), "5", QtCore.Qt.EditRole)
    assert model.commit() == 1
    assert frame.iat[0, 1] == 5.0


# ── filtering and sorting ────────────────────────────────────────────────


def test_global_search_filters_rows(frame):
    model = ChiTableModel(DataFrameSource(frame))
    model.set_filter(FilterSpec(query="a"))
    names = [model.data(model.index(r, 0), QtCore.Qt.DisplayRole) for r in range(model.rowCount())]
    assert names == ["alpha", "beta", "gamma", "delta"]
    model.set_filter(FilterSpec(query="mm"))
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0), QtCore.Qt.DisplayRole) == "gamma"


def test_numeric_column_filter(frame):
    model = ChiTableModel(DataFrameSource(frame))
    col = model.column_index("value")
    model.set_filter(FilterSpec(columns=(ColumnFilter(column=col, op="ge", value=20),)))
    assert model.rowCount() == 2
    model.set_filter(
        FilterSpec(columns=(ColumnFilter(column=col, op="between", value=0, value2=25),))
    )
    assert model.rowCount() == 2
    model.set_filter(FilterSpec(columns=(ColumnFilter(column=col, op="isnull"),)))
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0), QtCore.Qt.DisplayRole) == "delta"


def test_text_column_filter(frame):
    model = ChiTableModel(DataFrameSource(frame))
    col = model.column_index("name")
    model.set_filter(FilterSpec(columns=(ColumnFilter(column=col, op="startswith", value="del"),)))
    assert model.rowCount() == 1
    model.set_filter(FilterSpec(columns=(ColumnFilter(column=col, op="regex", value="^[bg]"),)))
    assert model.rowCount() == 2


def test_sort_is_stable_and_reversible(frame):
    model = ChiTableModel(DataFrameSource(frame))
    col = model.column_index("value")
    model.sort(col, QtCore.Qt.AscendingOrder)
    shown = [model.data(model.index(r, 0), QtCore.Qt.DisplayRole) for r in range(model.rowCount())]
    assert shown[:3] == ["alpha", "beta", "gamma"]
    model.sort(col, QtCore.Qt.DescendingOrder)
    shown = [model.data(model.index(r, 0), QtCore.Qt.DisplayRole) for r in range(model.rowCount())]
    assert shown[0] == "delta"  # NaN sorts last ascending, first descending
    assert shown[1] == "gamma"


def test_filter_and_sort_compose(frame):
    model = ChiTableModel(DataFrameSource(frame))
    model.set_filter(FilterSpec(query="a"))
    model.sort(model.column_index("value"), QtCore.Qt.DescendingOrder)
    assert model.rowCount() == 4
    assert model.data(model.index(1, 0), QtCore.Qt.DisplayRole) == "gamma"


def test_edit_while_filtered_writes_the_right_source_row(frame):
    """Regression: a filtered view must not write through the view index.

    The previous editor repopulated its widget from a filtered frame but wrote
    edits back with ``df.iloc[view_row, col]``, silently corrupting an unrelated
    row.
    """
    src = DataFrameSource(frame, editable=True)
    model = ChiTableModel(src)
    model.set_filter(FilterSpec(query="gamma"))
    assert model.rowCount() == 1
    assert model.source_row(0) == 2

    assert model.setData(model.index(0, 1), "999", QtCore.Qt.EditRole)
    assert frame.iat[2, 1] == 999.0
    assert frame.iat[0, 1] == 1.0


def test_source_and_view_row_round_trip(frame):
    model = ChiTableModel(DataFrameSource(frame))
    model.sort(model.column_index("value"), QtCore.Qt.DescendingOrder)
    for view_row in range(model.rowCount()):
        assert model.view_row(model.source_row(view_row)) == view_row


# ── colouring ────────────────────────────────────────────────────────────


def test_color_ramp_spans_the_range():
    scheme = ValueColorScheme(enabled=True)
    low = scheme.color(0.0, 0.0, 10.0)
    high = scheme.color(10.0, 0.0, 10.0)
    mid = scheme.color(5.0, 0.0, 10.0)
    assert low is not None and high is not None and mid is not None
    assert low.hueF() != high.hueF()
    assert min(low.hueF(), high.hueF()) <= mid.hueF() <= max(low.hueF(), high.hueF())


def test_color_handles_degenerate_range_and_nan():
    scheme = ValueColorScheme(enabled=True)
    assert scheme.color(5.0, 5.0, 5.0) is not None
    assert scheme.color(float("nan"), 0.0, 1.0) is None
    assert scheme.color("text", 0.0, 1.0) is None


def test_color_disables_itself_on_huge_tables():
    scheme = ValueColorScheme(enabled=True, max_cells=50)
    assert scheme.affordable(10, 5)
    assert not scheme.affordable(1000, 5)

    df = pd.DataFrame({"x": np.arange(50.0), "y": np.arange(50.0)})
    model = ChiTableModel(DataFrameSource(df), color_scheme=scheme)
    assert not model.color_affordable()
    assert model.data(model.index(0, 0), QtCore.Qt.BackgroundRole) is None


def test_background_applies_to_numeric_columns_only(frame):
    model = ChiTableModel(DataFrameSource(frame), color_scheme=ValueColorScheme(enabled=True))
    assert model.data(model.index(0, 1), QtCore.Qt.BackgroundRole) is not None
    assert model.data(model.index(0, 0), QtCore.Qt.BackgroundRole) is None


# ── widget ───────────────────────────────────────────────────────────────


def test_widget_shows_frame_and_reports_status(qapp, frame):
    widget = ChiTableWidget()
    widget.set_dataframe(frame)
    assert widget.table_model.rowCount() == 4
    assert "4 rows" in widget._status.text()
    widget.set_search_text("gamma")
    assert widget.visible_row_count() == 1
    assert "1 / 4 rows" in widget._status.text()
    widget.deleteLater()


def test_widget_hide_empty_columns(qapp, frame):
    widget = ChiTableWidget()
    widget.set_dataframe(frame)
    note = widget.table_model.column_index("note")
    assert not widget.table_view.isColumnHidden(note)
    widget.hide_empty_columns(True)
    assert widget.table_view.isColumnHidden(note)
    widget.hide_empty_columns(False)
    assert not widget.table_view.isColumnHidden(note)
    widget.deleteLater()


def test_widget_select_columns(qapp, frame):
    widget = ChiTableWidget()
    widget.set_dataframe(frame)
    widget.select_columns(["name", "value"])
    hidden = [widget.table_view.isColumnHidden(c) for c in range(widget.table_model.columnCount())]
    assert hidden == [False, False, True, True, True]
    widget.deleteLater()


def test_widget_copy_with_headers(qapp, frame):
    widget = ChiTableWidget()
    widget.set_dataframe(frame)
    view = widget.table_view
    view.selectAll()
    text = view.copy_selection(include_header=True)
    lines = text.splitlines()
    assert lines[0].split("\t")[:2] == ["name", "value"]
    assert lines[1].split("\t")[0] == "alpha"
    assert len(lines) == 5
    widget.deleteLater()


def test_widget_export_csv_honours_filter(qapp, frame, tmp_path):
    widget = ChiTableWidget()
    widget.set_dataframe(frame)
    widget.set_search_text("gamma")
    out = tmp_path / "table.csv"
    assert widget.export_csv(str(out)) == str(out)
    written = pd.read_csv(out)
    assert len(written) == 1
    assert written["name"].iloc[0] == "gamma"
    widget.deleteLater()


def test_widget_export_csv_omits_hidden_columns(qapp, frame, tmp_path):
    widget = ChiTableWidget()
    widget.set_dataframe(frame)
    widget.select_columns(["name"])
    out = tmp_path / "one.csv"
    widget.export_csv(str(out))
    assert list(pd.read_csv(out).columns) == ["name"]
    widget.deleteLater()


def test_widget_wraps_a_foreign_model(qapp):
    """A bespoke model keeps its semantics and still gains search."""

    class _Model(QtCore.QAbstractTableModel):
        def __init__(self):
            super().__init__()
            self._rows = [("a", 1), ("bb", 2), ("ccc", 3)]

        def rowCount(self, parent=QtCore.QModelIndex()):
            return 0 if parent.isValid() else len(self._rows)

        def columnCount(self, parent=QtCore.QModelIndex()):
            return 0 if parent.isValid() else 2

        def data(self, index, role=QtCore.Qt.DisplayRole):
            if role != QtCore.Qt.DisplayRole or not index.isValid():
                return None
            return str(self._rows[index.row()][index.column()])

        def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
                return ["Name", "Value"][section]
            return None

    source = _Model()
    widget = ChiTableWidget(model=source)
    assert widget.table_model is source
    assert widget.visible_row_count() == 3
    widget.set_filter(FilterSpec(query="cc"))
    assert widget.visible_row_count() == 1
    widget.set_filter(FilterSpec(columns=(ColumnFilter(column=1, op="ge", value=2),)))
    assert widget.visible_row_count() == 2
    widget.deleteLater()


def test_foreign_proxy_strips_source_backgrounds(qapp):
    """With no scheme the proxy removes any background the source paints."""

    class _Colored(QtCore.QAbstractTableModel):
        def rowCount(self, parent=QtCore.QModelIndex()):
            return 0 if parent.isValid() else 1

        def columnCount(self, parent=QtCore.QModelIndex()):
            return 0 if parent.isValid() else 1

        def data(self, index, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.BackgroundRole:
                from qtpy import QtGui

                return QtGui.QColor("red")
            if role == QtCore.Qt.DisplayRole:
                return "1"
            return None

    widget = ChiTableWidget(model=_Colored())
    proxy = widget.proxy
    assert proxy is not None
    assert proxy.data(proxy.index(0, 0), QtCore.Qt.BackgroundRole) is None
    widget.deleteLater()


# ── dialog ───────────────────────────────────────────────────────────────


def test_edit_dataframe_cancel_leaves_original_untouched(qapp, frame, monkeypatch):
    monkeypatch.setattr(
        QtWidgets.QDialog, "exec_", lambda self: QtWidgets.QDialog.Rejected, raising=False
    )
    assert edit_dataframe(frame) is None
    assert frame.iat[0, 1] == 1.0


def test_edit_dataframe_accept_returns_a_copy(qapp, frame, monkeypatch):
    def _accept(self):
        model = self.table.table_model
        model.setData(model.index(0, 1), "77", QtCore.Qt.EditRole)
        self.accept()
        return QtWidgets.QDialog.Accepted

    monkeypatch.setattr(
        "chisurf.gui.widgets.chitable.editor.ChiTableDialog.exec_", _accept, raising=False
    )
    out = edit_dataframe(frame)
    assert out is not None
    assert out.iat[0, 1] == 77.0
    assert frame.iat[0, 1] == 1.0  # the caller's frame is never mutated


def test_edit_dataframe_readonly_columns_and_bool_delegate(qapp, frame, monkeypatch):
    from chisurf.gui.widgets.chitable.delegates import BooleanToggleDelegate

    checked = {}

    def _inspect(self):
        # Assert while the dialog is alive: its C++ objects go as soon as
        # ``edit_dataframe`` returns and drops the last reference.
        model = self.table.table_model
        checked["name_readonly"] = not (model.flags(model.index(0, 0)) & QtCore.Qt.ItemIsEditable)
        checked["value_editable"] = bool(model.flags(model.index(0, 1)) & QtCore.Qt.ItemIsEditable)
        flag_col = model.column_index("flag")
        checked["bool_delegate"] = isinstance(
            self.table.table_view.itemDelegateForColumn(flag_col), BooleanToggleDelegate
        )
        self.reject()
        return QtWidgets.QDialog.Rejected

    monkeypatch.setattr(
        "chisurf.gui.widgets.chitable.editor.ChiTableDialog.exec_", _inspect, raising=False
    )
    edit_dataframe(frame, readonly_columns=("name",), bool_columns=("flag",))
    assert checked == {
        "name_readonly": True,
        "value_editable": True,
        "bool_delegate": True,
    }


def test_status_line_follows_row_changes_in_a_wrapped_model(qtbot):
    """A foreign model's row changes must reach the status line.

    Only ``dataChanged`` was connected, and a model does not emit that when rows
    are inserted or removed. A table wrapping an external model and filled after
    construction therefore reported "0 rows" while plainly showing them — and
    went on disagreeing with the view for the rest of the session.
    """
    from qtpy import QtGui

    from chisurf.gui.widgets.chitable import ChiTableWidget

    model = QtGui.QStandardItemModel(0, 2)
    model.setHorizontalHeaderLabels(["a", "b"])
    widget = ChiTableWidget(model=model)
    qtbot.addWidget(widget)

    assert widget.total_row_count() == 0

    for row in range(3):
        model.insertRow(row)
        model.setItem(row, 0, QtGui.QStandardItem(str(row)))
    assert widget.total_row_count() == 3, "row insertion did not reach the status line"

    model.removeRow(0)
    assert widget.total_row_count() == 2, "row removal did not reach the status line"

    model.setRowCount(0)
    assert widget.total_row_count() == 0


def _paint_ink_width(delegate, text: str, width: int = 240, height: int = 24) -> int:
    """Return the horizontal extent of the ink ``delegate`` paints for ``text``.

    Paints a single cell holding ``text`` onto a white pixmap and measures the
    distance between the first and last column carrying a non-white pixel. The
    raw source ``&nu;`` is four glyphs wide; the entity rendered as ν is one, so
    the width tells rendered from unrendered apart without pinning exact pixels.

    Parameters
    ----------
    delegate : qtpy.QtWidgets.QStyledItemDelegate
        Delegate whose ``paint`` is exercised.
    text : str
        Display text of the single cell.
    width, height : int
        Size of the painted cell.

    Returns
    -------
    int
        Ink width in pixels, ``0`` when nothing was painted.
    """
    from qtpy import QtGui

    model = QtGui.QStandardItemModel(1, 1)
    model.setItem(0, 0, QtGui.QStandardItem(text))
    pixmap = QtGui.QPixmap(width, height)
    pixmap.fill(QtGui.QColor("white"))
    option = QtWidgets.QStyleOptionViewItem()
    option.rect = QtCore.QRect(0, 0, width, height)
    option.state = QtWidgets.QStyle.State_Enabled
    painter = QtGui.QPainter(pixmap)
    try:
        delegate.paint(painter, option, model.index(0, 0))
    finally:
        painter.end()

    image = pixmap.toImage()
    columns = [
        x
        for x in range(width)
        for y in range(height)
        if QtGui.QColor(image.pixel(x, y)) != QtGui.QColor("white")
    ]
    return 0 if not columns else max(columns) - min(columns) + 1


def test_rich_text_delegate_renders_entity_only_labels(qapp):
    """Regression (RF-432): a label made only of entities was printed verbatim.

    ``RichTextDelegate`` decided whether a cell needed HTML by testing for
    ``<``, so ``&nu;`` / ``&#8491;`` never reached ``QTextDocument`` and the two
    shape parameters of the DEER Rice model — and the FCS and SAW-ν brightness
    labels — rendered as their source text in every model editor. The sibling
    ``RichTextHeaderView`` already tested for ``<`` *or* ``&``.
    """
    from chisurf.gui.widgets.chitable.delegates import RichTextDelegate

    rich = RichTextDelegate()
    plain = QtWidgets.QStyledItemDelegate()

    raw = _paint_ink_width(plain, "&nu;")
    rendered = _paint_ink_width(rich, "&nu;")
    assert raw > 0, "the plain delegate painted nothing — measurement is not valid"
    assert rendered > 0, "the rich delegate painted nothing"
    # One glyph, not four: entity-only labels must go through the HTML path.
    assert rendered < raw / 2, f"&nu; rendered {rendered}px wide against {raw}px of raw source"

    # Numeric entities too, and markup keeps working.
    assert _paint_ink_width(rich, "&#8491;") < _paint_ink_width(plain, "&#8491;") / 2
    assert _paint_ink_width(rich, "n<sub>0</sub>") < _paint_ink_width(plain, "n<sub>0</sub>") / 2

    # Plain text still takes the cheap path: same ink as the base delegate.
    assert _paint_ink_width(rich, "tau") == _paint_ink_width(plain, "tau")
