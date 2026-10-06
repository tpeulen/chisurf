"""Server calls off the drawing thread, results applied on it.

Every MMFDB call of the native admin is a :class:`Call`: a function that talks
to the server and returns plain data, run by a :class:`Runner`, and a callback
that applies the result to the model. :class:`ThreadRunner` runs the calls one
at a time, in order, on one worker thread (a ZMQ socket must not be shared by
two threads at once) and hands the results back in :meth:`Runner.poll`, which
the app calls every frame, so the model is only ever changed on the drawing
thread. :class:`InlineRunner` runs a call where it is submitted: the tests use
it to drive the app frame by frame without waiting.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Call:
    """One server call: ``fn()`` in the worker, then ``done(result)`` or ``failed(message)``."""

    label: str
    fn: Callable[[], Any]
    done: Callable[[Any], None] | None = None
    failed: Callable[[str], None] | None = None
    #: Secrets to blank out of an error message before it is shown (an API key).
    redact: tuple[str, ...] = field(default_factory=tuple)


def _message(call: Call, exc: BaseException) -> str:
    text = str(exc) or type(exc).__name__
    for secret in call.redact:
        if secret:
            text = text.replace(secret, "***REDACTED***")
    return text


class Runner:
    """Runs :class:`Call` objects; subclasses decide where."""

    #: Called with ``(call, message)`` when a call without its own ``failed`` raises.
    on_error: Callable[[Call, str], None] | None = None

    def submit(self, call: Call) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def poll(self) -> bool:
        """Apply finished calls; whether anything was applied."""
        return False

    @property
    def busy(self) -> bool:
        return False

    def _finish(self, call: Call, ok: bool, value: Any) -> None:
        if ok:
            if call.done is not None:
                call.done(value)
        elif call.failed is not None:
            call.failed(value)
        elif self.on_error is not None:
            self.on_error(call, value)

    def close(self) -> None:
        """Stop taking calls."""


class InlineRunner(Runner):
    """Run each call at once, in the caller's thread."""

    def submit(self, call: Call) -> None:
        try:
            value = call.fn()
        except Exception as exc:  # noqa: BLE001 - a failed server call is shown, never raised
            self._finish(call, False, _message(call, exc))
            return
        self._finish(call, True, value)


class ThreadRunner(Runner):
    """Run calls in order on one daemon worker; results are applied by :meth:`poll`."""

    def __init__(self) -> None:
        self._todo: queue.SimpleQueue = queue.SimpleQueue()
        self._results: queue.SimpleQueue = queue.SimpleQueue()
        self._pending = 0
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._work, name="mmfdb-admin", daemon=True)
        self._closed = False
        self._thread.start()

    def _work(self) -> None:
        while True:
            call = self._todo.get()
            if call is None:
                return
            try:
                self._results.put((call, True, call.fn()))
            except Exception as exc:  # noqa: BLE001 - reported on the drawing thread
                self._results.put((call, False, _message(call, exc)))

    def submit(self, call: Call) -> None:
        if self._closed:
            return
        with self._lock:
            self._pending += 1
        self._todo.put(call)

    @property
    def busy(self) -> bool:
        return self._pending > 0

    @property
    def current(self) -> str:
        return "" if not self.busy else "working"

    def poll(self) -> bool:
        applied = False
        while True:
            try:
                call, ok, value = self._results.get_nowait()
            except queue.Empty:
                return applied
            with self._lock:
                self._pending -= 1
            self._finish(call, ok, value)
            applied = True

    def wait(self, timeout: float = 10.0) -> None:
        """Block until every submitted call has been applied (tests, shutdown)."""
        import time

        end = time.monotonic() + timeout
        while self.busy and time.monotonic() < end:
            self.poll()
            time.sleep(0.005)
        self.poll()

    def close(self) -> None:
        self._closed = True
        self._todo.put(None)
