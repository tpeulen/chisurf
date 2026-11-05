"""The burst search run ahead of time: searched while the user still looks at the settings.

A search of a 300 MB measurement takes ~12 s; storing its bursts in the measurement's container
afterwards takes ~1 s. So the pipeline's Burst Selection searches as soon as it knows what to
search -- the files, the detector setup and the settings -- and writes nothing: when the user
presses Next with the same settings, only the store is left (:meth:`.model.BurstSelectionModel.run`
with ``_reuse``). A change of a setting starts a new search once the settings have been still for
:data:`DELAY_S`; the search of the old settings is dropped (between files it is stopped, inside a
file it runs out and its result is thrown away).

Nothing here touches the model on screen from the worker: the thread only fills this object's
fields, which the window reads.
"""

from __future__ import annotations

import threading
import time
from typing import Any

#: Seconds the settings must be still before a new search starts (typing "60" is not "6" then "60").
DELAY_S = 0.8
#: Searches of dropped settings still running (inside a file nothing stops them) beside the
#: current one: more are not started -- the newest settings wait for one to end.
MAX_DROPPED = 1


class _Dropped(Exception):
    """Raised from the progress callback of a search whose settings are no longer wanted."""


class _Search:
    """One search: its key, its thread, and what it found."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.dropped = threading.Event()
        self.thread: threading.Thread | None = None
        self.result: dict[str, Any] | None = None
        self.error = ""
        self.started = time.monotonic()
        self.finished: float | None = None
        self.done_files = 0
        self.total_files = 0

    @property
    def alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


class SpeculativeSearch:
    """Runs a burst search ahead of time and keeps its result for the settings it was run with.

    Parameters
    ----------
    client : object
        Has ``analyze_files(paths, progress_callback=..., **request)`` (the model's client).
    delay_s : float
        Seconds the wanted search must stay the same before it starts (:data:`DELAY_S`).
    """

    def __init__(self, client: Any, delay_s: float = DELAY_S) -> None:
        self.client = client
        self.delay_s = float(delay_s)
        self.current: _Search | None = None
        self._dropped: list[_Search] = []
        #: ``(key, files, request, due)`` of the search wanted next
        self._wanted: tuple[str, list, dict, float] | None = None

    # -- what the window asks ------------------------------------------------------------------- #
    @property
    def running(self) -> bool:
        """The search of the newest settings is running."""
        return self.current is not None and self.current.alive

    @property
    def done(self) -> bool:
        """The search of the newest settings finished (with a result or an error)."""
        s = self.current
        return s is not None and s.finished is not None and self._wanted is None

    @property
    def pending(self) -> bool:
        """A search is wanted but has not started (the settings are settling, or a dropped one runs out)."""
        return self._wanted is not None

    def has(self, key: str) -> bool:
        """Whether the search of *key* is running, finished or about to start."""
        if self._wanted is not None:
            return self._wanted[0] == key
        return self.current is not None and self.current.key == key

    def result_for(self, key: str) -> dict[str, Any] | None:
        """The result of the search of *key*, if it finished without an error."""
        s = self.current
        if s is None or s.key != key or s.finished is None or s.error:
            return None
        return s.result

    def error_for(self, key: str) -> str:
        """Why the search of *key* failed ("" when it did not, or is not that search)."""
        s = self.current
        return s.error if s is not None and s.key == key and s.finished is not None else ""

    def status(self) -> tuple[str, float | None]:
        """A line for the window and the fraction done (``None``: unknown, or nothing running)."""
        s = self.current
        if self._wanted is not None and (s is None or s.key != self._wanted[0]):
            return "Settings changed: searching again in a moment …", None
        if s is None:
            return "", None
        now = time.monotonic()
        if s.finished is None:
            fraction = s.done_files / s.total_files if s.total_files > 1 else None
            return f"Searching ahead … {now - s.started:.0f} s", fraction
        if s.error:
            return f"The search ahead failed: {s.error}", None
        meta = (s.result or {}).get("metadata") or {}
        return (
            f"Searched ahead: {meta.get('n_bursts', 0)} bursts in {meta.get('n_files', 0)} file(s), "
            f"in {s.finished - s.started:.1f} s.",
            1.0,
        )

    def seconds_for(self, key: str) -> float | None:
        """How long the finished search of *key* took (``None``: not that search, or not done)."""
        s = self.current
        if s is None or s.key != key or s.finished is None:
            return None
        return s.finished - s.started

    # -- what the window tells ------------------------------------------------------------------- #
    def want(self, key: str, files, request: dict, *, now: float | None = None, delay_s: float | None = None) -> None:
        """Search *files* with *request* once *key* has been wanted for *delay_s* (default
        :attr:`delay_s`); nothing when that search is already running or done."""
        now = time.monotonic() if now is None else now
        if self.current is not None and self.current.key == key and (
            self.current.alive or self.current.finished is not None
        ):
            self._wanted = None  # back to the settings already searched
            return
        delay = self.delay_s if delay_s is None else float(delay_s)
        if self._wanted is not None and self._wanted[0] == key:
            due = min(self._wanted[3], now + delay)
        else:
            due = now + delay
        self._wanted = (key, list(files), dict(request), due)

    def forget(self) -> None:
        """Drop what is wanted and the search running (the files or setup are gone)."""
        self._wanted = None
        self._drop_current()

    def tick(self, now: float | None = None) -> bool:
        """Start the wanted search when it is due; returns whether one started."""
        now = time.monotonic() if now is None else now
        self._dropped = [s for s in self._dropped if s.alive]
        wanted = self._wanted
        if wanted is None or now < wanted[3]:
            return False
        if self.current is not None and self.current.alive and self.current.key != wanted[0]:
            self._drop_current()
        if len(self._dropped) > MAX_DROPPED:
            return False  # the newest settings wait until a dropped search ran out
        self._wanted = None
        self._start(*wanted[:3])
        return True

    def wait(self, timeout: float | None = None) -> bool:
        """Block until the current search ends (tests and scripts); whether it did."""
        s = self.current
        if s is None or s.thread is None:
            return True
        s.thread.join(timeout)
        return not s.alive

    # -- the worker ------------------------------------------------------------------------------ #
    def _drop_current(self) -> None:
        s = self.current
        if s is not None:
            s.dropped.set()
            if s.alive:
                self._dropped.append(s)
        self.current = None

    def _start(self, key: str, files: list, request: dict) -> None:
        search = _Search(key)
        search.total_files = len(files)
        self.current = search

        def progress(done: int, total: int, _path: str) -> None:
            if search.dropped.is_set():
                raise _Dropped  # between files: the rest is not searched
            search.done_files, search.total_files = int(done), int(total)

        def work() -> None:
            try:
                result = self.client.analyze_files(list(files), progress_callback=progress, **request)
            except Exception as exc:  # noqa: BLE001 - the window says it; Next searches itself
                if not search.dropped.is_set():
                    search.error = str(exc) or type(exc).__name__
            else:
                if not search.dropped.is_set():
                    search.result = result
            finally:
                search.finished = time.monotonic()

        from chisurf.emtk.background_build import track

        search.thread = track(threading.Thread(target=work, name="burst-search-ahead", daemon=True))
        search.thread.start()
