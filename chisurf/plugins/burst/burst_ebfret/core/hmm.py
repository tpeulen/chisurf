"""Variational-Bayes Gaussian HMM of ebFRET (``+ebfret/+analysis/+hmm``).

A line-by-line port of the functions ebFRET's main window reaches: the VBEM
E-/M-steps, forward-backward and Viterbi, the per-trace ``vbayes`` loop, the
prior guess, posterior initialisation for restarts, the empirical-Bayes
``h_step``, and the analysis summary (``report`` with ``h_step_remap``). The
two signal helpers of ``+analysis`` -- ``x_lim`` and ``photobleach_index`` --
live here too.

Everything is ``D = 1`` (a FRET signal), which is what the GUI analyses.
State numbers returned by Viterbi are **1-based**, as in the reference, since
they are written to exported files as they are.

The reference ships C++ MEX files for ``forwback`` and ``viterbi``; the port
follows the native MATLAB fallbacks (``forwback_native.m``,
``viterbi_native.m``). The MEX ``forwback`` accumulates its messages in
single precision, so a MATLAB run that loaded the MEX agrees with this port
to ~1e-7 rather than to rounding.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.special import digamma

from . import _matlab as ml
from . import dist
from .model import Expect, HmmParams, Viterbi

__all__ = [
    "e_step",
    "forwback",
    "guess_prior",
    "h_step",
    "h_step_remap",
    "init_posterior",
    "init_prior",
    "kl_div",
    "m_step",
    "normalize",
    "photobleach_index",
    "report",
    "valid_prior",
    "vbayes",
    "vbayes_series",
    "viterbi",
    "viterbi_vb",
    "x_lim",
]


def _vec(value) -> np.ndarray:
    """Return ``value`` as a flat float array.

    Parameters
    ----------
    value : array_like
        Input.

    Returns
    -------
    numpy.ndarray
    """
    return np.asarray(value, dtype=float).reshape(-1)


def normalize(A, axis: int | None = None):
    """Normalise an array, over all elements or along one axis (``normalize.m``).

    A zero normaliser is replaced by one, so an all-zero row stays zero.

    Parameters
    ----------
    A : array_like
        Array.
    axis : int, optional
        Axis to normalise along; all elements when omitted.

    Returns
    -------
    A0 : numpy.ndarray
        Normalised array.
    C : float or numpy.ndarray
        Normalisation constant(s).
    """
    A = np.asarray(A, dtype=float)
    if axis is None:
        C = A.sum()
        return A / (C + (C == 0)), C
    C = A.sum(axis=axis, keepdims=True)
    return A / (C + (C == 0)), np.squeeze(C, axis=axis)


# --------------------------------------------------------------------------- #
# VBEM steps
# --------------------------------------------------------------------------- #
def e_step(w: HmmParams, x):
    """Expected log parameters under ``q(theta | w)`` (``e_step.m``).

    Parameters
    ----------
    w : HmmParams
        Variational parameters.
    x : array_like
        Observations, ``(T,)``.

    Returns
    -------
    E_ln_pi : numpy.ndarray
        ``(K,)``.
    E_ln_A : numpy.ndarray
        ``(K, K)``.
    E_ln_px_z : numpy.ndarray
        ``(T, K)``.
    """
    pi = _vec(w.pi)
    A = np.asarray(w.A, dtype=float).reshape(pi.size, pi.size)
    e_ln_pi = digamma(pi) - digamma(pi.sum())
    e_ln_a = digamma(A) - digamma(A.sum(axis=1, keepdims=True))
    return e_ln_pi, e_ln_a, dist.normwish_e_step(w, x)


def m_step(u: HmmParams, x, g, xi):
    """Variational M-step from the state statistics (``m_step.m``).

    Parameters
    ----------
    u : HmmParams
        Prior.
    x : array_like
        Observations, ``(T,)``.
    g : array_like
        Responsibilities, ``(T, K)``.
    xi : array_like
        Pairwise marginals, ``(T-1, K, K)``.

    Returns
    -------
    w : HmmParams
        Posterior.
    ev : dict
        ``{"xmean", "xvar"}`` per state.
    """
    g = np.asarray(g, dtype=float)
    xi = np.asarray(xi, dtype=float)
    emission, ev = dist.normwish_m_step(u, x, g)
    K = g.shape[1]
    w = HmmParams(
        mu=emission["mu"],
        beta=emission["beta"],
        W=emission["W"],
        nu=emission["nu"],
        A=np.asarray(u.A, dtype=float).reshape(K, K) + xi.reshape(-1, K, K).sum(axis=0),
        pi=_vec(u.pi) + g[0, :],
    )
    return w, ev


def kl_div(w: HmmParams, u: HmmParams) -> float:
    """``KL(q(theta | w) || p(theta | u))`` summed over all factors (``kl_div.m``).

    Parameters
    ----------
    w, u : HmmParams
        Posterior and prior.

    Returns
    -------
    float
    """
    K = _vec(w.pi).size
    d_pi = dist.dirichlet_kl_div(_vec(w.pi), _vec(u.pi))
    d_a = dist.dirichlet_kl_div(
        np.asarray(w.A, dtype=float).reshape(K, K), np.asarray(u.A, dtype=float).reshape(K, K)
    )
    d_mu_l = dist.normwish_kl_div(w, u)
    return float(np.sum(d_mu_l) + np.sum(d_a) + np.sum(d_pi))


def forwback(px_z, A, pi):
    """Scaled forward-backward message passing (``forwback_native.m``).

    Parameters
    ----------
    px_z : array_like
        Emission likelihoods, ``(T, K)``.
    A : array_like
        Transition matrix, ``(K, K)``; ``A[k, l] = p(z_{t+1} = l | z_t = k)``.
    pi : array_like
        Initial-state probabilities, ``(K,)``.

    Returns
    -------
    gamma : numpy.ndarray
        ``(T, K)`` posterior state probabilities.
    xi : numpy.ndarray
        ``(T-1, K, K)`` posterior pairwise probabilities.
    ln_Z : float
        Log normalisation, ``sum_t log c_t``.
    """
    px_z = np.asarray(px_z, dtype=float)
    A = np.asarray(A, dtype=float)
    pi = _vec(pi)
    T, K = px_z.shape
    alpha = np.zeros((T, K))
    beta = np.zeros((T, K))
    c = np.zeros(T)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        alpha[0] = pi * px_z[0]
        c[0] = alpha[0].sum()
        alpha[0] = alpha[0] / c[0]
        for t in range(1, T):
            at = (alpha[t - 1] @ A) * px_z[t]
            c[t] = at.sum()
            alpha[t] = at / c[t]
        beta[T - 1] = 1.0
        for t in range(T - 2, -1, -1):
            beta[t] = ((beta[t + 1] * px_z[t + 1]) @ A.T) / c[t + 1]
        gamma = alpha * beta
        pxz_b_c = (1.0 / c[1:])[:, None] * beta[1:] * px_z[1:]
        xi = alpha[:-1, :, None] * A[None, :, :] * pxz_b_c[:, None, :]
        ln_z = float(np.sum(np.log(c)))
    return gamma, xi, ln_z


def viterbi(ln_px_z, ln_A, ln_pi) -> np.ndarray:
    """Most likely state path (``viterbi_native.m``).

    Parameters
    ----------
    ln_px_z : array_like
        Log emission probabilities, ``(T, K)``.
    ln_A : array_like
        Log transition matrix, ``(K, K)``.
    ln_pi : array_like
        Log initial-state probabilities, ``(K,)``.

    Returns
    -------
    numpy.ndarray
        1-based state number per time point, ``(T,)``. Ties go to the lowest
        state number, as MATLAB's ``max`` does.
    """
    ln_px_z = np.asarray(ln_px_z, dtype=float)
    ln_A = np.asarray(ln_A, dtype=float)
    T, K = ln_px_z.shape
    omega = np.zeros((T, K))
    z_max = np.zeros((T, K), dtype=int)
    omega[0] = _vec(ln_pi) + ln_px_z[0]
    cols = np.arange(K)
    for t in range(1, T):
        scores = omega[t - 1][:, None] + ln_A  # [l, k]
        scores = np.where(np.isnan(scores), -np.inf, scores)
        best = np.argmax(scores, axis=0)
        z_max[t] = best
        omega[t] = scores[best, cols] + ln_px_z[t]
    z_hat = np.zeros(T, dtype=int)
    last = np.where(np.isnan(omega[T - 1]), -np.inf, omega[T - 1])
    z_hat[T - 1] = int(np.argmax(last))
    for t in range(T - 2, -1, -1):
        z_hat[t] = z_max[t + 1, z_hat[t + 1]]
    return z_hat + 1


def viterbi_vb(w: HmmParams, x):
    """Viterbi path under the variational parameter estimates (``viterbi_vb.m``).

    Parameters
    ----------
    w : HmmParams
        Posterior of the trace.
    x : array_like
        Observations, ``(T,)``.

    Returns
    -------
    z_hat : numpy.ndarray
        1-based states, ``(T,)``.
    x_hat : numpy.ndarray
        ``w.mu`` of the state at each time point, ``(T,)``.
    """
    e_ln_pi, e_ln_a, e_ln_px_z = e_step(w, x)
    z_hat = viterbi(e_ln_px_z, e_ln_a, e_ln_pi)
    return z_hat, _vec(w.mu)[z_hat - 1]


def vbayes(x, w0: HmmParams, u: HmmParams, threshold: float = 1e-5, max_iter: int = 100):
    """Variational Bayes EM for one trace (``vbayes.m``, ``ignore='none'``).

    The lower bound of iteration ``it`` is computed from the parameters going
    *into* that iteration's M-step; the loop stops from the third iteration on
    once the relative change drops below ``threshold`` or the bound is not
    finite.

    Parameters
    ----------
    x : array_like
        Observations, ``(T,)``.
    w0 : HmmParams
        Initial variational parameters.
    u : HmmParams
        Prior.
    threshold : float
        Relative convergence threshold.
    max_iter : int
        Iteration limit.

    Returns
    -------
    w : HmmParams
        Final variational parameters.
    L : numpy.ndarray
        Lower bound per iteration.
    expect : dict
        ``gamma``, ``xi``, ``ln_Z``, ``xmean``, ``xvar`` of the last iteration.
    """
    x = _vec(x)
    w = w0
    L = []
    g = xi = ln_z = ev = None
    for it in range(max_iter):
        e_ln_pi, e_ln_a, e_ln_px_z = e_step(w, x)
        with np.errstate(over="ignore", under="ignore"):
            g, xi, ln_z = forwback(np.exp(e_ln_px_z), np.exp(e_ln_a), np.exp(e_ln_pi))
        L.append(ln_z - kl_div(w, u))
        with np.errstate(divide="ignore", invalid="ignore"):
            w, ev = m_step(u, x, g, xi)
        if it > 1:
            with np.errstate(divide="ignore", invalid="ignore"):
                rel = abs((L[it] - L[it - 1]) / L[it - 1])
            if rel < threshold or not math.isfinite(L[it]):
                break
    expect = {"gamma": g, "xi": xi, "ln_Z": ln_z}
    if ev is not None:
        expect.update(ev)
    return w, np.asarray(L, dtype=float), expect


# --------------------------------------------------------------------------- #
# Priors and initial posteriors
# --------------------------------------------------------------------------- #
def x_lim(x, spread: int = 5):
    """Robust signal range from repeated medians and a histogram (``x_lim.m``).

    Parameters
    ----------
    x : array_like or sequence of array_like
        Signal, or a list of traces (concatenated).
    spread : int
        Number of median-of-half steps outward.

    Returns
    -------
    x_min, x_max : float
    """
    if isinstance(x, (list, tuple)):
        parts = [_vec(v) for v in x if v is not None]
        x = np.concatenate(parts) if parts else np.zeros(0)
    x = _vec(x)
    x0 = ml.median(x)
    left = [ml.median(x[x < x0])]
    right = [ml.median(x[x > x0])]
    for _ in range(1, spread):
        left.append(ml.median(x[x < left[-1]]))
        right.append(ml.median(x[x > right[-1]]))
    centers = ml.linspace(left[-1], right[-1], min(200, x.size / 10))
    h, b = ml.hist(x, centers)
    above = np.flatnonzero(h > 0.01 * np.max(h))
    x_min = ml.nan_max(b[above[0]], left[-1])
    x_max = ml.nan_min(b[above[-1]], right[-1])
    return x_min, x_max


def init_prior(theta: dict, counts: dict) -> HmmParams:
    """Prior from expected parameter values and prior counts (``init_prior.m``).

    Parameters
    ----------
    theta : dict
        ``mu``, ``lambda`` (precision) and ``tau`` (dwell time), each ``(K,)``.
    counts : dict
        Prior strength of ``mu``, ``lambda`` and ``tau``, each ``(K,)``.

    Returns
    -------
    HmmParams
    """
    tau = _vec(theta["tau"])
    K = tau.size
    counts_tau = _vec(counts["tau"])
    if K > 1:
        akk = np.exp(-1.0 / tau)
        e_a = (1 - np.eye(K)) * ((1 - akk) / (K - 1))[:, None] + np.eye(K) * akk[:, None]
        vals, vecs = np.linalg.eig(e_a.T)
        k = int(np.argmax(np.abs(vals) if np.iscomplexobj(vals) else vals))
        e_pi = normalize(np.real(vecs[:, k]))[0]
    else:
        e_a = np.ones((1, 1))
        e_pi = np.ones(1)
    return HmmParams(
        mu=_vec(theta["mu"]).copy(),
        beta=_vec(counts["mu"]).copy(),
        W=_vec(theta["lambda"]) / _vec(counts["lambda"]),
        nu=_vec(counts["lambda"]).copy(),
        A=counts_tau[:, None] * e_a,
        pi=np.mean(counts_tau) * e_pi,
    )


def guess_prior(x: Sequence, K: int, spread: int = 5, strength: float = 1.0) -> HmmParams:
    """Initial prior guessed from the pooled signal histogram (``guess_prior.m``).

    Parameters
    ----------
    x : sequence of array_like or None
        Traces. ``None`` or an empty trace (an excluded series) still counts
        with length 0 towards the mean trace length, as in the reference.
    K : int
        Number of states.
    spread : int
        Passed to :func:`x_lim`.
    strength : float
        Scale of all prior counts.

    Returns
    -------
    HmmParams
    """
    traces = [np.zeros(0) if v is None else _vec(v) for v in x]
    lengths = np.array([t.size for t in traces], dtype=float)
    pooled = np.concatenate(traces) if traces else np.zeros(0)
    x_min, x_max = x_lim(pooled, spread)
    mu = np.linspace(x_min, x_max, K + 2)
    theta = {
        "mu": mu[1:-1],
        "lambda": (12.0 / (x_max - x_min)) ** 2 * np.ones(K),
        "tau": 0.5 * np.mean(lengths) * np.ones(K),
    }
    counts = {
        "mu": 0.025 * strength * np.ones(K),
        "lambda": 1.0 * strength * np.ones(K),
        "tau": K * strength * np.ones(K),
    }
    return init_prior(theta, counts)


def init_posterior(
    x, u: HmmParams, draw_params: bool = False, rng: np.random.Generator | None = None
) -> HmmParams:
    """Initial variational parameters for one VBEM run (``init_posterior.m``).

    Parameters
    ----------
    x : array_like
        Observations, ``(T,)``.
    u : HmmParams
        Prior.
    draw_params : bool
        ``False``: one M-step with uniform state probabilities (the
        uninformative restart). ``True``: parameters drawn from the prior.
    rng : numpy.random.Generator, optional
        Random source for ``draw_params``.

    Returns
    -------
    HmmParams
    """
    x = _vec(x)
    K = _vec(u.mu).size
    T = x.size
    if not draw_params:
        w, _ = m_step(u, x, np.ones((T, K)) / K, np.ones((max(T - 1, 0), K, K)) / K**2)
        return w

    rng = np.random.default_rng() if rng is None else rng
    theta_pi = dist.dirichlet_rand(_vec(u.pi), rng)
    theta_a = dist.dirichlet_rand(np.asarray(u.A, dtype=float).reshape(K, K), rng)
    if np.any(np.isnan(theta_pi)):
        theta_pi = np.ones(K) / K
    if np.any(np.isnan(theta_a)):
        theta_a = np.where(np.isnan(theta_a), 1.0, theta_a)
        theta_a = normalize(theta_a, axis=1)[0]
    lam = np.zeros(K)
    mu = np.zeros(K)
    u_w, u_nu, u_mu, u_beta = _vec(u.W), _vec(u.nu), _vec(u.mu), _vec(u.beta)
    for k in range(K):
        # a one-dimensional Wishart(W, nu) is Gamma(nu / 2, scale 2 W)
        lam[k] = rng.gamma(u_nu[k] / 2.0, 2.0 * u_w[k])
        mu[k] = rng.normal(u_mu[k], math.sqrt(1.0 / (u_beta[k] * lam[k])))
    beta = u_beta + T / K
    nu = beta + 1
    return HmmParams(
        mu=(u_beta * u_mu + T / K * mu) / beta,
        beta=beta,
        W=lam / nu,
        nu=nu,
        A=np.asarray(u.A, dtype=float).reshape(K, K) + theta_a * (T - 1) / K,
        pi=_vec(u.pi) + theta_pi,
    )


def valid_prior(u: HmmParams) -> bool:
    """Whether every hyperparameter is in its domain (``valid_prior.m``).

    Parameters
    ----------
    u : HmmParams
        Parameters to check.

    Returns
    -------
    bool
    """
    with np.errstate(invalid="ignore"):
        return bool(
            np.all(np.asarray(u.A) > 0)
            and np.all(np.asarray(u.pi) > 0)
            and np.all(np.asarray(u.beta) > 0)
            and np.all(np.asarray(u.nu) > 0)
            and np.all(np.isfinite(u.mu))
            and np.all(np.asarray(u.W) > 0)
        )


def vbayes_series(
    x,
    u: HmmParams,
    w_prev: HmmParams | None,
    restarts: int,
    threshold: float,
    rng: np.random.Generator | None = None,
    vb_threshold: float = 1e-5,
    vb_max_iter: int = 100,
) -> dict:
    """Fit one series with restarts and keep the best (``run_vbayes.m``, loop body).

    Initial guesses are the previous posterior (when there is one), then, if
    ``restarts > 0``, one uninformative guess, then ``restarts - 1`` draws from
    the prior. Each runs :func:`vbayes` with its default threshold; a later
    restart replaces the current best only when its bound is higher by more
    than ``1e-2 * threshold * |L_max|``.

    Parameters
    ----------
    x : array_like
        Cropped, clipped signal of the series.
    u : HmmParams
        Prior.
    w_prev : HmmParams or None
        Previous posterior of this series.
    restarts : int
        The *Restarts* control.
    threshold : float
        The *Precision* control.
    rng : numpy.random.Generator, optional
        Random source for the drawn restarts.
    vb_threshold, vb_max_iter : float, int
        Passed to :func:`vbayes`; the reference uses its defaults.

    Returns
    -------
    dict
        ``posterior`` (HmmParams), ``expect`` (Expect or None), ``viterbi``
        (Viterbi or None), ``lowerbound`` (float) and ``restart`` (int; ``-1``
        when no valid posterior was found).

    Raises
    ------
    ValueError
        With no previous posterior and ``restarts == 0`` there is nothing to
        start from (the reference fails indexing an empty result there).
    """
    x = _vec(x)
    w0 = []
    if w_prev is not None and _vec(w_prev.mu).size:
        w0.append(w_prev)
    if restarts > 0:
        w0.append(init_posterior(x, u))
    for _ in range(2, int(restarts) + 1):
        w0.append(init_posterior(x, u, draw_params=True, rng=rng))
    if not w0:
        raise ValueError("no initial posterior: set Restarts > 0 for a series without a result")

    runs = [vbayes(x, guess, u, threshold=vb_threshold, max_iter=vb_max_iter) for guess in w0]
    l_max = runs[0][1][-1]
    r_max = 0
    for r in range(1, len(runs)):
        l_r = runs[r][1][-1]
        if (l_r - l_max) > 1e-2 * threshold * abs(l_max) or math.isnan(l_max):
            r_max = r
            l_max = l_r
    w, L, E = runs[r_max]
    if valid_prior(w):
        state, mean = viterbi_vb(w, x)
        gamma, xi = E["gamma"], E["xi"]
        K = gamma.shape[1]
        return {
            "posterior": w,
            "expect": Expect(
                z=gamma[1:, :].sum(axis=0),
                z1=gamma[0, :].copy(),
                zz=xi.reshape(-1, K, K).sum(axis=0),
                x=_vec(E["xmean"]).copy(),
                xx=_vec(E["xvar"]) + _vec(E["xmean"]) ** 2,
            ),
            "viterbi": Viterbi(state=state, mean=mean),
            "lowerbound": float(L[-1]),
            "restart": int(r_max + 1 + restarts - len(w0)),
        }
    return {
        "posterior": u.copy(),
        "expect": None,
        "viterbi": None,
        "lowerbound": 0.0,
        "restart": -1,
    }


# --------------------------------------------------------------------------- #
# Empirical Bayes
# --------------------------------------------------------------------------- #
def _stack(w_list: Sequence[HmmParams]):
    """Stack posteriors into MATLAB's ``[K N]`` / ``[K K N]`` arrays.

    Parameters
    ----------
    w_list : sequence of HmmParams
        Posteriors of ``N`` traces.

    Returns
    -------
    dict
        ``mu, beta, a, b, pi`` as ``(K, N)`` and ``A`` as ``(K, K, N)``.
    """
    mu = np.stack([_vec(w.mu) for w in w_list], axis=1)
    K = mu.shape[0]
    return {
        "mu": mu,
        "beta": np.stack([_vec(w.beta) for w in w_list], axis=1),
        "a": 0.5 * np.stack([_vec(w.nu) for w in w_list], axis=1),
        "b": 0.5 / np.stack([_vec(w.W) for w in w_list], axis=1),
        "A": np.stack([np.asarray(w.A, dtype=float).reshape(K, K) for w in w_list], axis=2),
        "pi": np.stack([_vec(w.pi) for w in w_list], axis=1),
    }


class _Prior:
    """The mutable ``u`` struct of the h-step loops, with Normal-Gamma ``a, b``.

    Attributes
    ----------
    mu, beta, a, b, nu, W, A, pi : numpy.ndarray
        Hyperparameters.
    """

    def __init__(self, stacked: dict) -> None:
        m, beta, a, b = dist.normgamma_h_step(
            stacked["mu"], stacked["beta"], stacked["a"], stacked["b"], 1
        )
        self.mu, self.beta, self.a, self.b = m, beta, a, b
        self.nu = 2 * a
        self.W = 0.5 / b
        self.A = dist.dirichlet_h_step(stacked["A"])
        self.pi = dist.dirichlet_h_step(stacked["pi"])

    def params(self) -> HmmParams:
        """Return the prior as :class:`HmmParams` (dropping ``a, b``).

        Returns
        -------
        HmmParams
        """
        return HmmParams(
            mu=np.array(self.mu),
            beta=np.array(self.beta),
            W=np.array(self.W),
            nu=np.array(self.nu),
            A=np.array(self.A),
            pi=np.array(self.pi),
        )


def _posteriors_from_stats(u: _Prior, E: dict) -> dict:
    """Posterior arrays implied by prior ``u`` and fixed statistics ``E``.

    Parameters
    ----------
    u : _Prior
        Prior.
    E : dict
        ``z, z1, x, V_x`` as ``(K, N)`` and ``zz`` as ``(K, K, N)``.

    Returns
    -------
    dict
        Stacked posterior arrays as :func:`_stack` returns them.
    """
    w_beta = E["z"] + u.beta[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        w_mu = (E["z"] * E["x"] + (u.beta * u.mu)[:, None]) / w_beta
        w_b = 0.5 * (
            2 * u.b[:, None]
            + E["z"] * E["V_x"]
            + (E["z"] * u.beta[:, None]) / w_beta * (E["x"] - u.mu[:, None]) ** 2
        )
    return {
        "pi": E["z1"] + u.pi[:, None],
        "A": E["zz"] + np.asarray(u.A)[:, :, None],
        "beta": w_beta,
        "mu": w_mu,
        "a": 0.5 * E["z"] + u.a[:, None],
        "b": w_b,
    }


def _unstack(stacked: dict) -> list[HmmParams]:
    """Split stacked posterior arrays back into one :class:`HmmParams` per trace.

    Parameters
    ----------
    stacked : dict
        As returned by :func:`_posteriors_from_stats`.

    Returns
    -------
    list of HmmParams
    """
    N = stacked["mu"].shape[1]
    return [
        HmmParams(
            mu=stacked["mu"][:, n].copy(),
            beta=stacked["beta"][:, n].copy(),
            W=0.5 / stacked["b"][:, n],
            nu=2 * stacked["a"][:, n],
            A=stacked["A"][:, :, n].copy(),
            pi=stacked["pi"][:, n].copy(),
        )
        for n in range(N)
    ]


def h_step(
    w_list: Sequence[HmmParams],
    u: HmmParams | None = None,
    expect: Sequence[Expect | None] | None = None,
    max_iter: int = 100,
    threshold: float = 1e-5,
    return_posteriors: bool = False,
):
    """Empirical-Bayes hyperparameter update (``h_step.m``).

    Without ``expect`` this is a single moment match of the prior to the
    posteriors. With it, the posteriors are re-derived from the fixed
    statistics under each new prior and the update repeated, until the change
    in ``KL(u || u_old)`` stalls.

    Parameters
    ----------
    w_list : sequence of HmmParams
        Posteriors of the analysed traces.
    u : HmmParams, optional
        Current prior (only its identity as ``u_old`` matters, as in the
        reference, where it is overwritten before first use).
    expect : sequence of Expect or None, optional
        Statistics of the same traces; ``None`` entries (an invalid fit) are
        left out, as MATLAB's ``cat`` drops empty structs.
    max_iter : int
        Iteration limit.
    threshold : float
        Convergence threshold.
    return_posteriors : bool
        Also return the updated per-trace posteriors.

    Returns
    -------
    HmmParams or tuple
        The new prior, and with ``return_posteriors`` the posteriors too.
    """
    stacked = _stack(w_list)
    E = None
    if expect is not None:
        items = [e for e in expect if e is not None and _vec(e.z).size]
        if items:
            K = _vec(items[0].z).size
            E = {
                "z": np.stack([_vec(e.z) for e in items], axis=1),
                "z1": np.stack([_vec(e.z1) for e in items], axis=1),
                "zz": np.stack(
                    [np.asarray(e.zz, dtype=float).reshape(K, K) for e in items], axis=2
                ),
                "x": np.stack([_vec(e.x) for e in items], axis=1),
            }
            E["V_x"] = np.stack([_vec(e.xx) for e in items], axis=1) - E["x"] ** 2

    u_old = u
    kl: list[float] = []
    it = 0
    while True:
        prior = _Prior(stacked)
        if it >= max_iter:
            break
        if it >= 1:
            kl.append(kl_div(prior, u_old))
        if it >= 2 and (kl[it - 2] - kl[it - 1]) / (1 - kl[it - 1]) < threshold:
            break
        if it == 0 and E is not None:
            pass
        elif E is None:
            break
        stacked = _posteriors_from_stats(prior, E)
        it += 1
        u_old = prior
    if return_posteriors:
        return prior.params(), _unstack(stacked)
    return prior.params()


def h_step_remap(
    u0: HmmParams,
    expect: Sequence[Expect | None],
    mapping=None,
    max_iter: int = 100,
    threshold: float = 1e-4,
):
    """Prior, posteriors and statistics after merging states (``h_step_remap.m``).

    Parameters
    ----------
    u0 : HmmParams
        Prior of the analysis.
    expect : sequence of Expect or None
        Statistics per trace; ``None`` entries are passed through.
    mapping : array_like, optional
        1-based target state for each state; identity by default.
    max_iter : int
        Iteration limit of the h-step loop.
    threshold : float
        Convergence threshold.

    Returns
    -------
    u : HmmParams
        Remapped, re-estimated prior.
    w : list of HmmParams or None
        Posteriors aligned with ``expect``.
    expect : list of Expect or None
        Remapped statistics aligned with ``expect``.
    """
    K0 = _vec(u0.mu).size
    mapping = (
        np.arange(1, K0 + 1)
        if mapping is None or len(mapping) == 0
        else np.asarray(mapping, dtype=int).reshape(-1)
    )
    M = int(mapping.max())
    u_mu = np.zeros(M)
    u_beta = np.zeros(M)
    u_a = np.zeros(M)
    u_b = np.zeros(M)
    u_pi = np.zeros(M)
    u_A = np.zeros((M, M))
    a0 = 0.5 * _vec(u0.nu)
    b0 = 0.5 / _vec(u0.W)
    mu0, beta0, pi0 = _vec(u0.mu), _vec(u0.beta), _vec(u0.pi)
    A0 = np.asarray(u0.A, dtype=float).reshape(K0, K0)
    msk = np.zeros(M, dtype=bool)
    groups = [np.flatnonzero(mapping == km) for km in range(1, M + 1)]
    for km, k in enumerate(groups):
        msk[km] = k.size > 0
        if k.size:
            u_mu[km] = np.sum(mu0[k] * beta0[k]) / np.sum(beta0[k])
            u_beta[km] = np.sum(beta0[k])
            u_a[km] = np.sum(a0[k])
            u_b[km] = np.sum(b0[k] * a0[k]) / np.sum(a0[k])
            u_pi[km] = np.sum(pi0[k])
            for lm, l_idx in enumerate(groups):
                if l_idx.size:
                    u_A[km, lm] = np.sum(A0[np.ix_(k, l_idx)])

    ns = [i for i, e in enumerate(expect) if e is not None and _vec(e.z).size]
    N = len(ns)
    E_z = np.zeros((M, N))
    E_z1 = np.zeros((M, N))
    E_x = np.zeros((M, N))
    E_xx = np.zeros((M, N))
    E_zz = np.zeros((M, M, N))
    for km, k in enumerate(groups):
        if not k.size:
            continue
        for j, n in enumerate(ns):
            e = expect[n]
            z = _vec(e.z)
            E_z[km, j] = np.sum(z[k])
            E_z1[km, j] = np.sum(_vec(e.z1)[k])
            with np.errstate(divide="ignore", invalid="ignore"):
                E_x[km, j] = np.nan_to_num(np.sum(_vec(e.x)[k] * z[k]) / np.sum(z[k]), nan=0.0)
                E_xx[km, j] = np.nan_to_num(np.sum(_vec(e.xx)[k] * z[k]) / np.sum(z[k]), nan=0.0)
            zz = np.asarray(e.zz, dtype=float).reshape(K0, K0)
            for lm, l_idx in enumerate(groups):
                if l_idx.size:
                    E_zz[km, lm, j] = np.sum(zz[np.ix_(k, l_idx)])
    E = {"z": E_z[msk], "z1": E_z1[msk], "x": E_x[msk], "zz": E_zz[np.ix_(msk, msk)]}
    E_xx = E_xx[msk]
    E["V_x"] = E_xx - E["x"] ** 2

    class _U:
        pass

    prior = _U()
    prior.mu, prior.beta, prior.a, prior.b = u_mu[msk], u_beta[msk], u_a[msk], u_b[msk]
    prior.nu, prior.W = 2 * prior.a, 0.5 / prior.b
    prior.A, prior.pi = u_A, u_pi

    u_old = prior
    kl: list[float] = []
    it = 1
    while True:
        stacked = _posteriors_from_stats(prior, E)
        prior = _Prior(stacked)
        if it >= max_iter:
            break
        kl.append(kl_div(prior, u_old))
        if it >= 2 and (kl[it - 2] - kl[it - 1]) / (1 - kl[it - 1]) < threshold:
            break
        if len(expect) == 0:
            break
        it += 1
        u_old = prior
    stacked = _posteriors_from_stats(prior, E)
    posteriors = _unstack(stacked)
    w_out: list = [None] * len(expect)
    e_out: list = [None] * len(expect)
    Kr = int(msk.sum())
    for j, n in enumerate(ns):
        w_out[n] = posteriors[j]
        e_out[n] = Expect(
            z=E["z"][:, j].copy(),
            z1=E["z1"][:, j].copy(),
            zz=E["zz"][:, :, j].reshape(Kr, Kr).copy(),
            x=E["x"][:, j].copy(),
            xx=E_xx[:, j].copy(),
        )
    return prior.params(), w_out, e_out


# --------------------------------------------------------------------------- #
# Analysis summary
# --------------------------------------------------------------------------- #
def _length_stats(values) -> dict:
    """``Mean, Std, Median, Min, Max, Total`` of a vector, MATLAB-style.

    Parameters
    ----------
    values : array_like
        Values.

    Returns
    -------
    dict
    """
    v = _vec(values)
    return {
        "Mean": float(np.mean(v)) if v.size else float("nan"),
        "Std": ml.std(v),
        "Median": ml.median(v),
        "Min": float(np.min(v)) if v.size else float("nan"),
        "Max": float(np.max(v)) if v.size else float("nan"),
        "Total": float(np.sum(v)),
    }


def report(
    signal: Sequence,
    prior: HmmParams,
    expect: Sequence[Expect | None],
    lowerbound=None,
    splits=None,
    labels=None,
    mapping=None,
) -> list[dict]:
    """Summary statistics of an analysis, per split of the series (``report.m``).

    The nested dicts keep the reference's field order, which is the row order
    of the exported CSV.

    Parameters
    ----------
    signal : sequence of array_like or None
        Analysed signal per series (``None``/empty for an excluded series).
    prior : HmmParams
        Prior of the analysis.
    expect : sequence of Expect or None
        Statistics per series.
    lowerbound : array_like, optional
        Lower bound per series.
    splits : sequence of sequence of int, optional
        0-based series indices per split; one split of all series by default.
    labels : sequence of str, optional
        Label per split.
    mapping : array_like, optional
        1-based state mapping passed to :func:`h_step_remap`.

    Returns
    -------
    list of dict
        One report per split.
    """
    signal = list(signal)
    if not splits:
        splits = [list(range(len(signal)))]
    reports = []
    for s, split in enumerate(splits):
        split = list(split)
        lengths = np.array([0 if signal[n] is None else _vec(signal[n]).size for n in split])
        ns = [n for n, t in zip(split, lengths) if t > 0]
        T = lengths[lengths > 0].astype(float)
        rep: dict = {"Series": {}}
        if labels:
            rep["Series"]["Label"] = labels[s]
        rep["Series"]["Number"] = float(T.size)
        rep["Series"]["Length"] = _length_stats(T)
        u, _w, e = h_step_remap(prior, [expect[n] for n in ns], mapping)
        e = [item for item in e if item is not None]
        K = _vec(u.mu).size
        if lowerbound is not None and len(lowerbound):
            L = _vec(lowerbound)[ns]
            label = labels[s] if labels else ""
            rep["Lower_Bound"] = {
                "Label": label,
                "Num_States": "%d" % K,
                "per_Series": _length_stats(L),
                "per_Observation": _length_stats(L / T),
            }
        stats: dict = {}
        if labels:
            stats["Label"] = [labels[s]] + [""] * (K - 1)
            stats["Num_States"] = ["%d" % K] + [""] * (K - 1)
        z = np.stack([item.z for item in e], axis=1) if e else np.zeros((K, 0))
        x = np.stack([item.x for item in e], axis=1) if e else np.zeros((K, 0))
        xx = np.stack([item.xx for item in e], axis=1) if e else np.zeros((K, 0))
        zz = np.stack([item.zz for item in e], axis=2) if e else np.zeros((K, K, 0))
        with np.errstate(divide="ignore", invalid="ignore"):
            obs_mean = np.sum(x * z, axis=1) / np.sum(z, axis=1)
            obs_std = (np.sum(xx * z, axis=1) / np.sum(z, axis=1) - obs_mean**2) ** 0.5
        stats["State"] = np.arange(1, K + 1, dtype=float)
        stats["Occupancy"] = {
            "Fraction": normalize(np.sum(z, axis=1))[0],
            "Total": np.sum(z, axis=1),
        }
        stats["Observation"] = {"Mean": obs_mean, "Std": obs_std}
        stats["Transitions"] = {
            "Mean": normalize(np.sum(zz, axis=2), axis=1)[0],
            "Total": np.sum(zz, axis=2),
        }
        rep["Statistics"] = stats

        pars: dict = {}
        if labels:
            pars["Label"] = [labels[s]] + [""] * (K - 1)
            pars["Num_States"] = ["%d" % K] + [""] * (K - 1)
        pars["State"] = np.arange(1, K + 1, dtype=float)
        a, b = 0.5 * _vec(u.nu), 0.5 / _vec(u.W)
        c_mean, p_mean = dist.normgamma_mean(u.mu, u.beta, a, b)
        with np.errstate(divide="ignore", invalid="ignore"):
            v_mu, v_l = dist.normgamma_var(u.mu, u.beta, a, b)
            c_std, p_std = np.sqrt(v_mu), np.sqrt(v_l)
        _, p_mode = dist.normgamma_mode(u.mu, u.beta, a, b)
        pars["Center"] = {"Mean": c_mean, "Std": c_std}
        pars["Precision"] = {"Mean": p_mean, "Std": p_std, "Mode": p_mode}
        pars["Dwell_Time"] = {"Mode": dist.dirichlet_tau(u.A)}
        pars["Transition_Matrix"] = {
            "Mean": dist.dirichlet_mean(u.A),
            "Std": dist.dirichlet_var(u.A) ** 0.5,
        }
        rep["Parameters"] = pars
        reports.append(rep)
    return reports


# --------------------------------------------------------------------------- #
# Photobleaching
# --------------------------------------------------------------------------- #
def photobleach_index(signal, sigma: float = 5.0, threshold: float = 4.0):
    """Frame where a donor or acceptor signal bleaches (``photobleach_index.m``).

    Parameters
    ----------
    signal : array_like
        One intensity channel, ``(T,)``.
    sigma : float
        Width of the Gaussian that smooths the detection signal.
    threshold : float
        Minimum peak of the detection signal.

    Returns
    -------
    index : int
        1-based bleaching frame, or ``T`` when no peak exceeds ``threshold``.
    d : numpy.ndarray
        Detection signal, ``(T + 2 W,)`` with ``W = round(3 sigma)``.
    """
    s = _vec(signal)
    T = s.size
    n_f = np.arange(1, T + 1, dtype=float)
    n_b = np.arange(T, 0, -1, dtype=float)
    mf = np.cumsum(s) / n_f
    var_f = np.cumsum(s**2) / n_f - mf**2
    mb = np.cumsum(s[::-1])[::-1] / n_b
    var_b = np.cumsum((s**2)[::-1])[::-1] / n_b - mb**2
    sf = np.lib.scimath.sqrt(var_f)
    sb = np.lib.scimath.sqrt(var_b)
    W = int(math.floor(3 * sigma + 0.5))
    k = np.arange(-W, W + 1, dtype=float)
    S = np.exp(-(k**2) / sigma**2)
    S = S / S.sum()
    sf = np.array(sf)
    sb = np.array(sb)
    if T > 1:
        sf[0] = sf[1]
        sb[-1] = sb[-2]
    with np.errstate(divide="ignore", invalid="ignore"):
        df = (mf - s) / sf
        db = (s - mb) / sb
    d = np.convolve(df + db, S)
    if np.iscomplexobj(d):
        score = np.abs(d)
        idx = int(np.nanargmax(score))
        dmax = float(np.real(d[idx]))
    else:
        idx = int(np.nanargmax(d)) if not np.all(np.isnan(d)) else 0
        dmax = float(d[idx])
    if dmax > threshold:
        return idx + 1 - W, d
    return T, d
