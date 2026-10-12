"""Long-running work: one mechanism, observable and cooperatively cancelable.

`LAY-07` recorded three unrelated mechanisms — a thread pool in the web backend,
a blocking call in the CLI, a `QProgressDialog` in the GUI — none of which could
be observed or stopped from outside.

These tests hold two things in place. First, the **contract** matches
`chisurf/server/jobs.py`, because a host has to recognise what QuEst reports.
Second, and more important, that cancellation **actually stops work** — a cancel
button that sets a flag nothing reads is worse than no button, because it
reports success.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from chisurf.plugins.quenching_estimator.core.scan import scan_positions
from chisurf.plugins.quenching_estimator.core.tasks import Job, JobManager, JobStatus

STRUCTURE = Path(__file__).parent / "148l.pdb"


@pytest.fixture
def manager() -> JobManager:
    return JobManager()


class TestTheContractMatchesTheHost:
    def test_the_status_vocabulary_is_chisurfs(self) -> None:
        """Same strings, so a host's UI can render QuEst's jobs unchanged."""
        assert {s.value for s in JobStatus} == {
            "queued",
            "running",
            "cancelling",
            "completed",
            "failed",
            "cancelled",
        }

    def test_cancelling_is_not_terminal_but_cancelled_is(self) -> None:
        """The distinction exists because cancellation is cooperative.

        Between the request and the worker noticing, the job is still running
        and may still be touching shared state. Collapsing the two states would
        tell a caller the work had stopped when it had not.
        """
        assert not JobStatus.CANCELLING.is_terminal
        assert JobStatus.CANCELLED.is_terminal
        assert JobStatus.COMPLETED.is_terminal
        assert JobStatus.FAILED.is_terminal
        assert not JobStatus.QUEUED.is_terminal
        assert not JobStatus.RUNNING.is_terminal

    def test_the_dict_shape_is_json_only(self) -> None:
        """It crosses a transport, so it must not carry a result object."""
        import json

        job = Job("id-1", "quest.scan")
        job.result = object()
        payload = job.to_dict()
        assert "result" not in payload
        json.dumps(payload)
        assert set(payload) == {
            "job_id",
            "action",
            "status",
            "progress",
            "message",
            "error",
            "error_code",
        }


class TestLifecycle:
    def test_a_new_job_is_queued(self, manager: JobManager) -> None:
        job = manager.create("quest.scan")
        assert job.status is JobStatus.QUEUED
        assert manager.get(job.job_id) is job

    def test_start_then_finish(self, manager: JobManager) -> None:
        job = manager.create("quest.simulate")
        assert manager.start(job.job_id) is True
        assert job.status is JobStatus.RUNNING
        manager.finish(job.job_id, result={"x": 1})
        assert job.status is JobStatus.COMPLETED
        assert job.progress == 100
        assert job.result == {"x": 1}

    def test_failure_carries_a_code(self, manager: JobManager) -> None:
        job = manager.create("quest.simulate")
        manager.start(job.job_id)
        manager.fail(job.job_id, "boom", "unlabelable_site")
        assert job.status is JobStatus.FAILED
        assert job.error_code == "unlabelable_site"

    def test_progress_is_clamped(self, manager: JobManager) -> None:
        job = manager.create("quest.scan")
        manager.start(job.job_id)
        manager.set_progress(job.job_id, 500)
        assert job.progress == 100
        manager.set_progress(job.job_id, -5)
        assert job.progress == 0

    def test_a_terminal_job_stops_accepting_progress(self, manager: JobManager) -> None:
        job = manager.create("quest.scan")
        manager.start(job.job_id)
        manager.finish(job.job_id)
        assert manager.set_progress(job.job_id, 50) is False
        assert job.progress == 100

    def test_listing_is_newest_first(self, manager: JobManager) -> None:
        ids = [manager.create("quest.scan").job_id for _ in range(3)]
        assert [entry["job_id"] for entry in manager.list()] == ids[::-1]


class TestCancellation:
    def test_a_queued_job_is_cancelled_outright(self, manager: JobManager) -> None:
        """There is no worker to notice, so it is terminal immediately."""
        job = manager.create("quest.scan")
        assert manager.cancel(job.job_id) is True
        assert job.status is JobStatus.CANCELLED
        assert manager.start(job.job_id) is False

    def test_a_running_job_goes_to_cancelling_first(self, manager: JobManager) -> None:
        job = manager.create("quest.scan")
        manager.start(job.job_id)
        manager.cancel(job.job_id)
        assert job.status is JobStatus.CANCELLING
        assert manager.should_cancel(job.job_id) is True

    def test_a_worker_that_returns_after_cancelling_is_cancelled(self, manager: JobManager) -> None:
        """Not `completed`: its result is partial, and saying otherwise lies."""
        job = manager.create("quest.scan")
        manager.start(job.job_id)
        manager.cancel(job.job_id)
        manager.finish(job.job_id, result="partial")
        assert job.status is JobStatus.CANCELLED
        assert job.result is None

    def test_cancelling_a_terminal_job_is_refused(self, manager: JobManager) -> None:
        job = manager.create("quest.scan")
        manager.start(job.job_id)
        manager.finish(job.job_id)
        assert manager.cancel(job.job_id) is False

    def test_cancelling_an_unknown_job_is_refused(self, manager: JobManager) -> None:
        assert manager.cancel("not-a-job") is False
        assert manager.should_cancel("not-a-job") is False

    def test_the_canceller_is_a_bare_predicate(self, manager: JobManager) -> None:
        """The domain takes a callable, not a job or a manager.

        That is what keeps `quest.core` free of job bookkeeping and lets a
        caller with its own cancellation source pass its own.
        """
        job = manager.create("quest.scan")
        manager.start(job.job_id)
        should_cancel = manager.canceller(job.job_id)

        assert should_cancel() is False
        manager.cancel(job.job_id)
        assert should_cancel() is True

    def test_it_is_thread_safe(self, manager: JobManager) -> None:
        job = manager.create("quest.scan")
        manager.start(job.job_id)
        errors: list[BaseException] = []

        def hammer() -> None:
            try:
                for index in range(200):
                    manager.set_progress(job.job_id, index % 100)
                    manager.should_cancel(job.job_id)
                    manager.list()
            except BaseException as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=hammer) for _ in range(8)]
        for thread in threads:
            thread.start()
        manager.cancel(job.job_id)
        for thread in threads:
            thread.join()
        assert not errors


class TestTheScanActuallyStops:
    """The part that matters: the flag is read, and work stops.

    A cancel button whose flag nothing polls still reports success. These run
    the real domain function.
    """

    POSITIONS = {
        f"E{residue}": {
            "chain_identifier": "E",
            "residue_seq_number": residue,
            "atom_name": "CB",
            "residue_name": "ALA",
        }
        for residue in (96, 139, 129, 100, 110)
    }

    def _project(self) -> dict:
        from chisurf.plugins.quenching_estimator.core.dye_diffusion import (
            default_amino_acid_interactions,
        )

        return {
            "tau0": 4.2,
            "n_photons": 100,
            "t_max": 20.0,
            "t_step": 0.05,
            "dg": 0.5,
            "critical_distance": 8.5,
            "slow_radius": 8.5,
            "av_parameter": {"linker_length": 21.5, "linker_width": 0.5, "radius1": 3.5},
            "amino_acid_interactions": default_amino_acid_interactions(slow_factor=0.1),
            "pdb": str(STRUCTURE),
            "n_bins": 16,
            "parallel_trajectories": 1,
            "fret": {"enabled": False, "dyes": [{"name": "D0", "D": 7.0, "random_seed": 5}]},
        }

    def test_cancelling_before_the_first_site_yields_nothing(self, tmp_path) -> None:
        records = list(
            scan_positions(
                self._project(),
                self.POSITIONS,
                project_dir=tmp_path,
                should_cancel=lambda: True,
            )
        )
        assert records == []

    def test_it_stops_after_the_site_in_flight(self, tmp_path) -> None:
        """Cancellation lands within one site — a scan's only checkpoint."""
        seen: list[str] = []
        stop_after = 2

        def should_cancel() -> bool:
            return len(seen) >= stop_after

        for record in scan_positions(
            self._project(),
            self.POSITIONS,
            project_dir=tmp_path,
            should_cancel=should_cancel,
        ):
            seen.append(record["name"])

        assert len(seen) == stop_after, (
            f"expected the scan to stop after {stop_after} sites, got {seen}"
        )
        assert seen == list(self.POSITIONS)[:stop_after]

    def test_without_a_canceller_it_runs_everything(self, tmp_path) -> None:
        """The guard must not change behaviour when nobody is cancelling."""
        records = list(scan_positions(self._project(), self.POSITIONS, project_dir=tmp_path))
        assert [record["name"] for record in records] == list(self.POSITIONS)

    def test_progress_is_reported_per_site(self, tmp_path) -> None:
        reported: list[tuple[int, str]] = []
        list(
            scan_positions(
                self._project(),
                self.POSITIONS,
                project_dir=tmp_path,
                report_progress=lambda percent, message="": reported.append((percent, message)),
            )
        )
        assert [percent for percent, _ in reported] == [20, 40, 60, 80, 100]
        assert [name for _, name in reported] == list(self.POSITIONS)


class TestTheRpcSurface:
    def test_cancel_reports_whether_it_was_accepted(self) -> None:
        from chisurf.plugins.quenching_estimator.core.tasks import default_manager
        from chisurf.plugins.quenching_estimator.rpc import local_client

        job = default_manager().create("quest.scan")
        default_manager().start(job.job_id)
        client = local_client()

        assert (
            client.result("quest.jobs.cancel", {"job_id": job.job_id})["cancel_requested"] is True
        )
        assert client.result("quest.jobs.get", {"job_id": job.job_id})["status"] == ("cancelling")

    def test_an_unknown_job_is_an_error_not_a_null(self) -> None:
        from chisurf.plugins.quenching_estimator.rpc import local_client

        response = local_client().call("quest.jobs.get", {"job_id": "nope"})
        assert response["ok"] is False

    def test_runs_and_jobs_are_different_methods(self) -> None:
        """The whole point of the rename."""
        from chisurf.plugins.quenching_estimator.rpc import METHODS

        assert "quest.runs.list" in METHODS
        assert "quest.jobs.list" in METHODS
        assert METHODS["quest.runs.list"] != METHODS["quest.jobs.list"]
