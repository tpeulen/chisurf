"""RPC contract constants and helpers for spot_finder."""

from __future__ import annotations

from typing import Any

from chisurf.plugins.microscopy.mle_common.contract import (
    build_contract_descriptor,
    service_error,
    service_success,
)

PLUGIN_ID = "spot_finder"
CONTRACT_VERSION = "1.0.0"

METHOD_DETECT = f"{PLUGIN_ID}.detect.run"
METHOD_WORKFLOWS = f"{PLUGIN_ID}.workflow.list"
METHOD_PREPARE_WORKFLOW = f"{PLUGIN_ID}.workflow.prepare"
METHOD_CONTRACT = f"{PLUGIN_ID}.contract.describe"

__all__ = [
    "PLUGIN_ID",
    "CONTRACT_VERSION",
    "METHOD_DETECT",
    "METHOD_WORKFLOWS",
    "METHOD_PREPARE_WORKFLOW",
    "METHOD_CONTRACT",
    "contract_descriptor",
    "service_success",
    "service_error",
]


def contract_descriptor() -> dict[str, Any]:
    """Return a dict describing the plugin RPC contract."""
    return build_contract_descriptor(
        PLUGIN_ID,
        CONTRACT_VERSION,
        [METHOD_DETECT, METHOD_WORKFLOWS, METHOD_PREPARE_WORKFLOW, METHOD_CONTRACT],
    )
