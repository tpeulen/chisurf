"""Adam optimiser for the multilayer perceptron.

Implements Kingma & Ba's Adam with the exact parameter combination
scikit-learn's ``_stochastic_optimizers.AdamOptimizer`` uses: learning rate
0.001, ``beta1=0.9``, ``beta2=0.999``, and the time-dependent bias correction
``lr_t = lr * sqrt(1 - beta2^t) / (1 - beta1^t)`` applied to the raw moments.
"""

from __future__ import annotations

import numpy as np


class AdamOptimizer:
    """Adam with bias-corrected moments and a global learning rate.

    Parameters
    ----------
    params : list of numpy.ndarray
        The weight and bias arrays being optimised.
    learning_rate_init : float, default 1e-3
        Base learning rate.
    beta1 : float, default 0.9
        Exponential decay for the first moment.
    beta2 : float, default 0.999
        Exponential decay for the second moment.
    epsilon : float, default 1e-8
        Numerical guard in the parameter update.
    """

    def __init__(
        self,
        params,
        learning_rate_init: float = 1e-3,
        beta1: float = 0.9,
        beta2: float = 0.999,
        epsilon: float = 1e-8,
    ):
        if not isinstance(params, list) or len(params) < 2:
            raise ValueError("Adam needs a list of at least two parameter arrays")

        self.params = params
        self.learning_rate_init = learning_rate_init
        self.beta1 = beta1
        self.beta2 = beta2
        self.epsilon = epsilon

        self.t = 0
        self.ms = [np.zeros_like(p) for p in params]
        self.vs = [np.zeros_like(p) for p in params]
        self.learning_rate = learning_rate_init

    def update(self, grads: list[np.ndarray]) -> None:
        """One optimisation step from the gradient of every parameter.

        Parameters
        ----------
        grads : list of numpy.ndarray
            Gradients in the same order as ``params``.
        """
        self.t += 1
        for i, (param, grad) in enumerate(zip(self.params, grads)):
            if grad is None:
                continue
            self.ms[i] = self.beta1 * self.ms[i] + (1.0 - self.beta1) * grad
            self.vs[i] = self.beta2 * self.vs[i] + (1.0 - self.beta2) * grad**2

        self.learning_rate = (
            self.learning_rate_init * np.sqrt(1.0 - self.beta2**self.t) / (1.0 - self.beta1**self.t)
        )
        for i, param in enumerate(self.params):
            param -= self.learning_rate * self.ms[i] / (np.sqrt(self.vs[i]) + self.epsilon)


__all__ = ["AdamOptimizer"]
