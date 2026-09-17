"""Estimator base classes, mirroring the small surface scikit-learn provides.

This module deliberately implements only the parts of the estimator contract
the tree actually reaches for: ``get_params``/``set_params`` (used by clone
patterns and call sites that introspect configuration), ``__repr__``, and the
``fit``-and-return-``self`` convention. Nothing else is present — no metadata
routing, no ``set_output``, no ``n_jobs``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any


def _safe_repr(value: Any) -> str:
    """Return ``repr(value)`` truncated like scikit-learn's ``_safe_repr``.

    Long parameters (arrays, dataframes) would make ``__repr__`` unusable as a
    config summary, so anything wider than ``MAX_WIDTH`` is shortened.
    """
    MAX_WIDTH = 70
    text = repr(value)
    if len(text) >= MAX_WIDTH:
        text = text[: MAX_WIDTH - 1] + "…"
    return text


class BaseEstimator(ABC):
    """Shared estimator state machine: parameter access and the fit contract.

    Parameters
    ----------
    **kwargs : dict
        Exposed as attributes. Subclasses that want constructor parameters to
        appear in :meth:`get_params` must store them under the same name.
    """

    @abstractmethod
    def fit(self, X, y=None):
        """Fit the estimator and return ``self``."""

    def get_params(self, deep: bool = True) -> dict[str, Any]:
        """Return the constructor parameters of this estimator.

        Parameters
        ----------
        deep : bool
            Accepted for interface parity. Deep copies are only possible for
            parameters that have a ``get_params`` themselves, which the
            estimators here never nest, so it is accepted and ignored.

        Returns
        -------
        dict
            ``param name -> value`` for every attribute that matches a
            constructor parameter name.
        """
        names = getattr(self, "_constructor_params", {})
        return {
            name: deepcopy(getattr(self, name)) if deep else getattr(self, name) for name in names
        }

    def set_params(self, **params: Any) -> BaseEstimator:
        """Set constructor parameters, validating that they exist.

        Parameters
        ----------
        **params : dict
            ``name -> value`` for parameters to change.

        Returns
        -------
        BaseEstimator
            ``self``, for chaining.
        """
        valid = getattr(self, "_constructor_params", {})
        for name, value in params.items():
            if name not in valid:
                raise ValueError(
                    f"Invalid parameter {name!r} for estimator {type(self).__name__}. "
                    f"Valid parameters are: {sorted(valid)!r}."
                )
            setattr(self, name, value)
        return self

    def __repr__(self) -> str:
        """Return a compact, parameterised summary like scikit-learn's."""
        params = self.get_params(deep=False)
        body = ", ".join(f"{name}={_safe_repr(value)}" for name, value in sorted(params.items()))
        return f"{type(self).__name__}({body})"

    def _validate_params(
        self, *, n_features: int, n_components: int, **bounds: dict[str, Any]
    ) -> None:
        """Validate a component-style estimator against its bounds.

        Parameters
        ----------
        n_features : int
            Observed feature count, from the fit input.
        n_components : int
            Requested component count, already clamped to the data.
        **bounds : dict
            ``name -> {"min": int, "max": int}``. Misses: scikit-learn raises
            ``ValueError`` for out-of-range values; the wrapped names are the
            historical ones (``n_features_in_``).
        """
        if n_components < 1:
            raise ValueError(f"n_components should be >= 1, got {n_components}")
        if n_components > n_features:
            raise ValueError(
                f"n_components={n_components} must be <= n_features={n_features} "
                f"for covariance_type='full'"
            )


__all__ = ["BaseEstimator", "_safe_repr"]
