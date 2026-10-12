"""QuEst's service layer: named operations behind one call contract.

See :mod:`quest.rpc.contract` for the identity, error codes and the
serialization boundary, :mod:`quest.rpc.services` for the method table, and
:mod:`quest.rpc.dispatcher` for the envelope and the in-process client.
"""

from chisurf.plugins.quenching_estimator.rpc.contract import (
    CONTRACT_VERSION,
    ERROR_CODES,
    PLUGIN_ID,
    contract_descriptor,
    error_code_for,
    service_error,
    service_success,
    to_payload,
)
from chisurf.plugins.quenching_estimator.rpc.dispatcher import (
    InProcessClient,
    RemoteError,
    ServiceDispatcher,
)
from chisurf.plugins.quenching_estimator.rpc.services import (
    METHODS,
    local_client,
    register_services,
    result_payload,
    simulation_payload,
)

__all__ = [
    "InProcessClient",
    "RemoteError",
    "ServiceDispatcher",
    "METHODS",
    "local_client",
    "register_services",
    "result_payload",
    "simulation_payload",
    "PLUGIN_ID",
    "CONTRACT_VERSION",
    "ERROR_CODES",
    "contract_descriptor",
    "error_code_for",
    "service_error",
    "service_success",
    "to_payload",
]
