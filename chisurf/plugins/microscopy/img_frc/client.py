"""Transport-agnostic client for the FRC backend services.

Wraps an in-process dispatcher by default and a ZMQ client when pointed at a
server, so the CLI and the GUI behave identically in local and server mode.
"""

from __future__ import annotations

from typing import Any

from .api import contract


class FrcClient:
    """Typed convenience wrapper over the ``img_frc.*`` RPC methods."""

    def __init__(
        self,
        client: Any = None,
        host: str = "127.0.0.1",
        cmd_port: int = 8765,
        pub_port: int = 8766,
    ) -> None:
        self._host = host
        self._cmd_port = cmd_port
        self._pub_port = pub_port
        self._client = client if client is not None else self._make_local_client()

    @staticmethod
    def _make_local_client() -> Any:
        """Create an in-process client with the FRC services registered."""
        from chisurf.core.plugin.client import InProcessClient
        from chisurf.server.dispatcher import ServiceDispatcher
        from chisurf.server.session import SessionState

        from .backend.services import register_services

        dispatcher = ServiceDispatcher(SessionState())
        register_services(dispatcher)
        return InProcessClient(dispatcher)

    def make_remote_client(self) -> Any:
        """Switch this client to a ZMQ transport connected to ``host:port``."""
        from chisurf.server.transport.zmq import ZmqClient

        self._client = ZmqClient(host=self._host, cmd_port=self._cmd_port, pub_port=self._pub_port)
        return self._client

    def _call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        result = self._client.call(method, params or {})
        if not result.get("ok", True):
            raise RuntimeError(result.get("error", f"{method} failed"))
        return result.get("result")

    # ── methods ────────────────────────────────────────────────────────
    def resolution(self, filename: str, **kwargs: Any) -> dict[str, Any]:
        """Measure the resolution of *filename*; see the API for the options."""
        return self._call(contract.METHOD_RESOLUTION, {"filename": filename, **kwargs})

    def criteria(self) -> dict[str, Any]:
        """List the threshold criteria and the available splits."""
        return self._call(contract.METHOD_CRITERIA)

    def describe(self) -> dict[str, Any]:
        """Return the RPC contract descriptor."""
        return self._call(contract.METHOD_CONTRACT)
