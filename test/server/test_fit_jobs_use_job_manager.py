"""Long-running fit work must live in the shared job manager (INC-08).

Sampling and parameter scans each kept their own module-level ``dict`` of job
state, mutated from worker threads without a lock and never pruned, while
``JobManager`` -- the thing built for exactly this -- sat unused. These tests
pin that both job families are now registered jobs with real status
transitions, cooperative cancellation, and no cross-talk between the two
endpoint families.
"""

from __future__ import annotations

import time

import pytest

from chisurf.server.services import fits as fit_service


class _Parameter:
    """A free parameter with a value the scan may move."""

    def __init__(self, value: float):
        """Start at *value* with no error estimate, so the scan picks a range."""
        self.value = value
        self.error_estimate = None


class _Model:
    """A one-parameter parabola whose chi2 the owning fit reads back."""

    def __init__(self, fit, step_delay: float = 0.0):
        """Bind to *fit*; ``step_delay`` slows each update so a cancel can land."""
        self._fit = fit
        self._step_delay = step_delay
        self.parameters_all_dict = {"a": _Parameter(2.0)}

    def _update_model(self) -> None:
        """Recompute the fit's chi2 from the current parameter value."""
        if self._step_delay:
            time.sleep(self._step_delay)
        residual = self.parameters_all_dict["a"].value - 2.0
        self._fit.chi2 = residual ** 2
        self._fit.chi2r = residual ** 2 / 2.0


class _Fit:
    """Minimal stand-in for a fit the scan service can drive."""

    def __init__(self, step_delay: float = 0.0):
        """Create a fit whose model is a parabola in its single parameter."""
        self.unique_identifier = "fit-uid"
        self.chi2 = 0.0
        self.chi2r = 0.0
        self.model = _Model(self, step_delay=step_delay)


class _State:
    """Minimal stand-in for the server's session state."""

    def __init__(self, fits):
        """Hold the list of fits the service resolves against."""
        self.fits = fits


def _wait_for(job_id: str, timeout: float = 30.0) -> dict:
    """Poll a scan job until it leaves the queued/running states."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = fit_service.fit_parameter_scan_result(None, job_id)
        if result.get("status") not in ("queued", "running", "cancelling"):
            return result
        time.sleep(0.01)
    raise AssertionError("parameter scan did not finish in time")


def test_a_parameter_scan_is_a_job_in_the_shared_manager():
    """The scan must be registered, complete, and hand back its curve."""
    fit = _Fit()
    started = fit_service.fit_parameter_scan_start(
        _State([fit]), parameter_name="a", fit_index=0, n_steps=11,
    )
    assert started["ok"]
    job_id = started["job_id"]

    job = fit_service._JOBS.get_job(job_id)
    assert job is not None
    assert job.action == fit_service.PARAMETER_SCAN_ACTION
    assert job.params["parameter_name"] == "a"

    result = _wait_for(job_id)
    assert result["status"] == "completed", result.get("error")
    assert result["progress"] == 100
    assert len(result["values"]) == 11
    assert len(result["chi2"]) == 11
    # The scan walks the live model, so it owes the starting value back.
    assert fit.model.parameters_all_dict["a"].value == pytest.approx(2.0)


def test_cancelling_a_scan_stops_it_and_restores_the_parameter():
    """Cancellation is cooperative: the worker must notice and put things back."""
    fit = _Fit(step_delay=0.01)
    started = fit_service.fit_parameter_scan_start(
        _State([fit]), parameter_name="a", fit_index=0, n_steps=500,
    )
    job_id = started["job_id"]

    # Let the worker take a few steps so it is genuinely mid-scan.
    time.sleep(0.05)
    cancelled = fit_service.fit_parameter_scan_cancel(None, job_id)
    assert cancelled["ok"]

    result = _wait_for(job_id)
    assert result["status"] == "cancelled"
    assert result["values"] == []
    assert fit.model.parameters_all_dict["a"].value == pytest.approx(2.0)


def test_a_failing_scan_is_reported_as_failed():
    """An exception in the worker must surface as a failed job, not a hang."""
    fit = _Fit()

    def _boom() -> None:
        raise RuntimeError("model blew up")

    fit.model._update_model = _boom
    started = fit_service.fit_parameter_scan_start(
        _State([fit]), parameter_name="a", fit_index=0, n_steps=5,
    )
    result = _wait_for(started["job_id"])
    assert result["status"] == "failed"
    assert "model blew up" in (result["error"] or "")
    # Even a scan that never took a single successful step must not leave the
    # fit holding a probe value.
    assert fit.model.parameters_all_dict["a"].value == pytest.approx(2.0)


def test_a_failing_scan_still_restores_the_parameter():
    """A probe value outside the model's domain is the normal way a scan fails.

    Walking towards the edge of a model's domain is what a scan is for, so
    ``update_model`` raising mid-scan is expected -- and the borrowed parameter
    must come back regardless, not keep whichever probe value blew up.
    """
    fit = _Fit()
    real_update = fit.model._update_model
    calls = {"n": 0}

    def _boom_on_the_fourth_step() -> None:
        """Behave normally, then raise once the scan is genuinely under way."""
        calls["n"] += 1
        if calls["n"] == 4:
            raise RuntimeError("model blew up")
        real_update()

    fit.model._update_model = _boom_on_the_fourth_step
    started = fit_service.fit_parameter_scan_start(
        _State([fit]), parameter_name="a", fit_index=0, n_steps=11,
    )
    result = _wait_for(started["job_id"])
    assert result["status"] == "failed"
    assert "model blew up" in (result["error"] or "")
    assert fit.model.parameters_all_dict["a"].value == pytest.approx(2.0)


def test_the_two_job_families_do_not_share_an_id_space():
    """A scan id must not be pollable through the sampling endpoints."""
    fit = _Fit()
    started = fit_service.fit_parameter_scan_start(
        _State([fit]), parameter_name="a", fit_index=0, n_steps=5,
    )
    job_id = started["job_id"]
    _wait_for(job_id)

    status = fit_service.fit_sample_status(None, job_id)
    assert not status.get("ok", False)
    cancelled = fit_service.fit_sample_cancel(None, job_id)
    assert not cancelled.get("ok", False)


def test_an_unknown_scan_job_is_an_error():
    """Polling a job that never existed must not look like a clean result."""
    assert not fit_service.fit_parameter_scan_result(None, "no-such-job").get("ok", False)
    assert not fit_service.fit_parameter_scan_cancel(None, "no-such-job").get("ok", False)
