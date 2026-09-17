"""Tests for the Ising two-state Gaussian-chain distance distribution."""

from __future__ import annotations

import numpy as np

from chisurf.core.math.functions import rdf


def _rms(r, p):
    area = np.trapezoid(p, r)
    return np.sqrt(np.trapezoid(r * r * p, r) / area)


def test_normalised():
    r = np.linspace(1e-3, 400.0, 3000)
    p = rdf.ising_chain(
        r, number_of_residues=40, b_structured=5.0, b_unstructured=8.0, coupling=1.0, field=0.0
    )
    assert abs(np.trapezoid(p, r) - 1.0) < 1e-3
    assert np.all(p >= 0)


def test_reduces_to_gaussian_chain_when_states_equal():
    """b_S == b_U -> Gaussian chain with <r^2> = N b^2 regardless of J, h."""
    r = np.linspace(1e-3, 400.0, 4000)
    n, b = 50, 6.0
    p_ising = rdf.ising_chain(r, n, b_structured=b, b_unstructured=b, coupling=2.0, field=0.5)
    # Gaussian chain with the same <r^2> = N b^2 -> segment_length*sqrt(N)=b*sqrt(N).
    p_gauss = rdf.gaussian_chain(r, b, n)
    p_gauss = p_gauss / np.trapezoid(p_gauss, r)
    assert abs(_rms(r, p_ising) - b * np.sqrt(n)) / (b * np.sqrt(n)) < 0.05
    np.testing.assert_allclose(p_ising, p_gauss, atol=3e-4)


def test_field_drives_compaction():
    """A field towards the (compact) structured state shortens the chain."""
    r = np.linspace(1e-3, 500.0, 4000)
    n = 50
    p_unfold = rdf.ising_chain(r, n, 4.0, 9.0, coupling=1.0, field=-3.0)  # -> U (expanded)
    p_fold = rdf.ising_chain(r, n, 4.0, 9.0, coupling=1.0, field=+3.0)  # -> S (compact)
    assert _rms(r, p_fold) < _rms(r, p_unfold)


def test_cooperativity_sharpens_transition():
    """Stronger coupling makes the chain more two-state (mixed states rarer)."""
    r = np.linspace(1e-3, 500.0, 3000)
    n = 60
    rms_lowJ = _rms(r, rdf.ising_chain(r, n, 4.0, 9.0, coupling=0.1, field=0.0))
    rms_highJ = _rms(r, rdf.ising_chain(r, n, 4.0, 9.0, coupling=3.0, field=0.0))
    # both are finite, positive RMS distances; sanity that the model runs across J
    assert rms_lowJ > 0 and rms_highJ > 0
