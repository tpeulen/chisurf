"""The ``data_table`` section's display options, shared with emtk's painted table.

A ranked table (ndX's *Find informative projections*) is declared once in a
``view.json`` and drawn by either renderer, so the options the painted one
honours -- ``display: "bar"`` with a ``range``, ``format``, ``columns_source``,
``sort``, ``tooltip_key``, ``row_key`` -- must mean the same here, and a source
that grows while a computation streams must be re-read without losing the sort
or the user's selection.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class Ranking:
    def __init__(self):
        self.rows = []
        self.picked = []
        self.method = "structure"

    def ranked_rows(self):
        return self.rows

    def ranked_columns(self):
        title, span = ("r", [-1, 1]) if self.method == "pearson" else ("Structure", [0, 1])
        return [
            {"key": "score", "title": title, "display": "bar", "range": span, "format": "%.3f"},
            {"key": "x", "title": "x"},
        ]

    def apply_row(self, record):
        self.picked.append(record)

    def add(self, score, x):
        self.rows.append({"score": score, "x": x, "key": x, "note": f"{x} scored {score}"})


OPTIONS = {
    "source": "ranked_rows", "columns_source": "ranked_columns", "selected_call": "apply_row",
    "sort": {"key": "score", "descending": True}, "tooltip_key": "note", "row_key": "key",
}


def make(model):
    from chisurf.gui.autoform.sections.data_table_section import DataTableSectionWidget

    return DataTableSectionWidget(model, **OPTIONS)


def shown(widget, column=1):
    from qtpy import QtCore

    model = widget.table._chi_model
    return [model.data(model.index(r, column), QtCore.Qt.DisplayRole) for r in range(model.rowCount())]


def test_a_bar_column_gets_the_bar_delegate_and_its_range(qapp):
    from chisurf.gui.widgets.chitable.delegates import BarDelegate

    model = Ranking()
    model.add(0.3, "a")
    widget = make(model)
    delegate = widget.table._view.itemDelegateForColumn(0)
    assert isinstance(delegate, BarDelegate)
    assert (delegate.lo, delegate.hi) == (0.0, 1.0)
    assert delegate.bar(0.5)[:2] == (0.0, 0.5)
    assert shown(widget, 0) == ["0.300"]
    # Only the declared columns: the identity and tooltip fields are not shown.
    assert [spec.key for spec in widget.table._chi_model.specs] == ["score", "x"]


def test_a_range_across_zero_diverges(qapp):
    from chisurf.gui.widgets.chitable.delegates import BarDelegate

    bar = BarDelegate((-1.0, 1.0))
    assert bar.bar(0.5)[:2] == (0.5, 0.75)
    assert bar.bar(-0.5)[:2] == (0.25, 0.5)
    assert bar.bar(0.5)[2] != bar.bar(-0.5)[2]


def test_sorted_best_first_and_streaming_keeps_sort_and_selection(qapp):
    model = Ranking()
    for score, x in [(0.2, "a"), (0.7, "b"), (0.4, "c")]:
        model.add(score, x)
    widget = make(model)
    assert shown(widget) == ["b", "c", "a"]
    widget.table._view.selectRow(1)  # "c"
    assert model.picked[-1]["x"] == "c"
    calls = len(model.picked)
    model.add(0.9, "d")
    model.add(0.1, "e")
    widget.refresh()
    assert shown(widget) == ["d", "b", "c", "a", "e"]
    selected = widget.table._view.selectionModel().currentIndex().row()
    assert shown(widget)[selected] == "c"
    assert len(model.picked) == calls, "re-selecting the same row must not re-apply it"


def test_tooltips_come_from_the_tooltip_key(qapp):
    from qtpy import QtCore

    model = Ranking()
    model.add(0.3, "a")
    widget = make(model)
    chi = widget.table._chi_model
    assert chi.data(chi.index(0, 1), QtCore.Qt.ToolTipRole) == "a scored 0.3"


def test_columns_follow_columns_source(qapp):
    from chisurf.gui.widgets.chitable.delegates import BarDelegate

    model = Ranking()
    model.add(0.3, "a")
    widget = make(model)
    model.method = "pearson"
    widget.refresh()
    chi = widget.table._chi_model
    from qtpy import QtCore

    assert chi.headerData(0, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole) == "r"
    delegate = widget.table._view.itemDelegateForColumn(0)
    assert isinstance(delegate, BarDelegate) and delegate.lo == -1.0
