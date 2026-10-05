from __future__ import annotations

from typing import Any

from chisurf.server.services import ServiceResult
from chisurf.server.services._stats import _safe_chi2
from chisurf.server.session import SessionState


def session_describe(state: SessionState) -> ServiceResult:
    """Return a full session overview."""
    return {
        "ok": True,
        "datasets": [
            {
                "index": idx,
                "uid": str(getattr(d, "unique_identifier", "") or ""),
                "name": str(getattr(d, "name", "") or ""),
                "type": type(d).__name__,
            }
            for idx, d in enumerate(state.datasets)
        ],
        "fits": [
            {
                "index": idx,
                "uid": str(getattr(f, "unique_identifier", "") or ""),
                "name": str(getattr(f, "name", "") or ""),
                "type": type(f).__name__,
                "chi2": _safe_chi2(f),
                "dataset_name": str(getattr(getattr(f, "data", None), "name", "") or ""),
            }
            for idx, f in enumerate(state.fits)
        ],
        "dataset_count": len(state.datasets),
        "fit_count": len(state.fits),
        "current_experiment": state.current_experiment,
        "current_setup": state.current_setup,
        "current_fit_uid": state.current_fit_uid,
        "experiment_names": sorted(state.experiments.keys()),
    }


def session_clear(state: SessionState, event_bus: Any = None) -> ServiceResult:
    """Reset science through the same lifecycle gate as public project restore."""
    from chisurf.server.services.projects import reset_project

    del event_bus
    return reset_project(state)


def session_snapshot(state: SessionState) -> ServiceResult:
    """Return a lightweight snapshot suitable for GUI persistence."""
    return {
        "ok": True,
        "snapshot": state.to_dict(),
    }


def session_restore(
    state: SessionState,
    project_path: str | None = None,
    event_bus: Any = None,
) -> ServiceResult:
    """Restore session state.

    If *project_path* is given, loads a project from disk into the
    server's session.  Otherwise clears the session to a known-empty
    baseline (useful for client reconnection).
    """
    if project_path:
        from chisurf.server.services.projects import load_project

        result = load_project(state, project_path)
        if result.get("ok") is True and event_bus is not None:
            event_bus.publish("session.restored", {"project_path": project_path})
        return result
    result = session_clear(state)
    if result.get("ok") is True and event_bus is not None:
        event_bus.publish("session.restored", {})
    return {**result, "message": "session cleared"} if result.get("ok") is True else result
