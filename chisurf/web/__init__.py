"""ChiSurf in a browser tab: ``python -m chisurf.web``.

Builds the emtk shell (:func:`chisurf.emtk.main_app.EmtkShellApp`) into a page --
Pyodide runs it, the browser's WebGPU draws it -- and serves it::

    python -m chisurf.web                       # build, serve on :8790, open a tab
    python -m chisurf.web --no-open --port 8800
    python -m chisurf.web --wheels ~/wheels/imp-*.whl   # one more local wheel
    python -m chisurf.web --build-only --out site/      # a static site to host

Every :mod:`emtk.web.serve` option works; this only presets the bundle.

What the page carries
---------------------
* **chisurf** (without the Qt GUI package) and **emtk**, as the archive: the
  whole package tree minus ``chisurf/gui`` (the Qt shell this one replaces) and
  the plugin template, so the shell's manifests, the plugins' native entrypoint
  modules, the settings, the startup stages, the session's server-side state and
  the macros all come along (:data:`CHISURF_EXCLUDE`);
* **mmfdb**'s runtime config, which ``chisurf.settings`` reads, and **chimol**'s
  readers (:data:`MMFDB_KEEP`, :data:`CHIMOL_KEEP`);
* from the Pyodide distribution: numpy, scipy, PyYAML, Pillow and ``lzma``
  (:data:`PYODIDE_PACKAGES`);
* **tttrlib**'s Pyodide wheel -- every data source is a ``tttrlib.DataStore``;
* **IMP.bff**'s Pyodide wheel (the IMP-free core) -- the port runtime behind
  chisurf's fitting parameters. Without it the page boots anyway and the
  affected features say why they are off;
* any further ``--wheels``.

Which plugins
-------------
Every plugin directory ships whose ``entrypoints.emtk`` factory imports. That is
the gate ``test/native_emtk/test_emtk_plugins_are_qt_free.py`` enforces (a
blocked-Qt import of every declared native factory), so the page's plugin set is
exactly the shell's menu. Plugins with only a Qt ``gui`` entrypoint are not
offered by the shell and their modules just ride along unimported; a plugin
whose *runtime* work needs what a browser has no sockets for fails when opened,
as one failed job, with the shell still up. Cookiecutter's template directory is
the one tree left out.

The session, without sockets
----------------------------
The desktop shell's session embeds a real TCP server (ZMQ REQ/REP plus PUB on
loopback ports); a browser page cannot bind sockets. :func:`make_app` therefore
starts the shell with :func:`start_web_session`, which runs the same startup
stages over an in-process :class:`~chisurf.core.api.ChiSurfAPI` in ``local``
mode: the state aliases the live ``chisurf.fits`` / ``chisurf.imported_datasets``
lists as on the desktop, and a :class:`WebEventHost` owns an
:class:`~chisurf.server.eventbus.InProcessEventBus` published on by
``fit.update()`` and friends -- the same shared-bus events the desktop's PUB
socket carries, drained per frame by a :class:`BusEventSubscriber` with the
subscriber interface the shell already drives. No wheel, thread or package is
added for this; the desktop shell is untouched.

The wheels are found by :func:`find_wheel` (:data:`WHEELS`): an environment
variable naming the file, else the newest match under a checkout's
``dist/pyodide``.

Data comes in by dropping a file (a ``.bur``, a ``.csv``, a ``.ptu``) or a whole
folder on the view, or through *Mount folder...* (Chrome); a save is a download.
"""

from __future__ import annotations

import collections
import glob
import logging
import os
import pathlib
import sys
import threading
from typing import Any, Callable, Optional, Sequence

__all__ = [
    "APP",
    "CHIMOL_KEEP",
    "CHISURF_EXCLUDE",
    "DEFAULT_PORT",
    "MMFDB_KEEP",
    "PYODIDE_PACKAGES",
    "PLUGIN_EXCLUDE",
    "WHEELS",
    "BusEventSubscriber",
    "WebEventHost",
    "bundle",
    "find_wheel",
    "main",
    "make_app",
    "start_web_session",
]

_log = logging.getLogger("chisurf.web")

#: The factory the page mounts: the emtk shell over the socket-free session.
APP = "chisurf.web:make_app"

#: Not emtk's 8788 (other emtk pages), not ndX's 8795 and not 8765
#: (ChiSurf's command port).
DEFAULT_PORT = 8790

#: Loaded from the Pyodide distribution (numpy and Pillow come anyway).
PYODIDE_PACKAGES = ("numpy", "scipy", "pyyaml", "Pillow", "lzma")

#: Entries of the ``chisurf`` package that stay behind: the Qt GUI shell this
#: page replaces, and the cookiecutter template (no plugin). Everything else
#: ships -- ``emtk``, ``plugins``, ``core``, ``settings``, ``startup``,
#: ``server`` (its state and event bus; its sockets are never touched here),
#: ``macros``, ``history``, ``chiplot``.
CHISURF_EXCLUDE = ("gui",)

#: Plugin directories that stay behind.
PLUGIN_EXCLUDE = ("cookiecutter-chisurf-plugin",)

#: The parts of ``mmfdb`` the page ships: its root re-exports ``config``, which
#: ``chisurf.core.settings`` reads; the database layer is never imported.
MMFDB_KEEP = ("__init__.py", "config.py")

#: The parts of ``chimol`` the page ships: its readers, which ``chisurf.core``
#: imports; the viewer does not come.
CHIMOL_KEEP = ("__init__.py", "io")

#: The Pyodide wheels a page needs, by name: ``(environment variable, globs,
#: required)``. The variable names the file; otherwise the newest match of the
#: globs (a checkout's ``dist/pyodide``, where ``pyodide build`` puts it) wins.
#: A missing required wheel stops the build; a missing optional one is said.
WHEELS = {
    "tttrlib": ("CHISURF_WEB_TTTRLIB_WHEEL", (
        "~/dev/worktrees/tttrlib-pyodide/dist/pyodide/tttrlib-*-pyodide_*_wasm32.whl",
        "~/dev/tttrlib/dist/pyodide/tttrlib-*-pyodide_*_wasm32.whl",
    ), True),
    "IMP.bff": ("CHISURF_WEB_IMPBFF_WHEEL", (
        "~/dev/worktrees/imp.bff-pyodide/dist/pyodide/imp_bff-*-pyodide_*_wasm32.whl",
        "~/dev/imp.bff/dist/pyodide/imp_bff-*-pyodide_*_wasm32.whl",
    ), False),
}


def find_wheel(name: str) -> Optional[pathlib.Path]:
    """The Pyodide wheel of *name* (a key of :data:`WHEELS`), or ``None``.

    Raises
    ------
    FileNotFoundError
        If the environment variable names a file that is not there, or a
        required wheel (tttrlib: a page without it cannot open a single
        tttr file) is not found.
    """
    variable, patterns, required = WHEELS[name]
    named = os.environ.get(variable)
    if named:
        path = pathlib.Path(os.path.expanduser(named))
        if not path.is_file():
            raise FileNotFoundError(f"${variable}={named}: no such file")
        return path
    for pattern in patterns:
        matches = sorted(glob.glob(os.path.expanduser(pattern)), key=os.path.getmtime)
        if matches:
            return pathlib.Path(matches[-1])
    if required:
        raise FileNotFoundError(
            f"no {name} wheel for Pyodide found; build one (pyodide build in a {name} "
            f"checkout) and point ${variable} at it, or pass --no-{name.lower().replace('.', '')}-wheel "
            "with --wheels PATH")
    return None


def _package_dir(name: str) -> Optional[pathlib.Path]:
    """The directory of the regular package *name*, or ``None`` if it is not installed.

    Raises
    ------
    FileNotFoundError
        If *name* resolves to a namespace package: a stray directory of that
        name (``~/chisurf`` when run from ``~``; ``python -m`` puts the working
        directory first on ``sys.path``) shadowing the real one. Packing it
        would ship an empty package and the page would fail at import.
    """
    import importlib.util

    spec = importlib.util.find_spec(name)
    if spec is None:
        return None
    if not spec.origin or not spec.origin.endswith("__init__.py"):
        where = ", ".join(map(str, spec.submodule_search_locations or []))
        raise FileNotFoundError(
            f"{name!r} resolves to a namespace package ({where}), a directory that "
            f"shadows the installed {name}; run from another directory")
    return pathlib.Path(spec.origin).resolve().parent


def _exclude_entries(name: str, dropped: Sequence[str]) -> list[str]:
    """Archive prefixes that leave out *dropped* of package *name* (a directory
    entry is excluded as ``name/entry/``, a file as ``name/entry``)."""
    root = _package_dir(name)
    if root is None:
        return []
    out = []
    for entry in sorted(root.iterdir()):
        if entry.name not in dropped or entry.name == "__pycache__":
            continue
        out.append(f"{name}/{entry.name}/" if entry.is_dir() else f"{name}/{entry.name}")
    return out


def _exclude_all_but(name: str, keep: Sequence[str]) -> list[str]:
    """Archive prefixes that leave only *keep* of package *name*."""
    root = _package_dir(name)
    if root is None:
        return []
    out = []
    for entry in sorted(root.iterdir()):
        if entry.name in keep or entry.name == "__pycache__":
            continue
        out.append(f"{name}/{entry.name}/" if entry.is_dir() else f"{name}/{entry.name}")
    return out


def bundle(tttrlib_wheel: bool = True, impbff_wheel: bool = True):
    """The :class:`emtk.web.serve.Bundle` for ChiSurf: app, dependencies, wheels."""
    from emtk.web.serve import DEFAULT_PYODIDE_PACKAGES, Bundle

    exclude = _exclude_entries("chisurf", (*CHISURF_EXCLUDE, *PLUGIN_EXCLUDE))
    exclude += [f"chisurf/plugins/{name}/" for name in PLUGIN_EXCLUDE]
    # The plugins' own test trees (fixtures, baseline renders -- the chimol
    # baselines alone are ~20 MB) ride on no page: no plugin's runtime code
    # imports them (grep-checked), the demos carry their own generators.
    plugins_root = _package_dir("chisurf")
    if plugins_root is not None:
        plugins_root = plugins_root / "plugins"
        for tree in sorted(plugins_root.rglob("*")):
            if tree.is_dir() and tree.name in ("test", "tests"):
                exclude.append("chisurf/" + tree.relative_to(plugins_root.parent).as_posix() + "/")
    extra, exclude_built = [], list(exclude)
    for name, keep in (("mmfdb", MMFDB_KEEP), ("chimol", CHIMOL_KEEP)):
        if _package_dir(name) is not None:
            extra.append(name)
            exclude_built += _exclude_all_but(name, keep)
    pyodide = list(DEFAULT_PYODIDE_PACKAGES)
    pyodide += [p for p in PYODIDE_PACKAGES if p not in pyodide]
    wheels = []
    for name, wanted in (("tttrlib", tttrlib_wheel), ("IMP.bff", impbff_wheel)):
        wheel = find_wheel(name) if wanted else None
        if wheel is not None:
            wheels.append(wheel)
        elif wanted:
            print(f"no {name} wheel for Pyodide found (${WHEELS[name][0]}); "
                  "the page boots without it")
    return Bundle(
        app=APP,
        packages=["chisurf"],
        extra_packages=extra,
        pyodide_packages=pyodide,
        wheels=wheels,
        exclude=tuple(exclude_built),
        title="ChiSurf",
        ready_message="ready -- drop a data file or folder on the view",
    )


# -- the page's session, without sockets -------------------------------------- #

_SHARED_BUS: Any = None
_SHARED_BUS_LOCK = threading.Lock()


def shared_event_bus() -> Any:
    """The page's one event bus, process-wide.

    ``fit.update()`` publishes on the bus of ``chisurf.__chisurf_rpc_server__``
    -- the first session's host -- so a second shell in this process (a probe,
    a test) must subscribe to the *same* bus, not its own, or its events never
    arrive. The desktop's equivalent, the server's PUB socket, is a process
    fixture too.
    """
    global _SHARED_BUS
    if _SHARED_BUS is None:
        from chisurf.server.eventbus import InProcessEventBus

        with _SHARED_BUS_LOCK:
            if _SHARED_BUS is None:
                _SHARED_BUS = InProcessEventBus()
    return _SHARED_BUS


class WebEventHost:
    """Stands in for the desktop session's embedded server, in one process.

    The desktop's :class:`~chisurf.server.app.ChiSurfServer` owns the
    ``SessionState`` the fit windows read and the event bus that
    ``fit.update()`` publishes ``fit.updated`` on
    (:func:`chisurf.server.startup.get_shared_event_bus` reads it from
    ``chisurf.__chisurf_rpc_server__``). Here both live in the page: *state*
    and the process-wide :func:`shared_event_bus`. ``cmd_port``/``pub_port``
    are ``None`` -- the attributes the desktop's
    :class:`~chisurf.emtk.shell_session.ProjectChannel` connects to; the shell
    treats a port-less server like an absent one (the project channel and its
    menus stay off; the console uses the session's own local API).
    ``stop()`` is what
    :meth:`ShellSession.close <chisurf.emtk.session.ShellSession.close>`
    calls; nothing to stop without sockets.
    """

    #: Loopback, as on the desktop; no port is ever bound.
    host = "127.0.0.1"
    #: ``None``: the marker the shell reads to skip its socket channel.
    cmd_port: int | None = None
    pub_port: int | None = None

    def __init__(self, state: Any) -> None:
        self.state = state
        self.event_bus = shared_event_bus()

    def stop(self) -> None:  # noqa: D401 - the server's shape, minus the sockets
        """Nothing to stop: no sockets were bound."""


class BusEventSubscriber:
    """The shared bus's events, queued on publish and dispatched on :meth:`drain`.

    The shell drives its event source through the
    :class:`~chisurf.core.server_events.ServerEventSubscriber` interface --
    :meth:`subscribe`, :attr:`pending`, :meth:`drain`, :meth:`start`,
    :meth:`stop`, a settable ``wake`` -- so this offers the same, fed by an
    in-process bus subscription instead of a ZMQ PUB socket. Payloads are the
    bus's event dicts (``topic`` included), the same shape the PUB socket
    carries.
    """

    def __init__(self, bus: Any, wake: Callable[[], None] | None = None) -> None:
        self.wake = wake
        self._bus = bus
        self._queue: collections.deque[tuple[str, dict[str, Any]]] = collections.deque()
        self._lock = threading.Lock()
        self._callbacks: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        #: How many events the bus delivered (for tests and diagnostics).
        self.received = 0
        self._token = bus.subscribe("*", self._on_event)

    def _on_event(self, event: dict[str, Any]) -> None:
        """Queue one published event (runs on the publishing thread)."""
        topic = str(event.get("topic", ""))
        with self._lock:
            self._queue.append((topic, dict(event)))
            self.received += 1
        if self.wake is not None:
            try:
                self.wake()
            except Exception:  # noqa: BLE001 - a wake hook must not kill the publisher
                _log.exception("event wake callback failed")

    # -- the owner's side (the ServerEventSubscriber interface) -------------- #
    def subscribe(self, prefix: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """Run ``callback(payload)`` in :meth:`drain` for every topic starting with *prefix*."""
        self._callbacks.setdefault(str(prefix).rstrip("*?"), []).append(callback)

    def unsubscribe(self, prefix: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """Forget a callback registered with :meth:`subscribe`."""
        key = str(prefix).rstrip("*?")
        kept = [cb for cb in self._callbacks.get(key, []) if cb is not callback]
        if kept:
            self._callbacks[key] = kept
        else:
            self._callbacks.pop(key, None)

    @property
    def pending(self) -> int:
        """Events received and not yet drained."""
        with self._lock:
            return len(self._queue)

    def drain(self, limit: int | None = None) -> int:
        """Dispatch the queued events, oldest first, on the calling thread.

        Returns
        -------
        int
            How many events were dispatched.
        """
        done = 0
        while limit is None or done < limit:
            with self._lock:
                if not self._queue:
                    break
                topic, payload = self._queue.popleft()
            done += 1
            for prefix, callbacks in list(self._callbacks.items()):
                if not topic.startswith(prefix):
                    continue
                for callback in list(callbacks):
                    try:
                        callback(payload)
                    except Exception:  # noqa: BLE001 - one view failing must not starve the others
                        _log.exception("event callback for %r failed", topic)
        return done

    @property
    def running(self) -> bool:
        """Always true: there is no worker to stop."""
        return True

    def start(self, timeout: float = 5.0) -> "BusEventSubscriber":
        """Nothing to start (the subscription is live); returns ``self``."""
        return self

    def stop(self, timeout: float = 2.0) -> None:
        """Unsubscribe from the bus; queued events stay drainable, as after the
        socket subscriber's stop."""
        try:
            self._bus.unsubscribe(self._token)
        except Exception:  # noqa: BLE001 - closing must not raise
            _log.exception("unsubscribing from the event bus failed")


def start_web_session(
    *,
    wake: Callable[[], None] | None = None,
    on_stage: Callable[[dict[str, Any]], None] | None = None,
    timeout: float = 60.0,
) -> Any:
    """The shell's session for a browser page: local API mode, no sockets.

    The desktop's :func:`chisurf.emtk.session.start_session` embeds a TCP
    server and talks to it over loopback ZMQ; a page cannot bind sockets. This
    runs the same stages against objects in this process:

    1. register the experiments (readers and model classes) without Qt;
    2. make the session state over the live ``chisurf.fits`` /
       ``chisurf.imported_datasets`` lists and an in-process
       :class:`WebEventHost` published on by ``fit.update()`` and friends;
    3. connect a :class:`~chisurf.core.api.ChiSurfAPI` in ``local`` mode and a
       :class:`BusEventSubscriber` on the host's bus;
    4. add the global-fit dataset, as the desktop's last stage does.

    Called by the shell's worker with ``wake`` (the frame request) and
    ``on_stage`` (the splash/status reporter), exactly as
    ``session_factory`` promises.

    Returns
    -------
    chisurf.emtk.session.ShellSession
        ``api`` in ``local`` mode, ``events`` on the shared bus, ``server`` the
        :class:`WebEventHost` (``presentation_fit`` reads its ``state``),
        ``client`` and ``thread`` ``None``.
    """
    import time as _time

    stage = on_stage or (lambda payload: None)

    def _stage(stage_id: str, label: str, progress: float) -> None:
        stage({"id": stage_id, "label": label, "progress": progress,
               "surface": "emtk", "phase": "web"})

    started = _time.monotonic()
    _stage("experiments", "Registering the experiments", 0.05)
    from chisurf.core.experiments.bootstrap import ensure_experiments_registered

    ensure_experiments_registered()

    _stage("session", "Starting the local session", 0.3)
    import chisurf
    from chisurf.core.api import ChiSurfAPI
    from chisurf.emtk.session import ShellSession
    from chisurf.server.startup import session_state_from_live_chisurf

    state = session_state_from_live_chisurf()
    if state is None:
        from chisurf.server.session import SessionState

        state = SessionState()
    host = WebEventHost(state)
    events = BusEventSubscriber(host.event_bus, wake=wake)
    api = ChiSurfAPI(mode="local", state=state)
    session = ShellSession(api=api, events=events, server=host, client=None, thread=None)
    # fit.update() and friends publish on this bus through
    # get_shared_event_bus(), which reads __chisurf_rpc_server__.event_bus --
    # so the page's host is the shared bus's owner, as the desktop's server is.
    if getattr(chisurf, "__chisurf_rpc_server__", None) is None:
        chisurf.__chisurf_rpc_server__ = host
        session._published = True

    _stage("dataset", "Adding the global-fit dataset", 0.8)
    try:
        session.ensure_global_dataset()
    except Exception:  # noqa: BLE001 - local fits still work without it; the shell retries on adopt
        _log.exception("adding the global-fit dataset failed")
    _stage("done", "Ready", 1.0)
    _log.info("web session ready in %.2fs (local API mode, no sockets)",
              _time.monotonic() - started)
    return session


def make_app() -> Any:
    """The page's factory: the emtk shell over the socket-free session.

    Unlike the desktop's :func:`chisurf.emtk.main_app.make_app`, nothing is
    persisted (no stored layout is read, none is written back) and there is no
    splash and no update check -- a page boots fresh every time, and the
    browser tab is its own window.
    """
    from chisurf.emtk.main_app import EmtkShellApp

    return EmtkShellApp(session_factory=start_web_session, post_show=False)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m chisurf.web [emtk.web.serve options] [--no-tttrlib-wheel]
    [--no-impbff-wheel]``."""
    from emtk.web import serve

    argv = list(sys.argv[1:] if argv is None else argv)
    flags = {"tttrlib": "--no-tttrlib-wheel", "impbff": "--no-impbff-wheel"}
    off = {key for key, flag in flags.items() if flag in argv}
    argv = [a for a in argv if a not in flags.values()]
    if not any(a == "--port" or a.startswith("--port=") for a in argv):
        argv += ["--port", str(DEFAULT_PORT)]
    return serve.main(argv, base=bundle(tttrlib_wheel="tttrlib" not in off,
                                        impbff_wheel="impbff" not in off))


if __name__ == "__main__":  # pragma: no cover - a dev server
    sys.exit(main())
