"""Fast synthetic-data tests for the ebFRET VBEM / empirical-Bayes core."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_ebfret.core.ebayes import ebayes, init_prior
from chisurf.plugins.burst.burst_ebfret.core.vbem import vbem_single
from chisurf.plugins.burst.burst_ebfret.core.viterbi import viterbi


def _simulate(means, trans, lengths, noise=0.05, seed=0):
    """Generate Gaussian-emission HMM traces with known state means."""
    rng = np.random.default_rng(seed)
    n_states = len(means)
    traces = []
    truths = []
    for length in lengths:
        states = np.empty(length, dtype=int)
        states[0] = rng.integers(n_states)
        for t in range(1, length):
            states[t] = rng.choice(n_states, p=trans[states[t - 1]])
        x = np.array(means)[states] + rng.normal(0, noise, size=length)
        traces.append(x)
        truths.append(states)
    return traces, truths


def test_single_trace_vbem_recovers_two_states():
    """A single two-state trace recovers well-separated means."""
    means = [0.25, 0.75]
    trans = np.array([[0.95, 0.05], [0.05, 0.95]])
    traces, _ = _simulate(means, trans, [400], noise=0.05, seed=1)
    prior = init_prior(traces, 2)
    result = vbem_single(traces[0], prior)
    recovered = np.sort(result.posterior.m)
    assert result.converged
    assert np.allclose(recovered, means, atol=0.05)


def test_ebayes_recovers_three_states_and_is_finite():
    """Empirical Bayes over many traces recovers three ordered states."""
    means = [0.2, 0.5, 0.8]
    trans = np.array([[0.9, 0.05, 0.05], [0.05, 0.9, 0.05], [0.05, 0.05, 0.9]])
    lengths = [150] * 30
    traces, _ = _simulate(means, trans, lengths, noise=0.05, seed=2)
    fit = ebayes(traces, 3, max_iter=15)
    recovered = fit.state_means
    assert np.all(np.isfinite(fit.evidence_history))
    assert np.all(np.diff(recovered) > 0)  # states are distinct and ordered
    assert np.allclose(recovered, means, atol=0.06)


def test_evidence_is_nondecreasing_overall():
    """The empirical-Bayes evidence should trend upward over iterations."""
    means = [0.3, 0.7]
    trans = np.array([[0.9, 0.1], [0.1, 0.9]])
    traces, _ = _simulate(means, trans, [120] * 20, noise=0.06, seed=3)
    fit = ebayes(traces, 2, max_iter=12)
    history = np.array(fit.evidence_history)
    assert history[-1] >= history[0] - 1e-6


def test_viterbi_labels_match_simulation():
    """Viterbi decoding recovers the simulated state sequence up to labelling."""
    means = [0.2, 0.8]
    trans = np.array([[0.97, 0.03], [0.03, 0.97]])
    traces, truths = _simulate(means, trans, [500], noise=0.04, seed=4)
    prior = init_prior(traces, 2)
    result = vbem_single(traces[0], prior)
    states, state_means = viterbi(traces[0], result.posterior)
    # Align decoded labels to the ascending-mean order before comparing.
    order = np.argsort(result.posterior.m)
    rank = np.empty_like(order)
    rank[order] = np.arange(order.size)
    decoded = rank[states]
    agreement = np.mean(decoded == truths[0])
    assert max(agreement, 1 - agreement) > 0.9
    assert state_means.shape == traces[0].shape


@pytest.mark.parametrize("n_states", [2, 3, 4])
def test_init_prior_shapes(n_states):
    """Prior initialisation yields consistently shaped hyper-parameters."""
    traces = [np.random.default_rng(0).random(50) for _ in range(5)]
    prior = init_prior(traces, n_states)
    assert prior.m.shape == (n_states,)
    assert prior.A.shape == (n_states, n_states)
    assert np.all(np.diff(prior.m) >= 0)  # quantile means are sorted
