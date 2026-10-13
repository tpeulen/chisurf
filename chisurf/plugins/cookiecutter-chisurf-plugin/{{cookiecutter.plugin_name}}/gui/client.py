"""PluginClient wrapper for {{ cookiecutter.plugin_display_name }}.

GUI code should use this client instead of importing ``..api`` or ``..core``
directly.
"""

from __future__ import annotations

from typing import Any

from chisurf.core.plugin.client import InProcessClient


class {{ cookiecutter.class_prefix }}Client:
    """Client for {{ cookiecutter.plugin_display_name }} backend services."""

    def __init__(self, client: Any = None):
        if client is not None:
            self._client = client
        else:
            self._client = self._make_local_client()

    def ping(self) -> dict[str, Any]:
        """Check if the plugin backend is alive."""
        result = self._client.call("{{ cookiecutter.plugin_name }}.ping")
        return result.get("result", {})

    def compute(self, settings: dict[str, Any]) -> float:
        """The result of *settings* (a ``PluginSettings`` dict), computed by the backend."""
        result = self._client.call("{{ cookiecutter.plugin_name }}.compute", settings)
        return result.get("result", {})["result"]

    @staticmethod
    def _make_local_client() -> InProcessClient:
        """Create a local in-process client with plugin services."""
        from chisurf.server.dispatcher import ServiceDispatcher
        from chisurf.server.session import SessionState

        state = SessionState()
        dispatcher = ServiceDispatcher(state)
        dispatcher._build_default_registry()

        from chisurf.plugins.{{ cookiecutter.plugin_name }}.backend.services import (
            register_services,
        )
        register_services(dispatcher)
        return InProcessClient(dispatcher)
