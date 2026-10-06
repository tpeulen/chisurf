"""Real Driver input cancels a fit or BIC scan without losing prior results."""

from concurrent.futures import CancelledError
from pathlib import Path
from threading import Event
from time import monotonic

import numpy as np
import pytest
from emtk.testing import Driver

from chisurf.core.math.hmm import GaussianHMM
from chisurf.plugins.tttr.intensity_trace.demo import make_demo
from chisurf.plugins.tttr.intensity_trace.gui.app import make_app
from chisurf.plugins.tttr.intensity_trace.model import IntensityTraceModel


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Load the plugin's actual switching-molecule demo in isolated settings."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "metadata"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))
    control = make_app()
    control.model.window_ms = 2.0
    assert control.model.load(make_demo(tmp_path / "data"))
    control.tab = "HMM"
    yield control
    control.close()


def _gate_estep(monkeypatch):
    """Pause after a real E-step so the user cancellation cannot race job completion."""
    original = GaussianHMM._do_estep
    entered, released = Event(), Event()

    def step(self, *args):
        """Hold one numerical step until the test has pressed the visible button."""
        result = original(self, *args)
        entered.set()
        assert released.wait(5), "test failed to release the actual E-step"
        return result

    monkeypatch.setattr(GaussianHMM, "_do_estep", step)
    return entered, released


@pytest.mark.parametrize("action", ["request_bic", "request_hmm"])
def test_cancel_button_returns_busy_demo_to_idle_and_keeps_previous_results(app, monkeypatch, action):
    """Both actual compute buttons preserve the previous complete result on cancel."""
    old_curve = [(1, 123.0)]
    old_states = np.zeros(len(app.model.counts), dtype=int)
    old_matrix = np.ones((1, 1))
    app.bics = old_curve
    app.model.states, app.model.transmat = old_states, old_matrix
    entered, released = _gate_estep(monkeypatch)
    driver = Driver(app, (1100, 720))
    driver.frame(2)
    assert not app.form_model.enabled("request_cancel")
    try:
        driver.click(action)
        assert entered.wait(5), "the actual HMM worker never entered an E-step"
        assert app.busy and app.form_model.enabled("request_cancel")
        driver.click("request_cancel")
        assert app._cancel_event.is_set()
        assert not app.form_model.enabled("request_cancel")
        released.set()
        app.wait(5)
        driver.frame(2)
        assert not app.busy
        assert app.status == "Cancelled. Previous results kept."
        assert app.bics is old_curve
        assert app.model.states is old_states
        assert app.model.transmat is old_matrix
        assert not list(Path(app.model.path).parent.glob("*_HMM*"))
    finally:
        released.set()


def test_app_close_cancels_scan_and_bounds_cleanup(app, monkeypatch):
    """Closing requests cancellation and returns despite one still-running numerical step."""
    entered, released = _gate_estep(monkeypatch)
    app.compute_bic()
    assert entered.wait(5)
    start = monotonic()
    try:
        app.close()
        assert monotonic() - start < 2
        assert app._cancel_event.is_set()
        assert app._closed
        assert not app.animating()
    finally:
        released.set()
        app.wait(5)
    assert not app.busy


def test_model_cancellation_keeps_previous_hmm_results():
    """The model never commits a partial fit when estimation is cancelled."""
    previous_states, previous_matrix = np.zeros(10, dtype=int), np.ones((1, 1))
    model = IntensityTraceModel(counts=np.arange(20, dtype=float).reshape(10, 2),
                                states=previous_states, transmat=previous_matrix)
    with pytest.raises(CancelledError):
        model.run_hmm(cancel=lambda: True)
    assert model.states is previous_states and model.transmat is previous_matrix


def test_cancellation_at_fit_commit_restores_previous_result_and_skips_export(app, monkeypatch):
    """A cancel arriving between model commit and export cannot replace prior results."""
    old_states, old_matrix, old_message = app.model.states, app.model.transmat, app.model.message

    def fitted(*, cancel):
        """Model the narrow interval just after the completed fit was assigned."""
        app.model.states = np.zeros(len(app.model.counts), dtype=int)
        app.model.transmat = np.ones((1, 1))
        app.model.message = "completed fit"
        app._cancel_event.set()
        return app.model.message

    monkeypatch.setattr(app.model, "run_hmm", fitted)
    app.compute_hmm()
    app.wait(5)
    assert not app.busy
    assert app.status == "Cancelled. Previous results kept."
    assert app.model.states is old_states and app.model.transmat is old_matrix
    assert app.model.message == old_message
    assert not list(Path(app.model.path).parent.glob("*_HMM*"))
