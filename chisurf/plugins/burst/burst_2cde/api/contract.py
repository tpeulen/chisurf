"""Workflow contract for the 2CDE plugin."""

from __future__ import annotations

from typing import Any

from .models import TwoCdeSettings
from .serialization import settings_from_dict

PLUGIN_ID = "burst_2cde"
CONTRACT_VERSION = "1.0.0"

METHOD_COMPUTE_2CDE = "burst_2cde.jobs.compute"
METHOD_DESCRIBE_CONTRACT = "burst_2cde.contract.describe"

CANONICAL_METHODS = (
    METHOD_COMPUTE_2CDE,
    METHOD_DESCRIBE_CONTRACT,
)


def two_cde_request_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize a JSON-compatible payload into a 2CDE request dict."""
    settings_payload = payload.get("settings", {})
    if isinstance(settings_payload, TwoCdeSettings):
        settings = settings_payload
    elif isinstance(settings_payload, dict):
        settings = settings_from_dict(TwoCdeSettings, settings_payload)
    else:
        settings = TwoCdeSettings()
    return {
        "files": [str(p) for p in payload.get("files", [])],
        "settings": settings,
        "analysis_folder": payload.get("analysis_folder"),
        "pattern": payload.get("pattern", "bi4_bur"),
    }


def service_success(result: dict[str, Any] | Any) -> dict[str, Any]:
    """Wrap a result in the standard JSON-RPC service envelope."""
    from .serialization import to_jsonable
    return {"ok": True, "result": to_jsonable(result)}


def contract_descriptor() -> dict[str, Any]:
    """Return the JSON-compatible 2CDE workflow contract."""
    return {
        "plugin_id": PLUGIN_ID,
        "contract_version": CONTRACT_VERSION,
        "transport": {
            "rpc": "JSON-RPC over ChiSurf ServiceDispatcher/ZMQ",
            "cli": "chisurf 2cde",
            "api": "chisurf.plugins.burst.burst_2cde.api",
        },
        "inputs": {
            "Compute2CDE": {
                "type": "object",
                "required": ["files"],
                "properties": {
                    "files": {"type": "array", "items": {"type": "string"}},
                    "analysis_folder": {"type": ["string", "null"]},
                    "pattern": {"type": "string"},
                    "settings": {"$ref": "#/definitions/TwoCdeSettings"},
                },
            },
        },
        "outputs": {
            "ServiceResult": {
                "type": "object",
                "required": ["ok"],
                "properties": {
                    "ok": {"type": "boolean"},
                    "result": {"type": "object"},
                    "error": {"type": "string"},
                },
            },
        },
        "definitions": {
            "TwoCdeSettings": {
                "type": "object",
                "properties": {
                    "donor_channels": {"type": "array", "items": {"type": "integer"}},
                    "donor_micro_time_ranges": {"type": "array", "items": {"type": "array", "minItems": 2, "maxItems": 2}},
                    "acceptor_channels": {"type": "array", "items": {"type": "integer"}},
                    "acceptor_micro_time_ranges": {"type": "array", "items": {"type": "array", "minItems": 2, "maxItems": 2}},
                    "acceptor_excitation_channels": {"type": "array", "items": {"type": "integer"}},
                    "acceptor_excitation_micro_time_ranges": {"type": "array", "items": {"type": "array", "minItems": 2, "maxItems": 2}},
                    "tau": {"type": "number"},
                    "kernel": {"type": "string", "enum": ["laplace", "gaussian"]},
                    "variant": {"type": "string", "enum": ["fret", "alex"]},
                    "file_type": {"type": "string"},
                },
            },
        },
        "rpc_methods": {
            METHOD_COMPUTE_2CDE: {
                "input": "Compute2CDE",
                "output": "ServiceResult",
                "long_running": True,
            },
            METHOD_DESCRIBE_CONTRACT: {"input": "{}", "output": "ServiceResult"},
        },
    }
