"""The rate-vectorised PDDEM spectrum against the per-rate loop it replaced.

`PDDEMModel.lifetime_spectrum` used to call the pair kernel once per rate of
the FRET-rate spectrum — 96 calls per evaluation on the standard distance
axis, each on a (1, 1) pair grid where numpy's per-call overhead dwarfs the
arithmetic. `pddem_rates` is one broadcast over a leading rate axis and must
be **bit-for-bit** the concatenation the loop produced, in the same order —
an order test, not only a value test, because getting the rate-major
interleaving wrong would reorder the spectrum without changing any value.
"""
import numpy as np
import pytest

from chisurf.core.fluorescence.tcspc.tcspc import pddem, pddem_rates


def _reference(decayA, decayB, ks, px, pm, pAB, weights):
    decays = []
    for (kab, kba), w in zip(ks, weights):
        tmp = pddem(decayA, decayB, np.array([kab, kba]), px, pm, pAB)
        tmp[0::2] *= w
        decays.append(tmp)
    return np.concatenate(decays)


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("n_a,n_b", [(1, 1), (2, 3), (3, 1)])
def test_pddem_rates_matches_the_per_rate_loop(seed, n_a, n_b):
    rng = np.random.default_rng(seed)
    decayA = np.empty(2 * n_a)
    decayA[0::2] = rng.uniform(0.1, 1.0, n_a)
    decayA[1::2] = rng.uniform(0.5, 5.0, n_a)
    decayB = np.empty(2 * n_b)
    decayB[0::2] = rng.uniform(0.1, 1.0, n_b)
    decayB[1::2] = rng.uniform(0.5, 5.0, n_b)
    rates = rng.uniform(0.01, 10.0, 17)
    fABBA = np.array([1.0, 0.3])
    ks = rates[:, None] * fABBA[None, :]
    px = np.array([0.6, 0.4])
    pm = np.array([0.7, 0.3])
    pAB = np.array([0.2, 0.1])
    weights = rng.uniform(0.0, 1.0, rates.size)

    want = _reference(decayA, decayB, ks, px, pm, pAB, weights)
    got = pddem_rates(decayA, decayB, ks, px, pm, pAB, weights)
    np.testing.assert_array_equal(got, want)


def test_zero_amplitude_and_zero_lifetime_pairs_are_skipped_identically():
    """The keep semantics — a zero amplitude or lifetime drops the pair, both
    branches — must survive the vectorisation, including the ragged per-rate
    lengths they produce."""
    decayA = np.array([0.5, 2.0, 0.0, 1.0, 0.4, 0.0])   # one zero c, one zero tau
    decayB = np.array([0.8, 3.0, 0.2, 1.5])
    ks = np.array([[0.5, 0.15], [5.0, 1.5]])
    px = np.array([0.5, 0.5])
    pm = np.array([0.5, 0.5])
    pAB = np.array([0.3, 0.2])
    weights = np.array([0.7, 0.3])
    want = _reference(decayA, decayB, ks, px, pm, pAB, weights)
    got = pddem_rates(decayA, decayB, ks, px, pm, pAB, weights)
    np.testing.assert_array_equal(got, want)
