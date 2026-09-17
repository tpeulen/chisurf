"""``ScientificDoubleSpinBox`` must emit ``editingFinished`` when text is committed.

This is the "the plot does not update reliably" bug.

``ScientificDoubleSpinBox`` subclasses ``QAbstractSpinBox`` and manages its own
value, and it connects the **inner QLineEdit's** ``editingFinished`` to its text
commit. That is a different signal object from the spin box's own
``editingFinished``, and ``QAbstractSpinBox`` does not forward it for a subclass
like this one. Every ``FittingParameterWidget`` connects to the spin box's
``editingFinished`` (there is not a single ``valueChanged``/``sigValueChanged``
connection in ``parameter_widgets.py``), so committing typed text updated the
display and emitted ``sigValueChanged`` but never reached the model.

The result looked intermittent rather than broken: stepping with the arrows
worked, because ``stepBy()`` emits ``editingFinished`` explicitly, while typing
a value and pressing Enter left the model, the fit and the plots on the old
number.

``setValue()`` deliberately does *not* emit it -- that is the programmatic path
used to push fit results back into the widgets, and emitting there would write
the value straight back into the model.
"""

import pytest

pytest.importorskip("qtpy")

from chisurf.gui.widgets.fitting.scientific_spinbox import (  # noqa: E402
    ScientificDoubleSpinBox,
)


@pytest.fixture
def spin(qtbot):
    sb = ScientificDoubleSpinBox()
    qtbot.addWidget(sb)
    sb.setRange(0.0, 100.0)
    sb.setValue(2.0)
    return sb


def _count(sb):
    seen = {"n": 0}
    sb.editingFinished.connect(lambda: seen.__setitem__("n", seen["n"] + 1))
    return seen


def test_committing_typed_text_emits_editing_finished(spin):
    """The regression."""
    seen = _count(spin)
    spin.lineEdit().setText("9.25")
    spin.lineEdit().editingFinished.emit()

    assert spin.value() == pytest.approx(9.25)
    assert seen["n"] == 1, "typed value committed without emitting editingFinished"


def test_committing_an_unchanged_value_still_emits(spin):
    """Qt emits editingFinished on focus-out regardless of whether it changed."""
    seen = _count(spin)
    spin.lineEdit().setText("2.0")
    spin.lineEdit().editingFinished.emit()
    assert seen["n"] == 1


def test_stepping_emits_editing_finished(spin):
    """Already worked -- pinned so the two paths stay consistent."""
    seen = _count(spin)
    spin.stepUp()
    assert seen["n"] == 1
    assert spin.value() > 2.0


def test_set_value_does_not_emit_editing_finished(spin):
    """The programmatic path must stay silent, or fit results write themselves back."""
    seen = _count(spin)
    spin.setValue(7.5)
    assert spin.value() == pytest.approx(7.5)
    assert seen["n"] == 0


def test_invalid_text_does_not_change_the_value(spin):
    spin.lineEdit().setText("not-a-number")
    spin.lineEdit().editingFinished.emit()
    assert spin.value() == pytest.approx(2.0)


def test_committed_text_is_clamped_to_the_range(spin):
    spin.lineEdit().setText("1e6")
    spin.lineEdit().editingFinished.emit()
    assert spin.value() == pytest.approx(100.0)


def test_sig_value_changed_still_fires_on_commit(spin):
    seen = {"n": 0}
    spin.sigValueChanged.connect(lambda *_: seen.__setitem__("n", seen["n"] + 1))
    spin.lineEdit().setText("5.5")
    spin.lineEdit().editingFinished.emit()
    assert seen["n"] == 1


# ---------------------------------------------------------------------------
# End to end: the parameter must actually follow the widget.
# ---------------------------------------------------------------------------


def test_typed_value_reaches_the_fitting_parameter(qtbot):
    from chisurf.core.fitting.parameter import FittingParameter
    from chisurf.gui.widgets.fitting.parameter_widgets import FittingParameterWidget

    p = FittingParameter(value=2.0, name="tau", lb=0.01, ub=50.0)
    w = FittingParameterWidget(fitting_parameter=p)
    qtbot.addWidget(w)

    sb = w.widget_value
    sb.lineEdit().setText("9.25")
    sb.lineEdit().editingFinished.emit()

    assert float(p.value) == pytest.approx(9.25), (
        "typed value never reached the model — the plot would show a stale curve"
    )


def test_stepped_value_reaches_the_fitting_parameter(qtbot):
    from chisurf.core.fitting.parameter import FittingParameter
    from chisurf.gui.widgets.fitting.parameter_widgets import FittingParameterWidget

    p = FittingParameter(value=2.0, name="tau", lb=0.01, ub=50.0)
    w = FittingParameterWidget(fitting_parameter=p)
    qtbot.addWidget(w)

    w.widget_value.stepUp()
    assert float(p.value) == pytest.approx(w.widget_value.value())
