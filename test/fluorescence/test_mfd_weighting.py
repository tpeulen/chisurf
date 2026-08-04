"""Which mixture the donor photons of an exchanging burst are drawn from.

The cheapest test in the MFD suite and the one that would have caught the
longest-lived error in it: no simulation, no ground truth, no fitting — just the
conditioning argument, checked against a burst built photon by photon.

The error it guards is invisible to every other test in the tree, because the
histogram source and the burst-wise source shared it. Two sources agreeing is
what confirmation looks like right up until they are wrong the same way.
"""
import numpy as np
import pytest

from chisurf.core.fluorescence.mfd.fit import donor_weights
from chisurf.core.fluorescence.mfd.moments import mixture_moments


#: A burst that spent half its transit in each of a low- and a high-FRET state.
FRACTIONS = np.array([[0.5, 0.5]])
#: Acceptor-channel probabilities of those states: E = 0.2 and 0.8, no corrections.
P_RED = np.array([0.2, 0.8])
#: Their donor-channel mean delays and variances (ns, ns^2).
MEAN = np.array([3.2, 0.8])
VARIANCE = np.array([3.2 ** 2, 0.8 ** 2])


def test_the_channel_counts_are_the_occupancy_mixture():
    """``f·p`` is exact for the acceptor probability — this half was never wrong.

    Each photon picks a state with probability ``f`` and is then red with that
    state's probability, so marginally it is red with probability ``f·p``
    independently of every other photon. Thinning a multinomial gives a binomial.
    """
    rng = np.random.default_rng(4)
    n_photons, n_bursts = 60, 200_000
    state = rng.random((n_bursts, n_photons)) < FRACTIONS[0, 0]
    p = np.where(state, P_RED[0], P_RED[1])
    sampled = (rng.random((n_bursts, n_photons)) < p).sum(axis=1)

    expected = float(FRACTIONS[0] @ P_RED)
    assert sampled.mean() / n_photons == pytest.approx(expected, abs=0.002)
    # and the spread is binomial, not over-dispersed by the state mixing
    assert sampled.var() == pytest.approx(
        n_photons * expected * (1.0 - expected), rel=0.02
    )


def test_the_donor_photons_are_the_green_weighted_mixture():
    """Conditioned on reaching the donor channel, the state is ``g``, not ``f``.

    Built here without either formula: photons pick a state, then a channel, and
    the surviving donor photons are counted. A 50/50 burst of an E=0.2 and an
    E=0.8 state yields **80 %** of its donor photons from the low-FRET state.
    """
    rng = np.random.default_rng(5)
    n = 4_000_000
    low = rng.random(n) < FRACTIONS[0, 0]
    p_red = np.where(low, P_RED[0], P_RED[1])
    green = rng.random(n) >= p_red

    measured = float(np.count_nonzero(low & green) / np.count_nonzero(green))
    expected = float(donor_weights(FRACTIONS, P_RED)[0, 0])

    assert expected == pytest.approx(0.8, abs=1e-12)
    assert measured == pytest.approx(expected, abs=0.001)
    # the occupancy weighting claims half, and is wrong by a factor of 1.6
    assert donor_weights(FRACTIONS, P_RED, mode="occupancy")[0, 0] == 0.5


def test_the_two_weightings_disagree_by_more_than_a_micro_time_bin():
    """The error is systematic and coarser than the histogram's own resolution.

    Guards the *size* of the effect, not just its sign: a fix that changed the
    weighting but not the answer would pass the test above and fail this one.
    """
    green, _ = mixture_moments(
        donor_weights(FRACTIONS, P_RED), MEAN[None, :], VARIANCE[None, :]
    )
    occupancy, _ = mixture_moments(
        donor_weights(FRACTIONS, P_RED, mode="occupancy"),
        MEAN[None, :], VARIANCE[None, :],
    )

    # 0.8*3.2 + 0.2*0.8 = 2.72 ns against the naive 0.5*3.2 + 0.5*0.8 = 2.00 ns.
    assert float(green[0]) == pytest.approx(2.72, abs=1e-9)
    assert float(occupancy[0]) == pytest.approx(2.00, abs=1e-9)
    # the default micro-time axis is 41 bins over 0-8 ns, i.e. 0.195 ns
    assert float(green[0] - occupancy[0]) > 3.0 * (8.0 / 41.0)


def test_the_donor_photon_mean_matches_a_photon_by_photon_burst():
    """End to end on the quantity the histogram actually plots: ⟨t⟩ of the greens."""
    rng = np.random.default_rng(6)
    n = 2_000_000
    low = rng.random(n) < FRACTIONS[0, 0]
    green = rng.random(n) >= np.where(low, P_RED[0], P_RED[1])
    # each donor photon's delay is exponential with its own state's lifetime
    delay = rng.exponential(np.where(low, MEAN[0], MEAN[1]))[green]

    predicted, _ = mixture_moments(
        donor_weights(FRACTIONS, P_RED), MEAN[None, :], VARIANCE[None, :]
    )
    assert float(delay.mean()) == pytest.approx(float(predicted[0]), rel=0.005)


@pytest.mark.parametrize("mode", ["green", "occupancy"])
def test_the_weightings_agree_when_the_states_are_equally_bright(mode):
    """No FRET contrast, no distinction — the sanity limit of the whole argument."""
    equal = np.array([0.4, 0.4])
    weights = donor_weights(FRACTIONS, equal, mode=mode)
    assert weights[0] == pytest.approx(FRACTIONS[0])


def test_an_all_acceptor_node_falls_back_rather_than_dividing_by_zero():
    """A burst with no donor photons is cut later; the weight only has to be finite."""
    weights = donor_weights(FRACTIONS, np.array([1.0, 1.0]))
    assert np.all(np.isfinite(weights))
    assert weights[0] == pytest.approx(FRACTIONS[0])


def test_an_unknown_mode_is_refused():
    """A typo must not silently select a weighting."""
    with pytest.raises(ValueError, match="green.*occupancy"):
        donor_weights(FRACTIONS, P_RED, mode="occupanct")
