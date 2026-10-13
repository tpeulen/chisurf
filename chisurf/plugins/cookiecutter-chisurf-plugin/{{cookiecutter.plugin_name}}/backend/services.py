"""ServiceDispatcher-compatible RPC handlers for {{ cookiecutter.plugin_display_name }}.

Thin adapters: accept JSON-compatible params, delegate to core, return JSON-safe results.
"""

from __future__ import annotations

from typing import Any


def register_services(dispatcher: Any) -> None:
    """Register RPC handlers with a ServiceDispatcher.

    Parameters
    ----------
    dispatcher : ServiceDispatcher
        The server's service dispatcher.

    """
    dispatcher.register(
        "{{ cookiecutter.plugin_name }}.ping",
        lambda params: {"ok": True, "result": "pong"},
    )
    dispatcher.register("{{ cookiecutter.plugin_name }}.compute", _compute)


def _compute(params: dict[str, Any]) -> dict[str, Any]:
    """Run :func:`..core.algorithms.compute_example` on the settings in *params*."""
    from ..api.serialization import settings_from_dict
    from ..core.algorithms import compute_example

    return {"ok": True, "result": compute_example(settings_from_dict(params or {}))}


def list_methods() -> dict[str, str]:
    """Return the RPC method catalogue."""
    return {
        "{{ cookiecutter.plugin_name }}.ping": "Liveness check.",
        "{{ cookiecutter.plugin_name }}.compute": "Compute the example result of a PluginSettings dict.",
    }
