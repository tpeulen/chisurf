"""The FCS MEM inversion runs in tttrlib's engine — pinned against the loop.

`fcs_maxent` solved its inversion with a QuickFit-style fixed-count Python
iteration; it now routes through `tttrlib.maxent_invert_weighted` — the
shared Skilling–Bryan engine behind `maxent_invert` and
`solve_tcspc_mem_lifetime`, with the weights and the prior the engine always
supported exposed (owner ruling 2026-09-02: the MEM loop belongs in
tttrlib). The deleted loop is transcribed below as the frozen reference.

The two are *the same objective* (maximise ``alpha*S(p; m) - chi2_w/2``;
the engine's ``nu = sqrt(2*alpha)``) but not the same iteration: the loop
ran a fixed count with no convergence test, the engine converges. So the
pin is on the objective, not the iterates: the engine's solution must score
**at least as well** as the loop's on the loop's own objective, and on
well-conditioned problems the reconstructions must agree.
"""
import numpy as np
import pytest

from chisurf.core.models.fcs.maxent import (
    build_diffusion_kernel, fcs_maxent, _maxent_engine_solve)


def _quickfit_reference(A, ydata, stdev, m_prior, alpha, num_iter):
    """The deleted `_quickfit_mem_iteration`, transcribed whole (with the
    SVD front-end it consumed) as this A/B's frozen reference."""
    U_np, svals, VT = np.linalg.svd(A, full_matrices=False)
    thresh = svals[0] / 100000.0
    mask = svals >= thresh
    if not np.any(mask):
        mask[0] = True
    s_count = int(mask.sum())
    svals = svals[:s_count]
    Vred = U_np[:, :s_count]
    Ured = VT[:s_count, :].T
    inv_sigma2 = 1.0 / (stdev ** 2)
    VW = Vred * inv_sigma2[:, None]
    M = (svals[:, None] * (Vred.T @ VW)) * svals[None, :]

    N = Ured.shape[0]
    s = svals.shape[0]
    m = np.where(np.asarray(m_prior, dtype=np.float64) <= 0.0, 1.0, m_prior)
    total = m.sum()
    if total <= 0.0:
        total = float(N)
    m = m / total
    stdev2 = stdev * stdev
    u = np.zeros(s)
    eye = np.eye(s)
    for _ in range(num_iter):
        work = np.clip(Ured @ u, -100.0, 100.0)
        f = m * np.exp(work)
        f = np.where(np.isfinite(f) & (f >= 0.0), f, 0.0)
        K = Ured.T @ (f.reshape(N, 1) * Ured)
        F = Vred @ (svals * (Ured.T @ f))
        gvec = svals * (Vred.T @ ((F - ydata) / stdev2))
        du = np.linalg.solve(alpha * eye + M @ K, -alpha * u - gvec)
        u = u + du
    work = np.clip(Ured @ u, -100.0, 100.0)
    f = m * np.exp(work)
    f = np.where(np.isfinite(f) & (f >= 0.0), f, 0.0)
    return f, Vred @ (svals * (Ured.T @ f))


def _objective(A, p, ydata, inv_sigma2, m, alpha):
    """The shared objective: chi2_w/2 - alpha*S(p; m). Lower is better."""
    r = A @ p - ydata
    chi2 = float(np.sum(r * r * inv_sigma2))
    with np.errstate(divide="ignore", invalid="ignore"):
        entropy = np.where(p > 0, p - m - p * np.log(p / m), -m)
    return 0.5 * chi2 - alpha * float(np.sum(entropy))


def _fixture(seed=0, n_tau=96, n_td=48):
    rng = np.random.default_rng(seed)
    tau = np.logspace(-3.0, 1.0, n_tau)
    td_grid = np.logspace(-2.0, 0.5, n_td)
    A = build_diffusion_kernel(tau, td_grid)
    p_true = np.exp(-0.5 * ((np.log10(td_grid) + 0.7) / 0.25) ** 2)
    p_true /= p_true.sum()
    g = A @ p_true
    sigma = np.full(n_tau, 2e-3)
    ydata = g + rng.normal(0.0, sigma)
    m = np.full(n_td, 1.0 / n_td)
    return tau, td_grid, A, ydata, sigma, m


@pytest.mark.parametrize("alpha", [1e-3, 0.1])
def test_the_engine_solves_the_loops_objective_at_least_as_well(alpha):
    tau, td, A, ydata, sigma, m = _fixture()
    p_ref, _ = _quickfit_reference(A, ydata, sigma, m, alpha, 200)
    p_eng, _ = _maxent_engine_solve(A, ydata, sigma, m, alpha, 500)
    inv_sigma2 = 1.0 / sigma ** 2
    q_ref = _objective(A, p_ref, ydata, inv_sigma2, m, alpha)
    q_eng = _objective(A, p_eng, ydata, inv_sigma2, m, alpha)
    # Performance only improves: the converged engine must not score worse
    # than the fixed-count loop on the loop's own objective (small slack
    # for the two solvers' distinct stopping rules).
    assert q_eng <= q_ref + 1e-6 * abs(q_ref)


def test_the_reconstructions_agree_on_a_well_conditioned_problem():
    tau, td, A, ydata, sigma, m = _fixture(seed=3)
    alpha = 0.05
    _, g_ref = _quickfit_reference(A, ydata, sigma, m, alpha, 400)
    _, g_eng = _maxent_engine_solve(A, ydata, sigma, m, alpha, 800)
    scale = float(np.max(np.abs(ydata)))
    np.testing.assert_allclose(g_eng / scale, g_ref / scale, atol=5e-3)


def test_fcs_maxent_end_to_end_recovers_the_curve():
    """The public entry: the reconstruction tracks the data and the
    distribution is non-negative on the grid.

    Judged in the model's own weighting, not absolute sigma: `fcs_maxent`
    clamps and renormalises the supplied weights to a mean standard
    deviation of ~1 (the QuickFit convention it has always had), so the
    absolute noise scale deliberately does not reach the solver and a
    sigma-units residual bound would test the convention, not the route.
    """
    tau, td, A, ydata, sigma, m = _fixture(seed=7)
    result = fcs_maxent(tau, ydata + 1.0, reg=0.05,
                        weights=1.0 / sigma, td_grid=td)
    assert result["p"].shape == td.shape
    assert np.all(result["p"] >= 0.0)
    g0 = ydata + 1.0
    ss_res = float(np.sum((result["g_fit"] - g0) ** 2))
    ss_tot = float(np.sum((g0 - g0.mean()) ** 2))
    assert 1.0 - ss_res / ss_tot > 0.95, "reconstruction must track the data"
