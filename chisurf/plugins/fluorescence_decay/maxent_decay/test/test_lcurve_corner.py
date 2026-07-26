"""Headless tests for the MaxEnt MEM L-curve corner selection (RF-217)."""

from __future__ import annotations

import numpy as np

from chisurf.core.math.regularization import discrete_lcurve_corner
from chisurf.plugins.fluorescence_decay.maxent_decay.backend.services import (
    _lcurve_corner_index,
)


def _l_shaped_sweep() -> tuple[list[float], list[float]]:
    """Return a synthetic L-shaped (chi2, solution-norm) sweep with a clear corner."""
    chi2 = [1.0, 1.0, 1.0, 1.0, 2.0, 10.0, 100.0, 1000.0]
    sol_norm = [1000.0, 100.0, 10.0, 2.0, 1.0, 1.0, 1.0, 1.0]
    return chi2, sol_norm


def test_corner_index_is_reported_not_swallowed():
    """A sweep with a corner reports an index — it must never come back as None."""
    chi2, sol_norm = _l_shaped_sweep()
    index = _lcurve_corner_index(chi2, sol_norm)
    assert index is not None
    assert index == discrete_lcurve_corner(np.asarray(chi2), np.asarray(sol_norm))


def test_corner_index_refers_to_the_unfiltered_sweep():
    """Non-finite leading points shift the corner index of the filtered arrays back."""
    chi2, sol_norm = _l_shaped_sweep()
    reference = _lcurve_corner_index(chi2, sol_norm)

    padded_chi2 = [float("nan"), -1.0, *chi2]
    padded_sol = [1.0, 1.0, *sol_norm]
    assert _lcurve_corner_index(padded_chi2, padded_sol) == reference + 2


def test_corner_index_is_none_without_enough_usable_points():
    """Fewer than three usable sweep points cannot define a corner."""
    assert _lcurve_corner_index([1.0, 2.0], [2.0, 1.0]) is None
    assert _lcurve_corner_index([np.nan] * 8, [1.0] * 8) is None
    assert _lcurve_corner_index([], []) is None
