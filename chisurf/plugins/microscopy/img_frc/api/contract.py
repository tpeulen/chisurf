"""RPC contract constants and envelope helpers for the FRC calculator."""

from __future__ import annotations

from typing import Any

PLUGIN_ID = "img_frc"
CONTRACT_VERSION = "1.0.0"

METHOD_RESOLUTION = "img_frc.resolution.compute"
METHOD_CRITERIA = "img_frc.criteria.list"
METHOD_CONTRACT = "img_frc.contract.describe"

ALL_METHODS = (METHOD_RESOLUTION, METHOD_CRITERIA, METHOD_CONTRACT)


def contract_descriptor() -> dict[str, Any]:
    """Return a dict describing the plugin RPC contract."""
    return {
        "plugin_id": PLUGIN_ID,
        "version": CONTRACT_VERSION,
        "methods": list(ALL_METHODS),
    }


def service_success(result: Any) -> dict[str, Any]:
    """Wrap a result in the standard success envelope."""
    return {"ok": True, "result": result}


def service_error(msg: Any) -> dict[str, Any]:
    """Wrap an error message in the standard error envelope."""
    return {"ok": False, "error": str(msg)}
