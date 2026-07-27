"""RPC service registration for the FRC resolution calculator."""

from __future__ import annotations

import logging
from typing import Any

from ..api.contract import (
    METHOD_CONTRACT,
    METHOD_CRITERIA,
    METHOD_RESOLUTION,
    contract_descriptor,
    service_error,
    service_success,
)

logger = logging.getLogger(__name__)


def register_services(dispatcher: Any) -> None:
    """Register all ``img_frc.*`` RPC handlers with *dispatcher*."""
    dispatcher.register(METHOD_RESOLUTION, _handle_resolution)
    dispatcher.register(METHOD_CRITERIA, _handle_criteria)
    dispatcher.register(METHOD_CONTRACT, _handle_contract)


def _guard(method: str, fn, params: dict[str, Any] | None):
    """Run *fn* with *params* and wrap the result or the exception in an envelope."""
    try:
        return service_success(fn(**(params or {})))
    except Exception as exc:
        logger.exception("%s failed", method)
        return service_error(exc)


def _handle_resolution(params: dict[str, Any]) -> dict[str, Any]:
    from ..api.frc import compute_resolution

    return _guard(METHOD_RESOLUTION, compute_resolution, params)


def _handle_criteria(params: dict[str, Any] | None = None) -> dict[str, Any]:
    from ..api.frc import list_criteria

    return _guard(METHOD_CRITERIA, list_criteria, {})


def _handle_contract(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the contract descriptor (never fails, so it needs no guard)."""
    return service_success(contract_descriptor())
