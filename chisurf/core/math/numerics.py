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

__all__ = [
    "OptimizeResult",
    "RootResults",
    "curve_fit",
    "least_squares",
    "lsq_linear",
    "nnls",
    "root_scalar",
]


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
        Evaluation budget in scipy's units. ``trf``/``dogbox`` count only
        the main-loop evaluations (default ``100 * n``), not the ``n`` per
        iteration the forward-difference Jacobian costs; MINPACK counts
        every one, so the budget handed to it is ``max_nfev * (n + 1)``.
        ``lm`` counts like MINPACK already (default ``100 * n * (n + 1)``).
        ``nfev`` in the result is MINPACK's count, Jacobian included.

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
    if method == "lm":
        budget = int(max_nfev) if max_nfev else 100 * n * (n + 1)
    else:
        budget = (int(max_nfev) if max_nfev else 100 * n) * (n + 1)
    minimizer.set_maxfev(budget)
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
        Evaluation budget (``max_nfev`` is accepted too), in scipy's units:
        every evaluation without bounds (MINPACK, default ``200 * (n + 1)``),
        main-loop evaluations with bounds (trf, see :func:`least_squares`).

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
    lb0, ub0 = bounds
    bounded = bool(np.any(np.isfinite(lb0)) or np.any(np.isfinite(ub0)))
    # scipy's choice and its budget units: without bounds curve_fit runs
    # MINPACK through leastsq (every evaluation counted, default
    # 200 * (n + 1)); with bounds it runs trf, where maxfev is max_nfev.
    fit_method = "trf" if bounded else "lm"
    if not bounded and max_nfev is None:
        max_nfev = 200 * (p0.size + 1)
    lb, ub = bounds
    lb_arr = np.broadcast_to(np.asarray(lb, dtype=float), p0.shape)
    ub_arr = np.broadcast_to(np.asarray(ub, dtype=float), p0.shape)
    p0 = np.clip(p0, lb_arr, ub_arr)
    res = least_squares(residuals, p0, bounds=bounds, max_nfev=max_nfev, method=fit_method)
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


# --------------------------------------------------------------------------
# Bounded scalar minimisation: ``scipy.optimize.minimize`` for the two
# methods chisurf uses, L-BFGS-B and Nelder-Mead (bff.minimize_lbfgsb /
# bff.minimize_nelder_mead). Other methods raise rather than silently
# substituting a different algorithm.

__all__ += ["minimize"]

_LBFGSB_OPTIONS = {"maxcor", "ftol", "gtol", "eps", "maxfun", "maxiter", "maxls"}
_NELDER_MEAD_OPTIONS = {"maxiter", "maxfev", "xatol", "fatol", "adaptive", "initial_simplex"}
_IGNORED_OPTIONS = {"disp", "iprint"}


class _LbfgsInvHess:
    """The L-BFGS inverse-Hessian approximation, as ``hess_inv`` in scipy."""

    def __init__(self, sk: np.ndarray, yk: np.ndarray):
        self.sk = sk
        self.yk = yk
        self.n_corrs = sk.shape[0]
        self.shape = (sk.shape[1], sk.shape[1])
        self.rho = 1.0 / np.einsum("ij,ij->i", sk, yk) if self.n_corrs else np.empty(0)

    def matvec(self, x) -> np.ndarray:
        """Return ``H x`` by the two-loop recursion."""
        q = np.array(x, dtype=float, copy=True).reshape(-1)
        alpha = np.empty(self.n_corrs)
        for i in range(self.n_corrs - 1, -1, -1):
            alpha[i] = self.rho[i] * np.dot(self.sk[i], q)
            q = q - alpha[i] * self.yk[i]
        for i in range(self.n_corrs):
            beta = self.rho[i] * np.dot(self.yk[i], q)
            q = q + self.sk[i] * (alpha[i] - beta)
        return q

    def __matmul__(self, x):
        x = np.asarray(x, dtype=float)
        if x.ndim == 1:
            return self.matvec(x)
        return np.column_stack([self.matvec(c) for c in x.T])

    def todense(self) -> np.ndarray:
        """Return ``H`` as a dense array."""
        return self @ np.eye(self.shape[0])


def _bounds_arrays(bounds, n: int):
    """``(lb, ub)`` float arrays (``-inf``/``inf`` for open sides), or ``None``."""
    if bounds is None:
        return None
    if hasattr(bounds, "lb") and hasattr(bounds, "ub"):
        lb = np.broadcast_to(np.asarray(bounds.lb, dtype=float), (n,)).copy()
        ub = np.broadcast_to(np.asarray(bounds.ub, dtype=float), (n,)).copy()
        return lb, ub
    bounds = list(bounds)
    if len(bounds) != n:
        raise ValueError("length of x0 != length of bounds")
    lb = np.array([-np.inf if b[0] is None else float(b[0]) for b in bounds])
    ub = np.array([np.inf if b[1] is None else float(b[1]) for b in bounds])
    return lb, ub


def _objective(fun, args, jac):
    """A bff.MinimizeObjective calling ``fun`` (and ``jac``) on ndarrays."""
    bff = _bff()

    class _Objective(bff.MinimizeObjective):
        def evaluate(self, x):
            value = fun(np.asarray(x, dtype=float), *args)
            if jac is True:
                value = value[0]
            return float(np.asarray(value).item())

        def evaluate_with_gradient(self, x):
            x = np.asarray(x, dtype=float)
            if jac is True:
                value, grad = fun(x, *args)
            else:
                value, grad = fun(x, *args), jac(x, *args)
            grad = np.asarray(grad, dtype=float).ravel()
            out = np.empty(grad.size + 1)
            out[0] = float(np.asarray(value).item())
            out[1:] = grad
            return out

    return _Objective()


def _restricted(fun, jac, i_fixed: np.ndarray, x_fixed: np.ndarray):
    """``fun``/``jac`` over the free variables only (scipy's _Remove_From_Func)."""

    def expand(x_free, *args):
        x = np.empty(i_fixed.size)
        x[i_fixed] = x_fixed
        x[~i_fixed] = x_free
        return x

    if jac is True:

        def fun_free(x_free, *args):
            value, grad = fun(expand(x_free), *args)
            return value, np.asarray(grad, dtype=float)[~i_fixed]

        return fun_free, True

    def fun_free(x_free, *args):
        return fun(expand(x_free), *args)

    if callable(jac):

        def jac_free(x_free, *args):
            return np.asarray(jac(expand(x_free), *args), dtype=float)[~i_fixed]

        return fun_free, jac_free
    return fun_free, jac


def minimize(
    fun,
    x0,
    args=(),
    method=None,
    jac=None,
    bounds=None,
    tol=None,
    callback=None,
    options=None,
) -> OptimizeResult:
    """Minimise a scalar function -- ``scipy.optimize.minimize`` for L-BFGS-B
    and Nelder-Mead, on IMP.bff.

    Parameters
    ----------
    fun : callable
        ``fun(x, *args) -> float``; with ``jac=True`` it returns
        ``(f, gradient)``.
    x0 : array_like
        Start, shape ``(n,)``.
    args : tuple, optional
        Extra arguments to ``fun`` (and ``jac``).
    method : {"L-BFGS-B", "Nelder-Mead"}, optional
        ``None`` means L-BFGS-B when ``bounds`` are given, as in scipy. scipy's
        other methods are not provided and raise ``NotImplementedError``.
    jac : bool, callable or "2-point", optional
        ``True``: ``fun`` returns the gradient too; a callable computes it;
        ``None``/``False``/``"2-point"``: forward differences (L-BFGS-B).
    bounds : sequence of ``(min, max)`` or ``Bounds``, optional
        ``None`` on either side leaves it open.
    tol : float, optional
        L-BFGS-B: ``ftol`` and ``gtol``; Nelder-Mead: ``xatol`` and ``fatol``.
    callback : None
        Not supported; raises if given.
    options : dict, optional
        The method's scipy options (L-BFGS-B: maxcor, ftol, gtol, eps, maxfun,
        maxiter, maxls; Nelder-Mead: maxiter, maxfev, xatol, fatol, adaptive,
        initial_simplex). ``disp``/``iprint`` are accepted and ignored.

    Returns
    -------
    OptimizeResult
        ``x``, ``fun``, ``nit``, ``nfev``, ``status``, ``success``,
        ``message``; L-BFGS-B adds ``jac``, ``njev`` and ``hess_inv``,
        Nelder-Mead ``final_simplex``.
    """
    if callback is not None:
        raise NotImplementedError("callback is not supported by chisurf's minimize")
    x0 = np.atleast_1d(np.asarray(x0, dtype=float))
    if x0.ndim != 1:
        raise ValueError("'x0' must only have one dimension.")
    n = x0.size
    if method is None:
        if bounds is None:
            raise NotImplementedError(
                "method=None without bounds is BFGS in scipy, which is not provided; "
                "pass method='L-BFGS-B'"
            )
        method = "L-BFGS-B"
    meth = str(method).lower()
    options = dict(options or {})
    for key in _IGNORED_OPTIONS:
        options.pop(key, None)
    box = _bounds_arrays(bounds, n)
    if box is not None and np.any(box[0] > box[1]):
        raise ValueError("An upper bound is less than the corresponding lower bound.")

    if meth == "nelder-mead":
        if tol is not None:
            options.setdefault("xatol", tol)
            options.setdefault("fatol", tol)
        unknown = set(options) - _NELDER_MEAD_OPTIONS
        if unknown:
            raise TypeError(f"unsupported Nelder-Mead options: {sorted(unknown)}")
        simplex = options.get("initial_simplex")
        r = _bff().minimize_nelder_mead(
            _objective(fun, args, None),
            x0.tolist(),
            [] if box is None else box[0].tolist(),
            [] if box is None else box[1].tolist(),
            int(options.get("maxiter") or 0),
            int(options.get("maxfev") or 0),
            float(options.get("xatol", 1e-4)),
            float(options.get("fatol", 1e-4)),
            bool(options.get("adaptive", False)),
            [] if simplex is None else np.asarray(simplex, dtype=float).ravel().tolist(),
        )
        sim = np.asarray(r.final_simplex, dtype=float).reshape(n + 1, n)
        return OptimizeResult(
            x=np.asarray(r.x, dtype=float),
            fun=float(r.fun),
            nit=int(r.nit),
            nfev=int(r.nfev),
            status=int(r.status),
            success=bool(r.success),
            message=str(r.message),
            final_simplex=(sim, np.asarray(r.final_simplex_values, dtype=float)),
        )

    if meth != "l-bfgs-b":
        raise NotImplementedError(
            f"minimize(method={method!r}) is not provided; chisurf supports "
            "'L-BFGS-B' and 'Nelder-Mead'"
        )
    if jac is False or jac == "2-point":
        jac = None
    if isinstance(jac, str):
        raise NotImplementedError(f"jac={jac!r} is not provided; use '2-point'")
    if tol is not None:
        options.setdefault("ftol", tol)
        options.setdefault("gtol", tol)
    unknown = set(options) - _LBFGSB_OPTIONS
    if unknown:
        raise TypeError(f"unsupported L-BFGS-B options: {sorted(unknown)}")

    # scipy answers outright when the bounds fix every variable, and removes
    # the fixed ones before L-BFGS-B sees them -- but only when the gradient
    # is differenced: it has already turned ``jac=True`` into a callable by
    # then, and with a gradient L-BFGS-B keeps ``lb == ub`` variables itself.
    i_fixed = None
    if box is not None:
        fixed = box[0] == box[1]
        if np.all(fixed):
            x = box[0].copy()
            value = fun(x, *args)
            if jac is True:
                value = value[0]
            return OptimizeResult(
                x=x,
                fun=float(np.asarray(value).item()),
                success=True,
                message="All independent variables were fixed by bounds.",
                nfev=1,
                njev=0,
                nhev=0,
            )
        if np.any(fixed) and jac is None:
            i_fixed = fixed
            x_fixed = box[0][fixed]
            fun, jac = _restricted(fun, jac, i_fixed, x_fixed)
            x0 = x0[~fixed]
            box = (box[0][~fixed], box[1][~fixed])

    use_gradient = jac is True or callable(jac)
    r = _bff().minimize_lbfgsb(
        _objective(fun, args, jac if use_gradient else None),
        x0.tolist(),
        [] if box is None else box[0].tolist(),
        [] if box is None else box[1].tolist(),
        use_gradient,
        int(options.get("maxcor", 10)),
        float(options.get("ftol", 2.2204460492503131e-09)),
        float(options.get("gtol", 1e-5)),
        float(options.get("eps", 1e-8)),
        int(options.get("maxfun", 15000)),
        int(options.get("maxiter", 15000)),
        int(options.get("maxls", 20)),
    )
    x = np.asarray(r.x, dtype=float)
    g = np.asarray(r.jac, dtype=float)
    k = int(r.n_corrections)
    m = x.size
    hess_inv = _LbfgsInvHess(
        np.asarray(r.correction_s, dtype=float).reshape(k, m),
        np.asarray(r.correction_y, dtype=float).reshape(k, m),
    )
    if i_fixed is not None:
        x_full = np.empty(i_fixed.size)
        x_full[i_fixed] = x_fixed
        x_full[~i_fixed] = x
        g_full = np.full(i_fixed.size, np.nan)
        g_full[~i_fixed] = g
        x, g = x_full, g_full
    return OptimizeResult(
        x=x,
        fun=float(r.fun),
        jac=g,
        nit=int(r.nit),
        nfev=int(r.nfev),
        njev=int(r.njev),
        status=int(r.status),
        success=bool(r.success),
        message=str(r.message),
        hess_inv=hess_inv,
    )


# --------------------------------------------------------------------------
# ODE integration: ``scipy.integrate.odeint`` (LSODA) on bff.odeint.

__all__ += ["ODEintWarning", "odeint"]


class ODEintWarning(Warning):
    """Warning raised during the execution of `odeint`, as in scipy."""


def odeint(
    func,
    y0,
    t,
    args=(),
    Dfun=None,
    col_deriv=0,
    full_output=0,
    ml=None,
    mu=None,
    rtol=None,
    atol=None,
    tcrit=None,
    h0=0.0,
    hmax=0.0,
    hmin=0.0,
    ixpr=0,
    mxstep=0,
    mxhnil=0,
    mxordn=12,
    mxords=5,
    printmessg=0,
    tfirst=False,
):
    """Integrate ``dy/dt = func(y, t, *args)`` -- ``scipy.integrate.odeint``
    on IMP.bff's port of the same LSODA.

    Parameters
    ----------
    func : callable
        ``func(y, t, *args) -> dy/dt`` (``func(t, y, *args)`` with
        ``tfirst=True``).
    y0 : array_like
        State at ``t[0]``.
    t : array_like
        Output times; the first is the start.
    args : tuple, optional
        Extra arguments to ``func``.
    Dfun, col_deriv, ml, mu : None
        A user Jacobian (full or banded) is not provided; LSODA differences
        the full Jacobian itself, as scipy does without ``Dfun``. Passing one
        raises ``NotImplementedError``.
    full_output : bool, optional
        Also return scipy's ``infodict``.
    rtol, atol, tcrit, h0, hmax, hmin, ixpr, mxstep, mxhnil, mxordn, mxords
        scipy's options, with scipy's defaults.
    printmessg : bool, optional
        Warn with the convergence message even on success.
    tfirst : bool, optional
        ``func`` takes ``t`` first.

    Returns
    -------
    y : ndarray, shape (len(t), len(y0))
        The solution at each time. On a failure (an ``ODEintWarning`` is
        issued) the rows after the last reached time are NaN.
    infodict : dict
        With ``full_output``: ``hu``, ``tcur``, ``tolsf``, ``tsw``, ``nst``,
        ``nfe``, ``nje``, ``nqu``, ``imxer``, ``lenrw``, ``leniw``, ``mused``,
        ``message``.
    """
    import warnings

    if Dfun is not None or col_deriv or ml is not None or mu is not None:
        raise NotImplementedError(
            "odeint: a user Jacobian (Dfun, col_deriv, ml, mu) is not provided; "
            "LSODA differences the full Jacobian"
        )
    if not isinstance(args, tuple):
        args = (args,)
    y0 = np.array(y0, dtype=float, copy=True).ravel()
    t = np.array(t, dtype=float, copy=True).ravel()
    bff = _bff()

    class _Rhs(bff.OdeFunction):
        def evaluate(self, y, tt):
            y = np.asarray(y, dtype=float)
            out = func(tt, y, *args) if tfirst else func(y, tt, *args)
            return np.asarray(out, dtype=float).ravel()

    def _tol(v):
        if v is None:
            return []
        return np.atleast_1d(np.asarray(v, dtype=float)).tolist()

    r = bff.odeint(
        _Rhs(),
        y0.tolist(),
        t.tolist(),
        _tol(rtol),
        _tol(atol),
        [] if tcrit is None else _tol(tcrit),
        float(h0),
        float(hmax),
        float(hmin),
        int(ixpr),
        int(mxstep or 0),
        int(mxhnil),
        int(mxordn),
        int(mxords),
    )
    y = np.asarray(r.y, dtype=float).reshape(len(t), len(y0))
    if r.istate < 0:
        warnings.warn(
            f"{r.message} Run with full_output = 1 to get quantitative information.",
            ODEintWarning,
            stacklevel=2,
        )
    elif printmessg:
        warnings.warn(r.message, ODEintWarning, stacklevel=2)
    if not full_output:
        return y
    info = {
        "hu": np.asarray(r.hu, dtype=float),
        "tcur": np.asarray(r.tcur, dtype=float),
        "tolsf": np.asarray(r.tolsf, dtype=float),
        "tsw": np.asarray(r.tsw, dtype=float),
        "nst": np.asarray(r.nst, dtype=np.int32),
        "nfe": np.asarray(r.nfe, dtype=np.int32),
        "nje": np.asarray(r.nje, dtype=np.int32),
        "nqu": np.asarray(r.nqu, dtype=np.int32),
        "imxer": int(r.imxer),
        "lenrw": int(r.lenrw),
        "leniw": int(r.leniw),
        "mused": np.asarray(r.mused, dtype=np.int32),
        "message": r.message,
    }
    return y, info


class RootResults(OptimizeResult):
    """``scipy.optimize.RootResults``: ``root``, ``iterations``,
    ``function_calls``, ``converged``, ``flag``, ``method``."""


def root_scalar(f, args=(), method=None, bracket=None, xtol=None, rtol=None, maxiter=None):
    """A root of the scalar ``f`` inside ``bracket``, as ``scipy.optimize.root_scalar``.

    Only the bracketed form is served -- ``method`` ``None`` or ``"brentq"``,
    which is what scipy picks for a bracket -- and it runs scipy's own Brent
    loop ported into IMP.bff, so root, iterations and calls are scipy's.

    Parameters
    ----------
    f : callable
        ``f(x, *args) -> float``.
    args : tuple, optional
        Extra arguments for ``f``.
    method : {None, "brentq"}, optional
        The bracketed method.
    bracket : sequence of two floats
        ``[a, b]`` with ``f(a)`` and ``f(b)`` of opposite sign.
    xtol, rtol : float, optional
        Absolute and relative tolerance (scipy's defaults when omitted).
    maxiter : int, optional
        Iteration limit (scipy's default 100).

    Returns
    -------
    RootResults

    Raises
    ------
    ValueError
        ``f(a)`` and ``f(b)`` have the same sign.
    """
    if method not in (None, "brentq"):
        raise NotImplementedError(f"root_scalar: method {method!r} (only 'brentq')")
    if bracket is None or len(bracket) != 2:
        raise ValueError("root_scalar: a two-element bracket is required")
    bff = _bff()
    extra = tuple(args) if isinstance(args, (tuple, list)) else (args,)

    class _Scalar(bff.MinimizeObjective):
        def evaluate(self, x):
            return float(f(float(x[0]), *extra))

    kwargs = {}
    if xtol is not None:
        kwargs["xtol"] = float(xtol)
    if rtol is not None:
        kwargs["rtol"] = float(rtol)
    if maxiter is not None:
        kwargs["maxiter"] = int(maxiter)
    r = bff.root_brentq(_Scalar(), float(bracket[0]), float(bracket[1]), **kwargs)
    return RootResults(
        root=r.root,
        iterations=r.iterations,
        function_calls=r.function_calls,
        converged=bool(r.converged),
        flag=r.flag,
        method="brentq",
    )
