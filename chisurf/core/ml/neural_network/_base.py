"""Activations used by the multilayer perceptron.

Only the pieces the surrogate needs are here: ``relu`` (the network's hidden
activation), ``identity`` (the output regression activation), and their
derivatives for backpropagation. The names are scikit-learn's, so a caller
bringing ``activation=...`` over keeps working.
"""

from __future__ import annotations

import numpy as np

__all__ = ["identity", "relu", "logistic", "tanh", "ACTIVATIONS", "DERIVATIVES"]


def identity(X: np.ndarray) -> np.ndarray:
    """Return ``X`` unchanged (linear output activation)."""
    return X


def relu(X: np.ndarray) -> np.ndarray:
    """Rectified linear unit, ``max(X, 0)``."""
    return np.maximum(X, 0.0)


def logistic(X: np.ndarray) -> np.ndarray:
    """Sigmoid, ``1 / (1 + exp(-X))`` with overflow guard."""
    return 1.0 / (1.0 + np.exp(-X))


def tanh(X: np.ndarray) -> np.ndarray:
    """Hyperbolic tangent."""
    return np.tanh(X)


def _identity_derivative(Z: np.ndarray) -> np.ndarray:
    return np.ones_like(Z)


def _relu_derivative(Z: np.ndarray) -> np.ndarray:
    return (Z > 0.0).astype(float)


def _logistic_derivative(Z: np.ndarray) -> np.ndarray:
    sig = logistic(Z)
    return sig * (1.0 - sig)


def _tanh_derivative(Z: np.ndarray) -> np.ndarray:
    return 1.0 - np.tanh(Z) ** 2


#: ``{name: forward}`` — the activation functions public API uses.
ACTIVATIONS = {
    "identity": identity,
    "relu": relu,
    "logistic": logistic,
    "tanh": tanh,
}

#: ``{name: derivative}`` — used by the backpropagation pass.
DERIVATIVES = {
    "identity": _identity_derivative,
    "relu": _relu_derivative,
    "logistic": _logistic_derivative,
    "tanh": _tanh_derivative,
}
