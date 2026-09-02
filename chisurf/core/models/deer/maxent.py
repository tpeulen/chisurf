"""Maximum-entropy (MaxEnt) model-free distance-distribution inversion for DEER.

An alternative to Tikhonov regularisation: recover a non-negative ``P(r)`` from
the intramolecular form factor ``K @ P = V`` by maximising the Shannon–Jaynes
entropy ``S = -sum_i p_i log(p_i / m_i)`` subject to the data, i.e. minimising

    Q(P) = chi2(P) / 2 - alpha * S(P),   P >= 0,   sum(P) = 1.

That is the ``1/2 chi2 - alpha S`` spelling of the weight, i.e.
:attr:`~chisurf.core.fitting.inversion.EntropyWeight.HALF_CHI2` at the
inversion seam, *with* the probability-simplex constraint. The solve runs in
the shared compiled engine; the weight selection (a discrepancy criterion or
an L-curve corner) stays here.

This module carried its own damped exponential fixed-point iteration
(``p = m * exp(-grad/alpha)``, renormalised) until 2026-09-02. It did not
converge to the minimiser of the objective above at the weights this module
actually sweeps: measured against an independent optimiser on a 120x60
dipolar problem, the iteration at its shipped settings overshot the optimal
``Q`` by **+187%** at ``alpha = 0.1``, **+990%** at ``0.01`` and **+4760%**
at ``0.001``, agreeing only near ``alpha = 1``. Since the automatic weight
grid is ``logspace(-3, 1.3)``, most of every sweep was scored on
badly-solved inversions. The engine lands within 0.1% of the same referee
across that whole grid.

**It costs time, and the cost is the honest reason to read this twice.**
Re-measured on that same 120x60 fixture: the engine is *slower* per solve
(61 ms against 14 ms at ``alpha = 1e-3``, 16 ms against 0.6 ms at
``alpha = 1``, where the old iteration hit its tolerance almost at once),
and end-to-end ``maxent_distance_distribution`` is **2.1x slower** (414 ms
against 196 ms for the discrepancy sweep, 450 ms against 223 ms for the
L-curve sweep). That is a regression in wall-clock, taken deliberately:
unlike the FCS MEM loop -- which is *correct* and merely runs a fixed count,
and whose default therefore stays put under the owner's standing decision --
this iteration was returning a different answer than the objective it
documents, so the trade here is a wrong answer for a slower right one, not
speed for tidiness.

One user-visible consequence beyond the fix: with the sweep now scored on
properly-solved inversions, ``method='lcurve'`` selects a different corner
(``alpha = 0.18`` against ``0.0017`` on the fixture above). The
``'discrepancy'`` default is unaffected (``alpha = 0.001`` either way).
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fitting.inversion import EntropyWeight, maxent

from .tikhonov import second_derivative_operator


def maxent_inversion(
    kernel: np.ndarray,
    b: np.ndarray,
    weights: np.ndarray,
    alpha: float,
    prior: np.ndarray | None = None,
    p_init: np.ndarray | None = None,
    n_iter: int = 1000,
    damping: float = 0.3,
    tol: float = 1e-10,
) -> np.ndarray:
    """Return MaxEnt probability masses ``p`` (``sum(p) = 1``) for ``K @ p = b``.

    Parameters
    ----------
    kernel : numpy.ndarray
        Dipolar kernel ``K`` of shape ``(nt, nr)`` (probability-mass convention:
        ``K @ p`` is the form factor when ``p`` are masses summing to one).
    b : numpy.ndarray
        Target form factor ``(nt,)``.
    weights : numpy.ndarray
        Per-point weights ``1/sigma**2`` (scalar-broadcast or length ``nt``).
    alpha : float
        Entropy regularisation weight (larger -> smoother/flatter).
    prior : numpy.ndarray, optional
        Prior masses ``m`` (the entropy reference measure); uniform when ``None``.
    p_init : numpy.ndarray, optional
        Accepted for call compatibility and ignored: the engine does not take
        a warm start, and warm-starting the iteration this replaced made it
        *worse* rather than better (it walked away from a good point), which
        is part of how its non-convergence was found.
    n_iter, damping, tol : int, float, float
        Iteration budget and convergence tolerance for the engine.
        ``damping`` belonged to the replaced fixed point and is ignored.

    Returns
    -------
    numpy.ndarray
        Non-negative masses summing to one, of shape ``(nr,)``.
    """
    K = np.asarray(kernel, dtype=float)
    b = np.asarray(b, dtype=float).ravel()
    nr = K.shape[1]

    m = (np.ones(nr) / nr) if prior is None else np.clip(prior, 1e-12, None)
    m = m / m.sum()

    return maxent(
        K, b, max(float(alpha), 1e-12),
        convention=EntropyWeight.HALF_CHI2,
        weights=weights,
        prior=m,
        normalise=True,
        max_iter=max(int(n_iter), 500),
        tol=float(tol),
    )


def maxent_distance_distribution(
    kernel: np.ndarray,
    r: np.ndarray,
    v_target: np.ndarray,
    sigma: float = 1.0,
    alpha: float | None = None,
    n_iter: int = 1000,
    n_alpha: int = 20,
    method: str = "discrepancy",
    return_lcurve: bool = False,
):
    """Invert ``K @ P = v_target`` for a non-negative ``P(r)`` by MaxEnt.

    Parameters
    ----------
    kernel : numpy.ndarray
        Dipolar kernel ``K(t, r)`` of shape ``(nt, nr)``.
    r : numpy.ndarray
        Distance axis (Å).
    v_target : numpy.ndarray
        Intramolecular form factor to fit ``(nt,)``.
    sigma : float
        Noise level; sets the weight ``1/sigma**2``.
    alpha : float, optional
        Entropy weight; auto-selected when ``None`` or ``<= 0``.
    n_iter : int
        MaxEnt iterations per solve.
    n_alpha : int
        Number of log-spaced ``alpha`` values sampled for auto-selection.
    method : str
        Auto-selection criterion: ``'discrepancy'`` (default — the smoothest
        solution whose data misfit is within a small tolerance of the best
        achievable, so the fit is as good as an unregularised inversion) or
        ``'lcurve'`` (the L-curve corner). ``'discrepancy'`` is far more robust
        inside the outer fit loop.
    return_lcurve : bool
        When True, also return an ``info`` dict with the sampled ``alphas``,
        residual norms ``rho``, roughness ``eta`` and the selected index.

    Returns
    -------
    (numpy.ndarray, float[, dict])
        The area-normalised distribution ``P(r)``, the ``alpha`` used and,
        when ``return_lcurve`` is set, the L-curve ``info`` dict.
    """
    r = np.asarray(r, dtype=float)
    dr = float(np.mean(np.diff(r))) if r.size > 1 else 1.0
    K = np.asarray(kernel, dtype=float)
    b = np.asarray(v_target, dtype=float)
    # Solve the *unweighted* form-factor problem (as Tikhonov does): the entropy
    # weight ``alpha`` then lives on the same scale for both methods and the
    # discrepancy criterion behaves well. ``sigma`` is accepted for API symmetry
    # but does not rescale the entropy balance.
    w = 1.0
    L = second_derivative_operator(r.size)

    info: dict | None = None
    if alpha is not None and alpha > 1e-8:
        # A concrete, non-trivial alpha was requested (floored for stability).
        p = maxent_inversion(K, b, w, max(float(alpha), 1e-6), n_iter=n_iter)
        alpha = float(alpha)
    else:
        alphas = np.logspace(-3, 1.3, int(n_alpha))  # small -> large smoothing
        rho = np.empty(alphas.size)
        eta = np.empty(alphas.size)
        masses: list[np.ndarray] = []
        for i, a in enumerate(alphas):
            p_i = maxent_inversion(K, b, w, a, n_iter=n_iter)
            masses.append(p_i)
            rho[i] = float(np.linalg.norm(K @ p_i - b))
            eta[i] = float(np.linalg.norm(L @ p_i))

        if str(method).lower() == "lcurve":
            from chisurf.core.math.regularization import discrete_lcurve_corner

            k = discrete_lcurve_corner(rho, eta)
            idx = int(k) if k is not None else int(np.argmin(rho))
        else:
            # Discrepancy: pick the LARGEST alpha (smoothest P) whose misfit is
            # still within 2% of the best achievable, so the reconstruction is
            # as faithful as an unregularised fit (comparable to Tikhonov) while
            # staying as smooth as the data allow.
            rho_min = float(np.min(rho))
            ok = np.where(rho <= rho_min * 1.02)[0]
            idx = int(ok.max()) if ok.size else int(np.argmin(rho))

        alpha = float(alphas[idx])
        # Refine the chosen alpha with a longer, warm-started solve.
        p = maxent_inversion(K, b, w, alpha, p_init=masses[idx], n_iter=n_iter * 3)
        info = {"alphas": alphas, "rho": rho, "eta": eta, "corner": idx}

    # masses (sum=1) -> density, area-normalised on r with the trapezoidal rule
    # (consistent with the Tikhonov path).
    from scipy.integrate import trapezoid

    density = p / dr
    area = float(trapezoid(density, r))
    if area > 0:
        density = density / area
    if return_lcurve:
        return density, float(alpha), info
    return density, float(alpha)
