"""RPC service registration for spot_finder."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from ..api.contract import (
    METHOD_CONTRACT,
    METHOD_DETECT,
    METHOD_PREPARE_WORKFLOW,
    METHOD_WORKFLOWS,
    contract_descriptor,
    service_error,
    service_success,
)

logger = logging.getLogger(__name__)


def register_services(dispatcher: Any) -> None:
    """Register all spot_finder RPC handlers with *dispatcher*."""
    dispatcher.register(METHOD_DETECT, _handle_detect)
    dispatcher.register(METHOD_WORKFLOWS, _handle_workflows)
    dispatcher.register(METHOD_PREPARE_WORKFLOW, _handle_prepare_workflow)
    dispatcher.register(METHOD_CONTRACT, _handle_contract)


def _handle_detect(params: dict[str, Any]) -> dict[str, Any]:
    """Detect regions in one or more images and write them to their containers."""
    try:
        from ..api.spot_finder import detect_request
        from ..core.workflow import STANDARD, request_from_workflow

        # A workflow name, a whole document, or nothing — which means the
        # standard one. `settings` then overrides only what it names, so a
        # caller sending three keys does not silently reset the other twelve.
        request = request_from_workflow(
            params.get("workflow") or STANDARD,
            files=params.get("files") or [],
            out_dir=params.get("out_dir", ""),
        )
        for key, value in (params.get("settings") or {}).items():
            if not hasattr(request.settings, key):
                raise ValueError(f"unknown detection setting {key!r}")
            setattr(request.settings, key, value)
        request.name = params.get("name", request.name)
        if params.get("channels"):
            request.channels = list(params["channels"])
        if "frame" in params:
            request.frame = int(params["frame"])
        if "write" in params:
            request.write = bool(params["write"])

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


def _handle_workflows(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the shipped workflow documents, the standard one first."""
    try:
        from ..core.workflow import STANDARD, builtin_workflow, list_workflows

        names = list_workflows()
        return service_success(
            {
                "standard": STANDARD,
                "names": names,
                "workflows": {name: builtin_workflow(name) for name in names},
            }
        )
    except Exception as exc:
        logger.exception("spot_finder.workflow.list failed")
        return service_error(exc)


def _handle_prepare_workflow(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve detection inputs from a cross-plugin workflow context.

    The handoff the burst tools already speak, for imaging: an earlier step
    announces the raw files (and which detector channels they were acquired
    on), and this returns the request that would detect in them — without
    running it, so a panel can show what is about to happen.
    """
    try:
        from ..core.workflow import STANDARD, request_from_workflow, workflow_from_request

        params = params or {}
        context = params.get("workflow_context") or {}
        files = params.get("files") or context.get("raw_files") or []

        request = request_from_workflow(
            params.get("workflow") or STANDARD,
            files=[str(f) for f in files],
            out_dir=params.get("out_dir", ""),
        )
        for key, value in (params.get("settings") or {}).items():
            if not hasattr(request.settings, key):
                raise ValueError(f"unknown detection setting {key!r}")
            setattr(request.settings, key, value)

        # The channels an earlier step settled on, rather than every channel in
        # the file: a detector setup is a decision, and re-deriving it here
        # would be a second answer to a question already answered.
        channels = _channels_from_context(context)
        if channels:
            request.channels = channels

        return service_success(
            {
                "files": list(request.files),
                "channels": request.channels,
                "workflow": workflow_from_request(request),
                "workflow_context": context,
            }
        )
    except Exception as exc:
        logger.exception("spot_finder.workflow.prepare failed")
        return service_error(exc)


def _channels_from_context(context: dict[str, Any]) -> list[int]:
    """Return the routing channels a workflow context declares, if any."""
    channel_settings = context.get("channel_settings") or {}
    channels: list[int] = []
    for entry in channel_settings.values():
        if isinstance(entry, dict):
            channels.extend(int(c) for c in entry.get("chs", []))
    return sorted(set(channels))


def _handle_contract(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the RPC contract descriptor."""
    return service_success(contract_descriptor())
