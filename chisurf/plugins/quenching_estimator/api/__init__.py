"""QuEst's contract, re-exported for host code that wants it locally.

Nothing is *defined* here. The contract belongs to the `quest` package
(`quest.rpc.contract`), and a second copy in the plugin would be one more
thing to keep in step — which is precisely the drift `LAY-05` was about.
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
