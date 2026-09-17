"""Starting values read off the measurement (PRD-71).

A two-state MFD fit has six free numbers over a strongly multi-modal objective, so
the start point decides the answer. The generic defaults put every state at the
*same* distance -- two states that are literally one species, so the optimiser's
first step is rank-deficient -- with ``alpha`` sitting on its lower bound. On a
real measurement that converged to a crosstalk of 0.31, placing the model's
donor-only population at a proximity ratio of 0.24 while the data's sat at 0.012.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.fluorescence.mfd.seed import estimate_starting_values

ANALYSIS = (
    pathlib.Path(__file__).resolve().parents[2]
    / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
    / "burstwise_All 0.1000#15"
)

pytestmark = pytest.mark.skipif(
    not ANALYSIS.is_dir(), reason="the bh_spc132_sm_dna burst folder is not present"
)


@pytest.fixture(scope="module")
def data():
    from chisurf.core.fluorescence.mfd.fit import load_mfd_data

    return load_mfd_data(ANALYSIS)


def test_the_crosstalk_comes_from_where_the_donor_only_population_sits(data):
    """A burst with no acceptor has ``PR = alpha / (1 + alpha)``, up to background."""
    start = estimate_starting_values(data, n_states=2)
    counts = np.asarray(data.observed.counts, dtype=float)
    ratio = 0.5 * (data.axes.ratio_edges[:-1] + data.axes.ratio_edges[1:])
    observed_mode = ratio[counts.sum(axis=1)[: ratio.size // 4].argmax()]
    expected = observed_mode / (1.0 - observed_mode)
    assert start.alpha == pytest.approx(max(expected, 1e-3), abs=0.005)
    # Small, as spectral crosstalk is -- and emphatically not the 0.31 a fit from
    # the generic defaults settled on.
    assert 0.0 < start.alpha < 0.1


def test_the_donor_lifetime_comes_from_the_measured_decay(data):
    """Means add under convolution, so the response's mean subtracts off."""
    start = estimate_starting_values(data, n_states=2)
    offset = start.diagnostics["response_mean_ns"]
    mean_micro = start.diagnostics["donor_only_mean_micro_ns"]
    assert start.tau_d0 == pytest.approx(mean_micro - offset, abs=1e-6)
    assert 0.2 < start.tau_d0 < 8.0


def test_the_states_never_start_on_top_of_each_other(data):
    """Equal distances are one species twice: identical Jacobian columns."""
    for n_states in (2, 3, 4):
        start = estimate_starting_values(data, n_states=n_states)
        assert len(start.distances) == n_states
        gaps = np.diff(sorted(start.distances))
        assert np.all(gaps >= 1.0), f"{n_states} states started degenerate"


def test_nothing_starts_on_a_bound(data):
    """A forward-difference gradient at a bound sees one side only."""
    start = estimate_starting_values(data, n_states=2)
    assert start.alpha > 0.0
    assert 0.0 < start.donor_only < 1.0
    assert all(5.0 < d < 250.0 for d in start.distances)


def test_seeding_moves_a_real_fit_into_a_better_basin(data):
    """The point of the whole exercise, measured as the objective itself."""
    from chisurf.core.fluorescence.mfd.fit import MfdKineticModel
    from chisurf.core.fluorescence.mfd.patterns import FretState, Optics

    def chi2(alpha, tau_d0, donor_only, distances, populations):
        model = MfdKineticModel(
            optics=Optics(
                r0=52.0, tau_d0=tau_d0, tau_a=3.0, alpha=alpha, delta=0.0, gamma=1.0, sigma=6.0
            ),
            states=[FretState(distance=d, name=f"R{i}") for i, d in enumerate(distances, 1)],
            populations=np.asarray(populations, dtype=float),
            donor_only=donor_only,
        )
        predicted = model.histogram(data)
        observed = np.asarray(data.observed.counts, dtype=float)
        scale = observed.sum() / predicted.sum()
        return float(
            np.sum((observed - predicted * scale) ** 2 / np.maximum(predicted * scale, 1.0))
        )

    generic = chi2(0.0, 4.0, 0.2, [50.0, 50.0], [1.0, 1.0])
    start = estimate_starting_values(data, n_states=2)
    seeded = chi2(start.alpha, start.tau_d0, start.donor_only, start.distances, start.populations)
    assert seeded < generic, f"seeded start {seeded:.1f} is no better than {generic:.1f}"


def test_a_state_may_be_more_populated_than_the_reference():
    """The fractions are *relative* weights against a first state held at 1.

    Bounded at 1 they could never exceed the reference, so no state could hold
    more than half the population and a fit that wanted more sat on the bound.
    """
    from chisurf.core.models.mfd.two_dimensional import MfdStates

    states = MfdStates(n_states=2)
    assert states._fractions[0].fixed, "the reference weight must be held"
    assert states._fractions[1].bounds[1] > 1.0
    states._fractions[1].value = 9.0
    assert states.populations[1] == pytest.approx(0.9)
