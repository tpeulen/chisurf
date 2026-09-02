"""The optimiser's own covariance, against SciPy's.

Was `test_leastsqbound_covariance.py`, and it tested ChiSurf's own bounded
Levenberg-Marquardt. That implementation was deleted on 2026-09-01 -- there
is one of this algorithm in the stack now and it is `IMP.bff.Minimizer` --
so the properties moved onto the implementation that ships. They are the
same properties and they are still worth defending:

* the matrix agrees with SciPy's ``cov_x`` for the identical problem;
* it is ``(J'J)^-1`` in **external** coordinates, whatever the bounds -- the
  transform's gradient is divided out of ``R``'s columns first, and without
  that step the answer is the covariance of the *internal* coordinates,
  which is a different number wearing the same name;
* its rows and columns are the caller's parameters, in the caller's order.

That last one is here because it was once false and nothing said so:
MINPACK's pivot ``ipvt`` became 0-based in SciPy while ChiSurf kept
subtracting one from it, the ``-1`` wrapped to the last row, and the
permutation used to un-pivot ``R`` stopped being a permutation. A permuted
covariance is *plausible* -- positive diagonal, symmetric, right magnitudes
-- so only a test that compares against something else finds it.
"""
import numpy as np
import pytest
import scipy.optimize

import chisurf.core.fitting.minimizer as M

pytestmark = pytest.mark.skipif(not M.have_minimizer(),
                                reason="IMP.bff carries no Minimizer")


def problem():
    rng = np.random.default_rng(7)
    x = np.linspace(0.0, 10.0, 200)
    y = 1.4 * np.exp(-x / 0.8) + 0.5 * np.exp(-x / 3.0) + rng.normal(0, 0.02, 200)
    ey = np.full(200, 0.02)

    def f(p):
        return (y - (p[0] * np.exp(-x / p[1]) + p[2] * np.exp(-x / p[3]))) / ey

    # Off the model's permutation-symmetry ridge: started at (1, 1, 1, 1) a
    # sum of exponentials has two identical pairs of Jacobian columns, and
    # which of two equal norms the QR pivots on is then arbitrary.
    return f, np.array([1.0, 0.5, 0.3, 2.0])


def run(f, start, bounds):
    """Optimise *f* and hand back the minimiser, still holding its answer.

    The node has to be named and kept: it is a SWIG director and the C++ side
    holds only a weak reference to its Python proxy, so letting it fall out
    of scope while the minimiser is alive is a use-after-free.
    """
    m, node = M.director_objective(f, start)
    m.set_initial_values([float(v) for v in start])
    m.bounds = list(bounds)
    ier = m.run()
    assert ier in (1, 2, 3, 4), m.message
    return m, node


def test_unbounded_covariance_matches_scipy():
    f, start = problem()
    reference = scipy.optimize.leastsq(f, start, full_output=1)[1]
    m, node = run(f, start, [(None, None)] * 4)
    np.testing.assert_allclose(m.covariance, reference, rtol=1e-10, atol=1e-16)
    assert node is not None


@pytest.mark.parametrize("bounds", [
    [(None, None)] * 4,
    [(0.0, 10.0), (0.01, 5.0), (0.0, 10.0), (0.01, 20.0)],
    [(0.0, None), (0.01, None), (0.0, None), (0.01, None)],
])
def test_covariance_is_the_inverse_gram_matrix(bounds):
    f, start = problem()
    m, node = run(f, start, bounds)
    x = np.asarray(m.x)
    cov = m.covariance
    assert cov.size

    f0 = f(x)
    eps = np.sqrt(np.finfo(float).eps)
    jacobian = np.empty((f0.size, x.size))
    for j in range(x.size):
        q = np.array(x, dtype=float)
        h = eps * abs(q[j]) or eps
        q[j] += h
        jacobian[:, j] = (f(q) - f0) / h
    np.testing.assert_allclose(cov, np.linalg.inv(jacobian.T @ jacobian),
                               rtol=1e-3)
    assert node is not None


def test_the_covariance_is_not_permuted():
    f, start = problem()
    reference = scipy.optimize.leastsq(f, start, full_output=1)[1]
    m, node = run(f, start, [(None, None)] * 4)
    got = m.covariance
    n = len(start)
    for shift in range(1, n):
        rolled = np.roll(np.roll(reference, shift, axis=0), shift, axis=1)
        assert not np.allclose(got, rolled, rtol=1e-6), (
            "the covariance is a cyclic shift of scipy's by %d" % shift)
    assert node is not None


def test_the_finite_difference_covariance_agrees_with_it_here():
    """Two matrices, one answer -- when the step resolves every parameter.

    `Minimizer.covariance` comes from the QR the optimiser already holds;
    `finite_difference_covariance` differences the objective afresh at
    `approx_grad`'s step. They are different computations and they are
    allowed to differ where MINPACK's relative step does not resolve a
    parameter -- which is the whole reason the second one exists. This
    fixture is the *other* case, every parameter of one order, and there they
    have to agree.
    """
    f, start = problem()
    m, node = run(f, start, [(None, None)] * 4)
    fd, used = m.finite_difference_covariance()
    assert used == [0, 1, 2, 3]
    np.testing.assert_allclose(np.sqrt(np.diag(fd)),
                               np.sqrt(np.diag(m.covariance)), rtol=1e-3)
    assert node is not None
