"""Synthetic-data tests of the ported VBEM / empirical-Bayes loop."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_ebfret.core import ebayes, hmm
from chisurf.plugins.burst.burst_ebfret.core.analysis import analyse
from chisurf.plugins.burst.burst_ebfret.core.model import Analysis


def _simulate(means, trans, lengths, noise=0.05, seed=0):
    """Generate Gaussian-emission HMM traces with known state means."""
    rng = np.random.default_rng(seed)
    n_states = len(means)
    traces, truths = [], []
    for length in lengths:
        states = np.empty(length, dtype=int)
        states[0] = rng.integers(n_states)
        for t in range(1, length):
            states[t] = rng.choice(n_states, p=trans[states[t - 1]])
        traces.append(np.array(means)[states] + rng.normal(0, noise, size=length))
        truths.append(states)
    return traces, truths


TRANS2 = np.array([[0.95, 0.05], [0.05, 0.95]])


def _run(generator):
    """Drain a run_ebayes generator, returning (events, return value)."""
    events = []
    while True:
        try:
            events.append(next(generator))
        except StopIteration as stop:
            return events, stop.value


def test_single_trace_vbayes_recovers_two_states():
    traces, truths = _simulate([0.25, 0.75], TRANS2, [400], seed=1)
    u = hmm.guess_prior(traces, 2)
    w, L, _ = hmm.vbayes(traces[0], hmm.init_posterior(traces[0], u), u)
    assert np.all(np.diff(L[1:]) > -1e-9 * np.abs(L[2:]))
    np.testing.assert_allclose(np.sort(w.mu), [0.25, 0.75], atol=0.03)
    state, mean = hmm.viterbi_vb(w, traces[0])
    assert set(np.unique(state)) <= {1, 2}
    decoded = (mean > 0.5).astype(int)
    assert np.mean(decoded == truths[0]) > 0.95


def test_guess_prior_counts_excluded_series_in_the_mean_length():
    traces, _ = _simulate([0.25, 0.75], TRANS2, [100, 100], seed=2)
    with_gap = hmm.guess_prior([traces[0], None, traces[1]], 2)
    without = hmm.guess_prior(traces, 2)
    # dwell prior tau = 0.5 * mean(T): 50 without the gap, 33.3 with it
    assert with_gap.A[0, 0] / with_gap.A[0].sum() < without.A[0, 0] / without.A[0].sum()
    np.testing.assert_allclose(with_gap.mu, without.mu)


def test_vbayes_series_keeps_the_better_restart_and_flags_invalid_fits():
    traces, _ = _simulate([0.25, 0.75], TRANS2, [200], seed=3)
    u = hmm.guess_prior(traces, 2)
    rng = np.random.default_rng(0)
    fit = hmm.vbayes_series(traces[0], u, None, 3, 1e-3, rng)
    assert fit["expect"] is not None and fit["viterbi"] is not None
    assert 1 <= fit["restart"] <= 3  # 1-based restart; 0 would be the previous posterior
    assert fit["viterbi"].state.size == traces[0].size
    with pytest.raises(ValueError):
        hmm.vbayes_series(traces[0], u, None, 0, 1e-3, rng)
    bad = u.copy()
    bad.W = -bad.W
    invalid = hmm.vbayes_series(traces[0], bad, bad, 0, 1e-3, rng)
    assert invalid["restart"] == -1 and invalid["expect"] is None


def test_run_ebayes_recovers_means_and_skips_excluded_series():
    traces, _ = _simulate([0.3, 0.7], TRANS2, [150] * 8, seed=4)
    signals = [*traces[:4], None, *traces[4:]]
    analysis = Analysis(states=2, prior=hmm.guess_prior(signals, 2))
    events, history = _run(
        ebayes.run_ebayes(
            analysis, signals, restarts=1, precision=1e-4, rng=np.random.default_rng(0)
        )
    )
    iterations = [e for e in events if e["kind"] == "iteration"]
    assert len(iterations) == len(history) >= 2
    assert history[-1] >= history[0]
    np.testing.assert_allclose(np.sort(analysis.prior.mu), [0.3, 0.7], atol=0.03)
    assert analysis.posterior[4] is None and analysis.viterbi[4] is None
    assert len(analysis.posterior) == len(signals)


def test_run_ebayes_stops_when_asked():
    traces, _ = _simulate([0.3, 0.7], TRANS2, [100] * 30, seed=5)
    analysis = Analysis(states=2, prior=hmm.guess_prior(traces, 2))
    prior_before = analysis.prior.copy()
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 1

    events, history = _run(ebayes.run_ebayes(analysis, traces, restarts=1, should_stop=stop))
    # the first batch of 24 ran, the second was refused, and the prior was
    # never updated because the loop stopped before its h-step
    assert [e["kind"] for e in events][0] == "batch"
    assert sum(analysis.posterior[n] is not None for n in range(30)) == 24
    np.testing.assert_array_equal(analysis.prior.mu, prior_before.mu)
    assert len(history) == 1


def test_analyse_selects_and_decodes():
    traces, _ = _simulate([0.25, 0.75], TRANS2, [150] * 6, seed=6)
    result = analyse(traces, min_states=2, max_states=3, max_iter=10, restarts=1)
    assert set(result.scan) == {2, 3}
    assert result.scan[result.n_states] == max(result.scan.values())
    K = result.n_states
    assert result.transition_counts.shape == (K, K)
    assert sum(s.occupancy for s in result.states) == pytest.approx(1.0)
    assert result.dwells and all(0 <= d.state < K for d in result.dwells)
    assert np.all(np.diff(result.state_means) > 0)
    # the two occupied levels are the simulated ones
    occupied = [s.mean for s in result.states if s.occupancy > 0.1]
    np.testing.assert_allclose(occupied, [0.25, 0.75], atol=0.03)
