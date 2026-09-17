"""The wheel edits the parameter under the mouse.

Reaching for a parameter, clicking into its cell, typing a number and pressing
Enter is four actions to try one value. Hovering it and turning the wheel is
one, and the fit follows immediately — which is how a parameter gets *explored*
rather than merely set.

The step has to be relative: a parameter table holds a lifetime of 4, an
amplitude of 1e-3 and a count of 1e6 at the same time, and a fixed step is
either useless on one or destructive on another.
"""
import numpy as np
import pytest
from qtpy import QtCore, QtGui, QtWidgets

import chisurf
import chisurf.core.fitting.fit  # noqa: F401  (binds the fitting submodules)
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.gui.autoform.sections.parameter_table import (
    COLUMN_IDS,
    WHEEL_COLUMNS,
    ParameterGroupTableWidget,
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
    return event.isAccepted()


def turn_wheel_raw(view, row, column, delta):
    """Send one wheel event with a raw ``angleDelta`` (eighths of a degree)."""
    position = view.visualRect(view.model().index(row, column)).center()
    event = QtGui.QWheelEvent(
        QtCore.QPointF(position),
        QtCore.QPointF(view.viewport().mapToGlobal(position)),
        QtCore.QPoint(0, 0),
        QtCore.QPoint(0, delta),
        QtCore.Qt.NoButton,
        QtCore.Qt.NoModifier,
        QtCore.Qt.NoScrollPhase,
        False,
    )
    QtWidgets.QApplication.sendEvent(view.viewport(), event)
    return event.isAccepted()


@pytest.fixture
def table_long(qtbot):
    """A table with far more rows than its viewport can show."""
    params = [FittingParameter(name=f"p{i}", value=1.0) for i in range(40)]
    widget = ParameterGroupTableWidget(params)
    qtbot.addWidget(widget)
    # A table sizes itself to its rows unless its host bounds it; a bounded
    # one scrolls what does not fit, which is the case under test.
    widget.set_scrollable(3)
    widget.resize(520, 120)
    widget.show()
    return widget, params


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
    """One notch is one decade below the value's own magnitude (1–10 % of it).

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


# --- what the review of this feature found (RF-834..RF-839) ----------------

def test_a_cell_the_table_declares_read_only_is_not_wheeled(table):
    """RF-834: a bound that is not enforced paints blank and cannot be typed.

    It must not be wheelable either — the write lands invisibly and then clamps
    the parameter the moment bounds are switched on.
    """
    widget, params = table
    assert not params[0].bounds_on
    index = widget.table_view.model().index(0, COLUMN_IDS.index("bounds_lo"))
    assert not (widget.table_view.model().flags(index) & QtCore.Qt.ItemIsEditable)

    before = (params[0].lb, params[0].ub, params[0].value)
    turn_wheel(widget.table_view, 0, COLUMN_IDS.index("bounds_lo"), +1)
    assert (params[0].lb, params[0].ub, params[0].value) == before

    params[0].bounds_on = True
    assert params[0].value == pytest.approx(4.0), "the parameter was clamped"


def test_editing_one_bound_leaves_the_other_alone(table):
    """RF-835: the untouched half must not become nan.

    ``param.bounds`` is masked by enforcement; ``lb``/``ub`` are not, and the
    partner has to be read through them.
    """
    widget, params = table
    params[0].bounds_on = True
    params[0].bounds = (1.0, 10.0)

    turn_wheel(widget.table_view, 0, COLUMN_IDS.index("bounds_lo"), +1)
    # 1.0 steps by 0.1, one decade below its magnitude.
    assert params[0].lb == pytest.approx(1.1)
    assert params[0].ub == pytest.approx(10.0)
    assert not np.isnan(params[0].ub)


def test_wheel_motion_is_measured_not_counted(table):
    """RF-836: a trackpad sends fractions of a detent and a wheel sends several.

    One event is not one step: the motion is accumulated in units of 120.
    """
    widget, params = table
    value_column = COLUMN_IDS.index("value")
    view = widget.table_view

    # An eighth of a detent, eight times, is one step — not eight.
    for _ in range(8):
        turn_wheel_raw(view, 0, value_column, 15)
    assert params[0].value == pytest.approx(4.1)

    # Ten detents merged into one event are ten steps, not one.
    before = params[1].value
    turn_wheel_raw(view, 1, value_column, 1200)
    assert params[1].value == pytest.approx(before + 10 * 0.0001)


def test_a_long_table_can_still_be_scrolled(table_long):
    """RF-837: reaching a parameter must not retune the ones passed on the way.

    With something to scroll, only the cell the user made current is edited.
    """
    widget, params = table_long
    view = widget.table_view
    value_column = COLUMN_IDS.index("value")
    bar = view.verticalScrollBar()
    assert bar.maximum() > bar.minimum(), "the fixture must overflow its viewport"

    before = [p.value for p in params]
    for _ in range(3):
        turn_wheel(view, 0, value_column, -1)
    assert [p.value for p in params] == before, "wheeling over a value retuned it"
    assert bar.value() > 0, "the table did not scroll"

    # ...and the parameter the user selected is still wheelable.
    view.setCurrentIndex(view.model().index(0, value_column))
    turn_wheel(view, 0, value_column, +1)
    assert params[0].value != before[0]


def test_a_value_pinned_at_its_bound_scrolls_instead_of_swallowing(table):
    """RF-838: an edit that changes nothing must not eat the gesture."""
    widget, params = table
    params[0].bounds_on = True
    params[0].bounds = (1.0, 4.0)
    params[0].value = 4.0

    accepted = turn_wheel(widget.table_view, 0, COLUMN_IDS.index("value"), +1)
    assert params[0].value == pytest.approx(4.0)
    assert not accepted, "the event was consumed although nothing moved"


def test_the_wheel_reaches_zero_and_crosses_it(table):
    """RF-839: an IRF time shift is legitimately negative.

    Re-deriving the step from a shrinking value makes the descent asymptotic —
    2000 notches from 1.0 reached 3e-23 and never zero. One step per gesture
    fixes that, so the wheel can take a parameter back through zero.
    """
    widget, params = table
    params[0].value = 1.0
    value_column = COLUMN_IDS.index("value")
    view = widget.table_view

    for _ in range(11):
        turn_wheel(view, 0, value_column, -1)
    assert params[0].value == pytest.approx(-0.1, abs=1e-9)


# --- what a changed parameter must actually do -----------------------------

def test_changing_a_parameter_recomputes_the_curve(qtbot):
    """The plot has to follow the value. Changing is not fitting.

    Nothing is optimised: the model is evaluated again at the value the user
    just set. Without this the table moved the number and left the curve, the
    residuals and chi2r on the old one.
    """
    import numpy as np

    import chisurf.core.data
    import chisurf.core.fitting.fit as fit_module
    import chisurf.core.models.parse

    rng = np.random.default_rng(0)
    x = np.linspace(0, 10, 64)
    y = 2.0 + 0.5 * x ** 2 + rng.normal(0, 0.5, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y))
    fit = fit_module.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x**2'
    fit.model.find_parameters()
    chisurf.fits.append(fit)
    try:
        params = list(fit.model.parameters_all)
        widget = ParameterGroupTableWidget(params)
        qtbot.addWidget(widget)
        widget.show()

        before_curve = np.array(fit.model.y[:6])
        before_chi2 = float(fit.chi2r)
        turn_wheel(widget.table_view, 0, COLUMN_IDS.index("value"), +1)

        assert not np.allclose(before_curve, fit.model.y[:6]), "the curve did not follow"
        assert float(fit.chi2r) != before_chi2
    finally:
        chisurf.fits.remove(fit)


def test_a_host_can_decline_the_backend(qtbot, monkeypatch):
    """nDXplorer's constants are rendered by this table and belong to no fit.

    Every edit used to attempt ``parameter.set_value`` for them, and the server
    answered "fit not found" — once per keystroke, or per wheel notch, with a
    stack trace each time.
    """
    import chisurf.gui.widgets.fitting.parameter_widgets as pw

    calls = []

    class _Client:
        """Stand-in fitting client that records what it was asked to do."""

        def __getattr__(self, name):
            def record(**_kw):
                calls.append(name)
            return record

    monkeypatch.setattr(pw, "get_fitting_client", lambda: _Client())

    params = [FittingParameter(name="R0", value=52.0)]
    widget = ParameterGroupTableWidget(params, remote=False)
    qtbot.addWidget(widget)
    widget.show()

    turn_wheel(widget.table_view, 0, COLUMN_IDS.index("value"), +1)

    assert params[0].value == pytest.approx(53.0), "the edit itself must still happen"
    assert calls == [], f"the backend was called for a host that declined it: {calls}"


def test_the_host_is_told_about_an_edit(qtbot):
    """The table's own controller notification is what redraws it.

    nDXplorer hangs its recompute on the same callback, so a missing
    notification is a stale plot there as much as a stale cell here.
    """
    params = [FittingParameter(name="R0", value=52.0)]
    notified = []
    widget = ParameterGroupTableWidget(
        params, remote=False, on_change=lambda: notified.append(True)
    )
    qtbot.addWidget(widget)
    widget.show()

    turn_wheel(widget.table_view, 0, COLUMN_IDS.index("value"), +1)
    assert notified, "the host was not told the parameter changed"
