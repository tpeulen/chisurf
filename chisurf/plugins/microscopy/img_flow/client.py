"""Transport-agnostic client for the flow-map backend services.

Wraps an in-process dispatcher by default and a ZMQ client when pointed at a
server, so the CLI and the GUI take the same path in local and server mode.
"""

from __future__ import annotations

from typing import Any

from .api import contract


class FlowClient:
    """Typed convenience wrapper over the ``img_flow.*`` RPC methods."""

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
        """Create an in-process client with the flow services registered."""
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
    def flow_map(self, filename: str, **kwargs: Any) -> dict[str, Any]:
        """Compute a velocity field; see the API for the options."""
        return self._call(contract.METHOD_MAP, {"filename": filename, **kwargs})

    def methods(self) -> dict[str, Any]:
        """List the estimators and what each can see."""
        return self._call(contract.METHOD_METHODS)

    def demo(self, **kwargs: Any) -> dict[str, Any]:
        """Simulate (or reuse) the demo photon stream and return its ground truth."""
        return self._call(contract.METHOD_DEMO, kwargs)

    def describe(self) -> dict[str, Any]:
        """Return the RPC contract descriptor."""
        return self._call(contract.METHOD_CONTRACT)
