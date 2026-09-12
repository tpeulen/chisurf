"""Olga-style greedy informative FRET pair selection.

The selector itself is ``IMP.bff.select_probe_pairs``, in C++: it takes
efficiencies and RMSDs and answers which pairs to measure, which is a
question about numbers and not about this application.

What stays here is :func:`_chisq_rt_cdf`, the chi-squared right-tail weight.
It is a closed form, it is pinned directly by a test, and it is the one piece
a reader checking this against Olga's ``chisqdist.hpp`` wants to see.
"""

from __future__ import annotations

import math
from typing import Tuple

import numpy as np
from scipy.special import erfc, gammaincc


def _chisq_rt_cdf(chisq: np.ndarray, ndof: int) -> np.ndarray:
    r"""Chi-squared right-tail CDF, used as the weight.

    Evaluates :math:`Q(\nu/2,\ \chi^2/2)`, the regularized upper incomplete
    gamma, via the closed forms that exist because :math:`\nu/2` is always an
    integer or a half-integer -- elementwise over an array of any shape.

    Parameters
    ----------
    chisq : numpy.ndarray
        Chi-squared values, any shape.
    ndof : int
        Degrees of freedom.

    Returns
    -------
    numpy.ndarray
        The right-tail probability, elementwise, ``float64``.

    Notes
    -----
    **The half-integer branch was wrong for every odd** ``ndof``. Olga takes the
    expansion from Boost, whose half-integer branch loops
    ``for (n = 2; n < a; ++n)`` with ``a`` a half-integer; the port wrote
    ``range(2, int(a))``, and ``int(2.5)`` is ``2`` -- so it ran one iteration
    short every time, zero where Boost runs one. At ``ndof = 5``,
    ``chisq = 3.008`` that returned ``0.3903934`` for a true ``0.6987524`` --
    not a rounding error but very nearly half. ``ndof`` is
    the number of pairs chosen so far, so it is odd on every other greedy step,
    and these weights are exactly what decides which pair looks most
    informative.

    :func:`scipy.special.gammaincc` is the same function and settles the
    direction of that error (the corrected series agrees with it to ``4e-14``),
    but it does not carry the common path: it is general-purpose, and on the
    ``(candidates, n, n)`` arrays this is called with it measured **18x slower**
    end to end than these few-term series. Correctness came from comparing
    against it; speed came from not calling it where the closed form applies.

    ``chisq = 0`` -- the whole diagonal, on every call -- would divide by
    ``sqrt(pi * x)``. ``Q(a, 0) = 1`` exactly, so those entries are filled
    directly rather than computed.
    """
    # 0.5 * chisq allocates, deliberately. Scaling in place would halve the
    # caller's chi-squared accumulator -- which is the same defect this project
    # filed against a library's CDF sampler, and it was written here by hand
    # while trying to save exactly this one allocation.
    x = 0.5 * np.asarray(chisq, dtype=np.float64)
    a = 0.5 * ndof

    if a > 100.0:
        # Olga approximates this tail with a normal, which is off by up to
        # 1.3e-2 near the median. The series would need ~a terms here, but this
        # branch is reached only past 200 selected pairs, so the general
        # function is affordable exactly where the cheap one stops being cheap.
        return gammaincc(a, x)

    if ndof % 2 == 0:
        # a is an integer: Q(a, x) = exp(-x) * sum_{n=0}^{a-1} x**n / n!
        term = np.exp(-x)
        total = term.copy()
        for n in range(1, int(a)):
            term = term * x / n
            total += term
        return total

    # a is a half-integer: Q(a, x) = erfc(sqrt(x)) + exp(-x)/sqrt(pi x) * series
    total = erfc(np.sqrt(x))
    if a > 1.0:
        positive = x > 0.0
        xp = np.where(positive, x, 1.0)
        term = np.exp(-xp) / np.sqrt(np.pi * xp) * xp / 0.5
        series = term.copy()
        n = 2
        while n < a:
            term = term / (n - 0.5) * xp
            series += term
            n += 1
        total = total + np.where(positive, series, 0.0)
    return total


def select_informative_pairs(
    effs: np.ndarray,
    rmsds: np.ndarray,
    err: float,
    max_pairs: int,
    unique_only: bool = True,
    diag_weight: float = 0.99,
) -> Tuple[np.ndarray, np.ndarray]:
    """Choose the most informative FRET pairs, greedily.

    Parameters
    ----------
    effs : numpy.ndarray
        ``(n_structures, n_pairs)`` FRET efficiencies. Must be finite:
        Olga's GUI filters and fills NaNs before it calls the selector, and
        so must a caller here.
    rmsds : numpy.ndarray
        ``(n_structures,)`` RMSDs to the reference.
    err : float
        The efficiency error bar.
    max_pairs : int
        How many pairs to select.
    unique_only : bool
        Do not select the same pair twice.
    diag_weight : float
        Weight of the diagonal term in the precision decay.

    Returns
    -------
    tuple of numpy.ndarray
        The selected pair indices and the precision after each addition.
    """
    import IMP.bff as bff

    return bff.select_probe_pairs(
        np.ascontiguousarray(effs, dtype=np.float64),
        np.ascontiguousarray(rmsds, dtype=np.float64),
        float(err),
        int(max_pairs),
        bool(unique_only),
        float(diag_weight),
    )


__all__ = ["select_informative_pairs"]
