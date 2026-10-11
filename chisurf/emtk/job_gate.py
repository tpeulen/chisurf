"""A gate on background jobs, so a test can hold one open and press its real Stop.

A Stop/Cancel button is enabled only while its job runs, so a test that wants to press it
cannot let the job race to its end. Every background worker of the emtk tools
(:class:`~chisurf.plugins.tttr.tttr_splitter.gui.jobs.BackgroundJob`, the correlator's thread)
passes through this gate. Nothing is armed in production, and the gate is then a no-op; a
test that arms it keeps each job that starts *open* until it is released or its own
cancel flag is set, so the press lands on an enabled Stop and the job ends because of it.

Usage on the worker side::

    ticket = job_gate.admit()                   # on the frame thread, when the job is submitted
    ...
    with job_gate.hold(ticket, cancelled) as go:  # on the worker, before it computes
        if go:
            compute()

Usage on the test side: :func:`arm`, start the work, :func:`active` says whether a job is open,
press Stop, :func:`stopped` counts the jobs ended by that press, then :func:`release` and
:func:`wait_idle` let the rest finish; :func:`disarm` restores production behaviour.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Callable, Iterator

_lock = threading.Lock()
_armed = False
_held = False
_active = 0
_stopped = 0


class Ticket:
    """One admitted job; handed to :func:`hold` by the worker that runs it."""


def arm() -> None:
    """Hold every job that is admitted from now on."""
    global _armed, _held
    with _lock:
        _armed, _held = True, True


def release() -> None:
    """Let the held jobs go on (the gate stays armed, later jobs run unheld)."""
    global _held
    with _lock:
        _held = False


def disarm() -> None:
    """Back to production behaviour: nothing is admitted, nothing is held."""
    global _armed, _held
    with _lock:
        _armed = _held = False


def active() -> int:
    """How many admitted jobs have not finished (held or running)."""
    with _lock:
        return _active


def stopped() -> int:
    """How many jobs were ended by their own cancel flag while held open (since :func:`reset`)."""
    with _lock:
        return _stopped


def reset() -> None:
    """Zero the :func:`stopped` counter."""
    global _stopped
    with _lock:
        _stopped = 0


def wait_idle(timeout: float = 30.0) -> bool:
    """Wait until no admitted job is left; whether that happened within ``timeout`` seconds."""
    end = time.monotonic() + timeout
    while active():
        if time.monotonic() > end:
            return False
        time.sleep(0.005)
    return True


def admit() -> Ticket | None:
    """Register a job being submitted; ``None`` (and free) unless a test armed the gate."""
    global _active
    with _lock:
        if not _armed:
            return None
        _active += 1
        return Ticket()


@contextmanager
def hold(ticket: Ticket | None, cancelled: Callable[[], bool]) -> Iterator[bool]:
    """Worker side: wait while the gate is held, yield whether the job should still compute.

    Yields ``False`` when ``cancelled()`` became true during the hold (the Stop was pressed): the
    job must then skip its work. The ticket is retired when the block exits.
    """
    global _active, _stopped
    if ticket is None:
        yield True
        return
    try:
        while _held and not cancelled():
            time.sleep(0.005)
        if cancelled() and _held:
            with _lock:
                _stopped += 1
            yield False
        else:
            yield True
    finally:
        with _lock:
            _active -= 1
