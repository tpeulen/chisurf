"""Make a hub's embedded tools on a worker thread, so the hub's first frame does not pay for them.

A hub (tool rail, calculator list, settings destinations) shows one embedded tool when it opens. Importing and
constructing that tool costs a few hundred ms (its module tree, a database, a dictionary) -- on the UI thread that is
a frozen first frame. :class:`BackgroundBuild` runs the factories on a daemon thread; the hub draws an "Opening"
placeholder (:func:`draw_opening`) while :attr:`BackgroundBuild.busy`, and adopts what was made in a later frame with
:meth:`BackgroundBuild.collect`. Anything that needs a tool *now* (a click, a restore, a test) calls
``collect(wait=True)`` first, so a build under way is joined rather than duplicated.

Factories run off the UI thread, so they must not draw or touch the current emtk context; the hub wires a made tool
into itself (frame callbacks, saved settings, shared models) when it adopts it, on the UI thread.

A frame that lazily first-imports a module while a worker imports waits for the worker's import
(:mod:`chisurf._import_gate`); :meth:`BackgroundBuild.start` and :func:`track` first import what frames import
lazily (:func:`chisurf.emtk.frame_modules.import_frame_modules`).
"""

from __future__ import annotations

import threading
import weakref
from typing import Any, Callable, Hashable

from emtk import im
from emtk.i18n import tr

from chisurf.emtk.frame_modules import import_frame_modules

#: Every build that may be running, and other first-frame reads (:func:`track`), for :func:`join_all`.
_LIVE: weakref.WeakSet[BackgroundBuild] = weakref.WeakSet()
_THREADS: weakref.WeakSet[threading.Thread] = weakref.WeakSet()


def track(thread: threading.Thread) -> threading.Thread:
    """Register a worker that reads what a window's first frames show (a store, a registry) for :func:`join_all`."""
    import_frame_modules()
    _THREADS.add(thread)
    return thread


def join_all(timeout: float = 120.0) -> None:
    """Wait until every background build and tracked read has finished (not adopted: the next frame does that, as
    in a host).

    For test drivers that issue frames back to back: a host draws again when the work wakes it, a test that
    draws N frames in a row would otherwise see only the placeholder.
    """
    for build in list(_LIVE):
        thread = build._thread
        if thread is not None:
            thread.join(timeout)
    for thread in list(_THREADS):
        thread.join(timeout)


class BackgroundBuild:
    """One batch of factories on a worker thread; results are ``key -> (made, error)``."""

    def __init__(self, wake: Callable[[], None] | None = None) -> None:
        #: Called from the worker when the batch is done (an app's thread-safe ``request_frame``).
        self.wake = wake
        self._thread: threading.Thread | None = None
        self._keys: tuple[Hashable, ...] = ()
        self._results: dict[Hashable, tuple[Any, BaseException | None]] = {}
        _LIVE.add(self)

    @property
    def busy(self) -> bool:
        """Whether a batch was started and not yet collected."""
        return self._thread is not None

    @property
    def running(self) -> bool:
        """Whether the worker is still at it (``busy`` stays true after it ends, until :meth:`collect`)."""
        thread = self._thread
        return thread is not None and thread.is_alive()

    def building(self, key: Hashable) -> bool:
        """Whether *key* is in the batch under way."""
        return key in self._keys

    def start(self, jobs: dict[Hashable, Callable[[], Any]], name: str = "chisurf-build") -> bool:
        """Run *jobs* (in order) on a worker thread; ``False`` when a batch is already running or *jobs* is empty."""
        if self._thread is not None or not jobs:
            return False
        import_frame_modules()
        self._keys = tuple(jobs)
        self._results = {}

        def work() -> None:
            for key, factory in jobs.items():
                try:
                    self._results[key] = (factory(), None)
                except Exception as exc:  # noqa: BLE001 - handed to the hub, which shows it as it would a sync failure
                    self._results[key] = (None, exc)
            if self.wake is not None:
                self.wake()

        self._thread = threading.Thread(target=work, name=name, daemon=True)
        self._thread.start()
        return True

    def collect(
        self, wait: bool = False
    ) -> dict[Hashable, tuple[Any, BaseException | None]] | None:
        """The finished batch (``None`` while it runs, unless *wait*), cleared so it is adopted once."""
        thread = self._thread
        if thread is None or (thread.is_alive() and not wait):
            return None
        thread.join()
        results, self._results, self._keys, self._thread = self._results, {}, (), None
        return results


def draw_opening(name: str, box: tuple[float, float, float, float], window_id: str) -> None:
    """The placeholder a hub draws in its tool area while the tool is made: "Opening <name>…"."""
    x, y, w, h = box
    im.set_next_window_pos((x, y), im.Cond.ALWAYS)
    im.set_next_window_size((max(1.0, w), max(1.0, h)), im.Cond.ALWAYS)
    if im.begin(window_id, flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
        im.text_disabled(tr("Opening {name}…").format(name=name))
    im.end()


__all__ = ["BackgroundBuild", "draw_opening", "join_all", "track"]
