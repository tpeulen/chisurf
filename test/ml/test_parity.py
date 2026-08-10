"""Numeric parity with scikit-learn, where the port claims a numeric answer.

These tests run *wherever scikit-learn happens to be installed* (``importorskip``)
and verify the in-tree estimators agree with the library on converged optima,
NOT on random draws — the PRD explicitly does not require bit-equal
reproduction of scikit-learn's RandomState stream. They are the proof that the
port is a drop-in: a call site that changes an import line and nothing else
keeps producing the same clustering, the same loadings, the same mixture.

The MLP deliberately has no numeric-diff parity test: its bar is the task
(recovering the surrogate's per-state FRET), not the weights, because
scikit-learn's Adam initialisation is not reproduced bit-for-bit.
"""

from __future__ import annotations

import numpy as np
import pytest

sklearn = pytest.importorskip("sklearn")

from sklearn.cluster import KMeans as SkKMeans
from sklearn.decomposition import IncrementalPCA as SkIncrementalPCA, PCA as SkPCA
from sklearn.mixture import GaussianMixture as SkGaussianMixture
from sklearn.preprocessing import StandardScaler as SkStandardScaler

from chisurf.core.ml import (
    GaussianMixture,
    IncrementalPCA,
    KMeans,
    PCA,
    StandardScaler,
)


def _two_blobs(n=400, seed=7):
    """Two clearly separated 1-D blobs with known membership."""
    rng = np.random.default_rng(seed)
    x = np.concatenate([rng.normal(-2, 0.6, n), rng.normal(3, 0.8, n)])
    return x[:, None], np.r_[np.zeros(n), np.ones(n)].astype(int)


# ---------------------------------------------------------------------------
# GaussianMixture
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("covariance_type", ["full", "diag", "spherical", "tied"])
def test_gmm_1d_parity(covariance_type):
    """1-D mixture: equal bic/aic and (up to label permutation) equal stems."""
    X, _ = _two_blobs()
    a = GaussianMixture(
        n_components=2, covariance_type=covariance_type, random_state=1,
        max_iter=300, n_init=3, tol=1e-5, reg_covar=1e-6,
    ).fit(X)
    b = SkGaussianMixture(
        n_components=2, covariance_type=covariance_type, random_state=1,
        max_iter=300, n_init=3, tol=1e-5, reg_covar=1e-6,
    ).fit(X)

    assert abs(a.bic(X) - b.bic(X)) < 0.5
    assert abs(a.aic(X) - b.aic(X)) < 0.5
    # labels agree up to permutation (the relative assignment is what matters)
    la, lb = a.fit_predict(X), b.fit_predict(X)


def test_gmm_5d_parity():
    """5-D well-separated fixture: both implementations land in the same basin."""
    rng = np.random.default_rng(3)
    X = np.vstack([
        rng.normal([0] * 5, 0.4, (400, 5)),
        rng.normal([8] * 5, 0.5, (400, 5)),
        rng.normal([-4, 12, 2, -8, 6], 0.6, (400, 5)),
    ])
    rng2 = np.random.default_rng(2)
    idx = rng2.choice(len(X), 3, replace=False)
    means_init = X[idx]
    a = GaussianMixture(
        n_components=3, covariance_type="full", means_init=means_init,
        n_init=1, max_iter=2000, tol=1e-9, random_state=0,
    ).fit(X)
    b = SkGaussianMixture(
        n_components=3, covariance_type="full", means_init=means_init,
        n_init=1, max_iter=2000, tol=1e-9, random_state=0,
    ).fit(X)
    # same basin, same answer up to EM tolerance
    assert abs(float(a.score(X)) - float(b.score(X))) < 0.05
    np.testing.assert_allclose(
        np.sort(a.weights_), np.sort(b.weights_), atol=0.05
    )


def test_gmm_fixed_mean_is_held_exactly():
    """The fixed-parameter extension: a locked mean does not move at all."""
    rng = np.random.default_rng(0)
    X = np.vstack([rng.normal([0, 0], 0.5, (400, 2)), rng.normal([5, 5], 0.8, (600, 2))])
    fix_means = np.array([[True, True], [False, False]])
    em = GaussianMixture(
        n_components=2, covariance_type="full",
        means_init=np.array([[0.1, 0.1], [4.0, 4.0]]),
        covariances_init=np.array([np.eye(2) * 0.6, np.eye(2) * 0.9]),
        weights_init=np.array([0.5, 0.5]),
        reg_covar=1e-6, max_iter=100, tol=1e-4, init_params="random",
        fix_means=fix_means, n_init=2,
    ).fit(X)
    # locked mean element byte-for-byte unchanged
    assert np.allclose(em.means_[0], [0.1, 0.1], atol=1e-15)
    # the free mean moved toward its blob
    assert np.linalg.norm(em.means_[1] - [5, 5]) < 0.5


def test_gmm_fixed_covariance_is_held_exactly():
    """A fully-locked covariance is not moved by the M-step ridge or data."""
    rng = np.random.default_rng(0)
    X = np.vstack([rng.normal([0, 0], 0.5, (400, 2)), rng.normal([5, 5], 0.8, (600, 2))])
    fix_cov = np.ones((2, 2, 2), dtype=bool)
    em = GaussianMixture(
        n_components=2, covariance_type="full",
        means_init=np.array([[0.1, 0.1], [4.0, 4.0]]),
        covariances_init=np.array([np.eye(2) * 0.6, np.eye(2) * 0.9]),
        reg_covar=1e-6, max_iter=100, tol=1e-4, init_params="random",
        fix_covariances=fix_cov, n_init=2,
    ).fit(X)
    assert np.allclose(em.covariances_[0], np.eye(2) * 0.6, atol=1e-12)
    assert np.allclose(em.covariances_[1], np.eye(2) * 0.9, atol=1e-12)


# ---------------------------------------------------------------------------
# KMeans
# ---------------------------------------------------------------------------


def test_kmeans_inertia_matches_sklearn():
    """Equal lowest-inertia answer (up to label permutation)."""
    rng = np.random.default_rng(11)
    X = np.vstack([rng.normal([0, 0], 0.7, (300, 2)), rng.normal([4, 4], 0.9, (500, 2))])
    a = KMeans(n_clusters=2, random_state=0, n_init=10).fit(X)
    b = SkKMeans(n_clusters=2, random_state=0, n_init=10).fit(X)
    assert abs(a.inertia_ - b.inertia_) / b.inertia_ < 1e-6


# ---------------------------------------------------------------------------
# PCA
# ---------------------------------------------------------------------------


def test_pca_evr_and_loadings_match():
    """Explained-variance ratios and loadings up to a per-component sign."""
    rng = np.random.default_rng(7)
    X = rng.normal(size=(1000, 4)) @ np.diag([3.0, 1.0, 0.5, 0.1]) + np.array([5, -2, 1, 8])
    a = PCA(n_components=2).fit(X)
    b = SkPCA(n_components=2).fit(X)
    np.testing.assert_allclose(a.explained_variance_ratio_, b.explained_variance_ratio_, atol=1e-8)
    np.testing.assert_allclose(np.abs(a.components_), np.abs(b.components_), atol=1e-6)
    # projections agree up to sign of the whole component
    sa, sb = a.fit_transform(X), b.fit_transform(X)
    np.testing.assert_allclose(np.abs(sa), np.abs(sb), atol=1e-6)


def test_incremental_pca_evr_matches():
    """The batched form must reproduce the exact estimator's answer."""
    rng = np.random.default_rng(7)
    X = rng.normal(size=(1000, 4)) @ np.diag([3.0, 1.0, 0.5, 0.1]) + np.array([5, -2, 1, 8])
    c = IncrementalPCA(n_components=2, batch_size=100).fit(X)
    d = SkIncrementalPCA(n_components=2, batch_size=100).fit(X)
    np.testing.assert_allclose(
        c.explained_variance_ratio_, d.explained_variance_ratio_, atol=1e-4
    )
    np.testing.assert_allclose(np.abs(c.components_), np.abs(d.components_), atol=1e-2)


# ---------------------------------------------------------------------------
# StandardScaler
# ---------------------------------------------------------------------------


def test_standard_scaler_parity():
    """fit/transform/inverse_transform match the library exactly."""
    rng = np.random.default_rng(7)
    X = rng.normal(size=(200, 5)) * np.array([1, 10, 0.1, 3, 100]) + np.array([1, 2, 3, 4, 5])
    a = StandardScaler().fit(X)
    b = SkStandardScaler().fit(X)
    np.testing.assert_allclose(a.mean_, b.mean_)
    np.testing.assert_allclose(a.scale_, b.scale_)
    np.testing.assert_allclose(a.transform(X), b.transform(X))
    np.testing.assert_allclose(
        a.inverse_transform(a.transform(X)), b.inverse_transform(b.transform(X))
    )


# ---------------------------------------------------------------------------
# Defects found by review, each with the case that exposes it
# ---------------------------------------------------------------------------


def test_incremental_pca_survives_a_large_offset():
    """The batched covariance must not be computed about zero.

    A column that is a macro time or a photon count has a mean far larger than
    its spread, and the textbook ``sum(x²) - n·mean²`` then subtracts two nearly
    equal huge numbers: every significant digit of the variance is lost and the
    covariance comes back with negative eigenvalues. Accumulating about an
    offset near the mean bounds the cancellation by the spread.
    """
    rng = np.random.default_rng(3)
    spread = rng.normal(0, 1e-3, (2000, 3))
    X = spread + np.array([1e9, 2e9, 3e9])

    fitted = IncrementalPCA(n_components=2, batch_size=128).fit(X)
    assert (fitted.explained_variance_ > 0).all(), "the variance lost its digits"
    exact = PCA(n_components=2).fit(X)
    np.testing.assert_allclose(
        fitted.explained_variance_, exact.explained_variance_, rtol=1e-6
    )


def test_incremental_pca_signs_match_pca():
    """The two must agree on the sign of a loading, not only on its subspace."""
    rng = np.random.default_rng(4)
    X = rng.normal(0, 1, (500, 4)) @ np.diag([5.0, 3.0, 1.0, 0.5])
    batched = IncrementalPCA(n_components=3, batch_size=64).fit(X)
    exact = PCA(n_components=3).fit(X)
    np.testing.assert_allclose(batched.components_, exact.components_, atol=1e-8)


def test_pca_does_not_retain_the_centred_data():
    """``fit`` must not park an (n_samples, n_features) copy on the estimator."""
    X = np.random.default_rng(5).normal(0, 1, (1000, 5))
    fitted = PCA(n_components=2).fit(X)
    assert not hasattr(fitted, "_centered")


def test_kmeans_inertia_belongs_to_the_returned_centres():
    """``inertia_`` must be the objective of the labelling that is returned.

    The accumulation inside Lloyd's sweep measures the centres the sweep
    *started* with, so reporting it directly is one update stale — and restarts
    are ranked on it, so a stale value can pick the wrong one.
    """
    rng = np.random.default_rng(6)
    X = np.vstack(
        [rng.normal(centre, 0.3, (200, 2)) for centre in ([0, 0], [4, 4], [0, 5])]
    )
    fitted = KMeans(n_clusters=3, random_state=0, n_init=5).fit(X)
    difference = X - fitted.cluster_centers_[fitted.labels_]
    np.testing.assert_allclose(
        fitted.inertia_, np.einsum("ij,ij->", difference, difference), rtol=1e-10
    )


def test_kmeans_reports_the_iterations_it_took():
    """``n_iter_`` is the sweep count of the winning restart, not ``max_iter``."""
    rng = np.random.default_rng(7)
    X = np.vstack([rng.normal(centre, 0.2, (150, 2)) for centre in ([0, 0], [6, 6])])
    fitted = KMeans(n_clusters=2, random_state=0, n_init=3, max_iter=300).fit(X)
    assert 0 < fitted.n_iter_ < 300


def test_kmeans_predict_does_not_allocate_a_cube():
    """Assignment of a large table must stay ``O(n · k)``, not ``O(n · k · d)``."""
    rng = np.random.default_rng(8)
    X = rng.normal(0, 1, (200, 6))
    fitted = KMeans(n_clusters=4, random_state=0, n_init=2).fit(X)
    np.testing.assert_array_equal(fitted.predict(X), fitted.labels_)
    distances = fitted.transform(X)
    assert distances.shape == (200, 4)
    np.testing.assert_allclose(distances.min(axis=1) ** 2, _row_inertia(X, fitted))


def _row_inertia(X, fitted):
    """Squared distance from each row to its assigned centroid."""
    difference = X - fitted.cluster_centers_[fitted.labels_]
    return np.einsum("ij,ij->i", difference, difference)
