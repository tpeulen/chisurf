"""Backend RPC services for the synthetic decay generator."""

from __future__ import annotations

from typing import Any

from ..core.algorithms import (
    compute_aniso_decay,
    compute_component_decay,
    compute_decay,
    compute_rt,
)


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


def _compute_aniso_handler(**params) -> dict[str, Any]:
    try:
        return {"ok": True, "result": compute_aniso_decay(**params)}
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": str(exc)}


def _compute_rt_handler(**params) -> dict[str, Any]:
    try:
        return {"ok": True, "result": compute_rt(**params)}
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": str(exc)}


def register_services(dispatcher: Any) -> None:
    """Register the synthetic_decay RPC handlers with a ServiceDispatcher."""
    dispatcher.register("synthetic_decay.compute", lambda p: _compute_handler(**p))
    dispatcher.register(
        "synthetic_decay.compute_component", lambda p: _compute_component_handler(**p)
    )
    dispatcher.register("synthetic_decay.compute_aniso", lambda p: _compute_aniso_handler(**p))
    dispatcher.register("synthetic_decay.compute_rt", lambda p: _compute_rt_handler(**p))
