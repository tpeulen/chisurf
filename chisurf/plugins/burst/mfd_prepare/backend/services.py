"""RPC backend services for the MFD preparation plugin."""

from __future__ import annotations

import logging
from typing import Any

from ..api import (
    METHOD_DESCRIBE,
    METHOD_PREPARE,
    describe_preparation,
    prepare_folder,
    request_from_payload,
    service_error,
    service_success,
)

logger = logging.getLogger(__name__)


def register_services(dispatcher: Any) -> None:
    """Register MFD-prepare RPC handlers on a ServiceDispatcher."""
    dispatcher.register(METHOD_PREPARE, _prepare_handler)
    dispatcher.register(METHOD_DESCRIBE, _describe_handler)


def _prepare_handler(params: dict[str, Any]) -> dict[str, Any]:
    request = request_from_payload(params or {})
    result = prepare_folder(request)
    if result.error:
        return service_error(result.error)
    return service_success(result)


def _describe_handler(params: dict[str, Any]) -> dict[str, Any]:
    return service_success(describe_preparation())
