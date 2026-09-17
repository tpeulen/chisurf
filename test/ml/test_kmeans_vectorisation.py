"""The vectorised k-means kernels must match the scalar loops they replaced.

The loops were the reference implementation for every consumer of this module —
:class:`KMeans`, the Gaussian-mixture initialisation, the HMM's emission seeding
and, through those, the automatic FRET calibration. Replacing them for speed is
only safe if the answers are the same ones, so the loops live on here as the
oracle.
"""

from __future__ import annotations

import importlib

import numpy as np
import pytest

# The package re-exports a *function* named ``_kmeans``, which shadows the
# module of the same name: both ``from ...cluster import _kmeans`` and
# ``import ...cluster._kmeans as K`` hand back the function, because both
# resolve by attribute lookup on the package. ``import_module`` does not.
K = importlib.import_module("chisurf.core.ml.cluster._kmeans")


# ── the loops, as they were ───────────────────────────────────────────────────


def _reference_seed(X, n_clusters, uniforms):
    """``_kmeanspp_seed`` as an element-at-a-time loop."""
    n_samples, n_features = X.shape
    n_trials = uniforms.shape[0] // n_clusters
    centers = np.empty((n_clusters, n_features))
    index = min(int(uniforms[0] * n_samples), n_samples - 1)
    centers[0] = X[index]
    closest = np.array(
        [sum((X[t, j] - centers[0, j]) ** 2 for j in range(n_features)) for t in range(n_samples)]
    )
    for c in range(1, n_clusters):
        total = 0.0
        for t in range(n_samples):
            total += closest[t]
        best_potential, best_index = np.inf, -1
        for trial in range(n_trials):
            uniform = uniforms[c * n_trials + trial]
            if total <= 0.0:
                index = min(int(uniform * n_samples), n_samples - 1)
            else:
                target, acc, index = uniform * total, 0.0, n_samples - 1
                for t in range(n_samples):
                    acc += closest[t]
                    if acc >= target:
                        index = t
                        break
            candidate = ((X - X[index]) ** 2).sum(axis=1)
            potential = 0.0
            for t in range(n_samples):
                potential += min(candidate[t], closest[t])
            if potential < best_potential:
                best_potential, best_index = potential, index
        centers[c] = X[best_index]
        candidate = ((X - centers[c]) ** 2).sum(axis=1)
        for t in range(n_samples):
            if candidate[t] < closest[t]:
                closest[t] = candidate[t]
    return centers


def _reference_lloyd(X, centers, labels, max_iter, tol):
    """``_kmeans_lloyd`` as an element-at-a-time loop."""
    n_samples, n_features = X.shape
    n_clusters = centers.shape[0]
    labels[:] = -1
    sums = np.empty((n_clusters, n_features))
    counts = np.empty(n_clusters)
    n_iter = 0
    for _ in range(max_iter):
        n_iter += 1
        sums[:, :] = 0.0
        counts[:] = 0.0
        n_changed, worst_distance, worst_index = 0, -1.0, 0
        for t in range(n_samples):
            best, best_c = np.inf, 0
            for c in range(n_clusters):
                acc = sum((X[t, j] - centers[c, j]) ** 2 for j in range(n_features))
                if acc < best:
                    best, best_c = acc, c
            if labels[t] != best_c:
                labels[t] = best_c
                n_changed += 1
            counts[best_c] += 1.0
            for j in range(n_features):
                sums[best_c, j] += X[t, j]
            if best > worst_distance:
                worst_distance, worst_index = best, t
        shift = 0.0
        for c in range(n_clusters):
            if counts[c] > 0.0:
                for j in range(n_features):
                    updated = sums[c, j] / counts[c]
                    shift += (updated - centers[c, j]) ** 2
                    centers[c, j] = updated
            else:
                for j in range(n_features):
                    centers[c, j] = X[worst_index, j]
                worst_distance = -1.0
                for t in range(n_samples):
                    if labels[t] == c:
                        continue
                    acc = sum((X[t, j] - centers[labels[t], j]) ** 2 for j in range(n_features))
                    if acc > worst_distance:
                        worst_distance, worst_index = acc, t
                shift += tol + 1.0
        if n_changed == 0 or shift <= tol * tol:
            break
    inertia = 0.0
    for t in range(n_samples):
        best, best_c = np.inf, 0
        for c in range(n_clusters):
            acc = sum((X[t, j] - centers[c, j]) ** 2 for j in range(n_features))
            if acc < best:
                best, best_c = acc, c
        labels[t] = best_c
        inertia += best
    return inertia, n_iter


# ── the parity ───────────────────────────────────────────────────────────────


def _samples(rng, n=400, n_features=1, n_blobs=3):
    """Well-separated blobs, the shape a mixture initialisation actually sees."""
    means = rng.normal(0.0, 5.0, (n_blobs, n_features))
    which = rng.integers(0, n_blobs, n)
    return means[which] + rng.normal(0.0, 0.4, (n, n_features))


@pytest.mark.parametrize("n_features", [1, 2, 3])
@pytest.mark.parametrize("n_clusters", [2, 3, 5])
def test_the_seed_is_the_one_the_loop_chose(n_features, n_clusters):
    rng = np.random.default_rng(7)
    X = _samples(rng, n_features=n_features)
    uniforms = rng.random(n_clusters * (2 + int(np.log(n_clusters))))
    np.testing.assert_allclose(
        K._kmeanspp_seed(X, n_clusters, uniforms),
        _reference_seed(X, n_clusters, uniforms),
    )


@pytest.mark.parametrize("n_features", [1, 2])
@pytest.mark.parametrize("n_clusters", [2, 3, 4])
def test_lloyd_converges_where_the_loop_did(n_features, n_clusters):
    rng = np.random.default_rng(11)
    X = _samples(rng, n_features=n_features)
    start = X[rng.choice(len(X), n_clusters, replace=False)].copy()

    fast_centers, fast_labels = start.copy(), np.empty(len(X), dtype=np.int64)
    fast = K._kmeans_lloyd(X, fast_centers, fast_labels, 300, 1e-4)

    slow_centers, slow_labels = start.copy(), np.empty(len(X), dtype=np.int64)
    slow = _reference_lloyd(X, slow_centers, slow_labels, 300, 1e-4)

    np.testing.assert_allclose(fast_centers, slow_centers)
    np.testing.assert_array_equal(fast_labels, slow_labels)
    assert fast[1] == slow[1]  # same number of sweeps
    assert fast[0] == pytest.approx(slow[0])  # same inertia


def test_an_emptied_cluster_is_reseeded_the_same_way():
    """The empty-cluster branch is the one the loops handled least obviously."""
    # More clusters than distinct points guarantees the branch is taken.
    X = np.repeat(np.array([[0.0], [1.0], [2.0]]), 20, axis=0)
    start = np.array([[0.0], [1.0], [2.0], [50.0], [60.0]])
    rng = np.random.default_rng(3)
    del rng

    fast_centers, fast_labels = start.copy(), np.empty(len(X), dtype=np.int64)
    K._kmeans_lloyd(X, fast_centers, fast_labels, 50, 1e-4)
    slow_centers, slow_labels = start.copy(), np.empty(len(X), dtype=np.int64)
    _reference_lloyd(X, slow_centers, slow_labels, 50, 1e-4)

    np.testing.assert_allclose(fast_centers, slow_centers)
    np.testing.assert_array_equal(fast_labels, slow_labels)


def test_the_blocked_distance_matrix_matches_a_single_block(monkeypatch):
    """Blocking is for memory; it must not change a number."""
    rng = np.random.default_rng(5)
    X = _samples(rng, n=1000, n_features=2)
    centers = X[:4].copy()
    whole = K._distances_to_centers(X, centers)
    monkeypatch.setattr(K, "_DISTANCE_BLOCK", 97)
    np.testing.assert_allclose(K._distances_to_centers(X, centers), whole)


def test_the_kernels_are_not_element_at_a_time_again():
    """A guardrail: these are hot, and the loops cost 2.2 s per calibration.

    Not a style rule — the module is imported by the FRET calibration, which a
    user waits on. If a loop over samples comes back, so does the wait.
    """
    import inspect

    source = inspect.getsource(K._kmeans_lloyd) + inspect.getsource(K._kmeanspp_seed)
    assert "for t in range(n_samples)" not in source
