"""chisurf.core.math.numerics reads like scipy and answers like scipy.

scipy is the oracle here: these are the calls the shim replaced, and a call
site routed through it must not see a different answer or a different shape.
"""

import numpy as np
import pytest

from chisurf.core.math import numerics

so = pytest.importorskip("scipy.optimize")


def _problems(n=60, seed=0):
    rng = np.random.default_rng(seed)
    for k in range(n):
        m, p = int(rng.integers(3, 50)), int(rng.integers(2, 20))
        a = np.abs(rng.normal(size=(m, p))) if k % 2 else rng.normal(size=(m, p))
        b = rng.normal(size=m) * 5.0
        yield a, b


def test_nnls_returns_scipy_tuple():
    for a, b in _problems():
        x, rnorm = numerics.nnls(a, b)
        xs, rs = so.nnls(a, b)
        assert isinstance(x, np.ndarray) and isinstance(rnorm, float)
        assert x.shape == xs.shape
        assert rnorm - rs <= 1e-9 * max(1.0, np.linalg.norm(b))


def test_nnls_column_vector_b_and_empty_A():
    a = np.eye(3)
    x, _ = numerics.nnls(a, np.array([[1.0], [-1.0], [2.0]]))
    np.testing.assert_allclose(x, [1.0, 0.0, 2.0])
    x, rnorm = numerics.nnls(np.zeros((3, 0)), np.ones(3))
    assert x.size == 0 and rnorm == pytest.approx(np.sqrt(3.0))


def test_nnls_rejects_what_scipy_rejects():
    with pytest.raises(ValueError):
        numerics.nnls(np.ones((3, 2)), np.ones(4))
    with pytest.raises(ValueError):
        numerics.nnls(np.array([[np.nan, 1.0]]), np.ones(1))


def test_nnls_iteration_limit_raises():
    rng = np.random.default_rng(1)
    with pytest.raises(RuntimeError):
        numerics.nnls(rng.normal(size=(30, 20)), rng.normal(size=30), maxiter=1)


def test_lsq_linear_nonnegative_matches_scipy():
    for a, b in _problems(seed=2):
        r = numerics.lsq_linear(a, b, bounds=(0.0, np.inf))
        s = so.lsq_linear(a, b, bounds=(0.0, np.inf))
        assert r.success and r.status in (1, 2, 3)
        assert r.cost - s.cost <= 1e-8 * max(1.0, s.cost)
        assert np.all(r.x >= 0.0)
        np.testing.assert_allclose(r.fun, a @ r.x - b, atol=1e-10 * max(1.0, np.linalg.norm(b)))


def test_lsq_linear_box_bounds_and_active_mask():
    a = np.eye(3)
    r = numerics.lsq_linear(a, np.array([-1.0, 0.5, 5.0]), bounds=([0, 0, 0], [1, 1, 1]))
    np.testing.assert_allclose(r.x, [0.0, 0.5, 1.0])
    np.testing.assert_array_equal(r.active_mask, [-1, 0, 1])
    assert r["x"] is r.x


def _exp_problem(seed):
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, 10.0, 120)
    a, tau, c = rng.uniform(1, 5), rng.uniform(0.5, 3), rng.uniform(0, 0.5)
    y = a * np.exp(-t / tau) + c + rng.normal(scale=0.02, size=t.size)
    return t, y


def test_least_squares_matches_scipy_bounded():
    for seed in range(20):
        t, y = _exp_problem(seed)

        def fun(p):
            return p[0] * np.exp(-t / p[1]) + p[2] - y

        x0 = [1.0, 1.0, 0.1]
        bounds = ([0.0, 0.05, 0.0], [10.0, 10.0, 1.0])
        r = numerics.least_squares(fun, x0, bounds=bounds)
        s = so.least_squares(fun, x0, bounds=bounds)
        assert r.success
        assert r.cost <= s.cost * (1 + 1e-6) + 1e-12
        np.testing.assert_allclose(r.x, s.x, rtol=1e-4, atol=1e-6)
        np.testing.assert_allclose(r.jac, s.jac, rtol=1e-3, atol=1e-6)
        assert r.nfev > 0 and r.fun.shape == s.fun.shape


def test_least_squares_args_and_active_bound():
    def fun(p, target, *, scale):
        return scale * (p - target)

    r = numerics.least_squares(fun, [0.5, 0.5], bounds=(0.0, 1.0), args=(np.array([2.0, 0.3]),),
                               kwargs={"scale": 3.0})
    # A parameter pinned at its bound dominates the cost, so the relative
    # ftol stop fires while the free one is still ~1e-5 out -- MINPACK with
    # the leastsqbound transform, as chisurf's fitter always behaved; scipy's
    # trf lands exactly. Documented in okf/subsystems/scipy-retirement.md.
    np.testing.assert_allclose(r.x, [1.0, 0.3], atol=1e-4)
    assert r.active_mask[0] == 1 and r.active_mask[1] == 0


def test_least_squares_propagates_exceptions():
    def fun(p):
        raise ZeroDivisionError("boom")

    with pytest.raises(ZeroDivisionError):
        numerics.least_squares(fun, [1.0])


def test_curve_fit_matches_scipy_including_pcov():
    for seed in range(10):
        t, y = _exp_problem(seed)
        sigma = np.full_like(y, 0.02)

        def f(x, a, tau, c):
            return a * np.exp(-x / tau) + c

        for absolute in (False, True):
            popt, pcov = numerics.curve_fit(f, t, y, p0=[1, 1, 0.1], sigma=sigma, absolute_sigma=absolute)
            ps, cs = so.curve_fit(f, t, y, p0=[1, 1, 0.1], sigma=sigma, absolute_sigma=absolute)
            np.testing.assert_allclose(popt, ps, rtol=1e-4, atol=1e-6)
            np.testing.assert_allclose(pcov, cs, rtol=2e-2, atol=1e-12)


def test_curve_fit_p0_from_signature_and_bounds():
    x = np.linspace(0, 1, 30)
    popt, _ = numerics.curve_fit(lambda x, a, b: a * x + b, x, 2 * x + 1)
    np.testing.assert_allclose(popt, [2.0, 1.0], atol=1e-6)
    popt, _ = numerics.curve_fit(lambda x, a, b: a * x + b, x, 2 * x + 1, bounds=([0, 0], [1.5, 5]))
    assert popt[0] == pytest.approx(1.5, abs=1e-6)
