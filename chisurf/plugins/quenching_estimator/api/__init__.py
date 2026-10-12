"""Host-side access to QuEst: the in-process client and the contract.

``local`` is the facade (``template``, ``validate``, ``simulate``, ``scan`` ...); it is imported on
use, not here, because it reaches the engine and through it IMP.
"""

from .client import QuEstClient
from .contract import (
    CONTRACT_VERSION,
    ERROR_CODES,
    METHOD_NAMES,
    PLUGIN_ID,
    contract_descriptor,
)

__all__ = [
    "QuEstClient",
    "PLUGIN_ID",
    "CONTRACT_VERSION",
    "ERROR_CODES",
    "METHOD_NAMES",
    "contract_descriptor",
]
