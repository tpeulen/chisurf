"""A finished sampling job must say whether its chain is usable (PRD-69).

The server ran ``sample_fit`` in a thread and threw the return value away, so
``fit.sample.status`` reported ``completed`` for a chain that never left its
starting point exactly as for one that explored the posterior. These tests pin
that the convergence verdict travels with the job.
"""
import time

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse
from chisurf.server.services import fits as fit_service


class _State:
    """Minimal stand-in for the server's session state."""

    def __init__(self, fits):
        """Hold the list of fits the service resolves against."""
        self.fits = fits


def _quadratic_fit(seed: int = 1):
    """Return a converged ``c + a*x**2`` fit to noisy data."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, 64)
    y = 3.1 + 1.2 * x ** 2 + rng.normal(0.0, 0.05, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, 0.05))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x**2'
    fit.model.find_parameters()
    fit.run()
    return fit


def _wait(job_id, timeout=120.0):
    """Block until the job leaves the running state, then return its status."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = fit_service.fit_sample_status(None, job_id)
        if status.get("status") not in ("starting", "running"):
            return status
        time.sleep(0.1)
    raise AssertionError("sampling job did not finish in time")


@pytest.fixture(autouse=True)
def _stub_project_save(monkeypatch):
    """``sample_fit`` saves the whole project; that is not under test here."""
    import chisurf.macros.core_fit
    monkeypatch.setattr(
        chisurf.macros.core_fit, "save_project",
        lambda target_path, project_name="project", **kw: None,
    )


def test_a_converged_job_reports_no_warnings(tmp_path):
    """A healthy run must come back with ``converged`` true and no warnings."""
    np.random.seed(0)
    fit = _quadratic_fit()
    state = _State([fit])

    started = fit_service.fit_sample_start(
        state, fit_index=0, n_steps=3000, n_runs=2,
        target_directory=str(tmp_path), method='blocked', thin=1,
    )
    assert started["ok"]
    status = _wait(started["job_id"])

    assert status["status"] == "completed", status.get("error")
    assert status["converged"] is True
    assert status["warnings"] == []
    report = status["diagnostics"]
    assert report["n_runs"] == 2
    assert {e["name"] for e in report["parameters"]} == set(fit.model.parameter_names)


def test_a_stuck_job_completes_but_is_reported_as_unusable(tmp_path):
    """The whole point: ``completed`` must not imply ``trustworthy``."""
    np.random.seed(1)
    fit = _quadratic_fit()
    state = _State([fit])

    # A step size of essentially zero: the chain accepts everything and goes
    # nowhere, which is the classic silently-wrong MCMC result.
    started = fit_service.fit_sample_start(
        state, fit_index=0, n_steps=200, n_runs=2,
        target_directory=str(tmp_path), method='mcmc', thin=1, step_size=1e-12,
    )
    status = _wait(started["job_id"])

    assert status["status"] == "completed"
    assert status["converged"] is False
    assert status["warnings"]
    assert any("R-hat" in w or "effective sample size" in w for w in status["warnings"])


def test_the_method_keyword_reaches_the_sampler(tmp_path):
    """The backend must be selectable per job, not only via the settings file."""
    np.random.seed(2)
    fit = _quadratic_fit()
    state = _State([fit])

    seen = {}
    original = chisurf.core.fitting.fit.sample_fit

    def _spy(*args, **kwargs):
        seen.update(kwargs)
        return original(*args, **kwargs)

    chisurf.core.fitting.fit.sample_fit = _spy
    try:
        started = fit_service.fit_sample_start(
            state, fit_index=0, n_steps=200, n_runs=1,
            target_directory=str(tmp_path), method='blocked', thin=1,
        )
        _wait(started["job_id"])
    finally:
        chisurf.core.fitting.fit.sample_fit = original

    assert seen.get("method") == 'blocked'


def test_status_of_an_unknown_job_is_an_error():
    """Polling a job that never existed must not look like a clean result."""
    result = fit_service.fit_sample_status(None, "no-such-job")
    assert not result.get("ok", False)
