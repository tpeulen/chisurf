"""Conjugate distributions of ebFRET's variational HMM (``+ebfret/+analysis/+dist``).

A line-by-line port of the ``D = 1`` branches of ebFRET's distribution
package: the Dirichlet (transition rows and initial-state weights), the
Normal-Gamma empirical-Bayes step, the Normal-Wishart E-/M-steps and KL
divergence, and the log densities the plots evaluate.

The numerics are kept exactly, including the small constants the reference
adds (``G + 1e-10`` in the M-step, ``eps`` inside the Dirichlet h-step, the
step-length constraint of its Newton solver) -- they change converged numbers
in the last digits, and the port is checked against the reference to ~1e-8.

MATLAB's ``[K N]`` column convention is kept: a per-trace parameter stacked
over ``N`` traces is an array of shape ``(K, N)``, a stacked transition matrix
``(K, K, N)``.
"""

from __future__ import annotations

import numpy as np
from scipy.special import digamma, gammaln, polygamma

__all__ = [
    "beta_log_pdf",
    "dirichlet_h_step",
    "dirichlet_kl_div",
    "dirichlet_mean",
    "dirichlet_rand",
    "dirichlet_tau",
    "dirichlet_var",
    "gamma_log_pdf",
    "normgamma_h_step",
    "normgamma_mean",
    "normgamma_mode",
    "normgamma_var",
    "normwish_e_step",
    "normwish_kl_div",
    "normwish_m_step",
    "studt_log_pdf",
]

#: MATLAB's ``eps``: the double-precision machine epsilon.
EPS = np.finfo(float).eps


def _trigamma(x):
    """Return MATLAB's ``psi(1, x)``.

    Parameters
    ----------
    x : array_like
        Argument.

    Returns
    -------
    numpy.ndarray
    """
    return polygamma(1, x)


# --------------------------------------------------------------------------- #
# Dirichlet
# --------------------------------------------------------------------------- #
def dirichlet_kl_div(alpha_p, alpha_q):
    """Kullback-Leibler divergence ``KL(Dir(alpha_p) || Dir(alpha_q))``.

    Port of ``+dist/+dirichlet/kl_div.m``. Parameters sharing a zero in both
    arguments are left out of that row, as the reference does.

    Parameters
    ----------
    alpha_p, alpha_q : array_like
        Dirichlet parameters, shape ``(K,)`` or ``(L, K)``.

    Returns
    -------
    numpy.ndarray
        Divergence per row, shape ``(1,)`` for a vector and ``(L,)`` for a
        matrix.
    """
    p = np.asarray(alpha_p, dtype=float)
    q = np.asarray(alpha_q, dtype=float)
    if p.ndim <= 1 or sum(s > 1 for s in p.shape) <= 1:
        p = p.reshape(1, -1)
        q = q.reshape(1, -1)

    def _kl(pp, qq):
        return (
            gammaln(pp.sum(axis=-1))
            - gammaln(qq.sum(axis=-1))
            - (gammaln(pp) - gammaln(qq)).sum(axis=-1)
            + ((pp - qq) * (digamma(pp) - digamma(pp.sum(axis=-1, keepdims=True)))).sum(axis=-1)
        )

    msk = (p == 0) & (q == 0)
    if np.any(msk):
        out = np.zeros(p.shape[0])
        for row in range(p.shape[0]):
            keep = ~msk[row]
            out[row] = _kl(p[row, keep], q[row, keep])
        return out
    return np.atleast_1d(_kl(p, q))


def dirichlet_h_step(
    w_alpha, alpha0=None, max_iter: int = 1000, threshold: float = 1e-6, eps: float = 1e-12
):
    """Empirical-Bayes step for a Dirichlet prior (Newton solver).

    Port of ``+dist/+dirichlet/h_step.m``: solve
    ``psi(sum alpha) - psi(alpha_k) = -mean_n E[ln theta_k]`` for ``alpha``.

    Parameters
    ----------
    w_alpha : array_like
        Posterior parameters over ``N`` traces: ``(K, N)`` for one Dirichlet
        (initial-state weights) or ``(L, K, N)`` for ``L`` of them
        (transition-matrix rows).
    alpha0 : array_like, optional
        Initial guess; ones by default.
    max_iter : int
        Maximum Newton iterations.
    threshold : float
        Convergence threshold on ``max |dalpha| / alpha``.
    eps : float
        Pseudo-count added to ``w_alpha`` before taking expectations.

    Returns
    -------
    numpy.ndarray
        ``(K,)`` for ``(K, N)`` input, ``(L, K)`` for ``(L, K, N)`` input.
    """
    w = np.asarray(w_alpha, dtype=float)
    transposed = False
    if w.ndim == 3:
        n_rows, n_states, _ = w.shape
    elif w.ndim == 2:
        n_rows = 1
        n_states = w.shape[0]
        w = w.reshape(1, n_states, w.shape[1])
        transposed = True
    else:
        raise ValueError(f"w_alpha must have shape (K, N) or (L, K, N), got {w.shape}")

    if alpha0 is None:
        alpha = np.ones((n_rows, n_states))
    else:
        alpha = np.array(alpha0, dtype=float).reshape(n_rows, n_states)

    we = w + eps
    e_log_q = np.mean(digamma(we) - digamma(we.sum(axis=1, keepdims=True)), axis=2)

    it = 0
    while True:
        total = alpha.sum(axis=1, keepdims=True)
        g = digamma(total) - (digamma(alpha) - e_log_q)
        z = _trigamma(total)
        q = -_trigamma(alpha)
        b = (g / q).sum(axis=1, keepdims=True) / (1.0 / z + (1.0 / q).sum(axis=1, keepdims=True))
        dalpha = (g - b) / q
        # Keep alpha + dalpha >= 1e-3 alpha: a shrinking component limits the
        # step of its whole row; a growing one leaves it at 1.
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.fmin((1 - 1e-3) * alpha / dalpha, 1.0)
        step = np.where(dalpha > 0, ratio, 1.0)
        delta = np.nanmin(step, axis=1, keepdims=True)
        delta[dalpha.sum(axis=1) == 0, :] = 0.0
        if np.max(np.abs(dalpha).ravel() / (alpha.ravel() + EPS)) < threshold:
            break
        if it >= max_iter:
            break
        alpha = alpha - delta * dalpha
        it += 1

    if transposed:
        return alpha.reshape(n_states)
    return alpha


def dirichlet_rand(alpha, rng: np.random.Generator | None = None):
    """Draw from a Dirichlet, normalising Gamma draws along the last axis.

    Port of ``+dist/+dirichlet/rand.m`` for a single draw.

    Parameters
    ----------
    alpha : array_like
        ``(K,)`` or ``(L, K)`` parameters.
    rng : numpy.random.Generator, optional
        Random source.

    Returns
    -------
    numpy.ndarray
        Same shape as ``alpha``; rows sum to one.
    """
    rng = np.random.default_rng() if rng is None else rng
    a = np.asarray(alpha, dtype=float)
    draws = rng.gamma(a)
    return draws / draws.sum(axis=-1, keepdims=True)


def dirichlet_mean(alpha):
    """Expectation of a Dirichlet, row-wise (``+dist/+dirichlet/mean.m``).

    Parameters
    ----------
    alpha : array_like
        ``(K,)`` or ``(L, K)``.

    Returns
    -------
    numpy.ndarray
    """
    a = np.asarray(alpha, dtype=float)
    total = a.sum(axis=-1, keepdims=True)
    return a / (total + (total == 0))


def dirichlet_var(alpha):
    """Variance of each Dirichlet component, row-wise (``+dist/+dirichlet/var.m``).

    Parameters
    ----------
    alpha : array_like
        ``(K,)`` or ``(L, K)``.

    Returns
    -------
    numpy.ndarray
    """
    a = np.asarray(alpha, dtype=float)
    total = a.sum(axis=-1, keepdims=True)
    return a * (total - a) / (total**2 * (total + 1))


def dirichlet_tau(alpha):
    """Most likely dwell time of each state from transition-row Dirichlets.

    Port of ``+dist/+dirichlet/tau.m``: the self-transition probability
    ``rho`` is Beta-distributed; the mode of the implied density on
    ``tau = -1 / log(rho)`` is found on a fixed grid of 2e4 ``rho`` values.

    Parameters
    ----------
    alpha : array_like
        Transition Dirichlet parameters, ``(K, K)``.

    Returns
    -------
    numpy.ndarray
        Dwell-time mode per state, ``(K,)``.
    """
    alpha = np.asarray(alpha, dtype=float)
    a = np.diag(alpha).copy()
    b = alpha.sum(axis=1) - a
    log_b = gammaln(a) + gammaln(b) - gammaln(a + b)
    e_rho = a / (a + b)
    out = np.zeros(a.shape[0])
    for k in range(a.shape[0]):
        rho = np.exp(np.linspace(np.log(1e-4 * e_rho[k]), np.log(0.5), 10000))
        rho = np.concatenate([rho, 1 - rho[::-1]])
        tau = -1.0 / np.log(rho)
        with np.errstate(divide="ignore", invalid="ignore"):
            log_pdf = (
                -log_b[k]
                - 2 * np.log(tau)
                - (a[k] / tau)
                + np.log(1 - np.exp(-1.0 / tau)) * (b[k] - 1)
            )
        out[k] = tau[_nanargmax(log_pdf)]
    return out


def _nanargmax(values) -> int:
    """First index of the maximum, ignoring NaN (MATLAB ``[~, i] = max(v)``).

    Parameters
    ----------
    values : numpy.ndarray
        One-dimensional values.

    Returns
    -------
    int
    """
    v = np.asarray(values, dtype=float)
    if np.all(np.isnan(v)):
        return 0
    return int(np.nanargmax(v))


# --------------------------------------------------------------------------- #
# Normal-Gamma
# --------------------------------------------------------------------------- #
def normgamma_h_step(
    w_m, w_beta, w_a, w_b, a0=2.0, max_iter: int = 1000, threshold: float = 1e-6, constraints=None
):
    """Empirical-Bayes step for a Normal-Gamma prior.

    Port of ``+dist/+normgamma/h_step.m``: solve

    ``m = E[m l] / E[l]``, ``beta = 1 / (E[m^2 l] - E[m l]^2 / E[l])``,
    ``psi(a) - log(a) = E[log l] - log E[l]``, ``b = a / E[l]``,

    then clamp ``beta >= 1e-3`` and ``a >= 1 + 1e-3``. ``b`` is computed from
    the unclamped ``a``, as in the reference.

    Parameters
    ----------
    w_m, w_beta, w_a, w_b : array_like
        Posterior parameters, shape ``(K, N)``.
    a0 : float
        Initial Newton value for ``a`` (``hmm.h_step`` passes ``1``).
    max_iter : int
        Maximum Newton iterations.
    threshold : float
        Relative convergence threshold on ``a``.
    constraints : dict, optional
        ``{name: (lo, hi)}``; defaults to the reference's.

    Returns
    -------
    tuple of numpy.ndarray
        ``(u_m, u_beta, u_a, u_b)``, each ``(K,)``.
    """
    w_m = np.asarray(w_m, dtype=float)
    w_beta = np.asarray(w_beta, dtype=float)
    w_a = np.asarray(w_a, dtype=float)
    w_b = np.asarray(w_b, dtype=float)
    if constraints is None:
        constraints = {"beta": (1e-3, np.inf), "a": (1 + 1e-3, np.inf)}

    e_l = np.mean(w_a / w_b, axis=1)
    log_e_l = np.log(e_l)
    e_ml = np.mean(w_m * w_a / w_b, axis=1)
    e_m2l = np.mean(1.0 / w_beta + w_m**2 * w_a / w_b, axis=1)
    e_log_l = np.mean(digamma(w_a) - np.log(w_b), axis=1)

    a_old = np.asarray(a0, dtype=float)
    a = np.asarray(a0, dtype=float)
    it = 0
    while True:
        if it >= max_iter:
            break
        g = digamma(a) - np.log(a) - (e_log_l - log_e_l)
        hess = _trigamma(a) - 1.0 / a
        da = g / hess
        a = np.maximum(a - da, 1 + 1e-3 * (a - 1))
        if np.all(np.abs(a - a_old) / a < threshold):
            break
        it += 1
        a_old = a

    u = {
        "m": e_ml / e_l,
        "beta": 1.0 / (e_m2l - e_ml**2 / e_l),
        "a": np.broadcast_to(a, e_l.shape).astype(float),
        "b": a / e_l,
    }
    for name, (lo, hi) in constraints.items():
        if name in u:
            value = np.array(u[name], dtype=float)
            value[value < lo] = lo
            value[value > hi] = hi
            u[name] = value
    return u["m"], u["beta"], u["a"], u["b"]


def normgamma_mean(m, beta, a, b):
    """Expectations ``(E[mu], E[lambda])`` of a Normal-Gamma (``mean.m``).

    Parameters
    ----------
    m, beta, a, b : array_like
        Normal-Gamma parameters.

    Returns
    -------
    tuple of numpy.ndarray
    """
    return np.asarray(m, dtype=float), np.asarray(a, dtype=float) / np.asarray(b, dtype=float)


def normgamma_var(m, beta, a, b):
    """Variances ``(V[mu], V[lambda])`` of a Normal-Gamma (``var.m``).

    Parameters
    ----------
    m, beta, a, b : array_like
        Normal-Gamma parameters.

    Returns
    -------
    tuple of numpy.ndarray
    """
    beta = np.asarray(beta, dtype=float)
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    return b / (beta * (a - 1)), a / b**2


def normgamma_mode(m, beta, a, b):
    """Modes ``(M[mu], M[lambda])`` of a Normal-Gamma (``mode.m``).

    Parameters
    ----------
    m, beta, a, b : array_like
        Normal-Gamma parameters.

    Returns
    -------
    tuple of numpy.ndarray
        The precision mode is NaN where ``a < 1``.
    """
    a = np.asarray(a, dtype=float)
    mode_l = (a - 1) / np.asarray(b, dtype=float)
    mode_l = np.where(a < 1, np.nan, mode_l)
    return np.asarray(m, dtype=float), mode_l


# --------------------------------------------------------------------------- #
# Normal-Wishart, D = 1
# --------------------------------------------------------------------------- #
def normwish_e_step(w, x):
    """Expected log emission density ``E_q[ln p(x_t | z_t = k)]``.

    Port of the ``D = 1`` branch of ``+dist/+normwish/e_step.m``.

    Parameters
    ----------
    w : HmmParams
        Variational parameters (uses ``mu, beta, W, nu``).
    x : array_like
        Observations, shape ``(T,)``.

    Returns
    -------
    numpy.ndarray
        Shape ``(T, K)``.
    """
    x = np.asarray(x, dtype=float).reshape(-1)
    mu = np.asarray(w.mu, dtype=float).reshape(-1)
    beta = np.asarray(w.beta, dtype=float).reshape(-1)
    W = np.asarray(w.W, dtype=float).reshape(-1)
    nu = np.asarray(w.nu, dtype=float).reshape(-1)
    e_ln_det_l = np.log(2 * W) + digamma(0.5 * nu)
    dx = x[:, None] - mu[None, :]
    dxwdx = dx * (W[None, :] * dx)
    e_delta2 = (1.0 / beta)[None, :] + nu[None, :] * dxwdx
    return np.log(2 * np.pi) * (-0.5) + (0.5 * e_ln_det_l[None, :] - 0.5 * e_delta2)


def normwish_m_step(u, x, g):
    """Variational M-step of the Normal-Wishart emission parameters.

    Port of the ``D = 1`` branch of ``+dist/+normwish/m_step.m``.

    Parameters
    ----------
    u : HmmParams
        Prior.
    x : array_like
        Observations, ``(T,)``.
    g : array_like
        State responsibilities, ``(T, K)``.

    Returns
    -------
    dict
        ``{"mu", "beta", "W", "nu"}`` of the posterior, each ``(K,)``.
    dict
        ``{"xmean", "xvar"}``, each ``(K,)``.
    """
    x = np.asarray(x, dtype=float).reshape(-1)
    g = np.asarray(g, dtype=float)
    u_mu = np.asarray(u.mu, dtype=float).reshape(-1)
    u_beta = np.asarray(u.beta, dtype=float).reshape(-1)
    u_W = np.asarray(u.W, dtype=float).reshape(-1)
    u_nu = np.asarray(u.nu, dtype=float).reshape(-1)

    G = g.sum(axis=0) + 1e-10
    g0 = g / G[None, :]
    xmean = (g0 * x[:, None]).sum(axis=0)
    dx = x[:, None] - xmean[None, :]
    xvar = (g0 * dx * dx).sum(axis=0)

    beta = u_beta + G
    mu = (u_beta * u_mu + G * xmean) / beta
    nu = u_nu + G
    dx0 = xmean - u_mu
    xvar0 = dx0 * dx0
    W = 1.0 / (1.0 / u_W + G * xvar + (u_beta * G) / beta * xvar0)
    return {"mu": mu, "beta": beta, "W": W, "nu": nu}, {"xmean": xmean, "xvar": xvar}


def normwish_kl_div(w, u):
    """``KL(q(mu, L | w) || p(mu, L | u))`` per state, ``D = 1``.

    Port of ``+dist/+normwish/kl_div.m``.

    Parameters
    ----------
    w, u : HmmParams
        Posterior and prior (use ``mu, beta, W, nu``).

    Returns
    -------
    numpy.ndarray
        Shape ``(K,)``.
    """
    w_mu, w_beta, w_W, w_nu = (
        np.asarray(getattr(w, n), dtype=float).reshape(-1) for n in ("mu", "beta", "W", "nu")
    )
    u_mu, u_beta, u_W, u_nu = (
        np.asarray(getattr(u, n), dtype=float).reshape(-1) for n in ("mu", "beta", "W", "nu")
    )
    D = 1
    e_ln_det_l = np.log(w_W) + D * np.log(2) + digamma(0.5 * (w_nu + 1 - 1))
    log_det_w_u = np.log(u_W)
    log_det_w_w = np.log(w_W)
    e_tr = w_W / u_W
    dmwdm = w_W * (w_mu - u_mu) ** 2

    def log_b(log_det_w, nu):
        return (
            -(nu / 2) * log_det_w
            - (nu * D / 2) * np.log(2)
            - (D * (D - 1) / 4) * np.log(np.pi)
            - gammaln(0.5 * (nu + 1 - 1))
        )

    e_log_nw_w = (
        0.5 * e_ln_det_l
        + 0.5 * D * np.log(w_beta / (2 * np.pi))
        - 0.5 * D
        + log_b(log_det_w_w, w_nu)
        + 0.5 * (w_nu - D - 1) * e_ln_det_l
        - 0.5 * w_nu * D
    )
    e_log_norm_u = 0.5 * (
        D * np.log(u_beta / (2 * np.pi)) + e_ln_det_l - D * u_beta / w_beta - u_beta * w_nu * dmwdm
    )
    e_log_wish_u = log_b(log_det_w_u, u_nu) + 0.5 * (u_nu - D - 1) * e_ln_det_l - 0.5 * w_nu * e_tr
    return e_log_nw_w - (e_log_norm_u + e_log_wish_u)


# --------------------------------------------------------------------------- #
# Log densities
# --------------------------------------------------------------------------- #
def beta_log_pdf(x, a, b):
    """Log density of a Beta distribution (``+dist/+beta/log_pdf.m``).

    Parameters
    ----------
    x, a, b : array_like
        Broadcast against each other.

    Returns
    -------
    numpy.ndarray
    """
    x, a, b = np.broadcast_arrays(*(np.asarray(v, dtype=float) for v in (x, a, b)))
    with np.errstate(divide="ignore", invalid="ignore"):
        return (
            gammaln(a + b) - gammaln(a) - gammaln(b) + (a - 1) * np.log(x) + (b - 1) * np.log(1 - x)
        )


def gamma_log_pdf(x, a, b):
    """Log density of a Gamma (shape-rate) distribution (``+dist/+gamma/log_pdf.m``).

    Parameters
    ----------
    x, a, b : array_like
        Broadcast against each other.

    Returns
    -------
    numpy.ndarray
    """
    x, a, b = np.broadcast_arrays(*(np.asarray(v, dtype=float) for v in (x, a, b)))
    with np.errstate(divide="ignore", invalid="ignore"):
        return a * np.log(b) - gammaln(a) + (a - 1) * np.log(x) - b * x


def studt_log_pdf(x, m, lam, nu):
    """Log density of a Student t distribution (``+dist/+studt/log_pdf.m``).

    Parameters
    ----------
    x, m, lam, nu : array_like
        Value, location, precision and degrees of freedom; broadcast.

    Returns
    -------
    numpy.ndarray
    """
    x, m, lam, nu = np.broadcast_arrays(*(np.asarray(v, dtype=float) for v in (x, m, lam, nu)))
    return (
        gammaln(0.5 * (nu + 1))
        - gammaln(0.5 * nu)
        + 0.5 * np.log(lam / (np.pi * nu))
        - 0.5 * (nu + 1) * np.log(1 + lam * (x - m) ** 2 / nu)
    )
