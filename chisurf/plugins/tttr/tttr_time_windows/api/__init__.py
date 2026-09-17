"""Time Window Bins API package.

Pure Python layer with no Qt dependencies. GUI, CLI, and RPC layers
normalize to :class:`TimeWindowRequest` and return
:class:`TimeWindowResult` payloads.
"""

from .contract import (
    METHOD_ANALYZE_FILES,
    METHOD_DESCRIBE_CONTRACT,
    PLUGIN_ID,
    contract_descriptor,
    request_from_payload,
    request_to_payload,
    result_to_payload,
    service_success,
)
from .io import compute_and_save, load_tttr, save_bst
from .models import TimeWindowRequest, TimeWindowResult
from .selection import compute_bids_from_tttr

__all__ = [
    "METHOD_ANALYZE_FILES",
    "METHOD_DESCRIBE_CONTRACT",
    "PLUGIN_ID",
    "TimeWindowRequest",
    "TimeWindowResult",
    "compute_bids_from_tttr",
    "compute_and_save",
    "contract_descriptor",
    "load_tttr",
    "request_from_payload",
    "request_to_payload",
    "result_to_payload",
    "save_bst",
    "service_success",
]
