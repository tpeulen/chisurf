"""scipy-shaped numerics served by IMP.bff's C++ core.

The one place chisurf reaches the numerical routines that used to come from
scipy and now live in IMP.bff. Call sites read as they did with scipy --
``nnls(A, b)`` returns ``(x, rnorm)``, ``lsq_linear(...)`` returns a result
with ``.x``, ``.cost``, ``.fun``, ``.active_mask``, ``.status`` and
``.success`` -- so routing a call is an import change, not a rewrite. Nothing
outside this module imports the bff entry points directly.

What is here and why it lives in bff rather than in numpy or chisurf: see
[scipy retirement](okf/subsystems/scipy-retirement.md) (route 3).
"""

from __future__ import annotations

import numpy as np

__all__ = ["OptimizeResult", "curve_fit", "least_squares", "lsq_linear", "nnls"]


class OptimizeResult(dict):
    """A dict with attribute access, like ``scipy.optimize.OptimizeResult``."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def _bff():
    # Imported on first use: IMP.bff costs ~0.3 s at import, and the modules
    # that call into here are reached from start-up paths that never solve.
    from IMP import bff

    return bff


def _matrix(A) -> np.ndarray:
    A = np.asarray(A, dtype=float)
    if A.ndim != 2:
        raise ValueError(f"Expected a 2D array, but the shape of A is {A.shape}")
    if not np.all(np.isfinite(A)):
        raise ValueError("array must not contain infs or NaNs")
    return A


def _vector(b, m: int) -> np.ndarray:
    b = np.asarray(b, dtype=float)
    if b.ndim == 2 and b.shape[1] == 1:
        b = b.ravel()
    if b.ndim != 1:
        raise ValueError(f"Expected a 1D array, but the shape of b is {b.shape}")
    if b.shape[0] != m:
        raise ValueError(
            f"Incompatible dimensions. The first dimension of A is {m}, "
            f"while the shape of b is {b.shape}"
        )
    if not np.all(np.isfinite(b)):
        raise ValueError("array must not contain infs or NaNs")
    return b


def nnls(A, b, *, maxiter: int | None = None) -> tuple[np.ndarray, float]:
    """Solve ``argmin_x ||A x - b||_2`` subject to ``x >= 0``.

    Lawson & Hanson's NNLS, as ``scipy.optimize.nnls``.

    Parameters
    ----------
    A : array_like, shape (m, n)
        Coefficient matrix.
    b : array_like, shape (m,)
        Right-hand side.
    maxiter : int, optional
        Iteration limit; ``3 n`` when omitted.

    Returns
    -------
    x : numpy.ndarray, shape (n,)
        The solution.
    rnorm : float
        ``||A x - b||_2``.

    Raises
    ------
    RuntimeError
        If the iteration limit is reached, as scipy raises.
    """
    A = _matrix(A)
    m, n = A.shape
    b = _vector(b, m)
    if n == 0:
        return np.empty(0), float(np.linalg.norm(b))
    r = _bff().nnls(A, b, maxiter=int(maxiter or 0))
    if r.status != 0:
        raise RuntimeError("Maximum number of iterations reached.")
    return np.asarray(r.x, dtype=float), float(r.rnorm)


def lsq_linear(
    A,
    b,
    bounds=(-np.inf, np.inf),
    method: str = "bvls",
    max_iter: int | None = None,
    **_unused,
) -> OptimizeResult:
    """Solve ``argmin_x 0.5 ||A x - b||^2`` subject to ``lb <= x <= ub``.

    Stark & Parker's BVLS, as ``scipy.optimize.lsq_linear``. scipy's default
    method is ``trf``; both reach the same minimiser of this convex problem,
    so ``method`` is accepted for signature compatibility and BVLS is always
    used. Dense ``A`` only.

    Parameters
    ----------
    A : array_like, shape (m, n)
        Coefficient matrix.
    b : array_like, shape (m,)
        Right-hand side.
    bounds : tuple of (array_like or float), optional
        ``(lb, ub)``, each a scalar or one entry per unknown; ``+-inf`` for
        none.
    method : str, optional
        Ignored beyond validation; see above.
    max_iter : int, optional
        Iteration limit; ``max(100, n)`` when omitted.

    Returns
    -------
    OptimizeResult
        ``x``, ``cost``, ``fun``, ``optimality``, ``active_mask``, ``nit``,
        ``status`` (1 when converged, 0 when the iteration limit was hit, as
        scipy reports them), ``message`` and ``success``.
    """
    if method not in ("bvls", "trf"):
        raise ValueError("`method` must be 'trf' or 'bvls'")
    A = _matrix(A)
    m, n = A.shape
    b = _vector(b, m)
    lb, ub = bounds
    lb = np.broadcast_to(np.asarray(lb, dtype=float), (n,)).copy()
    ub = np.broadcast_to(np.asarray(ub, dtype=float), (n,)).copy()
    if np.any(lb >= ub):
        raise ValueError("Each lower bound must be strictly less than each upper bound.")
    r = _bff().bvls(A, b, lb, ub, maxiter=int(max_iter or 0))
    x = np.asarray(r.x, dtype=float)
    fun = np.asarray(r.residuals, dtype=float)
    g = A.T @ fun
    active = np.asarray(r.active_mask, dtype=int)
    free = active == 0
    optimality = float(np.max(np.abs(g[free]), initial=0.0))
    converged = r.status == 0
    return OptimizeResult(
        x=x,
        cost=0.5 * float(fun @ fun),
        fun=fun,
        optimality=optimality,
        active_mask=active,
        unbounded_sol=None,
        nit=int(r.iterations),
        status=1 if converged else 0,
        message=r.get_message(),
        success=converged,
    )


#: MINPACK lmdif ``info`` -> ``least_squares`` ``status``. scipy numbers
#: gtol 1, ftol 2, xtol 3, both 4, budget 0; lmdif numbers ftol 1, xtol 2,
#: both 3, gtol 4, budget 5, and 6-8 for "a tolerance is too small to make
#: progress", which is convergence at working precision.
_LMDIF_TO_STATUS = {1: 2, 2: 3, 3: 4, 4: 1, 5: 0, 6: 2, 7: 3, 8: 1, -1: -1, 0: -1}

_STATUS_MESSAGE = {
    -1: "Improper input or the evaluation was cancelled.",
    0: "The maximum number of function evaluations is exceeded.",
    1: "`gtol` termination condition is satisfied.",
    2: "`ftol` termination condition is satisfied.",
    3: "`xtol` termination condition is satisfied.",
    4: "Both `ftol` and `xtol` termination conditions are satisfied.",
}


def _residual_function(fun, args, kwargs):
    bff = _bff()

    class _Residuals(bff.FitResidualFunction):
        def evaluate(self, x):
            r = np.asarray(fun(np.asarray(x, dtype=float), *args, **kwargs), dtype=float)
            return r.ravel()

    return _Residuals()


def least_squares(
    fun,
    x0,
    jac="2-point",
    bounds=(-np.inf, np.inf),
    method="trf",
    ftol=1e-8,
    xtol=1e-8,
    gtol=1e-8,
    x_scale=None,
    loss="linear",
    f_scale=1.0,
    diff_step=None,
    tr_solver=None,
    tr_options=None,
    jac_sparsity=None,
    max_nfev=None,
    verbose=0,
    args=(),
    kwargs=None,
) -> OptimizeResult:
    """Minimise ``0.5 * sum(fun(x)**2)`` subject to ``lb <= x <= ub``.

    The ``scipy.optimize.least_squares`` call shape, solved by IMP.bff's
    ``FitMinimizer``: MINPACK's Levenberg-Marquardt (``lmdif``) with the
    bounds handled by the ``leastsqbound`` variable transform. scipy's
    ``trf``, ``dogbox`` and ``lm`` all land on the same local minimum of a
    well-posed problem, so ``method`` selects nothing here; the Jacobian is
    always a forward difference (``diff_step`` sets its relative step).

    Parameters
    ----------
    fun : callable
        ``fun(x, *args, **kwargs) -> residuals``, a 1-D array whose length
        does not depend on ``x``.
    x0 : array_like
        Start. A start sitting exactly on a bound is moved a hair inside.
    bounds : tuple, optional
        ``(lb, ub)``, scalars or one entry per parameter; ``+-inf`` for none.
    ftol, xtol, gtol : float, optional
        MINPACK's convergence tolerances.
    diff_step : float, optional
        Relative finite-difference step; MINPACK's ``epsfcn`` is its square.
    max_nfev : int, optional
        Residual-evaluation budget; ``200 * (n + 1)`` when omitted.

    Returns
    -------
    OptimizeResult
        ``x``, ``cost``, ``fun``, ``jac`` (at the solution), ``grad``,
        ``optimality``, ``active_mask``, ``nfev``, ``njev``, ``status``,
        ``message``, ``success`` -- the fields scipy reports.

    Raises
    ------
    NotImplementedError
        For a robust ``loss`` other than ``"linear"``: no caller uses one,
        and silently fitting the wrong objective would be worse than refusing.
    """
    if loss != "linear":
        raise NotImplementedError(f"loss={loss!r}: only the linear loss is served")
    if method not in ("trf", "dogbox", "lm"):
        raise ValueError(f"method must be 'trf', 'dogbox' or 'lm', not {method!r}")
    kwargs = kwargs or {}
    x0 = np.atleast_1d(np.asarray(x0, dtype=float))
    if x0.ndim != 1:
        raise ValueError("`x0` must have at most 1 dimension.")
    n = x0.size
    lb, ub = bounds
    lb = np.broadcast_to(np.asarray(lb, dtype=float), (n,)).copy()
    ub = np.broadcast_to(np.asarray(ub, dtype=float), (n,)).copy()
    if np.any(lb >= ub):
        raise ValueError("Each lower bound must be strictly less than each upper bound.")
    if method == "lm" and (np.any(np.isfinite(lb)) or np.any(np.isfinite(ub))):
        raise ValueError("Method 'lm' doesn't support bounds.")
    if np.any((x0 < lb) | (x0 > ub)):
        raise ValueError("`x0` is infeasible.")

    bff = _bff()
    minimizer = bff.FitMinimizer()
    function = _residual_function(fun, args, kwargs)
    minimizer.set_residual_function(function)
    minimizer.set_initial_values([float(v) for v in x0])
    minimizer.set_bounds([float(v) for v in lb], [float(v) for v in ub])
    minimizer.set_ftol(float(ftol))
    minimizer.set_xtol(float(xtol))
    minimizer.set_gtol(float(gtol) if gtol else 0.0)
    if max_nfev:
        minimizer.set_maxfev(int(max_nfev))
    if diff_step is not None:
        minimizer.set_epsfcn(float(diff_step) ** 2)
    info = minimizer.run()

    x = np.asarray(minimizer.get_x(), dtype=float)
    fvec = np.asarray(minimizer.get_residuals(), dtype=float)
    m = fvec.size
    jac_flat = np.asarray(minimizer.compute_jacobian(list(x)), dtype=float)
    J = jac_flat.reshape(n, m).T if jac_flat.size == n * m else np.full((m, n), np.nan)
    grad = J.T @ fvec
    active = np.zeros(n, dtype=int)
    # The bounds transform approaches a bound asymptotically (x - lb goes as
    # the square of the internal distance), so "on the bound" is a tolerance
    # well above round-off.
    span = np.maximum(1.0, np.abs(x))
    active[np.isfinite(lb) & (x - lb <= 1e-6 * span)] = -1
    active[np.isfinite(ub) & (ub - x <= 1e-6 * span)] = 1
    free = active == 0
    status = _LMDIF_TO_STATUS.get(int(info), -1)
    nfev = int(minimizer.get_number_of_evaluations())
    return OptimizeResult(
        x=x,
        cost=0.5 * float(fvec @ fvec),
        fun=fvec,
        jac=J,
        grad=grad,
        optimality=float(np.max(np.abs(grad[free]), initial=0.0)),
        active_mask=active,
        nfev=nfev,
        njev=None,
        status=status,
        message=_STATUS_MESSAGE.get(status, minimizer.get_message()),
        success=status > 0,
    )


def curve_fit(
    f,
    xdata,
    ydata,
    p0=None,
    sigma=None,
    absolute_sigma=False,
    check_finite=True,
    bounds=(-np.inf, np.inf),
    method=None,
    jac=None,
    *,
    full_output=False,
    nan_policy=None,
    maxfev=None,
    **kwargs,
):
    """Fit ``f(xdata, *p)`` to ``ydata``; ``scipy.optimize.curve_fit``'s shape.

    Parameters
    ----------
    f : callable
        ``f(xdata, *params) -> model``.
    xdata, ydata : array_like
        Independent and dependent data.
    p0 : array_like, optional
        Start; all ones when omitted (the number of parameters is read from
        ``f``'s signature, as scipy does).
    sigma : array_like, optional
        One standard deviation per point; the residuals are divided by it.
    absolute_sigma : bool, optional
        If True ``sigma`` is absolute and ``pcov`` is not rescaled by the
        reduced chi-square; otherwise it is, as scipy does.
    bounds : tuple, optional
        ``(lb, ub)`` as in :func:`least_squares`.
    maxfev : int, optional
        Evaluation budget (``max_nfev`` is accepted too).

    Returns
    -------
    popt : numpy.ndarray
        Best-fit parameters.
    pcov : numpy.ndarray
        Their covariance, ``inv(J^T J)`` (scaled unless ``absolute_sigma``),
        from the pseudo-inverse as scipy computes it; ``inf`` when the fit
        leaves no degrees of freedom.

    Raises
    ------
    RuntimeError
        When the fit does not converge, as scipy raises.
    """
    import inspect

    if p0 is None:
        params = inspect.signature(f).parameters
        n_args = len(params) - 1
        if n_args < 1:
            raise ValueError("Unable to determine number of fit parameters.")
        p0 = np.ones(n_args)
    p0 = np.atleast_1d(np.asarray(p0, dtype=float))
    ydata = np.asarray(ydata, dtype=float)
    if check_finite and not np.all(np.isfinite(ydata)):
        raise ValueError("array must not contain infs or NaNs")
    if sigma is not None:
        sigma = np.asarray(sigma, dtype=float)
        if sigma.ndim != 1 and sigma.shape != ydata.shape:
            raise ValueError("`sigma` must be a 1-D array of standard deviations")
        weight = 1.0 / sigma
    else:
        weight = None

    def residuals(p):
        r = np.asarray(f(xdata, *p), dtype=float) - ydata
        if weight is not None:
            r = r * weight
        return r.ravel()

    max_nfev = maxfev if maxfev is not None else kwargs.pop("max_nfev", None)
    lb, ub = bounds
    lb_arr = np.broadcast_to(np.asarray(lb, dtype=float), p0.shape)
    ub_arr = np.broadcast_to(np.asarray(ub, dtype=float), p0.shape)
    p0 = np.clip(p0, lb_arr, ub_arr)
    res = least_squares(residuals, p0, bounds=bounds, max_nfev=max_nfev)
    if not res.success:
        raise RuntimeError("Optimal parameters not found: " + res.message)
    popt = res.x
    # scipy's covariance: the Moore-Penrose inverse of J^T J through the SVD
    # of J, discarding singular values below its own threshold.
    _, s, vt = np.linalg.svd(res.jac, full_matrices=False)
    threshold = np.finfo(float).eps * max(res.jac.shape) * (s[0] if s.size else 0.0)
    keep = s > threshold
    s, vt = s[keep], vt[keep]
    pcov = (vt.T / s**2) @ vt
    m = ydata.size
    n = popt.size
    if not absolute_sigma:
        if m > n:
            pcov = pcov * (2.0 * res.cost / (m - n))
        else:
            pcov = np.full((n, n), np.inf)
    if full_output:
        infodict = {"nfev": res.nfev, "fvec": res.fun}
        return popt, pcov, infodict, res.message, res.status
    return popt, pcov
