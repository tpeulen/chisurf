r"""Dependence between parameters, when a correlation coefficient is not it.

The posterior graph shades its edges by the correlation of two parameters, which
for a Gaussian posterior is the whole story: :math:`r = 0` there *means*
independent. Away from Gaussian it means nothing of the kind. A banana-shaped
posterior -- the ordinary shape when a lifetime trades against an amplitude near
a bound -- has :math:`r \approx 0` and two parameters that are almost perfectly
determined by each other. Drawn by correlation alone it appears as two
independent measurements, which is the opposite of the truth.

Mutual information does not have that blind spot:

.. math::

    I(X;Y) \;=\; H(X) + H(Y) - H(X,Y),

zero **iff** the two are independent, whatever the shape. It is reported here on
the scale of a correlation coefficient via the informational coefficient

.. math::

    r_I \;=\; \sqrt{1 - e^{-2I}},

which for a Gaussian is exactly :math:`|r|` -- so the two numbers are directly
comparable, and the interesting quantity is where they *disagree*: dependence
that a correlation coefficient cannot see.

Two things make the estimate trustworthy rather than merely available.

**Equiprobable bins.** Each variable is binned by its own quantiles rather than
on an equal-width grid, so both marginals are uniform by construction. The
estimator's behaviour then depends on the draw count and the bin count alone,
not on whether a parameter's posterior happens to be skewed -- which matters
here, because skew is exactly what these posteriors have.

**A measured null.** The plug-in estimator is positively biased: independent
variables score above zero, by roughly :math:`(B-1)^2/2N` nats, which at any
realistic draw count is the same size as a weak real dependence. Miller-Madow
removes the leading term, and what remains is measured directly by permuting one
variable -- destroying the dependence while preserving both marginals -- and
subtracting what the estimator still reports. Nothing is called dependent until
it exceeds that null by a margin the null's own spread sets.
"""

from __future__ import annotations

import numpy as np

from chisurf import typing

__all__ = [
    "mutual_information",
    "informational_correlation",
    "dependence",
    "NULL_SIGMA",
    "NONLINEAR_MARGIN",
]

#: How many standard deviations of the permutation null a mutual information
#: must clear before it is reported as dependence rather than estimator bias.
NULL_SIGMA = 4.0

#: How much larger the informational correlation must be than ``|r|`` before the
#: pair is called non-linearly dependent. Below this the two agree and the
#: ordinary correlation is a fair summary; the margin is on the same scale as a
#: correlation coefficient.
NONLINEAR_MARGIN = 0.15

#: Permutations used to measure the null. Enough to put the null's mean and
#: spread well inside the margin they are compared against, and cheap: each is a
#: shuffle and a ``bincount``, with no model evaluation anywhere.
N_PERMUTATIONS = 64


def _thin_to_independent(
    x: np.ndarray,
    y: np.ndarray,
) -> typing.Tuple[np.ndarray, np.ndarray, float]:
    """Thin a pair of MCMC columns down to roughly independent draws.

    The permutation null destroys the dependence *and* the autocorrelation, so
    on a sticky chain it describes a sample far more informative than the one in
    hand and the verdict comes out far too eager. Measured on independent
    AR(1) columns: at an effective size near 100 the raw estimator called them
    dependent 7 times in 12, and near 20 it did so every time, reporting up to
    ``r_I = 0.51`` between two variables that share nothing at all.

    Thinning by the worst of the two autocorrelation times is the principled
    repair rather than a fudge factor: the mutual information of a posterior is a
    property of the posterior, not of how correlated the sampler's steps were, so
    the estimator should be handed the independent sample it assumes.

    Returns
    -------
    tuple
        The thinned columns and the stride used.
    """
    from chisurf.core.fitting import diagnostics as _dg

    try:
        # One chain each, so this is the within-chain autocorrelation time.
        tau_x = float(_dg.within_chain_tau(x.reshape(1, -1, 1))[0])
        tau_y = float(_dg.within_chain_tau(y.reshape(1, -1, 1))[0])
    except Exception:
        return x, y, 1.0
    tau = max(tau_x, tau_y)
    if not np.isfinite(tau) or tau <= 1.0:
        return x, y, 1.0
    stride = int(max(1, round(tau)))
    if stride <= 1:
        return x, y, 1.0
    return x[::stride], y[::stride], float(stride)


def _bin_count(n: int) -> int:
    """Return a bin count per axis for ``n`` draws.

    Grows slowly with the sample, because the estimator's bias goes as the
    *square* of the bin count while its resolution goes only as the first power:
    a fine grid on a short chain measures its own noise.
    """
    return int(max(4, min(24, round(n**0.35))))


def _resolvable(x: np.ndarray, y: np.ndarray, bins: int) -> bool:
    """Say whether two columns carry enough distinct values to be binned.

    Rank binning is blind to how *few* distinct values there are: a parameter
    stuck at one value the whole run has identical entries, and a stable argsort
    hands them the ranks ``0..n-1`` -- so a constant comes out looking uniformly
    distributed and pairs with anything at a spurious 0.14. A parameter pinned at
    a bound is not an exotic case, it is one of the commonest, and the honest
    answer for it is that the chain cannot say.
    """
    for column in (x, y):
        if np.unique(column).size < max(4, bins // 2):
            return False
    return True


def _equiprobable(x: np.ndarray, bins: int) -> np.ndarray:
    """Return bin indices placing (near) equal counts in each bin.

    Uses the rank rather than the value, so the result is invariant to any
    monotone rescaling of the parameter and both marginals come out uniform.
    Ties -- a parameter pinned at a bound for part of the chain -- are broken by
    position, which keeps the marginal uniform at the cost of splitting the tied
    block arbitrarily; that is the conservative direction, since it can only
    dilute a dependence, never manufacture one.
    """
    order = np.argsort(x, kind="stable")
    ranks = np.empty(x.size, dtype=np.int64)
    ranks[order] = np.arange(x.size, dtype=np.int64)
    return (ranks * bins) // x.size


def _plug_in_mi(bx: np.ndarray, by: np.ndarray, bins: int) -> float:
    """Return the Miller-Madow-corrected mutual information of binned data, in nats."""
    n = bx.size
    joint = np.bincount(bx * bins + by, minlength=bins * bins).astype(np.float64)
    table = joint.reshape(bins, bins)
    px = table.sum(axis=1)
    py = table.sum(axis=0)

    def _entropy(counts: np.ndarray) -> float:
        """Plug-in entropy with the Miller-Madow bias correction, in nats."""
        c = counts[counts > 0]
        p = c / n
        h = float(-(p * np.log(p)).sum())
        # The plug-in entropy is biased *low* by (m-1)/2N for m occupied cells.
        return h + (c.size - 1) / (2.0 * n)

    return _entropy(px) + _entropy(py) - _entropy(joint)


def mutual_information(
    x: np.ndarray,
    y: np.ndarray,
    bins: typing.Optional[int] = None,
) -> float:
    """Return the mutual information of two samples, in nats.

    Parameters
    ----------
    x, y : numpy.ndarray
        Paired samples of two quantities. Rows where either is non-finite are
        dropped from both.
    bins : int, optional
        Equiprobable bins per axis. Defaults to a count chosen from the sample
        size; see :func:`_bin_count`.

    Returns
    -------
    float
        Mutual information in nats, ``nan`` when there are too few usable pairs.
        The value is bias-corrected but **not** null-subtracted -- use
        :func:`dependence` for a number that has been compared against chance.
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    y = np.asarray(y, dtype=np.float64).ravel()
    if x.size != y.size:
        raise ValueError(f"x and y must be the same length, got {x.size} and {y.size}")
    keep = np.isfinite(x) & np.isfinite(y)
    x, y = x[keep], y[keep]
    if x.size < 32:
        return float("nan")
    b = int(bins) if bins else _bin_count(x.size)
    if not _resolvable(x, y, b):
        return float("nan")
    return _plug_in_mi(_equiprobable(x, b), _equiprobable(y, b), b)


def informational_correlation(mi: float) -> float:
    r"""Return mutual information on the scale of a correlation coefficient.

    :math:`r_I = \sqrt{1 - e^{-2I}}`, which for a bivariate Gaussian equals
    :math:`|r|` exactly. That equality is the point: it lets the two be compared
    directly, so a pair where they disagree is a pair whose dependence a
    correlation coefficient is missing.

    Parameters
    ----------
    mi : float
        Mutual information in nats.

    Returns
    -------
    float
        A value in ``[0, 1)``, or ``nan`` for a non-finite input. Negative
        inputs -- which a null-subtracted estimate can legitimately produce --
        return ``0.0``.
    """
    if not np.isfinite(mi):
        return float("nan")
    if mi <= 0.0:
        return 0.0
    return float(np.sqrt(1.0 - np.exp(-2.0 * mi)))


def dependence(
    x: np.ndarray,
    y: np.ndarray,
    bins: typing.Optional[int] = None,
    n_permutations: int = N_PERMUTATIONS,
    seed: int = 0,
    thin: bool = True,
) -> typing.Dict[str, typing.Any]:
    """Measure how strongly two parameters constrain each other, linearly or not.

    Parameters
    ----------
    x, y : numpy.ndarray
        Paired posterior draws of two parameters.
    bins : int, optional
        Equiprobable bins per axis; defaults to a count chosen from the sample.
    n_permutations : int, optional
        Permutations used to measure the estimator's null. Zero skips the null,
        which makes the result an upper bound rather than a verdict.
    seed : int, optional
        Fixed so the same draws give the same verdict on every call. A diagnostic
        that changes its mind between two runs on identical data is not one.
    thin : bool, optional
        Thin to roughly independent draws first; see
        :func:`_thin_to_independent` for the measurement that makes this
        necessary rather than optional. Turn it off only for samples already
        known to be independent.

    Returns
    -------
    dict
        ``mi`` (nats, null-subtracted), ``mi_raw``, ``null_mean``, ``null_sd``,
        ``dependence`` (:math:`r_I`, on the correlation scale), ``pearson``,
        ``dependent`` (clears the null), ``nonlinear`` (dependence materially
        exceeds ``|r|``) and a human-readable ``note``.

        ``dependence`` is a point estimate and stays slightly positive on
        independent data, as any such estimate does; ``dependent`` is the
        verdict, and a consumer that draws or flags an edge should honour that
        rather than the number.

    Examples
    --------
    >>> rng = np.random.default_rng(0)
    >>> t = rng.normal(size=4000)
    >>> d = dependence(t, t ** 2 + 0.1 * rng.normal(size=4000))
    >>> bool(abs(d['pearson']) < 0.1), d['nonlinear']
    (True, True)
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    y = np.asarray(y, dtype=np.float64).ravel()
    if x.size != y.size:
        raise ValueError(f"x and y must be the same length, got {x.size} and {y.size}")
    keep = np.isfinite(x) & np.isfinite(y)
    x, y = x[keep], y[keep]

    out = {
        "mi": float("nan"),
        "mi_raw": float("nan"),
        "null_mean": float("nan"),
        "null_sd": float("nan"),
        "dependence": float("nan"),
        "pearson": float("nan"),
        "dependent": False,
        "nonlinear": False,
        "n": int(x.size),
        "note": "",
    }
    if x.size < 32:
        out["note"] = "too few draws to measure dependence"
        return out

    if thin:
        x, y, stride = _thin_to_independent(x, y)
        out["stride"] = stride
        out["n_independent"] = int(x.size)
        if x.size < 32:
            out["note"] = (
                f"chain too autocorrelated to judge: {out['n']} draws thin to "
                f"{x.size} independent ones"
            )
            return out

    b = int(bins) if bins else _bin_count(x.size)
    if not _resolvable(x, y, b):
        out["note"] = (
            "a parameter barely moved, so the chain cannot say whether these two are related"
        )
        return out
    bx, by = _equiprobable(x, b), _equiprobable(y, b)
    raw = _plug_in_mi(bx, by, b)
    out["mi_raw"] = float(raw)
    out["bins"] = b

    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.corrcoef(x, y)[0, 1]
    out["pearson"] = float(r) if np.isfinite(r) else float("nan")

    if n_permutations > 0:
        # Permuting one variable destroys the dependence and preserves both
        # marginals exactly, so whatever the estimator still reports is bias.
        rng = np.random.default_rng(seed)
        null = np.empty(int(n_permutations), dtype=np.float64)
        for i in range(int(n_permutations)):
            null[i] = _plug_in_mi(bx, rng.permutation(by), b)
        mean, sd = float(null.mean()), float(null.std(ddof=1))
        out["null_mean"], out["null_sd"] = mean, sd
        mi = raw - mean
        out["dependent"] = bool(sd > 0 and (raw - mean) > NULL_SIGMA * sd)
    else:
        mi = raw
        out["dependent"] = bool(raw > 0.0)

    out["mi"] = float(mi)
    out["dependence"] = informational_correlation(mi)

    linear = abs(out["pearson"]) if np.isfinite(out["pearson"]) else 0.0
    excess = out["dependence"] - linear
    out["nonlinear"] = bool(out["dependent"] and np.isfinite(excess) and excess > NONLINEAR_MARGIN)
    if out["nonlinear"]:
        out["note"] = (
            f"dependent but not linearly (r={out['pearson']:.2f}, "
            f"r_I={out['dependence']:.2f}); a correlation coefficient "
            f"understates how much these two constrain each other"
        )
    return out


def dependence_matrix(
    draws: np.ndarray,
    bins: typing.Optional[int] = None,
    n_permutations: int = N_PERMUTATIONS,
    seed: int = 0,
) -> typing.Tuple[np.ndarray, np.ndarray]:
    """Return ``(dependence, nonlinear)`` matrices over every pair of columns.

    Parameters
    ----------
    draws : numpy.ndarray
        ``(n_draws, k)`` posterior draws.
    bins : int, optional
        Equiprobable bins per axis.
    n_permutations : int, optional
        Permutations per pair for the null. The default is affordable because a
        permutation costs a shuffle and a ``bincount``; for a wide model, lower
        it rather than skipping the null entirely.
    seed : int, optional
        Fixed for reproducibility; each pair is offset from it so pairs do not
        share a permutation sequence.

    Returns
    -------
    tuple of numpy.ndarray
        A ``(k, k)`` symmetric matrix of :math:`r_I` with ones on the diagonal,
        and a boolean ``(k, k)`` matrix flagging pairs whose dependence a
        correlation coefficient understates.

        A pair that could not be measured -- one parameter stuck, or a chain so
        autocorrelated that thinning leaves nothing -- is ``nan``, **not** zero.
        The two are opposite claims: zero asserts independence, and a stuck
        parameter is the case where that assertion is least likely to be true.
    """
    draws = np.atleast_2d(np.asarray(draws, dtype=np.float64))
    k = draws.shape[1]
    out = np.full((k, k), np.nan, dtype=np.float64)
    np.fill_diagonal(out, 1.0)
    flags = np.zeros((k, k), dtype=bool)
    for i in range(k):
        for j in range(i + 1, k):
            d = dependence(
                draws[:, i],
                draws[:, j],
                bins=bins,
                n_permutations=n_permutations,
                seed=seed + i * k + j,
            )
            out[i, j] = out[j, i] = d["dependence"]
            flags[i, j] = flags[j, i] = d["nonlinear"]
    return out, flags
