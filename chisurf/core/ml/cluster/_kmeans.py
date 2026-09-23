"""k-means++ clustering, and the KMeans estimator surface.

The iteration kernels came out of ``chisurf/core/math/hmm.py``, which used them
only to seed the HMM's emission initialisation. They are pure functionals over
``(samples, centers)`` and carry no state, so the HMM and :class:`KMeans` share
one implementation.

They are **vectorised**, which they were not: the kernels were written as
element-at-a-time loops over samples, features and clusters, in the shape a JIT
would compile away — and nothing here is jitted. On a 7 000-burst
the accurate-FRET gating (``tttrlib.gaussian_mixture_1d``, a 1-D mixture
that uses k-means only to *seed* its EM) that was 2.2 of the 2.7 seconds, in
seeding rather than in the fit anybody was waiting for.

The rewrite is semantics-preserving, deliberately: ``argmin``/``argmax`` return
the first extremum, matching the strict ``<``/``>`` of the loops they replace,
and the k-means++ draw is the same cumulative search (``searchsorted(...,
"left")`` is the first index whose partial sum reaches the target). The one
difference is summation order — NumPy sums pairwise where the loops accumulated
left to right, which is *more* accurate, not less.
"""

from __future__ import annotations

import numpy as np

from ..base import BaseEstimator

__all__ = [
    "KMeans",
    "_squared_distances",
    "_distances_to_centers",
    "_kmeanspp_seed",
    "_kmeans_lloyd",
    "_kmeans",
]


#: Rows per block when the sample-to-centre distances are materialised. Bounds
#: the temporary at ``_DISTANCE_BLOCK × n_clusters × n_features`` floats
#: regardless of how many photons a burst search produced.
_DISTANCE_BLOCK = 65_536


def _squared_distances(X: np.ndarray, center: np.ndarray, out: np.ndarray) -> None:
    """Fill ``out`` with the squared distance from every row of ``X`` to ``center``."""
    diff = X - center
    np.einsum("ij,ij->i", diff, diff, out=out)


def _distances_to_centers(X: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Squared distance from every sample to every centre, shape ``(n, k)``.

    Blocked, so the temporary stays bounded on a long measurement instead of
    scaling with the number of samples.
    """
    n_samples = X.shape[0]
    distances = np.empty((n_samples, centers.shape[0]))
    for start in range(0, n_samples, _DISTANCE_BLOCK):
        stop = min(start + _DISTANCE_BLOCK, n_samples)
        diff = X[start:stop, None, :] - centers[None, :, :]
        np.einsum("ijk,ijk->ij", diff, diff, out=distances[start:stop])
    return distances


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
        total = float(closest.sum())
        trials = uniforms[c * n_trials : (c + 1) * n_trials]
        if total <= 0.0:
            indices = np.minimum((trials * n_samples).astype(np.int64), n_samples - 1)
        else:
            # The loop searched for the first partial sum reaching the target;
            # that is exactly a left-side binary search on the cumulative sum.
            indices = np.searchsorted(np.cumsum(closest), trials * total, side="left")
            indices = np.minimum(indices, n_samples - 1)
        best_potential = np.inf
        best_index = -1
        # Few trials (2 + log k), so they stay a loop; each one is vectorised.
        for index in indices:
            _squared_distances(X, X[index], candidate)
            potential = float(np.minimum(candidate, closest).sum())
            if potential < best_potential:
                best_potential = potential
                best_index = int(index)
        centers[c] = X[best_index]
        _squared_distances(X, centers[c], candidate)
        np.minimum(closest, candidate, out=closest)
    return centers


def _kmeans_lloyd(
    X: np.ndarray, centers: np.ndarray, labels: np.ndarray, max_iter: int, tol: float
) -> tuple[float, int]:
    """Run Lloyd's algorithm in place on ``centers``/``labels``.

    Returns
    -------
    inertia : float
        Within-cluster sum of squares **of the returned centres**. The
        accumulation pass computes it against the centres the sweep started
        with, so a final assignment pass is made once the sweep has converged —
        otherwise the value reported is one update stale, and restarts get
        ranked on it.
    n_iter : int
        Sweeps actually performed.
    """
    n_samples, n_features = X.shape
    n_clusters = centers.shape[0]
    labels[:] = -1
    inertia = 0.0
    n_iter = 0
    for _ in range(max_iter):
        n_iter += 1
        distances = _distances_to_centers(X, centers)
        assignment = np.argmin(distances, axis=1)
        best = distances[np.arange(n_samples), assignment]
        n_changed = int(np.count_nonzero(labels != assignment))
        labels[:] = assignment
        inertia = float(best.sum())

        counts = np.bincount(assignment, minlength=n_clusters).astype(float)
        sums = np.empty((n_clusters, n_features))
        for j in range(n_features):
            sums[:, j] = np.bincount(assignment, weights=X[:, j], minlength=n_clusters)
        worst_index = int(np.argmax(best))

        shift = 0.0
        for c in range(n_clusters):
            if counts[c] > 0.0:
                updated = sums[c] / counts[c]
                diff = updated - centers[c]
                shift += float(diff @ diff)
                centers[c] = updated
            else:
                # Re-seed an emptied cluster on the worst-explained sample, and
                # take that sample out of the running so that a second empty
                # cluster does not land on top of the first. The residuals are
                # measured against the centres *as they now stand*, so an
                # earlier cluster's update in this same sweep is accounted for.
                centers[c] = X[worst_index]
                residual = X - centers[labels]
                own = np.einsum("ij,ij->i", residual, residual)
                worst_index = int(np.argmax(own))
                shift += tol + 1.0
        if n_changed == 0 or shift <= tol * tol:
            break

    # The inertia above was accumulated against the centres of the *previous*
    # sweep. One more assignment pass makes it the inertia of what is returned.
    distances = _distances_to_centers(X, centers)
    labels[:] = np.argmin(distances, axis=1)
    inertia = float(distances[np.arange(n_samples), labels].sum())
    return inertia, n_iter


def _kmeans(
    X: np.ndarray,
    n_clusters: int,
    random_state: np.random.Generator,
    n_init: int = 10,
    max_iter: int = 300,
    tol: float = 1e-4,
) -> tuple[np.ndarray, np.ndarray, float, int]:
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
    inertia : float
        Within-cluster sum of squares of the winning restart.
    n_iter : int
        Sweeps the winning restart took.
    """
    X = np.ascontiguousarray(X, dtype=float)
    n_samples = len(X)
    if n_samples <= n_clusters:
        centers = np.repeat(X.mean(axis=0)[None, :], n_clusters, axis=0)
        centers[:n_samples] = X
        return centers, np.arange(n_samples) % n_clusters, 0.0, 0

    # Candidates per centre for the greedy seeding, as in the reference
    # implementations: enough to matter, few enough to stay cheap.
    n_trials = 2 + int(np.log(n_clusters))
    labels = np.empty(n_samples, dtype=np.int64)
    best, best_inertia, best_n_iter = None, np.inf, 0
    for _ in range(n_init):
        centers = _kmeanspp_seed(X, n_clusters, random_state.random(n_clusters * n_trials))
        inertia, n_iter = _kmeans_lloyd(X, centers, labels, max_iter, tol)
        if inertia < best_inertia:
            best = (centers, labels.copy())
            best_inertia, best_n_iter = inertia, n_iter
    return best[0], best[1], best_inertia, best_n_iter


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
        random_state: int | None = None,
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
            "n_clusters",
            "random_state",
            "n_init",
            "max_iter",
            "tol",
            "verbose",
        }

    def fit(self, X, y=None):
        """Compute k-means clustering on ``X`` and return ``self``."""
        X = np.ascontiguousarray(X, dtype=float)
        rng = np.random.default_rng(self.random_state)
        centers, labels, inertia, n_iter = _kmeans(
            X,
            int(self.n_clusters),
            rng,
            n_init=max(1, int(self.n_init)),
            max_iter=int(self.max_iter),
            tol=float(self.tol),
        )
        self.cluster_centers_ = centers
        self.labels_ = labels
        self.n_iter_ = n_iter
        self.inertia_ = float(inertia)
        self.n_features_in_ = X.shape[1]
        return self

    def fit_predict(self, X, y=None) -> np.ndarray:
        """Fit and return the cluster labels of ``X``."""
        return self.fit(X).labels_

    def _squared_distances_to_centers(self, X: np.ndarray) -> np.ndarray:
        """Return the ``(n, k)`` squared distances, without an ``(n, k, d)`` temporary.

        The obvious broadcast ``X[:, None, :] - centers[None, :, :]`` allocates
        ``n * k * d`` doubles, which for a burst table and a dozen clusters is
        gigabytes. The expansion below allocates ``n * k``.
        """
        centers = self.cluster_centers_
        squared = (
            np.einsum("ij,ij->i", X, X)[:, None]
            + np.einsum("ij,ij->i", centers, centers)[None, :]
            - 2.0 * (X @ centers.T)
        )
        return np.maximum(squared, 0.0, out=squared)

    def predict(self, X) -> np.ndarray:
        """Return the closest-centroid index of each row of ``X``."""
        X = np.asarray(X, dtype=float)
        return self._squared_distances_to_centers(X).argmin(axis=1)

    def transform(self, X) -> np.ndarray:
        """Return the per-row distance to every centroid, ``(n, k)``."""
        X = np.asarray(X, dtype=float)
        return np.sqrt(self._squared_distances_to_centers(X))


__all__ = ["KMeans", "_kmeans", "_kmeanspp_seed", "_kmeans_lloyd", "_squared_distances"]
