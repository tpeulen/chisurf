"""Cooperative cancellation preserves HMM numerics and stops between maps."""

from concurrent.futures import CancelledError
from threading import Event

import numpy as np
import pytest

from chisurf.core.math.hmm import GaussianHMM
from chisurf.plugins.core.hmm.api import HmmSettings
from chisurf.plugins.core.hmm.core.analysis import fit_traces, scan_state_counts


def _trace():
    """Return a fixed two-level Gaussian-emission trace."""
    rng = np.random.default_rng(154)
    return np.concatenate([rng.normal(0, 0.5, (80, 1)), rng.normal(6, 0.5, (80, 1))])


@pytest.mark.parametrize("accelerate", [False, True])
def test_no_cancel_preserves_fit_parameters_likelihood_and_decoding(accelerate):
    """A false cancellation callback leaves the complete scientific result exact."""
    trace = _trace()
    plain = GaussianHMM(2, covariance_type="diag", accelerate=accelerate, random_state=9)
    cancellable = GaussianHMM(2, covariance_type="diag", accelerate=accelerate, random_state=9)
    plain.fit(trace)
    cancellable.fit(trace, cancel=lambda: False)
    for name in ("startprob_", "transmat_", "means_", "covars_"):
        np.testing.assert_array_equal(getattr(plain, name), getattr(cancellable, name))
    assert plain.score(trace) == cancellable.score(trace)
    assert plain.bic(trace) == cancellable.bic(trace)
    np.testing.assert_array_equal(plain.predict(trace), cancellable.predict(trace))


@pytest.mark.parametrize("accelerate", [False, True])
def test_cancel_interrupts_em_maps_and_squarem_without_another_estep(monkeypatch, accelerate):
    """An event set during one E-step prevents any subsequent EM map."""
    requested = Event()
    model = GaussianHMM(2, covariance_type="diag", n_iter=100, tol=0,
                        accelerate=accelerate, random_state=9)
    original = model._do_estep
    calls = []

    def step(*args):
        """Request cancellation after two actual lattice sweeps."""
        result = original(*args)
        calls.append(1)
        if len(calls) == 2:
            requested.set()
        return result

    monkeypatch.setattr(model, "_do_estep", step)
    with pytest.raises(CancelledError):
        model.fit(_trace(), cancel=requested.is_set)
    assert len(calls) == 2
    # Cancellation is per invocation, so this estimator can be used again.
    model.fit(_trace())


def test_scan_cancel_is_not_converted_to_a_nan_fit(monkeypatch):
    """Cancellation propagates out of the scan instead of reporting a fit failure."""
    original = GaussianHMM._do_estep
    requested = Event()

    def step(self, *args):
        """Finish one real E-step, then ask the next map to stop."""
        result = original(self, *args)
        requested.set()
        return result

    monkeypatch.setattr(GaussianHMM, "_do_estep", step)
    with pytest.raises(CancelledError):
        scan_state_counts(_trace(), HmmSettings(n_iter=50), max_states=3, cancel=requested.is_set)


def test_scan_checks_cancellation_between_state_counts(monkeypatch):
    """Finishing a scored model after cancellation does not start the next count."""
    original = GaussianHMM.bic
    requested = Event()
    counts = []

    def bic(self, *args):
        """Record the completed criterion and stop before the next model."""
        result = original(self, *args)
        counts.append(self.n_components)
        requested.set()
        return result

    monkeypatch.setattr(GaussianHMM, "bic", bic)
    with pytest.raises(CancelledError):
        scan_state_counts(_trace(), HmmSettings(n_iter=2), max_states=3, cancel=requested.is_set)
    assert counts == [1]


def test_fit_traces_propagates_preexisting_cancellation():
    """The analysis API forwards cancellation before starting estimation."""
    with pytest.raises(CancelledError):
        fit_traces(_trace(), cancel=lambda: True)
