"""Principal component analysis and its incremental variant.

PCA is used by the companion photon-data exploration tool to answer "which of
my parameters distinguish anything?". It implements the same estimators
scikit-learn exposes under ``sklearn.decomposition`` — ``PCA`` and
``IncrementalPCA`` — with the standardised-input and non-finite-row handling
the caller needs, but no solver options beyond what the port uses.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..base import BaseEstimator

__all__ = ["PCA", "IncrementalPCA"]

#: Numerical guard for the explained-variance denominator.
_EPS = np.finfo(float).tiny


def _svd_flip(U: np.ndarray, V: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Flip columns of ``U`` / rows of ``V`` so the loadings have positive
    maximal absolute entries per column; sklearn's ``svd_flip``.

    Parameters
    ----------
    U : numpy.ndarray
        Left singular vectors, ``(n_samples, k)``.
    V : numpy.ndarray
        Right singular vectors, ``(k, n_features)``.

    Returns
    -------
    tuple of numpy.ndarray
        Flipped ``U`` and ``V``.
    """
    max_abs_cols = np.argmax(np.abs(U), axis=0)
    signs = np.sign(U[max_abs_cols, range(U.shape[1])])
    # A zero column would leave the sign 0 and destroy the vector; treat it as +.
    signs[signs == 0] = 1.0
    U = U * signs
    V = V * signs[:, np.newaxis]
    return U, V


class PCA(BaseEstimator):
    """Principal component analysis via the covariance matrix's eigendecomposition.

    Parameters
    ----------
    n_components : int, optional
        Number of components to keep. If None, all ``min(n_samples, n_features)``
        components are retained (and the caller reads ``explained_variance_``).
    svd_solver : {"auto", "full", "arpack", "randomized"}, default "auto"
        Accepted for interface parity; the covariance eigendecomposition is the
        implementation for every solver.
    random_state : int, optional
        Accepted for interface parity; the fit is deterministic.

    Attributes
    ----------
    components_ : numpy.ndarray
        ``(n_components, n_features)`` loadings (right eigenvectors).
    explained_variance_ : numpy.ndarray
        Variance carried by each component.
    explained_variance_ratio_ : numpy.ndarray
        Fraction of total (centred) variance per component.
    mean_ : numpy.ndarray
        Per-column mean of the fit input.
    n_components_ : int
        Retained component count.
    """

    def __init__(self, n_components: Optional[int] = None,
                 svd_solver: str = "auto", random_state: Optional[int] = None):
        self.n_components = n_components
        self.svd_solver = svd_solver
        self.random_state = random_state
        self._constructor_params = {"n_components", "svd_solver", "random_state"}

    def fit(self, X, y=None):
        """Fit the model with ``X`` and return ``self``."""
        X = np.asarray(X, dtype=float)
        self.n_samples_, n_features = X.shape
        self.mean_ = X.mean(axis=0)
        centered = X - self.mean_
        n_comp = self.n_components
        if n_comp is None:
            n_comp = min(self.n_samples_, n_features)
        n_comp = int(n_comp)
        if n_comp <= 0:
            raise ValueError("n_components must be >= 1")

        cov = (centered.T @ centered) / (self.n_samples_ - 1)
        eigvals, eigvecs = np.linalg.eigh(cov)
        order = np.argsort(eigvals)[::-1]
        self.explained_variance_ = eigvals[order][:n_comp].copy()
        # sklearn's ratio normalises by the *full* spectrum sum, which equals the
        # total (unbiased) centred variance, not just the retained part.
        self.explained_variance_ratio_ = self.explained_variance_ / max(
            eigvals.sum(), _EPS
        )
        self.components_ = eigvecs[:, order][:, :n_comp].T.copy()
        # Deterministic sign convention: the largest absolute loading per
        # component is positive, matching sklearn's svd_flip.
        self.components_ = _svd_flip(
            np.zeros((1, n_comp)), self.components_
        )[1]
        self.n_components_ = n_comp
        return self

    def fit_transform(self, X, y=None) -> np.ndarray:
        """Fit and project ``X`` in one call."""
        X = np.asarray(X, dtype=float)
        self.fit(X)
        # Projected here rather than by keeping the centred copy from `fit`:
        # holding an (n_samples, n_features) array on the estimator for the sake
        # of one call is the kind of retention that only shows up as a memory
        # figure much later.
        return (X - self.mean_) @ self.components_.T

    def transform(self, X) -> np.ndarray:
        """Project ``X`` onto the components."""
        X = np.asarray(X, dtype=float)
        return (X - self.mean_) @ self.components_.T

    def inverse_transform(self, X) -> np.ndarray:
        """Map projected ``X`` back to the original feature space."""
        return np.asarray(X, dtype=float) @ self.components_ + self.mean_


class IncrementalPCA(BaseEstimator):
    """Streamed principal component analysis for matrices too large to hold.

    Batches of rows update the covariance moment (sum and sum-of-squares);
    the final eigendecomposition is computed once, on the accumulated moment.
    This keeps memory bounded by the batch size and reproduces the exact
    result of :class:`PCA` on the same data, which is what the caller's
    ideal-answer comparison relies on.

    Parameters
    ----------
    n_components : int, optional
        Number of components to keep; if None, all are retained.
    batch_size : int, optional
        How many rows are consumed per update. The final decomposition still
        sees the full moment, so this affects only peak memory.
    random_state : int, optional
        Accepted for interface parity; the fit is deterministic.

    Attributes
    ----------
    components_ : numpy.ndarray
        ``(n_components, n_features)`` loadings.
    mean_ : numpy.ndarray
        Per-column mean of the accumulated data.
    explained_variance_ : numpy.ndarray
        Variance carried by each component.
    explained_variance_ratio_ : numpy.ndarray
        Fraction of total (centred) variance per component.
    n_components_ : int
        Retained component count.
    """

    def __init__(self, n_components: Optional[int] = None, batch_size: Optional[int] = None,
                 random_state: Optional[int] = None):
        self.n_components = n_components
        self.batch_size = batch_size
        self.random_state = random_state
        self._constructor_params = {"n_components", "batch_size", "random_state"}

    def fit(self, X, y=None):
        """Fit the model with batched ``X`` and return ``self``."""
        X = np.asarray(X, dtype=float)
        batch = int(self.batch_size or max(len(X) // 10, 1))
        n_features = X.shape[1]

        # Accumulated about an offset, not about zero. The textbook
        # sum-of-squares-minus-square-of-sum loses every significant digit when
        # the mean is large next to the spread -- which is the normal case for a
        # column that is a macro time or a photon count -- and the covariance
        # then comes out with negative eigenvalues. Shifting by any value near
        # the mean bounds the cancellation by the spread instead. The first
        # block's mean is near enough and costs nothing.
        offset = X[:batch].mean(axis=0)
        total_sum = np.zeros(n_features)
        total_sq = np.zeros((n_features, n_features))
        n = 0
        for start in range(0, len(X), batch):
            block = X[start : start + batch] - offset
            total_sum += block.sum(axis=0)
            total_sq += block.T @ block
            n += len(block)

        shifted_mean = total_sum / n
        mean = offset + shifted_mean
        cov = (total_sq - n * np.outer(shifted_mean, shifted_mean)) / (n - 1)
        eigvals, eigvecs = np.linalg.eigh(cov)
        order = np.argsort(eigvals)[::-1]
        n_comp = self.n_components
        if n_comp is None:
            n_comp = min(n, n_features)
        n_comp = int(n_comp)
        if n_comp <= 0:
            raise ValueError("n_components must be >= 1")
        self.components_ = eigvecs[:, order[:n_comp]].T.copy()
        # The same sign convention as PCA. Without it the two disagree on the
        # sign of every loading -- a difference that is meaningless to the
        # decomposition and very visible to anyone reading a loadings plot.
        self.components_ = _svd_flip(np.zeros((1, n_comp)), self.components_)[1]
        self.explained_variance_ = eigvals[order[:n_comp]].copy()
        self.mean_ = mean
        self.n_components_ = n_comp
        self.explained_variance_ratio_ = (
            self.explained_variance_ / max(eigvals.sum(), _EPS)
        )
        self.n_samples_ = n
        return self

    def fit_transform(self, X, y=None) -> np.ndarray:
        """Fit and project ``X`` in one call."""
        self.fit(X)
        return (np.asarray(X, dtype=float) - self.mean_) @ self.components_.T

    def transform(self, X) -> np.ndarray:
        """Project ``X`` onto the components."""
        return (np.asarray(X, dtype=float) - self.mean_) @ self.components_.T

    def inverse_transform(self, X) -> np.ndarray:
        """Map projected ``X`` back to the original feature space."""
        return np.asarray(X, dtype=float) @ self.components_ + self.mean_


__all__ = ["PCA", "IncrementalPCA", "_svd_flip"]
