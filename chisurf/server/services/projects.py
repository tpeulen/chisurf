from __future__ import annotations

import copy
import pathlib
from collections.abc import Callable
from typing import Any

from chisurf.core.project import Project, capture_session
from chisurf.core.project.project import ResourceContext
from chisurf.core.project.pto import PROJECT_SUFFIX
from chisurf.core.project.storage import load_file, save_file
from chisurf.core.project.transition import (
    OwnerTransaction,
    ProjectTransitionCancelled,
    authorize_project_owner,
    check_project_owner,
    replace_project,
)
from chisurf.server.services import (
    NOT_FOUND,
    OPERATION_FAILED,
    ServiceResult,
    service_error,
)
from chisurf.server.session import SessionState


def get_project_info(state: SessionState) -> ServiceResult:
    """Return a summary of the current session as project info.

    Parameters
    ----------
    state : SessionState
        Server-side session state.

    """
    return {
        "ok": True,
        "project_path": getattr(state, "project_path", None),
        "fit_count": len(state.fits),
        "dataset_count": len(state.datasets),
    }


def save_project(
    state: SessionState,
    target_path: str,
    project_name: str | None = None,
) -> ServiceResult:
    """Save the current session as a ``.cs.pto`` project.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    target_path : str
        Destination ``.cs.pto`` path, or a directory for ``project.cs.pto``.
    project_name : str, optional
        Project display name (defaults to destination stem).

    """
    try:
        project_path, name = _project_archive_path(target_path, project_name)
        project = _capture_project(state, name=name)
        save_file(project, project_path)
        return {"ok": True, "path": str(project_path)}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def load_project(
    state: SessionState,
    project_path: str,
) -> ServiceResult:
    """Load a ``.cs.pto`` project from disk and return metadata.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    project_path : str
        Path to the project archive.

    """
    try:
        archive_path = _project_archive_input_path(project_path)
        if not archive_path.is_file():
            return service_error(
                f"project archive not found at {archive_path}", error_code=NOT_FOUND
            )
        return _public_transition(state, lambda: (load_file(archive_path), str(archive_path)))
    except FileNotFoundError:
        return service_error(f"project archive not found at {project_path}", error_code=NOT_FOUND)
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def capture_project_payload(state: SessionState, ui_state: dict | None = None) -> ServiceResult:
    """Capture server-owned science together with detached client presentation."""
    try:
        project = _capture_project(state, ui_state=ui_state)
        return {
            "ok": True,
            "project": project.to_dict(),
            "resources": project.resources.to_transport_dict(),
        }
    except Exception as exc:
        return service_error(str(exc), error_code=OPERATION_FAILED, exception=exc)


def restore_project_payload(
    state: SessionState,
    project: Project | dict[str, Any],
    resources: dict | None = None,
) -> ServiceResult:
    """Restore a canonical project DTO into the server as one transaction."""
    try:
        return _public_transition(
            state,
            lambda: (_project_from_payload(project, resources), None),
        )
    except Exception as exc:
        return service_error(str(exc), error_code=OPERATION_FAILED, exception=exc)


def register_project_snapshot_services(dispatcher: Any, state: SessionState) -> None:
    """Register project DTO RPCs that are intentionally unavailable as file aliases."""
    dispatcher.register(
        "project.capture",
        lambda params: capture_project_payload(state, ui_state=params.get("ui_state")),
    )
    dispatcher.register("project.read", lambda params: read_project_payload(params["project_path"]))
    dispatcher.register(
        "project.presentation.attach", lambda _params: attach_project_presentation(state)
    )
    dispatcher.register(
        "project.transition.authorize",
        lambda params: authorize_project_transition(state, **params),
    )
    dispatcher.register(
        "project.restore_payload",
        lambda params: restore_project_payload(
            state,
            project=params["project"],
            resources=params.get("resources"),
        ),
    )

    dispatcher.register(
        "project.transition.begin",
        lambda params: begin_project_transition(state, **params),
    )
    dispatcher.register(
        "project.transition.finish",
        lambda params: finish_project_transition(state, **params),
    )
    dispatcher.register(
        "project.transition.abort",
        lambda params: abort_project_transition(state, **params),
    )
    dispatcher.register(
        "project.transition.status",
        lambda params: project_transition_status(state, **params),
    )


def _capture_project(
    state: SessionState,
    *,
    name: str | None = None,
    ui_state: dict | None = None,
) -> Project:
    # Presentation is client-owned; scientific selection remains owner-authoritative.
    # When the owner has a selection, the index is derived from it: a client
    # without a GUI sends its local "nothing selected" index, which beside the
    # owner's UID makes a project that restore rejects as contradictory. Without
    # an owner selection, the view's own index stands.
    view_state = copy.deepcopy(ui_state) if ui_state is not None else {}
    uids = [str(fit.unique_identifier) for fit in state.fits]
    if state.current_fit_uid is not None and str(state.current_fit_uid) in uids:
        view_state["current_fit_index"] = uids.index(str(state.current_fit_uid))
    view_state.update(
        {
            "current_fit_uid": state.current_fit_uid,
            "current_experiment_name": state.current_experiment,
            "current_setup_name": state.current_setup,
        }
    )
    project = capture_session(
        state.datasets,
        state.fits,
        experiments=state.experiments,
        ui_state=view_state,
        name=name or str(getattr(state, "project_name", "chisurf_project")),
        resources=getattr(state, "project_resources", None),
    )
    from chisurf.core.project.history import capture_history

    project.extra.update(capture_history(getattr(state, "history", None)))
    project.metadata["server_session"] = {
        "project_metadata": copy.deepcopy(getattr(state, "project_metadata", {})),
        "project_path": getattr(state, "project_path", None),
    }
    return project


def begin_project_transition(
    state: SessionState,
    project: dict[str, Any],
    project_path: str | None = None,
    resources: dict | None = None,
    authorization: str | None = None,
) -> ServiceResult:
    """Install detached science while holding the owner's rollback state for acknowledgement."""
    try:
        transaction = OwnerTransaction(
            state,
            _project_from_payload(project, resources),
            project_path=project_path,
            authorization=authorization,
        )
        return transaction.begin()
    except ProjectTransitionCancelled:
        return {"ok": False, "cancelled": True}
    except Exception as exc:
        return service_error(str(exc), error_code=OPERATION_FAILED, exception=exc)
    finally:
        if isinstance(authorization, str):
            getattr(state, "_project_authorizations", {}).pop(authorization, None)


def authorize_project_transition(
    state: SessionState,
    project: dict,
    resources: dict | None = None,
    project_path: str | None = None,
) -> ServiceResult:
    """Acquire authority from the registered owner, never from caller fields."""
    try:
        decoded = _project_from_payload(project, resources)
        return {
            "ok": True,
            "authorization": authorize_project_owner(
                state,
                project=decoded,
                project_path=project_path,
            ),
        }
    except ProjectTransitionCancelled:
        # A completed policy query may decline authority. Keeping the query
        # successful preserves this explicit decision through JSON-RPC, whose
        # generic error envelope otherwise drops the cancellation indicator.
        return {"ok": True, "cancelled": True}
    except Exception as exc:
        return service_error(str(exc), error_code=OPERATION_FAILED, exception=exc)


def finish_project_transition(
    state: SessionState,
    transaction_id: str,
    commit: bool,
) -> ServiceResult:
    """Commit or roll back the exact outstanding owner-issued transaction."""
    try:
        transaction = getattr(state, "_project_transition", None)
        if transaction is None or transaction.transaction_id != transaction_id:
            raise ValueError("Unknown project transaction_id")
        if not isinstance(commit, bool):
            raise ValueError("commit must be a boolean acknowledgement")
        transaction.finish(commit=commit)
        return {"ok": True}
    except Exception as exc:
        return service_error(str(exc), error_code=OPERATION_FAILED, exception=exc)


def read_project_payload(project_path: str) -> ServiceResult:
    """Read detached science for a GUI transaction without replacing the owner."""
    try:
        archive_path = _project_archive_input_path(project_path)
        project = load_file(archive_path)
        return {
            "ok": True,
            "project": project.to_dict(),
            "path": str(archive_path),
            "resources": project.resources.to_transport_dict(),
        }
    except Exception as exc:
        return service_error(str(exc), error_code=OPERATION_FAILED, exception=exc)


def abort_project_transition(state: SessionState, authorization: str) -> ServiceResult:
    """Revoke a capability or roll back its stage when the begin reply was lost."""
    try:
        if not isinstance(authorization, str) or not authorization:
            raise ValueError("Invalid project authorization")
        transaction = getattr(state, "_project_transition", None)
        if transaction is not None and transaction.authorization == authorization:
            transaction.finish(commit=False)
        getattr(state, "_project_authorizations", {}).pop(authorization, None)
        return {"ok": True}
    except Exception as exc:
        return service_error(str(exc), error_code=OPERATION_FAILED, exception=exc)


def project_transition_status(state: SessionState, authorization: str) -> ServiceResult:
    """Report an actual owner outcome without letting caller fields assert success."""
    if not isinstance(authorization, str) or not authorization:
        return service_error("Invalid project authorization", error_code=OPERATION_FAILED)
    transaction = getattr(state, "_project_transition", None)
    if transaction is not None and transaction.authorization == authorization:
        return {"ok": True, "phase": "pending", "result": transaction.result}
    outcome = getattr(state, "_project_transition_outcomes", {}).get(authorization)
    if outcome is None:
        return service_error("Unknown project authorization outcome", error_code=NOT_FOUND)
    return copy.deepcopy(outcome)


def _project_from_payload(project: Project | dict, resources: dict | None) -> Project:
    """Decode one canonical scientific snapshot and its bounded owned byte context."""
    if not isinstance(project, Project):
        project = Project.from_dict(project)
    if resources is not None:
        project.resources = ResourceContext.from_transport_dict(resources)
    return project


def reset_project(state: SessionState) -> ServiceResult:
    """Replace with canonical empty science through the public lifecycle boundary."""
    try:
        return _public_transition(
            state, lambda: (capture_session([], [], name="untitled"), None), reset=True
        )
    except Exception as exc:
        return service_error(str(exc), error_code=OPERATION_FAILED, exception=exc)


def attach_project_presentation(state: SessionState) -> ServiceResult:
    """Declare GUI ownership so public headless RPC cannot infer GUI consent.

    This only restricts public replacement. It does not authorize a transition
    or grant backend authentication. Staging still requires owner-issued authority.
    """
    state._project_gui_required = True
    getattr(state, "_project_authorizations", {}).clear()
    return {"ok": True}


def _public_transition(
    state: Any,
    load: Callable[[], tuple[Project, str | None]],
    *,
    reset: bool = False,
    client: Any = None,
) -> ServiceResult:
    """Authorize and synchronously publish a public replacement at its actual owner.

    A headless owner applies its headless replacement policy. GUI ownership never
    supplies implicit consent: its guard must explicitly accept on the GUI thread.
    The remote begin/finish calls are used only after that local authorization.
    """
    import chisurf as cs
    from chisurf.core.project.lifecycle import ProjectDocument

    gui = getattr(state, "_project_gui", None) or getattr(cs, "cs", None)
    if gui is None and getattr(state, "_project_gui_required", False):
        raise RuntimeError(
            "Project replacement requires its owning GUI authorization and presentation"
        )
    from chisurf.core.plugin.client import InProcessClient

    remote = client is not None and not isinstance(client, InProcessClient)
    authority = client._dispatcher._state if isinstance(client, InProcessClient) else state
    loaded = load() if gui is None else None
    try:
        authorization = None
        if remote:
            check_project_owner(authority, gui=gui, client=client)
        else:
            authorization = authorize_project_owner(
                authority,
                gui=gui,
                client=client,
                project=loaded[0] if loaded is not None else None,
                project_path=loaded[1] if loaded is not None else None,
            )
    except ProjectTransitionCancelled:
        return {"ok": False, "cancelled": True}
    issued = authorization
    try:
        if gui is not None and state is not cs:
            state._project_gui = gui
        project, project_path = load() if loaded is None else loaded
        if remote:
            from chisurf.core.project.transition import _rpc_result

            # Local presentation consent cannot mint a remote owner's grant.
            reply = client.call(
                "project.transition.authorize",
                {
                    "project": project.to_dict(),
                    "resources": project.resources.to_transport_dict(),
                    "project_path": project_path,
                },
            )
            if reply.get("cancelled") is True:
                return {"ok": False, "cancelled": True}
            authorization = _rpc_result(reply)["authorization"]
        document = getattr(gui, "_get_project_document", lambda: None)()
        staged = None
        if document is not None:
            staged = (
                ProjectDocument()
                if reset
                else document.stage_file_save(project, project_path)
                if project_path is not None
                else ProjectDocument(name=project.name)
            )
        present = None
        if gui is not None:
            from chisurf.macros import core_fit

            def present(uids, ui):
                """Present this owner rather than process-global unrelated science."""
                if state is cs:
                    return core_fit.restore_gui_from_fits(uids, ui)
                fits = state.fits
                if client is not None:
                    from chisurf.core.api._proxies import ProxyFitList

                    fits = ProxyFitList(client)
                return core_fit.restore_gui_from_fits(uids, ui, main_window=gui, fits=fits)

        return replace_project(
            project,
            gui=gui,
            document=document,
            target_identity=staged,
            present=present,
            authorization=authorization,
            owner=state if client is None else None,
            client=client,
            project_path=project_path,
        )

    finally:
        if not remote and isinstance(issued, str):
            getattr(authority, "_project_authorizations", {}).pop(issued, None)


def _project_archive_path(target_path: str, project_name: str | None) -> tuple[pathlib.Path, str]:
    path = pathlib.Path(target_path)
    if str(path).lower().endswith(PROJECT_SUFFIX):
        return path, path.stem or (project_name or "chisurf_project")
    name = project_name or path.name or "chisurf_project"
    return path / f"{name}{PROJECT_SUFFIX}", name


def _project_archive_input_path(project_path: str) -> pathlib.Path:
    path = pathlib.Path(project_path)
    if str(path).lower().endswith(PROJECT_SUFFIX):
        return path
    if path.is_dir():
        return path / f"project{PROJECT_SUFFIX}"
    return pathlib.Path(f"{path}{PROJECT_SUFFIX}")
