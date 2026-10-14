"""The plugin's contract: the identity, error codes and method table of ``rpc/``.

Everything is imported **lazily**, inside functions: the method table reaches
the engine (``core/``), and through it IMP, and ChiSurf's plugin discovery
imports every plugin at startup.
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
        from ..rpc.contract import CONTRACT_VERSION

        return CONTRACT_VERSION
    if name == "ERROR_CODES":
        from ..rpc.contract import ERROR_CODES

        return ERROR_CODES
    if name == "METHOD_NAMES":
        from ..rpc.services import METHODS

        return tuple(METHODS)
    raise AttributeError(name)


def contract_descriptor() -> dict[str, Any]:
    """The service descriptor, with the host-side identity added."""
    from ..rpc.contract import contract_descriptor as _descriptor

    descriptor = _descriptor()
    descriptor["host_plugin_id"] = PLUGIN_ID
    descriptor["transport"]["emtk"] = "chisurf.plugins.quenching_estimator.gui.app:make_app"
    return descriptor


def service_success(result: Any) -> dict[str, Any]:
    """The success envelope of :mod:`..rpc.contract`."""
    from ..rpc.contract import service_success as _ok

    return _ok(result)


def service_error(error: str, error_code: str = "operation_failed", **kwargs: Any):
    """The error envelope of :mod:`..rpc.contract`."""
    from ..rpc.contract import service_error as _fail

    return _fail(error, error_code, **kwargs)
