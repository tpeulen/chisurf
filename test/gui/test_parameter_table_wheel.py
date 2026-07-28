"""The wheel edits the parameter under the mouse.

Reaching for a parameter, clicking into its cell, typing a number and pressing
Enter is four actions to try one value. Hovering it and turning the wheel is
one, and the fit follows immediately — which is how a parameter gets *explored*
rather than merely set.

The step has to be relative: a parameter table holds a lifetime of 4, an
amplitude of 1e-3 and a count of 1e6 at the same time, and a fixed step is
either useless on one or destructive on another.
"""
import pytest

from qtpy import QtCore, QtGui, QtWidgets

import chisurf
import chisurf.core.fitting.fit  # noqa: F401  (binds the fitting submodules)
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.gui.autoform.sections.parameter_table import (
    COLUMN_IDS,
    ParameterGroupTableWidget,
    WHEEL_COLUMNS,
    wheel_step,
)


def turn_wheel(view, row, column, notches=1, modifiers=QtCore.Qt.NoModifier):
    """Send one wheel event to the centre of a cell.

    Parameters
    ----------
    view : QtWidgets.QTableView
        The table.
    row, column : int
        Cell to point at.
    notches : int
        Wheel notches; negative turns the other way.
    modifiers : QtCore.Qt.KeyboardModifiers
        Modifiers held during the turn.
    """
    position = view.visualRect(view.model().index(row, column)).center()
    event = QtGui.QWheelEvent(
        QtCore.QPointF(position),
        QtCore.QPointF(view.viewport().mapToGlobal(position)),
        QtCore.QPoint(0, 0),
        QtCore.QPoint(0, 120 * notches),
        QtCore.Qt.NoButton,
        modifiers,
        QtCore.Qt.NoScrollPhase,
        False,
    )
    QtWidgets.QApplication.sendEvent(view.viewport(), event)


@pytest.fixture
def table(qtbot):
    """A parameter table over two parameters of very different magnitude."""
    params = [
        FittingParameter(name="tau", value=4.0),
        FittingParameter(name="x", value=0.001),
    ]
    widget = ParameterGroupTableWidget(params)
    qtbot.addWidget(widget)
    widget.resize(520, 140)
    widget.show()
    return widget, params


def test_the_wheel_steps_the_value_under_the_mouse(table):
    """Up adds, down subtracts, and the cell it lands on is the one that moves."""
    widget, params = table
    value_column = COLUMN_IDS.index("value")

    turn_wheel(widget.table_view, 0, value_column, +1)
    assert params[0].value == pytest.approx(4.1)
    assert params[1].value == pytest.approx(0.001), "the other row must not move"

    turn_wheel(widget.table_view, 0, value_column, -1)
    assert params[0].value == pytest.approx(4.0)


def test_the_step_is_relative_to_the_value_it_moves(table):
    """One notch is one percent of the value's own magnitude.

    A step that suits a lifetime of 4 would take a thousand turns to move an
    amplitude of 1e-3, and would obliterate it in one.
    """
    widget, params = table
    value_column = COLUMN_IDS.index("value")

    turn_wheel(widget.table_view, 1, value_column, +1)
    assert params[1].value == pytest.approx(0.0011)

    assert wheel_step(4.0) == pytest.approx(0.1)
    assert wheel_step(1.2e6) == pytest.approx(1e5)
    # Nothing to be relative to, so a tenth: small enough to be safe, large
    # enough to leave zero at all.
    assert wheel_step(0.0) == pytest.approx(0.1)


def test_modifiers_change_the_gear(table):
    """Ctrl is ten times coarser, Shift ten times finer, as in the spin boxes."""
    widget, params = table
    value_column = COLUMN_IDS.index("value")

    turn_wheel(widget.table_view, 0, value_column, +1, QtCore.Qt.ControlModifier)
    assert params[0].value == pytest.approx(5.0)

    turn_wheel(widget.table_view, 0, value_column, +1, QtCore.Qt.ShiftModifier)
    assert params[0].value == pytest.approx(5.01)


def test_bounds_can_be_wheeled_too(table):
    """They are numbers on the same row and are edited the same way."""
    widget, params = table
    params[0].bounds_on = True
    params[0].bounds = (1.0, 10.0)
    widget.table_view.model().layoutChanged.emit()

    turn_wheel(widget.table_view, 0, COLUMN_IDS.index("bounds_hi"), +1)
    # 10 sits on a decade boundary, so its step is 1 — the rule is one decade
    # below the value's own magnitude, i.e. between 1 % and 10 % of it.
    assert params[0].bounds[1] == pytest.approx(11.0)


def test_the_wheel_still_scrolls_where_there_is_nothing_to_edit(table):
    """Only the numeric columns take the wheel; the rest keep scrolling.

    A table that swallowed every wheel event would be a table you cannot
    scroll, which is worse than one you cannot spin.
    """
    widget, params = table
    assert set(WHEEL_COLUMNS) == {"value", "bounds_lo", "bounds_hi"}

    before = params[0].value
    turn_wheel(widget.table_view, 0, COLUMN_IDS.index("name"), +1)
    turn_wheel(widget.table_view, 0, COLUMN_IDS.index("error"), +1)
    assert params[0].value == before


def test_a_linked_follower_is_left_alone(table):
    """A follower takes its value from its master, wheel or no wheel.

    The event is then not consumed either, so the table still scrolls over it.
    """
    widget, params = table
    master = FittingParameter(name="master", value=9.0)
    params[0].link = master
    assert params[0].is_linked
    try:
        before = params[0].value
        turn_wheel(widget.table_view, 0, COLUMN_IDS.index("value"), +1)
        assert params[0].value == before
    finally:
        # The link is a reference the follower's port holds across into the
        # master. Leaving it dangling when this frame drops ``master`` takes
        # the process down later, in whichever test next repaints a table.
        params[0].link = None


def test_the_wheel_writes_through_the_same_path_as_typing(table):
    """It is an edit, not a poke at the object: the controller carries it.

    That is what makes the value reach the backend and the provenance trace,
    exactly as a typed edit does. A wheel that assigned the attribute directly
    would look identical here and be invisible everywhere else.
    """
    from chisurf.gui.autoform.sections.parameter_table import _editor

    widget, params = table
    controller = _editor(params[0])
    assert controller is not None, "the table installs a controller on every parameter"

    applied = []
    original = controller.apply_value
    controller.apply_value = lambda value, parameter=None: (
        applied.append(value), original(value, parameter)
    )[1]
    try:
        turn_wheel(widget.table_view, 0, COLUMN_IDS.index("value"), +1)
        assert applied == [pytest.approx(4.1)]
    finally:
        controller.apply_value = original
