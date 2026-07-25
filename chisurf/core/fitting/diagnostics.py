r"""Convergence diagnostics for MCMC chains.

A sampler that returns a chain and says nothing about it is not much use: an
under-converged run and a converged one look identical in the output. This
module supplies the standard evidence — the split :math:`\hat{R}`, the effective
sample size, the integrated autocorrelation time, the Monte-Carlo standard error
and a burn-in suggestion — so a run can report whether it is worth believing.

Chains are shaped ``(n_chains, n_draws, n_parameters)``; a single chain may be
passed as ``(n_draws, n_parameters)``. Everything here is plain numpy.

Notes
-----
The ESS follows the standard multi-chain estimator: the autocorrelation is
combined across chains through the pooled variance, and the sum is truncated by
Geyer's initial positive (and monotone) sequence rather than at a fixed lag.
Correctness is pinned in the test suite against an AR(1) process, whose
autocorrelation time :math:`(1+\varphi)/(1-\varphi)` is known in closed form.

**Ensemble samplers.** The walkers of an affine-invariant ensemble sampler are
*not* independent chains -- they interact by construction -- so an
:math:`\hat{R}` computed across walkers is optimistic. A large value is still
conclusive evidence of failure; a small one is not evidence of success. Compute
the decisive :math:`\hat{R}` across genuinely independent *runs* instead, which
is what :func:`chisurf.core.fitting.fit.sample_fit` does with its ``n_runs``
chains.
"""
from __future__ import annotations

import math

import numpy as np

from chisurf import typing

__all__ = [
    "autocovariance",
    "effective_sample_size",
    "autocorrelation_time",
    "split_rhat",
    "mcse",
    "suggest_burn_in",
    "summarize",
    "convergence_warnings",
    "as_chains",
    "RHAT_THRESHOLD",
    "ESS_THRESHOLD",
]

#: Split-:math:`\hat{R}` above which a chain is reported as not converged. The
#: conventional 1.1 is now widely considered too permissive; 1.01 is the modern
#: recommendation and is what the warnings key off.
RHAT_THRESHOLD = 1.01

#: Effective sample size below which posterior quantiles are too noisy to quote.
#: 400 is the usual rule of thumb (100 per chain over four chains).
ESS_THRESHOLD = 400.0


def as_chains(samples: np.ndarray) -> np.ndarray:
    """Coerce a sample array to the canonical ``(chains, draws, parameters)`` shape.

    Parameters
    ----------
    samples : numpy.ndarray
        ``(n_draws,)``, ``(n_draws, n_parameters)`` or
        ``(n_chains, n_draws, n_parameters)``.

    Returns
    -------
    numpy.ndarray
        A 3-D array. A 1-D input becomes one chain of one parameter, a 2-D input
        one chain of several parameters.

    Raises
    ------
    ValueError
        If ``samples`` has more than three dimensions.
    """
    a = np.asarray(samples, dtype=np.float64)
    if a.ndim == 1:
        return a[np.newaxis, :, np.newaxis]
    if a.ndim == 2:
        return a[np.newaxis, :, :]
    if a.ndim == 3:
        return a
    raise ValueError(f"expected at most 3 dimensions, got {a.ndim}")


def autocovariance(x: np.ndarray) -> np.ndarray:
    """Return the biased autocovariance of a 1-D series at lags ``0 … n-1``.

    Computed through the FFT, so the cost is ``O(n log n)`` rather than the
    ``O(n²)`` of the direct sum -- which matters because this is evaluated once
    per parameter per chain on chains of many thousands of draws.

    Parameters
    ----------
    x : numpy.ndarray
        1-D sample series.

    Returns
    -------
    numpy.ndarray
        Autocovariance at each lag, of the same length as ``x``.
    """
    x = np.asarray(x, dtype=np.float64)
    n = x.size
    if n == 0:
        return np.empty(0, dtype=np.float64)
    centred = x - x.mean()
    # Zero-pad to at least 2n so the circular correlation of the FFT equals the
    # linear one, and to a power of two so the transform is cheap.
    nfft = 1 << int(max(1, 2 * n - 1)).bit_length()
    f = np.fft.rfft(centred, nfft)
    acov = np.fft.irfft(f * np.conjugate(f), nfft)[:n]
    return acov / n


def _pooled_variance(
        chains: np.ndarray
) -> typing.Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(within, var_plus, acov)`` for one parameter across chains.

    ``within`` is the mean within-chain variance ``W``, ``var_plus`` the
    Gelman–Rubin pooled variance estimate that overestimates the target variance
    for a finite chain, and ``acov`` the chain-averaged autocovariance.
    """
    m, n = chains.shape
    acov = np.array([autocovariance(c) for c in chains], dtype=np.float64)
    # acov[:, 0] is the biased variance; rescale to the unbiased one.
    chain_var = acov[:, 0] * n / max(1, n - 1)
    within = float(chain_var.mean())
    if m > 1:
        between = n * float(np.var(chains.mean(axis=1), ddof=1))
        var_plus = (n - 1) / n * within + between / n
    else:
        var_plus = within
    return within, float(var_plus), acov.mean(axis=0)


def _ess_1d(chains: np.ndarray) -> float:
    """Effective sample size of one parameter, given ``(n_chains, n_draws)``."""
    m, n = chains.shape
    total = float(m * n)
    if n < 4:
        return total

    within, var_plus, acov = _pooled_variance(chains)
    if not (var_plus > 0.0) or not (within > 0.0):
        # A constant parameter carries no information; calling that "n samples"
        # would be misleading, but so would zero. Report the raw draw count.
        return total

    # Combine the chains' autocorrelation through the pooled variance: with one
    # chain this reduces to the ordinary rho_t = acov_t / var.
    rho = 1.0 - (within - acov) / var_plus
    rho[0] = 1.0

    # Geyer's initial positive sequence: sum the *paired* autocorrelations,
    # which are theoretically positive and decreasing for a reversible chain,
    # and stop at the first pair that is not. Truncating at a fixed lag instead
    # either discards signal or accumulates noise.
    tau = -1.0
    previous = np.inf
    t = 0
    while t + 1 < n:
        pair = float(rho[t] + rho[t + 1])
        if t > 0 and pair < 0.0:
            break
        pair = min(pair, previous)
        tau += 2.0 * pair
        previous = pair
        t += 2

    tau = max(tau, 1.0)
    return float(min(total, total / tau))


def effective_sample_size(samples: np.ndarray) -> np.ndarray:
    """Return the effective sample size of each parameter.

    Parameters
    ----------
    samples : numpy.ndarray
        Chains, in any shape accepted by :func:`as_chains`.

    Returns
    -------
    numpy.ndarray
        One effective sample size per parameter.
    """
    chains = as_chains(samples)
    return np.array(
        [_ess_1d(chains[:, :, k]) for k in range(chains.shape[2])],
        dtype=np.float64,
    )


def autocorrelation_time(samples: np.ndarray) -> np.ndarray:
    """Return the integrated autocorrelation time of each parameter.

    This is ``n_chains * n_draws / ESS``: the number of draws that must elapse
    before the chain delivers one independent sample.

    Parameters
    ----------
    samples : numpy.ndarray
        Chains, in any shape accepted by :func:`as_chains`.

    Returns
    -------
    numpy.ndarray
        One autocorrelation time per parameter.
    """
    chains = as_chains(samples)
    total = float(chains.shape[0] * chains.shape[1])
    ess = effective_sample_size(chains)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(ess > 0.0, total / ess, np.inf)


def split_rhat(samples: np.ndarray) -> np.ndarray:
    r"""Return the split Gelman–Rubin statistic of each parameter.

    Each chain is halved before the comparison, so a *single* chain that drifts
    over its length is still caught: its two halves disagree even though there
    is no second chain to disagree with.

    Parameters
    ----------
    samples : numpy.ndarray
        Chains, in any shape accepted by :func:`as_chains`.

    Returns
    -------
    numpy.ndarray
        One :math:`\\hat{R}` per parameter; ``nan`` when the chains are too
        short (fewer than four draws) to split.
    """
    chains = as_chains(samples)
    m, n, n_par = chains.shape
    half = n // 2
    if half < 2:
        return np.full(n_par, np.nan, dtype=np.float64)

    split = np.concatenate([chains[:, :half, :], chains[:, n - half:, :]], axis=0)
    m2, n2, _ = split.shape

    out = np.empty(n_par, dtype=np.float64)
    for k in range(n_par):
        block = split[:, :, k]
        within = float(np.mean(np.var(block, axis=1, ddof=1)))
        if not (within > 0.0):
            # Every chain is constant. If they agree the chains are identical
            # (R-hat 1); if they disagree they are stuck in different places,
            # which is the worst possible failure.
            means = block.mean(axis=1)
            out[k] = 1.0 if np.allclose(means, means[0]) else np.inf
            continue
        between = n2 * float(np.var(block.mean(axis=1), ddof=1))
        var_plus = (n2 - 1) / n2 * within + between / n2
        out[k] = math.sqrt(var_plus / within)
    return out


def mcse(samples: np.ndarray) -> np.ndarray:
    """Return the Monte-Carlo standard error of each parameter's mean.

    ``sd / sqrt(ESS)`` -- how much of the reported posterior mean is sampling
    noise rather than posterior. A credible interval is only meaningful when
    this is small against the posterior width.

    Parameters
    ----------
    samples : numpy.ndarray
        Chains, in any shape accepted by :func:`as_chains`.

    Returns
    -------
    numpy.ndarray
        One standard error per parameter.
    """
    chains = as_chains(samples)
    flat = chains.reshape(-1, chains.shape[2])
    sd = flat.std(axis=0, ddof=1) if flat.shape[0] > 1 else np.zeros(flat.shape[1])
    ess = effective_sample_size(chains)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(ess > 0.0, sd / np.sqrt(ess), np.inf)


def suggest_burn_in(samples: np.ndarray) -> int:
    """Return the number of initial draws that should be discarded.

    ``min(n_draws // 2, ceil(2 * tau_max))``: twice the slowest parameter's
    autocorrelation time is the usual rule for the chain to have forgotten where
    it started, capped so that a badly mixing chain does not consume itself.

    The value is a *recommendation*. Callers apply it to summary statistics and
    leave the stored chain intact, so the raw draws remain available for a
    reader who disagrees.

    Parameters
    ----------
    samples : numpy.ndarray
        Chains, in any shape accepted by :func:`as_chains`.

    Returns
    -------
    int
        Number of leading draws to discard from each chain.
    """
    chains = as_chains(samples)
    n = chains.shape[1]
    if n < 4:
        return 0
    tau = autocorrelation_time(chains)
    tau = tau[np.isfinite(tau)]
    if tau.size == 0:
        return n // 4
    return int(min(n // 2, math.ceil(2.0 * float(tau.max()))))


def summarize(
        samples: np.ndarray,
        names: typing.Sequence[str] = None,
        burn_in: int = None,
        quantiles: typing.Sequence[float] = (0.025, 0.16, 0.5, 0.84, 0.975),
) -> typing.List[typing.Dict[str, typing.Any]]:
    r"""Summarise a set of chains, one entry per parameter.

    Location and spread are computed *after* discarding the burn-in, while
    :math:`\\hat{R}` and the effective sample size are computed on the same
    post-burn-in draws, so every reported number describes the same sample.

    Parameters
    ----------
    samples : numpy.ndarray
        Chains, in any shape accepted by :func:`as_chains`.
    names : sequence of str, optional
        Parameter names; defaults to ``p0``, ``p1``, …
    burn_in : int, optional
        Draws to discard from the start of each chain. Defaults to
        :func:`suggest_burn_in`; pass ``0`` to keep everything.
    quantiles : sequence of float, optional
        Posterior quantiles to report.

    Returns
    -------
    list of dict
        Per parameter: ``name``, ``mean``, ``sd``, ``quantiles`` (a dict keyed by
        the requested probabilities), ``ess``, ``rhat``, ``tau``, ``mcse``,
        ``n_chains``, ``n_draws`` and the applied ``burn_in``.
    """
    chains = as_chains(samples)
    if burn_in is None:
        burn_in = suggest_burn_in(chains)
    burn_in = int(max(0, min(burn_in, chains.shape[1] - 1)))
    kept = chains[:, burn_in:, :]

    n_par = kept.shape[2]
    if names is None:
        names = [f"p{k}" for k in range(n_par)]
    names = list(names)
    if len(names) < n_par:
        names += [f"p{k}" for k in range(len(names), n_par)]

    ess = effective_sample_size(kept)
    rhat = split_rhat(kept)
    tau = autocorrelation_time(kept)
    err = mcse(kept)
    flat = kept.reshape(-1, n_par)

    out = []
    for k in range(n_par):
        column = flat[:, k]
        finite = column[np.isfinite(column)]
        qs = (
            {str(q): float(np.quantile(finite, q)) for q in quantiles}
            if finite.size else {str(q): float("nan") for q in quantiles}
        )
        out.append({
            "name": str(names[k]),
            "mean": float(finite.mean()) if finite.size else float("nan"),
            "sd": float(finite.std(ddof=1)) if finite.size > 1 else float("nan"),
            "quantiles": qs,
            "ess": float(ess[k]),
            "rhat": float(rhat[k]),
            "tau": float(tau[k]),
            "mcse": float(err[k]),
            "n_chains": int(kept.shape[0]),
            "n_draws": int(kept.shape[1]),
            "burn_in": burn_in,
        })
    return out


def convergence_warnings(
        summary: typing.Sequence[typing.Dict[str, typing.Any]],
        rhat_threshold: float = RHAT_THRESHOLD,
        ess_threshold: float = ESS_THRESHOLD,
) -> typing.List[str]:
    r"""Return the human-readable reasons not to trust a chain.

    An empty list is the only "this looks converged" signal this module gives;
    it is deliberately not phrased as a guarantee, because these statistics can
    only ever detect failure, never prove success.

    Parameters
    ----------
    summary : sequence of dict
        Output of :func:`summarize`.
    rhat_threshold : float, optional
        Split-:math:`\\hat{R}` above which a parameter is flagged.
    ess_threshold : float, optional
        Effective sample size below which a parameter is flagged.

    Returns
    -------
    list of str
        One message per problem found.
    """
    messages = []
    bad_rhat = [
        e for e in summary
        if np.isfinite(e.get("rhat", np.nan)) and e["rhat"] > rhat_threshold
    ]
    if bad_rhat:
        worst = max(bad_rhat, key=lambda e: e["rhat"])
        messages.append(
            f"{len(bad_rhat)} parameter(s) have split R-hat > {rhat_threshold} "
            f"(worst: {worst['name']} at {worst['rhat']:.3f}) -- the chains have "
            "not mixed; sample longer or improve the proposal."
        )
    low_ess = [
        e for e in summary
        if np.isfinite(e.get("ess", np.nan)) and e["ess"] < ess_threshold
    ]
    if low_ess:
        worst = min(low_ess, key=lambda e: e["ess"])
        messages.append(
            f"{len(low_ess)} parameter(s) have an effective sample size below "
            f"{ess_threshold:g} (worst: {worst['name']} at {worst['ess']:.0f}) -- "
            "the reported quantiles are dominated by sampling noise."
        )
    stuck = [e for e in summary if not np.isfinite(e.get("rhat", np.nan))]
    if stuck:
        messages.append(
            f"{len(stuck)} parameter(s) never moved or disagree completely "
            f"between chains (e.g. {stuck[0]['name']})."
        )
    return messages
