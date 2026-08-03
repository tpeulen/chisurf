"""The burst-fusion workflow contract: methods, payload shapes, envelopes.

One place that states what the RPC surface accepts and returns, so the service,
the CLI, the GUI client and a caller in another process cannot each hold a
slightly different idea of it. ``burst_fusion.contract.describe`` returns
:func:`contract_descriptor` verbatim, which makes the contract discoverable at
run time rather than only in this file.
"""

from __future__ import annotations

from typing import Any

from .models import FusionSettings

PLUGIN_ID = "burst_fusion"
CONTRACT_VERSION = "1.0.0"

METHOD_ANALYZE = "burst_fusion.jobs.analyze"
METHOD_FUSE = "burst_fusion.jobs.fuse"
METHOD_PREPARE = "burst_fusion.workflow.prepare"
METHOD_DESCRIBE_CONTRACT = "burst_fusion.contract.describe"

CANONICAL_METHODS = (
    METHOD_ANALYZE,
    METHOD_FUSE,
    METHOD_PREPARE,
    METHOD_DESCRIBE_CONTRACT,
)


def settings_from_payload(payload: dict[str, Any] | None) -> FusionSettings:
    """Normalise a JSON payload (or a settings object) into :class:`FusionSettings`."""
    if isinstance(payload, FusionSettings):
        return payload
    return FusionSettings.from_dict(payload if isinstance(payload, dict) else None)


def service_success(result: dict[str, Any]) -> dict[str, Any]:
    """Wrap a result in the service envelope every handler returns."""
    out: dict[str, Any] = {"status": "ok"}
    out.update(result)
    return out


def service_error(message: str) -> dict[str, Any]:
    """Wrap a failure in the same envelope, so a caller tests one field."""
    return {"status": "error", "error": str(message)}


def contract_descriptor() -> dict[str, Any]:
    """Return the JSON-compatible burst-fusion workflow contract."""
    return {
        "plugin_id": PLUGIN_ID,
        "contract_version": CONTRACT_VERSION,
        "transport": {
            "rpc": "JSON-RPC over ChiSurf ServiceDispatcher/ZMQ",
            "cli": "csc fusion",
            "api": "chisurf.plugins.burst.burst_fusion.api",
        },
        "inputs": {
            "Analyze": {
                "type": "object",
                "required": ["analysis_folder"],
                "properties": {
                    "analysis_folder": {"type": "string"},
                    "settings": {"$ref": "#/definitions/FusionSettings"},
                },
            },
            "Fuse": {
                "type": "object",
                "required": ["analysis_folder"],
                "properties": {
                    "analysis_folder": {"type": "string"},
                    "settings": {"$ref": "#/definitions/FusionSettings"},
                    "output_folder": {"type": ["string", "null"]},
                    "detectors": {"type": ["object", "null"]},
                    "windows": {"type": ["object", "null"]},
                    "data_folder": {"type": ["string", "null"]},
                },
            },
        },
        "outputs": {
            "AnalyzeResult": {
                "type": "object",
                "required": ["status", "curve", "statistics"],
                "properties": {
                    "status": {"enum": ["ok", "error"]},
                    "analysis_folder": {"type": "string"},
                    "curve": {"$ref": "#/definitions/PSameCurve"},
                    "statistics": {"type": "object"},
                    "settings": {"$ref": "#/definitions/FusionSettings"},
                },
            },
            "FuseResult": {
                "type": "object",
                "required": ["status", "output_folder"],
                "properties": {
                    "status": {"enum": ["ok", "error"]},
                    "output_folder": {"type": "string"},
                    "bur_files": {"type": "array", "items": {"type": "string"}},
                    "per_measurement": {"type": "object"},
                    "tau_max_s": {"type": "number"},
                    "tau_used_s": {"type": "number"},
                    "resolved": {"type": "boolean"},
                    "statistics": {"type": "object"},
                },
            },
        },
        "definitions": {
            "FusionSettings": {
                "type": "object",
                "properties": {
                    key: {"type": _json_type(value)}
                    for key, value in FusionSettings().to_dict().items()
                },
            },
            "PSameCurve": {
                "type": "object",
                "properties": {
                    "tau_s": {"type": "array", "items": {"type": "number"}},
                    # ``null`` marks a lag bin with too few counted pairs to judge,
                    # which is deliberately not the same as a probability of zero.
                    "p_same": {"type": "array", "items": {"type": ["number", "null"]}},
                    "pairs": {"type": "array", "items": {"type": "number"}},
                    "tau_max_s": {"type": "number"},
                    "resolved": {"type": "boolean"},
                    "threshold": {"type": "number"},
                    "n_bursts": {"type": "integer"},
                },
            },
        },
        "side_effects": {
            "Analyze": "none — reads the burst tables only",
            "Fuse": (
                "writes a new burst-analysis folder (bi4_bur, fu4, Info) and, "
                "unless disabled, an fg4 companion beside the source bursts"
            ),
        },
        "methods": list(CANONICAL_METHODS),
    }


def _json_type(value: Any) -> str:
    """Map a settings default to its JSON Schema type name."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"


__all__ = [
    "CANONICAL_METHODS",
    "CONTRACT_VERSION",
    "METHOD_ANALYZE",
    "METHOD_DESCRIBE_CONTRACT",
    "METHOD_FUSE",
    "METHOD_PREPARE",
    "PLUGIN_ID",
    "contract_descriptor",
    "service_error",
    "service_success",
    "settings_from_payload",
]
