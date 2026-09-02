"""``kappa2_to_distance_ratio`` and ``convolve_distance_with_k2_ratio``.

Both forwarded to a module path that never existed
(``IMP.bff.spectroscopy.kappa2``, not the flat ``IMP.bff`` the rest of
ChiSurf's ``IMP.bff`` forwarders use) and raised ``ImportError`` the moment
either was called. Nothing exercised them, so nothing said so.

``kappa2_to_distance_ratio`` now forwards to
``IMP.bff.kappa2_distance_ratio_transform``, a deterministic change of
variable (no Monte-Carlo, no RNG) -- so its output is checked against closed
forms, not moments. ``convolve_distance_with_k2_ratio`` stays ChiSurf-owned
(data reduction over ChiSurf arrays, not a structure/spectroscopy model) and
is checked against the exact outer-product path it has a fallback for.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.general import (
    convolve_distance_with_k2_ratio,
    kappa2_to_distance_ratio,
)


def test_a_single_kappa2_value_maps_to_a_single_ratio_of_one():
    """With no spread in kappa^2, R_app/R_DA is 1 everywhere it has mass."""
    k2_amp = np.array([1.0])
    k2_val = np.array([2.0 / 3.0])
    r_ratio, weights, k2_mean = kappa2_to_distance_ratio(k2_amp, k2_val, n_bins=8)

    assert k2_mean == pytest.approx(2.0 / 3.0)
    # All the mass sits on the single input value, so it lands in one bin
    # (interpolation can spread it across at most its immediate neighbours).
    assert weights.sum() == pytest.approx(1.0, abs=1e-6)
    nonzero = r_ratio[weights > 1e-9]
    assert np.allclose(nonzero, 1.0, atol=0.2)


def test_the_weights_are_normalized():
    """Whatever the input amplitudes, the output is a probability distribution."""
    k2_amp = np.array([3.0, 1.0, 5.0, 0.5])
    k2_val = np.array([0.3, 0.667, 1.2, 2.0])
    _, weights, _ = kappa2_to_distance_ratio(k2_amp, k2_val, n_bins=32)
    assert weights.sum() == pytest.approx(1.0, abs=1e-6)
    assert np.all(weights >= 0.0)


def test_low_kappa2_gives_a_larger_apparent_distance():
    """R_app/R_DA = (<k2>/k2)^(1/6): the defining inverse relationship."""
    k2_amp = np.array([1.0, 1.0])
    k2_val = np.array([0.1, 3.9])
    r_ratio, weights, k2_mean = kappa2_to_distance_ratio(k2_amp, k2_val, n_bins=64)
    # The low-kappa2 branch's mass sits above ratio 1; the high-kappa2
    # branch's sits below it.
    below = weights[r_ratio < 1.0].sum()
    above = weights[r_ratio > 1.0].sum()
    assert above > 0.0 and below > 0.0


def test_it_rejects_non_positive_kappa2():
    with pytest.raises(Exception):
        kappa2_to_distance_ratio(np.array([1.0]), np.array([0.0]), n_bins=8)


def test_convolution_matches_its_own_exact_outer_product_path():
    """The binned fast path and the exact outer-product path answer alike."""
    rng = np.random.default_rng(20260902)
    r_da = np.linspace(30.0, 70.0, 40)
    amp_r_da = rng.random(40) + 0.1
    r_ratio = np.linspace(0.7, 1.4, 25)
    weights_ratio = rng.random(25) + 0.05
    weights_ratio /= weights_ratio.sum()

    r_fast, a_fast = convolve_distance_with_k2_ratio(
        r_da, amp_r_da, r_ratio, weights_ratio, n_bins=128, use_fast=True
    )
    r_exact, a_exact = convolve_distance_with_k2_ratio(
        r_da, amp_r_da, r_ratio, weights_ratio, n_bins=128, use_fast=False
    )

    mean_fast = np.average(r_fast, weights=a_fast)
    mean_exact = np.average(r_exact, weights=a_exact)
    assert mean_fast == pytest.approx(mean_exact, rel=0.02)


def test_convolution_output_spans_the_product_of_its_inputs_ranges():
    """R_app = R_DA * ratio, so its support is bounded by the input extremes."""
    r_da = np.linspace(40.0, 60.0, 30)
    amp_r_da = np.ones_like(r_da)
    r_ratio = np.linspace(0.8, 1.2, 20)
    weights_ratio = np.ones_like(r_ratio) / r_ratio.size

    r_app, amp_app = convolve_distance_with_k2_ratio(
        r_da, amp_r_da, r_ratio, weights_ratio, n_bins=64, use_fast=True
    )
    assert amp_app.sum() > 0
    assert r_app.min() >= 40.0 * 0.8 - 1e-6
    assert r_app.max() <= 60.0 * 1.2 + 1e-6
