"""RPC backend services for the MFD preparation plugin (PRD-72 item 7)."""

from __future__ import annotations

import logging
from typing import Any

from ..api import (
    METHOD_PREPARE,
    METHOD_DESCRIBE,
    prepare_folder,
    describe_preparation,
    request_from_payload,
    service_success,
    service_error,
)

logger = logging.getLogger(__name__)


def register_services(dispatcher, **kwargs: Any) -> None:
    """Register MFD-prepare RPC handlers on a ServiceDispatcher."""

    @dispatcher.method(METHOD_PREPARE)
    def _prepare(params: dict[str, Any]) -> dict[str, Any]:
        request = request_from_payload(params)
        result = prepare_folder(request)
        if result.error:
            return service_error(result.error)
        return service_success(result)

    @dispatcher.method(METHOD_DESCRIBE)
    def _describe(params: dict[str, Any]) -> dict[str, Any]:
        return service_success(describe_preparation())
