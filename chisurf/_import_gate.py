"""One thread at a time imports a module for the first time.

CPython guards each module's first import with a lock of its own, and a submodule's import takes
the submodule's lock *before* its package's (it imports the parent while holding the child), while a
package's ``__init__`` takes them the other way round when it imports its submodules. Two threads
first-importing into the same package can therefore wait on each other, and one dies with::

    _frozen_importlib._DeadlockError: deadlock detected by _ModuleLock('chisurf.server')

The emtk shell does that by design: the session starts on a worker, hosted plugins are built on
workers (:class:`chisurf.emtk.background_build.BackgroundBuild`), the post-show update check
imports the updater on one, and the frame loop imports lazily on the main thread all the while.
Ordering imports at each call site closes one instance at a time and cannot be kept up.

:func:`install` closes the class: every *first* import -- the only imports that take module locks
-- runs under one re-entrant gate, taken before any module lock. A thread that has the gate imports
whatever its module needs (nested imports re-enter); another thread that needs a module nobody has
loaded yet waits until the first thread's outermost import is complete, and then finds the module
loaded. A module already in ``sys.modules`` is returned without the gate, so the frame loop never
waits on a worker for something it has.

The gate sits on :func:`importlib._bootstrap._find_and_load`, the one function every first import
goes through: the ``import`` statement, :func:`importlib.import_module`, ``__import__`` and the C
API (Cython modules included) all reach it by name, and it is entered *before* the module lock.

Rule that follows: a module's top-level code never waits for another thread (joins it, waits on
its event or a blocking call into it). That thread may need a first import, and the gate is held
until the module is executed. It was already a deadlock without the gate whenever the other thread
imported the same package.
"""

from __future__ import annotations

import _frozen_importlib as _bootstrap
import _thread
import sys
import threading
import time

#: How long a thread waits for the gate before it says, once, who holds it (it keeps waiting).
SLOW_WAIT_S = 10.0

_GATE = _thread.RLock()
#: ``(thread name, module)`` of the outermost first import under way; for the slow-wait message.
_holder: tuple[str, str] | None = None
_depth = 0
_original = None
_MISSING = object()
#: ``(ms, module, holder)`` for each time the main thread waited for the gate (newest last).
_main_waits: list[tuple[float, str, tuple[str, str] | None]] = []
_MAIN_WAITS_KEPT = 1000


def _loaded(name: str) -> bool:
    """Whether *name* is in ``sys.modules`` and done initialising (CPython's own fast-path test)."""
    module = sys.modules.get(name, _MISSING)
    if module is _MISSING or module is None:
        return False
    return not getattr(getattr(module, "__spec__", None), "_initializing", False)


def _acquire(name: str) -> None:
    """Take the gate; after :data:`SLOW_WAIT_S` say once which import holds it, then keep waiting.

    A wait of the main thread is recorded (:func:`main_thread_waits`): it is a frame that paid for
    a worker's import, which a module the frame imports lazily can avoid by being imported first.
    """
    if _GATE.acquire(False):
        return
    holder = _holder
    start = time.perf_counter()
    if not _GATE.acquire(True, SLOW_WAIT_S):
        sys.stderr.write(
            f"chisurf import gate: {_thread_name()} has waited {SLOW_WAIT_S:.0f} s to import "
            f"{name!r}; held by {holder[0] if holder else '?'} importing "
            f"{holder[1] if holder else '?'!r}. A module's top-level code is waiting for another "
            "thread.\n"
        )
        _GATE.acquire()
    if threading.current_thread() is threading.main_thread():
        _main_waits.append(((time.perf_counter() - start) * 1000.0, name, holder))
        del _main_waits[:-_MAIN_WAITS_KEPT]


def _thread_name() -> str:
    return threading.current_thread().name


def _gated_find_and_load(name, import_):
    """``_find_and_load`` under the gate (see the module docstring)."""
    global _holder, _depth
    if _loaded(name):
        return _original(name, import_)
    _acquire(name)
    try:
        if _depth == 0:
            _holder = (_thread_name(), name)
        _depth += 1
        try:
            return _original(name, import_)
        finally:
            _depth -= 1
            if _depth == 0:
                _holder = None
    finally:
        _GATE.release()


def install() -> None:
    """Put the gate in front of every first import of this process; a second call does nothing.

    Raises
    ------
    RuntimeError
        When this Python's import system has no ``_find_and_load`` to gate (a CPython change that
        must be looked at, not run past).
    """
    global _original
    if _original is not None:
        return
    found = getattr(_bootstrap, "_find_and_load", None)
    if found is None or not callable(found):
        raise RuntimeError(
            "importlib._bootstrap._find_and_load is gone; chisurf._import_gate cannot serialise "
            "first imports on this Python"
        )
    _original = found
    setattr(_bootstrap, "_find_and_load", _gated_find_and_load)


def installed() -> bool:
    """Whether :func:`install` has put the gate in place."""
    return getattr(_bootstrap, "_find_and_load", None) is _gated_find_and_load


def holder() -> tuple[str, str] | None:
    """``(thread, module)`` of the first import under way, or ``None`` (for tests and diagnostics)."""
    return _holder


def main_thread_waits(clear: bool = False) -> list[tuple[float, str, tuple[str, str] | None]]:
    """Each wait of the main thread for another thread's first import: ``(ms, module, holder)``.

    *holder* is ``(thread, module)`` of the outermost import it waited behind. With *clear* the
    record starts over (the frame-time harness reads it per plugin).
    """
    waits = list(_main_waits)
    if clear:
        _main_waits.clear()
    return waits


__all__ = ["SLOW_WAIT_S", "holder", "install", "installed", "main_thread_waits"]
