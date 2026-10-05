"""The typed document-history boundary shared by capture and publication."""

from __future__ import annotations

import copy
import sys
from types import ModuleType
from typing import Any


class ProjectHistoryError(ValueError):
    """A project contains an invalid or inconsistent owned history envelope."""


def _concrete_history(history: Any) -> Any:
    """Resolve only the declared ChiSurf facade without traversing module state."""
    if isinstance(history, ModuleType):
        if history is not sys.modules.get("chisurf.history"):
            raise ProjectHistoryError("Unsupported project history module")
        return history.get_history()
    return history


def capture_history(history: Any) -> dict[str, Any]:
    """Detach history data; never serialize callbacks, locks or subscribers."""
    history = _concrete_history(history)
    if history is None:
        return {}
    export = getattr(history, "export_state", None)
    if callable(export):
        state = copy.deepcopy(export())
        if not isinstance(state, dict) or not isinstance(state.get("events"), list):
            raise ProjectHistoryError("Invalid history export envelope")
        return {"history_state": state, "history_events": copy.deepcopy(state["events"])}
    events = getattr(history, "list_events", None)
    if callable(events):
        # Non-scientific audit adapters carry no replay authority. They cannot
        # stand in for OperationHistory's complete scientific envelope.
        return {"history_events": copy.deepcopy(events())}
    return {}


def validate_history_state(project: Any, *, history: Any = None) -> Any:
    """Stage typed history against its owner before any file/RPC/owner mutation."""
    extra = project.extra
    if "history_state" not in extra:
        return None
    from chisurf.history.core import OperationHistory

    state = extra["history_state"]
    try:
        validator = OperationHistory() if history is None else _concrete_history(history)
        if not isinstance(validator, OperationHistory):
            raise ValueError("Scientific history requires a concrete OperationHistory owner")
        staged = validator.validate_state(state)
        if "history_events" in extra and extra["history_events"] != state["events"]:
            raise ValueError("history event projection differs from its owned envelope")
        return staged
    except Exception as exc:
        raise ProjectHistoryError(f"Invalid project history: {exc}") from exc
