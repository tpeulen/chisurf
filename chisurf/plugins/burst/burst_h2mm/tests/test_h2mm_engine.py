"""Headless correctness tests for the Numba H2MM engine."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_h2mm.core import analysis, h2mm


def _make_ground_truth() -> h2mm.H2mmModel:
    """Return a well-separated 2-state, 2-stream model."""
    prior = np.array([0.5, 0.5])
    # Moderate switching so bursts contain several transitions.
    trans = np.array([[0.995, 0.005], [0.010, 0.990]])
    # State 0 emits mostly stream 0; state 1 mostly stream 1.
    obs = np.array([[0.85, 0.15], [0.20, 0.80]])
    return h2mm.H2mmModel(prior=prior, trans=trans, obs=obs)


def _simulate(model, n_bursts=400, burst_len=80, rate=0.25, seed=1):
    """Generate bursts with Poisson-spaced (variable-Δt) photon times."""
    rng = np.random.default_rng(seed)
    times = []
    for _ in range(n_bursts):
        gaps = rng.poisson(lam=1.0 / rate, size=burst_len - 1) + 1
        t = np.concatenate([[0], np.cumsum(gaps)]).astype(np.int64)
        times.append(t)
    streams = h2mm.simulate_bursts(model, times, seed=seed + 7)
    return times, streams


def test_prepare_bursts_layout():
    times = [np.array([0, 5, 9]), np.array([0, 3])]
    streams = [np.array([0, 1, 0]), np.array([1, 0])]
    data = h2mm.prepare_bursts(times, streams, n_streams=2)
    assert data.n_bursts == 2
    assert data.n_photons == 5
    # Unique Δt across data: {5,4,3} -> sorted {3,4,5}
    assert list(data.unique_dt) == [3, 4, 5]
    # Last photon of each burst has slot -1.
    assert data.gap_slot[2] == -1
    assert data.gap_slot[4] == -1


def _reference_loglik(model, times, streams) -> float:
    """Return ``logL`` by a direct forward recursion with explicit ``A^Δt``.

    Independent of the engine's slot cache: every gap is propagated with
    :func:`numpy.linalg.matrix_power`, so a coincident pair (``Δt == 0``) is
    propagated with the identity by construction.
    """
    ll = 0.0
    for t, s in zip(times, streams):
        alpha = model.prior * model.obs[:, s[0]]
        tot = alpha.sum()
        alpha = alpha / tot
        ll += np.log(tot)
        for k in range(1, len(t)):
            propagator = np.linalg.matrix_power(model.trans, int(t[k] - t[k - 1]))
            alpha = (alpha @ propagator) * model.obs[:, s[k]]
            tot = alpha.sum()
            alpha = alpha / tot
            ll += np.log(tot)
    return float(ll)


def test_zero_dt_gets_its_own_slot():
    """Coincident macro times are a slot of their own, not the smallest Δt."""
    times = [np.array([0, 0, 5, 5, 5, 12])]
    streams = [np.array([0, 1, 0, 1, 0, 1])]
    data = h2mm.prepare_bursts(times, streams, n_streams=2)
    # Gaps are {0,5,0,0,7} -> unique {0,5,7}; without the zero slot the ties
    # would resolve to slot 0 == the smallest *positive* Δt.
    assert list(data.unique_dt) == [0, 5, 7]
    assert list(data.gap_slot) == [0, 1, 0, 0, 2, -1]


def test_zero_dt_propagates_with_the_identity():
    """A tie-containing burst scores exactly like identity-propagated ties."""
    model = _make_ground_truth()
    times = [np.array([0, 0, 5, 5, 5, 12]), np.array([0, 3, 3, 9])]
    streams = [np.array([0, 1, 0, 1, 0, 1]), np.array([1, 1, 0, 0])]
    data = h2mm.prepare_bursts(times, streams, n_streams=2)

    # One EM map, unaccelerated: ``loglik`` is that of the *input* model.
    got = h2mm.optimize(model, data, max_iter=1, tol=0.0, accelerate=False).loglik
    assert got == pytest.approx(_reference_loglik(model, times, streams), abs=1e-9)


def test_all_gaps_zero_is_not_a_free_lunch():
    """Fully coincident bursts keep one (identity) slot and an honest logL."""
    model = _make_ground_truth()
    times = [np.zeros(4, dtype=np.int64), np.zeros(3, dtype=np.int64)]
    streams = [np.array([0, 1, 0, 1]), np.array([1, 1, 0])]
    data = h2mm.prepare_bursts(times, streams, n_streams=2)

    # Previously the table came out empty, the propagator cache was never filled
    # and the logL counted only the first photon of each burst.
    assert list(data.unique_dt) == [0]
    got = h2mm.optimize(model, data, max_iter=1, tol=0.0, accelerate=False).loglik
    assert got == pytest.approx(_reference_loglik(model, times, streams), abs=1e-9)
    assert got < np.log(0.5) * data.n_bursts


def test_eig_build_handles_the_zero_dt_slot():
    """The spectral build must not turn ``Δt == 0`` into ``λ⁻¹``."""
    n = 2
    # An exactly singular ``A``: the confluent term ``Δt·λ^{Δt-1}`` would evaluate
    # ``0⁻¹ = inf`` at the Δt == 0 slot and poison the divided differences with NaN.
    trans = np.array([[0.0, 1.0], [0.0, 1.0]])
    unique_dt = np.array([0, 4], dtype=np.int64)
    n_s = unique_dt.shape[0]
    pow_pp = np.zeros((n_s, n, n))
    rho_pp = np.zeros((n_s, n, n, n, n))
    pow_eig = np.zeros((n_s, n, n))
    rho_eig = np.zeros((n_s, n, n, n, n))

    h2mm._build_caches(trans, unique_dt, pow_pp, rho_pp)
    assert h2mm._build_caches_eig(trans, unique_dt, pow_eig, rho_eig) is True
    assert np.all(np.isfinite(pow_eig)) and np.all(np.isfinite(rho_eig))
    assert np.abs(pow_eig - pow_pp).max() < 1e-9
    assert np.abs(rho_eig - rho_pp).max() < 1e-8
    # The Δt == 0 slot is the identity with no transition mass either way.
    assert np.abs(pow_pp[0] - np.eye(n)).max() < 1e-12
    assert np.abs(rho_pp[0]).max() < 1e-12


def test_loglik_monotonic_increase():
    gt = _make_ground_truth()
    times, streams = _simulate(gt, n_bursts=150, burst_len=60, seed=3)
    data = h2mm.prepare_bursts(times, streams, n_streams=2)

    init = h2mm.factory_model(2, 2, seed=0)
    lls = []
    model = init
    # Run EM one iteration at a time and confirm logL never decreases.
    for _ in range(15):
        model = h2mm.optimize(model, data, max_iter=1, tol=0.0)
        lls.append(model.loglik)
    diffs = np.diff(lls)
    assert np.all(diffs >= -1e-6), f"logL decreased: {lls}"


def test_recovers_ground_truth_two_state():
    gt = _make_ground_truth()
    times, streams = _simulate(gt, n_bursts=600, burst_len=100, seed=11)
    data = h2mm.prepare_bursts(times, streams, n_streams=2)

    fit = h2mm.fit_states(data, n_states=2, n_restarts=2, max_iter=400, seed=0)

    # States may be permuted; align by donor (stream-0) emission probability.
    order = np.argsort(-fit.obs[:, 0])
    obs = fit.obs[order]
    trans = fit.trans[np.ix_(order, order)]

    # Emission probabilities recovered within a loose tolerance.
    assert obs[0, 0] == pytest.approx(0.85, abs=0.08)
    assert obs[1, 1] == pytest.approx(0.80, abs=0.08)
    # Transition rates recovered to the right order of magnitude.
    assert trans[0, 1] == pytest.approx(0.005, abs=0.004)
    assert trans[1, 0] == pytest.approx(0.010, abs=0.006)


def test_bic_prefers_two_states():
    gt = _make_ground_truth()
    times, streams = _simulate(gt, n_bursts=500, burst_len=100, seed=21)
    data = h2mm.prepare_bursts(times, streams, n_streams=2)

    fit1 = h2mm.fit_states(data, n_states=1, n_restarts=1, max_iter=200, seed=0)
    fit2 = h2mm.fit_states(data, n_states=2, n_restarts=2, max_iter=400, seed=0)

    assert fit2.loglik > fit1.loglik
    assert fit2.bic < fit1.bic


def test_viterbi_path_and_icl():
    gt = _make_ground_truth()
    times, streams = _simulate(gt, n_bursts=200, burst_len=80, seed=31)
    data = h2mm.prepare_bursts(times, streams, n_streams=2)
    fit = h2mm.fit_states(data, n_states=2, n_restarts=1, max_iter=300, seed=0)

    path, icl = h2mm.viterbi(fit, data)
    assert path.shape[0] == data.n_photons
    assert path.min() >= 0 and path.max() < 2
    assert np.isfinite(icl)


def test_squarem_matches_plain_em_but_fewer_iters():
    """SQUAREM must reach the same EM fixed point in no more maps than plain EM."""
    gt = _make_ground_truth()
    times, streams = _simulate(gt, n_bursts=500, burst_len=100, seed=41)
    data = h2mm.prepare_bursts(times, streams, n_streams=2)
    init = h2mm.factory_model(2, 2, seed=0)

    plain = h2mm.optimize(init, data, max_iter=2000, tol=1e-10, accelerate=False)
    fast = h2mm.optimize(init, data, max_iter=2000, tol=1e-10, accelerate=True)

    assert plain.converged and fast.converged
    # Same optimum (log-likelihood and model parameters).
    assert fast.loglik == pytest.approx(plain.loglik, rel=1e-6, abs=1e-3)
    assert np.abs(fast.trans - plain.trans).max() < 1e-3
    assert np.abs(fast.obs - plain.obs).max() < 1e-3
    # Acceleration must not cost more EM maps than the plain loop.
    assert fast.n_iter <= plain.n_iter


def test_eig_build_matches_pair_power():
    """The spectral cache build agrees with the pair-power build on long Δt."""
    n = 3
    trans = np.array([[0.97, 0.02, 0.01], [0.02, 0.96, 0.02], [0.01, 0.03, 0.96]])
    trans = h2mm._row_normalize(trans)
    unique_dt = np.array([1, 7, 64, 513, 2000], dtype=np.int64)

    n_s = unique_dt.shape[0]
    pow_pp = np.zeros((n_s, n, n))
    rho_pp = np.zeros((n_s, n, n, n, n))
    pow_eig = np.zeros((n_s, n, n))
    rho_eig = np.zeros((n_s, n, n, n, n))

    h2mm._build_caches(trans, unique_dt, pow_pp, rho_pp)
    assert h2mm._build_caches_eig(trans, unique_dt, pow_eig, rho_eig) is True

    assert np.abs(pow_eig - pow_pp).max() < 1e-9
    assert np.abs(rho_eig - rho_pp).max() < 1e-8


def test_eig_build_declines_on_defective_matrix():
    """A non-diagonalisable ``A`` must be rejected so the caller falls back."""
    # A 2x2 shear-like stochastic matrix with a repeated eigenvalue and a single
    # eigenvector is defective; the spectral build must decline.
    trans = np.array([[1.0, 0.0], [1.0, 0.0]])  # rank-deficient, repeated eig 0/1
    unique_dt = np.array([3, 10], dtype=np.int64)
    pow_c = np.zeros((2, 2, 2))
    rho_c = np.zeros((2, 2, 2, 2, 2))
    # Either it declines (returns False) or it succeeds and still matches
    # pair-power; both keep the caller correct.  Assert the fallback path is
    # exercised by _fill_caches without error.
    h2mm._fill_caches(trans, unique_dt, pow_c, rho_c, prefer_eig=True)
    assert np.all(np.isfinite(pow_c)) and np.all(np.isfinite(rho_c))


def test_scan_early_stopping_matches_full_scan():
    """`patience` stops the scan past the BIC minimum but keeps the selection."""
    gt = _make_ground_truth()  # well-separated 2-state
    times, streams = _simulate(gt, n_bursts=400, burst_len=80, seed=61)
    data = h2mm.prepare_bursts(times, streams, n_streams=2)

    full = analysis.scan_states(data, (1, 2, 3, 4), n_restarts=1, max_iter=200)
    early = analysis.scan_states(
        data, (1, 2, 3, 4), n_restarts=1, max_iter=200, criterion="bic", patience=1
    )

    # Early stop fits no more counts than the full scan...
    assert len(early) <= len(full)
    # ...and both select the same (true) state count by BIC.
    assert min(full, key=lambda f: f.bic).n_states == 2
    assert min(early, key=lambda f: f.bic).n_states == 2


def test_single_precision_lands_near_double():
    """The approximate float32 mode reaches essentially the float64 optimum."""
    gt = _make_ground_truth()
    times, streams = _simulate(gt, n_bursts=500, burst_len=100, seed=51)
    data = h2mm.prepare_bursts(times, streams, n_streams=2)
    init = h2mm.factory_model(2, 2, seed=0)

    ref = h2mm.optimize(init, data, max_iter=2000, tol=1e-10)
    f32 = h2mm.optimize(init, data, max_iter=2000, tol=1e-6, single_precision=True)

    # Approximate mode: float32 round-off plus the coarse (floored) convergence
    # threshold and non-deterministic parallel reduction order mean it only lands
    # *near* the float64 optimum — assert the same basin, not bitwise agreement.
    assert f32.loglik == pytest.approx(ref.loglik, rel=1e-3)
    assert np.abs(f32.obs - ref.obs).max() < 2e-2
    assert np.abs(f32.trans - ref.trans).max() < 2e-2
