"""Owner transactions for complete scientific project replacement.

Remote clients hold an owner-issued transaction until synchronous presentation
and document publication succeed. Rollback always runs at the runtime owner.
"""

from __future__ import annotations

import builtins
import copy
import hashlib
import inspect
import json
import sys
import threading
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from types import ModuleType, SimpleNamespace
from typing import Any
from uuid import uuid4

from .lifecycle import ProjectDocument
from .project import Project
from .session import (
    _CONSTRUCTION_LOCK,
    _curve_record,
    _local_fits,
    _model_state,
    _scientific_value,
    owned_scientific_objects,
    restore_session,
)

_PENDING_TRANSACTIONS: list[Any] = []


class ProjectTransitionError(RuntimeError):
    """A runtime owner could not complete or acknowledge a replacement."""


class ProjectTransitionCancelled(ProjectTransitionError):
    """The actual owner's policy declined destructive replacement."""


def _bound_project_gui(owner: Any) -> Any:
    """Resolve declared presentation ownership and actual shared Main collections."""
    import chisurf as cs

    bound = getattr(owner, "_project_gui", None)
    if bound is not None:
        return bound
    gui = getattr(cs, "cs", None)
    if owner is cs:
        return gui
    datasets = getattr(owner, "datasets", None)
    if gui is not None and owner.fits is cs.fits and datasets is cs.imported_datasets:
        return gui
    return None


def _assert_gui_thread(gui: Any) -> None:
    """Reject RPC workers before accessing any QWidget or QObject affinity API."""
    if gui is not None and hasattr(gui, "thread"):
        if threading.current_thread() is not threading.main_thread():
            raise ProjectTransitionError("Project replacement requires its owning GUI thread")
        from qtpy.QtCore import QThread

        if gui.thread() != QThread.currentThread():
            raise ProjectTransitionError("Project replacement requires its owning GUI thread")


def check_project_owner(
    owner: Any,
    *,
    gui: Any = None,
    client: Any = None,
    project: Project | None = None,
    project_path: str | None = None,
) -> tuple[Any, Any, Any]:
    """Apply the owner's declared policy without minting staging authority.

    GUI policy runs on its owning thread. A remotely presented owner must declare
    a callable ``_project_transition_policy`` at application bootstrap to approve
    requests through its own channel; a public caller cannot install that policy.
    """
    import chisurf as cs

    if getattr(owner, "_project_transition", None) is not None:
        raise ProjectTransitionError("A project replacement is awaiting acknowledgement")
    bound = _bound_project_gui(owner)
    if bound is not None and gui is not None and bound is not gui:
        raise ProjectTransitionError("Authorization belongs to a different GUI owner")
    gui = bound if bound is not None else gui
    if (
        bound is None
        and gui is not None
        and not hasattr(gui, "thread")
        and not hasattr(gui, "_guard_project_transition")
    ):
        # A headless operation may supply an ordinary presentation context.
        # It does not declare GUI ownership or alter the owning-state policy.
        gui = None
    policy = getattr(owner, "_project_transition_policy", None)
    if policy is not None and not callable(policy):
        raise ProjectTransitionError("Invalid project owner authorization policy")
    if gui is not None:
        _assert_gui_thread(gui)
        if callable(getattr(gui, "_project_has_content", None)):
            if client is None:
                datasets = getattr(owner, "datasets", getattr(owner, "imported_datasets", None))
                attached = owner.fits is cs.fits and datasets is cs.imported_datasets
            else:
                attached = (
                    getattr(cs.fits, "_client", None) is client
                    and getattr(cs.imported_datasets, "_client", None) is client
                )
            if not attached:
                raise ProjectTransitionError(
                    "GUI is not attached to this project's scientific owner"
                )
        if owner is not cs or hasattr(gui, "thread"):
            owner._project_gui = gui
        guard = getattr(gui, "_guard_project_transition", None)
        if not callable(guard):
            raise ProjectTransitionError("GUI project owner has no transition guard")
        accepted = guard()
    elif getattr(owner, "_project_gui_required", False):
        if not callable(policy):
            raise ProjectTransitionError(
                "Project replacement requires its owning GUI authorization"
            )
        accepted = policy(project, project_path)
    else:
        # Explicit headless owners retain their declared replacement policy.
        accepted = policy(project, project_path) if callable(policy) else True
    if accepted is not True:
        raise ProjectTransitionCancelled("Project owner declined replacement")
    binding = gui if gui is not None and (owner is not cs or hasattr(gui, "thread")) else bound
    current = _bound_project_gui(owner)
    if current is not binding:
        raise ProjectTransitionError("Project authorization policy changed")
    return gui, guard if gui is not None else policy, binding


def authorize_project_owner(
    owner: Any,
    *,
    gui: Any = None,
    client: Any = None,
    project: Project | None = None,
    project_path: str | None = None,
) -> str:
    """Issue a one-use capability after this actual scientific owner accepts."""
    gui, policy, binding = check_project_owner(
        owner,
        gui=gui,
        client=client,
        project=project,
        project_path=project_path,
    )
    token = str(uuid4())
    grants = getattr(owner, "_project_authorizations", None)
    if grants is None:
        grants = owner._project_authorizations = {}
    scope = _authorization_scope(project, project_path) if project is not None else None
    grants[token] = (gui, policy, scope, _owner_content(owner), binding)
    return token


def _owner_content(owner: Any) -> str:
    """Bind a decision to the science/resources/history that may be discarded."""
    from chisurf.core.data import DataCurve
    from chisurf.core.models.global_model import GlobalFitModel
    from chisurf.core.models.model import Model

    datasets = getattr(owner, "datasets", None)
    if datasets is None:
        datasets = owner.imported_datasets
    objects = _transition_science(owner)
    records, links = {}, []
    contexts = [getattr(owner, "project_resources", None)]
    for uid, obj in objects.items():
        contexts.append(getattr(obj, "_project_resources", None))
        record: dict[str, Any] = {"identity": id(obj)}
        if isinstance(obj, DataCurve):
            record["curve"] = _curve_record(obj)
        elif isinstance(obj, Model):
            parameters = obj.global_parameters_all if isinstance(obj, GlobalFitModel) else None
            record["model"] = _model_state(obj, parameters=parameters)
            for parameter in obj.parameters_all:
                target = getattr(parameter, "link", None)
                links.append((str(parameter.unique_identifier), id(target)))
        else:
            # Parameter/reader/experiment values are captured by these same
            # scientific records. Transient discovery groups are presentation
            # wrappers; their freshly generated identities are not edits.
            continue
        records[uid] = record
    history = getattr(owner, "history", None)
    list_events = getattr(history, "list_events", None)
    events = list_events() if callable(list_events) else []
    payload = {
        "objects": records,
        "datasets": [id(dataset) for dataset in datasets],
        "fits": [
            (
                id(fit),
                getattr(fit, "selected_fit_index", None),
                [
                    (
                        member.fit_range,
                        getattr(member, "mask", None),
                        getattr(member, "noise_model", None),
                    )
                    for member in _local_fits(fit)
                ],
            )
            for fit in owner.fits
        ],
        "links": links,
        "resources": [context.to_transport_dict() for context in contexts if context is not None],
        "events": events,
    }
    payload = _scientific_value(payload)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _authorization_scope(project: Project, project_path: str | None) -> str:
    """Bind authority to complete science, history, resources and target identity."""
    payload = {
        "project": project.to_dict(),
        "resources": project.resources.to_transport_dict(),
        "project_path": project_path,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _consume_authorization(
    owner: Any, token: str, project: Project, project_path: str | None
) -> None:
    """Consume exactly one capability held by this owner and its current policy."""
    grants = getattr(owner, "_project_authorizations", {})
    if not isinstance(token, str) or token not in grants:
        raise ProjectTransitionError("Missing, invalid or cross-owner project authorization")
    gui, policy, scope, source, binding = grants.pop(token)
    import chisurf as cs

    bound = _bound_project_gui(owner)
    if bound is not binding:
        raise ProjectTransitionError("Project authorization policy changed")
    if source != _owner_content(owner):
        raise ProjectTransitionError("Project owner changed after authorization")
    if scope is not None and scope != _authorization_scope(project, project_path):
        raise ProjectTransitionError("Project authorization does not match the approved operation")
    if gui is not None:
        if getattr(gui, "_guard_project_transition", None) != policy:
            raise ProjectTransitionError("Project authorization policy changed")
    elif getattr(owner, "_project_transition_policy", None) != policy:
        raise ProjectTransitionError("Project authorization policy changed")


@dataclass
class PreparedPresentation:
    """Reversible window publication prepared by a synchronous view callback.

    ``commit`` must retain original windows, so ``rollback`` remains valid until
    the runtime owner acknowledges success. Dispose old resources after return.
    """

    commit: Callable[[], None]
    rollback: Callable[[], None]
    finalize: Callable[[], None] | None = None


class _MutableSnapshot:
    """Retain mutable container contents without copying opaque runtime resources."""

    def __init__(self, root: Any):
        self.containers: list[tuple[Any, Any]] = []
        self._seen: set[int] = set()
        self._visit(root)

    def _visit(self, value: Any) -> None:
        """Walk built-in containers, retaining all scientific/resource identities."""
        if id(value) in self._seen:
            return
        self._seen.add(id(value))
        if isinstance(value, dict):
            # Namespaces are shared interpreter resources, never owned session data.
            if (
                value is builtins.__dict__
                or "__builtins__" in value
                or ("__name__" in value and "__spec__" in value)
            ):
                return
            saved = dict(value)
            self.containers.append((value, saved))
            for item in saved.values():
                self._visit(item)
        elif isinstance(value, list):
            saved_list = list(value)
            self.containers.append((value, saved_list))
            for item in saved_list:
                self._visit(item)
        elif isinstance(value, set):
            self.containers.append((value, set(value)))
        elif isinstance(value, tuple):
            for item in value:
                self._visit(item)

    def restore(self) -> None:
        """Restore original containers in place without invoking mutation listeners."""
        for target, saved in reversed(self.containers):
            if isinstance(target, dict):
                dict.clear(target)
                dict.update(target, saved)
            elif isinstance(target, list):
                list.__setitem__(target, slice(None), saved)
            else:
                set.clear(target)
                set.update(target, saved)


class _Attributes:
    """Snapshot a bounded set of owning attributes and their mutable containers."""

    def __init__(self, owner: Any, names: tuple[str, ...]):
        self.owner = owner
        self.values = {name: (hasattr(owner, name), getattr(owner, name, None)) for name in names}
        self.mutable = _MutableSnapshot([value for exists, value in self.values.values() if exists])

    def restore(self) -> None:
        """Reinstate attribute presence, values and original container identities."""
        self.mutable.restore()
        for name, (existed, value) in self.values.items():
            if existed:
                setattr(self.owner, name, value)
            elif hasattr(self.owner, name):
                delattr(self.owner, name)


_HISTORY_ATTRIBUTES = (
    "_events",
    "_checkpoints",
    "_lock",
    "_subscribers",
    "_checkpoint_capture_fn",
    "_checkpoint_interval",
    "_max_checkpoints",
    "_recording_suppressed",
    "_max_events",
    "_auto_compact_threshold",
    "events",
    "runtime",
    "_recording_context",
    "_cursor",
    "_science_states",
    "_baseline",
    "_state_subscribers",
    "_science_capture",
    "_science_publish",
)


def _history_owner(history: Any) -> Any:
    """Resolve the declared facade to bounded, concrete history state.

    OperationHistory owns the underscored attributes above; concrete histories
    may instead own ``events`` and a resource-bearing ``runtime`` cache. Other
    attributes (modules, function globals, registries) are not rollback state.
    """
    if isinstance(history, ModuleType):
        if history is not sys.modules.get("chisurf.history"):
            raise ValueError("Unsupported history module facade")
        from chisurf.history.core import OperationHistory

        history = history.get_history()
        if not isinstance(history, OperationHistory):
            raise ValueError("history facade must own an OperationHistory")
    if history is not None:
        if not callable(getattr(history, "load_events", None)):
            raise ValueError("history object cannot restore events")
        if not any(
            isinstance(getattr(history, name, None), list) for name in ("_events", "events")
        ):
            raise ValueError("history object has no supported owned event state")
    return history


def _selection(ui: dict[str, Any], fits: list[Any]) -> int:
    """Resolve a canonical selection before any live state is mutated."""
    selected_uid = ui.get("current_fit_uid")
    index = ui.get("current_fit_index")
    resolved = -1
    if index is not None:
        if isinstance(index, bool) or not isinstance(index, int) or index < -1:
            raise ValueError("current_fit_index must be None, -1 or a valid fit index")
        if index >= len(fits):
            raise ValueError("current_fit_index does not resolve in restored fits")
        resolved = index
    if selected_uid is not None:
        matches = [
            i for i, fit in enumerate(fits) if str(fit.unique_identifier) == str(selected_uid)
        ]
        if len(matches) != 1:
            raise ValueError("current_fit_uid does not resolve in restored fits")
        if index is not None and resolved != matches[0]:
            raise ValueError("current_fit_uid contradicts current_fit_index")
        resolved = matches[0]
    return resolved


def _transition_science(owner: Any) -> dict[str, Any]:
    """Index the owner plus the codec's declared IRF/background dependency edges.

    Modern TCSPC groups expose those edges through non-UID presentation facades.
    Those facades are not scientific objects, but their declared curves are.
    """
    result = owned_scientific_objects(owner, include_plugins=False)
    dependencies = []
    for fit in owner.fits:
        for member in _local_fits(fit):
            for group, field in (("generic", "background_curve"), ("convolve", "_irf")):
                facade = getattr(member.model, group, None)
                dependency = getattr(facade, field, None) if facade is not None else None
                if dependency is not None:
                    dependencies.append(dependency)
    for uid, obj in owned_scientific_objects(SimpleNamespace(datasets=dependencies)).items():
        if uid in result and result[uid] is not obj:
            raise ProjectTransitionError(f"Duplicate owned scientific UID {uid!r}")
        result[uid] = obj
    return result


def _same_native_port(first: Any, second: Any) -> bool:
    """Compare native shared pointers, whose SWIG proxies have different identities."""
    import IMP.bff as bff

    probe = bff.GraphSession()
    probe.add_port(first)
    probe.add_port(second)
    return probe.get_number_of_ports() == 1


def _same_native_entry(kind: str, first: Any, second: Any) -> bool:
    """Match port registrations or a scientific node's exact owned port topology."""
    if first is None or second is None:
        return first is second
    if kind == "ports":
        return len(first) == len(second) and all(
            _same_native_port(a, b) for a, b in zip(first, second)
        )
    if first is second:
        return True
    if first.get_uid() != second.get_uid():
        return False
    # GraphSession returns fresh shared_ptr proxies. Scientific nodes own
    # nonempty ports; their native pointer identities witness the topology.
    # An empty/unrecognised node never conveys retirement authority.
    a, b = first.get_ports(), second.get_ports()
    return bool(a) and set(a) == set(b) and all(_same_native_port(a[k], b[k]) for k in a)


def _native_state(session: Any) -> dict[str, dict[str, Any]]:
    """Hold exact nodes by registration key and all free ports by native UID."""
    ports: dict[str, list[Any]] = {}
    for port in session.get_ports():
        ports.setdefault(port.get_uid(), []).append(port)
    return {"nodes": dict(session.get_nodes().items()), "ports": ports}


def _native_changes(before: dict, after: dict) -> dict:
    """Record only registrations changed by this publication, retaining predecessors."""
    return {
        kind: {
            key: (before[kind].get(key), after[kind].get(key))
            for key in before[kind].keys() | after[kind].keys()
            if not _same_native_entry(kind, before[kind].get(key), after[kind].get(key))
        }
        for kind in ("nodes", "ports")
    }


def _apply_native_change(state: dict, kind: str, key: str, before: Any, after: Any) -> None:
    """Merge exact port additions/removals or replace a keyed node registration."""
    value = after
    if kind == "ports":
        before, after = before or [], after or []
        removed = [p for p in before if not any(_same_native_port(p, q) for q in after)]
        value = [
            p for p in state[kind].get(key, []) if not any(_same_native_port(p, q) for q in removed)
        ]
        for port in after:
            if not any(_same_native_port(port, p) for p in before) and not any(
                _same_native_port(port, p) for p in value
            ):
                value.append(port)
        value = value or None
    if value is None:
        state[kind].pop(key, None)
    else:
        state[kind][key] = value


def _native_rollback_matches(kind: str, current: Any, installed: Any) -> bool:
    """Allow inverse port deltas when our native objects remain among peer additions."""
    if kind == "ports" and current is not None and installed is not None:
        return any(_same_native_port(p, q) for p in current for q in installed)
    return _same_native_entry(kind, current, installed)


def _write_native_state(session: Any, state: dict) -> None:
    """Reconcile a session in place, preserving its identity and exact native objects."""
    session.clear()
    for key, node in state["nodes"].items():
        session.add_node(key, node)
    for ports in state["ports"].values():
        for port in ports:
            session.add_port(port)


class OwnerTransaction:
    """Hold an owner's original state until a replacement is acknowledged."""

    def __init__(
        self,
        owner: Any,
        project: Project,
        *,
        project_path: str | None = None,
        authorization: str | None = None,
    ):
        if getattr(owner, "_project_transition", None) is not None:
            raise ProjectTransitionError("A project replacement is awaiting acknowledgement")
        self.owner = owner
        self.authorization = authorization
        self.project = project
        self.authorization_path = project_path
        self.transaction_id = str(uuid4())
        self.restored = restore_session(project)
        self.selected_index = _selection(self.restored.ui_state, self.restored.fits)
        self.dataset_attr = "datasets" if hasattr(owner, "datasets") else "imported_datasets"
        if not isinstance(getattr(owner, self.dataset_attr), list) or not isinstance(
            owner.fits, list
        ):
            raise TypeError("Project transaction requires authoritative runtime collections")
        self.history = _history_owner(getattr(owner, "history", None))
        self.created_history = self.history is None and "history_state" in project.extra
        if self.created_history:
            from chisurf.history.core import OperationHistory

            self.history = OperationHistory()
        from .history import validate_history_state

        self.staged_history = validate_history_state(project, history=self.history)
        events = (project.extra or {}).get("history_events", [])
        if not isinstance(events, list):
            raise ValueError("history_events must be a list")
        self.events = copy.deepcopy(events)
        metadata = (project.metadata or {}).get("server_session", {})
        if not isinstance(metadata, dict) or not isinstance(
            metadata.get("project_metadata", {}), dict
        ):
            raise ValueError("server_session metadata must be a mapping")
        self.metadata = copy.deepcopy(metadata.get("project_metadata", {}))
        self.project_path = (
            project_path if project_path is not None else metadata.get("project_path")
        )
        self.attributes = _Attributes(
            owner,
            (
                self.dataset_attr,
                "fits",
                "experiments",
                "current_fit",
                "current_fit_idx",
                "current_fit_uid",
                "current_experiment",
                "current_setup",
                "current_experiment_name",
                "current_setup_name",
                "project_metadata",
                "project_path",
                "project_name",
                "native_session",
                "history",
                "project_resources",
            ),
        )
        import chisurf as cs

        self.runtime = (
            cs
            if owner is not cs
            and owner.fits is cs.fits
            and getattr(owner, self.dataset_attr) is cs.imported_datasets
            else None
        )
        self.runtime_state = (
            _Attributes(
                self.runtime,
                (
                    "project_resources",
                    "native_session",
                    "current_fit",
                    "current_fit_idx",
                    "current_fit_uid",
                ),
            )
            if self.runtime is not None
            else None
        )
        self.history_state = (
            _Attributes(self.history, _HISTORY_ATTRIBUTES) if self.history is not None else None
        )
        self.active = False
        self.uid_previous: dict[str, Any] = {}
        self.uid_installed: dict[str, Any] = {}
        self.native_previous: Any = None
        self.native_installed: Any = None
        self.registry = getattr(owner, "registry", None)
        self.registry_state = (
            _Attributes(self.registry, ("_datasets", "_fits", "_parameters"))
            if self.registry is not None
            else None
        )

    def _publish_identities(self) -> None:
        """Publish owned UID mappings and native science without clearing peers."""
        import IMP.bff as bff

        from chisurf.core.base import Base

        old = _transition_science(self.owner)
        new = _transition_science(self.restored)
        self.old_science = old
        if self.registry is not None:
            with self.registry._lock:
                for field in ("_datasets", "_fits", "_parameters"):
                    index = getattr(self.registry, field)
                    for uid in list(index):
                        if uid in old and index[uid] is old[uid]:
                            del index[uid]
                for uid in self.project.datasets:
                    self.registry._datasets[uid] = new[uid]
                for layout in self.project.ui_state.get("dataset_layout", []):
                    if layout["kind"] == "group":
                        self.registry._datasets[layout["uid"]] = new[layout["uid"]]
                for record in self.project.fits:
                    self.registry._fits[record["uid"]] = new[record["uid"]]
                    for member in record["members"]:
                        self.registry._fits[member["uid"]] = new[member["uid"]]
                    models = [m["model"] for m in record["members"]]
                    if record.get("aggregate_model"):
                        models.append(record["aggregate_model"])
                    for model in models:
                        for parameter in model["parameters"]:
                            self.registry._parameters[parameter["uid"]] = new[parameter["uid"]]
        for uid in old.keys() | new.keys():
            previous = Base._uuid_index.get(uid)
            self.uid_previous[uid] = previous
            if uid in new:
                Base._uuid_index[uid] = new[uid]
                self.uid_installed[uid] = new[uid]
            elif previous is old[uid]:
                del Base._uuid_index[uid]
                self.uid_installed[uid] = None
        self.native_previous = bff.get_session()
        self.native_before = _native_state(self.native_previous)
        native = bff.GraphSession()
        retired_ports = []
        retired_nodes = []
        for uid, obj in old.items():
            if self.uid_previous.get(uid) is not obj:
                continue
            port = getattr(obj, "_port", None)
            if port is not None:
                retired_ports.append(port)
            declared_nodes = getattr(obj, "get_session_native_nodes", None)
            if callable(declared_nodes):
                for node in declared_nodes():
                    retired_nodes.append(node)
                    retired_ports.extend(node.get_ports().values())
        for key, node in self.native_before["nodes"].items():
            if not any(_same_native_entry("nodes", node, old_node) for old_node in retired_nodes):
                native.add_node(key, node)
        incoming = _native_state(self.restored.native_session)
        for port in self.native_previous.get_ports():
            if port.get_uid() not in incoming["ports"] and not any(
                _same_native_port(port, old_port) for old_port in retired_ports
            ):
                native.add_port(port)
        for key, node in incoming["nodes"].items():
            native.add_node(key, node)
        for port in self.restored.native_session.get_ports():
            native.add_port(port)
        self.native_after = _native_state(native)
        self.native_changes = _native_changes(self.native_before, self.native_after)
        self.native_installed = native
        bff._session = native

    def _rollback_identities(self) -> None:
        """Undo our publications by identity, preserving concurrent peer writes."""
        import IMP.bff as bff

        from chisurf.core.base import Base

        restored_native_uids = set()
        for uid, installed in self.uid_installed.items():
            if Base._uuid_index.get(uid) is installed:
                previous = self.uid_previous[uid]
                for obj in (installed, previous):
                    port = getattr(obj, "_port", None)
                    if port is not None:
                        restored_native_uids.add(port.get_uid())
                    declared_nodes = getattr(obj, "get_session_native_nodes", None)
                    if callable(declared_nodes):
                        for node in declared_nodes():
                            restored_native_uids.update(
                                p.get_uid() for p in node.get_ports().values()
                            )
                if previous is None:
                    Base._uuid_index.pop(uid, None)
                else:
                    Base._uuid_index[uid] = previous
        if self.native_installed is None:
            return  # Publication failed before replacing the native graph.
        for peer in _PENDING_TRANSACTIONS:
            if peer is self or peer.native_previous is not self.native_installed:
                continue
            # This peer inherited registrations made after our publication.
            # Transfer that predecessor delta before removing our graph layer;
            # otherwise its later rollback would lose those peer objects.
            previous_state = _native_state(self.native_previous)
            for kind, changes in _native_changes(self.native_after, peer.native_before).items():
                for key, (before, value) in changes.items():
                    _apply_native_change(previous_state, kind, key, before, value)
            _write_native_state(self.native_previous, previous_state)
            peer.native_previous = self.native_previous
        current = bff.get_session()
        state = _native_state(current)
        if current is self.native_installed:
            # Carry registrations made during tentative presentation, including
            # replacements under existing keys/UIDs, into the original graph.
            previous_state = _native_state(self.native_previous)
            for kind, changes in _native_changes(self.native_after, state).items():
                for key, (before, value) in changes.items():
                    _apply_native_change(previous_state, kind, key, before, value)
            _write_native_state(self.native_previous, previous_state)
            bff._session = self.native_previous
        else:
            # A later owner controls the current graph. Undo only entries that
            # still contain our exact native objects, without replacing its graph.
            for kind, changes in self.native_changes.items():
                for key, (previous, installed) in changes.items():
                    if (
                        _native_rollback_matches(kind, state[kind].get(key), installed)
                        or kind == "ports"
                        and key in restored_native_uids
                    ):
                        _apply_native_change(state, kind, key, installed, previous)
            _write_native_state(current, state)
        # Pending peers must not resurrect this discarded layer on rollback or
        # mistake its reconciliation for a new presentation registration.
        for peer in _PENDING_TRANSACTIONS:
            if peer is self or peer.native_installed is None:
                continue
            for kind, changes in self.native_changes.items():
                for key, (previous, installed) in changes.items():
                    for snapshot in (peer.native_before, peer.native_after):
                        if _native_rollback_matches(kind, snapshot[kind].get(key), installed):
                            _apply_native_change(snapshot, kind, key, installed, previous)
            peer.native_changes = _native_changes(peer.native_before, peer.native_after)

    def begin(self) -> dict[str, Any]:
        """Install staged science while retaining the complete old owner state."""
        with _CONSTRUCTION_LOCK:
            token = self.authorization
            if token is None:
                token = authorize_project_owner(
                    self.owner, project=self.project, project_path=self.authorization_path
                )
            _consume_authorization(self.owner, token, self.project, self.authorization_path)
            self.authorization = token
            return self._begin()

    def _begin(self) -> dict[str, Any]:
        """Publish one complete owner and its indexes under the construction lock."""
        owner = self.owner
        if getattr(owner, "_project_transition", None) is not None:
            raise ProjectTransitionError("A project replacement is awaiting acknowledgement")
        owner._project_transition = self
        getattr(owner, "_project_authorizations", {}).clear()
        self.active = True
        _PENDING_TRANSACTIONS.append(self)
        try:
            self._publish_identities()
            getattr(owner, self.dataset_attr)[:] = self.restored.datasets
            owner.fits[:] = self.restored.fits
            if hasattr(owner, "experiments"):
                owner.experiments.clear()
                owner.experiments.update(self.restored.experiments)
            selected = self.restored.fits[self.selected_index] if self.selected_index >= 0 else None
            owner.current_fit = selected
            owner.current_fit_idx = self.selected_index
            owner.current_fit_uid = (
                str(selected.unique_identifier) if selected is not None else None
            )
            if self.dataset_attr == "datasets":
                owner.current_experiment = self.restored.ui_state.get("current_experiment_name")
                owner.current_setup = self.restored.ui_state.get("current_setup_name")
                owner.current_experiment_name = owner.current_experiment
                owner.current_setup_name = owner.current_setup
            owner.project_metadata = self.metadata
            owner.project_path = self.project_path
            owner.project_name = self.project.name
            owner.native_session = self.restored.native_session
            owner.project_resources = self.restored.resources
            if self.runtime is not None:
                for field in (
                    "project_resources",
                    "native_session",
                    "current_fit",
                    "current_fit_idx",
                    "current_fit_uid",
                ):
                    setattr(self.runtime, field, getattr(owner, field))
            if self.history is not None:
                if self.created_history:
                    owner.history = self.history
                if self.staged_history is not None:
                    # Validation and detached science reconstruction have already
                    # finished. Install owned data without copying runtime locks
                    # or notifying views about an unacknowledged replacement.
                    with self.history._lock:
                        self.history._restore_owned_state(self.staged_history)
                else:
                    from chisurf.history.core import OperationHistory

                    with (
                        self.history._suppress_notifications()
                        if isinstance(self.history, OperationHistory)
                        else nullcontext()
                    ):
                        self.history.load_events(self.events, replace=True)
        except Exception:
            self.finish(commit=False)
            raise
        self.result = {
            "ok": True,
            "transaction_id": self.transaction_id,
            "project_name": self.project.name,
            "fit_uids": [str(fit.unique_identifier) for fit in self.restored.fits],
            "dataset_count": len(self.restored.datasets),
            "fit_count": len(self.restored.fits),
        }
        return self.result

    def finish(self, *, commit: bool) -> None:
        """Accept the replacement or reinstate the original authoritative state."""
        with _CONSTRUCTION_LOCK:
            self._finish(commit=commit)

    def _finish(self, *, commit: bool) -> None:
        """Acknowledge or reconcile an owner without interleaved registry writes."""
        if not self.active or getattr(self.owner, "_project_transition", None) is not self:
            raise ProjectTransitionError("Project transaction is no longer active")
        if not commit:
            # A later session may have saved our staged mapping as its rollback
            # predecessor. Remove this reverted layer from those snapshots too.
            for peer in _PENDING_TRANSACTIONS:
                if peer is self:
                    continue
                for uid, installed in self.uid_installed.items():
                    if uid in peer.uid_previous and peer.uid_previous[uid] is installed:
                        peer.uid_previous[uid] = self.uid_previous[uid]
            self._rollback_identities()
            if self.registry_state is not None:
                self.registry_state.restore()
            self.attributes.restore()
            if self.runtime_state is not None:
                self.runtime_state.restore()
            if self.history_state is not None:
                self.history_state.restore()
        self.owner._project_transition = None
        self.active = False
        _PENDING_TRANSACTIONS[:] = [peer for peer in _PENDING_TRANSACTIONS if peer is not self]
        outcomes = getattr(self.owner, "_project_transition_outcomes", None)
        if outcomes is None:
            outcomes = self.owner._project_transition_outcomes = {}
        outcomes[self.authorization] = {
            "ok": True,
            "phase": "committed" if commit else "rolled_back",
            "result": getattr(self, "result", None),
        }
        while len(outcomes) > 100:
            del outcomes[next(iter(outcomes))]
        if commit and self.history is not None:
            from chisurf.history.core import OperationHistory

            if isinstance(self.history, OperationHistory):
                self.history._notify_state()


def _rpc_result(result: Any) -> dict[str, Any]:
    """Reject unsuccessful RPC responses before they can publish client identity."""
    if not isinstance(result, dict) or result.get("ok") is not True:
        message = (
            result.get("error", "Invalid project transition response")
            if isinstance(result, dict)
            else "Invalid project transition response"
        )
        raise ProjectTransitionError(str(message))
    return result


def replace_project(
    project: Project,
    *,
    gui: Any = None,
    document: ProjectDocument | None = None,
    target_identity: ProjectDocument | None = None,
    present: Callable[[list[str], dict[str, Any]], Any] | None = None,
    confirmed: bool = False,
    owner: Any = None,
    client: Any = None,
    project_path: str | None = None,
    authorization: str | None = None,
) -> dict[str, Any]:
    """Replace a canonical project through its runtime owner and synchronous view.

    Parameters
    ----------
    project : Project
        Canonical scientific snapshot, reconstructed before any live mutation.
    gui : object, optional
        Guard, selection and document context. The callback owns window staging.
    document : ProjectDocument, optional
        Live document; defaults to the GUI's document when available.
    target_identity : ProjectDocument, optional
        Validated, staged identity to publish after successful presentation.
    present : callable, optional
        Synchronous callback receiving normalized fit UIDs and canonical UI state.
    confirmed : bool, optional
        Compatibility argument with no authorization effect.
    owner : object, optional
        Explicit authoritative SessionState; defaults to the process runtime.
    client : object, optional
        RPC client for an authoritative remote owner; inferred for installed proxies.

    project_path : str, optional
        File identity to publish at a headless owner; staged document path takes precedence.
    authorization : str, optional
        One-use operation capability previously issued by the actual owner.

    Returns
    -------
    dict
        Normalized UID/count result, or ``ok=False, cancelled=True`` on cancellation.
    """
    import chisurf as cs

    del confirmed  # Compatibility input carries no destructive authority.
    _assert_gui_thread(gui)
    if not isinstance(project, Project):
        raise TypeError("Project replacement requires a canonical Project")
    if document is None and gui is not None:
        document = getattr(gui, "_get_project_document", lambda: None)()
    if target_identity is not None and document is None:
        raise ValueError("A target identity requires a live ProjectDocument")
    if target_identity is not None and not isinstance(target_identity, ProjectDocument):
        raise TypeError("target_identity must be a staged ProjectDocument")
    if owner is None and client is None:
        from chisurf.core.api._proxies import ProxyDatasetList, ProxyFitList

        if isinstance(cs.imported_datasets, ProxyDatasetList) and isinstance(cs.fits, ProxyFitList):
            client = getattr(cs, "__client__", None)
            if client is None:
                raise ProjectTransitionError("Installed proxies have no authoritative client")
        else:
            owner = cs
    path = (
        str(target_identity.path)
        if target_identity is not None and target_identity.path is not None
        else project_path
    )
    if authorization is None:
        try:
            if client is None:
                authorization = authorize_project_owner(
                    owner, gui=gui, project=project, project_path=path
                )
            else:
                from chisurf.core.plugin.client import InProcessClient

                if isinstance(client, InProcessClient):
                    authority = client._dispatcher._state
                    authorization = authorize_project_owner(
                        authority,
                        gui=gui,
                        client=client,
                        project=project,
                        project_path=path,
                    )
                else:
                    if gui is not None:
                        # Local presentation authorization does not establish
                        # remote owner authority; its policy must also accept.
                        check_project_owner(cs, gui=gui, client=client)
                    reply = client.call(
                        "project.transition.authorize",
                        {
                            "project": project.to_dict(),
                            "resources": project.resources.to_transport_dict(),
                            "project_path": path,
                        },
                    )
                    if reply.get("cancelled") is True:
                        return {"ok": False, "cancelled": True}
                    authorization = _rpc_result(reply)["authorization"]
        except ProjectTransitionCancelled:
            return {"ok": False, "cancelled": True}
    gui_state = (
        _Attributes(
            gui,
            (
                "_current_project_path",
                "_current_project_id",
                "_current_project_version_id",
                "_current_project_name",
                "current_fit",
                "_fit_idx",
                "_current_dataset",
            ),
        )
        if gui is not None
        else None
    )
    document_state = _MutableSnapshot(document.__dict__) if document is not None else None
    prepared = None
    transaction = None
    token = None
    try:
        if client is not None:
            result = _rpc_result(
                client.call(
                    "project.transition.begin",
                    {
                        "project": project.to_dict(),
                        "project_path": path,
                        "resources": project.resources.to_transport_dict(),
                        "authorization": authorization,
                    },
                )
            )
            token = result.get("transaction_id")
            if not isinstance(token, str) or not token:
                raise ProjectTransitionError("Owner did not return a transaction_id")
        else:
            transaction = OwnerTransaction(
                owner, project, project_path=path, authorization=authorization
            )
            result = transaction.begin()
        fit_uids = result.get("fit_uids")
        if not isinstance(fit_uids, list) or not all(isinstance(uid, str) for uid in fit_uids):
            raise ProjectTransitionError("Owner did not return normalized fit_uids")
        if present is not None:
            presented = present(fit_uids, project.ui_state)
            if isinstance(presented, PreparedPresentation):
                prepared = presented
            if inspect.isawaitable(presented):
                if inspect.iscoroutine(presented):
                    presented.close()
                raise ProjectTransitionError("Project presentation must complete synchronously")
            if presented is False:
                raise ProjectTransitionError("Project presentation was rejected")
        if target_identity is not None:
            assert document is not None
            document.adopt(target_identity)
            if gui is not None:
                gui._current_project_path = document.path
                gui._current_project_id = document.project_id
                gui._current_project_version_id = document.version_id
                gui._current_project_name = document.name
        if prepared is not None:
            prepared.commit()
        if client is not None:
            try:
                _rpc_result(
                    client.call(
                        "project.transition.finish", {"transaction_id": token, "commit": True}
                    )
                )
            except Exception:
                status = _rpc_result(
                    client.call("project.transition.status", {"authorization": authorization})
                )
                if status.get("phase") != "committed":
                    raise
        else:
            assert transaction is not None
            transaction.finish(commit=True)
    except Exception:
        try:
            if client is not None and token is not None:
                _rpc_result(
                    client.call(
                        "project.transition.finish", {"transaction_id": token, "commit": False}
                    )
                )
            elif client is not None and authorization is not None:
                _rpc_result(
                    client.call("project.transition.abort", {"authorization": authorization})
                )
            elif transaction is not None and transaction.active:
                transaction.finish(commit=False)
        finally:
            try:
                # Restoring windows may synchronously emit Qt activation signals.
                # Their handlers must see the original owner/document selection.
                if document_state is not None:
                    document_state.restore()
                if gui_state is not None:
                    gui_state.restore()
                if prepared is not None:
                    prepared.rollback()
            finally:
                if document_state is not None:
                    document_state.restore()
                if gui_state is not None:
                    gui_state.restore()
        raise
    finally:
        if client is None and isinstance(authorization, str):
            getattr(owner, "_project_authorizations", {}).pop(authorization, None)
    if prepared is not None and prepared.finalize is not None:
        prepared.finalize()
    return {key: value for key, value in result.items() if key != "transaction_id"}
