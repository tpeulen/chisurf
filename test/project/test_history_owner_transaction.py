"""History facade ownership and identity across authoritative replacements."""

import builtins
import copy
import importlib
import os
import subprocess
import sys
from pathlib import Path
from threading import RLock
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

import chisurf as cs
from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit
from chisurf.core.plugin.client import InProcessClient
from chisurf.core.project import capture_session
from chisurf.core.project.lifecycle import ProjectDocument
from chisurf.core.project.transition import OwnerTransaction, PreparedPresentation, replace_project
from chisurf.history.core import OperationHistory
from chisurf.server.dispatcher import ServiceDispatcher
from chisurf.server.services.projects import register_project_snapshot_services
from chisurf.server.session import SessionState
from test.project.test_server_project_snapshot import SnapshotLinearModel


def _assert_namespace(namespace, saved):
    """Check exact keys and entry identities without invoking object equality."""
    assert namespace.keys() == saved.keys()
    assert all(namespace[key] is value for key, value in saved.items())


def _isolated(request, tmp_path):
    """Keep a regressed builtins rollback inside a disposable interpreter."""
    if os.environ.get("CHISURF_HISTORY_OWNER_CHILD") == "1":
        return False
    env = os.environ.copy()
    env["CHISURF_HISTORY_OWNER_CHILD"] = "1"
    command = [
        sys.executable,
        "-m",
        "pytest",
        request.node.nodeid,
        "-q",
        "--tb=short",
        f"--basetemp={tmp_path / 'child'}",
        f"--junitxml={tmp_path / 'child.xml'}",
        "-p",
        "no:cacheprovider",
    ]
    result = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
    )
    (tmp_path / "child.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "child.xml").is_file()
    return True


def _live(monkeypatch, route):
    """Use the real facade singleton and real science on each owner route."""
    import IMP.bff as bff

    facade = importlib.import_module("chisurf.history")
    history = facade.get_history()
    old_event = OperationHistory().record("old", "Original operation", {"n": [1]}, persist=False)
    monkeypatch.setattr(history, "_events", [copy.deepcopy(old_event)])
    monkeypatch.setattr(history, "_cursor", 0)
    monkeypatch.setattr(history, "_checkpoints", {0: {"selection": [0]}})
    monkeypatch.setattr(history, "_subscribers", [])
    curve = DataCurve(x=np.arange(4.0), y=np.arange(4.0) + 1, ex=np.ones(4), ey=np.ones(4))
    fit = Fit(data=curve, model_class=SnapshotLinearModel)
    fit.model.update()
    native = bff.get_session()
    state = SessionState(datasets=[curve], fits=[fit], current_fit_uid=fit.unique_identifier)
    values = dict(
        history=facade,
        fits=state.fits,
        experiments={"old": {"setup": ["old"]}},
        current_fit=fit,
        current_fit_idx=0,
        current_fit_uid=fit.unique_identifier,
        native_session=native,
        project_metadata={"old": ["metadata"]},
        project_path="/old.cs.pto",
        project_name="old",
        _project_transition=None,
    )
    owner = cs if route == "local" else state
    for name, value in values.items():
        monkeypatch.setattr(owner, name, value, raising=False)
    dataset_attr = "imported_datasets" if route == "local" else "datasets"
    monkeypatch.setattr(owner, dataset_attr, state.datasets, raising=False)
    if route == "local":
        monkeypatch.setattr(cs, "__client__", None, raising=False)
        monkeypatch.setattr(cs, "cs", None, raising=False)
    client = None
    if route == "server":
        dispatcher = ServiceDispatcher(state)
        dispatcher._build_default_registry()
        register_project_snapshot_services(dispatcher, state)
        client = InProcessClient(dispatcher)
    document = ProjectDocument(name="old", project_id="old-id", version_id="old-version")
    document._saved_fingerprint = "old-baseline"
    window = SimpleNamespace(resource=RLock(), disposed=False)
    gui = SimpleNamespace(current_fit=fit, _fit_idx=0, windows=[window])
    project = capture_session([], [], name="incoming")
    incoming_event = OperationHistory().record("incoming", "Incoming operation", persist=False)
    project.extra["history_events"] = [copy.deepcopy(incoming_event)]
    return SimpleNamespace(
        owner=owner,
        client=client,
        dataset_attr=dataset_attr,
        facade=facade,
        history=history,
        curve=curve,
        fit=fit,
        native=native,
        document=document,
        gui=gui,
        window=window,
        project=project,
        old_event=old_event,
        incoming_event=incoming_event,
    )


@pytest.mark.parametrize("route", ["local", "explicit", "server"])
@pytest.mark.parametrize("failure", ["presentation", "publication"])
def test_facade_failed_replacement_restores_exact_live_state(
    monkeypatch,
    request,
    tmp_path,
    route,
    failure,
):
    """Failed synchronous publication preserves singleton state and namespaces."""
    if _isolated(request, tmp_path):
        return
    s = _live(monkeypatch, route)
    history = s.history
    events, checkpoints, subscribers = history._events, history._checkpoints, history._subscribers
    lock = history._lock
    nested = events[0]["payload"]["n"]
    selection = checkpoints[0]["selection"]
    datasets, fits = getattr(s.owner, s.dataset_attr), s.owner.fits
    experiments, metadata = s.owner.experiments, s.owner.project_metadata
    windows = s.gui.windows
    document_state = dict(s.document.__dict__)
    facade_dict, builtins_dict = s.facade.__dict__, builtins.__dict__
    facade_state, builtins_state = dict(facade_dict), dict(builtins_dict)

    # Fail safely before a regressed implementation can erase Python's builtins.
    probe = OwnerTransaction(s.owner, s.project)
    assert not any(
        target is builtins_dict or target is facade_dict
        for target, _ in probe.history_state.mutable.containers
    )

    def present(uids, ui):
        """Mutate real history and selection before a synchronous failure."""
        assert s.owner._project_transition.active
        assert not s.window.disposed
        assert uids == []
        assert history.list_events() == [s.incoming_event]
        nested.append(2)
        selection.append(1)
        history._subscribers.append(present)
        s.gui.current_fit, s.gui._fit_idx = None, -1
        if failure == "presentation":
            raise RuntimeError("presentation failed")

        def publish():
            """Keep old windows alive even after document publication."""
            assert s.document.name == "incoming"
            assert s.owner._project_transition.active
            assert not s.window.disposed
            windows.clear()
            raise RuntimeError("publication failed")

        def rollback():
            """Restore the retained original window after owner rollback."""
            assert s.owner._project_transition is None
            windows[:] = [s.window]

        return PreparedPresentation(publish, rollback)

    with pytest.raises(RuntimeError, match=f"{failure} failed"):
        replace_project(
            s.project,
            owner=None if route != "explicit" else s.owner,
            client=s.client,
            gui=s.gui,
            document=s.document,
            target_identity=ProjectDocument(name="incoming"),
            present=present,
            confirmed=True,
        )
    assert getattr(s.owner, s.dataset_attr) is datasets and datasets == [s.curve]
    assert s.owner.fits is fits and fits == [s.fit]
    assert s.owner.current_fit is s.fit and s.owner.current_fit_idx == 0
    assert s.owner.current_fit_uid == s.fit.unique_identifier
    assert s.owner.native_session is s.native
    assert s.owner.experiments is experiments and experiments == {"old": {"setup": ["old"]}}
    assert s.owner.project_metadata is metadata and metadata == {"old": ["metadata"]}
    assert s.owner.project_path == "/old.cs.pto" and s.owner.project_name == "old"
    assert s.owner.history is s.facade and s.facade.get_history() is history
    assert history._events is events and events == [s.old_event]
    assert events[0]["payload"]["n"] is nested
    assert history._checkpoints is checkpoints and checkpoints == {0: {"selection": [0]}}
    assert checkpoints[0]["selection"] is selection
    assert history._subscribers is subscribers and subscribers == []
    assert history._lock is lock
    with lock:
        assert history.list_events() == events
    assert s.gui.current_fit is s.fit and s.gui._fit_idx == 0
    assert s.gui.windows is windows and windows == [s.window] and not s.window.disposed
    _assert_namespace(s.document.__dict__, document_state)
    assert s.facade.__dict__ is facade_dict and builtins.__dict__ is builtins_dict
    _assert_namespace(facade_dict, facade_state)
    _assert_namespace(builtins_dict, builtins_state)
    assert s.owner._project_transition is None


@pytest.mark.parametrize("route", ["local", "explicit", "server"])
def test_facade_success_and_capture_use_singleton(monkeypatch, route):
    """Accepted replacement and subsequent capture share the same history owner."""
    s = _live(monkeypatch, route)
    lock = s.history._lock
    facade_state, builtins_state = dict(s.facade.__dict__), dict(builtins.__dict__)

    def present(uids, ui):
        """Check old resources remain retained until acknowledgement."""
        assert s.owner._project_transition.active and not s.window.disposed
        assert s.history.list_events() == [s.incoming_event]
        return PreparedPresentation(lambda: None, lambda: None)

    result = replace_project(
        s.project,
        owner=None if route != "explicit" else s.owner,
        client=s.client,
        present=present,
        confirmed=True,
    )
    assert result["ok"] is True and result["fit_count"] == 0
    assert getattr(s.owner, s.dataset_attr) == [] and s.owner.fits == []
    assert s.owner._project_transition is None and not s.window.disposed
    assert s.owner.history is s.facade and s.history._lock is lock
    assert s.history._checkpoints == {}
    if route == "server":
        from chisurf.core.project import Project

        captured = Project.from_dict(s.client.call("project.capture", {})["project"])
    elif route == "local":
        from chisurf.macros.core_fit import get_project_payload

        captured = get_project_payload()
    else:
        from chisurf.core.project import Project
        from chisurf.server.services.projects import capture_project_payload

        captured = Project.from_dict(capture_project_payload(s.owner)["project"])
    assert captured.extra["history_events"] == [s.incoming_event]
    _assert_namespace(s.facade.__dict__, facade_state)
    _assert_namespace(builtins.__dict__, builtins_state)


def test_unknown_module_facade_fails_before_mutation():
    """Arbitrary module namespaces cannot become transaction-owned state."""
    facade = ModuleType("unsupported_history")
    facade.load_events = lambda events, replace=True: None
    facade.get_history = lambda: SimpleNamespace(events=[])
    owner = SimpleNamespace(datasets=[object()], fits=[], history=facade)
    datasets = owner.datasets
    with pytest.raises(ValueError, match="history"):
        OwnerTransaction(owner, capture_session([], []))
    assert owner.datasets is datasets and len(datasets) == 1
    assert not hasattr(owner, "_project_transition")


def test_lock_bearing_history_ignores_namespace_and_registry_attributes():
    """Concrete history rollback owns bounded data, never imported runtime state."""

    class History:
        """A concrete history with runtime resources and unrelated namespaces."""

        def __init__(self):
            """Retain a lock and cache beside explicitly unowned module state."""
            self.events = [{"action_type": "old"}]
            self.runtime = {"lock": RLock(), "cache": ["old"], "namespace": sys.__dict__}
            self.module = sys.modules[__name__]
            self.globals = globals()
            self.registry = {"imported": []}

        def load_events(self, events, replace=True):
            """Mutate owned event and cache contents only."""
            self.events[:] = events
            self.runtime["cache"].clear()

    history = History()
    owner = SimpleNamespace(datasets=[], fits=[], history=history)
    transaction = OwnerTransaction(owner, capture_session([], []))
    forbidden = (
        globals(),
        builtins.__dict__,
        history.registry,
        history.module.__dict__,
        sys.__dict__,
        sys.modules,
    )
    assert not any(
        any(target is namespace for namespace in forbidden)
        for target, _ in transaction.history_state.mutable.containers
    )
    events, runtime, cache = history.events, history.runtime, history.runtime["cache"]
    transaction.begin()
    transaction.finish(commit=False)
    assert history.events is events and events == [{"action_type": "old"}]
    assert history.runtime is runtime and runtime["cache"] is cache and cache == ["old"]
    with runtime["lock"]:
        assert owner.history is history
