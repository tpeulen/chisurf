"""One mechanism for long-running work: observable, and cooperatively cancelable.

`LAY-07` recorded three unrelated mechanisms — a thread pool in the web backend,
a blocking call in the CLI, a `QProgressDialog` in the GUI — none of which could
be observed or stopped from outside. This is the one they all drive.

# It mirrors ChiSurf's contract, and does not import it

The status vocabulary, `progress`, the cooperative `should_cancel` and the
`to_dict()` shape match `chisurf/server/jobs.py` deliberately, so the host
recognises what QuEst reports. It is *implemented here* rather than imported,
because a plugin that needs its host in order to run standalone is not a
plugin.

# "job" means a running operation; run artefacts are "runs"

The word meant two things. `quest/jobs.py` was finished artefact *directories*
on disk, while a host's `jobs` are running tasks — so `quest.jobs.list` would
have handed a ChiSurf caller directories when it asked for tasks. The artefact
side is now :mod:`quest.runs` and this module owns "job".

# Cancellation is cooperative, and a single simulation is nearly atomic

Setting the flag asks; the worker notices at its next checkpoint. A **scan**
checks between sites, so it stops within one site. A single `simulate` has
essentially one checkpoint: `simulate_traj` computes the whole trajectory in
one compiled IMP.bff call, and compiled code cannot poll a Python flag. Cancelling one
site therefore means "do not start the next stage", not "stop now".

That limitation is stated rather than hidden, because a cancel button that
implies more than it delivers is worse than none: `CANCELLING` is a distinct
state from `CANCELLED` for exactly this reason.
"""

from __future__ import annotations

import enum
import threading
import uuid
from typing import Any, Callable, Dict, Optional

__all__ = [
    "JobStatus",
    "Job",
    "JobManager",
    "CancelledError",
    "default_manager",
]


class CancelledError(RuntimeError):
    """Raised inside a worker when it observes a cancellation request."""


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    #: Asked, not yet stopped. A running worker only notices at its next
    #: checkpoint, and until then it may still be touching shared state.
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


class Job:
    """One long-running operation."""

    def __init__(self, job_id: str, action: str, params: Optional[Dict[str, Any]] = None):
        self.job_id = job_id
        self.action = action
        self.params = params or {}
        self.status = JobStatus.QUEUED
        self.result: Any = None
        self.error: Optional[str] = None
        self.error_code: Optional[str] = None
        self.progress: int = 0
        self.message: str = ""
        self._cancel_event = threading.Event()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def to_dict(self) -> Dict[str, Any]:
        """The shape a host reads. Deliberately JSON-only — no result object.

        `result` is excluded: it may be a `DecaySimulationResult` full of numpy,
        and this dict crosses a transport. A caller fetches the result through
        the method that produced it, where `to_payload` applies.
        """
        return {
            "job_id": self.job_id,
            "action": self.action,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "error": self.error,
            "error_code": self.error_code,
        }


class JobManager:
    """Thread-safe creation, progress, and cooperative cancellation."""

    def __init__(self, max_history: int = 100):
        self._lock = threading.RLock()
        self._jobs: Dict[str, Job] = {}
        self._order: list[str] = []
        self._max_history = max(0, int(max_history))

    # -- lifecycle --------------------------------------------------------

    def create(self, action: str, params: Optional[Dict[str, Any]] = None) -> Job:
        job = Job(str(uuid.uuid4()), action, params)
        with self._lock:
            self._jobs[job.job_id] = job
            self._order.append(job.job_id)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Dict[str, Any]]:
        """Newest first, like every other listing here."""
        with self._lock:
            return [self._jobs[j].to_dict() for j in reversed(self._order) if j in self._jobs]

    def start(self, job_id: str) -> bool:
        job = self.get(job_id)
        with self._lock:
            if job is None or job.status is not JobStatus.QUEUED:
                return False
            if job.cancel_requested:
                # Cancelled before it ever ran: terminal immediately, since
                # there is no worker to notice anything.
                job.status = JobStatus.CANCELLED
                return False
            job.status = JobStatus.RUNNING
        return True

    def finish(self, job_id: str, result: Any = None) -> None:
        job = self.get(job_id)
        with self._lock:
            if job is None:
                return
            # A worker that returns *after* observing cancellation is cancelled,
            # not completed -- its result is partial.
            job.status = (
                JobStatus.CANCELLED if job.cancel_requested else JobStatus.COMPLETED
            )
            if job.status is JobStatus.COMPLETED:
                job.result = result
                job.progress = 100
        self._trim()

    def fail(self, job_id: str, error: str, error_code: str = "operation_failed") -> None:
        job = self.get(job_id)
        with self._lock:
            if job is None:
                return
            job.status = JobStatus.FAILED
            job.error = error
            job.error_code = error_code
        self._trim()

    # -- observation and cancellation -------------------------------------

    def set_progress(self, job_id: str, percent: int, message: str = "") -> bool:
        job = self.get(job_id)
        with self._lock:
            if job is None or job.status.is_terminal:
                return False
            job.progress = max(0, min(100, int(percent)))
            if message:
                job.message = message
        return True

    def cancel(self, job_id: str) -> bool:
        """Ask *job_id* to stop. Returns whether the request was accepted.

        A queued job is cancelled outright; a running one moves to
        `CANCELLING` and stays there until its worker notices.
        """
        job = self.get(job_id)
        with self._lock:
            if job is None or job.status.is_terminal:
                return False
            job._cancel_event.set()
            if job.status is JobStatus.QUEUED:
                job.status = JobStatus.CANCELLED
            else:
                job.status = JobStatus.CANCELLING
        return True

    def should_cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        return bool(job is not None and job.cancel_requested)

    def canceller(self, job_id: str) -> Callable[[], bool]:
        """A zero-argument predicate to hand to the domain.

        The domain takes a *callable*, not a `Job` or a manager: that keeps
        `quest.core` free of any notion of job bookkeeping, and lets a caller
        with its own cancellation source (a host, a Qt dialog) pass its own.
        """
        return lambda: self.should_cancel(job_id)

    def reporter(self, job_id: str) -> Callable[[int, str], None]:
        """A progress callback to hand to the domain."""
        return lambda percent, message="": self.set_progress(job_id, percent, message)

    # -- history ----------------------------------------------------------

    def _trim(self) -> None:
        with self._lock:
            terminal = [j for j in self._order if self._jobs[j].status.is_terminal]
            excess = len(terminal) - self._max_history
            for job_id in terminal[:excess] if excess > 0 else []:
                self._jobs.pop(job_id, None)
                self._order.remove(job_id)


#: The process-wide manager the surfaces share. A host may use its own.
_DEFAULT: Optional[JobManager] = None


def default_manager() -> JobManager:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = JobManager()
    return _DEFAULT
