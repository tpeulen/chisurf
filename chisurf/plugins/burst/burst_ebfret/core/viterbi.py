"""Viterbi decoding of the most-probable state path for a fitted Gaussian HMM."""

from __future__ import annotations

import numpy as np
from scipy.special import digamma

from .vbem import GaussHmmPrior

__all__ = ["viterbi"]


def viterbi(x: np.ndarray, post: GaussHmmPrior) -> tuple[np.ndarray, np.ndarray]:
    """Decode the maximum-a-posteriori state sequence of one trace.

    Uses the variational expected log-parameters of ``post`` (the same
    potentials as the E-step), consistent with ebFRET's ``viterbi_vb``.

    Parameters
    ----------
    x : numpy.ndarray
        FRET-efficiency time series, shape ``(T,)``.
    post : GaussHmmPrior
        Variational posterior for this trace.

    Returns
    -------
    states : numpy.ndarray
        Integer state index per time point, shape ``(T,)``.
    state_means : numpy.ndarray
        Posterior emission mean of the decoded state per time point, shape
        ``(T,)``.
    """
    x = np.asarray(x, dtype=float).ravel()
    n_obs = x.shape[0]
    n_states = post.n_states

    ln_pi = digamma(post.pi) - digamma(post.pi.sum())
    ln_A = digamma(post.A) - digamma(post.A.sum(axis=1, keepdims=True))
    e_lambda = post.a / post.b
    e_ln_lambda = digamma(post.a) - np.log(post.b)
    d2 = (x[:, None] - post.m[None, :]) ** 2
    ln_lik = (
        0.5 * e_ln_lambda[None, :]
        - 0.5 * np.log(2.0 * np.pi)
        - 0.5 * (1.0 / post.beta[None, :] + e_lambda[None, :] * d2)
    )

    delta = np.zeros((n_obs, n_states))
    psi = np.zeros((n_obs, n_states), dtype=int)
    delta[0] = ln_pi + ln_lik[0]
    for t in range(1, n_obs):
        scores = delta[t - 1][:, None] + ln_A  # (K_prev, K_next)
        psi[t] = np.argmax(scores, axis=0)
        delta[t] = scores[psi[t], np.arange(n_states)] + ln_lik[t]

    states = np.zeros(n_obs, dtype=int)
    states[-1] = int(np.argmax(delta[-1]))
    for t in range(n_obs - 2, -1, -1):
        states[t] = psi[t + 1, states[t + 1]]
    return states, post.m[states]
