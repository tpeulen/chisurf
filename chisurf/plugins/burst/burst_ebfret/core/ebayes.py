"""Empirical-Bayes hierarchical fitting of a Gaussian HMM over many FRET traces.

This is the outer loop of the ebFRET method: run per-trace variational Bayes
(:func:`~chisurf.plugins.burst.burst_ebfret.core.vbem.vbem_single`) against a
shared prior, then re-estimate that prior from all trace posteriors with a
conjugate hyper-parameter (h-step) update, and iterate until the summed
evidence converges. Tying every trace to one prior ("empirical Bayes") is what
separates ebFRET from a plain per-trace HMM fit and makes state recovery robust
across a heterogeneous population.

The Dirichlet and Normal-Gamma h-step updates are ported from ebFRET's
``+dist/+dirichlet/h_step.m`` and ``+dist/+normgamma/h_step.m``. Only the
single-prior (non-mixture) ``D = 1`` path is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import digamma, polygamma

from .vbem import GaussHmmPrior, VbemResult, vbem_single

__all__ = ["EbayesResult", "init_prior", "dirichlet_hstep", "normal_gamma_hstep", "ebayes"]

_EPS = 1e-12


@dataclass
class EbayesResult:
    """Result of an empirical-Bayes fit over a set of traces.

    Attributes
    ----------
    prior : GaussHmmPrior
        Converged shared prior (the empirical-Bayes hyper-parameters).
    traces : list of VbemResult
        Per-trace variational fits under the final prior.
    evidence : float
        Summed lower bound over all traces at convergence.
    evidence_history : list of float
        Summed lower bound after each empirical-Bayes iteration.
    n_iter : int
        Number of empirical-Bayes iterations performed.
    converged : bool
        Whether the summed evidence converged before ``max_iter``.

    Notes
    -----
    ``state_means`` returns the converged prior emission means sorted ascending,
    which is the natural summary for comparing recovered FRET states.
    """

    prior: GaussHmmPrior
    traces: list[VbemResult]
    evidence: float
    evidence_history: list[float]
    n_iter: int
    converged: bool

    @property
    def state_means(self) -> np.ndarray:
        """Converged prior emission means (FRET), sorted ascending."""
        return np.sort(self.prior.m)


def init_prior(
    traces: list[np.ndarray],
    n_states: int,
    *,
    self_transition: float = 10.0,
    emission_conf: float = 0.25,
    precision_conf: float = 2.5,
    seed: int | None = None,
) -> GaussHmmPrior:
    """Construct a weakly-informative shared prior from pooled trace statistics.

    Parameters
    ----------
    traces : list of numpy.ndarray
        FRET-efficiency traces.
    n_states : int
        Number of hidden states ``K``.
    self_transition : float, optional
        Extra Dirichlet count added to the transition-matrix diagonal to favour
        state persistence.
    emission_conf : float, optional
        Prior confidence ``beta`` on the emission means (in pseudo-counts).
    precision_conf : float, optional
        Prior Gamma shape ``a`` on the emission precisions.
    seed : int, optional
        Unused placeholder for API symmetry; initialisation is deterministic
        (state means placed at pooled quantiles).

    Returns
    -------
    GaussHmmPrior
    """
    pooled = np.concatenate([np.asarray(t, dtype=float).ravel() for t in traces])
    quantiles = np.linspace(0.0, 1.0, n_states + 2)[1:-1]
    means = np.quantile(pooled, quantiles)
    var = max(float(np.var(pooled)), 1e-4)
    e_lambda = 1.0 / var

    pi = np.ones(n_states)
    a_trans = np.ones((n_states, n_states)) + self_transition * np.eye(n_states)
    m = np.array(means, dtype=float)
    beta = np.full(n_states, emission_conf)
    a = np.full(n_states, precision_conf)
    b = a / e_lambda  # so that E[lambda] = a / b = 1 / var
    return GaussHmmPrior(pi=pi, A=a_trans, m=m, beta=beta, a=a, b=b)


def dirichlet_hstep(
    w: np.ndarray,
    *,
    alpha0: np.ndarray | None = None,
    max_iter: int = 1000,
    threshold: float = 1e-6,
) -> np.ndarray:
    """Empirical-Bayes update of a Dirichlet prior (Newton).

    Solves ``psi(alpha_k) - psi(sum alpha) = mean_n E[ln theta_k]`` for the
    shared parameters ``alpha`` given per-trace posterior parameters ``w``.

    Parameters
    ----------
    w : numpy.ndarray
        Posterior Dirichlet parameters, shape ``(N, K)`` for ``N`` traces.
    alpha0 : numpy.ndarray, optional
        Initial guess, shape ``(K,)``. Defaults to ones.
    max_iter : int, optional
        Maximum Newton iterations.
    threshold : float, optional
        Relative-step convergence threshold.

    Returns
    -------
    numpy.ndarray
        Estimated Dirichlet parameters, shape ``(K,)``.
    """
    w = np.asarray(w, dtype=float) + _EPS
    n_states = w.shape[1]
    e_log_q = np.mean(digamma(w) - digamma(w.sum(axis=1, keepdims=True)), axis=0)

    alpha = np.ones(n_states) if alpha0 is None else np.array(alpha0, dtype=float)
    for _ in range(max_iter):
        alpha_sum = alpha.sum()
        grad = digamma(alpha_sum) - digamma(alpha) + e_log_q
        z = polygamma(1, alpha_sum)  # trigamma of the total
        q = -polygamma(1, alpha)  # -trigamma of each component
        b = np.sum(grad / q) / (1.0 / z + np.sum(1.0 / q))
        dalpha = (grad - b) / q
        # Keep alpha positive: shrink the step if it would drive a component
        # below 1e-3 of its current value.
        pos = dalpha > 0
        if np.any(pos):
            step = np.min(np.minimum((1.0 - 1e-3) * alpha[pos] / dalpha[pos], 1.0))
        else:
            step = 1.0
        if np.max(np.abs(dalpha) / (alpha + _EPS)) < threshold:
            break
        alpha = alpha - step * dalpha
    return alpha


def normal_gamma_hstep(
    post: GaussHmmPrior,
    posteriors: list[GaussHmmPrior],
    *,
    a0: float = 2.0,
    max_iter: int = 1000,
    threshold: float = 1e-6,
    beta_floor: float = 1e-3,
    a_floor: float = 1.0 + 1e-3,
) -> GaussHmmPrior:
    """Empirical-Bayes update of the Normal-Gamma emission prior.

    Ported from ebFRET ``+dist/+normgamma/h_step.m``: match the shared prior to
    the population-averaged posterior moments of the emission mean and
    precision, solving ``psi(a) - log(a) = E[log lambda] - log E[lambda]`` by
    Newton iteration for the precision shape.

    Parameters
    ----------
    post : GaussHmmPrior
        Prior whose non-emission fields (``pi``, ``A``) are carried through
        unchanged; only the emission fields are re-estimated here.
    posteriors : list of GaussHmmPrior
        Per-trace variational posteriors.
    a0 : float, optional
        Initial precision shape for the Newton solver.
    max_iter, threshold : int, float, optional
        Newton solver controls.
    beta_floor, a_floor : float, optional
        Lower constraints on ``beta`` and ``a`` matching ebFRET.

    Returns
    -------
    GaussHmmPrior
        A copy of ``post`` with updated ``m``, ``beta``, ``a``, ``b``.
    """
    m = np.stack([p.m for p in posteriors], axis=1)  # (K, N)
    beta = np.stack([p.beta for p in posteriors], axis=1)
    a = np.stack([p.a for p in posteriors], axis=1)
    b = np.stack([p.b for p in posteriors], axis=1)

    e_lambda = np.mean(a / b, axis=1)  # (K,)
    e_ml = np.mean(m * a / b, axis=1)
    e_m2l = np.mean(1.0 / beta + m**2 * a / b, axis=1)
    e_log_lambda = np.mean(digamma(a) - np.log(b), axis=1)

    target = e_log_lambda - np.log(e_lambda)
    a_new = np.full(post.n_states, a0, dtype=float)
    for _ in range(max_iter):
        grad = digamma(a_new) - np.log(a_new) - target
        hess = polygamma(1, a_new) - 1.0 / a_new
        da = grad / hess
        a_new = np.maximum(a_new - da, 1.0 + 1e-3 * (a_new - 1.0))
        if np.all(np.abs(da) / a_new < threshold):
            break

    u_m = e_ml / e_lambda
    u_beta = 1.0 / (e_m2l - e_ml**2 / e_lambda)
    u_b = a_new / e_lambda

    u_beta = np.maximum(u_beta, beta_floor)
    u_a = np.maximum(a_new, a_floor)

    out = post.copy()
    out.m = u_m
    out.beta = u_beta
    out.a = u_a
    out.b = u_b
    return out


def ebayes(
    traces: list[np.ndarray],
    n_states: int,
    *,
    prior: GaussHmmPrior | None = None,
    max_iter: int = 20,
    threshold: float = 1e-4,
    vbem_max_iter: int = 100,
    vbem_threshold: float = 1e-5,
    seed: int | None = None,
) -> EbayesResult:
    """Fit a Gaussian HMM over many FRET traces by empirical Bayes.

    Parameters
    ----------
    traces : list of numpy.ndarray
        FRET-efficiency traces (variable length allowed).
    n_states : int
        Number of hidden states ``K``.
    prior : GaussHmmPrior, optional
        Initial shared prior. Defaults to :func:`init_prior`.
    max_iter : int, optional
        Maximum empirical-Bayes iterations.
    threshold : float, optional
        Relative summed-evidence convergence threshold.
    vbem_max_iter, vbem_threshold : int, float, optional
        Per-trace VBEM controls.
    seed : int, optional
        Seed forwarded to :func:`init_prior` (deterministic init).

    Returns
    -------
    EbayesResult
    """
    if prior is None:
        prior = init_prior(traces, n_states, seed=seed)
    traces = [np.asarray(t, dtype=float).ravel() for t in traces]

    evidence_history: list[float] = []
    results: list[VbemResult] = []
    last_evidence = -np.inf
    converged = False
    n_iter = 0
    for n_iter in range(1, max_iter + 1):
        results = [
            vbem_single(t, prior, max_iter=vbem_max_iter, threshold=vbem_threshold) for t in traces
        ]
        evidence = float(sum(r.lower_bound for r in results))
        evidence_history.append(evidence)

        posteriors = [r.posterior for r in results]
        pi = dirichlet_hstep(np.stack([p.pi for p in posteriors], axis=0))
        a_trans = np.stack(
            [
                dirichlet_hstep(np.stack([p.A[k] for p in posteriors], axis=0))
                for k in range(n_states)
            ],
            axis=0,
        )
        updated = normal_gamma_hstep(prior, posteriors)
        updated.pi = pi
        updated.A = a_trans
        prior = updated

        if np.isfinite(last_evidence) and abs(evidence - last_evidence) < threshold * max(
            1.0, abs(last_evidence)
        ):
            converged = True
            break
        last_evidence = evidence

    return EbayesResult(
        prior=prior,
        traces=results,
        evidence=evidence_history[-1] if evidence_history else float("nan"),
        evidence_history=evidence_history,
        n_iter=n_iter,
        converged=converged,
    )
