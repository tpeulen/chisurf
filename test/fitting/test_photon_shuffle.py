"""Integer, statistics-preserving spectral unmixing (photon reassignment).

``photon_shuffle_unmix`` reassigns each detected photon to a source by a
multinomial draw, so — unlike the least-squares inverses — the output is a
non-negative integer per-source photon stream that preserves the total count and
the Poisson shot-noise statistics.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.crosstalk import invert_mixing, photon_shuffle_unmix


def test_shuffle_is_integer_nonneg_and_count_preserving():
    d = np.array([[1.0, 0.1], [0.0, 1.0]])  # donor leaks into red, acceptor clean
    rng = np.random.default_rng(0)
    counts = rng.integers(0, 500, size=(2, 1000))  # (n_det, bursts)
    out = photon_shuffle_unmix(counts, d, seed=1)

    assert out.dtype.kind in "iu"  # integer
    assert np.all(out >= 0)  # non-negative
    assert out.shape == (2, 1000)
    # every detected photon assigned to exactly one source
    assert np.array_equal(out.sum(axis=0), counts.sum(axis=0))


def test_identity_mixing_is_lossless():
    d = np.eye(3)
    rng = np.random.default_rng(2)
    counts = rng.poisson(120, size=(3, 400))
    out = photon_shuffle_unmix(counts, d, seed=3)
    assert np.array_equal(out, counts)  # no crosstalk -> exact pass-through


def test_shuffle_mean_matches_soft_assignment():
    """Averaged over many draws the reassignment equals the soft (EM) unmix."""
    d = np.array([[1.0, 0.1], [0.0, 1.0]])
    counts = np.array([300, 200])  # green, red
    reps = np.repeat(counts[:, None], 20000, axis=1)
    out = photon_shuffle_unmix(reps, d, seed=4)

    # deterministic soft assignment with the same NNLS abundance prior
    a = invert_mixing(d, counts, nonneg=True)
    b = d / d.sum(axis=1, keepdims=True)
    soft = np.zeros(2)
    for det in range(2):
        w = a * b[:, det]
        soft += counts[det] * w / w.sum()

    assert np.allclose(out.mean(axis=1), soft, rtol=0.02)


def test_recovered_counts_keep_poisson_statistics():
    """A single Poisson source split across detectors is recovered ~ Poisson."""
    d = np.array([[1.0, 0.1], [0.0, 1.0]])
    lam = 200.0
    rng = np.random.default_rng(5)
    n = 8000
    true_d = rng.poisson(lam, size=n)  # true donor photons
    b0 = d[0] / d[0].sum()
    green = rng.binomial(true_d, b0[0])
    red = true_d - green
    counts = np.vstack([green, red])  # acceptor absent

    out = photon_shuffle_unmix(counts, d, seed=6)
    rec = out[0]  # recovered donor stream
    assert abs(rec.mean() - lam) < 5
    fano = rec.var() / rec.mean()  # Poisson -> Fano ~ 1
    assert 0.7 < fano < 1.4


def test_seed_is_reproducible_and_abundances_respected():
    d = np.array([[1.0, 0.1], [0.0, 1.0]])
    counts = np.array([[300, 250, 400], [200, 180, 220]])
    a = photon_shuffle_unmix(counts, d, seed=7)
    b = photon_shuffle_unmix(counts, d, seed=7)
    assert np.array_equal(a, b)  # deterministic given the seed

    # forcing the acceptor abundance to zero sends all red photons to the donor
    ab = np.array([[300.0, 250.0, 400.0], [0.0, 0.0, 0.0]])
    out = photon_shuffle_unmix(counts, d, abundances=ab, seed=8)
    assert np.array_equal(out[0], counts.sum(axis=0))
    assert np.all(out[1] == 0)
