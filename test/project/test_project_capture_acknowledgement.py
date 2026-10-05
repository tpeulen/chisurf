"""Every capture frontend requires an explicit authoritative acknowledgement."""

from __future__ import annotations

import pytest

import chisurf as cs
from chisurf.core.api import ChiSurfAPI
from chisurf.core.api._proxies import ProxyDatasetList, ProxyFitList
from chisurf.core.plugin.client import InProcessClient
from chisurf.core.project.session import capture_session
from chisurf.macros.core_fit import get_project_payload
from chisurf.server.dispatcher import ServiceDispatcher
from chisurf.server.services.projects import register_project_snapshot_services
from chisurf.server.session import SessionState


@pytest.mark.parametrize("route", ["macro", "api"])
@pytest.mark.parametrize("ack", [None, False, "true", 1, {}])
def test_capture_rejects_nonexplicit_acknowledgement(monkeypatch, route, ack):
    """A real captured DTO does not make a failed/missing acknowledgement valid."""
    project = capture_session([], [], name="actual empty capture control")
    reply = {"project": project.to_dict(), "resources": project.resources.to_transport_dict()}
    if ack is not None:
        reply["ok"] = ack
    state = SessionState()
    dispatcher = ServiceDispatcher(state)
    dispatcher._build_default_registry()
    register_project_snapshot_services(dispatcher, state)

    class FaultReplyClient(InProcessClient):
        def call(self, method, params=None, timeout=None):
            if method == "project.capture":
                return reply
            return super().call(method, params, timeout)

    client = FaultReplyClient(dispatcher)
    monkeypatch.setattr(cs, "cs", None, raising=False)
    monkeypatch.setattr(cs, "_project_gui", None, raising=False)
    monkeypatch.setattr(cs, "__client__", client, raising=False)
    monkeypatch.setattr(cs, "imported_datasets", ProxyDatasetList(client))
    monkeypatch.setattr(cs, "fits", ProxyFitList(client))
    api = ChiSurfAPI(client=client, mode="server", state=state)
    with pytest.raises(RuntimeError, match="Project capture failed"):
        get_project_payload() if route == "macro" else api.capture_project()
    assert state.datasets == []
    assert state.fits == []
