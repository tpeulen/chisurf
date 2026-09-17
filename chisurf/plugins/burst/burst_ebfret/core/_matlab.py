"""The MATLAB built-ins whose exact semantics ebFRET's numbers depend on.

``hist`` with bin centres, ``median``/``std`` of possibly empty vectors and
``linspace`` with a non-integer count each behave slightly differently from
their NumPy namesakes, and the difference moves axis limits and prior guesses.
They are collected here so the ports read like the reference.
"""

from __future__ import annotations

import math

import numpy as np

__all__ = ["hist", "linspace", "median", "std", "nan_max", "nan_min"]


def linspace(start: float, stop: float, n: float) -> np.ndarray:
    """MATLAB ``linspace(a, b, n)``: ``n`` is floored, and ``n < 2`` gives ``b``.

    Parameters
    ----------
    start, stop : float
        End points.
    n : float
        Number of points; a non-integer is rounded down.

    Returns
    -------
    numpy.ndarray
    """
    count = int(math.floor(n))
    if count < 1:
        return np.zeros(0)
    if count == 1:
        return np.array([float(stop)])
    return np.linspace(float(start), float(stop), count)


def hist(y, bins) -> tuple[np.ndarray, np.ndarray]:
    """MATLAB ``[n, centers] = hist(y, bins)``.

    With a vector of centres, each sample goes to the bin whose edges are the
    midpoints between neighbouring centres, the outer bins being open. A
    sample exactly on an edge goes to the upper bin. With a scalar, ``bins``
    equal-width bins span ``[min(y), max(y)]``.

    Parameters
    ----------
    y : array_like
        Samples; NaN is ignored.
    bins : int or array_like
        Number of bins or bin centres.

    Returns
    -------
    counts : numpy.ndarray
        Count per bin.
    centers : numpy.ndarray
        Bin centres.
    """
    y = np.asarray(y, dtype=float).ravel()
    y = y[~np.isnan(y)]
    if np.ndim(bins) == 0:
        n_bins = int(bins)
        lo = float(np.min(y)) if y.size else 0.0
        hi = float(np.max(y)) if y.size else 1.0
        if lo == hi:
            lo, hi = lo - 0.5, hi + 0.5
        width = (hi - lo) / n_bins
        edges = lo + width * np.arange(n_bins + 1)
        edges[-1] = hi
        centers = edges[:-1] + width / 2
    else:
        centers = np.asarray(bins, dtype=float).ravel()
    if centers.size == 0:
        return np.zeros(0), centers
    cutoff = (centers[:-1] + centers[1:]) / 2
    idx = np.searchsorted(cutoff, y, side="right")
    counts = np.bincount(idx, minlength=centers.size).astype(float)
    return counts, centers


def median(x) -> float:
    """MATLAB ``median`` of a vector: NaN for an empty one.

    Parameters
    ----------
    x : array_like
        Values.

    Returns
    -------
    float
    """
    x = np.asarray(x, dtype=float).ravel()
    if x.size == 0:
        return float("nan")
    return float(np.median(x))


def std(x) -> float:
    """MATLAB ``std``: N-1 normalised, and ``0`` for a single sample.

    Parameters
    ----------
    x : array_like
        Values.

    Returns
    -------
    float
    """
    x = np.asarray(x, dtype=float).ravel()
    if x.size == 0:
        return float("nan")
    if x.size == 1:
        return 0.0
    return float(np.std(x, ddof=1))


def nan_max(a: float, b: float) -> float:
    """MATLAB ``max(a, b)`` of two scalars, which ignores a NaN argument.

    Parameters
    ----------
    a, b : float
        Values.

    Returns
    -------
    float
    """
    return float(np.fmax(a, b))


def nan_min(a: float, b: float) -> float:
    """MATLAB ``min(a, b)`` of two scalars, which ignores a NaN argument.

    Parameters
    ----------
    a, b : float
        Values.

    Returns
    -------
    float
    """
    return float(np.fmin(a, b))
