"""The C++-backend fallback must not swallow a user's stop (RF-537).

A stop is delivered by raising :class:`concurrent.futures.CancelledError` out of
the per-EM-map ``on_iter`` callback. That exception is an ordinary ``Exception``,
so a bare ``except Exception`` around the tttrlib call would catch it and restart
the very same work on the numba engine instead of stopping. These tests pin both
halves of the contract: cancellation propagates, a genuine backend failure still
falls back (and says so).
"""

from __future__ import annotations

import concurrent.futures
import logging

import numpy as np
import pytest

from chisurf.plugins.burst.burst_h2mm.core import engines, h2mm


class _Raiser:
    """Stand-in for the tttrlib engine module whose calls raise *exc*."""

    def __init__(self, exc: BaseException):
        self._exc = exc
        self.calls = 0

    def fit_states(self, *args, **kwargs):
        """Raise the configured exception instead of fitting."""
        self.calls += 1
        raise self._exc

    def viterbi(self, *args, **kwargs):
        """Raise the configured exception instead of decoding."""
        self.calls += 1
        raise self._exc


@pytest.fixture
def data() -> h2mm.BurstPhotons:
    """Two tiny bursts in engine layout — never actually fitted here."""
    times = [np.array([0, 5, 9]), np.array([0, 3])]
    streams = [np.array([0, 1, 0]), np.array([1, 0])]
    return h2mm.prepare_bursts(times, streams, n_streams=2)


@pytest.fixture
def numba_sentinel(monkeypatch):
    """Replace the numba engines with counters so no real fit runs."""
    calls = {"fit_states": 0, "viterbi": 0}

    def fake_fit_states(*args, **kwargs):
        calls["fit_states"] += 1
        return "numba-model"

    def fake_viterbi(*args, **kwargs):
        calls["viterbi"] += 1
        return ("numba-path", -1.0)

    # `_fit_states_numba`, not `fit_states`: since the backend selector grew a
    # routed `fit_states`, the bare name is the router and patching it would
    # stub out the very dispatch these tests exercise. The private name is the
    # fallback engine, matching `_viterbi_numba` beside it.
    monkeypatch.setattr(engines, "_fit_states_numba", fake_fit_states)
    monkeypatch.setattr(engines, "_viterbi_numba", fake_viterbi)
    return calls


def _use_backend(monkeypatch, stub) -> None:
    """Force the tttrlib fast path onto *stub*."""
    monkeypatch.setattr(engines, "_tttrlib_engine", stub)
    monkeypatch.setattr(engines, "_HAVE_TTTRLIB", True)
    monkeypatch.delenv("CHISURF_H2MM_BACKEND", raising=False)


def test_fit_one_propagates_cancellation(monkeypatch, data, numba_sentinel):
    """A stop raised inside the backend reaches the caller, unfitted."""
    stub = _Raiser(concurrent.futures.CancelledError())
    _use_backend(monkeypatch, stub)

    with pytest.raises(concurrent.futures.CancelledError):
        engines.fit_one(data, 2, "em", on_iter=lambda done, total: None)

    assert stub.calls == 1
    assert numba_sentinel["fit_states"] == 0, "stop must not restart on numba"


def test_fit_one_falls_back_on_backend_failure(monkeypatch, caplog, data, numba_sentinel):
    """A real backend error still falls back to numba — and is logged."""
    stub = _Raiser(RuntimeError("no H2MM in this build"))
    _use_backend(monkeypatch, stub)

    with caplog.at_level(logging.WARNING, logger=engines.logger.name):
        assert engines.fit_one(data, 2, "em") == "numba-model"

    assert numba_sentinel["fit_states"] == 1
    assert "no H2MM in this build" in caplog.text


def test_viterbi_propagates_cancellation(monkeypatch, data, numba_sentinel):
    """Viterbi decoding stops on cancellation instead of redoing it on numba."""
    stub = _Raiser(concurrent.futures.CancelledError())
    _use_backend(monkeypatch, stub)

    with pytest.raises(concurrent.futures.CancelledError):
        engines.viterbi(h2mm.factory_model(2, 2), data)

    assert numba_sentinel["viterbi"] == 0


def test_viterbi_falls_back_on_backend_failure(monkeypatch, data, numba_sentinel):
    """A broken backend degrades to the numba decoder."""
    stub = _Raiser(ValueError("bad model"))
    _use_backend(monkeypatch, stub)

    assert engines.viterbi(h2mm.factory_model(2, 2), data) == ("numba-path", -1.0)
    assert numba_sentinel["viterbi"] == 1
