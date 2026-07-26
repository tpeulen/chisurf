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
EXCHANGE = (0.0, 0.5, 2.0, 8.0, 50.0, 5000.0)  # incl. fast exchange, where a
# naive exp(mu)*cosh(delta) overflows to nan


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
    from chisurf.core.models.pda2c.dynamic import two_state_occupation_quadrature

    fractions, weights = two_state_occupation_quadrature(p1, k_ex)
    assert np.all(weights >= 0.0)
    assert weights.sum() == pytest.approx(1.0, abs=1e-9)
    assert float(weights @ fractions) == pytest.approx(p1, abs=1e-3)


@pytest.mark.parametrize("k_ex", (0.0, 1e-6))
def test_the_static_limit_puts_everything_on_the_boundaries(k_ex):
    """No exchange means every molecule stayed put for the whole window."""
    from chisurf.core.models.pda2c.dynamic import two_state_occupation_quadrature

    fractions, weights = two_state_occupation_quadrature(0.3, k_ex)
    boundary = weights[0] + weights[-1]
    assert boundary == pytest.approx(1.0, abs=1e-5)
    assert fractions[0] == 0.0 and fractions[-1] == 1.0
    assert weights[-1] == pytest.approx(0.3, abs=1e-5)  # the state-1 population


def test_fast_exchange_collapses_onto_the_mean():
    """Many switches per window average the two states out."""
    from chisurf.core.models.pda2c.dynamic import two_state_occupation_quadrature

    fractions, weights = two_state_occupation_quadrature(0.3, 200.0)
    spread = np.sqrt(weights @ (fractions - 0.3) ** 2)
    assert spread < 0.06, spread
    assert weights[0] + weights[-1] < 1e-6  # no molecule survives without switching


@pytest.mark.slow
@pytest.mark.parametrize("p1, k_ex", [(0.3, 2.0), (0.8, 5.0), (0.5, 1.0)])
def test_the_quadrature_reproduces_a_direct_simulation(p1, k_ex):
    """The independent check: simulate the process and compare distributions."""
    from chisurf.core.models.pda2c.dynamic import two_state_occupation_quadrature

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


# ── what the old closed form got wrong ────────────────────────────────────


def test_unequal_populations_are_where_the_old_density_failed():
    """Guard on the regime the removed closed form could not describe.

    ``two_state_time_fraction_pdf`` was a probability distribution only at
    ``p1 = 0.5``; away from it the total mass reached 1.36 and the shape was
    tilted. Its error vanished exactly at equal populations, which is why it
    survived an acceptance test that happened to fit ``x1 = 0.503``. This pins
    the property it violated, at the populations where it violated it.
    """
    from chisurf.core.models.pda2c.dynamic import two_state_occupation_quadrature

    for p1 in (0.05, 0.2, 0.35, 0.65, 0.8, 0.95):
        for k_ex in (0.5, 2.0, 8.0):
            fractions, weights = two_state_occupation_quadrature(p1, k_ex)
            assert weights.sum() == pytest.approx(1.0, abs=1e-9), (p1, k_ex)
            assert float(weights @ fractions) == pytest.approx(p1, abs=1e-3), (p1, k_ex)
