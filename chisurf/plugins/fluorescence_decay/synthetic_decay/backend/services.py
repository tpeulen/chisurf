"""Backend RPC services for the synthetic decay generator."""

from __future__ import annotations

from typing import Any

from ..core.algorithms import compute_component_decay, compute_decay


def _compute_handler(**params) -> dict[str, Any]:
    try:
        return {"ok": True, "result": compute_decay(**params)}
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": str(exc)}


def _compute_component_handler(**params) -> dict[str, Any]:
    try:
        return {"ok": True, "result": compute_component_decay(**params)}
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": str(exc)}


def register_services(dispatcher: Any) -> None:
    """Register the synthetic_decay RPC handlers with a ServiceDispatcher."""
    dispatcher.register("synthetic_decay.compute", lambda p: _compute_handler(**p))
    dispatcher.register(
        "synthetic_decay.compute_component", lambda p: _compute_component_handler(**p)
    )
