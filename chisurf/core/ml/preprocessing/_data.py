"""Preprocessing estimators (``StandardScaler``)."""

from __future__ import annotations

import numpy as np

from ..base import BaseEstimator

__all__ = ["StandardScaler"]


class StandardScaler(BaseEstimator):
    """Standardise features by removing the mean and scaling to unit variance.

    The scaler used by the H2MM surrogate to feed and read the feature/target
    spaces: ``transform`` maps ``X`` into the fitted ``(mean_, scale_)`` space,
    ``inverse_transform`` maps it back.

    Parameters
    ----------
    copy : bool, default True
        Accepted for interface parity; transformed output always is a fresh
        array (the source is never mutated).
    with_mean : bool, default True
        Centre each column at its fitted mean.
    with_std : bool, default True
        Divide each column by its fitted standard deviation.

    Attributes
    ----------
    mean_ : numpy.ndarray
        Per-column mean of the fit input.
    scale_ : numpy.ndarray
        Per-column standard deviation of the fit input; values whose standard
        deviation is zero are left at 1.0 so that division does not produce NaN.
    var_ : numpy.ndarray
        Per-column variance, the square of ``scale_``.
    """

    def __init__(self, copy: bool = True, with_mean: bool = True, with_std: bool = True):
        self.copy = copy
        self.with_mean = with_mean
        self.with_std = with_std
        self._constructor_params = {"copy", "with_mean", "with_std"}

    def fit(self, X, y=None):
        """Compute the mean and standard deviation of ``X`` and return ``self``."""
        X = np.asarray(X, dtype=float)
        self.mean_ = X.mean(axis=0)
        scale = X.std(axis=0)
        # A constant column has zero variance and would produce NaN scaling.
        scale[scale == 0.0] = 1.0
        self.scale_ = scale
        self.var_ = scale**2
        self.n_features_in_ = X.shape[1]
        return self

    def transform(self, X) -> np.ndarray:
        """Return ``X`` standardised to the fitted space."""
        X = np.asarray(X, dtype=float)
        if self.with_mean:
            X = X - self.mean_
        if self.with_std:
            X = X / self.scale_
        return X

    def fit_transform(self, X, y=None) -> np.ndarray:
        """Fit and transform in one call."""
        return self.fit(X).transform(X)

    def inverse_transform(self, X) -> np.ndarray:
        """Map standardised ``X`` back to the original space."""
        X = np.asarray(X, dtype=float)
        if self.with_std:
            X = X * self.scale_
        if self.with_mean:
            X = X + self.mean_
        return X
