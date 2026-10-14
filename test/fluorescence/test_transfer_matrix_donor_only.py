"""The E(t) transfer matrix: FRET decay per distance, donor-only for the last bins.

Each row is exp(-k_FRET(r) t) with k_FRET = (3/2) kappa2 / tau0 (R0 / r)^6; the
``n_donor_bins`` longest distances stand for donor-only molecules, which transfer
nothing, so their rows are exp(0) = 1 at every time. The slice that was meant to
zero them (``rates[-1:-n]``) was empty, so no row was donor-only.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.general import calc_transfer_matrix


def _expected(times, r, R0=52.0, tau0=4.0, kappa2=0.667):
    k = 1.5 * kappa2 / tau0 * (R0 / r) ** 6
    return np.exp(-np.outer(k, times))


def test_the_last_bins_are_donor_only():
    times = np.linspace(0.0, 10.0, 51)
    m, r = calc_transfer_matrix(times, rDA_min=10.0, rDA_max=100.0, n_steps=20, n_donor_bins=3)
    np.testing.assert_array_equal(m[-3:], 1.0)
    np.testing.assert_allclose(m[:-3], _expected(times, r[:-3]), rtol=1e-12)


def test_no_donor_bins_keeps_every_distance():
    times = np.linspace(0.0, 10.0, 11)
    m, r = calc_transfer_matrix(times, rDA_min=10.0, rDA_max=100.0, n_steps=8, n_donor_bins=0)
    np.testing.assert_allclose(m, _expected(times, r), rtol=1e-12)
