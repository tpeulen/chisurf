"""The occupation-time law behind dynamic PDA (PRD-50 / PRD-65).

A molecule that switches conformation during a burst spends a random *fraction*
of the observation window in each state, and dynamic PDA averages over that
fraction. Getting its distribution wrong biases every dynamic fit, so this is
checked against two independent references: the law's own defining moments, and
a direct simulation of the telegraph process.

These tests also record a defect in the closed-form density that predates them.
"""

from __future__ import annotations

import numpy as np
import pytest

POPULATIONS = (0.2, 0.3, 0.5, 0.7, 0.8)
EXCHANGE = (0.0, 0.5, 2.0, 8.0, 50.0)


def _simulate(p1, k_ex, n=60000, seed=1):
    """Directly simulate the time fraction spent in state 1, stationary start."""
    rng = np.random.default_rng(seed)
    p2 = 1.0 - p1
    k1, k2 = k_ex * p2, k_ex * p1
    out = np.empty(n)
    for i in range(n):
        state = 1 if rng.random() < p1 else 2
        elapsed, in_one = 0.0, 0.0
        while elapsed < 1.0:
            rate = k1 if state == 1 else k2
            dwell = rng.exponential(1.0 / rate) if rate > 0 else np.inf
            step = min(dwell, 1.0 - elapsed)
            if state == 1:
                in_one += step
            elapsed += step
            state = 3 - state
        out[i] = in_one
    return out


# ── the exact law ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("p1", POPULATIONS)
@pytest.mark.parametrize("k_ex", EXCHANGE)
def test_the_quadrature_is_a_distribution_with_the_right_mean(p1, k_ex):
    """Two properties that hold for every two-state process, by definition.

    It must be a probability distribution, and the expected time fraction must
    equal the steady-state occupancy — the process is stationary, so it spends
    ``p1`` of its time in state 1 whatever the exchange rate.
    """
    from chisurf.core.models.pda.dynamic import two_state_occupation_quadrature

    fractions, weights = two_state_occupation_quadrature(p1, k_ex)
    assert np.all(weights >= 0.0)
    assert weights.sum() == pytest.approx(1.0, abs=1e-9)
    assert float(weights @ fractions) == pytest.approx(p1, abs=1e-3)


@pytest.mark.parametrize("k_ex", (0.0, 1e-6))
def test_the_static_limit_puts_everything_on_the_boundaries(k_ex):
    """No exchange means every molecule stayed put for the whole window."""
    from chisurf.core.models.pda.dynamic import two_state_occupation_quadrature

    fractions, weights = two_state_occupation_quadrature(0.3, k_ex)
    boundary = weights[0] + weights[-1]
    assert boundary == pytest.approx(1.0, abs=1e-5)
    assert fractions[0] == 0.0 and fractions[-1] == 1.0
    assert weights[-1] == pytest.approx(0.3, abs=1e-5)  # the state-1 population


def test_fast_exchange_collapses_onto_the_mean():
    """Many switches per window average the two states out."""
    from chisurf.core.models.pda.dynamic import two_state_occupation_quadrature

    fractions, weights = two_state_occupation_quadrature(0.3, 200.0)
    spread = np.sqrt(weights @ (fractions - 0.3) ** 2)
    assert spread < 0.06, spread
    assert weights[0] + weights[-1] < 1e-6  # no molecule survives without switching


@pytest.mark.slow
@pytest.mark.parametrize("p1, k_ex", [(0.3, 2.0), (0.8, 5.0), (0.5, 1.0)])
def test_the_quadrature_reproduces_a_direct_simulation(p1, k_ex):
    """The independent check: simulate the process and compare distributions."""
    from chisurf.core.models.pda.dynamic import two_state_occupation_quadrature

    fractions, weights = two_state_occupation_quadrature(p1, k_ex)
    sample = _simulate(p1, k_ex)

    edges = np.linspace(0.0, 1.0, 11)
    simulated, _ = np.histogram(sample, bins=edges)
    simulated = simulated / sample.size
    binned = np.bincount(
        np.clip(np.digitize(fractions, edges) - 1, 0, 9), weights=weights, minlength=10
    )
    total_variation = 0.5 * np.abs(binned - simulated).sum()
    assert total_variation < 0.02, total_variation


# ── the defect in the closed form ──────────────────────────────────────────


def test_the_closed_form_density_is_wrong_away_from_equal_populations():
    """Regression record for a defect in ``two_state_time_fraction_pdf``.

    Combined with the standard boundary masses it is not a probability
    distribution: the total exceeds one by up to a third at strongly unequal
    populations, and its shape disagrees with a direct simulation. It *is*
    correct at ``p1 = 0.5``, which is why it went unnoticed — the dynamic
    two-state acceptance test in PRD-50 recovered ``x1 = 0.503``, essentially
    the one population where the error vanishes.

    This test asserts the defect rather than the fix, so it fails loudly if the
    closed form is ever corrected and this note becomes stale. New code should
    use :func:`two_state_occupation_quadrature`.
    """
    from chisurf.core.models.pda.dynamic import two_state_time_fraction_pdf

    nodes, quad_weights = np.polynomial.legendre.leggauss(2000)
    fractions = 0.5 * (nodes + 1.0)
    weights = 0.5 * quad_weights

    def total_mass(p1, k_ex):
        p2 = 1.0 - p1
        a, b = k_ex * p2, k_ex * p1
        interior = float(two_state_time_fraction_pdf(fractions, p1, k_ex) @ weights)
        return interior + p1 * np.exp(-a) + p2 * np.exp(-b)

    # Exact where the populations are equal ...
    assert total_mass(0.5, 2.0) == pytest.approx(1.0, abs=1e-6)
    # ... and demonstrably not a distribution otherwise.
    assert total_mass(0.3, 2.0) > 1.10
    assert total_mass(0.2, 8.0) > 1.10
