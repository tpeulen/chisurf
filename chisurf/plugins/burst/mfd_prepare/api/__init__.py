"""Pure API layer for the MFD preparation plugin.

See the burst plugin group (/plugins/burst.md) for its place in the
smFRET pipeline, and :mod:`chisurf.core.fluorescence.mfd` for the core.

Thin wrappers over :mod:`chisurf.core.fluorescence.mfd.prepare` so the
preparation core is reachable from a CLI, an RPC client, and a GUI without
any of them importing the core directly. No Qt, no DB.
"""

from .models import PrepareRequest, PrepareResult
from .contract import (
    PLUGIN_ID,
    CONTRACT_VERSION,
    METHOD_PREPARE,
    METHOD_DESCRIBE,
    contract_descriptor,
    request_from_payload,
    result_to_payload,
    service_success,
    service_error,
)
from .prepare import prepare_folder, describe_preparation

__all__ = [
    "PrepareRequest",
    "PrepareResult",
    "PLUGIN_ID",
    "CONTRACT_VERSION",
    "METHOD_PREPARE",
    "METHOD_DESCRIBE",
    "contract_descriptor",
    "request_from_payload",
    "result_to_payload",
    "service_success",
    "service_error",
    "prepare_folder",
    "describe_preparation",
]
