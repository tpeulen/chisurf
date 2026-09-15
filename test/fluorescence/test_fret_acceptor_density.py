"""FRET to an acceptor density, checked against things it cannot get wrong.

The three decay laws differ only in one exponent — a sixth, a third, a half —
and in a gamma-function prefactor, which makes them easy to transcribe wrongly
in a way no smoke test would notice. These tests pin the exponent and the
prefactor separately, and pin the efficiency against an independent quadrature
rather than against the value the implementation happens to produce.

One number here disagrees with the standard reference. Lakowicz quotes 72 %,
66 % and 63 % for the transfer efficiency at ``C = C0`` in three, two and one
dimensions. The three-dimensional value reproduces; the other two do not — the
same integral, evaluated by SciPy's adaptive quadrature and by a dense
trapezoid rule, gives 67.2 % and 64.2 %. The constants are not in question
(they are exact gamma values, asserted below), so the discrepancy is in the
book's rounding, and the computed values are what the documentation quotes.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from chisurf.core.fluorescence.fret.acceptor_density import (
    characteristic_density,
    donor_decay,
    reduced_density,
    transfer_efficiency,
)

#: Efficiency at C = C0, computed independently with scipy.integrate.quad over
#: [0, inf) and confirmed with a dense trapezoid rule out to 400 tau.
EFFICIENCY_AT_C0 = {3: 0.72381, 2: 0.67222, 1: 0.64159}


@pytest.mark.parametrize("dimension", [1, 2, 3])
def test_zero_acceptor_density_is_the_unquenched_decay(dimension):
    """With no acceptors the law must collapse to a single exponential.

    This is the check that catches a wrong prefactor: any error in the gamma
    term survives here only if it multiplies a density that is zero.
    """
    t = np.linspace(0.0, 20.0, 512)
    got = donor_decay(t, tau_d0=4.0, c_over_c0=0.0, dimension=dimension)
    np.testing.assert_allclose(got, np.exp(-t / 4.0), rtol=0, atol=1e-12)


@pytest.mark.parametrize(
    "dimension, expected",
    [(3, math.sqrt(math.pi) / 2), (2, math.gamma(2 / 3) / 2), (1, math.gamma(5 / 6) / 2)],
)
def test_the_reduced_density_is_a_half_gamma(dimension, expected):
    """gamma, beta and delta of the literature, at C = C0."""
    assert reduced_density(1.0, dimension) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("dimension", [1, 2, 3])
def test_the_reduced_density_is_linear_in_concentration(dimension):
    """Doubling the acceptor density doubles the reduced density, exactly."""
    assert reduced_density(2.4, dimension) == pytest.approx(
        2.4 * reduced_density(1.0, dimension), rel=1e-12
    )


@pytest.mark.parametrize(
    "dimension, volume",
    [(3, 4 / 3 * math.pi * 50.0**3), (2, math.pi * 50.0**2), (1, 2 * 50.0)],
)
def test_the_characteristic_density_is_one_acceptor_per_forster_volume(dimension, volume):
    """C0 is defined so that C/C0 counts acceptors within R0."""
    assert characteristic_density(50.0, dimension) == pytest.approx(1.0 / volume, rel=1e-12)


@pytest.mark.parametrize("dimension", [1, 2, 3])
def test_the_stretch_exponent_is_d_over_six(dimension):
    """Recover the exponent from the decay itself, not from the source.

    Taking ``-ln(I) - t/tau`` isolates the stretched term; its slope against
    ``ln t`` in log-log is the exponent. A transposed 1/3 and 1/2 — the easiest
    possible mistake here — fails this and nothing else.
    """
    tau = 4.0
    t = np.geomspace(1e-4 * tau, 1e-2 * tau, 64)
    decay = donor_decay(t, tau_d0=tau, c_over_c0=0.7, dimension=dimension)
    stretched = -np.log(decay) - t / tau
    slope = np.polyfit(np.log(t), np.log(stretched), 1)[0]
    assert slope == pytest.approx(dimension / 6.0, abs=1e-3)


@pytest.mark.parametrize("dimension", [1, 2, 3])
def test_transfer_efficiency_at_the_characteristic_density(dimension):
    """The efficiency at C = C0, against an independent integration."""
    assert transfer_efficiency(1.0, dimension) == pytest.approx(
        EFFICIENCY_AT_C0[dimension], abs=1e-3
    )


def test_lower_dimensionality_transfers_less_at_the_same_reduced_density():
    """Fewer directions to approach from, less transfer -- 3 > 2 > 1.

    The ordering is the physical content of the comparison and must not depend
    on the quadrature settings.
    """
    e3, e2, e1 = (transfer_efficiency(1.0, d) for d in (3, 2, 1))
    assert e3 > e2 > e1


@pytest.mark.parametrize("dimension", [1, 2, 3])
def test_efficiency_is_monotonic_in_acceptor_density(dimension):
    """More acceptors, more transfer, saturating at one."""
    densities = [0.0, 0.25, 1.0, 4.0, 16.0]
    efficiencies = [transfer_efficiency(c, dimension) for c in densities]
    assert efficiencies[0] == pytest.approx(0.0, abs=1e-9)
    assert all(b > a for a, b in zip(efficiencies, efficiencies[1:]))
    assert efficiencies[-1] < 1.0


@pytest.mark.parametrize("dimension", [1, 2, 3])
def test_the_efficiency_quadrature_has_converged(dimension):
    """The integrand has an infinite derivative at zero -- prove it is resolved.

    Without this the default sampling could be silently too coarse for the
    one-dimensional case, whose integrand is the steepest.
    """
    coarse = transfer_efficiency(1.0, dimension)
    fine = transfer_efficiency(1.0, dimension, n_points=2_000_001, t_max_tau=400.0)
    assert coarse == pytest.approx(fine, abs=2e-4)


@pytest.mark.parametrize("bad", [0, 4, -1, 2.5])
def test_an_unsupported_dimension_raises(bad):
    """Only 1, 2 and 3 have a closed-form law; anything else is a caller bug."""
    with pytest.raises(ValueError, match="dimension must be"):
        reduced_density(1.0, bad)


def test_negative_time_raises():
    """A decay is not defined before the pulse, and t**(1/6) would be complex."""
    with pytest.raises(ValueError, match="non-negative"):
        donor_decay(np.array([-1.0, 0.0]), tau_d0=4.0, c_over_c0=1.0, dimension=2)


def test_non_positive_lifetime_raises():
    with pytest.raises(ValueError, match="tau_d0 must be positive"):
        donor_decay(np.array([0.0, 1.0]), tau_d0=0.0, c_over_c0=1.0, dimension=3)
