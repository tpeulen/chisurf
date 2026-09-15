"""An absent bound spelled as infinity must not poison the optimiser.

Was `test_leastsqbound_infinite_bounds.py`, against ChiSurf's own bounded
Levenberg-Marquardt; that implementation was deleted on 2026-09-01 and the
regression moved onto `IMP.bff.FitMinimizer`, which is now the only one.

The defect it guards: the optimiser works in an internal, unconstrained
coordinate and maps back through a sin/arcsin transform, and it used to
detect "this parameter is unconstrained" by testing ``bound is None`` alone
-- but ``Model.parameter_bounds`` reports an absent bound as ``+/-inf``. An
``(-inf, inf)`` parameter therefore took the *bounded* branch:

    arcsin((2 * (x - lower) / (upper - lower)) - 1)
      = arcsin(inf/inf - 1) = arcsin(nan) = nan

so every unbounded parameter was silently NaN in the internal vector. The
visible symptom was a fit that *destroyed* a good solution: started at the
true parameters with chi2r 1.55, it walked away to NaN.

The transforms are C++ internals now (`Minimizer::to_internal` and
`to_external`), so the round trip is asserted through the door rather than
on the functions: a run capped at one evaluation cannot move the answer, so
whatever comes back is exactly ``to_external(to_internal(start))``.
"""
import numpy as np
import pytest

import chisurf.core.fitting.minimizer as M

pytestmark = pytest.mark.skipif(not M.have_minimizer(),
                                reason="IMP.bff carries no Minimizer")

SPELLINGS = [
    (-np.inf, np.inf),      # fully free, as parameter_bounds reports it
    (None, None),           # fully free, spelled with None
    (0.0, np.inf),          # lower bound only, inf spelling
    (0.0, None),            # lower bound only, None spelling
    (-np.inf, 10.0),        # upper bound only, inf spelling
    (None, 10.0),           # upper bound only, None spelling
]


def line():
    x = np.linspace(0.0, 10.0, 200)
    truth = np.array([2.5, -1.3])
    y = truth[0] * x + truth[1]

    def residual(p):
        return p[0] * x + p[1] - y

    return residual, truth


@pytest.mark.parametrize("bound", SPELLINGS)
def test_the_bounds_transform_round_trips(bound):
    """`to_external(to_internal(x))` is `x`, for every spelling of a bound.

    Asked of an objective that does not depend on its parameters, so the
    optimiser has nothing to move: the Jacobian is zero, it stops at the
    start, and what comes back is the round trip and nothing else. A NaN
    internal coordinate shows up here as a NaN answer, which is exactly how
    the defect presented.
    """
    start = [0.7, 2.5]
    m, node = M.director_objective(lambda p: np.zeros(8), start)
    m.set_initial_values(start)
    m.bounds = [bound, bound]
    m.run()
    got = np.asarray(m.x, dtype=float)
    assert np.all(np.isfinite(got)), "%s produced %s" % (bound, got)
    np.testing.assert_allclose(got, start, rtol=0, atol=1e-12)
    assert node is not None


def test_infinite_bounds_do_not_poison_a_fit():
    """A fit with (-inf, inf) bounds must actually converge.

    Before the fix the internal parameter vector was NaN and the optimiser
    returned its starting point, or worse.
    """
    residual, truth = line()
    fitted, ier = M.minimize(
        residual, np.array([0.1, 0.1]),
        bounds=[(-np.inf, np.inf), (-np.inf, np.inf)])
    fitted = np.asarray(fitted, dtype=float)
    assert np.all(np.isfinite(fitted))
    np.testing.assert_allclose(fitted, truth, rtol=1e-6, atol=1e-6)


def test_mixed_finite_and_infinite_bounds():
    """The common real case: some parameters bounded, others free."""
    residual, truth = line()
    fitted, ier = M.minimize(
        residual, np.array([0.1, 0.1]),
        bounds=[(0.0, 100.0), (-np.inf, np.inf)])   # slope bounded, offset free
    fitted = np.asarray(fitted, dtype=float)
    assert np.all(np.isfinite(fitted))
    np.testing.assert_allclose(fitted, truth, rtol=1e-6, atol=1e-6)


def test_an_infinite_bound_does_not_scale_the_covariance_by_infinity():
    """The gradient of the transform divides `R`'s columns, so it must be 1.

    A parameter declared ``(-inf, inf)`` that took the two-sided branch would
    get ``(upper - lower) * cos(v) / 2`` = inf for its gradient, and an
    infinite column scaling on a covariance the caller then reads. Stated
    separately from the NaN above because it is a *different* consequence of
    the same mis-detection, and it survives in a fit that otherwise looks
    fine.
    """
    residual, _truth = line()
    free, free_node = M.director_objective(residual, [0.1, 0.1])
    free.set_initial_values([0.1, 0.1])
    free.bounds = [(None, None), (None, None)]
    free.run()
    infinite, infinite_node = M.director_objective(residual, [0.1, 0.1])
    infinite.set_initial_values([0.1, 0.1])
    infinite.bounds = [(-np.inf, np.inf), (-np.inf, np.inf)]
    infinite.run()
    assert np.all(np.isfinite(infinite.covariance))
    np.testing.assert_allclose(infinite.covariance, free.covariance, rtol=1e-12)
    assert free_node is not None and infinite_node is not None
