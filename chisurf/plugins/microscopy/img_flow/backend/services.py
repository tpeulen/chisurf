"""RPC service registration for the flow-map tool."""

from __future__ import annotations

import logging
from typing import Any

from ..api.contract import (
    METHOD_CONTRACT,
    METHOD_DEMO,
    METHOD_MAP,
    METHOD_METHODS,
    contract_descriptor,
    service_error,
    service_success,
)

logger = logging.getLogger(__name__)


def register_services(dispatcher: Any) -> None:
    """Register all ``img_flow.*`` RPC handlers with *dispatcher*."""
    dispatcher.register(METHOD_MAP, _handle_map)
    dispatcher.register(METHOD_METHODS, _handle_methods)
    dispatcher.register(METHOD_DEMO, _handle_demo)
    dispatcher.register(METHOD_CONTRACT, _handle_contract)


def _guard(method: str, fn, params: dict[str, Any] | None):
    """Run *fn* with *params* and wrap the result or the exception in an envelope."""
    try:
        return service_success(fn(**(params or {})))
    except Exception as exc:
        logger.exception("%s failed", method)
        return service_error(exc)


def _handle_map(params: dict[str, Any]) -> dict[str, Any]:
    from ..api.flow import compute_map

    return _guard(METHOD_MAP, compute_map, params)


def _handle_methods(params: dict[str, Any] | None = None) -> dict[str, Any]:
    from ..api.flow import list_methods

    return _guard(METHOD_METHODS, list_methods, {})


def _handle_demo(params: dict[str, Any] | None = None) -> dict[str, Any]:
    from ..api.flow import create_demo

    return _guard(METHOD_DEMO, create_demo, params or {})


def _handle_contract(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the contract descriptor (never fails, so it needs no guard)."""
    return service_success(contract_descriptor())
