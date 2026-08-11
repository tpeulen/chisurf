"""Tests for the in-tree Gaussian HMM (:mod:`chisurf.core.math.hmm`).

The reference points are analytical wherever one exists (a two-state chain whose
forward recursion can be written out by hand), and recovery of the generating
parameters otherwise. Nothing here depends on an external HMM package.
"""

import numpy as np
import pytest
from scipy.special import logsumexp

from chisurf.core.math import hmm
from chisurf.core.math.hmm import (
    COVARIANCE_TYPES,
    LOG_DOMAIN_FASTMATH,
    ConvergenceMonitor,
    GaussianHMM,
    _backward_log,
    _forward_log,
    _logsumexp,
    _viterbi,
)


def _reference_model(n_components=3, n_features=2):
    """Return a well-separated ground-truth model to sample from."""
    transmat = np.array(
        [[0.97, 0.02, 0.01], [0.03, 0.95, 0.02], [0.02, 0.03, 0.95]]
    )[:n_components, :n_components]
    transmat = transmat / transmat.sum(axis=1, keepdims=True)
    means = np.array([[10.0, 50.0], [30.0, 30.0], [55.0, 8.0]])[:n_components, :n_features]
    covars = np.array(
        [np.diag([9.0, 25.0]), np.diag([16.0, 16.0]), np.diag([25.0, 4.0])]
    )[:n_components, :n_features, :n_features]

    model = GaussianHMM(n_components=n_components, covariance_type="full", random_state=0)
    model.n_features = n_features
    model.startprob_ = np.full(n_components, 1.0 / n_components)
    model.transmat_ = transmat
    model.means_ = means
    model.covars_ = covars
    return model


def _matching_order(model, truth):
    """Return the permutation that lines a fitted model's states up with ``truth``.

    State labels carry no meaning, so a fit can only be compared after matching
    its states to the generating ones -- by nearest mean vector, over every
    permutation, since sorting on any single scalar is ambiguous whenever two
    states share it.
    """
    from itertools import permutations

    best, best_cost = None, np.inf
    for order in permutations(range(model.n_components)):
        cost = np.sum((model.means_[list(order)] - truth.means_) ** 2)
        if cost < best_cost:
            best, best_cost = list(order), cost
    return best


def _sorted_by_mean(model):
    """Return the state order that sorts a fitted model by total emission mean."""
    return np.argsort(model.means_.sum(axis=1))


# ---------------------------------------------------------------------------
# kernels against a direct implementation
# ---------------------------------------------------------------------------


def test_an_unexplainable_frame_stays_minus_inf_after_compilation():
    """The ``-inf`` guards must survive the compiler's fast-math licence.

    ``fastmath=True`` implies LLVM's ``ninf``, under which the compiler may
    assume no operand is infinite and folds ``if vmax == -np.inf`` away, so an
    all ``-inf`` frame -- what a structurally constrained model produces -- comes
    back as ``nan`` and poisons the whole lattice. The log-domain kernels are
    therefore compiled with every fast-math flag *except* ``nnan``/``ninf``.
    """
    assert not {"nnan", "ninf"} & LOG_DOMAIN_FASTMATH
    values = np.full(3, -np.inf)
    assert _logsumexp(values) == -np.inf
    assert _logsumexp(values) == _logsumexp.py_func(values)


def test_a_structurally_constrained_chain_fits_without_nan():
    """A left-to-right chain must stay constrained *and* keep a finite likelihood.

    Its forbidden transitions are exact zeros, i.e. ``-inf`` in log space, and
    the M-step keeps them at zero; the E-step has to carry whole ``-inf``
    columns through the lattice without turning them into ``nan``.
    """
    rng = np.random.default_rng(5)
    X = np.concatenate(
        [rng.normal(0.0, 0.3, 300), rng.normal(5.0, 0.3, 300), rng.normal(10.0, 0.3, 300)]
    )[:, None]

    model = GaussianHMM(
        n_components=3,
        covariance_type="diag",
        n_iter=100,
        random_state=0,
        params="mc",
        init_params="c",
    )
    model.n_features = 1
    model.startprob_ = np.array([1.0, 0.0, 0.0])
    model.transmat_ = np.array([[0.9, 0.1, 0.0], [0.0, 0.9, 0.1], [0.0, 0.0, 1.0]])
    model.means_ = np.array([[1.0], [4.0], [9.0]])
    model.fit(X)

    assert np.isfinite(model.score(X))
    assert np.isfinite(model.aic(X)) and np.isfinite(model.bic(X))
    np.testing.assert_allclose(model.means_.ravel(), [0.0, 5.0, 10.0], atol=0.1)
    # the constraint itself is untouched by the fit
    np.testing.assert_allclose(model.transmat_[np.tril_indices(3, -1)], 0.0)
    np.testing.assert_allclose(model.transmat_[0, 2], 0.0)


def test_forward_matches_the_recursion_written_out():
    rng = np.random.default_rng(0)
    n_samples, n_components = 40, 3
    log_startprob = np.log(np.full(n_components, 1 / n_components))
    transmat = rng.dirichlet(np.ones(n_components), size=n_components)
    log_transmat = np.log(transmat)
    log_frameprob = np.log(rng.random((n_samples, n_components)))

    fwd = np.empty((n_samples, n_components))
    log_prob = _forward_log(log_startprob, log_transmat, log_frameprob, fwd)

    expected = np.empty_like(fwd)
    expected[0] = log_startprob + log_frameprob[0]
    for t in range(1, n_samples):
        expected[t] = logsumexp(expected[t - 1][:, None] + log_transmat, axis=0)
        expected[t] += log_frameprob[t]
    np.testing.assert_allclose(fwd, expected, rtol=1e-12, atol=1e-12)
    assert log_prob == pytest.approx(logsumexp(expected[-1]))


def test_forward_and_backward_agree_on_the_likelihood():
    """Every time point must give the same total log-likelihood."""
    rng = np.random.default_rng(1)
    n_samples, n_components = 60, 4
    log_startprob = np.log(np.full(n_components, 1 / n_components))
    log_transmat = np.log(rng.dirichlet(np.ones(n_components), size=n_components))
    log_frameprob = np.log(rng.random((n_samples, n_components)))

    fwd = np.empty((n_samples, n_components))
    bwd = np.empty((n_samples, n_components))
    log_prob = _forward_log(log_startprob, log_transmat, log_frameprob, fwd)
    _backward_log(log_transmat, log_frameprob, bwd)
    per_frame = logsumexp(fwd + bwd, axis=1)
    np.testing.assert_allclose(per_frame, log_prob, rtol=1e-10)


def test_viterbi_matches_exhaustive_enumeration():
    """On a short sequence the best path can be found by brute force."""
    rng = np.random.default_rng(2)
    n_samples, n_components = 8, 3
    log_startprob = np.log(rng.dirichlet(np.ones(n_components)))
    log_transmat = np.log(rng.dirichlet(np.ones(n_components), size=n_components))
    log_frameprob = np.log(rng.random((n_samples, n_components)))

    states = np.empty(n_samples, dtype=np.int64)
    log_prob = _viterbi(log_startprob, log_transmat, log_frameprob, states)

    best_path, best_score = None, -np.inf
    for index in range(n_components**n_samples):
        path = []
        rest = index
        for _ in range(n_samples):
            path.append(rest % n_components)
            rest //= n_components
        score = log_startprob[path[0]] + log_frameprob[0, path[0]]
        for t in range(1, n_samples):
            score += log_transmat[path[t - 1], path[t]] + log_frameprob[t, path[t]]
        if score > best_score:
            best_path, best_score = path, score
    assert log_prob == pytest.approx(best_score)
    np.testing.assert_array_equal(states, best_path)


# ---------------------------------------------------------------------------
# fitting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("covariance_type", COVARIANCE_TYPES)
def test_fit_recovers_the_generating_parameters(covariance_type):
    truth = _reference_model()
    X, states = truth.sample(6000, random_state=7)

    model = GaussianHMM(
        n_components=3, covariance_type=covariance_type, n_iter=200, random_state=0
    )
    model.fit(X)
    order = _matching_order(model, truth)

    np.testing.assert_allclose(model.means_[order], truth.means_, atol=1.0)
    np.testing.assert_allclose(
        model.transmat_[np.ix_(order, order)], truth.transmat_, atol=0.03
    )
    # Relabelled the same way, the decoded path must match the true one.
    relabel = np.argsort(order)
    assert np.mean(relabel[model.predict(X)] == states) > 0.95


def test_covariances_are_recovered_in_every_layout():
    truth = _reference_model()
    X, _ = truth.sample(8000, random_state=11)
    for covariance_type, expected_shape in [
        ("full", (3, 2, 2)),
        ("diag", (3, 2)),
        ("spherical", (3,)),
        ("tied", (2, 2)),
    ]:
        model = GaussianHMM(
            n_components=3, covariance_type=covariance_type, n_iter=200, random_state=0
        ).fit(X)
        assert model.covars_.shape == expected_shape
        assert model.covars_full_.shape == (3, 2, 2)
        # Every full form must be symmetric positive definite.
        for covariance in model.covars_full_:
            np.testing.assert_allclose(covariance, covariance.T, rtol=1e-10)
            assert np.linalg.eigvalsh(covariance).min() > 0
    diag_model = GaussianHMM(
        n_components=3, covariance_type="diag", n_iter=200, random_state=0
    ).fit(X)
    variances = diag_model.covars_[_matching_order(diag_model, truth)]
    np.testing.assert_allclose(variances, [[9, 25], [16, 16], [25, 4]], rtol=0.2)


def test_log_likelihood_never_decreases():
    truth = _reference_model()
    X, _ = truth.sample(2000, random_state=3)
    for accelerate in (False, True):
        model = GaussianHMM(
            n_components=3,
            covariance_type="full",
            n_iter=60,
            tol=-np.inf,
            random_state=0,
            accelerate=accelerate,
        )
        scores = []

        original = ConvergenceMonitor.report

        def record(self, log_prob, _original=original):
            scores.append(log_prob)
            return _original(self, log_prob)

        ConvergenceMonitor.report = record
        try:
            model.fit(X)
        finally:
            ConvergenceMonitor.report = original
        assert np.all(np.diff(scores) > -1e-6), f"accelerate={accelerate}: {np.diff(scores)}"


def test_acceleration_reaches_the_same_optimum_with_fewer_maps():
    """SQUAREM must not change the answer, only the number of EM maps."""
    truth = _reference_model()
    X, _ = truth.sample(4000, random_state=5)
    kwargs = dict(n_components=3, covariance_type="full", n_iter=500, random_state=0)
    plain = GaussianHMM(accelerate=False, **kwargs).fit(X)
    fast = GaussianHMM(accelerate=True, **kwargs).fit(X)

    assert fast.score(X) >= plain.score(X) - 1.0
    assert fast.monitor_.iter <= plain.monitor_.iter
    np.testing.assert_allclose(
        fast.means_[_sorted_by_mean(fast)], plain.means_[_sorted_by_mean(plain)], atol=0.5
    )


def test_score_matches_a_hand_computed_two_state_likelihood():
    """A three-sample, two-state model is small enough to sum over all paths."""
    model = GaussianHMM(n_components=2, covariance_type="diag")
    model.n_features = 1
    model.startprob_ = np.array([0.6, 0.4])
    model.transmat_ = np.array([[0.7, 0.3], [0.2, 0.8]])
    model.means_ = np.array([[0.0], [5.0]])
    model.covars_ = np.array([[1.0], [4.0]])

    X = np.array([[0.2], [4.4], [5.1]])

    def emission(state, x):
        variance = model.covars_[state, 0]
        return np.exp(-0.5 * (x - model.means_[state, 0]) ** 2 / variance) / np.sqrt(
            2 * np.pi * variance
        )

    total = 0.0
    for a in range(2):
        for b in range(2):
            for c in range(2):
                total += (
                    model.startprob_[a]
                    * emission(a, X[0, 0])
                    * model.transmat_[a, b]
                    * emission(b, X[1, 0])
                    * model.transmat_[b, c]
                    * emission(c, X[2, 0])
                )
    assert model.score(X) == pytest.approx(np.log(total))
    # ... and the best single path is a lower bound on the total.
    assert model.decode(X)[0] < model.score(X)


def test_posteriors_sum_to_one_and_map_decoding_follows_them():
    truth = _reference_model()
    X, _ = truth.sample(500, random_state=13)
    model = GaussianHMM(n_components=3, covariance_type="full", n_iter=50, random_state=0)
    model.fit(X)
    log_prob, posteriors = model.score_samples(X)
    np.testing.assert_allclose(posteriors.sum(axis=1), 1.0, rtol=1e-10)
    assert log_prob == pytest.approx(model.score(X))
    np.testing.assert_array_equal(
        model.decode(X, algorithm="map")[1], posteriors.argmax(axis=1)
    )


def test_multiple_sequences_are_not_joined_across_their_boundaries():
    truth = _reference_model()
    first, _ = truth.sample(1500, random_state=17)
    second, _ = truth.sample(1500, random_state=19)
    X = np.concatenate([first, second])
    lengths = [len(first), len(second)]

    model = GaussianHMM(
        n_components=3, covariance_type="full", n_iter=100, random_state=0
    ).fit(X, lengths)
    # The likelihood of the split fit is the sum of the per-sequence ones.
    assert model.score(X, lengths) == pytest.approx(
        model.score(first) + model.score(second)
    )
    with pytest.raises(ValueError, match="lengths sum to"):
        model.score(X, [10, 20])


def test_a_one_dimensional_input_is_accepted_as_a_column():
    rng = np.random.default_rng(23)
    x = np.concatenate([rng.normal(0, 1, 400), rng.normal(8, 1, 400)])
    model = GaussianHMM(n_components=2, covariance_type="full", n_iter=100, random_state=0)
    model.fit(x)
    assert model.means_.shape == (2, 1)
    np.testing.assert_allclose(np.sort(model.means_.ravel()), [0, 8], atol=0.5)


def test_bic_selects_the_number_of_states_that_generated_the_data():
    truth = _reference_model(n_components=2, n_features=1)
    X, _ = truth.sample(4000, random_state=29)
    bics = [
        GaussianHMM(
            n_components=n, covariance_type="full", n_iter=200, random_state=0
        ).fit(X).bic(X)
        for n in range(1, 5)
    ]
    assert int(np.argmin(bics)) + 1 == 2
    model = GaussianHMM(n_components=2, covariance_type="full", n_iter=200, random_state=0)
    model.fit(X)
    # AIC and BIC differ only in how they charge for the parameters.
    assert model.bic(X) - model.aic(X) == pytest.approx(
        model.n_parameters * (np.log(len(X)) - 2)
    )


def test_frozen_parameters_are_left_untouched():
    truth = _reference_model()
    X, _ = truth.sample(1500, random_state=31)
    means = truth.means_ + 0.5
    model = GaussianHMM(
        n_components=3,
        covariance_type="full",
        n_iter=50,
        random_state=0,
        params="stc",
        init_params="stc",
    )
    model.n_features = 2
    model.means_ = means.copy()
    model.fit(X)
    np.testing.assert_allclose(model.means_, means)


def test_a_state_without_posterior_mass_does_not_poison_the_fit():
    """More states than the data supports must degrade, not produce nan."""
    rng = np.random.default_rng(37)
    X = rng.normal(0.0, 1.0, size=(600, 1))
    model = GaussianHMM(n_components=6, covariance_type="full", n_iter=100, random_state=0)
    model.fit(X)
    assert np.isfinite(model.means_).all()
    assert np.isfinite(model.covars_).all()
    assert np.isfinite(model.score(X))


def test_stationary_distribution_is_the_left_eigenvector():
    model = GaussianHMM(n_components=3)
    model.transmat_ = np.array([[0.9, 0.05, 0.05], [0.1, 0.8, 0.1], [0.2, 0.2, 0.6]])
    stationary = model.get_stationary_distribution()
    assert stationary.sum() == pytest.approx(1.0)
    np.testing.assert_allclose(stationary @ model.transmat_, stationary, rtol=1e-10)


def test_invalid_configurations_are_rejected():
    with pytest.raises(ValueError, match="covariance_type"):
        GaussianHMM(n_components=2, covariance_type="banana")
    with pytest.raises(ValueError, match="algorithm"):
        GaussianHMM(n_components=2, algorithm="beam")
    model = GaussianHMM(n_components=2, covariance_type="full")
    model.n_features = 1
    model.startprob_ = np.array([0.5, 0.7])
    model.transmat_ = np.eye(2)
    model.means_ = np.zeros((2, 1))
    model.covars_ = np.ones((2, 1, 1))
    with pytest.raises(ValueError, match="startprob_ must sum to 1"):
        model._check_parameters()
    with pytest.raises(ValueError, match="NaN"):
        GaussianHMM(n_components=2).fit(np.array([[1.0], [np.nan]]))


def test_a_fit_is_reproducible_for_a_fixed_seed():
    truth = _reference_model()
    X, _ = truth.sample(1200, random_state=41)
    first = GaussianHMM(n_components=3, covariance_type="full", random_state=4).fit(X)
    second = GaussianHMM(n_components=3, covariance_type="full", random_state=4).fit(X)
    np.testing.assert_allclose(first.means_, second.means_, rtol=1e-12)
    np.testing.assert_allclose(first.transmat_, second.transmat_, rtol=1e-12)


def test_an_impossible_sequence_contributes_no_transition_counts():
    """An ``-inf`` log-likelihood must not poison the shared xi accumulator.

    ``_backward_posteriors_xi`` scales its transition counts by
    ``exp(maximum + fwd[t, i] - log_prob)``. When the whole sequence is
    impossible that is ``exp(-inf + -inf - -inf)`` — ``exp(nan)`` — and because
    ``xi_sum`` is the accumulator *shared by every sequence* in the E-step, one
    such sequence turns the entire transition matrix into ``nan``, then the
    M-step, then every iteration after it.

    It hid because the posteriors survive: their uniform fallback triggers on
    the ``nan`` total and returns clean numbers, so the only visible symptom
    was a model that stopped improving.
    """
    n_samples, n_components = 40, 3
    rng = np.random.default_rng(6)
    log_startprob = np.log(np.full(n_components, 1.0 / n_components))
    log_transmat = np.log(rng.dirichlet(np.ones(n_components) * 8, size=n_components))
    log_frameprob = np.log(rng.uniform(1e-6, 1.0, (n_samples, n_components)))
    log_frameprob[17, :] = -np.inf          # no state can explain this frame

    fwd = np.empty((n_samples, n_components))
    log_prob = hmm._forward_log(log_startprob, log_transmat, log_frameprob, fwd)
    assert log_prob == -np.inf

    posteriors = np.empty((n_samples, n_components))
    xi_sum = np.zeros((n_components, n_components))
    hmm._backward_posteriors_xi(
        log_transmat, log_frameprob, fwd, log_prob, posteriors, xi_sum
    )

    assert not np.isnan(xi_sum).any(), "an impossible sequence poisoned xi_sum"
    assert not np.isnan(posteriors).any()
    # Contributing nothing is the right answer, not merely a finite number.
    np.testing.assert_array_equal(xi_sum, np.zeros((n_components, n_components)))


def test_a_possible_sequence_still_accumulates_after_an_impossible_one():
    """The guard must not switch off counting for the sequences that are fine."""
    n_samples, n_components = 30, 3
    rng = np.random.default_rng(7)
    log_startprob = np.log(np.full(n_components, 1.0 / n_components))
    log_transmat = np.log(rng.dirichlet(np.ones(n_components) * 8, size=n_components))
    good = np.log(rng.uniform(1e-6, 1.0, (n_samples, n_components)))
    bad = good.copy()
    bad[5, :] = -np.inf

    xi_sum = np.zeros((n_components, n_components))
    for frames in (bad, good):
        fwd = np.empty((n_samples, n_components))
        lp = hmm._forward_log(log_startprob, log_transmat, frames, fwd)
        posteriors = np.empty((n_samples, n_components))
        hmm._backward_posteriors_xi(log_transmat, frames, fwd, lp, posteriors, xi_sum)

    assert not np.isnan(xi_sum).any()
    assert xi_sum.sum() > 0.0, "the possible sequence contributed nothing"
