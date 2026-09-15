"""Unlinking from a parameter table, and how a table shows link/fixed state.

Two defects met here. Unlinking addressed the backend by *name plus fit*, which
an out-of-fit parameter does not have: unlinking an ndX constant came back
"parameter 'gG/gR' not found" while the table went on painting it as unlinked.
And a table drew a linked follower and a fixed parameter exactly like a free
one, so which numbers the fit would actually move was invisible.
"""
from __future__ import annotations

import numpy as np
import pytest

import chisurf
import chisurf.core.data as data
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.models.description import tcspc_lifetime as LifetimeModel
from chisurf.core.registry.parameter_groups import (
    register_parameter_group,
    unregister_parameter_group,
)
from chisurf.gui.autoform.sections.parameter_table import (
    ParameterGroupTableModel,
    ParameterGroupTableWidget,
)
from chisurf.gui.widgets.fitting.fitting_client import install_fitting_client
from chisurf.server.services.fits import get_fit_info, list_fits
from chisurf.server.services.parameters import parameter_link, parameter_unlink
from chisurf.server.session import SessionState


def _fit() -> FitGroup:
    """A TCSPC fit over one synthetic decay."""
    x = np.arange(1, 64, dtype=np.float64)
    y = 1000.0 * np.exp(-x / 10.0) + 1.0
    curve = data.DataCurve(x=x, y=y, ey=np.sqrt(y), name="decay")
    return FitGroup(
        data=data.DataCurveGroup([curve], name="decay"), model_class=LifetimeModel
    )


class _RecordingClient:
    """Dispatch into the services and keep every call for inspection."""

    def __init__(self, state: SessionState):
        self._state = state
        self.calls: list[tuple[str, dict]] = []

    def call(self, method: str, params: dict):
        self.calls.append((method, dict(params)))
        if method == "fit.list":
            return list_fits(self._state)
        if method == "fit.get":
            return get_fit_info(self._state, **params)
        if method == "parameter.link":
            return parameter_link(self._state, **params)
        if method == "parameter.unlink":
            return parameter_unlink(self._state, **params)
        raise AssertionError(f"unexpected RPC call {method}")


@pytest.fixture
def session(qapp, monkeypatch):
    """A fit plus a registered out-of-fit group, behind a recording client."""
    fit = _fit()
    state = SessionState(fits=[fit])
    client = _RecordingClient(state)
    install_fitting_client(client)
    monkeypatch.setattr(chisurf, "fits", [fit], raising=False)

    group = FittingParameterGroup(name="ndx-constants")
    group._parameters = [FittingParameter(name="gG/gR", value=0.6)]
    register_parameter_group(group, owner_id="test-ndx", label="ndX")
    try:
        yield fit, group, client
    finally:
        unregister_parameter_group("test-ndx")
        install_fitting_client(None)


def test_an_out_of_fit_parameter_is_addressed_by_uuid(session):
    """Name plus fit cannot address it; its UUID and its group's can."""
    _fit_group, group, _client = session
    parameter = group.parameters_all[0]
    table = ParameterGroupTableWidget(group.parameters_all, parent=None)

    address = table._controller(0)._rpc_address(parameter)

    assert address["parameter_uid"] == str(parameter.unique_identifier)
    assert address["owner_uid"] == str(group.unique_identifier)
    assert "fit_uid" not in address


def test_unlinking_an_out_of_fit_parameter_reaches_the_backend(session):
    """The reported bug: "parameter 'gG/gR' not found" on every unlink."""
    fit, group, client = session
    parameter = group.parameters_all[0]
    parameter.link = fit.model.parameters_all_dict["scatter"]
    table = ParameterGroupTableWidget(group.parameters_all, parent=None)
    client.calls.clear()

    table._unlink(0)

    unlinks = [params for method, params in client.calls if method == "parameter.unlink"]
    assert unlinks and unlinks[0]["parameter_uid"] == str(parameter.unique_identifier)
    assert not parameter.is_linked


def test_a_backend_free_table_unlinks_locally(session):
    """A host whose parameters have no backend counterpart still unlinks.

    ndX renders its constants with ``remote=False`` — they belong to no fit and
    its edits are local by design. Unlinking used to ignore that flag and call
    the backend anyway, which is where the "not found" error came from.
    """
    fit, group, client = session
    parameter = group.parameters_all[0]
    parameter.link = fit.model.parameters_all_dict["scatter"]
    table = ParameterGroupTableWidget(group.parameters_all, parent=None, remote=False)
    client.calls.clear()

    table._unlink(0)

    assert not parameter.is_linked
    assert not [m for m, _ in client.calls if m == "parameter.unlink"]


def test_a_fit_parameter_still_carries_its_fit(session):
    """The fit address is kept alongside the UUID, so finalisation still lands."""
    fit, _group, _client = session
    parameter = fit.model.parameters_all_dict["scatter"]
    table = ParameterGroupTableWidget([parameter], parent=None)

    address = table._controller(0)._rpc_address(parameter)

    assert address["parameter_uid"] == str(parameter.unique_identifier)
    assert address["fit_uid"]
    assert address["owner_uid"]


def test_a_linked_follower_is_italic(session):
    """A borrowed value reads as borrowed."""
    fit, _group, _client = session
    follower = fit.model.parameters_all_dict["background"]
    follower.link = fit.model.parameters_all_dict["scatter"]

    assert ParameterGroupTableModel._font(follower).italic()
    assert ParameterGroupTableModel._font(fit.model.parameters_all_dict["scatter"]) is None


def test_a_value_the_fit_will_not_move_is_dimmed(session):
    """Fixed and linked values are dimmed; the name is not, and free values are not."""
    fit, _group, _client = session
    fixed = fit.model.parameters_all_dict["timeshift"]
    fixed.fixed = True
    free = fit.model.parameters_all_dict["t0"]
    free.fixed = False

    assert ParameterGroupTableModel._foreground("value", fixed) is not None
    assert ParameterGroupTableModel._foreground("name", fixed) is None
    assert ParameterGroupTableModel._foreground("value", free) is None


def test_a_parameter_is_addressed_by_its_own_fit_not_its_group(qapp, monkeypatch):
    """A grouped fit's member parameters must not be addressed by the group uid.

    ``FitGroup.model`` is the **selected** member's model, so a group uid
    resolves to whichever member happens to be selected.  Addressing a
    parameter of any *other* member by name plus that uid wrote the value to
    the selected member instead — silently, with ``ok: True``.
    """
    from chisurf.gui.widgets.fitting.parameter_widgets import (
        FittingParameterProxyController,
    )
    from chisurf.server.services.parameters import set_parameter_value

    x = np.arange(1, 64, dtype=np.float64)
    curves = [
        data.DataCurve(x=x, y=1000.0 * np.exp(-x / tau) + 1.0, ey=np.sqrt(
            1000.0 * np.exp(-x / tau) + 1.0), name=f"decay{tau}")
        for tau in (10.0, 20.0)
    ]
    fit = FitGroup(
        data=data.DataCurveGroup(curves, name="decays"), model_class=LifetimeModel
    )
    monkeypatch.setattr(chisurf, "fits", [fit], raising=False)
    members = list(fit.grouped_fits)
    assert len(members) == 2 and fit.selected_fit_index == 0

    # The parameter of the member that is *not* selected.
    target = members[1].model.parameters_all_dict["n0"]
    other = members[0].model.parameters_all_dict["n0"]
    target.value, other.value = 101.0, 100.0

    controller = FittingParameterProxyController(target)
    address = controller._rpc_address(target)
    assert address["fit_uid"] == str(members[1].unique_identifier)
    assert address["fit_uid"] != str(fit.unique_identifier)

    # Even without the UUID that normally short-circuits the lookup, the
    # name-plus-fit path must reach the owning member.
    legacy = {k: v for k, v in address.items() if k not in ("parameter_uid", "owner_uid")}
    result = set_parameter_value(state=SessionState(fits=[fit]), value=999.0, **legacy)

    assert result.get("ok") is True
    assert target.value == 999.0
    assert other.value == 100.0, "the write landed on the selected member"
