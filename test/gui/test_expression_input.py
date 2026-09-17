"""GUI tests for the single-expression ExpressionInput widget."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chisurf.gui.widgets.expression_input import ExpressionInput


def test_valid_parse_formula_is_ok_and_discovers_params(qapp):
    w = ExpressionInput()
    w.setText("a1*exp(-x/tau1) + a2*exp(-x/tau2)")
    assert w.is_valid()
    assert w.discovered_parameters() == ["a1", "tau1", "a2", "tau2"]


def test_x_is_reserved_not_a_parameter(qapp):
    w = ExpressionInput()
    w.setText("a1*exp(-x/tau1)")
    assert "x" not in w.discovered_parameters()


def test_unsafe_expression_is_invalid(qapp):
    w = ExpressionInput()
    w.setText("a.__class__")
    assert not w.is_valid()
    assert w._badge.text() == "✗"


def test_syntax_error_is_invalid(qapp):
    w = ExpressionInput()
    w.setText("a1*exp(")
    assert not w.is_valid()


def test_empty_is_neutral(qapp):
    w = ExpressionInput()
    w.setText("")
    assert w._badge.text() == ""
    assert not w.is_valid()


def test_parameters_changed_signal(qapp):
    w = ExpressionInput()
    seen = []
    w.parametersChanged.connect(lambda p: seen.append(list(p)))
    w.setText("a*exp(-x/t)")
    assert seen and seen[-1] == ["a", "t"]


def test_committed_only_when_valid(qapp):
    w = ExpressionInput()
    fired = []
    w.committed.connect(lambda s: fired.append(s))
    w.setText("a1*exp(-x/tau1)")
    w._on_return()
    assert fired == ["a1*exp(-x/tau1)"]
    fired.clear()
    w.setText("a1*exp(")  # invalid
    w._on_return()
    assert fired == []


def test_reserved_names_extra(qapp):
    # Extra reserved names (via provider) are not parameters.
    w = ExpressionInput(names_provider=lambda: ["t0"])
    w.setText("a*exp(-(x-t0)/tau)")
    assert w.is_valid()
    assert "t0" not in w.discovered_parameters()
    assert set(w.discovered_parameters()) == {"a", "tau"}


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
