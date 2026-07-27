"""Public API surface of the FRC resolution calculator."""

from .contract import (
    ALL_METHODS,
    CONTRACT_VERSION,
    METHOD_CONTRACT,
    METHOD_CRITERIA,
    METHOD_RESOLUTION,
    PLUGIN_ID,
    contract_descriptor,
    service_error,
    service_success,
)
from .frc import compute_resolution, list_criteria

__all__ = [
    "ALL_METHODS",
    "CONTRACT_VERSION",
    "METHOD_CONTRACT",
    "METHOD_CRITERIA",
    "METHOD_RESOLUTION",
    "PLUGIN_ID",
    "compute_resolution",
    "contract_descriptor",
    "list_criteria",
    "service_error",
    "service_success",
]
