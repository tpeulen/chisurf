"""Concrete scalar/fit parameters share their actual controller refresh contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.parameter import Parameter, ParameterGroup
from chisurf.gui.widgets.fitting.parameter_widgets import make_fitting_parameter_widget


@pytest.mark.parametrize("parameter_type", [Parameter, FittingParameter])
@pytest.mark.parametrize("operation", ["update", "set_state"])
def test_real_editor_follows_explicit_parameter_refresh(qtbot, parameter_type, operation):
    """A real bare or fitting scalar editor follows model updates and restored state."""
    parameter = parameter_type(name="scalar", value=2.0)
    editor = make_fitting_parameter_widget(parameter)
    qtbot.addWidget(editor)
    uid = parameter.unique_identifier
    if operation == "update":
        parameter.value = 7.25
        parameter.update()
    else:
        parameter.set_state({"value": 7.25})
    assert parameter.value == editor.widget_value.value() == 7.25
    assert parameter.unique_identifier == uid
    assert editor.fitting_parameter is parameter


@pytest.mark.parametrize("derived", ["linked", "callable"])
@pytest.mark.parametrize("operation", ["update", "set_state"])
def test_real_derived_editor_reflects_current_graph_value(qtbot, derived, operation):
    """Refreshing shows the linked/computed scalar instead of its previous display value."""
    master = Parameter(name="master", value=2.0)
    if derived == "linked":
        parameter = Parameter(name="follower", link=master)
    else:
        parameter = Parameter(name="computed", value=lambda: master.value * 3.0)
    editor = make_fitting_parameter_widget(parameter)
    qtbot.addWidget(editor)
    master.value = 5.0
    if operation == "update":
        parameter.update()
    else:
        parameter.set_state({"description": "restored derived parameter"})
    expected = 5.0 if derived == "linked" else 15.0
    assert parameter.value == editor.widget_value.value() == expected


@pytest.mark.parametrize("parameter_type", [Parameter, FittingParameter])
def test_group_state_refreshes_its_existing_parameter_editor(qtbot, parameter_type):
    """The group's existing state hook refreshes each owned parameter's actual controller."""
    parameter = parameter_type(name="scale", value=2.0)
    group = ParameterGroup(parameters=[parameter])
    group.scale = parameter
    editor = make_fitting_parameter_widget(parameter)
    qtbot.addWidget(editor)
    group.scale = 5.75
    group.set_state({})
    assert group.values == [5.75]
    assert editor.widget_value.value() == 5.75
    assert group.parameters[0] is parameter


@pytest.mark.parametrize("parameter_type", [Parameter, FittingParameter])
def test_update_and_state_restore_notify_exactly_once(parameter_type):
    """Shared behavior neither duplicates fitting notifications nor mutates scalar state."""
    parameter = parameter_type(name="scalar", value=2.0)
    calls = []
    parameter.controller = SimpleNamespace(finalize=lambda: calls.append(parameter.value))
    assert parameter.update() is None
    assert calls == [2.0]
    parameter.set_state({"value": 5.75})
    assert calls == [2.0, 5.75]


@pytest.mark.parametrize("parameter_type", [Parameter, FittingParameter])
def test_controller_failure_keeps_existing_logged_nonthrowing_contract(parameter_type, caplog):
    """Controller failure is logged while the scientific value remains usable."""

    def fail():
        """Represent a controller that cannot repaint its view."""
        raise RuntimeError("controller failed to repaint")

    parameter = parameter_type(name="scalar", value=2.0)
    parameter.controller = SimpleNamespace(finalize=fail)
    assert parameter.update() is None
    assert parameter.value == 2.0
    assert "Failed to finalize parameter controller" in caplog.text


@pytest.mark.parametrize("parameter_type", [Parameter, FittingParameter])
def test_no_controller_preserves_pull_based_linked_and_callable_semantics(parameter_type):
    """Explicit notifications do not eagerly calculate or alter ports without controllers."""
    master = parameter_type(name="master", value=2.0)
    follower = parameter_type(name="follower", link=master)
    calls = []
    computed = parameter_type(value=lambda: calls.append(master.value) or master.value * 3.0)
    before = len(calls)
    assert master.update() is follower.update() is computed.update() is None
    assert len(calls) == before
    master.value = 4.0
    assert follower.value == 4.0 and computed.value == 12.0
    master.set_state({"value": 5.0})
    assert follower.value == 5.0 and computed.value == 15.0
