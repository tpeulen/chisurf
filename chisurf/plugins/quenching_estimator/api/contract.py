"""The contract, taken from QuEst rather than restated.

`chisurf/plugins/modelling/fps_json_editor/api/contract.py` *defines* its
plugin's contract because that plugin's logic lives in ChiSurf. QuEst is the
other case: the logic is an installable package, so the contract is
`quest.rpc.contract` and this module only re-exports it.

Everything is imported **lazily**, inside functions. Importing `quest` reaches
IMP and numba, and ChiSurf's plugin discovery imports every plugin at startup —
which is why the old single-file plugin made ChiSurf pay for QuEst whether or
not anyone opened it.
"""

from __future__ import annotations

from typing import Any

PLUGIN_ID = "quenching_estimator"

__all__ = [
    "PLUGIN_ID",
    "CONTRACT_VERSION",
    "ERROR_CODES",
    "METHOD_NAMES",
    "contract_descriptor",
    "service_success",
    "service_error",
]


def __getattr__(name: str) -> Any:
    """Resolve the re-exported names on first access, not at import."""
    if name == "CONTRACT_VERSION":
        from quest.rpc.contract import CONTRACT_VERSION

        return CONTRACT_VERSION
    if name == "ERROR_CODES":
        from quest.rpc.contract import ERROR_CODES

        return ERROR_CODES
    if name == "METHOD_NAMES":
        from quest.rpc.services import METHODS

        return tuple(METHODS)
    raise AttributeError(name)


def contract_descriptor() -> dict[str, Any]:
    """QuEst's descriptor, with the host-side identity added."""
    from quest.rpc.contract import contract_descriptor as _descriptor

    descriptor = _descriptor()
    descriptor["host_plugin_id"] = PLUGIN_ID
    descriptor["transport"]["gui"] = "chisurf.plugins.quenching_estimator.gui.tool:QuEstTool"
    return descriptor


def service_success(result: Any) -> dict[str, Any]:
    from quest.rpc.contract import service_success as _ok

    return _ok(result)


def service_error(error: str, error_code: str = "operation_failed", **kwargs: Any):
    from quest.rpc.contract import service_error as _fail

    return _fail(error, error_code, **kwargs)
