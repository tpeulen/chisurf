"""Multi-chromophore N-cube correction: reduces to 2-color, recovers 3-color E."""

from __future__ import annotations

import numpy as np
import pytest
from tttrlib import corrected_es, corrected_es_matrix


def test_two_chromophore_reduces_to_2color():
    """For N=2 the matrix correction equals the two-colour corrected_es E."""
    gamma, alpha, delta = 1.4, 0.08, 0.05
    rng = np.random.default_rng(0)
    i_dd = rng.uniform(50, 200, 40)
    i_da = rng.uniform(20, 150, 40)
    i_aa = rng.uniform(50, 200, 40)

    # 2x2 intensity matrix I[i,j]; diagonal = i_dd/i_aa, off = i_da.
    inten = np.array([[i_dd, i_da], [np.zeros_like(i_dd), i_aa]])
    g = np.array([[1.0, gamma], [gamma, 1.0]])
    a = np.array([[0.0, alpha], [alpha, 0.0]])
    d = np.array([[0.0, delta], [delta, 0.0]])

    e_matrix = corrected_es_matrix(inten, g, a, d)[(0, 1)]["E"]
    e_2color = corrected_es(i_dd, i_da, i_aa, gamma=gamma, alpha=alpha, delta=delta)["E"]
    assert np.allclose(e_matrix, e_2color, atol=1e-9)


@pytest.mark.parametrize("e01,e02", [(0.3, 0.4), (0.6, 0.1), (0.2, 0.2)])
def test_three_chromophore_coupled_recovery(e01, e02):
    """Both pairwise efficiencies are recovered when one donor feeds two acceptors."""
    # donor 0 quenched by acceptors 1 and 2; known per-pair gamma/alpha/delta.
    g01, g02 = 1.3, 0.8
    a01, a02 = 0.06, 0.09
    d01, d02 = 0.04, 0.03
    tot = 1000.0

    f_00 = (1 - e01 - e02) * tot
    i_11 = tot
    i_22 = tot
    i_00 = f_00
    i_01 = g01 * e01 * tot + a01 * f_00 + d01 * i_11
    i_02 = g02 * e02 * tot + a02 * f_00 + d02 * i_22

    n = 3
    inten = np.zeros((n, n))
    inten[0, 0], inten[1, 1], inten[2, 2] = i_00, i_11, i_22
    inten[0, 1], inten[0, 2] = i_01, i_02

    gamma = np.ones((n, n))
    gamma[0, 1], gamma[0, 2] = g01, g02
    alpha = np.zeros((n, n))
    alpha[0, 1], alpha[0, 2] = a01, a02
    delta = np.zeros((n, n))
    delta[0, 1], delta[0, 2] = d01, d02

    res = corrected_es_matrix(inten, gamma, alpha, delta, pairs=[(0, 1), (0, 2)])
    assert float(res[(0, 1)]["E"]) == pytest.approx(e01, abs=1e-6)
    assert float(res[(0, 2)]["E"]) == pytest.approx(e02, abs=1e-6)


def test_naive_pairwise_would_be_biased():
    """Sanity: ignoring the coupled donor budget would bias E (documents why)."""
    e01, e02 = 0.4, 0.4
    tot = 1000.0
    f_00 = (1 - e01 - e02) * tot
    g01 = 1.0
    # naive 2-color E for pair (0,1) ignoring acceptor 2: E = Fda/(Fda+g*Fdd)
    f_da = g01 * e01 * tot
    naive = f_da / (f_da + g01 * f_00)
    # the biased value is e01/(1-e02); the coupled matrix result is exact e01
    assert naive == pytest.approx(e01 / (1 - e02), abs=1e-6)
    assert not np.isclose(naive, e01, atol=0.02)
