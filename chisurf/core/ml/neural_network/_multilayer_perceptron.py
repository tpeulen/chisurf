"""Multilayer perceptron regressor with early stopping.

This is the estimator the H2MM surrogate trains with. Its contract is the
--- however --- the surrogate only reads ``coefs_``, ``intercepts_``,
``activation``, ``out_activation_`` and ``predict``, so this port faithfully
implements exactly those: feed-forward ReLU network, mean-squared-error loss,
Adam updates with a 10% validation split when ``early_stopping=True``, and the
scikit-learn attribute names that ``SurrogateModel.to_json`` depends on.
"""

from __future__ import annotations

import numpy as np

from ..base import BaseEstimator
from ._base import ACTIVATIONS, DERIVATIVES
from ._stochastic_optimizers import AdamOptimizer

__all__ = ["MLPRegressor"]

#: Fraction held out for early stopping when enabled.
_VALIDATION_FRACTION = 0.1


class MLPRegressor(BaseEstimator):
    """Multi-layer perceptron regressor trained with Adam.

    Parameters
    ----------
    hidden_layer_sizes : tuple of int, default (100,)
        Number of neurons per hidden layer.
    activation : {"relu", "identity", "logistic", "tanh"}, default "relu"
        Hidden-layer activation. The output layer is always linear.
    solver : {"adam"}, default "adam"
        Optimiser; only Adam is implemented.
    max_iter : int, default 200
        Maximum training epochs.
    random_state : int, optional
        Seed for the weight initialisation and validation split.
    early_stopping : bool, default False
        Hold out ``validation_fraction`` of the fit input, track its loss, and
        stop once it has not improved for ``n_iter_no_change`` epochs.
    learning_rate_init : float, default 1e-3
        Adam base learning rate.
    n_iter_no_change : int, default 10
        Patience for early stopping.
    validation_fraction : float, default 0.1
        Share of the samples held out as the validation split.
    tol : float, default 1e-4
        Relative loss improvement floor for the no-change counter.
    batch_size : {"auto", int}, default "auto"
        ``"auto"`` uses min(200, n_samples); an int is the batch size.
    shuffle : bool, default True
        Shuffle the training data each epoch.
    verbose : bool, default False
        Accepted for interface parity; emits nothing.

    Attributes
    ----------
    coefs_ : list of numpy.ndarray
        Weight matrices, shape ``(n_in, n_out)`` per layer — the scikit-learn
        storage the surrogate's JSON export reads and transposes.
    intercepts_ : list of numpy.ndarray
        Bias vectors, one per layer.
    activation : str
        The hidden activation name (mirrors the ``activation`` argument).
    out_activation_ : str
        Always ``"identity"`` for a regressor.
    n_iter_ : int
        Epochs actually run.
    loss_ : float
        Final training loss.
    best_validation_score_ : float
        Best validation score (negative loss) when early stopping ran.
    validation_scores_, loss_curve_ : list
        Observed scores/losses per epoch.
    """

    def __init__(
        self,
        hidden_layer_sizes: tuple[int, ...] = (100,),
        activation: str = "relu",
        solver: str = "adam",
        max_iter: int = 200,
        random_state: int | None = None,
        early_stopping: bool = False,
        learning_rate_init: float = 1e-3,
        n_iter_no_change: int = 10,
        validation_fraction: float = 0.1,
        learning_rate: str = "constant",
        power_t: float = 0.5,
        shuffle: bool = True,
        batch_size: str | int = "auto",
        verbose: bool = False,
        tol: float = 1e-4,
    ):
        self.hidden_layer_sizes = hidden_layer_sizes
        self.activation = activation
        self.solver = solver
        self.max_iter = max_iter
        self.random_state = random_state
        self.early_stopping = early_stopping
        self.learning_rate_init = learning_rate_init
        self.n_iter_no_change = n_iter_no_change
        self.validation_fraction = validation_fraction
        self.learning_rate = learning_rate
        self.power_t = power_t
        self.shuffle = shuffle
        self.batch_size = batch_size
        self.verbose = verbose
        self.tol = tol
        self._constructor_params = {
            "hidden_layer_sizes",
            "activation",
            "solver",
            "max_iter",
            "random_state",
            "early_stopping",
            "learning_rate_init",
            "n_iter_no_change",
            "validation_fraction",
            "learning_rate",
            "power_t",
            "shuffle",
            "batch_size",
            "verbose",
            "tol",
        }

    # ------------------------------------------------------------------ fit --

    def fit(self, X, y):
        """Train the network on ``(X, y)`` and return ``self``.

        Parameters
        ----------
        X : numpy.ndarray
            ``(n_samples, n_features)`` training inputs.
        y : numpy.ndarray
            ``(n_samples,)`` or ``(n_samples, n_targets)`` targets.

        Returns
        -------
        MLPRegressor
            ``self``, trained.
        """
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        if y.ndim == 1:
            y = y[:, None]
        n_samples, n_features = X.shape
        n_outputs = y.shape[1]
        if len(X) == 0:
            raise ValueError("fit called with no samples")

        rng = np.random.default_rng(self.random_state)

        # Validation split for early stopping.
        if self.early_stopping and n_samples > 1:
            n_val = max(1, int(n_samples * self.validation_fraction))
            perm = rng.permutation(n_samples)
            val_idx, train_idx = perm[:n_val], perm[n_val:]
            X_train, y_train = X[train_idx], y[train_idx]
            X_val, y_val = X[val_idx], y[val_idx]
        else:
            X_train, y_train, X_val, y_val = X, y, None, None

        layers = list(self.hidden_layer_sizes) + [n_outputs]
        self.coefs_ = []
        self.intercepts_ = []
        in_size = n_features
        for out_size in layers:
            # He-style init: uniform in +/-sqrt(6/(n_in + n_out)).
            limit = np.sqrt(6.0 / (in_size + out_size))
            self.coefs_.append(rng.uniform(-limit, limit, (in_size, out_size)))
            self.intercepts_.append(np.zeros(out_size))
            in_size = out_size
        self.out_activation_ = "identity"
        fwd = ACTIVATIONS[self.activation]
        dfwd = DERIVATIVES[self.activation]
        n_hidden_layers = len(self.coefs_) - 1

        params = self.coefs_ + self.intercepts_
        opt = AdamOptimizer(params, learning_rate_init=self.learning_rate_init)

        batch = (
            max(1, min(200, len(X_train)))
            if self.batch_size == "auto" or self.batch_size is None
            else max(1, int(self.batch_size))
        )

        n_iter = 0
        best_val = -np.inf
        no_change = 0
        self.loss_curve_ = []
        self.validation_scores_ = []
        n_train = len(X_train)
        sw_sum = float(n_train)

        while n_iter < self.max_iter:
            n_iter += 1
            if self.shuffle:
                order = rng.permutation(len(X_train))
                Xb, yb = X_train[order], y_train[order]
            else:
                Xb, yb = X_train, y_train

            epoch_loss = 0.0
            # Accumulate gradients over the epoch, then take one Adam step,
            # exactly like sklearn: _fit_stochastic accumulates coef_grads /
            # intercept_grads across batches and divides by sw_sum once.
            acc_grads_w = [np.zeros_like(w) for w in self.coefs_]
            acc_grads_b = [np.zeros_like(b) for b in self.intercepts_]
            for start in range(0, len(Xb), batch):
                Xmb, ymb = Xb[start : start + batch], yb[start : start + batch]
                grads_w, grads_b, loss = self._backprop(Xmb, ymb, fwd, dfwd, n_hidden_layers)
                epoch_loss += loss * len(Xmb)
                for templ, src in zip(acc_grads_w, grads_w):
                    templ += src
                for templ, src in zip(acc_grads_b, grads_b):
                    templ += src

            # sklearn divides every gradient by sw_sum (total weight = n_train).
            grads = [g / sw_sum for g in acc_grads_w + acc_grads_b]
            opt.update(grads)

            self.loss_curve_.append(float(epoch_loss / n_train))

            if self.early_stopping:
                val_loss = self._loss(X_val, y_val)
                score = -val_loss
                self.validation_scores_.append(score)
                if score > best_val:
                    best_val = score
                    no_change = 0
                    # remember best weights
                    best_coefs = [w.copy() for w in self.coefs_]
                    best_intercepts = [b.copy() for b in self.intercepts_]
                else:
                    no_change += 1
                if no_change >= self.n_iter_no_change:
                    self.coefs_ = best_coefs
                    self.intercepts_ = best_intercepts
                    break
            else:
                if n_iter >= 2:
                    prev, cur = self.loss_curve_[-2], self.loss_curve_[-1]
                    if prev - cur < max(self.tol, self.tol * abs(cur)):
                        no_change += 1
                        if no_change >= self.n_iter_no_change:
                            break
                    else:
                        no_change = 0

        self.n_iter_ = n_iter
        self.loss_ = self.loss_curve_[-1] if self.loss_curve_ else float("nan")
        if self.early_stopping:
            self.best_validation_score_ = best_val
            self.best_loss_ = self._loss(X_train, y_train)
        else:
            self.best_validation_score_ = -self.loss_
            self.best_loss_ = self.loss_
        return self

    def _backprop(self, X, y, fwd, dfwd, n_hidden_layers):
        """Run one forward/backward pass; return gradient lists and batch loss."""
        # Forward pass, keeping pre-activations.
        preacts: list[np.ndarray] = []
        acts: list[np.ndarray] = [X]
        a = X
        for i, w in enumerate(self.coefs_):
            z = a @ w + self.intercepts_[i]
            preacts.append(z)
            a = fwd(z) if i < n_hidden_layers else z
            acts.append(a)
        yhat = acts[-1]

        delta = yhat - y
        loss = float(np.mean(np.sum(delta**2, axis=1)))

        grads_w = [np.zeros_like(w) for w in self.coefs_]
        grads_b = [np.zeros_like(b) for b in self.intercepts_]

        # Backward: delta at the output is dL/dz_out = (yhat - y), and the 2/n
        # from the square loss is folded here (2 * delta / n_total).
        grad = 2.0 * delta
        for i in range(len(self.coefs_) - 1, -1, -1):
            grads_w[i] = acts[i].T @ grad
            grads_b[i] = grad.sum(axis=0)
            if i > 0:
                grad = (grad @ self.coefs_[i].T) * dfwd(preacts[i - 1])
        return grads_w, grads_b, loss

    # --------------------------------------------------------------- predict --

    def predict(self, X) -> np.ndarray:
        """Return the network's regression output for ``X``.

        Parameters
        ----------
        X : numpy.ndarray
            ``(n_samples, n_features)`` inputs.

        Returns
        -------
        numpy.ndarray
            Predictions, raveled to ``(n_samples,)`` when the network has a
            single output, else ``(n_samples, n_outputs)``.
        """
        X = np.asarray(X, dtype=float)
        fwd = ACTIVATIONS[self.activation]
        out = X
        for i, w in enumerate(self.coefs_):
            out = out @ w + self.intercepts_[i]
            if i < len(self.coefs_) - 1:
                out = fwd(out)
        if out.shape[1] == 1:
            return out.ravel()
        return out

    def _loss(self, X, y) -> float:
        """Mean squared error of the current network on ``(X, y)``."""
        pred = self.predict(X)
        target = np.asarray(y, dtype=float)
        if target.ndim == 1:
            pred = pred.ravel()
            target = target
        else:
            pred = pred.reshape(target.shape)
        return float(np.mean((pred - target) ** 2))


__all__ = ["MLPRegressor"]
