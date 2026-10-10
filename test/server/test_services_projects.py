from __future__ import annotations

"""Tests for chisurf.server.services.projects."""

import pathlib
import tempfile
from unittest.mock import MagicMock, patch

from chisurf.server.services.projects import (
    get_project_info,
    load_project,
    save_project,
)
from chisurf.server.session import SessionState


class TestProjectsService:
    def test_get_project_info_no_project(self):
        state = SessionState()
        result = get_project_info(state)
        assert result["ok"]
        assert result["project_path"] is None
        assert result["fit_count"] == 0
        assert result["dataset_count"] == 0

    @patch("chisurf.core.project.Project")
    def test_save_project(self, mock_project_cls):
        mock_project = MagicMock()
        mock_project.save = MagicMock(return_value=pathlib.Path("/tmp/test/project.cs.pto"))
        mock_project_cls.return_value = mock_project

        state = SessionState()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = save_project(state, target_path=tmpdir)
            assert result["ok"]
        assert result.get("path", "").endswith(".cs.pto")

    def test_load_project_not_found(self):
        state = SessionState()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_project(state, project_path=tmpdir)
            assert not result["ok"]
            assert "not found" in result["error"] or "not a valid ZIP" in result.get("error", "")


class TestAutosaveDefersWhileAJobMovesTheFits:
    """An autosave capture must not race a sampling job over the fit's parameters."""

    def _gated_job(self):
        import threading

        from chisurf.server.services import fits as fit_service

        started, release = threading.Event(), threading.Event()

        def _run():
            started.set()
            release.wait(10)
            return {}

        job = fit_service._JOBS.create_job(fit_service.SAMPLE_ACTION, {})
        fit_service._JOBS.start_threaded(job, _run)
        assert started.wait(10)
        return job, release

    def test_a_deferrable_capture_is_skipped_mid_job_and_taken_after(self):
        import time

        from chisurf.server.services.projects import capture_project_payload

        state = SessionState()
        job, release = self._gated_job()
        try:
            busy = capture_project_payload(state, skip_if_busy=True)
            assert busy == {"ok": True, "busy": True}
        finally:
            release.set()
        deadline = time.monotonic() + 10
        while not job.status.is_terminal and time.monotonic() < deadline:
            time.sleep(0.01)
        done = capture_project_payload(state, skip_if_busy=True)
        assert done["ok"] and not done.get("busy") and "project" in done

    def test_the_client_reads_busy_as_a_deferral_not_a_failure(self):
        import pytest

        from chisurf.core.project.capture import ProjectCaptureBusy, project_from_capture_reply

        with pytest.raises(ProjectCaptureBusy):
            project_from_capture_reply({"ok": True, "busy": True}, name="x")
