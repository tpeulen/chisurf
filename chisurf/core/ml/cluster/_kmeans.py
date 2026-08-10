"""k-means++ clustering, and the KMeans estimator surface.

The iteration kernels are moved verbatim out of ``chisurf/core/math/hmm.py``,
which used them only to seed the HMM's emission initialisation. They are pure
numba functionals over ``(samples, centers)`` and carry no state, so the HMM
and :class:`KMeans` share one implementation.
"""

from __future__ import annotations

from typing import Optional

import numba as nb
import numpy as np

from ..base import BaseEstimator

__all__ = [
    "KMeans",
    "_squared_distances",
    "_kmeanspp_seed",
    "_kmeans_lloyd",
    "_kmeans",
]


@nb.jit(nopython=True, nogil=True, fastmath=True)
def _squared_distances(X: np.ndarray, center: np.ndarray, out: np.ndarray) -> None:
    """Fill ``out`` with the squared distance from every row of ``X`` to ``center``."""
    n_samples, n_features = X.shape
    for t in range(n_samples):
        acc = 0.0
        for j in range(n_features):
            diff = X[t, j] - center[j]
            acc += diff * diff
        out[t] = acc


@nb.jit(nopython=True, nogil=True, fastmath=True)
def _kmeanspp_seed(X: np.ndarray, n_clusters: int, uniforms: np.ndarray) -> np.ndarray:
    """Choose ``n_clusters`` initial centres with the greedy k-means++ rule.

    Each further centre is sampled from the data with a probability
    proportional to its squared distance from the closest centre chosen so far.
    Several candidates are drawn per centre and the one that lowers the total
    squared distance the most is kept -- the greedy variant, which is markedly
    less likely to strand a centre than taking the first draw. ``uniforms``
    supplies the pre-drawn variates, so the caller keeps control of the random
    stream.
    """
    n_samples, n_features = X.shape
    n_trials = uniforms.shape[0] // n_clusters
    centers = np.empty((n_clusters, n_features))
    index = min(int(uniforms[0] * n_samples), n_samples - 1)
    centers[0] = X[index]
    closest = np.empty(n_samples)
    _squared_distances(X, centers[0], closest)
    candidate = np.empty(n_samples)
    for c in range(1, n_clusters):
        total = 0.0
        for t in range(n_samples):
            total += closest[t]
        best_potential = np.inf
        best_index = -1
        for trial in range(n_trials):
            uniform = uniforms[c * n_trials + trial]
            if total <= 0.0:
                index = min(int(uniform * n_samples), n_samples - 1)
            else:
                target = uniform * total
                acc = 0.0
                index = n_samples - 1
                for t in range(n_samples):
                    acc += closest[t]
                    if acc >= target:
                        index = t
                        break
            _squared_distances(X, X[index], candidate)
            potential = 0.0
            for t in range(n_samples):
                potential += min(candidate[t], closest[t])
            if potential < best_potential:
                best_potential = potential
                best_index = index
        centers[c] = X[best_index]
        _squared_distances(X, centers[c], candidate)
        for t in range(n_samples):
            if candidate[t] < closest[t]:
                closest[t] = candidate[t]
    return centers


@nb.jit(nopython=True, nogil=True, fastmath=True)
def _kmeans_lloyd(
    X: np.ndarray, centers: np.ndarray, labels: np.ndarray, max_iter: int, tol: float
) -> float:
    """Run Lloyd's algorithm in place on ``centers``/``labels``, returning the inertia.

    Assignment and centroid accumulation share one pass over the samples, so no
    ``(n_samples, n_clusters)`` distance matrix is ever materialised.
    """
    n_samples, n_features = X.shape
    n_clusters = centers.shape[0]
    labels[:] = -1
    sums = np.empty((n_clusters, n_features))
    counts = np.empty(n_clusters)
    inertia = 0.0
    for _ in range(max_iter):
        sums[:, :] = 0.0
        counts[:] = 0.0
        inertia = 0.0
        n_changed = 0
        worst_distance = -1.0
        worst_index = 0
        for t in range(n_samples):
            best = np.inf
            best_c = 0
            for c in range(n_clusters):
                acc = 0.0
                for j in range(n_features):
                    diff = X[t, j] - centers[c, j]
                    acc += diff * diff
                if acc < best:
                    best = acc
                    best_c = c
            if labels[t] != best_c:
                labels[t] = best_c
                n_changed += 1
            inertia += best
            counts[best_c] += 1.0
            for j in range(n_features):
                sums[best_c, j] += X[t, j]
            if best > worst_distance:
                worst_distance = best
                worst_index = t
        shift = 0.0
        for c in range(n_clusters):
            if counts[c] > 0.0:
                for j in range(n_features):
                    updated = sums[c, j] / counts[c]
                    diff = updated - centers[c, j]
                    shift += diff * diff
                    centers[c, j] = updated
            else:
                # Re-seed an emptied cluster on the worst-explained sample.
                for j in range(n_features):
                    centers[c, j] = X[worst_index, j]
                shift += tol + 1.0
        if n_changed == 0 or shift <= tol * tol:
            break
    return inertia


def _kmeans(
    X: np.ndarray,
    n_clusters: int,
    random_state: np.random.Generator,
    n_init: int = 10,
    max_iter: int = 300,
    tol: float = 1e-4,
) -> tuple[np.ndarray, np.ndarray]:
    """Cluster ``X`` with k-means++ seeded Lloyd iterations.

    Used to place the initial state means *and* -- through the labels it
    returns -- the initial transitions and covariances. The EM iterations take
    over from there, so a plain implementation is enough, and it keeps this
    module free of a machine-learning dependency.

    Parameters
    ----------
    X : numpy.ndarray
        Samples, shape ``(n_samples, n_features)``.
    n_clusters : int
        Number of centres to place.
    random_state : numpy.random.Generator
        Source of randomness for the seeding.
    n_init : int
        Number of restarts; the run with the lowest inertia wins.
    max_iter : int
        Maximum Lloyd iterations per restart.
    tol : float
        Stop a restart once the centres move less than this (Frobenius norm).

    Returns
    -------
    centers : numpy.ndarray
        Cluster centres, shape ``(n_clusters, n_features)``.
    labels : numpy.ndarray
        Index of the closest centre per sample, shape ``(n_samples, )``.
    """
    X = np.ascontiguousarray(X, dtype=float)
    n_samples = len(X)
    if n_samples <= n_clusters:
        centers = np.repeat(X.mean(axis=0)[None, :], n_clusters, axis=0)
        centers[:n_samples] = X
        return centers, np.arange(n_samples) % n_clusters

    # Candidates per centre for the greedy seeding, as in the reference
    # implementations: enough to matter, few enough to stay cheap.
    n_trials = 2 + int(np.log(n_clusters))
    labels = np.empty(n_samples, dtype=np.int64)
    best, best_inertia = None, np.inf
    for _ in range(n_init):
        centers = _kmeanspp_seed(
            X, n_clusters, random_state.random(n_clusters * n_trials)
        )
        inertia = _kmeans_lloyd(X, centers, labels, max_iter, tol)
        if inertia < best_inertia:
            best, best_inertia = (centers, labels.copy()), inertia
    return best


class KMeans(BaseEstimator):
    """k-means clustering with k-means++ seeding and Lloyd iterations.

    Parameters
    ----------
    n_clusters : int, default 8
        Number of centroids.
    random_state : int, optional
        Seed for the seeding stream.
    n_init : int, default 10
        Restarts; the lowest-inertia assignment wins.
    max_iter : int, default 300
        Lloyd iterations per restart.
    tol : float, default 1e-4
        Stop a restart once centroid displacement falls below ``tol``.
    verbose : int, default 0
        Accepted for interface parity; emits nothing.

    Attributes
    ----------
    cluster_centers_ : numpy.ndarray
        ``(n_clusters, n_features)`` final centroids.
    labels_ : numpy.ndarray
        ``(n_samples,)`` closest-centre index per sample.
    inertia_ : float
        Within-cluster sum of squared distances.
    n_iter_ : int
        Lloyd iterations of the winning restart.
    """

    def __init__(
        self,
        n_clusters: int = 8,
        random_state: Optional[int] = None,
        n_init: int = 10,
        max_iter: int = 300,
        tol: float = 1e-4,
        verbose: int = 0,
    ):
        self.n_clusters = n_clusters
        self.random_state = random_state
        self.n_init = n_init
        self.max_iter = max_iter
        self.tol = tol
        self.verbose = verbose
        self._constructor_params = {
            "n_clusters", "random_state", "n_init", "max_iter", "tol", "verbose",
        }

    def fit(self, X, y=None):
        """Compute k-means clustering on ``X`` and return ``self``."""
        X = np.asarray(X, dtype=float)
        rng = np.random.default_rng(self.random_state)
        centers, labels = _kmeans(
            X,
            int(self.n_clusters),
            rng,
            n_init=max(1, int(self.n_init)),
            max_iter=int(self.max_iter),
            tol=float(self.tol),
        )
        self.cluster_centers_ = centers
        self.labels_ = labels
        self.n_iter_ = int(self.max_iter)
        # inertia: sum of squared distances to the assigned centroid
        diff = X - centers[labels]
        self.inertia_ = float(np.einsum("ij,ij->", diff, diff))
        self.n_features_in_ = X.shape[1]
        return self

    def fit_predict(self, X, y=None) -> np.ndarray:
        """Fit and return the cluster labels of ``X``."""
        return self.fit(X).labels_

    def predict(self, X) -> np.ndarray:
        """Return the closest-centroid index of each row of ``X``."""
        X = np.asarray(X, dtype=float)
        diff = X[:, None, :] - self.cluster_centers_[None, :, :]
        return np.einsum("ijk,ijk->ij", diff, diff).argmin(axis=1)

    def transform(self, X) -> np.ndarray:
        """Return the per-row distance to every centroid, ``(n, k)``."""
        X = np.asarray(X, dtype=float)
        diff = X[:, None, :] - self.cluster_centers_[None, :, :]
        return np.sqrt(np.einsum("ijk,ijk->ij", diff, diff))


__all__ = ["KMeans", "_kmeans", "_kmeanspp_seed", "_kmeans_lloyd", "_squared_distances"]
