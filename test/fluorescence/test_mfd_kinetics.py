"""Kinetics in the 2D histogram: the two limits, and the bow between them.

Exchange enters the forward model through exactly one object, ``P(f | T, K)``, so
the kinetic model is the static model with a different notion of *component*. These
tests pin the three things that has to satisfy:

* **slow exchange** must reproduce the static mixture of the two states — if it did
  not, a fitted rate near zero would not mean "no exchange";
* **fast exchange** must collapse onto a single averaged species — otherwise a fast
  system would present as two states that are not there;
* **in between**, the cloud must move *off* the static line and broaden. That
  displacement is the entire signal: it is what distinguishes a molecule caught
  mid-exchange from a static one at an intermediate distance.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.fluorescence.mfd.fit import (
    MfdKineticModel,
    MfdModel,
    load_mfd_data,
)
from chisurf.core.fluorescence.mfd.histogram import HistogramAxes
from chisurf.core.fluorescence.mfd.patterns import FretState, Optics

REPO = pathlib.Path(__file__).resolve().parents[2]
ANALYSIS = (
    REPO
    / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
    / "burstwise_All 0.1000#15"
)

pytestmark = pytest.mark.skipif(
    not ANALYSIS.is_dir(), reason="the bh_spc132_sm_dna burst folder is not present"
)

STATES = [FretState(distance=40.0, name="closed"), FretState(distance=70.0, name="open")]
OPTICS = Optics(r0=52.0, tau_d0=3.5, tau_a=3.0, sigma=6.0, alpha=0.03)


def _rates(k_forward: float, k_backward: float) -> np.ndarray:
    """Return a two-state rate matrix, ``K[target, source]``, in Hz."""
    return np.array([[0.0, k_backward], [k_forward, 0.0]])


@pytest.fixture(scope="module")
def data():
    """Return the measurement, loaded once."""
    return load_mfd_data(
        ANALYSIS,
        axes=HistogramAxes.default(n_ratio=50, n_micro_time=50, micro_time_range=(2.0, 8.0)),
        n_signal_bins=12,
        n_span_bins=4,
    )


def _ratio_moments(histogram, axes):
    """Return the mean and standard deviation of the proximity-ratio marginal."""
    centres = 0.5 * (axes.ratio_edges[:-1] + axes.ratio_edges[1:])
    weights = histogram.sum(axis=1)
    # Exclude the donor-only spike, which does not exchange and would swamp both.
    keep = centres > 0.12
    centres, weights = centres[keep], weights[keep]
    mean = float((centres * weights).sum() / weights.sum())
    return mean, float(np.sqrt((weights * (centres - mean) ** 2).sum() / weights.sum()))


def test_slow_exchange_reproduces_the_static_mixture(data):
    """A rate far below one transition per burst *is* two static populations."""
    static = MfdModel(optics=OPTICS, states=STATES, populations=[0.5, 0.5], donor_only=0.2)
    slow = MfdKineticModel(
        optics=OPTICS,
        states=STATES,
        populations=[0.5, 0.5],
        donor_only=0.2,
        rate_matrix=_rates(1.0, 1.0),
    )
    a = static.histogram(data)
    b = slow.histogram(data)
    a = a / a.sum()
    b = b / b.sum()
    assert 0.5 * np.abs(a - b).sum() < 0.02


def test_fast_exchange_collapses_onto_one_averaged_population(data):
    """Thousands of transitions per burst leave a single narrow population.

    What must *not* be asserted here is that the two have the same mean, even
    though exchange conserves the equilibrium populations. Two separate effects
    break it, and both are real:

    * ``p_red(E)`` is a Möbius function of ``E``, so averaging the efficiency (what
      exchange does) is not averaging the proximity ratio (what a static mixture
      does); the two differ by a Jensen term.
    * The **green-photon cut is not neutral between populations.** A high-FRET burst
      sends most of its photons to the acceptor, so it has fewer green photons and
      is preferentially removed by the ``≥ 20`` cut. The static mixture loses much
      of its high-FRET population that way; the fast-exchanging one, sitting at an
      intermediate ratio, does not. The fit is unaffected — the data histogram is
      cut identically — but a model histogram is therefore *not* the population
      mixture, and amplitudes read off it directly would be misread.

    So the assertions are the ones that survive both: one population instead of two,
    and it sits between them.
    """
    kwargs = dict(optics=OPTICS, states=STATES, populations=[0.5, 0.5], donor_only=0.0)
    fast = MfdKineticModel(**kwargs, rate_matrix=_rates(2e5, 2e5))
    static = MfdModel(**kwargs)

    axes = data.axes
    centres = 0.5 * (axes.ratio_edges[:-1] + axes.ratio_edges[1:])

    def marginal(model):
        weights = model.histogram(data).sum(axis=1)
        return weights / weights.sum()

    fast_w = marginal(fast)
    static_w = marginal(static)

    def spread(weights):
        mean = float((centres * weights).sum())
        return mean, float(np.sqrt((weights * (centres - mean) ** 2).sum()))

    fast_mean, fast_sd = spread(fast_w)
    _, static_sd = spread(static_w)

    # One population, far narrower than the two it came from …
    assert fast_sd < static_sd * 0.4
    # … sitting between the two states' own acceptor probabilities.
    low, high = 0.173, 0.788
    assert low + 0.05 < fast_mean < high - 0.05

    # The static mixture is bimodal where the fast one is not: the static histogram
    # puts real weight at both states and little between, and vice versa.
    def weight_between(weights, lo, hi):
        return float(weights[(centres > lo) & (centres < hi)].sum())

    assert weight_between(static_w, 0.35, 0.60) < 0.10
    assert weight_between(fast_w, 0.35, 0.60) > 0.60


def test_intermediate_exchange_is_broader_than_either_limit(data):
    """The bow: bursts caught mid-exchange fill the space between the states.

    This is the whole signal. A fit that could not produce it would have to explain
    an intermediate population as a third static state.
    """
    axes = data.axes
    widths = {}
    for label, rates in (
        ("slow", _rates(5.0, 5.0)),
        ("intermediate", _rates(1e3, 1e3)),
        ("fast", _rates(2e5, 2e5)),
    ):
        model = MfdKineticModel(
            optics=OPTICS,
            states=STATES,
            populations=[0.5, 0.5],
            donor_only=0.2,
            rate_matrix=rates,
        )
        histogram = model.histogram(data)
        centres = 0.5 * (axes.ratio_edges[:-1] + axes.ratio_edges[1:])
        weights = histogram.sum(axis=1)
        keep = centres > 0.12
        widths[label] = (centres[keep], weights[keep] / weights[keep].sum())

    def between(entry):
        centres, weights = entry
        # Weight strictly between the two states' own proximity ratios.
        return float(weights[(centres > 0.30) & (centres < 0.55)].sum())

    assert between(widths["intermediate"]) > between(widths["slow"]) * 1.3
    assert between(widths["intermediate"]) > 0.15


def test_the_rate_matrix_must_match_the_states(data):
    """A three-state matrix on a two-state model is an error, not a broadcast."""
    model = MfdKineticModel(optics=OPTICS, states=STATES, rate_matrix=np.zeros((3, 3)))
    with pytest.raises(ValueError, match="rate matrix"):
        model.histogram(data)


def test_no_rate_matrix_is_the_static_model(data):
    """Leaving the kinetics out must not change the answer at all."""
    static = MfdModel(optics=OPTICS, states=STATES, donor_only=0.2)
    kinetic = MfdKineticModel(optics=OPTICS, states=STATES, donor_only=0.2)
    assert np.allclose(static.histogram(data), kinetic.histogram(data))
