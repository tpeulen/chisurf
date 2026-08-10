"""Shared Gaussian machinery: logsumexp and the four covariance layouts.

These are the exact helpers that used to live — private, sealed behind leading
underscores — inside ``chisurf/core/math/hmm.py``. They were moved here so that
the mixture estimators, the HMM, and (once ported) the other call sites all use
one implementation instead of four private copies.

The ``covariance_type`` spellings are scikit-learn's, so a caller bringing
settings over from the library keeps working unchanged.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from scipy import linalg

#: Emission covariance parameterisations, named as scikit-learn names them.
COVARIANCE_TYPES: tuple[Literal["spherical", "diag", "full", "tied"], ...] = (
    "spherical",
    "diag",
    "full",
    "tied",
)

#: Ridge added to a covariance being fitted from too few points.
DEFAULT_MIN_COVAR = 1e-7


def logsumexp(values: np.ndarray) -> float:
    """Return ``log(sum(exp(values)))`` computed without overflow.

    Parameters
    ----------
    values : numpy.ndarray
        1-D array of log-domain values.

    Returns
    -------
    float
        ``log(sum(exp(values)))``, or ``-inf`` when every value is ``-inf``.
    """
    vmax = -np.inf
    for v in values:
        if v > vmax:
            vmax = v
    if vmax == -np.inf:
        return -np.inf
    return float(np.log(np.exp(values - vmax).sum()) + vmax)


def _broadcast_covariance(covars: np.ndarray, n_components: int, n_features: int) -> np.ndarray:
    """Convert the compact covariance layout to a ``(K, d, d)`` array."""
    if covars.ndim == 1:
        return np.repeat(covars[:, None], n_features, axis=1)
    return np.broadcast_to(covars, (n_components, n_features, n_features))


def _log_gaussian_density(
    X: np.ndarray,
    means: np.ndarray,
    covars: np.ndarray,
    covariance_type: str,
    min_covar: float = DEFAULT_MIN_COVAR,
) -> np.ndarray:
    """Evaluate the log emission density of every component at every sample.

    Parameters
    ----------
    X : numpy.ndarray
        Samples, shape ``(n_samples, n_features)``.
    means : numpy.ndarray
        Component means, shape ``(n_components, n_features)``.
    covars : numpy.ndarray
        Covariances in the compact layout of ``covariance_type`` (spherical:
        ``(n_components,)``; diag: ``(n_components, n_features)``; tied: ``(n_features,
        n_features)``; full: ``(n_components, n_features, n_features)``).
    covariance_type : str
        One of :data:`COVARIANCE_TYPES`.
    min_covar : float
        Ridge added to a full covariance that is not positive definite, as a
        last attempt before giving up.

    Returns
    -------
    numpy.ndarray
        Log densities, shape ``(n_samples, n_components)``.
    """
    n_components, n_features = means.shape
    if covariance_type == "spherical":
        covars = np.repeat(np.asarray(covars)[:, None], n_features, axis=1)
        covariance_type = "diag"
    if covariance_type == "diag":
        # Guard the degenerate covariance case against 0 * log 0 = nan.
        covars = np.maximum(covars, np.finfo(float).tiny)
        with np.errstate(over="ignore"):
            return -0.5 * (
                n_features * np.log(2 * np.pi)
                + np.log(covars).sum(axis=-1)
                + ((X[:, None, :] - means) ** 2 / covars).sum(axis=-1)
            )
    if covariance_type == "tied":
        covars = np.broadcast_to(covars, (n_components, n_features, n_features))
    log_prob = np.empty((len(X), n_components))
    for c, (mu, cv) in enumerate(zip(means, covars)):
        try:
            cv_chol = linalg.cholesky(cv, lower=True)
        except linalg.LinAlgError:
            # A component that captured too few samples can go singular; nudge it.
            try:
                cv_chol = linalg.cholesky(
                    cv + min_covar * np.eye(n_features), lower=True
                )
            except linalg.LinAlgError as err:
                raise ValueError(
                    "covariances must be symmetric positive-definite"
                ) from err
        cv_log_det = 2 * np.sum(np.log(np.diagonal(cv_chol)))
        cv_sol = linalg.solve_triangular(cv_chol, (X - mu).T, lower=True).T
        log_prob[:, c] = -0.5 * (
            n_features * np.log(2 * np.pi) + (cv_sol**2).sum(axis=1) + cv_log_det
        )
    return log_prob


def _gaussian_parameters(
    covariance_type: str,
    n_components: int,
    n_features: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return zeroed (weights, means, covars) arrays in the compact layout."""
    if covariance_type == "full":
        covar_shape = (n_components, n_features, n_features)
    elif covariance_type == "diag":
        covar_shape = (n_components, n_features)
    elif covariance_type == "tied":
        covar_shape = (n_features, n_features)
    elif covariance_type == "spherical":
        covar_shape = (n_components,)
    else:
        raise ValueError(f"invalid covariance_type: {covariance_type!r}")

    means_shape = (n_components, n_features)
    weights = np.empty(n_components)
    means = np.empty(means_shape)
    covars = np.empty(covar_shape)
    return weights, means, covars


__all__ = [
    "COVARIANCE_TYPES",
    "DEFAULT_MIN_COVAR",
    "logsumexp",
    "_gaussian_parameters",
    "_log_gaussian_density",
    "_broadcast_covariance",
]
