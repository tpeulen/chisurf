"""A value drawn every frame but refreshed off the UI thread.

Option lists the Record tool draws every frame -- the lasers connected to the computer, the
setups of the Settings library -- are read from hardware or a database. Refreshed every two
seconds *in the frame*, each took 0.2-0.3 s: the window stuttered every two seconds, recording
or not. A :class:`Refreshed` returns its last value at once and refreshes on a worker thread; an
action that needs the current value (connecting, starting a run) calls :meth:`Refreshed.now`.

Hardware enumeration and connecting a device must not run at the same time (the vendor
libraries are not thread-safe), so every refresh that touches hardware and every connect hold
:data:`HARDWARE_LOCK`.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

#: Held by hardware enumeration and by connecting / disconnecting a device.
HARDWARE_LOCK = threading.RLock()


class Refreshed:
    """The last value of *fetch*, refreshed in the background at most every *every* seconds.

    Parameters
    ----------
    fetch : callable
        Computes the value (runs on a worker thread, or in :meth:`now`).
    every : float
        Seconds a value is fresh.
    initial : object
        What :meth:`get` returns before the first refresh has landed.
    hardware : bool
        *fetch* touches hardware: it holds :data:`HARDWARE_LOCK`, and a refresh is skipped (the
        last value kept) while the lock is taken by a connect.
    skip : callable, optional
        ``skip() -> bool``: keep the last value instead of refreshing (e.g. while a device this
        tool drives is open).
    on_change : callable, optional
        Called (from the worker) after a refresh landed -- a host's ``request_frame``.
    """

    def __init__(self, fetch: Callable[[], Any], every: float = 2.0, initial: Any = None, *,
                 hardware: bool = False, skip: Callable[[], bool] | None = None,
                 on_change: Callable[[], Any] | None = None) -> None:
        self._fetch, self.every, self.value = fetch, float(every), initial
        self.hardware, self.skip, self.on_change = hardware, skip, on_change
        self._at = -1e18
        self._thread: threading.Thread | None = None

    def _compute(self) -> Any:
        if not self.hardware:
            return self._fetch()
        with HARDWARE_LOCK:
            return self._fetch()

    def _work(self) -> None:
        try:
            if self.hardware and not HARDWARE_LOCK.acquire(blocking=False):
                return  # a connect is under way: keep the last value, try again later
            try:
                value = self._fetch()
            finally:
                if self.hardware:
                    HARDWARE_LOCK.release()
        except Exception:  # noqa: BLE001 - a failed refresh keeps the last value
            return
        self.value = value
        if callable(self.on_change):
            try:
                self.on_change()
            except Exception:  # noqa: BLE001
                pass

    def get(self) -> Any:
        """The last value at once; starts a background refresh when it is stale."""
        now = time.monotonic()
        running = self._thread is not None and self._thread.is_alive()
        if not running and now - self._at > self.every and not (callable(self.skip) and self.skip()):
            self._at = now
            self._thread = threading.Thread(target=self._work, daemon=True, name="record-refresh")
            self._thread.start()
        return self.value

    def now(self) -> Any:
        """A value computed now (for an action), which also becomes the last value."""
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(5.0)
        self.value = self._compute()
        self._at = time.monotonic()
        return self.value

    def invalidate(self) -> None:
        """Make the next :meth:`get` refresh."""
        self._at = -1e18


def holds_hardware(method):
    """Run *method* holding :data:`HARDWARE_LOCK` (connecting / disconnecting a device), so a
    background enumeration never talks to a vendor library at the same time."""
    import functools

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with HARDWARE_LOCK:
            return method(self, *args, **kwargs)

    return wrapper
