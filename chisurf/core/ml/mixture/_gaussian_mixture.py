"""Expectation-maximisation for Gaussian mixtures, with component locking.

This is the estimator the burst-selection call sites reach for. Beyond the
scikit-learn surface (``covariance_type`` in all four layouts, ``n_init``
restarts, ``aic``/``bic``, ``score_samples``) it implements the one extension
the companion photon-data exploration tool needed an entire private EM for:
``fix_means`` / ``fix_covariances`` masks that hold a subset of a component's
location or spread exactly in place while the rest of the mixture is fitted.
Holding a parameter must leave it *exactly* unchanged (``< 1e-15``), not merely
nearly so, which is the property the fixed-fit test pins.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..base import BaseEstimator
from .._gaussian import (
    COVARIANCE_TYPES,
    _broadcast_covariance,
    _log_gaussian_density,
    _responsibilities,
    _row_logsumexp,
    logsumexp,
)

#: Log-domain floor for responsibilities: a component with zero weight must not
#: feed ``0 * log 0 = nan`` into the E-step.
_LOG_RESP_FLOOR = -np.inf


def _n_parameters(covariance_type: str, n_features: int, n_components: int) -> int:
    """Return the number of free parameters a fitted layout holds."""
    if covariance_type == "full":
        cov_params = n_components * n_features * (n_features + 1) / 2.0
    elif covariance_type == "diag":
        cov_params = n_components * n_features
    elif covariance_type == "tied":
        cov_params = n_features * (n_features + 1) / 2.0
    elif covariance_type == "spherical":
        cov_params = n_components
    else:
        raise ValueError(f"invalid covariance_type: {covariance_type!r}")
    mean_params = n_features * n_components
    return int(cov_params + mean_params + n_components - 1)


class GaussianMixture(BaseEstimator):
    """Gaussian Mixture fitted by expectation-maximisation.

    Parameters
    ----------
    n_components : int, default 1
        Number of mixture components.
    covariance_type : {"full", "tied", "diag", "spherical"}, default "full"
        Covariance parameterisation, named as scikit-learn names them.
    random_state : int or numpy.random.Generator, optional
        Seed for the k-means-style initialisation of weights and means.
    max_iter : int, default 100
        Maximum EM iterations per restart.
    n_init : int, default 1
        Number of restarts; the run with the best converged score wins.
    tol : float, default 1e-3
        Stop a restart when the improvement in the lower bound is below this.
    reg_covar : float, default 1e-6
        Ridge added to the diagonal of every covariance on each M-step.
    init_params : {"kmeans", "random"}, default "kmeans"
        How initial means and responsibilities are produced.
    weights_init, means_init, precisions_init : optional
        Explicit starting values. ``means_init`` is also the anchor the
        fixed-mean mask uses, exactly as the companion tool's EM took it.
    fix_means : optional array of bool, shape (n_components, n_features)
        ``True`` holds that mean element at the value in ``means_init``.
    fix_covariances : optional array of bool, shape (n_components, n_features,
        n_features)
        ``True`` holds that covariance element (symmetrised across the diagonal
        pair) at the value in ``means_init``'s companion ``covariances_init``.

    Attributes
    ----------
    weights_, means_, covariances_ : numpy.ndarray
        Fitted component parameters, in the compact layout of
        ``covariance_type``.
    n_iter_ : int
        EM iterations of the winning restart.
    lower_bound_ : float
        Log-likelihood of the winning restart.
    warm_start_ : ignored (accepted for interface parity).
    """

    def __init__(
        self,
        n_components: int = 1,
        covariance_type: str = "full",
        random_state: Optional[int] = None,
        max_iter: int = 100,
        n_init: int = 1,
        init_params: str = "kmeans",
        tol: float = 1e-3,
        reg_covar: float = 1e-6,
        weights_init: Optional[np.ndarray] = None,
        means_init: Optional[np.ndarray] = None,
        precisions_init: Optional[np.ndarray] = None,
        fix_means: Optional[np.ndarray] = None,
        fix_covariances: Optional[np.ndarray] = None,
        covariances_init: Optional[np.ndarray] = None,
    ):
        self.n_components = n_components
        self.covariance_type = covariance_type
        self.random_state = random_state
        self.max_iter = max_iter
        self.n_init = n_init
        self.init_params = init_params
        self.tol = tol
        self.reg_covar = reg_covar
        self.weights_init = weights_init
        self.means_init = means_init
        self.precisions_init = precisions_init
        self.fix_means = fix_means
        self.fix_covariances = fix_covariances
        self.covariances_init = covariances_init
        self._constructor_params = {
            "n_components", "covariance_type", "random_state", "max_iter",
            "n_init", "init_params", "tol", "reg_covar", "weights_init",
            "means_init", "precisions_init", "fix_means", "fix_covariances",
            "covariances_init",
        }

    # ------------------------------------------------------------------ fit --
    @property
    def covs_(self) -> np.ndarray:
        """Alias for :attr:`covariances_` — the companion tool's old spelling."""
        return self.covariances_

    @property
    def converged_(self) -> bool:
        """Whether the winning restart ran to tolerance (converged)."""
        return self.n_iter_ < self.max_iter

    def fit(self, X):
        """Fit the mixture to ``X`` and return ``self``.

        Parameters
        ----------
        X : numpy.ndarray
            ``(n_samples, n_features)`` floats.

        Returns
        -------
        GaussianMixture
            ``self``, fitted.
        """
        X = self._validate_data(X)
        n_samples, n_features = X.shape
        self.n_features_in_ = n_features

        if self.covariance_type not in COVARIANCE_TYPES:
            raise ValueError(f"invalid covariance_type: {self.covariance_type!r}")

        rng = np.random.default_rng(self.random_state)
        init = self._initialise(X, rng)

        # The fixed masks are stated once, at construction; their anchors are
        # the initial values, exactly as the companion tool's EM behaved.
        fix_means = (
            None if self.fix_means is None else np.asarray(self.fix_means, dtype=bool)
        )
        fix_covars = (
            None
            if self.fix_covariances is None
            else np.asarray(self.fix_covariances, dtype=bool)
        )
        fix_means_vals = (
            None if fix_means is None else np.array(init["means"], dtype=float, copy=True)
        )
        fix_covars_vals = (
            None if fix_covars is None else np.array(init["covars"], dtype=float, copy=True)
        )

        best = None
        best_lb = -np.inf
        best_iter = 0
        for _ in range(max(1, self.n_init)):
            if self.n_init > 1:
                init = self._initialise(X, rng)
            means, covars, weights = (init["means"], init["covars"], init["weights"])

            converged = self._em(
                X,
                means,
                covars,
                weights,
                fix_means=fix_means,
                fix_covars=fix_covars,
                fix_means_vals=fix_means_vals,
                fix_covars_vals=fix_covars_vals,
            )
            lb = self._score(X, means, covars, weights)
            if lb > best_lb or best is None:
                best = (means.copy(), covars.copy(), weights.copy())
                best_lb = lb
                best_iter = converged

        self.weights_ = best[2]
        self.means_ = best[0]
        self.covariances_ = best[1]
        self.n_iter_ = best_iter
        self.lower_bound_ = best_lb
        return self

    def _validate_data(self, X) -> np.ndarray:
        """Convert ``X`` to a finite float array, raising on empty input."""
        X = np.asarray(X, dtype=float)
        if X.ndim != 2:
            raise ValueError("Expected a 2-D array (samples, features).")
        if X.shape[0] == 0:
            raise ValueError("Expected at least 1 sample.")
        return X

    def _initialise(self, X, rng) -> dict:
        """Return starting (means, covars, weights) for a restart.

        Means are seeded with k-means++ (``init_params="kmeans"``) or drawn
        uniformly from the samples; covariances come from the within-cluster
        variance of that seeding. Explicit ``means_init`` / ``weights_init`` /
        ``covariances_init`` override the data-driven values, which is how the
        fixed-parameter fit is anchored.
        """
        n_samples, n_features = X.shape
        n_components = self.n_components
        if n_components > n_samples:
            raise ValueError(
                f"n_components={n_components} exceeds n_samples={n_samples}"
            )

        if self.init_params == "kmeans" and self.means_init is None:
            from ..cluster import _kmeans  # local: avoids a circular import

            _, labels, _, _ = _kmeans(
                X, n_components, rng, n_init=1, max_iter=100, tol=1e-4
            )
            means = np.vstack(
                [X[labels == c].mean(axis=0) for c in range(n_components)]
            )
        else:
            idx = rng.choice(n_samples, size=n_components, replace=False)
            means = X[idx]

        # weights init: uniform, unless given explicitly
        weights = np.full(n_components, 1.0 / n_components)
        if self.weights_init is not None:
            weights = np.asarray(self.weights_init, dtype=float)
            s = weights.sum()
            if s <= 0:
                weights = np.full(n_components, 1.0 / n_components)
            else:
                weights = weights / s

        # covariance init from data; explicit init wins (the companion tool
        # feeds the table rows here so a fixed covariance anchors on it).
        covars = self._init_covars(X, means, rng)
        if self.covariances_init is not None:
            candidate = np.asarray(self.covariances_init, dtype=float)
            expected = {
                "full": (n_components, n_features, n_features),
                "diag": (n_components, n_features),
                "spherical": (n_components,),
                "tied": (n_features, n_features),
            }[self.covariance_type]
            if candidate.shape == expected:
                covars = candidate
            else:
                covars = self._init_covars(X, means, rng)

        if self.means_init is not None:
            means = np.asarray(self.means_init, dtype=float)

        return {"means": means, "covars": covars, "weights": weights}

    def _init_covars(self, X, means, rng) -> np.ndarray:
        """Return data-driven covariance initialisation in the compact layout.

        Mirrors scikit-learn's init: a single fast k-means labels the data,
        the per-cluster *full* covariance of that labelling seeds the mixture.
        The seeded means are used for the floor when a cluster is empty.
        """
        n_components = self.n_components
        covar_type = self.covariance_type
        try:
            from ..cluster import _kmeans  # local import to avoid cycles

            _, labels, _, _ = _kmeans(X, n_components, rng, n_init=1, max_iter=50, tol=1e-4)
            reg = self.reg_covar
            full = np.zeros((n_components, X.shape[1], X.shape[1]))
            for c in range(n_components):
                m = labels == c
                if m.sum() > 1:
                    full[c] = np.cov(X[m].T, rowvar=True) + reg * np.eye(X.shape[1])
                else:
                    full[c] = np.diag(X.var(axis=0)) + reg * np.eye(X.shape[1])
            full = np.maximum(full, np.finfo(float).tiny)
        except Exception:
            reg = self.reg_covar
            full = np.tile(
                np.diag(np.maximum(X.var(axis=0), np.finfo(float).tiny))
                + reg * np.eye(X.shape[1]),
                (n_components, 1, 1),
            )

        if covar_type == "full":
            return full
        if covar_type == "diag":
            return full[:, np.arange(X.shape[1]), np.arange(X.shape[1])].copy()
        if covar_type == "spherical":
            return np.trace(full, axis1=1, axis2=2) / X.shape[1]
        if covar_type == "tied":
            return full.mean(axis=0)

    # ----------------------------------------------------------------- EM ----

    def _em(
        self,
        X,
        means,
        covars,
        weights,
        fix_means=None,
        fix_covars=None,
        fix_means_vals=None,
        fix_covars_vals=None,
    ) -> int:
        """Run EM in place; return the number of iterations that ran."""
        n_samples, n_features = X.shape
        n_components = self.n_components
        reg = self.reg_covar
        tol = self.tol

        prev_lb = -np.inf
        for it in range(1, self.max_iter + 1):
            # E-step -----------------------------------------------------------------
            log_prob = _log_gaussian_density(
                X, means, covars, self.covariance_type, reg
            )
            with np.errstate(divide="ignore"):
                log_prob += np.log(np.maximum(weights, np.finfo(float).tiny))[None, :]
            lb = _log_likelihood(log_prob)

            # responsibilities -- shared with the HMM/1-D callers, and guards a
            # sample no component can explain (a row of -inf, whose naive
            # `-inf - (-inf)` is nan) into a uniform responsibility instead.
            resp = _responsibilities(log_prob)

            # M-step -----------------------------------------------------------------
            Nk = resp.sum(axis=0)
            Nk = np.maximum(Nk, np.finfo(float).tiny)
            weights[:] = Nk / n_samples

            # means
            new_means = (resp.T @ X) / Nk[:, None]
            if fix_means is not None:
                assert fix_means_vals is not None
                new_means[fix_means] = fix_means_vals[fix_means]
            means[:] = new_means

            # covariances
            if self.covariance_type == "full":
                new_covs = np.zeros_like(covars)
                for c in range(n_components):
                    diff = X - means[c]
                    Sk = (resp[:, c][:, None] * diff).T @ diff / Nk[c]
                    Sk = _clamp_covar(Sk) + reg * np.eye(n_features)
                    new_covs[c] = Sk
                if fix_covars is not None:
                    assert fix_covars_vals is not None
                    self._apply_cov_fix(new_covs, fix_covars, fix_covars_vals, reg, n_features)
                covars[:] = new_covs
            elif self.covariance_type == "diag":
                diff = X[:, None, :] - means[None]
                new_covs = ((resp[:, :, None] * diff) ** 2).sum(axis=0) / Nk[:, None]
                new_covs = np.maximum(new_covs, np.finfo(float).tiny) + reg
                if fix_covars is not None:
                    assert fix_covars_vals is not None
                    new_covs[fix_covars] = fix_covars_vals[fix_covars]
                covars[:] = new_covs
            elif self.covariance_type == "spherical":
                diff = X[:, None, :] - means[None]
                s2 = (((resp[:, :, None] * diff) ** 2).sum(axis=0)).mean(axis=1)
                s2 = s2 / Nk
                new_covs = np.maximum(s2, np.finfo(float).tiny) + reg
                if fix_covars is not None:
                    assert fix_covars_vals is not None
                    new_covs[fix_covars] = fix_covars_vals[fix_covars]
                covars[:] = new_covs
            elif self.covariance_type == "tied":
                acc = np.zeros((n_features, n_features))
                for c in range(n_components):
                    diff = X - means[c]
                    acc += (resp[:, c][:, None] * diff).T @ diff
                new_c = acc / n_samples + reg * np.eye(n_features)
                new_c = _clamp_covar(new_c)
                if fix_covars is not None:
                    assert fix_covars_vals is not None
                    new_c[fix_covars] = fix_covars_vals[fix_covars]
                    new_c = 0.5 * (new_c + new_c.T)
                    new_c = _clamp_covar(new_c)
                covars[:] = new_c

            if lb - prev_lb < tol:
                return it
            prev_lb = lb
        return self.max_iter

    def _apply_cov_fix(self, new_covs, fix_covars, fix_covars_vals, reg, n_features):
        """Stamp fixed covariance elements in place, keeping symmetry.

        A fixed element is held *exactly*: it is stamped after the data-driven
        M-step (including its ridge), mirroring how the companion tool's EM
        treated ``cov_fixed_vals`` — the row's current value — as the final
        word. Symmetry is restored by mirroring the fixed off-diagonal element
        onto its mate.
        """
        for c in range(new_covs.shape[0]):
            M = fix_covars[c]
            if not np.any(M):
                continue
            C = fix_covars_vals[c]
            # Mirror the fixed off-diagonal elements to keep the matrix symmetric,
            # then stamp both members.
            full = M.copy()
            if M.shape[0] == M.shape[1] and M.shape[0] == 2:
                full[0, 1] = full[1, 0] = bool(M[0, 1] or M[1, 0])
            new_covs[c][full] = C[full]
            new_covs[c] = 0.5 * (new_covs[c] + new_covs[c].T)

    # ---------------------------------------------------------------- score --

    def _log_proba(self, X, means, covars, weights) -> np.ndarray:
        """Log probability of each sample under each component plus weight."""
        log_prob = _log_gaussian_density(X, means, covars, self.covariance_type, self.reg_covar)
        with np.errstate(divide="ignore"):
            log_prob += np.log(np.maximum(weights, np.finfo(float).tiny))[None, :]
        return log_prob

    def _score(self, X, means, covars, weights):
        """Total log-likelihood of the data under the components."""
        return _log_likelihood(self._log_proba(X, means, covars, weights))

    def score_samples(self, X) -> np.ndarray:
        """Return the per-sample log probability, shape ``(n_samples,)``."""
        X = np.asarray(X, dtype=float)
        log_prob = self._log_proba(X, self.means_, self.covariances_, self.weights_)
        return _row_logsumexp(log_prob)

    def fit_predict(self, X) -> np.ndarray:
        """Fit the mixture and return the hard cluster labels of ``X``."""
        self.fit(X)
        return self._log_proba(
            np.asarray(X, dtype=float), self.means_, self.covariances_, self.weights_
        ).argmax(axis=1)

    def predict(self, X) -> np.ndarray:
        """Return the cluster label of the highest-probability component per row."""
        return self.predict_proba(X).argmax(axis=1)

    def predict_proba(self, X) -> np.ndarray:
        """Return the posterior component probabilities, shape ``(n, K)``."""
        log_prob = self._log_proba(
            np.asarray(X, dtype=float), self.means_, self.covariances_, self.weights_
        )
        return _responsibilities(log_prob)

    def _n_parameters(self) -> int:
        """Number of free parameters of the fitted layout."""
        return _n_parameters(self.covariance_type, self.means_.shape[1], self.weights_.shape[0])

    def aic(self, X) -> float:
        """Akaike information criterion, ``2k - 2LL`` (lower is better)."""
        X = np.asarray(X, dtype=float)
        total_ll = self.score_samples(X).sum()
        return 2.0 * self._n_parameters() - 2.0 * float(total_ll)

    def bic(self, X) -> float:
        """Bayesian information criterion, ``k ln n - 2LL`` (lower is better)."""
        X = np.asarray(X, dtype=float)
        total_ll = self.score_samples(X).sum()
        return self._n_parameters() * np.log(len(X)) - 2.0 * float(total_ll)

    def score(self, X) -> float:
        """Per-sample (mean) log-likelihood of ``X``, as scikit-learn defines it."""
        return float(np.mean(self.score_samples(X)))


def _log_likelihood(log_prob: np.ndarray) -> float:
    """Log-sum-exp over components of ``log_prob`` rows, summed over samples.

    A row no component can explain contributes ``-inf`` (see
    :func:`chisurf.core.ml._gaussian._row_logsumexp`), not ``nan``: the total
    then correctly reads as "impossible under this mixture" instead of
    silently corrupting the whole log-likelihood.
    """
    return float(_row_logsumexp(log_prob).sum())


def _clamp_covar(M: np.ndarray) -> np.ndarray:
    """Project a symmetric matrix to the PSD cone via eigen clipping."""
    M = 0.5 * (M + M.T)
    ev, V = np.linalg.eigh(M)
    ev = np.maximum(ev, 1e-12)
    return (V * ev) @ V.T


__all__ = ["GaussianMixture", "_n_parameters", "_log_likelihood", "_clamp_covar",
           "_broadcast_covariance"]
