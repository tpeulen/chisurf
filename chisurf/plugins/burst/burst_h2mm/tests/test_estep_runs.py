"""The Baum-Welch E-step must run at all.

``_estep`` sized its per-chunk accumulators from ``get_num_threads()``, a numba
symbol that went away with the numba kernels this module used to carry. Nothing
imported it any more, so the call raised ``NameError`` and **every** H2MM fit
failed -- ``fit_states``, the GUI tool, the burst export, the guide's worked
example.

This was not invisible: ``test_h2mm_engine.py`` was already failing 8 of its 14
tests at the time it was found. It went unnoticed because nobody ran that file.
This module is the short, named regression that says what broke and why, so the
next reader of a ``NameError`` in the E-step does not have to re-derive it.

The chunk loop is serial now, so one chunk is the whole partition and the
arithmetic is unchanged; these tests pin "it runs, and it converges on a problem
whose answer is known" rather than any thread count.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_h2mm.core import h2mm


def _two_state_bursts(n_bursts: int = 40, seed: int = 0):
    """Bursts alternating between a low- and a high-FRET state.

    Parameters
    ----------
    n_bursts : int
        How many bursts to simulate.
    seed : int
        Seed for the photon draw, so the assertions below are deterministic.

    Returns
    -------
    BurstPhotons
        Engine-layout photons whose true state alternates burst by burst.
    """
    rng = np.random.default_rng(seed)
    times, streams = [], []
    clock = 0
    for index in range(n_bursts):
        efficiency = 0.25 if index % 2 == 0 else 0.75
        burst_times, burst_streams = [], []
        for _ in range(int(rng.integers(60, 160))):
            clock += int(rng.integers(1, 40))
            burst_times.append(clock)
            burst_streams.append(1 if rng.random() < efficiency else 0)
        times.append(np.asarray(burst_times, dtype=np.int64))
        streams.append(np.asarray(burst_streams, dtype=np.int64))
        clock += 5000
    return h2mm.prepare_bursts(times, streams, n_streams=2)


def test_fitting_two_states_does_not_raise():
    """The regression itself: this used to be a NameError, not a poor fit."""
    data = _two_state_bursts()
    assert h2mm.fit_states(data, 2, n_restarts=1, max_iter=100, seed=0) is not None


def test_the_recovered_states_match_the_simulated_ones():
    """Running is not enough -- the E-step has to accumulate the right sums.

    A partition bug that dropped or double-counted a chunk would still "run",
    so the check is that the two recovered states straddle the two simulated
    emission probabilities rather than collapsing onto one.
    """
    data = _two_state_bursts()
    fit = h2mm.fit_states(data, 2, n_restarts=1, max_iter=300, seed=0)
    path, _ = h2mm.viterbi(fit, data)

    assert path.shape == data.streams.shape
    assert set(np.unique(path)) <= {0, 1}
    # Both states are used; a collapsed fit puts every photon in one of them.
    assert len(set(np.unique(path))) == 2

    fractions = sorted(
        float(np.mean(data.streams[path == state] == 1))
        for state in np.unique(path)
    )
    assert fractions[0] == pytest.approx(0.25, abs=0.12), fractions
    assert fractions[1] == pytest.approx(0.75, abs=0.12), fractions
