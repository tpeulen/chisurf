"""A kept process pool that lets its processes go when nobody has used it for a while.

ChiSurf keeps worker processes between calls where starting them costs more than the work (the
burst fit, Burst Analysis' BVA/2CDE tasks, the imaging calibration reader): a spawned Python with
tttrlib and the fit imports takes about a second. Kept for the life of the window, though, they
are memory nobody uses -- each burst-fit worker holds 1-3 GB once it has fitted a measurement, and
a few ChiSurf windows with their pools ran a 16 GB laptop out of memory (87 Python processes,
34 GB). :class:`IdlePool` starts its processes on the first :meth:`~IdlePool.submit`, shuts them
down once no task has run for :attr:`~IdlePool.idle_s` seconds, and starts them again on the next
submit; a caller never holds a pool that was shut down under it. Its workers end themselves when
the process that started them is gone (:func:`_exit_with_parent`).
"""

from __future__ import annotations

import concurrent.futures
import os
import threading
import time
from typing import Any, Callable

#: Seconds without a task after which a pool's processes are shut down
#: (``CHISURF_POOL_IDLE_S`` overrides; ``0`` keeps them for the life of the process).
DEFAULT_IDLE_S = 60.0


def idle_seconds() -> float:
    """The idle time after which kept pools let their processes go."""
    value = os.environ.get("CHISURF_POOL_IDLE_S", "").strip()
    try:
        return float(value) if value else DEFAULT_IDLE_S
    except ValueError:
        return DEFAULT_IDLE_S


def _exit_with_parent(parent: int) -> None:
    """Worker initializer: end this process once the process that started it is gone.

    A pool's workers wait for tasks on a pipe and never notice a parent that died without
    shutting them down (a crash, a kill, ``os._exit``): on ``ssh home`` 91 of them were left
    behind by benchmark runs, each holding its imports and caches."""

    def watch() -> None:
        while True:
            time.sleep(1.0)
            if os.getppid() != parent:
                os._exit(0)

    threading.Thread(target=watch, name="exit-with-parent", daemon=True).start()


class IdlePool:
    """A spawn :class:`~concurrent.futures.ProcessPoolExecutor` of *workers* processes, started on
    first use and shut down after *idle_s* seconds without a task (default :func:`idle_seconds`).

    Only :meth:`submit` and :meth:`shutdown` are offered: everything that runs goes through
    :meth:`submit`, which is what counts as use.
    """

    def __init__(self, workers: int, idle_s: float | None = None, name: str = "pool") -> None:
        self.workers = max(1, int(workers))
        self.idle_s = idle_seconds() if idle_s is None else float(idle_s)
        self.name = name
        self._lock = threading.Lock()
        self._pool: concurrent.futures.ProcessPoolExecutor | None = None
        self._in_flight = 0
        self._last = time.monotonic()
        self._reaper: threading.Thread | None = None

    @property
    def started(self) -> bool:
        """Whether the processes are up (or starting)."""
        return self._pool is not None

    def submit(self, fn: Callable, /, *args: Any, **kwargs: Any) -> concurrent.futures.Future:
        """Run ``fn(*args, **kwargs)`` in a worker, starting the processes when they are down."""
        with self._lock:
            if self._pool is None:
                import multiprocessing as mp

                self._pool = concurrent.futures.ProcessPoolExecutor(
                    max_workers=self.workers, mp_context=mp.get_context("spawn"),
                    initializer=_exit_with_parent, initargs=(os.getpid(),),
                )
            future = self._pool.submit(fn, *args, **kwargs)
            self._in_flight += 1
            self._last = time.monotonic()
            if self.idle_s > 0 and self._reaper is None:
                self._reaper = threading.Thread(
                    target=self._reap, name=f"{self.name}-idle", daemon=True
                )
                self._reaper.start()
        # outside the lock: a future already done runs the callback here, at once
        future.add_done_callback(self._done)
        return future

    def _done(self, _future) -> None:
        with self._lock:
            self._in_flight -= 1
            self._last = time.monotonic()

    def idle_for(self) -> float:
        """Seconds since the last task finished (``0`` while one runs)."""
        with self._lock:
            return 0.0 if self._in_flight > 0 else time.monotonic() - self._last

    def _reap(self) -> None:
        step = max(0.05, min(5.0, self.idle_s / 4.0))
        while True:
            time.sleep(step)
            with self._lock:
                if self._pool is None:
                    self._reaper = None
                    return
                if self._in_flight > 0 or time.monotonic() - self._last < self.idle_s:
                    continue
                pool, self._pool, self._reaper = self._pool, None, None
            pool.shutdown(wait=False, cancel_futures=True)
            return

    def shutdown(self, wait: bool = False, cancel_futures: bool = True) -> None:
        """Stop the processes now; the next :meth:`submit` starts them again."""
        with self._lock:
            pool, self._pool = self._pool, None
            self._in_flight = 0
        if pool is not None:
            pool.shutdown(wait=wait, cancel_futures=cancel_futures)


__all__ = ["DEFAULT_IDLE_S", "IdlePool", "idle_seconds"]
