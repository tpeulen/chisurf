"""Shared RPC contract/service envelope helpers for the MLE imaging tools.

The two MLE plugins had byte-identical ``service_success``/``service_error``
envelopes, an identical ``contract_descriptor`` shape and identical
``register_services``/``_handle_contract`` boilerplate — differing only in the
plugin id, version and the two derived method names. Those pieces live here so
each plugin's ``api/contract.py`` and ``backend/services.py`` only declare what
is genuinely theirs.
"""

from __future__ import annotations

from typing import Any


def service_success(result: Any) -> dict[str, Any]:
    """Wrap a result in the standard success envelope."""
    return {"ok": True, "result": result}


def service_error(msg: Any) -> dict[str, Any]:
    """Wrap an error message in the standard error envelope."""
    return {"ok": False, "error": str(msg)}


def build_contract_descriptor(plugin_id: str, version: str, methods: list[str]) -> dict[str, Any]:
    """Return the standard RPC contract descriptor dict."""
    return {"plugin_id": plugin_id, "version": version, "methods": list(methods)}


def register_analyze_and_contract(
    dispatcher: Any,
    method_analyze: str,
    method_contract: str,
    handle_analyze,
    contract_descriptor,
) -> None:
    """Register the shared ``analyze`` + ``contract`` handler pair.

    ``handle_analyze`` is the plugin-specific analysis handler; the contract
    handler is generated here since it only echoes ``contract_descriptor()``.
    """
    dispatcher.register(method_analyze, handle_analyze)
    dispatcher.register(method_contract, lambda params=None: service_success(contract_descriptor()))
