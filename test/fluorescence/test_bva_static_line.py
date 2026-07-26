"""Tests for the shot-noise (static) BVA line helper.

Pins RF-168: the helper carries a real NumPy docstring, and the core package is
the single home of the implementation that the burst-BVA plugin re-exports.
"""

import numpy as np
import pytest

from chisurf.core.fluorescence.burst import compute_static_bva_line


def test_static_bva_line_docstring_is_reachable():
    """The parameter documentation is the real ``__doc__``, not a stray expression."""
    doc = compute_static_bva_line.__doc__
    assert doc is not None
    for token in (
        "Parameters",
        "Returns",
        "prox_mean_bins",
        "number_of_photons_per_slice",
        "n_samples",
    ):
        assert token in doc


def test_plugin_reexports_the_core_implementation():
    """The burst-BVA plugin has no second copy of the static line."""
    from chisurf.plugins.burst.burst_bva.core import computation

    assert computation.compute_static_bva_line is compute_static_bva_line


@pytest.mark.parametrize("n_photons", [4, 10])
def test_static_line_matches_binomial_theory(n_photons):
    """Mean and SD follow the binomial shot-noise limit ``sqrt(E(1-E)/n)``."""
    rng_state = np.random.get_state()
    try:
        np.random.seed(20260726)
        bins = np.linspace(0.05, 0.95, 7)
        mean, sd = compute_static_bva_line(bins, n_photons, n_samples=200_000)
    finally:
        np.random.set_state(rng_state)

    assert mean.shape == sd.shape == bins.shape
    np.testing.assert_allclose(mean, bins, atol=0.005)
    np.testing.assert_allclose(sd, np.sqrt(bins * (1.0 - bins) / n_photons), atol=0.005)


def test_static_line_without_photons_returns_zeros():
    """A non-positive slice size yields zeros instead of dividing by zero."""
    bins = np.linspace(0.1, 0.9, 5)
    with np.errstate(all="raise"):
        mean, sd = compute_static_bva_line(bins, number_of_photons_per_slice=0)
    np.testing.assert_array_equal(mean, np.zeros(5))
    np.testing.assert_array_equal(sd, np.zeros(5))


def test_static_line_accepts_a_plain_list():
    """Callers pass grids as lists; the helper coerces them."""
    mean, sd = compute_static_bva_line([0.2, 0.5, 0.8], 5, n_samples=1000)
    assert mean.shape == (3,)
    assert sd.shape == (3,)
