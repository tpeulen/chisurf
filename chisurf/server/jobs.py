from __future__ import annotations

import enum
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    # Cancellation is cooperative: a running worker only notices the request at
    # its next checkpoint, and until then it may still be touching shared state.
    # CANCELLING says "asked, not yet stopped"; CANCELLED is terminal.
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Return ``True`` once the job's worker can no longer be running."""
        return self in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


class Job:
    """Represents a single asynchronous operation."""

    def __init__(
        self,
        job_id: str,
        action: str,
        params: dict[str, Any] | None = None,
    ):
        """Initialise a job.

        Parameters
        ----------
        job_id : str
            Unique job identifier.
        action : str
            Action name for this job.
        params : dict, optional
            Parameters associated with the job.

        """
        self.job_id = job_id
        self.action = action
        self.params = params or {}
        self.status = JobStatus.QUEUED
        self.result: Any = None
        self.error: str | None = None
        self.progress: int = 0
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self._cancel_event = threading.Event()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the job to a plain dictionary."""
        return {
            "job_id": self.job_id,
            "action": self.action,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "progress": self.progress,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class JobManager:
    """Manages lifecycle of async jobs.

    Provides thread-safe job creation, tracking, and basic cancellation
    (cooperative, checked via ``should_cancel``).
    """

    def __init__(self, max_history: int = 100):
        """Initialise an empty job manager.

        Parameters
        ----------
        max_history : int
            Maximum number of terminal jobs kept in memory. ``0`` keeps none;
            negative values are clamped to ``0``.

        """
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._max_history = max(0, int(max_history))

    def create_job(self, action: str, params: dict[str, Any] | None = None) -> Job:
        """Create a new queued job with a generated UUID.

        Parameters
        ----------
        action : str
            Action name.
        params : dict, optional
            Parameters for the job.

        """
        job_id = str(uuid.uuid4())
        job = Job(job_id=job_id, action=action, params=params)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Job | None:
        """Return a job by its ID, or ``None``.

        Parameters
        ----------
        job_id : str
            Job identifier.

        """
        with self._lock:
            return self._jobs.get(job_id)

    def start_job(self, job_id: str) -> bool:
        """Transition a job from QUEUED to RUNNING.

        Returns ``False`` if the job does not exist or was already
        cancelled.

        Parameters
        ----------
        job_id : str
            Job identifier.

        """
        job = self.get_job(job_id)
        if job is None:
            return False
        with self._lock:
            if job.status == JobStatus.CANCELLED:
                return False
            job.status = JobStatus.RUNNING
            job.started_at = time.time()
        return True

    def complete_job(self, job_id: str, result: Any = None) -> bool:
        """Mark a job as COMPLETED with an optional result.

        Parameters
        ----------
        job_id : str
            Job identifier.
        result : any, optional
            Result value to store.

        """
        job = self.get_job(job_id)
        if job is None:
            return False
        with self._lock:
            job.status = JobStatus.COMPLETED
            job.result = result
            job.finished_at = time.time()
        return True

    def fail_job(self, job_id: str, error: str) -> bool:
        """Mark a job as FAILED with an error message.

        Parameters
        ----------
        job_id : str
            Job identifier.
        error : str
            Error description.

        """
        job = self.get_job(job_id)
        if job is None:
            return False
        with self._lock:
            job.status = JobStatus.FAILED
            job.error = error
            job.finished_at = time.time()
        return True

    def cancel_job(self, job_id: str) -> bool:
        """Request cancellation of a job (cooperative, sets a cancellation event).

        A job that has not started yet is cancelled outright. A **running** one
        only moves to :attr:`JobStatus.CANCELLING`, because its worker keeps
        going until its next checkpoint -- reporting it as finished while it is
        still writing to the objects it borrowed would be a lie a caller acts
        on. :meth:`_execute_job` makes it CANCELLED when the worker actually
        stops.

        Parameters
        ----------
        job_id : str
            Job identifier.

        """
        job = self.get_job(job_id)
        if job is None:
            return False
        with self._lock:
            job._cancel_event.set()
            if job.status == JobStatus.RUNNING:
                job.status = JobStatus.CANCELLING
            elif not job.status.is_terminal:
                job.status = JobStatus.CANCELLED
                job.finished_at = time.time()
        return True

    def _finish_cancelled(self, job: Job) -> None:
        """Mark a job whose worker has now stopped as terminally CANCELLED."""
        with self._lock:
            job.status = JobStatus.CANCELLED
            job.finished_at = time.time()

    def set_progress(self, job_id: str, percent: int) -> bool:
        """Record how far a running job has got, in whole percent.

        Long-running work reports progress from its worker thread while a
        caller polls the job, so the value is clamped to ``0..100`` and written
        under the manager lock rather than left to the worker.

        Parameters
        ----------
        job_id : str
            Job identifier.
        percent : int
            Completion in percent; values outside ``0..100`` are clamped.

        """
        job = self.get_job(job_id)
        if job is None:
            return False
        with self._lock:
            job.progress = max(0, min(100, int(percent)))
        return True

    def should_cancel(self, job_id: str) -> bool:
        """Return ``True`` if the job's cancellation event has been set.

        Parameters
        ----------
        job_id : str
            Job identifier.

        """
        job = self.get_job(job_id)
        if job is None:
            return False
        return job._cancel_event.is_set()

    def list_jobs(self, status: JobStatus | None = None) -> list[Job]:
        """Return all jobs, optionally filtered by status.

        Parameters
        ----------
        status : JobStatus, optional
            If given, only jobs with this status are returned.

        """
        with self._lock:
            jobs = list(self._jobs.values())
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        return jobs

    def cleanup(self) -> int:
        """Remove oldest completed/failed/cancelled jobs beyond ``max_history``.

        Returns
        -------
        int
            Number of jobs removed.

        """
        with self._lock:
            terminal = [j for j in self._jobs.values() if j.status.is_terminal]
            terminal.sort(key=lambda j: j.finished_at or 0.0)
            # Count from the front rather than slicing with a negative stop:
            # ``terminal[:-0]`` is ``terminal[:0]`` — empty — so a manager asked
            # to keep no history would have pruned nothing at all.
            to_remove = terminal[: max(0, len(terminal) - self._max_history)]
            for j in to_remove:
                del self._jobs[j.job_id]
        return len(to_remove)

    # ── synchronous execution helpers ───────────────────────────────

    def run_fn(self, action: str, params: dict[str, Any] | None, fn: Callable) -> Job:
        """Synchronously create and execute a job.  Returns the completed job."""
        job = self.create_job(action, params)
        self._execute_job(job, fn)
        return job

    def run_threaded(self, action: str, params: dict[str, Any] | None, fn: Callable) -> Job:
        """Run *fn* in a daemon thread.  Returns the job immediately (RUNNING)."""
        return self.start_threaded(self.create_job(action, params), fn)

    def start_threaded(self, job: Job, fn: Callable) -> Job:
        """Run *fn* in a daemon thread for an **already created** job.

        A worker that reports progress or polls for cancellation needs the job
        id before it starts, which :meth:`run_threaded` cannot give it. Create
        the job first, close over its id, then hand both here.

        Parameters
        ----------
        job : Job
            Job to execute; must have been created by this manager.
        fn : callable
            Nullary callable whose return value becomes the job result.

        """
        t = threading.Thread(
            target=self._execute_job,
            args=(job, fn),
            daemon=True,
            name=f"{job.action}-{job.job_id[:8]}",
        )
        t.start()
        return job

    def _execute_job(self, job: Job, fn: Callable) -> None:
        """Run *fn* inside *job* and record the outcome.

        Parameters
        ----------
        job : Job
            Job to execute.
        fn : callable
            Nullary callable whose return value becomes the job result.

        """
        if job.status == JobStatus.CANCELLED:
            return
        self.start_job(job.job_id)
        try:
            if self.should_cancel(job.job_id):
                self._finish_cancelled(job)
                return
            result = fn()
            if self.should_cancel(job.job_id):
                self._finish_cancelled(job)
            else:
                self.complete_job(job.job_id, result)
        except Exception as e:
            if self.should_cancel(job.job_id):
                self._finish_cancelled(job)
            else:
                self.fail_job(job.job_id, str(e))
