"""ChiSurf's parameter table shows a vector as one expandable row.

Two kinds of vector reach the table: a group publishing one parameter per
population, named ``base[label]`` (nDXplorer's vector constants), and a
parameter whose value is an array. Before, the first read as unrelated rows and
the second as its first element only -- editing it silently collapsed the
array. Both are now a parent row, ``▸ base [n]`` with the values summed up,
that a click on the name opens; its elements are edited like any row.

``CHISURF_TABLE_SHOTS=<dir>`` saves the table there, for looking at.
"""

from __future__ import annotations

import os
import pathlib

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtCore, QtWidgets  # noqa: E402
from qtpy.QtTest import QTest  # noqa: E402

from chisurf.core.fitting.parameter import FittingParameter  # noqa: E402
from chisurf.gui.autoform.sections.parameter_table import (  # noqa: E402
    ParameterGroupTableWidget,
)


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _names(table):
    model = table.table_model
    return [str(model.index(r, 0).data()).strip() for r in range(model.rowCount())]


def _click_name(qapp, table, row):
    view = table.table_view
    rect = view.visualRect(table.table_model.index(row, 0))
    QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton, pos=rect.center())
    qapp.processEvents()


def _type_value(qapp, table, row, text):
    view = table.table_view
    rect = view.visualRect(table.table_model.index(row, 1))
    QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton, pos=rect.center())
    QTest.mouseDClick(view.viewport(), QtCore.Qt.LeftButton, pos=rect.center())
    qapp.processEvents()
    editor = view.findChild(QtWidgets.QLineEdit)
    assert editor is not None and editor.isVisible(), "the cell did not open for typing"
    editor.selectAll()
    QTest.keyClicks(editor, text)
    QTest.keyClick(editor, QtCore.Qt.Key_Return)
    qapp.processEvents()


def _shot(widget, name):
    folder = os.environ.get("CHISURF_TABLE_SHOTS")
    if folder:
        pathlib.Path(folder).mkdir(parents=True, exist_ok=True)
        widget.grab().save(str(pathlib.Path(folder) / f"{name}.png"))


def test_named_elements_read_as_one_vector(qapp):
    params = [
        FittingParameter(name="tau", value=4.0),
        FittingParameter(name="gamma", value=0.7, fixed=True),
        FittingParameter(name="gamma[HF]", value=0.61, fixed=True),
        FittingParameter(name="gamma[LF]", value=0.83, fixed=True),
        FittingParameter(name="x0", value=1.0),
    ]
    table = ParameterGroupTableWidget(params)
    table.resize(460, 260)
    table.show()
    assert _names(table) == ["tau", "▸ gamma [2]", "x0"]
    assert table.table_model.index(1, 1).data() == "0.61, 0.83"
    _click_name(qapp, table, 1)
    assert _names(table) == ["tau", "▾ gamma [2]", "(global)", "HF", "LF", "x0"]
    _type_value(qapp, table, 4, "0.9")
    assert params[3].value == pytest.approx(0.9)
    assert table.table_model.index(1, 1).data() == "0.61, 0.9"
    # The parent's Fixed frees every element, not the global value.
    model = table.table_model
    assert model.setData(model.index(1, 2), False, QtCore.Qt.EditRole)
    assert not params[2].fixed and not params[3].fixed and params[1].fixed
    # Every parameter still has its controller (the link menu, the popup).
    assert all(getattr(p, "controller", None) is not None for p in params)
    assert model.top_level() == [params[0], params[1], params[4]]
    assert model.top_level_position(4) == 1 and model.top_level_position(5) == 2
    _shot(table, "named_vector")
    _click_name(qapp, table, 1)
    assert _names(table) == ["tau", "▸ gamma [2]", "x0"]


def test_an_array_valued_parameter_is_edited_element_by_element(qapp):
    vector = FittingParameter(name="amplitudes", value=np.array([1.0, 2.0, 3.0]))
    scalar = FittingParameter(name="offset", value=0.5)
    table = ParameterGroupTableWidget([vector, scalar])
    table.resize(460, 220)
    table.show()
    assert _names(table) == ["▸ amplitudes [3]", "offset"]
    assert table.table_model.index(0, 1).data() == "1, 2, 3"
    # The whole array is not typed into; its elements are.
    assert not table.table_model.flags(table.table_model.index(0, 1)) & QtCore.Qt.ItemIsEditable
    _click_name(qapp, table, 0)
    assert _names(table) == ["▾ amplitudes [3]", "[0]", "[1]", "[2]", "offset"]
    _type_value(qapp, table, 2, "5")
    assert np.allclose(vector._port.value, [1.0, 5.0, 3.0])
    # Fixed applies to the whole array, on its parent row.
    model = table.table_model
    assert model.setData(model.index(0, 2), True, QtCore.Qt.EditRole)
    assert vector.fixed
    _shot(table, "array_vector")
