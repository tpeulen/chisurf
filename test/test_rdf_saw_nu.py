"""Tests for the SAW-ν polymer distance distribution in rdf.saw_nu."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.math.functions import rdf


def _moments(r, p):
    area = np.trapezoid(p, r)
    rms = np.sqrt(np.trapezoid(r * r * p, r) / area)
    return area, rms


def test_normalised_and_rms_recovered():
    r = np.linspace(1e-3, 300.0, 4000)
    p = rdf.saw_nu(r, r_rms=55.0, nu=0.588)
    area, rms = _moments(r, p)
    assert abs(area - 1.0) < 1e-3
    assert abs(rms - 55.0) / 55.0 < 0.02


def test_reduces_to_gaussian_chain_at_theta():
    """nu=0.5, gamma=1 reproduces the Gaussian-chain RDF of the same RMS."""
    r = np.linspace(1e-3, 300.0, 4000)
    r_rms = 55.0
    p_saw = rdf.saw_nu(r, r_rms, nu=0.5, gamma_exp=1.0)
    # Gaussian chain with matching <r^2>: segment_length*sqrt(N) = r_rms.
    n_seg = 100
    b = r_rms / np.sqrt(n_seg)
    p_gauss = rdf.gaussian_chain(r, b, n_seg)
    p_gauss = p_gauss / np.trapezoid(p_gauss, r)
    np.testing.assert_allclose(p_saw, p_gauss, atol=2e-4)


def test_expanded_chain_peaks_further_out():
    r = np.linspace(1e-3, 400.0, 6000)
    p_theta = rdf.saw_nu(r, 60.0, nu=0.5)
    p_exp = rdf.saw_nu(r, 60.0, nu=0.7)
    assert r[np.argmax(p_exp)] > r[np.argmax(p_theta)]


def test_invalid_inputs_return_zero():
    r = np.linspace(1e-3, 100.0, 100)
    assert np.all(rdf.saw_nu(r, 50.0, nu=1.5) == 0)
    assert np.all(rdf.saw_nu(r, -1.0, nu=0.5) == 0)
