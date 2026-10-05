"""Registered transactions must use the actual owner's authorization policy."""

from types import SimpleNamespace

import pytest

import chisurf as cs
from chisurf.core.data import DataCurve
from chisurf.core.project import capture_session
from chisurf.core.project.transition import replace_project
from chisurf.server.dispatcher import ServiceDispatcher
from chisurf.server.services.projects import register_project_snapshot_services
from chisurf.server.session import SessionState


@pytest.fixture
def guarded_owner(monkeypatch):
    """Own a real curve and a rejecting declared GUI without touching user state."""
    curve = DataCurve(x=[0.0], y=[7.0])
    state = SessionState(datasets=[curve])
    calls = []
    gui = SimpleNamespace(_guard_project_transition=lambda: calls.append("guard") or False)
    state._project_gui = gui
    state._project_gui_required = True
    monkeypatch.setattr(cs, "cs", None)
    dispatcher = ServiceDispatcher(state)
    register_project_snapshot_services(dispatcher, state)
    return state, curve, gui, calls, dispatcher


def test_registered_begin_cannot_stage_a_rejected_owner(guarded_owner):
    """A method name must never grant destructive authority to a public caller."""
    state, curve, gui, calls, dispatcher = guarded_owner
    result = dispatcher.dispatch(
        "project.transition.begin", {"project": capture_session([], []).to_dict()}
    )
    assert result == {"ok": False, "cancelled": True}
    assert calls == ["guard"]
    assert state.datasets == [curve]
    assert getattr(state, "_project_transition", None) is None


@pytest.mark.parametrize("confirmed", [True, 1, {"ok": True}])
def test_confirmed_cannot_bypass_actual_owner_policy(guarded_owner, confirmed):
    """A caller's flag and arbitrary truthiness carry no owner authority."""
    state, curve, gui, calls, dispatcher = guarded_owner
    result = replace_project(capture_session([], []), owner=state, confirmed=confirmed)
    assert result == {"ok": False, "cancelled": True}
    assert calls == ["guard"]
    assert state.datasets == [curve]


@pytest.mark.parametrize("decision", [None, 1, {"ok": True}])
def test_registered_owner_policy_requires_exact_true(guarded_owner, decision):
    """An ambiguous authorization result cannot stage the owner's real curve."""
    state, curve, gui, calls, dispatcher = guarded_owner
    gui._guard_project_transition = lambda: calls.append("guard") or decision
    result = dispatcher.dispatch(
        "project.transition.begin", {"project": capture_session([], []).to_dict()}
    )
    assert result == {"ok": False, "cancelled": True}
    assert state.datasets == [curve]
    assert calls == ["guard"]


def test_registered_bound_owner_without_gui_fails_closed(guarded_owner):
    """Remote presentation ownership prevents implicit headless staging."""
    state, curve, gui, calls, dispatcher = guarded_owner
    del state._project_gui
    result = dispatcher.dispatch(
        "project.transition.begin", {"project": capture_session([], []).to_dict()}
    )
    assert result["ok"] is False
    assert "GUI" in result["error"]
    assert state.datasets == [curve]


def test_registered_capability_is_one_use_and_cross_owner_fails_closed(monkeypatch):
    """Only an already accepted owner operation can carry staging authority."""
    monkeypatch.setattr(cs, "cs", None)
    state = SessionState(datasets=[DataCurve(x=[0.0], y=[7.0])])
    peer = SessionState(datasets=[DataCurve(x=[0.0], y=[9.0])])
    calls = []
    gui = SimpleNamespace(_guard_project_transition=lambda: calls.append("guard") or True)
    state._project_gui = gui
    dispatcher, other = ServiceDispatcher(state), ServiceDispatcher(peer)
    register_project_snapshot_services(dispatcher, state)
    register_project_snapshot_services(other, peer)
    project = capture_session([], [])
    request = {"project": project.to_dict(), "resources": project.resources.to_transport_dict()}
    authorized = dispatcher.dispatch("project.transition.authorize", request)
    assert authorized["ok"] is True, authorized
    token = authorized["authorization"]
    assert calls == ["guard"]
    rejected = other.dispatch("project.transition.begin", {**request, "authorization": token})
    assert rejected["ok"] is False
    assert len(peer.datasets) == 1
    begun = dispatcher.dispatch("project.transition.begin", {**request, "authorization": token})
    assert begun["ok"] is True, begun
    assert calls == ["guard"]
    assert dispatcher.dispatch(
        "project.transition.finish",
        {
            "transaction_id": begun["transaction_id"],
            "commit": False,
        },
    ) == {"ok": True}
    replay = dispatcher.dispatch("project.transition.begin", {**request, "authorization": token})
    assert replay["ok"] is False
    assert len(state.datasets) == 1


def test_authorized_operation_cannot_be_retargeted(monkeypatch):
    """Authorization is bound to the exact project bytes, aliases and path."""
    from chisurf.core.project.project import ResourceContext

    monkeypatch.setattr(cs, "cs", None)
    state = SessionState(datasets=[DataCurve(x=[0.0], y=[7.0])])
    dispatcher = ServiceDispatcher(state)
    register_project_snapshot_services(dispatcher, state)
    project = capture_session([], [])
    request = {
        "project": project.to_dict(),
        "resources": project.resources.to_transport_dict(),
        "project_path": "/approved.cs.pto",
    }
    token = dispatcher.dispatch("project.transition.authorize", request)["authorization"]
    project.resources = ResourceContext({"attachments/changed": b"different"})
    result = dispatcher.dispatch(
        "project.transition.begin",
        {
            **request,
            "resources": project.resources.to_transport_dict(),
            "authorization": token,
        },
    )
    assert result["ok"] is False
    assert len(state.datasets) == 1


def test_gui_declared_remote_policy_is_not_caller_installable(monkeypatch):
    """A remote owner applies only the policy supplied by its actual bootstrap."""
    monkeypatch.setattr(cs, "cs", None)
    state = SessionState(datasets=[DataCurve(x=[0.0], y=[7.0])])
    state._project_gui_required = True
    dispatcher = ServiceDispatcher(state)
    register_project_snapshot_services(dispatcher, state)
    project = capture_session([], [])
    request = {"project": project.to_dict(), "resources": project.resources.to_transport_dict()}
    denied = dispatcher.dispatch("project.transition.authorize", {**request, "confirmed": True})
    assert denied["ok"] is False
    calls = []
    state._project_transition_policy = lambda project, path: calls.append("owner-policy") or True
    allowed = dispatcher.dispatch("project.transition.authorize", request)
    assert allowed["ok"] is True
    assert calls == ["owner-policy"]
    begun = dispatcher.dispatch(
        "project.transition.begin",
        {
            **request,
            "authorization": allowed["authorization"],
        },
    )
    assert begun["ok"] is True
    assert dispatcher.dispatch(
        "project.transition.finish",
        {
            "transaction_id": begun["transaction_id"],
            "commit": True,
        },
    ) == {"ok": True}


def test_presentation_finalize_runs_only_after_ack_and_never_rolls_back(monkeypatch):
    """Retirement errors occur after commitment and cannot resurrect old science."""
    from chisurf.core.project.transition import PreparedPresentation

    monkeypatch.setattr(cs, "cs", None)
    state = SessionState(datasets=[DataCurve(x=[0.0], y=[7.0])])
    events = []

    def present(uids, ui):
        """Prepare one actual owner publication with explicit retirement."""

        def finalize():
            """Observe commitment before a disposal failure."""
            assert state._project_transition is None
            assert state.datasets == []
            events.append("finalize")
            raise RuntimeError("retired resource failure")

        return PreparedPresentation(
            commit=lambda: events.append("commit"),
            rollback=lambda: events.append("rollback"),
            finalize=finalize,
        )

    with pytest.raises(RuntimeError, match="retired resource failure"):
        replace_project(capture_session([], []), owner=state, present=present)
    assert events == ["commit", "finalize"]
    assert state.datasets == []


def test_macro_file_load_uses_one_owner_decision(monkeypatch, tmp_path):
    """Authorized file decoding and publication consume the same operation."""
    from chisurf.core.project.storage import save_file
    from chisurf.macros.core_fit import load_project

    calls = []
    gui = SimpleNamespace(_guard_project_transition=lambda: calls.append("guard") or True)
    monkeypatch.setattr(cs, "cs", gui)
    monkeypatch.setattr(cs, "fits", [])
    monkeypatch.setattr(cs, "imported_datasets", [DataCurve(x=[0.0], y=[7.0])])
    monkeypatch.setattr(cs, "__client__", None, raising=False)
    path = save_file(capture_session([], []), tmp_path / "incoming.cs.pto")
    result = load_project(str(path))
    assert result["ok"] is True
    assert calls == ["guard"]


def test_headless_grant_is_invalid_after_gui_ownership_changes(monkeypatch):
    """Attaching a GUI invalidates previously issued headless operation authority."""
    monkeypatch.setattr(cs, "cs", None)
    state = SessionState(datasets=[DataCurve(x=[0.0], y=[7.0])])
    dispatcher = ServiceDispatcher(state)
    register_project_snapshot_services(dispatcher, state)
    request = {"project": capture_session([], []).to_dict()}
    token = dispatcher.dispatch("project.transition.authorize", request)["authorization"]
    assert dispatcher.dispatch("project.presentation.attach") == {"ok": True}
    result = dispatcher.dispatch("project.transition.begin", {**request, "authorization": token})
    assert result["ok"] is False
    assert len(state.datasets) == 1


def test_capability_rejects_retargeted_history_and_document_path(monkeypatch):
    """History publication and target identity are part of the authorized operation."""
    monkeypatch.setattr(cs, "cs", None)
    state = SessionState(datasets=[DataCurve(x=[0.0], y=[7.0])])
    dispatcher = ServiceDispatcher(state)
    register_project_snapshot_services(dispatcher, state)
    project = capture_session([], [])
    request = {"project": project.to_dict(), "project_path": "/approved.cs.pto"}
    token = dispatcher.dispatch("project.transition.authorize", request)["authorization"]
    project.extra["history_events"] = [{"action_type": "retargeted"}]
    result = dispatcher.dispatch(
        "project.transition.begin",
        {
            **request,
            "project": project.to_dict(),
            "authorization": token,
        },
    )
    assert result["ok"] is False
    assert len(state.datasets) == 1
    token = dispatcher.dispatch("project.transition.authorize", request)["authorization"]
    result = dispatcher.dispatch(
        "project.transition.begin",
        {
            **request,
            "project_path": "/different.cs.pto",
            "authorization": token,
        },
    )
    assert result["ok"] is False
    assert len(state.datasets) == 1


def test_declared_tcspc_dependencies_publish_at_actual_api_owner(monkeypatch):
    """An IRF behind the declared model facade must not break registry publication."""
    from chisurf.core.api import ChiSurfAPI
    from chisurf.core.base import Base
    from chisurf.core.project.session import _local_fits
    from test.gui.test_tcspc_project_visual_roundtrip import _simulated_fit

    monkeypatch.setattr(cs, "cs", None)
    fit = _simulated_fit()
    state = SessionState(
        datasets=[m.data for m in fit.grouped_fits],
        fits=[fit],
        current_fit_uid=fit.unique_identifier,
    )
    api = ChiSurfAPI(mode="local", state=state)
    project = api.capture_project()
    irf_uids = [record["dependencies"]["irf"] for record in project.fits[0]["members"]]
    expected = [member.model.convolve._irf.y.copy() for member in _local_fits(fit)]
    result = api.restore_project_payload(project)
    assert result["ok"] is True, result
    for member, uid, values in zip(_local_fits(state.fits[0]), irf_uids, expected):
        dependency = member.model.convolve._irf
        assert dependency.unique_identifier == uid
        assert state.registry._datasets[uid] is dependency
        assert Base._uuid_index[uid] is dependency
        import numpy as np

        np.testing.assert_array_equal(dependency.y, values)


def test_direct_registered_begin_scopes_implicit_server_document_path(monkeypatch):
    """Metadata-derived publication paths cannot invalidate a legitimate operation."""
    monkeypatch.setattr(cs, "cs", None)
    state = SessionState(datasets=[DataCurve(x=[0.0], y=[7.0])])
    dispatcher = ServiceDispatcher(state)
    register_project_snapshot_services(dispatcher, state)
    project = capture_session([], [])
    project.metadata["server_session"] = {"project_path": "/captured.cs.pto"}
    begun = dispatcher.dispatch("project.transition.begin", {"project": project.to_dict()})
    assert begun["ok"] is True, begun
    assert state.project_path == "/captured.cs.pto"
    assert dispatcher.dispatch(
        "project.transition.finish",
        {
            "transaction_id": begun["transaction_id"],
            "commit": False,
        },
    ) == {"ok": True}


def test_failed_publication_restores_canonical_history_navigation_state(monkeypatch):
    """Cursor and scientific history caches survive failed project publication."""
    from chisurf.history.core import OperationHistory

    monkeypatch.setattr(cs, "cs", None)
    history = OperationHistory()
    state = SessionState(datasets=[DataCurve(x=[0.0], y=[7.0])])
    state.history = history
    project = capture_session(state.datasets, [])
    history.configure_science(lambda: project, lambda restored: {"ok": True})
    history.record("test.record", "isolated scientific edit", persist=False)
    original = history.export_state()
    states = history._science_states
    baseline = history._baseline
    cursor = history.cursor_index()

    def fail(*args):
        """Fail after the actual history replacement clears navigation caches."""
        assert history.cursor_index() == -1
        raise RuntimeError("history publication failed")

    with pytest.raises(RuntimeError, match="history publication failed"):
        replace_project(capture_session([], []), owner=state, present=fail)
    assert history.export_state() == original
    assert history._science_states is states
    assert history._baseline is baseline
    assert history.cursor_index() == cursor


def test_approval_cannot_destroy_work_created_after_authorization(monkeypatch):
    """Stale approval for old science cannot authorize discarding newly edited work."""
    monkeypatch.setattr(cs, "cs", None)
    curve = DataCurve(x=[0.0], y=[7.0])
    state = SessionState(datasets=[curve])
    calls = []
    state._project_gui = SimpleNamespace(
        _guard_project_transition=lambda: calls.append("guard") or True,
    )
    dispatcher = ServiceDispatcher(state)
    register_project_snapshot_services(dispatcher, state)
    request = {"project": capture_session([], []).to_dict()}
    token = dispatcher.dispatch("project.transition.authorize", request)["authorization"]
    curve.y = [11.0]
    result = dispatcher.dispatch("project.transition.begin", {**request, "authorization": token})
    assert result["ok"] is False
    assert state.datasets == [curve]
    assert curve.y[0] == 11.0
    assert calls == ["guard"]


def test_pending_replacement_cannot_issue_another_operation_capability(monkeypatch):
    """An unacknowledged owner stage cannot authorize subsequent destruction."""
    monkeypatch.setattr(cs, "cs", None)
    state = SessionState(datasets=[DataCurve(x=[0.0], y=[7.0])])
    dispatcher = ServiceDispatcher(state)
    register_project_snapshot_services(dispatcher, state)
    request = {"project": capture_session([], []).to_dict()}
    begun = dispatcher.dispatch("project.transition.begin", request)
    assert begun["ok"] is True
    result = dispatcher.dispatch("project.transition.authorize", request)
    assert result["ok"] is False
    assert dispatcher.dispatch(
        "project.transition.finish",
        {
            "transaction_id": begun["transaction_id"],
            "commit": False,
        },
    ) == {"ok": True}


@pytest.mark.parametrize("invalid", [True, False, "approved", {"ok": True}])
def test_invalid_declared_headless_policy_does_not_mean_consent(monkeypatch, invalid):
    """An invalid owning-state policy never falls back to implicit permission."""
    monkeypatch.setattr(cs, "cs", None)
    state = SessionState(datasets=[DataCurve(x=[0.0], y=[7.0])])
    state._project_transition_policy = invalid
    dispatcher = ServiceDispatcher(state)
    register_project_snapshot_services(dispatcher, state)
    result = dispatcher.dispatch(
        "project.transition.begin", {"project": capture_session([], []).to_dict()}
    )
    assert result["ok"] is False
    assert len(state.datasets) == 1


def test_failed_public_read_revokes_its_owner_operation(monkeypatch):
    """Failure before staging must not leave an approved destructive operation live."""
    from chisurf.server.services.projects import _public_transition

    monkeypatch.setattr(cs, "cs", None)
    state = SessionState(datasets=[DataCurve(x=[0.0], y=[7.0])])
    state._project_gui = SimpleNamespace(_guard_project_transition=lambda: True)

    def fail_read():
        """Reject detached decoding before any owner mutation."""
        raise ValueError("read failed")

    with pytest.raises(ValueError, match="read failed"):
        _public_transition(state, fail_read)
    assert getattr(state, "_project_authorizations", {}) == {}
    assert len(state.datasets) == 1


def test_local_entrypoint_policy_receives_exact_target_identity(monkeypatch):
    """An explicit owning-state policy sees the same target that is published."""
    monkeypatch.setattr(cs, "cs", None)
    state = SessionState(datasets=[DataCurve(x=[0.0], y=[7.0])])
    project = capture_session([], [], name="approved")
    calls = []
    state._project_transition_policy = lambda target, path: (
        calls.append((target, path)) or (target is project and path == "/approved.cs.pto")
    )
    result = replace_project(project, owner=state, project_path="/approved.cs.pto")
    assert result["ok"] is True, result
    assert calls == [(project, "/approved.cs.pto")]


@pytest.mark.parametrize("lost", ["begin", "ack"])
def test_lost_rpc_reply_reconciles_actual_owner_before_view_retirement(monkeypatch, lost):
    """A real dispatched stage/commit must be reconciled when its reply is lost."""
    from chisurf.core.plugin.client import InProcessClient
    from chisurf.core.project.transition import PreparedPresentation

    monkeypatch.setattr(cs, "cs", None)
    curve = DataCurve(x=[0.0], y=[7.0])
    state = SessionState(datasets=[curve])
    state._project_gui = SimpleNamespace(_guard_project_transition=lambda: True)
    dispatcher = ServiceDispatcher(state)
    register_project_snapshot_services(dispatcher, state)
    events = []

    class LostReplyClient(InProcessClient):
        """Discard one reply only after its actual registered handler executes."""

        def call(self, method, params=None, timeout=None):
            """Inject transport delivery failure without fabricating service results."""
            result = super().call(method, params, timeout)
            if (lost == "begin" and method == "project.transition.begin") or (
                lost == "ack" and method == "project.transition.finish" and params["commit"] is True
            ):
                raise RuntimeError("actual reply delivery lost")
            return result

    client = LostReplyClient(dispatcher)

    def present(*args):
        """Retain old resources until the actual owner's commit is established."""
        return PreparedPresentation(
            lambda: events.append("publish"),
            lambda: events.append("rollback"),
            lambda: events.append("retire"),
        )

    if lost == "begin":
        with pytest.raises(RuntimeError, match="actual reply delivery lost"):
            replace_project(capture_session([], []), client=client, present=present)
        assert state.datasets == [curve]
        assert state._project_transition is None
        assert events == []
    else:
        result = replace_project(capture_session([], []), client=client, present=present)
        assert result["ok"] is True
        assert state.datasets == []
        assert state._project_transition is None
        assert events == ["publish", "retire"]


def test_authorization_observes_live_science_without_reconstructing_it(monkeypatch):
    """Approval to discard live TCSPC science cannot rebuild it as a side effect."""
    from test.project.test_server_project_snapshot import _state_with_real_fit

    monkeypatch.setattr(cs, "cs", None)
    state = _state_with_real_fit()
    model_class = type(state.fits[0].grouped_fits[0].model)
    construct = model_class.__init__
    constructions = []

    def observe_construction(self, *args, **kwargs):
        """Count actual scientific reconstruction without altering its behavior."""
        constructions.append(True)
        construct(self, *args, **kwargs)

    monkeypatch.setattr(model_class, "__init__", observe_construction)
    result = replace_project(capture_session([], []), owner=state)
    assert result["ok"] is True, result
    assert state.datasets == state.fits == []
    assert constructions == []
