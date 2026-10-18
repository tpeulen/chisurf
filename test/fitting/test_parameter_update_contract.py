"""Concrete scalar/fit parameters share their controller refresh contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.parameter import Parameter


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
