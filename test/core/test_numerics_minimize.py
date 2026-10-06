"""``chisurf.core.math.numerics.minimize`` against ``scipy.optimize.minimize``.

scipy is the oracle. The bff engines are checked in imp.bff
(``test/numerics/test_minimize.py``); this file pins what the shim adds on
top: scipy's argument forms (bounds as pairs with ``None``, a ``Bounds``
object, ``tol``, ``jac`` as bool or callable), the removal of variables the
bounds fix, and the result fields the call sites read.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.math.numerics import minimize

so = pytest.importorskip("scipy.optimize")
rosen, rosen_der = so.rosen, so.rosen_der

X0 = np.array([-1.2, 1.0, 0.5, -0.3])
BOUNDS = [(-2, 2), (None, 2), (-2, 0.8), (0.6, None)]


def _close(r, s, atol):
    np.testing.assert_allclose(r.x, s.x, rtol=0, atol=atol)
    assert abs(r.fun - s.fun) <= max(atol, 1e-12)
    assert r.success == s.success


@pytest.mark.parametrize("jac", [None, True, "callable"])
def test_lbfgsb_with_open_sided_bounds(jac):
    fun = rosen if jac is None or jac == "callable" else (lambda x: (rosen(x), rosen_der(x)))
    j = rosen_der if jac == "callable" else jac
    r = minimize(fun, X0, method="L-BFGS-B", jac=j, bounds=BOUNDS)
    s = so.minimize(fun, X0, method="L-BFGS-B", jac=j, bounds=BOUNDS)
    _close(r, s, 1e-8)
    assert (r.nit, r.message) == (s.nit, s.message)
    np.testing.assert_allclose(r.hess_inv.todense(), s.hess_inv.todense(), rtol=1e-6, atol=1e-9)


def test_lbfgsb_with_a_bounds_object_and_tol():
    b = so.Bounds([-2, -2, -2, -2], [2, 2, 0.8, 2])
    r = minimize(rosen, X0, method="L-BFGS-B", bounds=b, tol=1e-12)
    s = so.minimize(rosen, X0, method="L-BFGS-B", bounds=b, tol=1e-12)
    _close(r, s, 1e-8)


@pytest.mark.parametrize("jac", [None, True])
def test_lbfgsb_drops_variables_the_bounds_fix(jac):
    fun = rosen if jac is None else (lambda x: (rosen(x), rosen_der(x)))
    bounds = [(-2, 2), (0.7, 0.7), (-2, 2), (-2, 2)]
    r = minimize(fun, X0, method="L-BFGS-B", jac=jac, bounds=bounds)
    s = so.minimize(fun, X0, method="L-BFGS-B", jac=jac, bounds=bounds)
    _close(r, s, 1e-8)
    assert r.x[1] == 0.7
    # Removed (NaN gradient) only when differencing; with a gradient scipy
    # keeps the fixed variable in the problem.
    assert np.isnan(r.jac[1]) == np.isnan(s.jac[1]) == (jac is None)
    assert r.nfev == s.nfev


def test_lbfgsb_with_every_variable_fixed_answers_outright():
    bounds = [(0.5, 0.5)] * 3
    r = minimize(rosen, np.zeros(3), method="L-BFGS-B", bounds=bounds)
    s = so.minimize(rosen, np.zeros(3), method="L-BFGS-B", bounds=bounds)
    np.testing.assert_array_equal(r.x, s.x)
    assert (r.fun, r.nfev, r.message, r.success) == (s.fun, s.nfev, s.message, s.success)


def test_nelder_mead_matches_scipy_exactly():
    opts = {"maxiter": 500, "fatol": 1e-4, "xatol": 1e-4}
    bounds = [(-2, 2)] * 4
    r = minimize(rosen, X0, method="Nelder-Mead", bounds=bounds, options=opts)
    s = so.minimize(rosen, X0, method="Nelder-Mead", bounds=bounds, options=opts)
    np.testing.assert_array_equal(r.x, s.x)
    assert (r.fun, r.nit, r.nfev, r.status, r.message) == (
        s.fun, s.nit, s.nfev, s.status, s.message,
    )
    np.testing.assert_array_equal(r.final_simplex[0], s.final_simplex[0])


def test_args_reach_the_objective():
    def f(x, a, b):
        return float(np.sum((x - a) ** 2) + b)

    r = minimize(f, np.zeros(2), args=(np.array([1.0, -2.0]), 3.0), method="L-BFGS-B",
                 bounds=[(-5, 5)] * 2)
    np.testing.assert_allclose(r.x, [1.0, -2.0], atol=1e-6)
    assert abs(r.fun - 3.0) < 1e-10


def test_methods_that_are_not_provided_raise():
    with pytest.raises(NotImplementedError):
        minimize(rosen, X0, method="BFGS")
    with pytest.raises(NotImplementedError):
        minimize(rosen, X0)  # scipy would pick BFGS
    with pytest.raises(NotImplementedError):
        minimize(rosen, X0, method="L-BFGS-B", callback=lambda r: None)
    with pytest.raises(TypeError):
        minimize(rosen, X0, method="L-BFGS-B", options={"finite_diff_rel_step": 1e-6})
