"""RPC contract constants and envelope helpers for the flow-map tool."""

from __future__ import annotations

from typing import Any

PLUGIN_ID = "img_flow"
CONTRACT_VERSION = "1.0.0"

METHOD_MAP = "img_flow.map.compute"
METHOD_METHODS = "img_flow.methods.list"
METHOD_DEMO = "img_flow.demo.create"
METHOD_CONTRACT = "img_flow.contract.describe"

ALL_METHODS = (METHOD_MAP, METHOD_METHODS, METHOD_DEMO, METHOD_CONTRACT)


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
