"""JSON-RPC contract descriptor for the MFD preparation plugin."""

from __future__ import annotations

from typing import Any

from .models import PrepareRequest, PrepareResult

PLUGIN_ID = "mfd_prepare"
CONTRACT_VERSION = "1.0.0"

METHOD_PREPARE = "mfd_prepare.prepare"
METHOD_DESCRIBE = "mfd_prepare.describe"


def request_from_payload(payload: dict[str, Any]) -> PrepareRequest:
    """Build a :class:`PrepareRequest` from a JSON-RPC payload."""
    return PrepareRequest(
        folder=str(payload.get("folder", "")),
        streams=payload.get("streams"),
        with_photons=bool(payload.get("with_photons", True)),
    )


def result_to_payload(result: PrepareResult) -> dict[str, Any]:
    """Serialize a :class:`PrepareResult` for JSON-RPC."""
    return result.to_dict()


def service_success(result: PrepareResult | dict[str, Any]) -> dict[str, Any]:
    """Wrap a result in the standard ``{"ok": True, ...}`` envelope."""
    if isinstance(result, dict):
        return {"ok": True, **result}
    return {"ok": True, "result": result_to_payload(result)}


def service_error(message: str, **extra: Any) -> dict[str, Any]:
    """Build a standard ``{"ok": False, "error": ...}`` envelope."""
    return {"ok": False, "error": message, **extra}


def contract_descriptor() -> dict[str, Any]:
    """Return the JSON-schema contract for this plugin's RPC methods."""
    return {
        "plugin": PLUGIN_ID,
        "version": CONTRACT_VERSION,
        "methods": [
            {
                "name": METHOD_PREPARE,
                "summary": "Prepare a burst folder for MFD analysis.",
                "params_schema": {
                    "type": "object",
                    "properties": {
                        "folder": {"type": "string"},
                        "streams": {"type": ["array", "null"]},
                        "with_photons": {"type": "boolean"},
                    },
                    "required": ["folder"],
                },
                "result_schema": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"},
                        "result": {"type": "object"},
                    },
                },
            },
            {
                "name": METHOD_DESCRIBE,
                "summary": "Return the plugin contract descriptor.",
                "params_schema": {"type": "object"},
                "result_schema": {"type": "object"},
            },
        ],
    }
