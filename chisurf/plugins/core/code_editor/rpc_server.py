from __future__ import annotations

import queue
import threading
import time
from typing import Any

from chisurf.plugins.core.code_editor.backend.services import dispatch
from chisurf.plugins.core.code_editor.document_store import DocumentStore
from chisurf.plugins.core.code_editor.ruff_runner import RuffRunner
from chisurf.server.transport.zmq import ZmqServer


class EditorRpcServer:
    """ZeroMQ JSON-RPC server for the GUI-owned editor document store."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        cmd_port: int = 8775,
        pub_port: int = 8776,
        store: DocumentStore | None = None,
        runner: RuffRunner | None = None,
    ) -> None:
        self.host = host
        self.cmd_port = cmd_port
        self.pub_port = pub_port
        self.store = store
        self.runner = runner
        self._events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._server = ZmqServer(
            handler=self._dispatch,
            cmd_port=cmd_port,
            pub_port=pub_port,
            host=host,
        )
        self._thread: threading.Thread | None = None
        self._startup_error: Exception | None = None

    def start(self) -> None:
        """Start the editor RPC server in a daemon thread."""
        if self._thread is not None:
            return
        self._startup_error = None

        def serve() -> None:
            try:
                self._server.serve_forever()
            except Exception as error:
                self._startup_error = error
                self._server._cleanup()

        thread = threading.Thread(target=serve, daemon=True)
        self._thread = thread
        thread.start()
        deadline = time.monotonic() + 1.5
        while (
            thread.is_alive()
            and not self._server._running
            and self._startup_error is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.005)
        if self._startup_error is not None or not self._server._running:
            error = self._startup_error or RuntimeError("Editor RPC startup timed out")
            self.stop()
            raise OSError(str(error)) from error

    def stop(self) -> None:
        """Stop the editor RPC server."""
        self._server.stop()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def drain_events(self) -> list[dict[str, Any]]:
        """Return queued document-change events."""
        events: list[dict[str, Any]] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events

    def _dispatch(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        result = dispatch(method, params, store=self.store, runner=self.runner)
        event = result.pop("event", None)
        if isinstance(event, dict):
            self._events.put(event)
        return result
