"""ServiceDispatcher RPC handlers of Excitation Windows: thin adapters over :mod:`..api`."""

from __future__ import annotations

from typing import Any

from .. import api

METHOD_DETECT = "excitation_windows.detect"
METHOD_CHECK = "excitation_windows.check"


def register_services(dispatcher: Any) -> None:
    """Register the Excitation Windows RPC handlers with a ServiceDispatcher."""
    dispatcher.register(METHOD_DETECT, lambda params: _detect(**(params or {})))
    dispatcher.register(METHOD_CHECK, lambda params: _check(**(params or {})))


def list_methods() -> dict[str, str]:
    """The RPC method catalogue."""
    return {
        METHOD_DETECT: "Detect the excitation scheme of a measurement and propose windows.",
        METHOD_CHECK: "Check a setup's windows against a measurement.",
    }


def _detect(path: str, setup: Any = None, kind: str = "auto", **_: Any) -> dict:
    return api.detect(path, setup, kind)


def _check(path: str, setup: Any, **_: Any) -> dict:
    return api.check(path, setup)


__all__ = ["METHOD_CHECK", "METHOD_DETECT", "list_methods", "register_services"]
