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

The server, the API facade and the event subscriber are imported *here*, at module level, not
by the session's worker. The shell runs :func:`start_session` on a worker thread while its main
thread goes on (the Log dock's call monitor imports ``chisurf.server.dispatcher``); two threads
importing the package ``chisurf.server`` for the first time take CPython's per-module import
locks in opposite orders and one of them dies with ``_DeadlockError``. Whoever names
``start_session`` has imported this module, so the package is complete before any worker starts.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# Imported before any thread starts (see the module docstring); never move these into a stage.
import chisurf.core.api
import chisurf.core.api._client
import chisurf.core.server_events
import chisurf.server.app
import chisurf.server.session
import chisurf.server.startup  # noqa: F401
import chisurf.startup.services

_log = logging.getLogger("chisurf.emtk.session")

#: Event topics the shell listens to.
TOPICS = ("fit.", "parameter.", "model.", "dataset.", "session.", "project.")
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

    def experiment(self, name: str) -> Any:
        """The registered experiment *name*, hidden ones (the global fit's) included."""
        import chisurf

        for experiment in getattr(chisurf, "experiment", {}).values():
            if str(getattr(experiment, "name", "")) == str(name):
                return experiment
        return None

    def ensure_global_dataset(self) -> bool:
        """Add the global-fit pseudo-dataset the Qt session always holds, unless it is there.

        A global fit is made on it (the *Global* experiment's models link the fits of
        other datasets). Returns whether one was added.
        """
        from chisurf.server.services.datasets import _is_global_fit_dataset

        # The API lists datasets as records (dicts): the check reads their name, as it reads a dataset's.
        def is_global(record: Any) -> bool:
            if isinstance(record, dict):
                from types import SimpleNamespace

                record = SimpleNamespace(name=record.get("name", ""))
            return _is_global_fit_dataset(record)

        if any(is_global(d) for d in (self.api.list_datasets() or [])):
            return False
        experiment = self.experiment("Global")
        readers = list(getattr(experiment, "readers", None) or [])
        if not readers:
            _log.warning("no global-fit reader is registered; global fits are unavailable")
            return False
        result = self.api.load_dataset(experiment_reader=readers[0], name="Global Dataset")
        return bool(isinstance(result, dict) and result.get("ok", True))

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
    on_stage: Callable[[dict[str, Any]], None] | None = None,
) -> ShellSession:
    """Start an in-process server and connect the shell to it.

    The work is the ``surface="emtk"``, ``phase="splash"`` stage set declared in
    ``chisurf/startup/services.d/25_emtk_splash.json`` (the stage functions below), run by
    the same :class:`~chisurf.startup.services.AppStartupServiceManager` that runs the Qt
    window's splash stages; the shell's splash shows each stage's label and progress.

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
    on_stage : callable, optional
        Called (on the calling thread) as each stage starts, with the stage's payload
        (``id``, ``label``, ``progress``, ``surface``, ``phase``).

    Returns
    -------
    ShellSession
    """
    from chisurf.startup.services import AppStartupServiceManager

    metadata: dict[str, Any] = {
        "state": state,
        "host": host,
        "cmd_port": cmd_port,
        "pub_port": pub_port,
        "wake": wake,
        "timeout": timeout,
    }
    manager = AppStartupServiceManager()
    try:
        manager.start(surface="emtk", phase="splash", on_stage_start=on_stage, metadata=metadata)
    except BaseException:
        session = metadata.get("session")
        if session is not None:
            session.close()
        elif metadata.get("server") is not None:
            metadata["server"].stop()
        raise
    session = metadata.get("session")
    if session is None:
        raise RuntimeError("the shell's startup stages made no session")
    return session


# -- the startup stages (``services.d/25_emtk_splash.json``) ---------------------------------- #
# Each takes the manager's shared context; the options and what the stages make travel in
# ``context.metadata``. They run on the shell's session worker, never on its frame loop.


def stage_experiments(context: Any) -> None:
    """Register the experiments (readers and model classes) without their Qt widgets."""
    from chisurf.core.experiments.bootstrap import ensure_experiments_registered

    ensure_experiments_registered(allow_widgets=False)


def stage_server(context: Any) -> None:
    """Make the server (its services and the plugins' RPC services), serve it on a thread, wait for it."""
    from chisurf.core.api._client import ChisurfClient
    from chisurf.server.app import ChiSurfServer
    from chisurf.server.session import SessionState
    from chisurf.server.startup import session_state_from_live_chisurf

    options = context.metadata
    host = str(options.get("host") or "127.0.0.1")
    state = options.get("state")
    if state is None:
        state = session_state_from_live_chisurf() or SessionState()
    cmd_port = int(options.get("cmd_port") or free_port())
    pub_port = int(options.get("pub_port") or free_port())
    server = ChiSurfServer(host=host, cmd_port=cmd_port, pub_port=pub_port, state=state)
    thread = threading.Thread(
        target=server.serve_forever, name="chisurf-emtk-shell-server", daemon=True
    )
    thread.start()
    options.update(server=server, thread=thread, host=host, cmd_port=cmd_port, pub_port=pub_port)
    # A short-timeout probe: the long-timeout client would wait minutes on a server that failed to bind.
    probe = ChisurfClient(cmd_port=cmd_port, pub_port=pub_port, host=host, timeout_ms=1000)
    probe.connect()
    end = time.monotonic() + float(options.get("timeout") or 60.0)
    try:
        while True:
            try:
                if probe.call("meta.ping", {}).get("ok"):
                    break
            except Exception:  # noqa: BLE001 - the socket is bound a moment after the thread starts
                pass
            if time.monotonic() > end or not thread.is_alive():
                raise RuntimeError(f"the ChiSurf server on port {cmd_port} did not answer")
            time.sleep(0.05)
    finally:
        probe.close()


def stage_connect(context: Any) -> None:
    """Connect the API facade and subscribe to the server's events."""
    import chisurf
    from chisurf.core.api import ChiSurfAPI
    from chisurf.core.api._client import ChisurfClient
    from chisurf.core.server_events import ServerEventSubscriber

    options = context.metadata
    host, cmd_port, pub_port = options["host"], options["cmd_port"], options["pub_port"]
    server = options["server"]
    client = ChisurfClient(
        cmd_port=cmd_port, pub_port=pub_port, host=host, timeout_ms=CALL_TIMEOUT_MS
    )
    client.connect()
    events = ServerEventSubscriber(pub_port, host, wake=options.get("wake"), topics=TOPICS).start()
    api = ChiSurfAPI(client=client, mode="server", state=server.state)
    session = ShellSession(
        api=api, events=events, server=server, client=client, thread=options["thread"]
    )
    # A fit's own update publishes ``fit.updated`` on the embedded server's bus
    # (``chisurf.server.startup.get_shared_event_bus``); that bus is this server's.
    if getattr(chisurf, "__chisurf_rpc_server__", None) is None:
        chisurf.__chisurf_rpc_server__ = server
        session._published = True
    options["session"] = session
    _log.info("session server on %s:%s (events on %s)", host, cmd_port, pub_port)


def stage_session(context: Any) -> None:
    """Add the global-fit dataset the session always holds (off the frame loop)."""
    session = context.metadata["session"]
    try:
        session.ensure_global_dataset()
    except Exception:  # noqa: BLE001 - local fits still work without it; the shell retries on adopt
        _log.exception("adding the global-fit dataset failed")


__all__ = [
    "ShellSession",
    "TOPICS",
    "free_port",
    "stage_connect",
    "stage_experiments",
    "stage_server",
    "stage_session",
    "start_session",
]
