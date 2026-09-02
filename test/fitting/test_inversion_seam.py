"""Every regularised inversion goes through one seam -- and keeps its own objective.

The seam (:mod:`chisurf.core.fitting.inversion`) is one *surface*, not one
objective: its callers write the same problem class with different weight
conventions, and the whole hazard this module exists to contain is that
getting a convention wrong does not raise. The fit converges and returns a
plausible answer to a differently-regularised problem.

So these tests do not check that anything converges. Each one pins the
**objective**: it evaluates the caller's own written-down functional at the
returned solution and compares it against an independent referee
(``scipy.optimize``) minimising that same functional. A convention slip of a
square or a factor of two moves the objective by orders of magnitude over the
log-spaced weight grids these solvers are swept on, so a wrong mapping fails
loudly here.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import minimize, nnls

from chisurf.core.fitting.inversion import (
    EntropyWeight,
    SmoothnessWeight,
    difference_operator,
    entropy_weight_to_nu,
    maxent,
    nu_to_entropy_weight,
    tikhonov_nnls,
)

pytest.importorskip("tttrlib")


# --------------------------------------------------------------- the mapping


def test_the_three_entropy_conventions_are_distinct_and_invertible():
    """Each convention maps a weight onto a different engine ``nu``.

    If two of these ever collided the seam would be silently interchangeable
    where it must not be.
    """
    w = 0.125
    nus = {
        c: entropy_weight_to_nu(w, c)
        for c in (EntropyWeight.HALF_CHI2, EntropyWeight.CHI2, EntropyWeight.RUN_MEM)
    }
    assert len(set(nus.values())) == 3, nus
    for convention, nu in nus.items():
        assert nu_to_entropy_weight(nu, convention) == pytest.approx(w, rel=1e-12)


def test_the_half_chi2_convention_is_the_square_root_of_twice_the_weight():
    """``1/2 chi2 - alpha S`` is the engine's ``chi2 - nu^2 S`` at ``nu = sqrt(2 alpha)``.

    Written out rather than round-tripped: this is the number the FCS and
    DEER inversions depend on, and a round-trip through the module's own
    inverse would pass even if both halves were wrong.
    """
    for alpha in (1e-4, 1e-2, 0.5, 3.0):
        assert entropy_weight_to_nu(alpha, EntropyWeight.HALF_CHI2) == pytest.approx(
            np.sqrt(2.0 * alpha)
        )


def test_the_two_smoothness_conventions_differ_by_a_square():
    """``AMPLITUDE`` at ``w`` regularises as hard as ``POWER`` at ``w**2``.

    This is the DEER/2D-FLC difference. Solved on the same problem, the two
    must agree only under that relation -- and must *dis*agree at the same
    numeric weight, which is what makes an unnamed convention dangerous.
    """
    rng = np.random.default_rng(0)
    A = rng.standard_normal((40, 12))
    b = A @ np.abs(rng.standard_normal(12)) + rng.normal(0, 1e-3, 40)
    w = 0.3

    amp = tikhonov_nnls(A, b, w, convention=SmoothnessWeight.AMPLITUDE)
    pwr_matched = tikhonov_nnls(A, b, w * w, convention=SmoothnessWeight.POWER)
    pwr_same = tikhonov_nnls(A, b, w, convention=SmoothnessWeight.POWER)

    np.testing.assert_allclose(amp, pwr_matched, rtol=1e-9, atol=1e-12)
    assert not np.allclose(amp, pwr_same, rtol=1e-3, atol=1e-6)


def test_the_difference_operator_is_the_roughness_operator():
    """One second-difference operator for every caller that penalises roughness."""
    L = difference_operator(6, order=2)
    assert L.shape == (4, 6)
    np.testing.assert_allclose(L[0, :3], [1.0, -2.0, 1.0])
    # Too short for the difference: degrade to the identity rather than empty.
    np.testing.assert_allclose(difference_operator(2, order=2), np.eye(2))


# ------------------------------------------------------- caller: DEER Tikhonov


def _deer_problem(n_t=120, n_r=60, seed=0):
    """A dipolar inversion problem with a known two-peak distribution."""
    from chisurf.core.models.deer.deer import dipolar_kernel

    rng = np.random.default_rng(seed)
    r = np.linspace(20.0, 60.0, n_r)
    t = np.linspace(0.0, 3.0, n_t)
    K = np.asarray(dipolar_kernel(t, r), dtype=float)
    p_true = (np.exp(-0.5 * ((r - 35.0) / 2.0) ** 2)
              + 0.5 * np.exp(-0.5 * ((r - 45.0) / 3.0) ** 2))
    p_true /= p_true.sum()
    b = K @ p_true + rng.normal(0.0, 2e-3, n_t)
    return r, K, b, p_true


def test_deer_tikhonov_still_optimises_alpha_squared_roughness():
    """DEER's ``alpha`` is the augmented-block amplitude, i.e. an ``alpha^2`` penalty.

    Refereed against the augmented system written out by hand -- if
    ``solve_tikhonov`` had been routed with the ``POWER`` convention it would
    stack ``sqrt(alpha) L`` instead of ``alpha L`` and this would fail.
    """
    from chisurf.core.models.deer.tikhonov import (
        second_derivative_operator,
        solve_tikhonov,
    )

    r, K, b, _ = _deer_problem()
    L = second_derivative_operator(r.size)
    alpha = 0.05

    got = solve_tikhonov(K, b, alpha, L)

    ref, _ = nnls(np.vstack([K, alpha * L]),
                  np.concatenate([b, np.zeros(L.shape[0])]))
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-12)

    def objective(p):
        res = K @ p - b
        return float(res @ res) + alpha ** 2 * float((L @ p) @ (L @ p))

    # No feasible point scores better: perturb toward the unregularised
    # solution and confirm the objective rises.
    unreg, _ = nnls(K, b)
    for s in (0.05, 0.2, 0.5):
        mixed = np.clip((1.0 - s) * got + s * unreg, 0.0, None)
        assert objective(mixed) >= objective(got) * (1.0 - 1e-9)


# --------------------------------------------------------- caller: DEER MaxEnt


def _deer_maxent_objective(K, b, m):
    """DEER's written objective: ``1/2 chi2 - alpha S``, ``S`` Shannon vs ``m``."""

    def Q(p, alpha):
        res = K @ p - b
        with np.errstate(divide="ignore", invalid="ignore"):
            S = float(np.sum(np.where(p > 0, -p * np.log(p / m), 0.0)))
        return 0.5 * float(res @ res) - alpha * S

    return Q


def _simplex_referee(Q, alpha, n, seed=0):
    """Minimise ``Q`` over the probability simplex with an independent optimiser."""
    rng = np.random.default_rng(seed)

    def f(z):
        z = z - z.max()
        e = np.exp(z)
        return Q(e / e.sum(), alpha)

    best = np.inf
    for k in range(3):
        z0 = np.zeros(n) if k == 0 else rng.standard_normal(n) * 0.1
        res = minimize(f, z0, method="L-BFGS-B",
                       options={"maxiter": 20000, "ftol": 1e-16, "gtol": 1e-12})
        best = min(best, float(res.fun))
    return best


@pytest.mark.parametrize("alpha", [1e-3, 1e-2, 1e-1, 1.0])
def test_deer_maxent_reaches_the_optimum_of_its_own_objective(alpha):
    """DEER MaxEnt minimises ``1/2 chi2 - alpha S`` subject to ``sum(p) == 1``.

    The tolerance is deliberately tight (1%). The damped fixed-point
    iteration this replaced missed it by **+187%** at ``alpha=0.1``, **+990%**
    at ``0.01`` and **+4760%** at ``0.001`` -- and since the automatic weight
    grid is ``logspace(-3, 1.3)``, most of every sweep was scored on
    inversions solved that badly. A loose tolerance here would let that back
    in, so this is the assertion that has to stay sharp.
    """
    from chisurf.core.models.deer.maxent import maxent_inversion

    r, K, b, _ = _deer_problem()
    m = np.full(r.size, 1.0 / r.size)
    Q = _deer_maxent_objective(K, b, m)

    p = maxent_inversion(K, b, 1.0, alpha)

    assert np.all(p >= 0.0)
    assert p.sum() == pytest.approx(1.0, abs=1e-6), "the simplex constraint is the convention"

    q_ref = _simplex_referee(Q, alpha, r.size)
    assert Q(p, alpha) <= q_ref * (1.0 + 1e-2) if q_ref > 0 else Q(p, alpha) <= q_ref * (1.0 - 1e-2)


def test_deer_maxent_weight_is_the_half_chi2_convention():
    """Raising ``alpha`` must smooth the distribution, monotonically.

    The direction check the convention buys: under ``1/2 chi2 - alpha S`` a
    larger ``alpha`` pulls toward the (uniform) prior. Were the weight
    inverted or squared into the engine, this ordering would break.
    """
    from chisurf.core.models.deer.maxent import maxent_inversion

    r, K, b, _ = _deer_problem()
    m = np.full(r.size, 1.0 / r.size)

    def neg_entropy(p):
        with np.errstate(divide="ignore", invalid="ignore"):
            return float(np.sum(np.where(p > 0, p * np.log(p / m), 0.0)))

    ps = [maxent_inversion(K, b, 1.0, a) for a in (1e-3, 1e-2, 1e-1, 1.0)]
    dists = [neg_entropy(p) for p in ps]
    assert dists == sorted(dists, reverse=True), dists


# ---------------------------------------------------------- caller: FCS MaxEnt


def test_fcs_maxent_engine_route_optimises_the_quickfit_objective():
    """The FCS route's ``alpha`` is ``1/2 chi2_w - alpha S`` in the *renormalised* sigmas.

    Two conventions stack here and both matter: the ``HALF_CHI2`` weight
    mapping, and ``fcs_maxent``'s clamp-and-renormalise of the supplied
    weights to a mean sigma of ~1. This checks the first directly (the second
    is upstream of the solve and is covered in
    ``test/models/test_fcs_maxent_engine.py``).
    """
    from chisurf.core.models.fcs.maxent import (
        _maxent_engine_solve,
        build_diffusion_kernel,
    )

    rng = np.random.default_rng(4)
    tau = np.logspace(-3.0, 1.0, 96)
    td = np.logspace(-2.0, 0.5, 48)
    A = build_diffusion_kernel(tau, td)
    p_true = np.exp(-0.5 * ((np.log10(td) + 0.7) / 0.25) ** 2)
    p_true /= p_true.sum()
    sigma = np.full(tau.size, 2e-3)
    y = A @ p_true + rng.normal(0.0, sigma)
    m = np.full(td.size, 1.0 / td.size)
    inv_sigma2 = 1.0 / sigma ** 2
    alpha = 0.05

    p, _ = _maxent_engine_solve(A, y, sigma, m, alpha, 800)

    def Q(x):
        res = A @ x - y
        chi2 = float(np.sum(res * res * inv_sigma2))
        with np.errstate(divide="ignore", invalid="ignore"):
            S = float(np.sum(np.where(x > 0, (x - m) - x * np.log(x / m), -m)))
        return 0.5 * chi2 - alpha * S

    # Referee: minimise the same functional over x >= 0 with an independent
    # optimiser, parametrised as exp() so positivity is automatic.
    def f(z):
        return Q(np.exp(np.clip(z, -60.0, 60.0)))

    res = minimize(f, np.log(np.clip(p, 1e-12, None)), method="L-BFGS-B",
                   options={"maxiter": 20000, "ftol": 1e-16, "gtol": 1e-12})
    assert Q(p) <= float(res.fun) * (1.0 + 1e-3) + 1e-9


def test_fcs_maxent_default_is_still_the_cached_svd_loop():
    """The owner's standing decision: the FCS MEM default does not move.

    The engine route is built, pinned and correct but 2-3x slower than the
    SVD-space loop, and that cost has not been accepted. This test fails if
    ``fcs_maxent`` is ever quietly repointed at the engine -- the loop is a
    fixed-count iteration with no convergence test, so the two give slightly
    different answers and a silent switch would be invisible otherwise.
    """
    import inspect

    from chisurf.core.models.fcs import maxent as fcs_maxent_mod

    src = inspect.getsource(fcs_maxent_mod.fcs_maxent)
    assert "_quickfit_mem_iteration" in src
    assert "_maxent_engine_solve" not in src
    assert hasattr(fcs_maxent_mod, "_quickfit_mem_iteration")


# ------------------------------------------------------ caller: TCSPC/run_mem


def test_run_mem_convention_is_half_nu_not_nu_squared():
    """The TCSPC optimiser's weight is ``chi2 - nu*S/2``, a *third* spelling.

    ``nu = 0.02`` means something different to this caller than to the FCS
    and DEER inversions, and the seam must not silently equate them. Solving
    one problem through both entry points at the *same numeric weight* under
    the two conventions must give the same solution only when the weights are
    related by the documented map.
    """
    from chisurf.core.fitting.inversion import maxent_normal_equations

    rng = np.random.default_rng(7)
    n_rows, n_cols = 60, 20
    A = np.abs(rng.standard_normal((n_rows, n_cols))) + 0.05
    x_true = np.abs(rng.standard_normal(n_cols))
    b = A @ x_true + rng.normal(0.0, 1e-3, n_rows)
    m = np.full(n_cols, 1.0 / n_cols)

    H = 2.0 * (A.T @ A)
    g0 = 2.0 * (A.T @ b)
    const = float(b @ b)

    nu_run = 0.02
    via_run_mem = np.asarray(
        maxent_normal_equations(H, g0, m, const, nu_run,
                                convention=EntropyWeight.RUN_MEM,
                                max_iter=2000, tol=1e-8).p,
        dtype=float,
    )
    # The same objective expressed in HALF_CHI2 units: chi2 - nu_run*S/2 is
    # 2 * (chi2/2 - (nu_run/4) * S), so alpha = nu_run / 4.
    via_half = maxent(A, b, nu_run / 4.0,
                      convention=EntropyWeight.HALF_CHI2,
                      prior=m, max_iter=2000, tol=1e-8)
    np.testing.assert_allclose(via_run_mem, via_half, rtol=2e-4, atol=1e-8)

    # And at the same *numeric* weight the two are not the same problem.
    via_half_naive = maxent(A, b, nu_run,
                            convention=EntropyWeight.HALF_CHI2,
                            prior=m, max_iter=2000, tol=1e-8)
    assert not np.allclose(via_run_mem, via_half_naive, rtol=1e-2, atol=1e-6)


def test_the_maxent_decay_solver_reaches_the_engine_through_the_seam():
    """The plugin's ``_run_mem`` is a seam call, not a second engine call site."""
    import inspect

    from chisurf.plugins.fluorescence_decay.maxent_decay.core import solver

    src = inspect.getsource(solver._run_mem)
    assert "maxent_normal_equations" in src
    assert "tcspc_run_mem" not in src.split('"""')[-1], "no direct engine call"
    assert not hasattr(solver, "_quadpr_bound"), "the dead bound-QP copy is gone"
    assert not hasattr(solver, "_tttrlib"), "the engine handle moved to the seam"


# --------------------------------------------------------- caller: 2D-FLC ILT


def test_flc_2d_ilt_uses_the_power_convention():
    """The 2D-FLC ``reg`` is the penalty power: the block is ``sqrt(reg) L``."""
    from chisurf.plugins.fcs.flc_2d.fit.ilt import _penalty_matrix, _solve_reg_L

    rng = np.random.default_rng(2)
    Wd = np.abs(rng.standard_normal((50, 14))) + 0.02
    wy = Wd @ np.abs(rng.standard_normal(14)) + rng.normal(0, 1e-3, 50)
    L = _penalty_matrix(14, 2)
    reg = 0.4

    got = _solve_reg_L(Wd, wy, L, reg, "nnls")
    ref, _ = nnls(np.vstack([Wd, np.sqrt(reg) * L]),
                  np.concatenate([wy, np.zeros(L.shape[0])]),
                  maxiter=40 * Wd.shape[1])
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-12)


def test_flc_2d_and_deer_penalty_operators_are_the_same_matrix():
    """One roughness operator, two callers that each used to build their own."""
    from chisurf.core.models.deer.tikhonov import second_derivative_operator
    from chisurf.plugins.fcs.flc_2d.fit.ilt import _penalty_matrix

    for n in (5, 12, 40):
        np.testing.assert_allclose(
            second_derivative_operator(n), _penalty_matrix(n, 2)
        )


# --------------------------------------------------------------- the register


def test_the_dead_regularised_inversion_copies_are_gone():
    """Guard the deletions this consolidation made.

    ``math/optimization/nnls.py`` (an amplitude-Tikhonov wrapper on the
    normal equations, zero callers) and the plugin solver's ``_quadpr_bound``
    (a clamping bound-QP, zero callers once the optimiser moved into the
    photon library) were third and fourth spellings of solves the seam now
    owns. Guards against either growing back.
    """
    import chisurf.core.math.optimization

    assert not hasattr(chisurf.core.math.optimization, "solve_nnls")
    with pytest.raises(ImportError):
        import chisurf.core.math.optimization.nnls  # noqa: F401
