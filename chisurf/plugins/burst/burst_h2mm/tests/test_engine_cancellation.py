"""A user's stop must reach the caller, not be mistaken for a backend problem.

A stop is delivered by raising :class:`concurrent.futures.CancelledError` out of
the per-EM-map ``on_iter`` callback. That exception is an ordinary
``Exception``, so a bare ``except Exception`` around the engine call would catch
it and treat a deliberate stop as a failure.

This file used to pin *two* halves: cancellation propagates, and a genuine
backend failure falls back to the second engine. The second half is gone with
that engine (2026-08-31) --- there is nothing to fall back to, and a failure is
now raised rather than downgraded to a slower path. So what is pinned here is
that nothing swallows an exception on the way out: neither a stop nor a real
error.
"""

from __future__ import annotations

import concurrent.futures

import numpy as np
import pytest

from chisurf.plugins.burst.burst_h2mm.core import engines, h2mm


class _Raiser:
    """Stand-in for the engine module whose calls raise *exc*."""

    def __init__(self, exc: BaseException):
        self._exc = exc
        self.calls = 0

    def fit_states(self, *args, **kwargs):
        """Raise the configured exception instead of fitting."""
        self.calls += 1
        raise self._exc

    def optimize(self, *args, **kwargs):
        """Raise the configured exception instead of optimising."""
        self.calls += 1
        raise self._exc

    def viterbi(self, *args, **kwargs):
        """Raise the configured exception instead of decoding."""
        self.calls += 1
        raise self._exc

    #: The router asks this before calling anything.
    HAVE_TTTRLIB = True


@pytest.fixture
def data() -> h2mm.BurstPhotons:
    """Two tiny bursts in engine layout — never actually fitted here."""
    times = [np.array([0, 5, 9]), np.array([0, 3])]
    streams = [np.array([0, 1, 0]), np.array([1, 0])]
    return h2mm.prepare_bursts(times, streams, n_streams=2)


def _use_engine(monkeypatch, stub) -> None:
    """Put *stub* in the engine's place."""
    monkeypatch.setattr(engines, "_tttrlib_engine", stub)


@pytest.mark.parametrize("call", ["fit_one", "optimize", "viterbi"])
def test_cancellation_reaches_the_caller(monkeypatch, data, call):
    """A stop raised inside the engine is not converted into anything else."""
    _use_engine(monkeypatch, _Raiser(concurrent.futures.CancelledError()))

    with pytest.raises(concurrent.futures.CancelledError):
        if call == "fit_one":
            engines.fit_one(data, 2, "em")
        elif call == "optimize":
            engines.optimize(h2mm.factory_model(2, 2), data, max_iter=1)
        else:
            engines.viterbi(h2mm.factory_model(2, 2), data)


@pytest.mark.parametrize("call", ["fit_one", "optimize", "viterbi"])
def test_a_real_engine_error_is_raised_rather_than_downgraded(monkeypatch, data, call):
    """There is no second engine to retry on, so the error must surface.

    It used to be logged and answered on the fallback engine, which made a
    broken build look like a working one that happened to be slow.
    """
    _use_engine(monkeypatch, _Raiser(RuntimeError("no H2MM in this build")))

    with pytest.raises(RuntimeError, match="no H2MM in this build"):
        if call == "fit_one":
            engines.fit_one(data, 2, "em")
        elif call == "optimize":
            engines.optimize(h2mm.factory_model(2, 2), data, max_iter=1)
        else:
            engines.viterbi(h2mm.factory_model(2, 2), data)


def test_a_missing_engine_says_so(monkeypatch, data):
    """Without the compiled engine, H2MM explains itself instead of failing oddly."""

    class _Absent:
        HAVE_TTTRLIB = False

    _use_engine(monkeypatch, _Absent())
    with pytest.raises(RuntimeError, match="tttrlib"):
        engines.fit_one(data, 2, "em")
