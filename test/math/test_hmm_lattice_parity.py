"""The delegated HMM lattice must return what the numba kernels returned.

``chisurf.core.math.hmm`` compiled its forward/backward/posteriors/Viterbi
recursions with numba; they are now the photon library's. The reference is a
committed fixture recorded from the numba originals **before** they were
deleted — not a live comparison, which becomes a skip the day numba leaves the
environment, and a skip reads like a pass.

The fixture is not only self-referential: every case in it was cross-checked
against hmmlearn, whose lattices came out bit-identical. See
``build_tools/dev_utils/hmm_lattice_fixture.py``, which regenerates it and
re-runs that check.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.math import hmm

_FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "data" / "numba_parity" / "hmm_lattice.npz"

#: The lattices are a different compilation of the same recursion, so they are
#: exact. Posteriors and xi are accumulated in the same order too, but the
#: normalisation divides, so allow a few ulp.
_TOL = 1e-12


@pytest.fixture(scope="module")
def cases():
    """The recorded (input, output) pairs."""
    if not _FIXTURE.is_file():
        pytest.skip(f"missing fixture {_FIXTURE}")
    # No allow_pickle: `names` is stored as fixed-width unicode precisely so a
    # test suite never has to ask for it.
    with np.load(_FIXTURE) as data:
        n = int(data["n_cases"])
        names = [str(x) for x in data["names"]]
        return [
            {
                "name": names[i],
                **{
                    k: data[f"{k}_{i}"]
                    for k in (
                        "log_startprob",
                        "log_transmat",
                        "log_frameprob",
                        "fwd",
                        "bwd",
                        "log_prob",
                        "posteriors",
                        "xi_sum",
                        "states",
                        "viterbi_logprob",
                    )
                },
            }
            for i in range(n)
        ]


def test_the_fixture_covers_the_degenerate_shapes(cases):
    """A parity fixture of well-behaved inputs proves the easy half only."""
    names = {c["name"] for c in cases}
    assert {
        "all_inf_frame",
        "dead_state_column",
        "forbidden_transitions",
        "zero_startprob",
        "single_sample",
        "combined_degeneracies",
    } <= names
    assert sum(np.isneginf(c["log_prob"]) for c in cases) >= 2, "no impossible sequence"
    assert any(c["log_frameprob"].shape[0] == 1 for c in cases), "no single-sample case"


def test_the_forward_lattice_matches_the_numba_reference(cases):
    """Same lattice and same log-likelihood, including where it is ``-inf``."""
    for c in cases:
        fwd = np.empty_like(c["fwd"])
        log_prob = hmm._forward_log(c["log_startprob"], c["log_transmat"], c["log_frameprob"], fwd)
        if np.isneginf(c["log_prob"]):
            assert np.isneginf(log_prob), c["name"]
        else:
            assert log_prob == pytest.approx(float(c["log_prob"]), abs=_TOL), c["name"]
        np.testing.assert_allclose(fwd, c["fwd"], rtol=0, atol=_TOL, err_msg=c["name"])


def test_the_backward_lattice_matches_the_numba_reference(cases):
    """The standalone backward recursion, which the fused sweep does not expose."""
    for c in cases:
        bwd = np.empty_like(c["bwd"])
        hmm._backward_log(c["log_transmat"], c["log_frameprob"], bwd)
        np.testing.assert_allclose(bwd, c["bwd"], rtol=0, atol=_TOL, err_msg=c["name"])


def test_the_posteriors_and_transition_counts_match(cases):
    """The fused sweep: state posteriors and expected transition counts."""
    for c in cases:
        fwd = np.array(c["fwd"], copy=True)
        posteriors = np.empty_like(c["posteriors"])
        xi_sum = np.zeros_like(c["xi_sum"])
        hmm._backward_posteriors_xi(
            c["log_transmat"],
            c["log_frameprob"],
            fwd,
            float(c["log_prob"]),
            posteriors,
            xi_sum,
        )
        assert not np.isnan(posteriors).any(), c["name"]
        assert not np.isnan(xi_sum).any(), c["name"]
        np.testing.assert_allclose(
            posteriors, c["posteriors"], rtol=0, atol=_TOL, err_msg=c["name"]
        )
        np.testing.assert_allclose(xi_sum, c["xi_sum"], rtol=0, atol=_TOL, err_msg=c["name"])


def test_an_impossible_sequence_still_contributes_no_transition_counts(cases):
    """The bug this fixture was built to avoid enshrining, on the other side."""
    impossible = [c for c in cases if np.isneginf(c["log_prob"])]
    assert impossible, "the fixture lost its impossible cases"
    for c in impossible:
        posteriors = np.empty_like(c["posteriors"])
        xi_sum = np.zeros_like(c["xi_sum"])
        hmm._backward_posteriors_xi(
            c["log_transmat"],
            c["log_frameprob"],
            np.array(c["fwd"], copy=True),
            float(c["log_prob"]),
            posteriors,
            xi_sum,
        )
        np.testing.assert_array_equal(xi_sum, np.zeros_like(xi_sum), err_msg=c["name"])


def test_xi_is_accumulated_across_sequences_not_overwritten(cases):
    """Every sequence of a fit adds into one matrix; clearing it loses all but the last."""
    c = next(c for c in cases if not np.isneginf(c["log_prob"]) and c["log_frameprob"].shape[0] > 1)
    posteriors = np.empty_like(c["posteriors"])
    xi_sum = np.zeros_like(c["xi_sum"])
    for _ in range(2):
        hmm._backward_posteriors_xi(
            c["log_transmat"],
            c["log_frameprob"],
            np.array(c["fwd"], copy=True),
            float(c["log_prob"]),
            posteriors,
            xi_sum,
        )
    np.testing.assert_allclose(xi_sum, 2.0 * c["xi_sum"], rtol=0, atol=_TOL)


def test_the_viterbi_path_matches_wherever_a_path_exists(cases):
    """Where every candidate scores ``-inf`` the arg-max is arbitrary.

    Both the log-probability and the path are checked on the cases that have an
    answer; on the impossible ones only the log-probability is, because there
    the returned labels record a tie-break rather than a result.
    """
    for c in cases:
        states = np.empty(c["log_frameprob"].shape[0], dtype=np.int64)
        log_prob = hmm._viterbi(c["log_startprob"], c["log_transmat"], c["log_frameprob"], states)
        n_components = c["log_frameprob"].shape[1]
        assert states.min() >= 0 and states.max() < n_components, c["name"]
        if np.isneginf(c["viterbi_logprob"]):
            assert np.isneginf(log_prob), c["name"]
            continue
        assert log_prob == pytest.approx(float(c["viterbi_logprob"]), abs=_TOL), c["name"]
        np.testing.assert_array_equal(states, c["states"], err_msg=c["name"])


def test_a_shape_mismatch_is_rejected_rather_than_read_past(cases):
    """The buffers are written in place, so a wrong shape must not be tolerated."""
    c = cases[1]
    n_samples, n_components = c["log_frameprob"].shape
    with pytest.raises(ValueError):
        hmm._forward_log(
            c["log_startprob"],
            c["log_transmat"],
            c["log_frameprob"],
            np.empty((n_samples - 1, n_components)),
        )
