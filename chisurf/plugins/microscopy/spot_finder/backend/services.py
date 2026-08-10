"""RPC service registration for spot_finder."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from ..api.contract import (
    METHOD_CONTRACT,
    METHOD_DETECT,
    contract_descriptor,
    service_error,
    service_success,
)

logger = logging.getLogger(__name__)


def register_services(dispatcher: Any) -> None:
    """Register all spot_finder RPC handlers with *dispatcher*."""
    dispatcher.register(METHOD_DETECT, _handle_detect)
    dispatcher.register(METHOD_CONTRACT, _handle_contract)


def _handle_detect(params: dict[str, Any]) -> dict[str, Any]:
    """Detect regions in one or more images and write them to their containers."""
    try:
        from ..api.models import SpotFinderRequest, SpotFinderSettings
        from ..api.spot_finder import detect_request

        settings_dict = params.get("settings") or {}
        field_names = {f.name for f in dataclasses.fields(SpotFinderSettings)}
        settings = SpotFinderSettings(
            **{k: v for k, v in settings_dict.items() if k in field_names}
        )
        request = SpotFinderRequest(
            files=params["files"],
            name=params.get("name", "spots"),
            channels=params.get("channels"),
            frame=int(params.get("frame", -1)),
            settings=settings,
            write=bool(params.get("write", True)),
            out_dir=params.get("out_dir", ""),
        )
        result = detect_request(request)
        return service_success(
            {
                # Every input, with what became of it -- a caller that only
                # reads `rows` where status == ok still sees the ones that did
                # not, which a shortened list would have hidden.
                "rows": [dataclasses.asdict(row) for row in result.rows],
                "n_regions": result.n_regions,
                "n_failed": len(result.failed),
            }
        )
    except Exception as exc:
        logger.exception("spot_finder.detect.run failed")
        return service_error(exc)


def _handle_contract(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the RPC contract descriptor."""
    return service_success(contract_descriptor())
