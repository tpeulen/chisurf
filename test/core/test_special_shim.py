"""chisurf.core.math.special against scipy, the oracle it replaces.

bff's own tests hold the kernels to scipy; these hold the shim's part --
broadcasting, scalar in/scalar out, and the entries written in numpy here
(logsumexp, xlogy, polygamma, poisson.logpmf, pinvh) -- to scipy's answers.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.math import special as sp

scipy = pytest.importorskip("scipy")
from scipy import linalg, special, stats  # noqa: E402

RNG = np.random.default_rng(7)


def test_scalar_in_scalar_out_and_shapes_kept():
    assert isinstance(sp.erf(0.3), float)
    assert sp.erf(0.3) == special.erf(0.3)
    x = RNG.normal(size=(3, 4))
    assert sp.gammaln(np.abs(x) + 1).shape == (3, 4)
    a = RNG.uniform(0.5, 4, (3, 1))
    np.testing.assert_array_equal(sp.gammainc(a, np.abs(x)), special.gammainc(a, np.abs(x)))


def test_polygamma_matches_scipy():
    x = RNG.uniform(0.1, 30, 500)
    for n in (0, 1, 2, 3):
        np.testing.assert_allclose(sp.polygamma(n, x), special.polygamma(n, x), rtol=1e-14)


@pytest.mark.parametrize("axis", [None, 0, 1])
def test_logsumexp_matches_scipy(axis):
    a = RNG.normal(size=(5, 7)) * 50
    a[0, 0] = -np.inf
    b = RNG.uniform(0, 2, (5, 7))
    b[1, :] = 0.0
    np.testing.assert_allclose(sp.logsumexp(a, axis=axis), special.logsumexp(a, axis=axis), rtol=1e-15)
    np.testing.assert_allclose(
        sp.logsumexp(a, axis=axis, b=b), special.logsumexp(a, axis=axis, b=b), rtol=1e-14
    )
    allneg = np.full((3, 4), -np.inf)
    np.testing.assert_array_equal(sp.logsumexp(allneg, axis=axis), special.logsumexp(allneg, axis=axis))


def test_xlogy_zero_times_log_zero_is_zero():
    x = np.array([0.0, 0.0, 1.0, 2.0])
    y = np.array([0.0, 3.0, 0.0, 5.0])
    np.testing.assert_array_equal(sp.xlogy(x, y), special.xlogy(x, y))


def test_distributions_match_scipy():
    x = RNG.normal(size=200)
    np.testing.assert_allclose(sp.norm.cdf(x, 0.5, 2.0), stats.norm.cdf(x, 0.5, 2.0), rtol=1e-15)
    np.testing.assert_allclose(sp.norm.pdf(x, 0.5, 2.0), stats.norm.pdf(x, 0.5, 2.0), rtol=1e-14)
    q = RNG.uniform(0.01, 0.99, 200)
    np.testing.assert_allclose(sp.beta.ppf(q, 2.5, 0.7), stats.beta.ppf(q, 2.5, 0.7), rtol=1e-12)
    np.testing.assert_allclose(sp.f.isf(q, 3, 20), stats.f.isf(q, 3, 20), rtol=1e-12)
    np.testing.assert_allclose(sp.f.cdf(x**2, 3, 20), stats.f.cdf(x**2, 3, 20), rtol=1e-12)
    np.testing.assert_allclose(sp.chi2.isf(q, 4), stats.chi2.isf(q, 4), rtol=1e-15)
    np.testing.assert_allclose(sp.t.sf(np.abs(x), 7.0), stats.t.sf(np.abs(x), 7.0), rtol=1e-12)
    k = np.arange(41)[None, :]
    p = RNG.uniform(0, 1, 6)[:, None]
    np.testing.assert_allclose(sp.binom.pmf(k, 40, p), stats.binom.pmf(k, 40, p), rtol=1e-12, atol=1e-300)
    kk = RNG.integers(0, 60, 300)
    mu = RNG.uniform(0.1, 40, 300)
    np.testing.assert_allclose(sp.poisson.logpmf(kk, mu), stats.poisson.logpmf(kk, mu), rtol=1e-13)
    assert sp.poisson.logpmf(-1, 3.0) == -np.inf
    xx = RNG.uniform(0, 80, 300)
    np.testing.assert_allclose(sp.ncx2.pdf(xx, 3, 12.0), stats.ncx2.pdf(xx, 3, 12.0), rtol=1e-12)


def test_fresnel_and_bessel():
    z = RNG.uniform(-10, 10, 300)
    s, c = sp.fresnel(z)
    ss, cc = special.fresnel(z)
    np.testing.assert_array_equal(s, ss)
    np.testing.assert_array_equal(c, cc)
    np.testing.assert_array_equal(sp.i0e(z * 50), special.i0e(z * 50))
    np.testing.assert_array_equal(sp.j0(z), special.j0(z))


def test_linalg():
    a = RNG.normal(size=(6, 6))
    np.testing.assert_allclose(sp.expm(a), linalg.expm(a), rtol=1e-11)
    m = RNG.normal(size=(6, 4))
    h = m @ m.T  # rank 4, symmetric
    np.testing.assert_allclose(sp.pinvh(h), linalg.pinvh(h), rtol=1e-8, atol=1e-12)
    _, rank = sp.pinvh(h, return_rank=True)
    assert rank == linalg.pinvh(h, return_rank=True)[1] == 4


def test_rankdata_average_ties_matches_scipy():
    for _ in range(50):
        a = RNG.integers(0, 6, RNG.integers(1, 40)).astype(float)
        np.testing.assert_array_equal(sp.rankdata(a), stats.rankdata(a))
