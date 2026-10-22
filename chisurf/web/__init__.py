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
* the **documentation** the help plugin browses: the user-facing ``docs/``
  markdown (getting started, fundamentals, guides, concepts, manual,
  reference) packed under its ``docs/...`` paths by :mod:`chisurf.web.docs`,
  so the page's help lists the same pages the desktop's does;
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

The user's settings survive a reload: what the shell's
:func:`chisurf.emtk.main_app.EmtkShellApp.export_settings` holds -- the plugins
that were open, the ribbon -- plus both dock layouts is kept under one
``localStorage`` key (:data:`SETTINGS_KEY`) and put back at the next boot.
Writes go through a :class:`WebSettingsStore` (localStorage, session-only dict
where there is none), debounced behind the shell's ``settings_sink`` and
flushed when the page goes away.
"""

from __future__ import annotations

import collections
import glob
import json
import logging
import os
import pathlib
import sys
import threading
import time
from typing import Any, Callable, Optional, Sequence

__all__ = [
    "APP",
    "CHIMOL_KEEP",
    "CHISURF_EXCLUDE",
    "DEFAULT_PORT",
    "MMFDB_KEEP",
    "PYODIDE_PACKAGES",
    "PLUGIN_EXCLUDE",
    "SETTINGS_DEBOUNCE_S",
    "SETTINGS_KEY",
    "SETTINGS_VERSION",
    "WHEELS",
    "BusEventSubscriber",
    "WebEventHost",
    "WebSettingsStore",
    "WebSettingsSaver",
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
PYODIDE_PACKAGES = ("numpy", "scipy", "pyyaml", "Pillow", "lzma", "fonttools",
                    "requests", "pyodide-http")

#: Entries of the ``chisurf`` package that stay behind: the Qt GUI shell this
#: page replaces, and the cookiecutter template (no plugin). Everything else
#: ships -- ``emtk``, ``plugins``, ``core``, ``settings``, ``startup``,
#: ``server`` (its state and event bus; its sockets are never touched here),
#: ``macros``, ``history``, ``chiplot``.
CHISURF_EXCLUDE = ("gui",)

#: Plugin directories that stay behind.
PLUGIN_EXCLUDE = ("cookiecutter-chisurf-plugin",)

#: The parts of ``mmfdb`` the page ships: its root re-exports ``config``, which
#: ``chisurf.core.settings`` reads, and the Zenodo deposit path
#: (:mod:`mmfdb.deposit`, what ``chisurf.plugins.core.zenodo_deposit`` drives)
#: with the credential store it reads (``mmfdb.security`` is inert at import:
#: its ``__init__`` is empty and ``credentials.py`` is stdlib-only; the token
#: store itself never runs in a tab -- a token is given or read from the
#: environment). The database layer is never imported.
MMFDB_KEEP = ("__init__.py", "config.py", "deposit", "security")

#: Attributes the shipped (standalone) IMP.bff wheel cannot carry **by
#: design**, which packed sources may still reference. The Pyodide wheel is
#: the IMP-free core: no ``IMP.atom`` (so no PDB/mmCIF via IMP --
#: ``read_structure_table``; chisurf's own reader handles plain PDB and the
#: import site raises a message saying so), no RMF (``RmfStructureWriter``),
#: no tttrlib link (``HmmSurrogate``), and no IMP model/docking engine
#: (``DockingAssembly`` and friends -- the modelling/fret plugin is a desktop
#: plugin). Everything else the packed sources use must be IN the wheel; the
#: web-release test fails on anything missing but undeclared, which is how a
#: stale wheel (no ``FitResidualFunction`` -> PSF fits dead) gets caught.
IMPBFF_STANDALONE_ABSENT = (
    "read_structure_table", "RmfStructureWriter",
    "HmmSurrogate", "hmm_surrogate",
    "DockingAssembly", "DockingParameters", "DockingResult", "DockingStop",
    "LoadedStructure", "create_docking_assembly", "dock_minimize",
    "estimate_docking_errors", "score_assembly",
    "load_structure_with_particles",
)

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
    # The wheel's missing pure-Python submodules ride in the archive under our
    # own namespace; make_app() installs them into the wheel's package at boot.
    compat = _tttrlib_compat_files()
    if not compat:
        print("warning: no tttrlib python submodules found to ship "
              "(ndimage/signal/interpolate/matfile)")
    # The help plugin's documentation: without it the page's help browser has
    # nothing to list (the checkout's docs/ does not exist in a browser tab).
    from chisurf.web.docs import doc_files

    docs = doc_files()
    if not docs:
        print("warning: no documentation found to ship; the page's help "
              "browser will be empty")
    return Bundle(
        app=APP,
        packages=["chisurf"],
        extra_packages=extra,
        extra_files={**compat, **docs},
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


# -- user settings across reloads (localStorage through the js bridge) --------- #

#: The one ``localStorage`` key the page's settings live under (namespaced, versioned).
SETTINGS_KEY = "chisurf.web.settings.v1"

#: The payload format written under :data:`SETTINGS_KEY`; a stored payload of another
#: version is dropped rather than half-understood.
SETTINGS_VERSION = 1

#: Seconds a settings write waits for the next one (the shell's sink fires per
#: plugin open/close; a boot's restore fires them in a burst, and a pagehide flush
#: saves regardless).
SETTINGS_DEBOUNCE_S = 1.5


def _local_storage() -> Any:
    """The browser's ``localStorage``, or ``None`` where there is none.

    ``js`` only exists inside Pyodide; a stripped or privacy-restricted page can
    also lack the storage (or its methods, when cookies are off the page is
    still given ``localStorage`` -- but a hostile embedder may not). ``None``
    means the store falls back to memory: settings last for the session only.
    """
    try:
        from js import localStorage  # noqa: PLC0415 - only exists inside Pyodide
    except Exception:  # noqa: BLE001 - ImportError off the page, FFI errors on a broken one
        return None
    for method in ("getItem", "setItem", "removeItem"):
        if not hasattr(localStorage, method):
            return None
    return localStorage


class WebSettingsStore:
    """One JSON payload of user settings, kept across page reloads.

    ``localStorage`` and not cookies: an origin gets megabytes of it rather
    than a cookie's ~4 KB, it is never sent with a request, and it is read and
    written synchronously right where the shell runs. Cookies would force every
    boot through a server round-trip to learn nothing new.

    The payload is a single namespaced key (``chisurf.web.settings.v1``) holding
    one JSON object -- one write, one read, one key to clear. A quota error
    (``setItem`` raising) degrades to the session: :meth:`set` says ``False``,
    the page keeps running without persistence, and the notice is logged once.
    Without a ``localStorage`` at all (tests, a host that is not a page) a
    plain dict stands in -- same session-only behaviour, no browser needed.
    """

    def __init__(self, storage: Any = None) -> None:
        # ``storage=None`` discovers the browser's storage; anything falsy
        # (``False`` in the tests) forces the session-only fallback.
        self._storage = _local_storage() if storage is None else (storage or None)
        self._fallback: dict[str, str] = {}
        self._warned = False

    @property
    def persistent(self) -> bool:
        """Whether settings survive a reload (a real storage backs the store)."""
        return self._storage is not None

    def get(self, key: str = SETTINGS_KEY) -> Optional[dict]:
        """The stored payload, or ``None``. A corrupt one is dropped, not raised on."""
        if self._storage is None:
            raw = self._fallback.get(str(key))
        else:
            try:
                raw = self._storage.getItem(str(key))
            except Exception:  # noqa: BLE001 - an unreadable storage reads as empty
                _log.exception("reading the stored settings failed")
                return None
        if raw is None:
            return None
        try:
            state = json.loads(str(raw))
        except ValueError:
            # A half-write or a payload of a format this page no longer speaks:
            # drop it and boot fresh, rather than restore from a broken state.
            _log.warning("dropping a corrupt stored settings payload")
            self.delete(key)
            return None
        return state if isinstance(state, dict) else None

    def set(self, key: str = SETTINGS_KEY, payload: Optional[dict] = None) -> bool:
        """Store *payload* (the page's settings, whole); ``False`` when the storage refused."""
        raw = json.dumps(payload if payload is not None else {})
        try:
            if self._storage is None:
                self._fallback[str(key)] = raw
            else:
                self._storage.setItem(str(key), raw)
            return True
        except Exception as exc:  # noqa: BLE001 - QuotaExceededError and friends cross as JsException
            self.failed(exc)
            return False

    def delete(self, key: str = SETTINGS_KEY) -> None:
        """Forget the stored payload (a corrupt one, a *reset*)."""
        self._fallback.pop(str(key), None)
        if self._storage is not None:
            try:
                self._storage.removeItem(str(key))
            except Exception:  # noqa: BLE001 - a storage that refuses writes refuses removals
                _log.exception("removing the stored settings failed")

    def failed(self, exc: Exception) -> None:
        """Say a write was refused, once: settings last for this session only."""
        if not self._warned:
            self._warned = True
            _log.warning(
                "settings are not persisted (%s: %s); they last for this "
                "session only", type(exc).__name__, exc)


def capture_settings(app: Any) -> dict:
    """The payload saved under :data:`SETTINGS_KEY`: the shell's own settings
    (the open plugins, the ribbon) plus both dock layouts."""
    return {
        "version": SETTINGS_VERSION,
        "saved_at": round(time.time(), 3),
        "shell": app.export_settings(),
        "docks": {
            name: docks.state()
            for name, docks in dict(getattr(app, "native_layouts", {})).items()
        },
    }


def apply_settings(app: Any, saved: dict) -> None:
    """Put a stored payload back: the dock layouts first, then the shell's settings.

    That is the order the desktop restores in (a layout's places exist before
    :meth:`restore_settings` reopens the plugins that go in them). Anything
    malformed is skipped, never raised on -- a bad payload must not keep the
    page from booting.
    """
    if not isinstance(saved, dict):
        return
    docks = saved.get("docks")
    if isinstance(docks, dict):
        for name, layout in dict(getattr(app, "native_layouts", {})).items():
            state = docks.get(name)
            if not isinstance(state, dict):
                continue
            try:
                layout.restore(state)
            except Exception:  # noqa: BLE001 - one bad layout must not stop the boot
                _log.exception("restoring the %s dock layout failed", name)
    shell = saved.get("shell")
    if isinstance(shell, dict):
        try:
            app.restore_settings(shell)
        except Exception:  # noqa: BLE001 - the page boots without its old settings
            _log.exception("restoring the stored settings failed")


class WebSettingsSaver:
    """Writes the shell's settings through a :class:`WebSettingsStore`.

    As the shell's ``settings_sink`` it saves debounced (:data:`SETTINGS_DEBOUNCE_S`):
    plugin opens come in bursts (a restore opens several). On the page a timer is
    JavaScript's ``setTimeout`` -- Pyodide has no thread to sleep on --; off the
    page a :class:`threading.Timer` stands in. :meth:`flush` saves right now;
    the page's ``pagehide`` and ``visibilitychange`` (hidden) call it, because
    ``beforeunload`` is unreliable and a tab killed without it would lose the
    last debounce window.
    """

    def __init__(self, app: Any, store: WebSettingsStore,
                 debounce: float = SETTINGS_DEBOUNCE_S) -> None:
        self.app = app
        self.store = store
        self.debounce = float(debounce)
        #: Successful and refused writes (tests and diagnostics).
        self.written = 0
        self.refused = 0
        self._timer: Any = None
        self._proxy: Any = None
        self._listeners: list[Any] = []

    def __call__(self, state: dict) -> None:
        """The shell's ``settings_sink``: the shape changed, schedule a save."""
        self.schedule()

    # -- scheduling --------------------------------------------------------- #
    def schedule(self) -> None:
        """Save *debounce* seconds from now; a change in the window replaces the wait."""
        self.cancel()
        timer = self._browser_timer(int(self.debounce * 1000))
        if timer is not None:
            self._timer = timer
            return
        try:
            timer = threading.Timer(self.debounce, self.flush)
            timer.daemon = True
            timer.start()
        except Exception:  # noqa: BLE001 - Pyodide: no threads; save right away
            self.flush()
            return
        self._timer = timer

    def _browser_timer(self, delay_ms: int) -> Any:
        """A ``setTimeout`` id on the page, ``None`` off it (or on a broken bridge)."""
        try:
            from js import window  # noqa: PLC0415 - only exists inside Pyodide
            from pyodide.ffi import create_proxy  # noqa: PLC0415
        except Exception:  # noqa: BLE001 - not a page
            return None
        try:
            if self._proxy is None:
                # The proxy is held on ``self``: a collected one would take the
                # callback's target with it and the timer would never fire.
                self._proxy = create_proxy(self.flush)
            return window.setTimeout(self._proxy, delay_ms)
        except Exception:  # noqa: BLE001 - a broken bridge falls back to the thread timer
            return None

    def cancel(self) -> None:
        """Drop a pending save."""
        timer, self._timer = self._timer, None
        if timer is None:
            return
        try:
            if hasattr(timer, "cancel"):  # a threading.Timer
                timer.cancel()
            else:  # a setTimeout id
                from js import window  # noqa: PLC0415

                window.clearTimeout(timer)
        except Exception:  # noqa: BLE001 - cancelling is best-effort
            pass

    # -- saving -------------------------------------------------------------- #
    def flush(self, *args: Any) -> bool:
        """Write the payload now (the pagehide shape). ``True`` when written."""
        self.cancel()
        if self.app is None:
            return False
        try:
            payload = capture_settings(self.app)
        except Exception:  # noqa: BLE001 - a half-built shell must not break the save
            _log.exception("collecting the shell's settings failed")
            return False
        if self.store.set(SETTINGS_KEY, payload):
            self.written += 1
            return True
        self.refused += 1
        return False

    def listen_to_page(self) -> bool:
        """Flush when the page goes away: ``pagehide`` and a ``visibilitychange``
        to hidden. ``False`` off a page (nothing to listen to)."""
        try:
            from js import document, window  # noqa: PLC0415 - only inside Pyodide
            from pyodide.ffi import create_proxy  # noqa: PLC0415
        except Exception:  # noqa: BLE001 - not a page
            return False

        def on_visibility(event: Any = None) -> None:
            if str(getattr(document, "visibilityState", "") or "") == "hidden":
                self.flush()

        for target, name, callback in (
            (window, "pagehide", self.flush),
            (document, "visibilitychange", on_visibility),
        ):
            try:
                proxy = create_proxy(callback)
                self._listeners.append(proxy)  # held: a collected proxy stops listening
                target.addEventListener(name, proxy)
            except Exception:  # noqa: BLE001 - one listener less still leaves the flush debounced
                _log.exception("listening for %s failed", name)
        return True


def make_app() -> Any:
    """The page's factory: the emtk shell over the socket-free session, its
    settings kept across reloads in ``localStorage``.

    A stored payload (:data:`SETTINGS_KEY`, written by the shell's
    ``settings_sink`` through a :class:`WebSettingsSaver`) is put back at boot:
    the dock layouts, then the plugins that were open and the ribbon
    (:meth:`EmtkShellApp.restore_settings`). Without one -- a first visit, a
    cleared storage, a corrupt payload -- the page boots fresh, as it always
    did. There is no splash and no update check, and the browser tab is the
    window.
    """
    _install_tttrlib_python_modules()
    try:
        # ``requests`` (the Zenodo client's transport) has no sockets in a
        # tab; pyodide-http routes it over fetch. Without the patch the page
        # still boots -- only a deposit upload would fail.
        import importlib  # noqa: PLC0415

        importlib.import_module("pyodide_http").patch_all()
    except Exception:  # pragma: no cover - depends on the loaded package set
        pass
    from chisurf.emtk.main_app import EmtkShellApp

    store = WebSettingsStore()
    saved = store.get(SETTINGS_KEY) or {}
    saver = WebSettingsSaver(None, store)
    app = EmtkShellApp(
        session_factory=start_web_session, post_show=False, settings_sink=saver
    )
    saver.app = app
    if saved:
        apply_settings(app, saved)
    saver.listen_to_page()
    return app


#: Pure-Python ``tttrlib`` submodules the Pyodide wheel does not carry (it ships
#: only the compiled extension and ``pipeline.py``). They are copied from the
#: local installation into the archive under our own namespace (no package
#: shadowing) and :func:`_install_tttrlib_python_modules` writes them into the
#: wheel's package directory at page boot, before the shell imports.
TTTRLIB_PYTHON_MODULES = ("ndimage.py", "signal.py", "interpolate.py", "matfile.py")


def _tttrlib_compat_files() -> dict:
    """The missing submodules' sources, keyed by their archive path.

    The wheel is read first: the rebuilt Pyodide wheels ship the pure-Python
    submodules themselves, and a build machine that has no native ``tttrlib``
    (the CI's pixi environment) still finds them. A native install is the
    fallback for wheels that ship the extension only.
    """
    files = {}
    wheel = find_wheel("tttrlib")
    if wheel is not None:
        import zipfile

        with zipfile.ZipFile(wheel) as archive:
            for name in TTTRLIB_PYTHON_MODULES:
                try:
                    files[f"chisurf/web/_tttrlib_compat/{name}"] = archive.read(
                        f"tttrlib/{name}")
                except KeyError:
                    pass
    if not files:
        import tttrlib

        if tttrlib.__file__ is None:  # a namespace-only install has no sources
            return files
        root = pathlib.Path(tttrlib.__file__).parent
        for name in TTTRLIB_PYTHON_MODULES:
            path = root / name
            if path.is_file():
                files[f"chisurf/web/_tttrlib_compat/{name}"] = path.read_bytes()
    return files


def _install_tttrlib_python_modules() -> None:
    """Give the in-browser ``tttrlib`` its pure-Python submodules.

    The Pyodide wheel ships only the compiled extension; ``chisurf.core`` and
    the burst plugins import ``tttrlib.ndimage`` and friends at module level.
    The archive carries the files under ``chisurf/web/_tttrlib_compat/``; write
    them next to the wheel's ``tttrlib/__init__.py``, which is exactly where a
    full install has them.
    """
    import importlib.util

    compat = pathlib.Path(__file__).parent / "_tttrlib_compat"
    if not compat.is_dir():
        return
    import tttrlib

    root = pathlib.Path(tttrlib.__file__).parent
    written = []
    for name in TTTRLIB_PYTHON_MODULES:
        module = name[:-3]
        if importlib.util.find_spec(f"tttrlib.{module}") is not None:
            continue  # a full install: nothing to add
        source = compat / name
        if source.is_file():
            (root / name).write_bytes(source.read_bytes())
            written.append(module)
    if written:
        import importlib

        importlib.invalidate_caches()


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
