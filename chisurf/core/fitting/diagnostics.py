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
    "rank_normalize",
    "rank_normalized_rhat",
    "bulk_tail_ess",
    "mcse",
    "suggest_burn_in",
    "summarize",
    "convergence_warnings",
    "rank_histogram",
    "rank_uniformity",
    "within_chain_tau",
    "ess_evolution",
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
    """Effective sample size of one parameter, given ``(n_chains, n_draws)``.

    Returns ``nan`` when any draw is non-finite: a single ``nan``/``inf``
    contaminates the whole autocovariance, so the effective sample size is
    *unknown* rather than maximal. :func:`rank_normalized_rhat` and
    :func:`bulk_tail_ess` refuse the same input, and returning the raw draw
    count here would read as perfectly independent draws beside their ``nan``.
    """
    m, n = chains.shape
    total = float(m * n)
    if not np.all(np.isfinite(chains)):
        return float("nan")
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
        One effective sample size per parameter; ``nan`` for a parameter with
        any non-finite draw.
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
        One autocorrelation time per parameter; ``nan`` for a parameter with
        any non-finite draw.
    """
    chains = as_chains(samples)
    total = float(chains.shape[0] * chains.shape[1])
    ess = effective_sample_size(chains)
    with np.errstate(divide="ignore", invalid="ignore"):
        tau = np.where(ess > 0.0, total / ess, np.inf)
    # An undefined effective sample size leaves the autocorrelation time
    # undefined too; "infinitely correlated" would be a different claim.
    return np.where(np.isnan(ess), np.nan, tau)


def rank_normalize(samples: np.ndarray) -> np.ndarray:
    r"""Replace draws by the normal scores of their pooled average ranks.

    :math:`z = \Phi^{-1}\!\left(\frac{r - 3/8}{N + 1/4}\right)` over the
    draws of *all* chains together, with tied values sharing their average rank.

    This is what makes :math:`\hat{R}` and the effective sample size usable on
    a posterior that is not nicely behaved. Both are defined through variances,
    so on a heavy-tailed -- or infinite-variance -- target they are not merely
    imprecise but undefined, and will happily report a comfortable number.
    Ranks exist whatever the tail does.

    Parameters
    ----------
    samples : numpy.ndarray
        ``(n_chains, n_draws)`` for one parameter.

    Returns
    -------
    numpy.ndarray
        Normal scores, same shape.
    """
    a = np.asarray(samples, dtype=np.float64)
    flat = a.ravel()
    n = flat.size
    order = np.argsort(flat, kind="mergesort")
    ranks = np.empty(n, dtype=np.float64)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and flat[order[j + 1]] == flat[order[i]]:
            j += 1
        # Ranks are 1-based; ties share their average.
        average = 0.5 * ((i + 1) + (j + 1))
        ranks[order[i:j + 1]] = average
        i = j + 1
    return _normal_ppf((ranks - 0.375) / (n + 0.25)).reshape(a.shape)


def _normal_ppf(p: np.ndarray) -> np.ndarray:
    """Return the standard-normal quantile, vectorised (Acklam's approximation).

    Accurate to ~1e-9 relative, which is far beyond what a rank transform needs,
    and avoids a SciPy import on a hot path.
    """
    p = np.asarray(p, dtype=np.float64)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    out = np.empty_like(p)
    lo, hi = p < 0.02425, p > 1 - 0.02425
    mid = ~(lo | hi)

    q = np.sqrt(-2.0 * np.log(np.where(lo, p, 0.5)))
    out = np.where(lo, (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5])
                   / ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1), out)
    q = np.sqrt(-2.0 * np.log(np.where(hi, 1.0 - p, 0.5)))
    out = np.where(hi, -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5])
                   / ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1), out)
    q = np.where(mid, p, 0.5) - 0.5
    r = q * q
    out = np.where(mid, (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5]) * q
                   / (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1), out)
    return out


def _split(chains: np.ndarray) -> np.ndarray:
    """Halve every chain, doubling their number.

    Splitting is what lets a *single* drifting chain be caught: its two halves
    disagree even when there is no second chain to disagree with.
    """
    m, n = chains.shape
    half = n // 2
    if half < 2:
        return chains
    return np.concatenate([chains[:, :half], chains[:, n - half:]], axis=0)


def _rhat_1d(chains: np.ndarray) -> float:
    """Plain Gelman-Rubin on already-split chains."""
    m, n = chains.shape
    within = float(np.mean(np.var(chains, axis=1, ddof=1)))
    if not (within > 0.0):
        means = chains.mean(axis=1)
        return 1.0 if np.allclose(means, means[0]) else float("inf")
    between = n * float(np.var(chains.mean(axis=1), ddof=1))
    var_plus = (n - 1) / n * within + between / n
    return math.sqrt(var_plus / within)


def rank_normalized_rhat(samples: np.ndarray) -> np.ndarray:
    r"""Return ``max(bulk, tail)`` split :math:`\hat{R}` per parameter.

    Two failures are reported, and the worse one wins:

    - **bulk** -- :math:`\hat{R}` of the rank-normalised draws. Chains sitting
      in different *places*.
    - **tail** -- :math:`\hat{R}` of the rank-normalised
      :math:`|x - \mathrm{median}|`. Chains with the same centre but different
      *spread*, which the location statistic cannot see at all: two chains, one
      twice as wide as the other, agree perfectly on their mean.

    Parameters
    ----------
    samples : numpy.ndarray
        Chains, in any shape accepted by :func:`as_chains`.

    Returns
    -------
    numpy.ndarray
        One value per parameter; ``nan`` when the chains are too short.

    References
    ----------
    Vehtari et al., *Rank-normalization, folding, and localization: an improved
    R-hat for assessing convergence of MCMC*, Bayesian Analysis 16, 667 (2021).
    """
    chains = as_chains(samples)
    n_par = chains.shape[2]
    out = np.empty(n_par, dtype=np.float64)
    for k in range(n_par):
        block = _split(chains[:, :, k])
        if block.shape[1] < 2 or not np.all(np.isfinite(block)):
            out[k] = np.nan
            continue
        if np.ptp(block) == 0.0:
            means = block.mean(axis=1)
            out[k] = 1.0 if np.allclose(means, means[0]) else np.inf
            continue
        bulk = _rhat_1d(rank_normalize(block))
        folded = np.abs(block - np.median(block))
        tail = _rhat_1d(rank_normalize(folded)) if np.ptp(folded) > 0 else 1.0
        out[k] = max(bulk, tail)
    return out


def bulk_tail_ess(samples: np.ndarray) -> typing.Tuple[np.ndarray, np.ndarray]:
    """Return the bulk and tail effective sample sizes per parameter.

    **bulk** is the effective sample size of the rank-normalised draws, and
    governs the posterior *mean*. **tail** is the smaller of the effective
    sample sizes of the 5 % and 95 % tail-indicator sequences, and governs the
    *quantiles* -- which are what a credible interval is actually made of. A
    chain can have a perfectly good bulk ESS and a tail ESS an order of
    magnitude smaller, and it is the tail one that says whether the interval
    can be quoted.

    Parameters
    ----------
    samples : numpy.ndarray
        Chains, in any shape accepted by :func:`as_chains`.

    Returns
    -------
    tuple of numpy.ndarray
        ``(bulk, tail)``, one entry per parameter.
    """
    chains = as_chains(samples)
    n_par = chains.shape[2]
    bulk = np.empty(n_par, dtype=np.float64)
    tail = np.empty(n_par, dtype=np.float64)
    for k in range(n_par):
        block = _split(chains[:, :, k])
        if block.shape[1] < 4 or not np.all(np.isfinite(block)) or np.ptp(block) == 0.0:
            bulk[k] = tail[k] = np.nan
            continue
        bulk[k] = _ess_1d(rank_normalize(block))
        flat = block.ravel()
        low = _ess_1d((block <= np.quantile(flat, 0.05)).astype(np.float64))
        high = _ess_1d((block >= np.quantile(flat, 0.95)).astype(np.float64))
        candidates = [v for v in (low, high) if np.isfinite(v)]
        tail[k] = min(candidates) if candidates else np.nan
    return bulk, tail


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
        One standard error per parameter; ``nan`` for a parameter with any
        non-finite draw.
    """
    chains = as_chains(samples)
    flat = chains.reshape(-1, chains.shape[2])
    sd = flat.std(axis=0, ddof=1) if flat.shape[0] > 1 else np.zeros(flat.shape[1])
    ess = effective_sample_size(chains)
    with np.errstate(divide="ignore", invalid="ignore"):
        err = np.where(ess > 0.0, sd / np.sqrt(ess), np.inf)
    # A zero effective sample size means the mean is pure noise; an undefined
    # one means the error is unknown, which is not the same statement.
    return np.where(np.isnan(ess), np.nan, err)


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
    # The rank-normalised statistics are what the verdict keys off: the plain
    # ones are undefined on a heavy-tailed target and blind to two chains that
    # share a centre but not a spread. Both are reported, so a disagreement
    # between them is visible rather than silently resolved.
    rhat = rank_normalized_rhat(kept)
    plain_rhat = split_rhat(kept)
    bulk, tail = bulk_tail_ess(kept)
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
            "ess_bulk": float(bulk[k]),
            "ess_tail": float(tail[k]),
            "rhat": float(rhat[k]),
            "rhat_plain": float(plain_rhat[k]),
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
            f"{len(bad_rhat)} parameter(s) have rank-normalised split R-hat > "
            f"{rhat_threshold} (worst: {worst['name']} at {worst['rhat']:.3f}) -- "
            "the chains have not mixed in location or in spread; sample longer "
            "or improve the proposal."
        )
    for key, what in (("ess_bulk", "bulk"), ("ess_tail", "tail")):
        low = [
            e for e in summary
            if np.isfinite(e.get(key, np.nan)) and e[key] < ess_threshold
        ]
        if not low:
            continue
        worst = min(low, key=lambda e: e[key])
        governs = ("the posterior mean" if what == "bulk"
                   else "the quantiles a credible interval is made of")
        messages.append(
            f"{len(low)} parameter(s) have a {what} effective sample size below "
            f"{ess_threshold:g} (worst: {worst['name']} at {worst[key]:.0f}) -- "
            f"{governs} are dominated by sampling noise."
        )
    if not any("effective sample size" in m for m in messages):
        low_ess = [
            e for e in summary
            if np.isfinite(e.get("ess", np.nan)) and e["ess"] < ess_threshold
        ]
        if low_ess:
            worst = min(low_ess, key=lambda e: e["ess"])
            messages.append(
                f"{len(low_ess)} parameter(s) have an effective sample size below "
                f"{ess_threshold:g} (worst: {worst['name']} at {worst['ess']:.0f})."
            )
    stuck = [e for e in summary if not np.isfinite(e.get("rhat", np.nan))]
    if stuck:
        messages.append(
            f"{len(stuck)} parameter(s) never moved or disagree completely "
            f"between chains (e.g. {stuck[0]['name']})."
        )
    return messages


def rank_histogram(
        samples: np.ndarray,
        bins: int = 20,
) -> typing.Tuple[np.ndarray, np.ndarray, float]:
    r"""Return per-chain rank histograms — the plot that replaces the trace plot.

    Draws are ranked **across all chains together** and each chain's ranks are
    histogrammed. If the chains are sampling the same distribution, every chain
    holds an equal share of the low, middle and high ranks, so every histogram
    is flat at ``n_draws / bins``. A chain that lingers somewhere the others do
    not shows as a slope or a spike, at a glance and on a fixed scale.

    This is the display counterpart of :func:`rank_normalized_rhat`, and it is
    recommended over a trace plot for the same reason
    ([Vehtari et al. 2021](https://doi.org/10.1214/20-BA1221)): a trace plot's
    resolution collapses as the chain gets longer, so exactly when there are
    enough draws to judge convergence it becomes a black smear. A rank histogram
    is just as readable at ten thousand draws as at one thousand.

    Parameters
    ----------
    samples : numpy.ndarray
        Chains, in any shape accepted by :func:`as_chains`.
    bins : int, optional
        Number of rank bins.

    Returns
    -------
    tuple
        ``(counts, edges, expected)`` -- ``counts`` is
        ``(n_parameters, n_chains, bins)``, ``edges`` the ``bins + 1`` bin edges
        in rank space ``[0, 1]``, and ``expected`` the flat level every chain
        should sit at.
    """
    chains = as_chains(samples)
    n_chains, n_draws, n_par = chains.shape
    bins = max(1, int(bins))
    total = n_chains * n_draws
    edges = np.linspace(0.0, 1.0, bins + 1)
    counts = np.zeros((n_par, n_chains, bins), dtype=np.float64)

    for k in range(n_par):
        flat = chains[:, :, k].ravel()
        order = np.argsort(flat, kind="mergesort")
        ranks = np.empty(total, dtype=np.float64)
        # Average ranks for ties, so a parameter stuck at a bound does not put
        # all of its draws in whichever bin the sort happened to favour.
        i = 0
        while i < total:
            j = i
            while j + 1 < total and flat[order[j + 1]] == flat[order[i]]:
                j += 1
            ranks[order[i:j + 1]] = 0.5 * ((i + 1) + (j + 1))
            i = j + 1
        scaled = (ranks - 0.5) / total
        for c in range(n_chains):
            counts[k, c], _ = np.histogram(
                scaled[c * n_draws:(c + 1) * n_draws], bins=edges
            )
    return counts, edges, float(n_draws) / bins


def ess_evolution(
        samples: np.ndarray,
        points: int = 12,
) -> typing.Tuple[np.ndarray, np.ndarray]:
    """Return the effective sample size computed on growing prefixes of a chain.

    A converged sampler's effective sample size grows **linearly** with the
    draws taken: twice the effort buys twice the information. One that has not
    converged -- stuck in a mode, or with an autocorrelation time longer than
    the run -- shows an ESS that flattens, and the flattening is visible long
    before any single number crosses a threshold. A final ESS on its own cannot
    show this, because it is one point on this curve with the shape discarded.

    Parameters
    ----------
    samples : numpy.ndarray
        Chains, in any shape accepted by :func:`as_chains`.
    points : int, optional
        How many prefix lengths to evaluate.

    Returns
    -------
    tuple
        ``(draws, ess)`` -- the prefix lengths, and ``(n_points, n_parameters)``
        effective sample sizes.
    """
    chains = as_chains(samples)
    n_draws = chains.shape[1]
    points = max(2, int(points))
    # Below ~8 draws the estimator has nothing to work with; start there rather
    # than reporting noise as the first point of the curve.
    if n_draws < 8:
        return np.zeros(0, dtype=int), np.zeros((0, chains.shape[2]))
    lengths = np.unique(
        np.linspace(max(8, n_draws // points), n_draws, points).astype(int)
    )
    # A prefix longer than the chain would silently be truncated by the slice
    # and reported under the wrong draw count.
    lengths = lengths[(lengths >= 8) & (lengths <= n_draws)]
    if lengths.size == 0:
        return np.zeros(0, dtype=int), np.zeros((0, chains.shape[2]))
    out = np.array([
        effective_sample_size(chains[:, :int(n), :]) for n in lengths
    ])
    return lengths, out


def within_chain_tau(samples: np.ndarray) -> np.ndarray:
    """Return each parameter's autocorrelation time *within* a chain.

    Averaged over chains, and deliberately **not** derived from the pooled
    effective sample size. The pooled figure collapses when chains disagree with
    each other, which is the very failure a rank histogram exists to detect: use
    it to set the noise level and a badly split run explains its own structure
    away. A chain's own autocorrelation is unaffected by where the other chains
    happen to be.

    Parameters
    ----------
    samples : numpy.ndarray
        Chains, in any shape accepted by :func:`as_chains`.

    Returns
    -------
    numpy.ndarray
        One autocorrelation time per parameter, at least 1.
    """
    chains = as_chains(samples)
    n_chains, n_draws, n_par = chains.shape
    per_chain = np.empty((n_chains, n_par), dtype=np.float64)
    for c in range(n_chains):
        ess = effective_sample_size(chains[c:c + 1])
        per_chain[c] = n_draws / np.maximum(ess, 1e-9)
    return np.maximum(per_chain.mean(axis=0), 1.0)


def rank_uniformity(
        counts: np.ndarray,
        n_draws: int,
        bins: int,
        tau: float = 1.0,
) -> typing.Tuple[float, float]:
    r"""Return ``(z_max, z_null)`` for one parameter's rank histogram.

    A rank histogram is never exactly flat, and how far from flat it should be
    is not a matter of taste: under the null each chain's bin count is
    :math:`\mathrm{Binomial}(n, 1/b)`, so the standard deviation is
    :math:`\sqrt{n\,p\,(1-p)}` and the largest of :math:`N` standardised
    deviations is about :math:`\sqrt{2\ln N}` even when nothing is wrong.

    Comparing the two is the difference between a diagnostic and a nuisance.
    Judging "flat" by a fixed percentage flags every converged run with enough
    bins in it -- and a warning that fires on healthy chains is worse than no
    warning at all, because it teaches the reader to skip it.

    The binomial variance assumes *independent* draws, which no MCMC chain
    produces. Autocorrelation inflates the variance of a bin count by roughly
    the autocorrelation time, so ``tau`` scales the null: without it a perfectly
    converged but slowly-mixing chain reports several sigma of structure that is
    nothing but its own memory. Pass :func:`within_chain_tau`, not something
    derived from the pooled effective sample size -- see that function for why.

    Parameters
    ----------
    counts : numpy.ndarray
        ``(n_chains, bins)`` counts for one parameter.
    n_draws : int
        Draws per chain.
    bins : int
        Number of rank bins.
    tau : float, optional
        Within-chain autocorrelation time. The default of 1 assumes independent
        draws and will over-report structure on any real chain.

    Returns
    -------
    tuple
        The largest standardised deviation, and the value expected from noise
        alone for a histogram of this size. Their *ratio* is the thing to read:
        near one is flat, well above one is structure.
    """
    counts = np.atleast_2d(np.asarray(counts, dtype=np.float64))
    p = 1.0 / max(1, int(bins))
    expected = float(n_draws) * p
    sd = math.sqrt(
        max(float(n_draws) * p * (1.0 - p) * max(float(tau), 1.0), 1e-30)
    )
    z_max = float(np.abs(counts - expected).max() / sd)
    n_cells = max(counts.size, 2)
    return z_max, math.sqrt(2.0 * math.log(n_cells))
