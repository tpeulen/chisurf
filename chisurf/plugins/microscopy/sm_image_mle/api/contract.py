"""RPC contract constants and helpers for sm_image_mle."""

from __future__ import annotations

from typing import Any

from chisurf.plugins.microscopy.mle_common.contract import (
    build_contract_descriptor,
    service_error,
    service_success,
)

PLUGIN_ID = "sm_image_mle"
CONTRACT_VERSION = "2.1.0"

METHOD_ANALYZE = f"{PLUGIN_ID}.analyze.run"
METHOD_CONTRACT = f"{PLUGIN_ID}.contract.describe"

__all__ = [
    "PLUGIN_ID",
    "CONTRACT_VERSION",
    "METHOD_ANALYZE",
    "METHOD_CONTRACT",
    "contract_descriptor",
    "service_success",
    "service_error",
]


def contract_descriptor() -> dict[str, Any]:
    """Return a dict describing the plugin RPC contract."""
    return build_contract_descriptor(
        PLUGIN_ID, CONTRACT_VERSION, [METHOD_ANALYZE, METHOD_CONTRACT]
    )
