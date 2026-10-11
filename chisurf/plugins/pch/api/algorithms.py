"""PCH distributions, re-exported from the one implementation in ``core``.

This module used to be a second, numba-compiled copy of
:mod:`chisurf.core.models.pch.pch`, which had already delegated to tttrlib's
C++ engine. Two implementations of the same integral is exactly the
arrangement where the conventions drift apart -- and for PCH a drift in the
``p1[0]`` normalisation changes what the fitted occupancy *means* rather than
what it equals, so nothing that compares amplitudes would catch it. There is
now one implementation; this is the plugin's name for it.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.models.pch.pch import (
    compute_p1,
    pch_mixture,
    pch_open_system,
    pch_single_species,
)


def pch_weighted_residuals(counts, p_model, total_bins, mask):
    """Poisson-weighted residuals of a histogram fit over the populated bins of *mask*.

    Neyman's weights: each bin's error is the square root of its count. Bins
    without counts are left out, so an empty tail where the model expects
    ~1e-14 bins neither dominates chi^2 nor counts as a degree of freedom.

    Parameters
    ----------
    counts : array_like
        Number of time bins with k = 0, 1, ... photons.
    p_model : array_like
        Model probabilities P(k), normalised to one.
    total_bins : float
        Number of time bins the histogram was built from.
    mask : array_like of bool
        The fit range.

    Returns
    -------
    numpy.ndarray
        ``(counts - total_bins * p_model) / sqrt(counts)`` on the populated bins of the range.
    """
    counts = np.asarray(counts, dtype=float)
    used = np.asarray(mask, dtype=bool) & (counts > 0)
    expected = np.asarray(p_model, dtype=float) * float(total_bins)
    return (counts[used] - expected[used]) / np.sqrt(counts[used])


def pch_chi2(counts, p_model, total_bins, mask, n_parameters):
    """Return ``(chi2, dof)`` of :func:`pch_weighted_residuals` for *n_parameters* fitted values."""
    residuals = pch_weighted_residuals(counts, p_model, total_bins, mask)
    return float(np.sum(residuals**2)), int(residuals.size) - int(n_parameters)


__all__ = [
    "pch_chi2",
    "pch_weighted_residuals",
    "compute_p1",
    "pch_mixture",
    "pch_open_system",
    "pch_single_species",
]
