r"""Reusing a chain under a *different* prior, without sampling again.

A sampling run is the expensive part of an analysis, and the question that
follows it is almost always "what would this look like if I had assumed
something else?" -- a tighter lifetime prior, a prior someone else prefers, or
no prior at all. Re-running the chain to answer that costs another few hundred
thousand model evaluations for a change that touches no data.

It does not have to. Draws from a posterior :math:`p_{\text{old}}` can be
reweighted to any other :math:`p_{\text{new}}` on the same support by

.. math::

    w_s \;\propto\; \frac{p_{\text{new}}(\theta_s)}{p_{\text{old}}(\theta_s)}
       \;=\; \exp\!\big[\ln\pi_{\text{new}}(\theta_s) - \ln\pi_{\text{old}}(\theta_s)\big],

because the likelihood is identical in both and cancels exactly. **No model
evaluation is involved** -- the ratio is a difference of two prior densities at
points already stored, so a reweighted answer costs microseconds where a fresh
chain costs minutes.

The catch is the one every importance sampler has: if the new prior puts mass
where the old chain has few draws, a handful of samples carry almost all the
weight and the estimate is dominated by noise -- silently, because the numbers
still look like numbers. **Pareto-smoothed importance sampling**
([Vehtari et al. 2024](https://doi.org/10.48550/arXiv.1507.02646)) addresses
both halves of that:

- it replaces the largest raw weights by the order statistics of a generalised
  Pareto distribution fitted to them, which caps their variance without the bias
  of plain truncation, and
- it returns the fitted shape :math:`\hat k`, which *diagnoses* the failure.
  :math:`\hat k > 0.7` means the reweighting cannot be trusted, however tidy the
  output looks.

That diagnostic is the reason to prefer this over raw importance sampling: it
gives an honest refusal instead of a confident wrong answer.

Notes
-----
Reweighting shares the draws of *one* chain, so it can only narrow or shift a
posterior within the region that chain explored. A new prior that moves the mass
somewhere the chain never visited is exactly the case :math:`\hat k` flags, and
the answer there is to sample again rather than to reweight.
"""
from __future__ import annotations

import math

import numpy as np

from chisurf import typing

__all__ = [
    "gpd_fit",
    "pareto_smoothed_log_weights",
    "importance_ess",
    "weighted_quantile",
    "weighted_summary",
    "reweight",
    "reweight_prior",
    "PARETO_K_THRESHOLD",
    "PARETO_K_WARN",
]

#: Fitted Pareto shape above which importance sampling is not reliable. Above
#: this the variance of the weights is infinite and the central limit theorem
#: does not apply, so the reweighted estimate has no usable error bar. From
#: Vehtari et al.; the practical recommendation is to sample again instead.
PARETO_K_THRESHOLD = 0.7

#: Shape above which the estimate is usable but converging slowly enough to be
#: worth mentioning. Below it, the reweighting behaves like ordinary Monte Carlo.
PARETO_K_WARN = 0.5


def _tail_length(n: int) -> int:
    """Return how many of the largest weights to smooth.

    ``min(n/5, 3*sqrt(n))``, the choice in Vehtari et al.: enough points to fit
    a two-parameter distribution to, but confined to the actual tail.

    Parameters
    ----------
    n : int
        Number of draws.

    Returns
    -------
    int
        Tail length.
    """
    return int(math.ceil(min(0.2 * n, 3.0 * math.sqrt(n))))


def gpd_fit(x: np.ndarray) -> typing.Tuple[float, float]:
    r"""Fit a generalised Pareto distribution to positive exceedances.

    The empirical-Bayes estimator of
    [Zhang and Stephens (2009)](https://doi.org/10.1198/tech.2009.08017): the
    profile likelihood in the single parameter :math:`\theta` is evaluated on a
    grid and averaged over it with the profile weights, which is both cheaper
    and more stable than maximising it. The shape is then shrunk towards
    :math:`1/2` by a weakly informative prior worth ten observations, which
    stops small samples reporting implausibly heavy tails.

    Parameters
    ----------
    x : numpy.ndarray
        Exceedances over the threshold, strictly positive and sorted ascending.

    Returns
    -------
    tuple of float
        ``(k, sigma)`` -- the shape and scale. ``k`` is ``nan`` if the sample is
        degenerate (fewer than five points, or no spread).
    """
    x = np.asarray(x, dtype=np.float64)
    n = x.size
    if n < 5 or not np.all(np.isfinite(x)) or x[-1] <= 0.0 or x[0] <= 0.0:
        return float("nan"), float("nan")

    # Grid of candidate theta, denser near the quartile as Zhang & Stephens
    # prescribe. ``prior`` = 3 is their recommended grid-spread constant.
    prior = 3.0
    m = 30 + int(math.sqrt(n))
    j = np.arange(1.0, m + 1.0)
    quartile = x[int(math.floor(n / 4.0 + 0.5)) - 1]
    if quartile <= 0.0:
        return float("nan"), float("nan")
    theta = 1.0 / x[-1] + (1.0 - np.sqrt(m / (j - 0.5))) / (prior * quartile)

    # Profile log-likelihood at each grid point.
    k_grid = np.mean(np.log1p(-theta[:, None] * x[None, :]), axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_like = n * (np.log(theta / -k_grid) - k_grid - 1.0)
    ok = np.isfinite(log_like)
    if not ok.any():
        return float("nan"), float("nan")
    log_like = np.where(ok, log_like, -np.inf)

    # Average theta over the grid, weighted by the profile likelihood.
    weights = np.exp(log_like - log_like.max())
    total = weights.sum()
    if not np.isfinite(total) or total <= 0.0:
        return float("nan"), float("nan")
    theta_hat = float((theta * weights).sum() / total)

    k = float(np.mean(np.log1p(-theta_hat * x)))
    sigma = float(-k / theta_hat) if theta_hat != 0.0 else float("nan")
    # Weakly informative prior on the shape, worth ten observations, centred at
    # 1/2. Without it a short tail routinely reports k > 1 from noise alone.
    k = k * n / (n + 10.0) + 0.5 * 10.0 / (n + 10.0)
    return k, sigma


def _gpd_quantile(p: np.ndarray, k: float, sigma: float) -> np.ndarray:
    """Return the generalised-Pareto inverse CDF at ``p``.

    Parameters
    ----------
    p : numpy.ndarray
        Probabilities in ``(0, 1)``.
    k : float
        Shape.
    sigma : float
        Scale.

    Returns
    -------
    numpy.ndarray
        Quantiles.
    """
    t = -np.log1p(-p)
    if abs(k) < 1e-10:
        return sigma * t          # the exponential limit as k -> 0
    return sigma * np.expm1(k * t) / k


def pareto_smoothed_log_weights(
        log_ratios: np.ndarray,
) -> typing.Tuple[np.ndarray, float]:
    r"""Return stabilised log importance weights and the Pareto shape.

    The largest weights -- the ones that would otherwise dominate -- are
    replaced by the expected order statistics of a generalised Pareto
    distribution fitted to them, and everything is capped at the largest raw
    weight. The returned :math:`\hat k` is the diagnostic: above
    :data:`PARETO_K_THRESHOLD` the result should not be used.

    Parameters
    ----------
    log_ratios : numpy.ndarray
        Log of the unnormalised importance ratios, one per draw.

    Returns
    -------
    tuple
        ``(log_weights, k_hat)``. The weights are normalised to sum to one on
        the linear scale (so ``exp(log_weights).sum() == 1``), and ``k_hat`` is
        ``nan`` when the tail was too short to fit.

    Notes
    -----
    Draws with a non-finite ratio (a new prior excluding a region the chain
    visited, giving ``-inf``) get zero weight rather than propagating ``nan``.
    """
    ratios = np.asarray(log_ratios, dtype=np.float64).ravel()
    n = ratios.size
    if n == 0:
        return np.zeros(0), float("nan")

    finite = np.isfinite(ratios)
    if not finite.any():
        # Every draw excluded: no reweighting is possible, and saying so with a
        # failing k is better than returning uniform weights.
        return np.full(n, -np.inf), float("inf")

    lw = np.where(finite, ratios, -np.inf)
    lw = lw - lw[finite].max()

    tail_len = _tail_length(int(finite.sum()))
    k_hat = float("nan")
    if tail_len >= 5:
        order = np.argsort(lw, kind="stable")
        tail_idx = order[-tail_len:]
        cutoff = lw[order[-tail_len - 1]]
        if np.isfinite(cutoff):
            # The exceedances are ``exp(lw) - exp(cutoff)``, but taking those
            # exponentials directly underflows to zero for every weight more
            # than ~700 log units below the largest -- which is exactly the
            # concentrated regime the diagnostic exists to catch, so it would go
            # blind precisely when it matters. Factoring ``exp(cutoff)`` out
            # leaves ``expm1(lw - cutoff)``, which is exact for a narrow tail
            # and finite far further out. The shape is scale-invariant, so it is
            # unchanged; the scale comes back with the ``cutoff +`` below.
            with np.errstate(over="ignore"):
                y = np.expm1(lw[tail_idx] - cutoff)
            if not np.all(np.isfinite(y)):
                # Too concentrated even for that: the tail spans more than the
                # exponential range, so the weight variance is unbounded. That
                # is a verdict, not a failure to reach one.
                k_hat = float("inf")
            elif y[-1] <= 0.0:
                # A perfectly flat tail -- equal weights, nothing to smooth and
                # nothing wrong.
                k_hat = 0.0
            else:
                # Ties at the cutoff leave leading zeros, which the fit cannot
                # use; they carry no tail information either way.
                k_hat, sigma = gpd_fit(y[y > 0.0])
                if np.isfinite(k_hat) and np.isfinite(sigma) and sigma > 0.0:
                    p = (np.arange(1.0, tail_len + 1.0) - 0.5) / tail_len
                    lw[tail_idx] = cutoff + np.log1p(
                        _gpd_quantile(p, k_hat, sigma)
                    )

    # Truncate at the largest raw weight, then normalise.
    lw = np.minimum(lw, 0.0)
    lw = np.where(finite, lw, -np.inf)
    total = float(np.log(np.exp(lw[finite]).sum()))
    return lw - total, k_hat


def importance_ess(log_weights: np.ndarray) -> float:
    r"""Return the effective sample size of a set of importance weights.

    :math:`1/\sum_s \bar w_s^2` for normalised weights -- the number of
    equally-weighted draws carrying the same information. A chain of 10 000
    draws with an ESS of 12 has been reweighted past the point of usefulness,
    which the raw draw count would not reveal.

    Parameters
    ----------
    log_weights : numpy.ndarray
        Log weights, normalised or not.

    Returns
    -------
    float
        Effective sample size.
    """
    lw = np.asarray(log_weights, dtype=np.float64).ravel()
    finite = np.isfinite(lw)
    if not finite.any():
        return 0.0
    w = np.zeros(lw.size, dtype=np.float64)
    w[finite] = np.exp(lw[finite] - lw[finite].max())
    total = w.sum()
    if total <= 0.0:
        return 0.0
    w /= total
    return float(1.0 / np.square(w).sum())


def weighted_quantile(
        values: np.ndarray,
        weights: np.ndarray,
        q: float,
) -> float:
    """Return a weighted quantile of a sample.

    Uses the mid-cumulative-weight plotting positions, which reduce to the usual
    linear-interpolation quantile when the weights are equal.

    Parameters
    ----------
    values : numpy.ndarray
        Sample values.
    weights : numpy.ndarray
        Non-negative weights, not necessarily normalised.
    q : float
        Probability in ``[0, 1]``.

    Returns
    -------
    float
        The quantile, or ``nan`` if no draw carries weight.
    """
    values = np.asarray(values, dtype=np.float64).ravel()
    weights = np.asarray(weights, dtype=np.float64).ravel()
    ok = np.isfinite(values) & np.isfinite(weights) & (weights > 0.0)
    if not ok.any():
        return float("nan")
    values, weights = values[ok], weights[ok]
    order = np.argsort(values, kind="stable")
    values, weights = values[order], weights[order]
    cumulative = np.cumsum(weights)
    positions = (cumulative - 0.5 * weights) / cumulative[-1]
    return float(np.interp(q, positions, values))


def weighted_summary(
        samples: np.ndarray,
        log_weights: np.ndarray,
        names: typing.Sequence[str] = None,
        quantiles: typing.Sequence[float] = (0.025, 0.16, 0.5, 0.84, 0.975),
) -> typing.List[typing.Dict[str, typing.Any]]:
    """Summarise draws under importance weights, one entry per parameter.

    The shape matches :func:`chisurf.core.fitting.diagnostics.summarize` so the
    two are interchangeable in a report, except that the chain-convergence
    statistics are replaced by the importance-sampling ones -- they describe
    different failures and it would be misleading to reuse the names.

    Parameters
    ----------
    samples : numpy.ndarray
        Flat draws, shape ``(n_samples, n_parameters)``.
    log_weights : numpy.ndarray
        One log weight per draw.
    names : sequence of str, optional
        Parameter names; defaults to ``p0``, ``p1``, …
    quantiles : sequence of float, optional
        Posterior quantiles to report.

    Returns
    -------
    list of dict
        Per parameter: ``name``, ``mean``, ``sd``, ``quantiles``, ``ess`` (the
        importance ESS) and ``n_draws``.
    """
    flat = np.atleast_2d(np.asarray(samples, dtype=np.float64))
    lw = np.asarray(log_weights, dtype=np.float64).ravel()
    n_par = flat.shape[1]
    if names is None:
        names = [f"p{k}" for k in range(n_par)]
    names = list(names)
    if len(names) < n_par:
        names += [f"p{k}" for k in range(len(names), n_par)]

    finite = np.isfinite(lw)
    w = np.zeros(lw.size, dtype=np.float64)
    if finite.any():
        w[finite] = np.exp(lw[finite] - lw[finite].max())
        if w.sum() > 0.0:
            w /= w.sum()
    ess = importance_ess(lw)

    out = []
    for k in range(n_par):
        column = flat[:, k]
        ok = np.isfinite(column) & (w > 0.0)
        if not ok.any():
            out.append({
                "name": str(names[k]), "mean": float("nan"), "sd": float("nan"),
                "quantiles": {str(q): float("nan") for q in quantiles},
                "ess": ess, "n_draws": int(flat.shape[0]),
            })
            continue
        values, weights = column[ok], w[ok]
        weights = weights / weights.sum()
        mean = float(values @ weights)
        # Frequency-weight variance would divide by n-1; these are reliability
        # weights, so the unbiased correction uses the weights themselves.
        denominator = 1.0 - float(np.square(weights).sum())
        var = float(weights @ np.square(values - mean))
        sd = math.sqrt(var / denominator) if denominator > 0.0 else float("nan")
        out.append({
            "name": str(names[k]),
            "mean": mean,
            "sd": sd,
            "quantiles": {
                str(q): weighted_quantile(values, weights, float(q))
                for q in quantiles
            },
            "ess": ess,
            "n_draws": int(flat.shape[0]),
        })
    return out


def reweight(
        samples: np.ndarray,
        log_ratios: np.ndarray,
        names: typing.Sequence[str] = None,
        quantiles: typing.Sequence[float] = (0.025, 0.16, 0.5, 0.84, 0.975),
) -> typing.Dict[str, typing.Any]:
    """Reweight a set of draws by given log importance ratios.

    Parameters
    ----------
    samples : numpy.ndarray
        Flat draws, shape ``(n_samples, n_parameters)``.
    log_ratios : numpy.ndarray
        Log of the unnormalised target-over-proposal ratio at each draw.
    names : sequence of str, optional
        Parameter names.
    quantiles : sequence of float, optional
        Posterior quantiles to report.

    Returns
    -------
    dict
        ``parameters`` (the per-parameter summary), ``pareto_k``, ``ess``,
        ``n_draws``, ``reliable`` and ``warnings``.
    """
    log_weights, k_hat = pareto_smoothed_log_weights(log_ratios)
    summary = weighted_summary(samples, log_weights, names=names, quantiles=quantiles)
    ess = importance_ess(log_weights)
    n = int(np.atleast_2d(np.asarray(samples)).shape[0])

    # One rule, so there is no way to be "reliable" without a shape that says
    # so: an undiagnosed reweighting is not a vouched-for one.
    warnings = []
    reliable = bool(np.isfinite(k_hat) and k_hat <= PARETO_K_THRESHOLD)
    if np.isnan(k_hat):
        warnings.append(
            "the tail was too short to fit a Pareto shape, so the weights are "
            "unsmoothed and undiagnosed -- not to be relied on either way"
        )
    elif k_hat > PARETO_K_THRESHOLD:
        warnings.append(
            f"Pareto k = {k_hat:.2f} exceeds {PARETO_K_THRESHOLD}: the weight "
            f"variance is infinite and these numbers should not be used -- the "
            f"new prior favours a region this chain did not explore, so sample "
            f"again under it"
        )
    elif k_hat > PARETO_K_WARN:
        warnings.append(
            f"Pareto k = {k_hat:.2f} is above {PARETO_K_WARN}: usable, but "
            f"converging slowly, so treat the tail quantiles with caution"
        )
    if n and ess < 0.1 * n:
        warnings.append(
            f"the reweighting kept an effective {ess:.0f} of {n} draws "
            f"({100.0 * ess / n:.1f}%)"
        )
    return {
        "parameters": summary,
        "pareto_k": float(k_hat),
        "ess": float(ess),
        "n_draws": n,
        "reliable": bool(reliable),
        "warnings": warnings,
    }


def reweight_prior(
        result: typing.Dict[str, typing.Any],
        priors: typing.Dict[str, typing.Any],
        model=None,
        old_priors: typing.Dict[str, typing.Any] = None,
        quantiles: typing.Sequence[float] = (0.025, 0.16, 0.5, 0.84, 0.975),
) -> typing.Dict[str, typing.Any]:
    r"""Ask what a stored chain would have looked like under different priors.

    Only the parameters named in ``priors`` contribute to the ratio: every other
    prior appears in both numerator and denominator and cancels exactly, as does
    the whole likelihood. So this is a difference of two scalar densities per
    named parameter per draw, and **no model is evaluated**.

    Parameters
    ----------
    result : dict
        A sampling result, as returned by the samplers in
        :mod:`chisurf.core.fitting.sample`. Needs ``parameter_values`` and
        ``parameter_names``.
    priors : dict
        Parameter name to the new prior. ``None`` removes the prior on that
        parameter (i.e. reweights towards a flat one).
    model : optional
        Model whose parameters carry the *old* priors. Names are matched against
        the chain's ``parameter_names``, tolerating a global model's ``fit:name``
        prefixes.
    old_priors : dict, optional
        Old priors by name, if they are not to be read from ``model``. Takes
        precedence over ``model`` where both supply a name.
    quantiles : sequence of float, optional
        Posterior quantiles to report.

    Returns
    -------
    dict
        As :func:`reweight`, plus ``changed`` -- the parameters whose prior
        actually differed.

    Raises
    ------
    KeyError
        If a named parameter is not in the chain. Silently ignoring it would
        answer a different question from the one asked.
    """
    from chisurf.core.fitting import priors as priors_module

    flat = np.atleast_2d(np.asarray(result["parameter_values"], dtype=np.float64))
    names = [str(n) for n in result["parameter_names"]]
    index = {n: i for i, n in enumerate(names)}
    # A global model prefixes its names; accept the short form too so a caller
    # need not know which model was sampled.
    short = {}
    for i, n in enumerate(names):
        short.setdefault(n.split(":")[-1], i)

    def _position(name: str) -> int:
        if name in index:
            return index[name]
        if name in short:
            return short[name]
        raise KeyError(f"{name!r} is not a parameter of this chain: {names}")

    def _old_prior(name: str):
        if old_priors is not None and name in old_priors:
            return priors_module.as_prior(old_priors[name])
        if model is None:
            return None
        for p in getattr(model, "parameters_all", []) or []:
            if p.name == name or str(p.name).split(":")[-1] == name.split(":")[-1]:
                return priors_module.as_prior(getattr(p, "prior", None))
        return None

    log_ratios = np.zeros(flat.shape[0], dtype=np.float64)
    changed = []
    for name, new in priors.items():
        column = flat[:, _position(name)]
        new_prior = priors_module.as_prior(new)
        old_prior = _old_prior(name)
        if new_prior is old_prior or (new_prior is None and old_prior is None):
            continue
        changed.append(name)
        for kind, prior, sign in (("new", new_prior, 1.0), ("old", old_prior, -1.0)):
            if prior is None:
                continue
            contribution = np.array(
                [prior.lnpdf(float(v)) for v in column], dtype=np.float64
            )
            log_ratios += sign * contribution

    out = reweight(flat, log_ratios, names=names, quantiles=quantiles)
    out["changed"] = changed
    if not changed:
        out["warnings"] = list(out["warnings"]) + [
            "no prior actually changed, so this is the original posterior"
        ]
    return out
