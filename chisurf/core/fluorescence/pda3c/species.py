r"""Correlated three-distance species and the quadrature that integrates them.

A tcPDA species is a **trivariate Gaussian** over $(R_{GR}, R_{BG}, R_{BR})$
with a full covariance matrix. The off-diagonal entries are the reason to do
three-colour FRET at all: three separate two-colour experiments give three
marginal distributions and can never say whether the distances move *together*.
Fitting the covariance is what distinguishes one conformational coordinate from
three independent ones.

Two things follow from the species being Gaussian.

**Parameterisation.** An optimiser stepping six covariance entries freely leaves
the positive-definite cone within a step or two, and a non-PD covariance is not
a distribution. The free parameters are therefore the entries of a lower
triangular Cholesky factor $L$ with positive diagonal, and
$\Sigma = L L^{\mathsf T}$ is positive definite by construction — no repair
step, no rejected proposals. :func:`covariance_to_cholesky` and
:func:`cholesky_to_statistics` convert to and from the user-facing
$(\sigma_i, \rho_{ij})$ view, and :func:`nearest_positive_definite` exists for
ingesting a covariance from outside that may not be valid.

**Integration.** Integrating a Gaussian on a uniform grid is the wrong
quadrature: cost is $O(n^3)$ in the resolution and most nodes sit where the
density is negligible. Substituting $R = \mu + \sqrt{2}\,L z$ turns the integral
into the Gauss–Hermite weight function exactly, so a handful of nodes per axis
reaches accuracy a uniform grid needs tens for. :func:`gauss_hermite_grid`
returns the nodes and their (normalised) weights.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "cholesky_to_statistics",
    "covariance_from_statistics",
    "covariance_to_cholesky",
    "gauss_hermite_grid",
    "nearest_positive_definite",
]


def covariance_from_statistics(sigmas, correlations) -> np.ndarray:
    """Build a covariance matrix from standard deviations and correlations.

    Parameters
    ----------
    sigmas : array_like
        Standard deviations, shape ``(K,)``, positive.
    correlations : array_like
        Off-diagonal correlation coefficients in the order
        ``(rho_01, rho_02, rho_12)`` for ``K = 3``; each in ``(-1, 1)``.

    Returns
    -------
    numpy.ndarray
        Symmetric ``(K, K)`` covariance. Not guaranteed positive definite —
        three pairwise correlations can be mutually inconsistent (e.g. all
        ``-0.9``); pass the result through :func:`nearest_positive_definite` if
        it came from user input.
    """
    sigmas = np.asarray(sigmas, dtype=float)
    correlations = np.asarray(correlations, dtype=float)
    k = sigmas.size

    corr = np.eye(k)
    idx = 0
    for i in range(k):
        for j in range(i + 1, k):
            corr[i, j] = corr[j, i] = correlations[idx]
            idx += 1
    return corr * np.outer(sigmas, sigmas)


def nearest_positive_definite(matrix, jitter: float = 1e-10) -> np.ndarray:
    """Return the nearest symmetric positive-definite matrix.

    Symmetrises, clips the eigenvalues at a small positive floor, and rebuilds.
    Used only for covariances arriving from outside the fit (user input, a saved
    session); inside the fit the Cholesky parameterisation makes this
    unnecessary by construction.

    Parameters
    ----------
    matrix : array_like
        Square, approximately symmetric.
    jitter : float
        Eigenvalue floor, relative to the largest eigenvalue.

    Returns
    -------
    numpy.ndarray
        Symmetric positive-definite matrix.
    """
    matrix = np.asarray(matrix, dtype=float)
    symmetric = 0.5 * (matrix + matrix.T)
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    floor = max(jitter * float(np.max(np.abs(eigenvalues))), jitter)
    return (eigenvectors * np.maximum(eigenvalues, floor)) @ eigenvectors.T


def covariance_to_cholesky(covariance) -> np.ndarray:
    """Return the lower-triangular Cholesky factor of a covariance matrix.

    Repairs the matrix first if it is not positive definite, so this is safe on
    user-supplied input.

    Parameters
    ----------
    covariance : array_like
        Symmetric ``(K, K)`` covariance.

    Returns
    -------
    numpy.ndarray
        Lower-triangular ``(K, K)`` factor ``L`` with ``L @ L.T == covariance``.
    """
    covariance = np.asarray(covariance, dtype=float)
    try:
        return np.linalg.cholesky(covariance)
    except np.linalg.LinAlgError:
        return np.linalg.cholesky(nearest_positive_definite(covariance))


def cholesky_to_statistics(cholesky):
    """Return ``(sigmas, correlations)`` for a Cholesky factor.

    The reporting direction: the fit moves ``L``, the user reads widths and
    correlations.

    Parameters
    ----------
    cholesky : array_like
        Lower-triangular ``(K, K)`` factor.

    Returns
    -------
    sigmas : numpy.ndarray
        Standard deviations, shape ``(K,)``.
    correlations : numpy.ndarray
        Off-diagonal correlations in the order ``(rho_01, rho_02, rho_12)``.
    """
    cholesky = np.asarray(cholesky, dtype=float)
    covariance = cholesky @ cholesky.T
    sigmas = np.sqrt(np.diag(covariance))
    k = sigmas.size
    correlations = []
    for i in range(k):
        for j in range(i + 1, k):
            denominator = sigmas[i] * sigmas[j]
            correlations.append(covariance[i, j] / denominator if denominator > 0 else 0.0)
    return sigmas, np.asarray(correlations, dtype=float)


def gauss_hermite_grid(means, cholesky, n_nodes: int = 7, truncate: float = 0.0):
    r"""Return quadrature nodes and weights for a multivariate Gaussian species.

    Uses the substitution :math:`R = \mu + \sqrt{2}\, L z`, which maps the
    Gaussian exactly onto the Gauss–Hermite weight :math:`e^{-z^2}`, so
    ``n_nodes`` per axis integrates a polynomial of degree ``2*n_nodes - 1``
    exactly against the true density. A uniform grid over the same region needs
    an order of magnitude more nodes for comparable accuracy and spends most of
    them where the density is negligible.

    Parameters
    ----------
    means : array_like
        Mean distances, shape ``(K,)``.
    cholesky : array_like
        Lower-triangular ``(K, K)`` factor of the covariance.
    n_nodes : int
        Nodes per axis; the tensor grid has ``n_nodes ** K`` points.
    truncate : float
        Drop nodes whose normalised weight falls below this. The tensor grid's
        corner nodes carry negligible weight, so a small value (e.g. ``1e-6``)
        removes a large fraction of the points for no measurable change.

    Returns
    -------
    points : numpy.ndarray
        Distances, shape ``(M, K)``. Clipped at zero — a Gaussian in distance
        space has support below zero and a negative distance is not physical.
    weights : numpy.ndarray
        Normalised weights summing to one, shape ``(M,)``.
    """
    means = np.asarray(means, dtype=float)
    cholesky = np.asarray(cholesky, dtype=float)
    k = means.size

    nodes, node_weights = np.polynomial.hermite.hermgauss(int(n_nodes))
    # e^{-z^2} weight -> standard normal via z = x * sqrt(2), weights / sqrt(pi).
    grids = np.meshgrid(*([nodes] * k), indexing="ij")
    weight_grids = np.meshgrid(*([node_weights] * k), indexing="ij")

    z = np.stack([g.ravel() for g in grids], axis=1) * np.sqrt(2.0)
    weights = np.prod(np.stack([w.ravel() for w in weight_grids], axis=1), axis=1)
    weights = weights / weights.sum()

    if truncate > 0.0:
        keep = weights >= truncate
        if np.any(keep):
            z = z[keep]
            weights = weights[keep]
            weights = weights / weights.sum()

    points = means[None, :] + z @ cholesky.T
    return np.clip(points, 0.0, None), weights
