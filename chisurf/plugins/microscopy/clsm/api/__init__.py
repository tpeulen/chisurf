"""Public, transport-agnostic API for the CLSM plugin."""

from __future__ import annotations

from .clsm import (
    compute_representation,
    extract_decay,
    image_info,
    list_setups,
)
from .contract import (
    ALL_METHODS,
    CONTRACT_VERSION,
    METHOD_CONTRACT,
    METHOD_DECAY,
    METHOD_INFO,
    METHOD_REPRESENTATION,
    METHOD_SETUPS,
    PLUGIN_ID,
    contract_descriptor,
    service_error,
    service_success,
)
from .models import ClsmSetup, DecayResult, RepresentationResult

__all__ = [
    "list_setups",
    "image_info",
    "compute_representation",
    "extract_decay",
    "ClsmSetup",
    "RepresentationResult",
    "DecayResult",
    "PLUGIN_ID",
    "CONTRACT_VERSION",
    "ALL_METHODS",
    "METHOD_SETUPS",
    "METHOD_INFO",
    "METHOD_REPRESENTATION",
    "METHOD_DECAY",
    "METHOD_CONTRACT",
    "contract_descriptor",
    "service_success",
    "service_error",
]
