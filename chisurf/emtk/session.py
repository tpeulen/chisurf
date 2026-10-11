"""The emtk shell's session: an in-process ChiSurf server, the API facade over it and its event stream.

The shell does not touch fits, datasets or parameters itself. It starts the same
server the Qt shell embeds (:class:`chisurf.server.app.ChiSurfServer`, on a
thread, on ports nobody else listens on), talks to it through
:class:`chisurf.core.api.ChiSurfAPI` in ``server`` mode -- every change is a
JSON-RPC call -- and hears what changed through
:class:`chisurf.core.server_events.ServerEventSubscriber`, which delivers the
server's PUB events on the shell's own thread.

What the server cannot send is something to *draw*: a fit window's pages are
plot objects built over the fit. Because the server runs in this process,
:meth:`ShellSession.presentation_fit` hands the window the fit object for
reading; edits still go through the API.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

_log = logging.getLogger("chisurf.emtk.session")

#: Event topics the shell listens to.
TOPICS = ("fit.", "parameter.", "dataset.", "session.", "project.")
#: How long one RPC may take; a fit runs inside one call.
CALL_TIMEOUT_MS = 600_000


def free_port() -> int:
    """A loopback TCP port nobody listens on right now."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class ShellSession:
    """What the shell's data and fit docks work through.

    Attributes
    ----------
    api : ChiSurfAPI
        The facade every change goes through (``server`` mode).
    events : ServerEventSubscriber
        The server's events, drained by the shell once per frame.
    server : ChiSurfServer or None
        The in-process server (``None`` for a session attached to another process).
    """

    api: Any
    events: Any
    server: Any = None
    client: Any = None
    thread: threading.Thread | None = None
    _published: bool = field(default=False, repr=False)

    def experiments(self) -> dict[str, Any]:
        """The registered experiments (readers and model classes) by name, hidden ones left out."""
        import chisurf

        found = {}
        for experiment in getattr(chisurf, "experiment", {}).values():
            if getattr(experiment, "hidden", False):
                continue
            if not getattr(experiment, "readers", None):
                continue
            found[str(experiment.name)] = experiment
        return found

    def presentation_fit(self, uid: str) -> Any:
        """The fit object with *uid* for a window to draw from (read only), ``None`` when absent."""
        state = getattr(self.server, "state", None)
        for fit in list(getattr(state, "fits", None) or ()):
            if str(getattr(fit, "unique_identifier", "")) == str(uid):
                return fit
        return None

    def close(self) -> None:
        """Stop listening, disconnect and stop the in-process server."""
        try:
            self.events.stop()
        except Exception:  # noqa: BLE001 - closing must reach the server too
            _log.exception("stopping the event subscriber failed")
        if self.client is not None:
            try:
                self.client.close()
            except Exception:  # noqa: BLE001
                _log.exception("closing the RPC client failed")
        if self.server is not None:
            self.server.stop()
            if self.thread is not None:
                self.thread.join(5)
        if self._published:
            import chisurf

            if getattr(chisurf, "__chisurf_rpc_server__", None) is self.server:
                chisurf.__chisurf_rpc_server__ = None
            self._published = False


def start_session(
    *,
    state: Any = None,
    host: str = "127.0.0.1",
    cmd_port: int | None = None,
    pub_port: int | None = None,
    wake: Callable[[], None] | None = None,
    timeout: float = 60.0,
) -> ShellSession:
    """Start an in-process server and connect the shell to it.

    Parameters
    ----------
    state : SessionState, optional
        The session the server owns; by default one sharing the process's
        ``chisurf.fits`` / ``chisurf.imported_datasets`` lists, as the Qt shell's
        embedded server does (plugins that still read those see the same data).
    host : str
        Loopback address.
    cmd_port, pub_port : int, optional
        Ports to bind; free ones by default, so a running ChiSurf is never adopted.
    wake : callable, optional
        Thread-safe callback run when events arrive (the shell's ``request_frame``).
    timeout : float
        Seconds to wait for the server to answer.

    Returns
    -------
    ShellSession
    """
    import chisurf
    from chisurf.core.api import ChiSurfAPI
    from chisurf.core.api._client import ChisurfClient
    from chisurf.core.experiments.bootstrap import ensure_experiments_registered
    from chisurf.core.server_events import ServerEventSubscriber
    from chisurf.server.app import ChiSurfServer
    from chisurf.server.session import SessionState
    from chisurf.server.startup import session_state_from_live_chisurf

    ensure_experiments_registered(allow_widgets=False)
    if state is None:
        state = session_state_from_live_chisurf() or SessionState()
    cmd_port = int(cmd_port or free_port())
    pub_port = int(pub_port or free_port())
    server = ChiSurfServer(host=host, cmd_port=cmd_port, pub_port=pub_port, state=state)
    thread = threading.Thread(
        target=server.serve_forever, name="chisurf-emtk-shell-server", daemon=True
    )
    thread.start()
    # A short-timeout probe: the long-timeout client would wait minutes on a server that failed to bind.
    probe = ChisurfClient(cmd_port=cmd_port, pub_port=pub_port, host=host, timeout_ms=1000)
    probe.connect()
    end = time.monotonic() + timeout
    try:
        while True:
            try:
                if probe.call("meta.ping", {}).get("ok"):
                    break
            except Exception:  # noqa: BLE001 - the socket is bound a moment after the thread starts
                pass
            if time.monotonic() > end or not thread.is_alive():
                server.stop()
                raise RuntimeError(f"the ChiSurf server on port {cmd_port} did not answer")
            time.sleep(0.05)
    finally:
        probe.close()
    client = ChisurfClient(
        cmd_port=cmd_port, pub_port=pub_port, host=host, timeout_ms=CALL_TIMEOUT_MS
    )
    client.connect()
    events = ServerEventSubscriber(pub_port, host, wake=wake, topics=TOPICS).start()
    api = ChiSurfAPI(client=client, mode="server", state=server.state)
    session = ShellSession(api=api, events=events, server=server, client=client, thread=thread)
    # A fit's own update publishes ``fit.updated`` on the embedded server's bus
    # (``chisurf.server.startup.get_shared_event_bus``); that bus is this server's.
    if getattr(chisurf, "__chisurf_rpc_server__", None) is None:
        chisurf.__chisurf_rpc_server__ = server
        session._published = True
    _log.info("session server on %s:%s (events on %s)", host, cmd_port, pub_port)
    return session


__all__ = ["ShellSession", "TOPICS", "free_port", "start_session"]
