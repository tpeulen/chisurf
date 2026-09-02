r"""One regularised inversion: every non-negative regularised linear solve.

ChiSurf inverts the same problem class in five places -- a DEER distance
distribution, an FCS diffusion-time distribution, a TCSPC lifetime or
distance distribution, a 2D fluorescence-lifetime correlation spectrum --
and each of them is

.. math::

    \min_{x \ge 0} \; \chi^2_w(x) + \text{(a regulariser)}

with the regulariser either a smoothness seminorm (Tikhonov) or a negative
entropy relative to a prior (maximum entropy). This module is the single
seam onto the compiled solvers; nothing else in the tree should implement
the iteration.

Why this module exists at all: the convention
--------------------------------------------

The five callers do **not** write the same objective. They differ in

* whether the misfit term is :math:`\chi^2` or :math:`\tfrac12\chi^2`;
* whether the regularisation weight multiplies the penalty linearly or
  squared;
* whether the solution is constrained to a probability simplex.

Those are not cosmetic. A weight that means :math:`\alpha` to one caller and
:math:`\alpha^2` to another differs by orders of magnitude over the log grids
these solvers are swept on, and getting it wrong does not raise -- the fit
converges and returns a plausible, differently-regularised answer. That
failure has been paid for once already (the FCS
:math:`\sigma\!\approx\!1` renormalisation; see
``test/models/test_fcs_maxent_engine.py``), which is why the weight
conventions here are named types rather than a comment, and why every caller
has a test that pins its objective rather than only its convergence.

The engine's own convention
---------------------------

The compiled maximum-entropy engine minimises

.. math::

    F(p) = \chi^2_w(p) - \nu^2 S(p; m), \qquad
    S(p; m) = \sum_i \left[(p_i - m_i) - p_i \log(p_i/m_i)\right]

over :math:`p \ge 0`, with :math:`\chi^2_w = \sum_i w_i (Ap-b)_i^2` and
:math:`w_i = 1/\sigma_i^2`. :class:`EntropyWeight` maps each caller's weight
onto that :math:`\nu`; :func:`entropy_weight_to_nu` is the only place in the
tree that conversion is written down.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from chisurf.core.math.regularization import (
    LCurveData,
    discrete_lcurve_corner,
    sample_lcurve,
)

__all__ = [
    "EntropyWeight",
    "LCurveData",
    "MaxEntResult",
    "SmoothnessWeight",
    "difference_operator",
    "discrete_lcurve_corner",
    "entropy_weight_to_nu",
    "maxent",
    "maxent_normal_equations",
    "nu_to_entropy_weight",
    "sample_lcurve",
    "tikhonov_nnls",
]

#: Default iteration cap handed to the compiled maximum-entropy engine.
DEFAULT_MAXENT_ITERATIONS = 500

#: Default convergence tolerance (the Skilling-Bryan ``TEST`` quantity).
DEFAULT_MAXENT_TOLERANCE = 1.0e-8


@dataclass(frozen=True)
class MaxEntResult:
    """A maximum-entropy solve, owned by Python.

    The compiled engine returns a struct whose array members SWIG exposes as
    *borrowed* views into the C++ object. Reading one after the owning result
    has been collected is a use-after-free -- it does not raise reliably; on
    the NumPy path it surfaced as a nonsense length. The seam therefore
    copies every array out while the owner is alive and hands back this,
    so no caller can hold a dangling view and no caller has to know the
    engine's type.

    Attributes
    ----------
    p : numpy.ndarray
        The recovered non-negative amplitudes.
    chisq, S, Q : float
        Misfit, entropy and the combined objective at ``p``.
    p_esm : numpy.ndarray
        The early-stop-maximum (effectively unregularised) amplitudes.
    chisq_esm, S_esm, Q_esm : float
        The same three quantities at ``p_esm``.
    niter : int
        Iterations the engine ran.
    success : bool
        Whether the engine reports convergence.
    """

    p: np.ndarray
    chisq: float
    S: float
    Q: float
    p_esm: np.ndarray
    chisq_esm: float
    S_esm: float
    Q_esm: float
    niter: int
    success: bool


class EntropyWeight(Enum):
    r"""How a caller's entropy weight relates to the engine's :math:`\nu`.

    Each member names the objective the caller believes it is minimising.
    ``value`` is the caller-facing weight symbol used in that objective.

    Attributes
    ----------
    HALF_CHI2
        :math:`\min \tfrac12 \chi^2_w - \alpha S`. The Cambridge/QuickFit
        spelling: the FCS MEM inversion and the DEER maximum-entropy
        inversion both write their weight this way. Maps to
        :math:`\nu = \sqrt{2\alpha}`.
    CHI2
        :math:`\min \chi^2_w - \nu^2 S`. The engine's own documented
        objective; the weight passes through unchanged.
    RUN_MEM
        :math:`\min \chi^2_w - \tfrac12 \nu_{\text{run}} S`. The form the
        compiled TCSPC driver takes its weight in, so a caller that already
        holds a ``nu`` destined for that driver declares it here. Maps to
        :math:`\nu = \sqrt{\nu_{\text{run}}/2}`.
    """

    HALF_CHI2 = "alpha"
    CHI2 = "nu"
    RUN_MEM = "nu_run"


class SmoothnessWeight(Enum):
    r"""How a caller's Tikhonov weight enters the penalty.

    Attributes
    ----------
    AMPLITUDE
        Penalty :math:`w^2 \|Lx\|^2` -- the weight is the amplitude of the
        augmented block, so the augmented system stacks :math:`wL`. This is
        the DEER spelling.
    POWER
        Penalty :math:`w \|Lx\|^2` -- the weight is the power, so the
        augmented system stacks :math:`\sqrt{w}L`. This is the spelling used
        by the 2D inverse-Laplace solvers and by most textbook/SciPy code.
    """

    AMPLITUDE = "amplitude"
    POWER = "power"


def entropy_weight_to_nu(weight: float, convention: EntropyWeight) -> float:
    r"""Convert a caller's entropy weight into the engine's :math:`\nu`.

    Parameters
    ----------
    weight : float
        The regularisation weight as the caller writes it, in the objective
        named by ``convention``.
    convention : EntropyWeight
        Which objective the weight belongs to.

    Returns
    -------
    float
        The engine's :math:`\nu`, i.e. the weight in
        :math:`\chi^2_w - \nu^2 S`.

    Raises
    ------
    ValueError
        If ``weight`` is negative or ``convention`` is unknown.

    Examples
    --------
    >>> entropy_weight_to_nu(0.5, EntropyWeight.HALF_CHI2)
    1.0
    >>> entropy_weight_to_nu(2.0, EntropyWeight.RUN_MEM)
    1.0
    """
    w = float(weight)
    if w < 0.0:
        raise ValueError("regularisation weight must be non-negative")
    if convention is EntropyWeight.HALF_CHI2:
        return float(np.sqrt(2.0 * w))
    if convention is EntropyWeight.CHI2:
        return w
    if convention is EntropyWeight.RUN_MEM:
        return float(np.sqrt(0.5 * w))
    raise ValueError(f"unknown entropy-weight convention: {convention!r}")


def nu_to_entropy_weight(nu: float, convention: EntropyWeight) -> float:
    r"""Convert the engine's :math:`\nu` back into a caller's weight.

    The exact inverse of :func:`entropy_weight_to_nu`; provided so a caller
    that reports the weight it used can report it in its own units.

    Parameters
    ----------
    nu : float
        The engine's entropy weight.
    convention : EntropyWeight
        Which objective to express the weight in.

    Returns
    -------
    float
        The weight in the caller's convention.

    Raises
    ------
    ValueError
        If ``nu`` is negative or ``convention`` is unknown.
    """
    n = float(nu)
    if n < 0.0:
        raise ValueError("nu must be non-negative")
    if convention is EntropyWeight.HALF_CHI2:
        return 0.5 * n * n
    if convention is EntropyWeight.CHI2:
        return n
    if convention is EntropyWeight.RUN_MEM:
        return 2.0 * n * n
    raise ValueError(f"unknown entropy-weight convention: {convention!r}")


def difference_operator(n: int, order: int = 2) -> np.ndarray:
    """Return the discrete finite-difference operator of the given order.

    For ``order=2`` the rows are ``[1, -2, 1]``, i.e. the second-derivative
    (roughness) operator every Tikhonov caller in the tree penalises.

    Parameters
    ----------
    n : int
        Number of grid points the operator acts on.
    order : int, optional
        Difference order. ``order <= 0``, or a grid too short to support the
        requested order, degrades to the identity so the caller still gets a
        usable (amplitude-penalising) operator rather than an empty matrix.

    Returns
    -------
    numpy.ndarray
        ``(n - order, n)`` difference matrix, or ``(n, n)`` identity when the
        difference is not defined on this grid.

    Examples
    --------
    >>> difference_operator(4)
    array([[ 1., -2.,  1.,  0.],
           [ 0.,  1., -2.,  1.]])
    >>> difference_operator(2).shape
    (2, 2)
    """
    n = int(n)
    order = int(order)
    if order <= 0 or n <= order:
        return np.eye(n, dtype=float)
    D = np.eye(n, dtype=float)
    for _ in range(order):
        D = np.diff(D, axis=0)
    return D


def tikhonov_nnls(
    A: np.ndarray,
    b: np.ndarray,
    weight: float,
    *,
    convention: SmoothnessWeight,
    L: np.ndarray | None = None,
    order: int = 2,
    max_iter: int | None = None,
) -> np.ndarray:
    r"""Solve :math:`\min_{x\ge 0} \|Ax-b\|^2 + \text{pen}(w)\|Lx\|^2`.

    The one non-negative Tikhonov solve in the tree. The augmented system
    ``[A; s L] x = [b; 0]`` is passed to a Lawson-Hanson non-negative
    least-squares solver, with the stacking factor ``s`` set by
    ``convention`` -- ``s = w`` for :attr:`SmoothnessWeight.AMPLITUDE` (a
    penalty of :math:`w^2\|Lx\|^2`) and ``s = \sqrt{w}`` for
    :attr:`SmoothnessWeight.POWER` (a penalty of :math:`w\|Lx\|^2`).

    Parameters
    ----------
    A : numpy.ndarray
        ``(m, n)`` design matrix. Any data weighting must already be folded
        into ``A`` and ``b``.
    b : numpy.ndarray
        ``(m,)`` target vector.
    weight : float
        Regularisation weight, in the units named by ``convention``.
    convention : SmoothnessWeight
        Whether ``weight`` is the amplitude or the power of the penalty.
        There is no default: choosing wrongly does not fail, it silently
        regularises by a squared or square-rooted amount.
    L : numpy.ndarray, optional
        Regularisation operator. When ``None``, ``difference_operator(n,
        order)`` is used.
    order : int, optional
        Difference order for the default operator.
    max_iter : int, optional
        Iteration cap for the non-negative solve. ``None`` uses the solver's
        own default (``3n``).

    Returns
    -------
    numpy.ndarray
        The non-negative solution ``x`` of shape ``(n,)``.

    Raises
    ------
    ValueError
        If ``weight`` is negative, the shapes disagree, or ``convention`` is
        not a :class:`SmoothnessWeight`.
    """
    from scipy.optimize import nnls

    A = np.asarray(A, dtype=float)
    b = np.asarray(b, dtype=float).ravel()
    if A.ndim != 2:
        raise ValueError("A must be two-dimensional")
    if A.shape[0] != b.size:
        raise ValueError(f"A has {A.shape[0]} rows but b has {b.size} entries")
    w = float(weight)
    if w < 0.0:
        raise ValueError("regularisation weight must be non-negative")

    if convention is SmoothnessWeight.AMPLITUDE:
        stack = w
    elif convention is SmoothnessWeight.POWER:
        stack = float(np.sqrt(w))
    else:
        raise ValueError(f"unknown smoothness-weight convention: {convention!r}")

    n = A.shape[1]
    if L is None:
        L = difference_operator(n, order)
    L = np.asarray(L, dtype=float)
    if L.ndim != 2 or L.shape[1] != n:
        raise ValueError(f"L must have {n} columns, got shape {L.shape}")

    aug_A = np.vstack([A, stack * L])
    aug_b = np.concatenate([b, np.zeros(L.shape[0], dtype=float)])
    kwargs = {} if max_iter is None else {"maxiter": int(max_iter)}
    x, _ = nnls(aug_A, aug_b, **kwargs)
    return x


def _engine():
    """Return the photon library's maximum-entropy engine, or say what is missing.

    Returns
    -------
    module
        The photon library.

    Raises
    ------
    RuntimeError
        If the library is missing or predates the weighted, prior-aware
        entry point.
    """
    try:
        import tttrlib
    except ImportError as error:  # pragma: no cover - a hard dependency
        raise RuntimeError(
            "regularised inversion needs the photon library, which is not importable"
        ) from error
    if not hasattr(tttrlib, "maxent_invert_weighted"):
        raise RuntimeError(
            "the installed photon library has no weighted maximum-entropy entry "
            "point (maxent_invert_weighted); rebuild it"
        )
    return tttrlib


def _prepare_maxent(A, b, weights, prior):
    """Validate and canonicalise the maximum-entropy inputs.

    Returns
    -------
    tuple
        ``(A_flat, b, w, m, n_rows, n_cols)`` ready for the engine.
    """
    A = np.ascontiguousarray(np.asarray(A, dtype=float))
    b = np.asarray(b, dtype=float).ravel()
    if A.ndim != 2:
        raise ValueError("A must be two-dimensional")
    if A.shape[0] != b.size:
        raise ValueError(f"A has {A.shape[0]} rows but b has {b.size} entries")
    n_rows, n_cols = A.shape

    if weights is None:
        w = np.ones(n_rows, dtype=float)
    else:
        w = np.broadcast_to(np.asarray(weights, dtype=float).ravel(), (n_rows,))
        w = np.ascontiguousarray(w, dtype=float)

    if prior is None:
        m = np.full(n_cols, 1.0 / n_cols, dtype=float)
    else:
        m = np.asarray(prior, dtype=float).ravel()
        if m.size != n_cols:
            raise ValueError(f"prior must have {n_cols} entries, got {m.size}")
        m = np.clip(m, 1.0e-300, None)
    return A.ravel(), b, w, m, n_rows, n_cols


def maxent(
    A: np.ndarray,
    b: np.ndarray,
    weight: float,
    *,
    convention: EntropyWeight,
    weights: np.ndarray | None = None,
    prior: np.ndarray | None = None,
    normalise: bool = False,
    max_iter: int = DEFAULT_MAXENT_ITERATIONS,
    tol: float = DEFAULT_MAXENT_TOLERANCE,
) -> np.ndarray:
    r"""Maximum-entropy inversion of ``A x = b`` for a non-negative ``x``.

    Runs the compiled Skilling-Bryan engine on the objective named by
    ``convention``.

    Parameters
    ----------
    A : numpy.ndarray
        ``(m, n)`` design matrix.
    b : numpy.ndarray
        ``(m,)`` target vector.
    weight : float
        Regularisation weight, in the units named by ``convention``.
    convention : EntropyWeight
        Which objective ``weight`` is written in. No default: see the module
        docstring for why this is a required, named argument.
    weights : array_like, optional
        Per-point chi-square weights :math:`w_i = 1/\sigma_i^2`. Scalars
        broadcast. ``None`` means unweighted.
    prior : array_like, optional
        The entropy prior ``m``; uniform (summing to one) when ``None``.
    normalise : bool, optional
        Constrain the solution to the probability simplex
        :math:`\sum_i x_i = 1`. The engine solves the unconstrained problem,
        so this is imposed exactly rather than by rescaling the answer -- see
        :func:`_maxent_simplex`.
    max_iter : int, optional
        Engine iteration cap.
    tol : float, optional
        Engine convergence tolerance.

    Returns
    -------
    numpy.ndarray
        The non-negative solution, of shape ``(n,)``.

    Raises
    ------
    ValueError
        If the shapes disagree or ``convention`` is unknown.
    RuntimeError
        If the compiled engine is unavailable.
    """
    flat, b, w, m, n_rows, n_cols = _prepare_maxent(A, b, weights, prior)
    nu = entropy_weight_to_nu(weight, convention)
    if normalise:
        return _maxent_simplex(flat, b, w, m, nu, n_rows, n_cols, max_iter, tol)
    return np.asarray(
        _engine().maxent_invert_weighted(
            flat, b, w, m, nu, int(n_rows), int(n_cols), int(max_iter), float(tol)
        ),
        dtype=float,
    )


def _maxent_simplex(flat, b, w, m, nu, n_rows, n_cols, max_iter, tol,
                    n_outer: int = 40, sum_tol: float = 1.0e-9):
    r"""Maximum entropy with the solution constrained to ``sum(x) == 1``.

    The engine solves the unconstrained problem, and simply rescaling its
    answer is *not* the constrained solution -- it is a feasible point of a
    different objective. The constrained stationarity condition

    .. math::

        \nabla \tfrac12\chi^2 + \alpha \log(x/m) = \lambda - \alpha

    differs from the unconstrained one only by a constant on the right-hand
    side, and a constant there is exactly a uniform rescaling of ``log m``.
    So the constrained solution *is* an unconstrained solve with the prior
    multiplied by one scalar ``c``, and ``sum(x)`` is monotone in ``c``:
    bisecting ``log c`` recovers the constrained optimum exactly rather than
    approximately.

    Returns
    -------
    numpy.ndarray
        The solution with ``sum(x) == 1`` to ``sum_tol``.
    """
    engine = _engine().maxent_invert_weighted

    def solve(log_c):
        return np.asarray(
            engine(flat, b, w, m * float(np.exp(log_c)), nu,
                   int(n_rows), int(n_cols), int(max_iter), float(tol)),
            dtype=float,
        )

    lo, hi = -8.0, 8.0
    p = solve(0.0)
    if abs(p.sum() - 1.0) < sum_tol:
        return p
    for _ in range(int(n_outer)):
        mid = 0.5 * (lo + hi)
        p = solve(mid)
        s = float(p.sum())
        if abs(s - 1.0) < sum_tol:
            break
        if s > 1.0:
            hi = mid
        else:
            lo = mid
    total = float(p.sum())
    return p / total if total > 0.0 else p


def maxent_normal_equations(
    H: np.ndarray,
    g0: np.ndarray,
    prior: np.ndarray,
    const_chi2: float,
    weight: float,
    *,
    convention: EntropyWeight,
    max_iter: int = 200,
    tol: float = 1.0e-4,
    min_prob: float = 1.0e-12,
):
    r"""Maximum entropy on an already-formed quadratic chi-square.

    The second entry point into the same engine, for callers that build the
    normal equations themselves (a TCSPC design matrix crosses the boundary
    once and is reused across an outer nuisance search, so re-forming
    :math:`A` per solve would be wasteful). Minimises

    .. math::

        Q(p) = \tfrac12 p^T H p - g_0^T p + \text{const} - \tfrac12 \nu_r S(p; m)

    with :math:`\nu_r` the weight in :attr:`EntropyWeight.RUN_MEM` units.

    Parameters
    ----------
    H : numpy.ndarray
        ``(n, n)`` curvature of the chi-square term.
    g0 : numpy.ndarray
        ``(n,)`` linear term.
    prior : numpy.ndarray
        ``(n,)`` entropy prior.
    const_chi2 : float
        The data-only constant of the chi-square.
    weight : float
        Regularisation weight, in the units named by ``convention``.
    convention : EntropyWeight
        Which objective ``weight`` is written in.
    max_iter, tol, min_prob : int, float, float
        Iteration cap, convergence tolerance and the floor on ``p``.

    Returns
    -------
    MaxEntResult
        The solve, with every array copied into Python-owned memory -- see
        :class:`MaxEntResult` for why the engine's own struct is not returned.

    Raises
    ------
    RuntimeError
        If the compiled engine is unavailable.
    """
    tttrlib = _engine()
    if not hasattr(tttrlib, "tcspc_run_mem"):
        raise RuntimeError(
            "the installed photon library has no maximum-entropy optimiser "
            "(tcspc_run_mem); rebuild it"
        )
    nu = entropy_weight_to_nu(weight, convention)
    nu_run = nu_to_entropy_weight(nu, EntropyWeight.RUN_MEM)
    H = np.asarray(H, dtype=float)
    g0 = np.asarray(g0, dtype=float).ravel()
    prior = np.asarray(prior, dtype=float).ravel()
    # Bound to a name, not chained: the array members below are borrowed
    # views into this object, so it has to outlive the copies.
    raw = tttrlib.tcspc_run_mem(
        H.ravel().tolist(), g0.tolist(), prior.tolist(),
        float(const_chi2), float(nu_run), int(max_iter), float(tol), float(min_prob),
    )
    return MaxEntResult(
        p=np.array(raw.p, dtype=float, copy=True),
        chisq=float(raw.chisq),
        S=float(raw.S),
        Q=float(raw.Q),
        p_esm=np.array(raw.p_esm, dtype=float, copy=True),
        chisq_esm=float(raw.chisq_esm),
        S_esm=float(raw.S_esm),
        Q_esm=float(raw.Q_esm),
        niter=int(raw.niter),
        success=bool(raw.success),
    )
