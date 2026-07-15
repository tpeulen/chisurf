"""Variational-Bayes inference for a single-trace Gaussian hidden Markov model.

This is a Qt-free, NumPy-only port of the per-trace VBEM core of ebFRET
(van de Meent et al.; a re-implementation of vbFRET, Bronson et al. 2009). It
fits a univariate Gaussian-emission HMM to a one-dimensional FRET-efficiency
time series by variational Bayes, using conjugate Dirichlet priors on the
initial-state and transition distributions and a Normal-Gamma prior on the
per-state emission (mean, precision).

Emission hyper-parameters follow ebFRET's ``(m, beta, a, b)`` convention: the
precision ``lambda`` of state ``k`` is ``Gamma(a_k, b_k)`` (shape-rate, so
``E[lambda] = a / b``) and the mean given the precision is
``Normal(m_k, (beta_k * lambda_k) ** -1)``. This maps to the more common
Normal-Wishart form via ``nu = 2 a`` and ``W = 1 / (2 b)``.

The module deliberately depends only on :mod:`numpy` and :mod:`scipy.special`
so it can run head-less, in tests, or from the CLI, mirroring the sibling
``burst_h2mm`` engine.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import digamma, gammaln

__all__ = ["GaussHmmPrior", "GaussHmmPosterior", "VbemResult", "vbem_single"]

_EPS = 1e-12


@dataclass
class GaussHmmPrior:
    """Shared Normal-Gamma / Dirichlet prior for a ``K``-state Gaussian HMM.

    Parameters
    ----------
    pi : numpy.ndarray
        Dirichlet parameters of the initial-state distribution, shape ``(K,)``.
    A : numpy.ndarray
        Dirichlet parameters of the transition matrix, shape ``(K, K)``; row
        ``i`` parameterises the distribution over the next state given state
        ``i``.
    m, beta, a, b : numpy.ndarray
        Normal-Gamma emission hyper-parameters, each shape ``(K,)``.
    """

    pi: np.ndarray
    A: np.ndarray
    m: np.ndarray
    beta: np.ndarray
    a: np.ndarray
    b: np.ndarray

    @property
    def n_states(self) -> int:
        """Number of hidden states ``K``."""
        return int(self.m.shape[0])

    def copy(self) -> GaussHmmPrior:
        """Return a deep copy with freshly allocated arrays."""
        return GaussHmmPrior(
            pi=np.array(self.pi, dtype=float),
            A=np.array(self.A, dtype=float),
            m=np.array(self.m, dtype=float),
            beta=np.array(self.beta, dtype=float),
            a=np.array(self.a, dtype=float),
            b=np.array(self.b, dtype=float),
        )


# The posterior of a single trace has exactly the same shape as the prior; a
# thin alias keeps call sites self-documenting.
GaussHmmPosterior = GaussHmmPrior


@dataclass
class VbemResult:
    """Result of fitting one trace with :func:`vbem_single`.

    Attributes
    ----------
    posterior : GaussHmmPrior
        Converged variational posterior over the HMM parameters.
    gamma : numpy.ndarray
        State responsibilities ``q(z_t = k)``, shape ``(T, K)``.
    xi_sum : numpy.ndarray
        Summed pairwise marginals ``sum_t q(z_{t-1}=i, z_t=j)``, shape
        ``(K, K)``.
    lower_bound : float
        Final variational lower bound (ELBO).
    n_iter : int
        Number of VBEM iterations performed.
    converged : bool
        Whether the ELBO change fell below ``threshold`` before ``max_iter``.
    """

    posterior: GaussHmmPrior
    gamma: np.ndarray
    xi_sum: np.ndarray
    lower_bound: float
    n_iter: int
    converged: bool


def _emission_expectations(post: GaussHmmPrior, x: np.ndarray) -> np.ndarray:
    """Compute the expected emission log-likelihood ``E_q[ln p(x_t | z_t = k)]``.

    Parameters
    ----------
    post : GaussHmmPrior
        Current variational posterior.
    x : numpy.ndarray
        Observation vector, shape ``(T,)``.

    Returns
    -------
    numpy.ndarray
        Array of shape ``(T, K)``.
    """
    e_lambda = post.a / post.b  # E[lambda], (K,)
    e_ln_lambda = digamma(post.a) - np.log(post.b)  # E[ln lambda], (K,)
    d2 = (x[:, None] - post.m[None, :]) ** 2  # (T, K)
    return (
        0.5 * e_ln_lambda[None, :]
        - 0.5 * np.log(2.0 * np.pi)
        - 0.5 * (1.0 / post.beta[None, :] + e_lambda[None, :] * d2)
    )


def _forward_backward(
    ln_pi: np.ndarray, ln_A: np.ndarray, ln_lik: np.ndarray
) -> tuple[np.ndarray, np.ndarray, float]:
    """Scaled forward-backward on expected log-potentials.

    Uses Rabiner's linear-domain scaled recursion (rather than a per-step
    :func:`logsumexp`) for speed: the expected initial/transition potentials
    are exponentiated once (they are sub-stochastic, so exponentiation is
    safe), and each time step's emissions are stabilised by subtracting their
    per-step maximum, whose sum is added back into the log normaliser.

    Parameters
    ----------
    ln_pi : numpy.ndarray
        ``E[ln pi]``, shape ``(K,)``.
    ln_A : numpy.ndarray
        ``E[ln A]``, shape ``(K, K)``.
    ln_lik : numpy.ndarray
        Expected emission log-likelihoods, shape ``(T, K)``.

    Returns
    -------
    gamma : numpy.ndarray
        State responsibilities, shape ``(T, K)``.
    xi_sum : numpy.ndarray
        Summed pairwise marginals, shape ``(K, K)``.
    ln_z : float
        Log normaliser of the expected-potential HMM (``ln Z_tilde``).
    """
    n_obs, n_states = ln_lik.shape
    pi = np.exp(ln_pi)
    trans = np.exp(ln_A)
    row_max = ln_lik.max(axis=1)
    emit = np.exp(ln_lik - row_max[:, None])  # (T, K), stabilised

    alpha = np.zeros((n_obs, n_states))
    scale = np.zeros(n_obs)  # linear per-step normalisers
    a0 = pi * emit[0]
    scale[0] = a0.sum()
    alpha[0] = a0 / scale[0]
    for t in range(1, n_obs):
        at = (alpha[t - 1] @ trans) * emit[t]
        scale[t] = at.sum()
        alpha[t] = at / scale[t]
    ln_z = float(np.log(scale).sum() + row_max.sum())

    beta = np.zeros((n_obs, n_states))
    beta[-1] = 1.0
    for t in range(n_obs - 2, -1, -1):
        beta[t] = (trans @ (emit[t + 1] * beta[t + 1])) / scale[t + 1]

    gamma = alpha * beta
    gamma /= gamma.sum(axis=1, keepdims=True)

    xi_sum = np.zeros((n_states, n_states))
    for t in range(1, n_obs):
        xi = alpha[t - 1][:, None] * trans * (emit[t] * beta[t])[None, :] / scale[t]
        xi_sum += xi
    return gamma, xi_sum, ln_z


def _m_step(
    prior: GaussHmmPrior, gamma: np.ndarray, xi_sum: np.ndarray, x: np.ndarray
) -> GaussHmmPrior:
    """Variational M-step: conjugate posterior update from responsibilities.

    Parameters
    ----------
    prior : GaussHmmPrior
        Shared prior hyper-parameters.
    gamma : numpy.ndarray
        Responsibilities, shape ``(T, K)``.
    xi_sum : numpy.ndarray
        Summed pairwise marginals, shape ``(K, K)``.
    x : numpy.ndarray
        Observations, shape ``(T,)``.

    Returns
    -------
    GaussHmmPrior
        Updated variational posterior.
    """
    n_k = gamma.sum(axis=0)  # (K,)
    safe_nk = np.maximum(n_k, _EPS)
    xbar = (gamma * x[:, None]).sum(axis=0) / safe_nk
    dev2 = (gamma * (x[:, None] - xbar[None, :]) ** 2).sum(axis=0) / safe_nk

    pi = prior.pi + gamma[0]
    a_trans = prior.A + xi_sum
    beta = prior.beta + n_k
    m = (prior.beta * prior.m + n_k * xbar) / beta
    a = prior.a + 0.5 * n_k
    b = prior.b + 0.5 * (
        n_k * dev2 + (prior.beta * n_k / (prior.beta + n_k)) * (xbar - prior.m) ** 2
    )
    return GaussHmmPrior(pi=pi, A=a_trans, m=m, beta=beta, a=a, b=b)


def _kl_dirichlet(w: np.ndarray, u: np.ndarray) -> float:
    """KL divergence ``KL(Dir(w) || Dir(u))`` for one Dirichlet.

    Parameters
    ----------
    w, u : numpy.ndarray
        Posterior and prior Dirichlet parameters, shape ``(K,)``.

    Returns
    -------
    float
    """
    w_sum = w.sum()
    u_sum = u.sum()
    return float(
        gammaln(w_sum)
        - gammaln(w).sum()
        - gammaln(u_sum)
        + gammaln(u).sum()
        + ((w - u) * (digamma(w) - digamma(w_sum))).sum()
    )


def _kl_normal_gamma(post: GaussHmmPrior, prior: GaussHmmPrior) -> float:
    """KL divergence between the Normal-Gamma emission factors, summed over states.

    Parameters
    ----------
    post, prior : GaussHmmPrior
        Posterior and prior emission hyper-parameters.

    Returns
    -------
    float
    """
    aq, bq, mq, betaq = post.a, post.b, post.m, post.beta
    ap, bp, mp, betap = prior.a, prior.b, prior.m, prior.beta

    kl_gamma = (
        (aq - ap) * digamma(aq)
        - gammaln(aq)
        + gammaln(ap)
        + ap * (np.log(bq) - np.log(bp))
        + aq * (bp - bq) / bq
    )
    e_lambda = aq / bq
    kl_normal = (
        0.5 * np.log(betaq / betap)
        - 0.5
        + 0.5 * betap / betaq
        + 0.5 * betap * (mq - mp) ** 2 * e_lambda
    )
    return float((kl_gamma + kl_normal).sum())


def _lower_bound(post: GaussHmmPrior, prior: GaussHmmPrior, ln_z: float) -> float:
    """Variational lower bound ``ln Z_tilde - KL(q(theta) || p(theta))``.

    Parameters
    ----------
    post, prior : GaussHmmPrior
        Variational posterior and shared prior.
    ln_z : float
        Log normaliser returned by the forward-backward pass.

    Returns
    -------
    float
    """
    kl = _kl_dirichlet(post.pi, prior.pi)
    for k in range(prior.n_states):
        kl += _kl_dirichlet(post.A[k], prior.A[k])
    kl += _kl_normal_gamma(post, prior)
    return ln_z - kl


def vbem_single(
    x: np.ndarray,
    prior: GaussHmmPrior,
    *,
    max_iter: int = 100,
    threshold: float = 1e-5,
) -> VbemResult:
    """Fit one FRET trace with variational-Bayes EM.

    Parameters
    ----------
    x : numpy.ndarray
        One-dimensional FRET-efficiency time series, shape ``(T,)``.
    prior : GaussHmmPrior
        Shared prior. The variational posterior is initialised from a copy of
        the prior, so the per-state prior means ``prior.m`` provide the
        symmetry breaking between states.
    max_iter : int, optional
        Maximum number of VBEM iterations.
    threshold : float, optional
        Relative ELBO-change convergence threshold.

    Returns
    -------
    VbemResult
        Converged posterior, responsibilities, summed pairwise marginals, ELBO
        and convergence diagnostics.
    """
    x = np.asarray(x, dtype=float).ravel()
    post = prior.copy()
    gamma = np.zeros((x.shape[0], prior.n_states))
    xi_sum = np.zeros((prior.n_states, prior.n_states))
    last_lb = -np.inf
    lb = -np.inf
    converged = False
    n_iter = 0
    for n_iter in range(1, max_iter + 1):
        ln_pi = digamma(post.pi) - digamma(post.pi.sum())
        ln_A = digamma(post.A) - digamma(post.A.sum(axis=1, keepdims=True))
        ln_lik = _emission_expectations(post, x)
        gamma, xi_sum, ln_z = _forward_backward(ln_pi, ln_A, ln_lik)
        post = _m_step(prior, gamma, xi_sum, x)
        lb = _lower_bound(post, prior, ln_z)
        if np.isfinite(last_lb) and abs(lb - last_lb) < threshold * max(1.0, abs(last_lb)):
            converged = True
            break
        last_lb = lb
    return VbemResult(
        posterior=post,
        gamma=gamma,
        xi_sum=xi_sum,
        lower_bound=lb,
        n_iter=n_iter,
        converged=converged,
    )
