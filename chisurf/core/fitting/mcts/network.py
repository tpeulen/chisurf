"""TCSPCNet: a small 1D convolutional policy/value network, in pure NumPy.

Why NumPy and not PyTorch/TensorFlow: the core deliberately ships no deep-
learning runtime (``chisurf.core.ml`` exists precisely because scikit-learn
and friends were dropped), and the network here is *small* — two conv layers
over a 128-bin observation and two heads. A hand-written forward/backward pass
with the existing :class:`~chisurf.core.ml.neural_network._stochastic_
optimizers.AdamOptimizer` keeps the MCTS engine importable everywhere the rest
of chisurf is, including the GUI thread and headless CI.

Architecture (AlphaZero-style, adapted to one-dimensional counting data):

- **Trunk**: two valid-correlation Conv1D layers (kernel 5) with ReLU over the
  three observation channels (decay, IRF, residuals), followed by global mean
  and max pooling.
- **Auxiliary input**: the four structure features (component count, the three
  toggles) are concatenated after pooling — the policy cannot be a function of
  the decay alone, because the same residuals mean different things depending
  on what is already in the model.
- **Policy head**: linear output over the :class:`DiscreteAction` space;
  invalid actions are masked before the softmax.
- **Value head**: ``tanh`` output in ``[-1, 1]``, trained to predict the
  reward improvement of the state relative to the search root (squashed), so
  the scalar is comparable across decays with different photon counts.

Training examples come from tree searches (:mod:`chisurf.core.fitting.mcts.
mcts`): the policy target is the normalised visit distribution of a node's
children, the value target the reward difference — the same self-play recipe
as AlphaZero, at the scale of one histogram.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

from chisurf.core.ml.neural_network._stochastic_optimizers import AdamOptimizer

from chisurf.core.fitting.mcts.environment import N_ACTIONS, N_TOGGLE_SLOTS

#: Logit substituted for masked (invalid) actions before the softmax. Large
#: enough to underflow their probabilities to zero, finite enough to keep the
#: softmax numerically stable (no NaN from ``inf - inf``).
_MASK_LOGIT = -1e9

#: Element-wise gradient clip. Self-play targets are noisy early in training;
#: a clipped step direction is better than a diverged network.
_GRAD_CLIP = 5.0


def masked_softmax(logits: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Softmax over the valid actions only.

    Parameters
    ----------
    logits : numpy.ndarray
        Shape ``(n_actions,)`` or ``(batch, n_actions)``.
    valid : numpy.ndarray
        Boolean mask of the same shape; ``False`` entries receive zero
        probability.

    Returns
    -------
    numpy.ndarray
        Probability distribution(s) summing to one over the valid entries.
    """
    logits = np.asarray(logits, dtype=float)
    valid = np.asarray(valid, dtype=bool)
    masked = np.where(valid, logits, _MASK_LOGIT)
    shifted = masked - masked.max(axis=-1, keepdims=True)
    exp = np.exp(shifted) * valid
    total = exp.sum(axis=-1, keepdims=True)
    total = np.where(total > 0.0, total, 1.0)
    return exp / total


class Conv1D:
    """Valid-correlation 1D convolution layer with He initialisation.

    The input/output layout is ``(batch, in_channels, length)``; the kernel
    ``W`` has shape ``(out_channels, in_channels, kernel)`` and the forward
    pass is ``y[b, o, l] = Σ_{i,k} x[b, i, l+k] · W[o, i, k] + b[o]``.
    """

    def __init__(self, in_channels: int, out_channels: int, kernel: int, rng: np.random.Generator):
        self.kernel = int(kernel)
        self.W = rng.normal(
            0.0,
            math.sqrt(2.0 / (in_channels * kernel)),
            size=(out_channels, in_channels, kernel),
        )
        self.b = np.zeros(out_channels, dtype=float)

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Pre-activations of length ``L - kernel + 1``."""
        from numpy.lib.stride_tricks import sliding_window_view

        self._x = np.asarray(x, dtype=float)
        windows = sliding_window_view(self._x, self.kernel, axis=2)  # (B, C, L', k)
        # The channel axis carries the same letter on both operands — 'c' —
        # so the channel dimension is contracted elementwise, not summed
        # independently (a stray second letter would turn the layer into a
        # channel-summing projection and silently break the backward pass).
        return np.einsum('bclk,ock->bol', windows, self.W, optimize=True) \
            + self.b[None, :, None]

    def backward(self, dout: np.ndarray) -> np.ndarray:
        """Accumulate ``self.dW``/``self.db`` and return ``dx``.

        The gradients follow from the index form of the forward pass:
        ``dW[o,i,k] = Σ_{b,l} dout[b,o,l]·x[b,i,l+k]`` and
        ``dx[b,i,t] = Σ_{o,k} dout[b,o,t−k]·W[o,i,k]``; both are computed with
        a short loop over the (small) kernel axis, which stays cheaper and far
        simpler to verify than a strided general convolution.
        """
        x = self._x
        out_len = dout.shape[2]
        self.dW = np.zeros_like(self.W)
        self.db = dout.sum(axis=(0, 2))
        dx = np.zeros_like(x)
        for k in range(self.kernel):
            # dW[:, :, k] pairs dout[:, :, l] with x[:, :, l + k]
            xs = x[:, :, k:k + out_len]
            self.dW[:, :, k] = np.einsum('bol,bil->oi', dout, xs, optimize=True)
            # dx[:, :, t] receives dout[:, :, t - k] weighted by W[:, :, k];
            # the t-k index shift means the contribution is computed at the
            # output length and accumulated into the input-length buffer.
            dx[:, :, k:k + out_len] += np.einsum(
                'bol,oi->bil', dout, self.W[:, :, k], optimize=True
            )
        return dx

    @property
    def parameters(self) -> List[np.ndarray]:
        return [self.W, self.b]

    @property
    def gradients(self) -> List[np.ndarray]:
        return [self.dW, self.db]


class Dense:
    """Fully-connected layer, ``(batch, in) -> (batch, out)``."""

    def __init__(self, n_in: int, n_out: int, rng: np.random.Generator):
        self.W = rng.normal(0.0, math.sqrt(2.0 / n_in), size=(n_in, n_out))
        self.b = np.zeros(n_out, dtype=float)

    def forward(self, x: np.ndarray) -> np.ndarray:
        self._x = np.asarray(x, dtype=float)
        return self._x @ self.W + self.b

    def backward(self, dout: np.ndarray) -> np.ndarray:
        self.dW = self._x.T @ dout
        self.db = dout.sum(axis=0)
        return dout @ self.W.T

    @property
    def parameters(self) -> List[np.ndarray]:
        return [self.W, self.b]

    @property
    def gradients(self) -> List[np.ndarray]:
        return [self.dW, self.db]


@dataclass
class NetConfig:
    """Layer sizes of :class:`TCSPCNet`.

    Parameters
    ----------
    channels : tuple of int
        Output channels of the convolutional layers, trunk to head.
    kernel : int
        Convolution kernel width (bins).
    hidden : int
        Width of the shared hidden layer after pooling.
    """

    channels: Tuple[int, int] = (16, 32)
    kernel: int = 5
    hidden: int = 64


class TCSPCNet:
    """Policy/value network over TCSPC fitting states.

    Parameters
    ----------
    obs_length : int
        Length of each observation channel (the environment's
        ``config.obs_length``).
    n_obs_channels : int
        Number of observation channels (decay/IRF/residuals → 3).
    n_structure_features : int
        Width of the auxiliary structure input (4).
    n_actions : int
        Width of the policy head.
    config : NetConfig, optional
        Layer sizes.
    seed : int, optional
        Weight-initialisation seed; training is deterministic for a fixed seed
        and data order.
    """

    def __init__(
        self,
        obs_length: int = 128,
        n_obs_channels: int = 3 + 7 + N_TOGGLE_SLOTS,
        n_structure_features: int = 7 + N_TOGGLE_SLOTS,
        n_actions: int = N_ACTIONS,
        config: Optional[NetConfig] = None,
        seed: Optional[int] = None,
    ):
        self.obs_length = int(obs_length)
        self.n_obs_channels = int(n_obs_channels)
        self.n_structure_features = int(n_structure_features)
        self.n_actions = int(n_actions)
        self.config = config if config is not None else NetConfig()
        rng = np.random.default_rng(seed)

        c1, c2 = self.config.channels
        k = self.config.kernel
        if self.obs_length - 2 * (k - 1) < 1:
            raise ValueError(
                f"obs_length {self.obs_length} too short for two kernels of {k}"
            )
        self.conv1 = Conv1D(self.n_obs_channels, c1, k, rng)
        self.conv2 = Conv1D(c1, c2, k, rng)
        pooled = 2 * c2 + self.n_structure_features
        self.shared = Dense(pooled, self.config.hidden, rng)
        self.policy_head = Dense(self.config.hidden, self.n_actions, rng)
        self.value_head = Dense(self.config.hidden, 1, rng)
        self._optimizer: Optional[AdamOptimizer] = None

    # ------------------------------------------------------------------ #
    # Inference                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _relu(x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        mask = x > 0.0
        return np.where(mask, x, 0.0), mask

    @staticmethod
    def _relu_backward(dout: np.ndarray, mask: np.ndarray) -> np.ndarray:
        return np.where(mask, dout, 0.0)

    def forward(
        self, obs: np.ndarray, structure: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Forward pass for a batch.

        Parameters
        ----------
        obs : numpy.ndarray
            Observations, shape ``(batch, obs_length, n_obs_channels)``.
        structure : numpy.ndarray
            Structure features, shape ``(batch, n_structure_features)``.

        Returns
        -------
        (logits, value) : tuple of numpy.ndarray
            Raw policy logits ``(batch, n_actions)`` (apply
            :func:`masked_softmax` for probabilities) and value estimates in
            ``(-1, 1)`` of shape ``(batch,)``.
        """
        x = np.asarray(obs, dtype=float).transpose(0, 2, 1)  # (B, C, L)
        h1, self._mask1 = self._relu(self.conv1.forward(x))
        h2, self._mask2 = self._relu(self.conv2.forward(h1))
        self._h2 = h2  # cached for the pooling backward pass
        pooled = np.concatenate(
            [h2.mean(axis=2), h2.max(axis=2), np.asarray(structure, dtype=float)],
            axis=1,
        )
        z, self._mask_shared = self._relu(self.shared.forward(pooled))
        logits = self.policy_head.forward(z)
        value = np.tanh(self.value_head.forward(z)).ravel()
        return logits, value

    def predict(
        self, obs: np.ndarray, structure: np.ndarray, valid_actions: np.ndarray
    ) -> Tuple[np.ndarray, float]:
        """Action priors and value for a single state.

        Parameters
        ----------
        obs, structure : numpy.ndarray
            One observation ``(obs_length, C)`` and its structure features.
        valid_actions : numpy.ndarray
            Boolean mask over the ``n_actions`` logits.

        Returns
        -------
        (priors, value) : (numpy.ndarray, float)
            Prior distribution over the valid actions and the scalar value.
        """
        logits, value = self.forward(obs[None], structure[None])
        return masked_softmax(logits[0], valid_actions), float(value[0])

    # ------------------------------------------------------------------ #
    # Training                                                           #
    # ------------------------------------------------------------------ #

    def _backward(self, dlogits: np.ndarray, dvalue: np.ndarray) -> List[np.ndarray]:
        """Backpropagate both heads; return the parameter gradients in order.

        The pooling split: global mean contributes ``d/n`` to every position,
        global max to the argmax position (ties share the gradient equally —
        any split is a valid subgradient, equal sharing keeps it symmetric).
        """
        dz = self._relu_backward(
            self.policy_head.backward(dlogits) + self.value_head.backward(dvalue[:, None]),
            self._mask_shared,
        )
        dpooled = self.shared.backward(dz)
        h2 = self._h2
        c2 = h2.shape[1]
        n = h2.shape[2]
        dmean = np.broadcast_to(dpooled[:, :c2, None], h2.shape) / n
        is_max = h2 == h2.max(axis=2, keepdims=True)
        tie = np.maximum(is_max.sum(axis=2, keepdims=True), 1)
        dmax = np.where(
            is_max, np.broadcast_to(dpooled[:, c2:2 * c2, None], h2.shape), 0.0
        ) / tie
        dh2 = dmean + dmax
        # ReLU gates sit on each layer's pre-activation: dh2 gates with mask2
        # *before* conv2's backward, its input gradient gates with mask1
        # before conv1's.
        da2 = self._relu_backward(dh2, self._mask2)
        dh1 = self.conv2.backward(da2)
        da1 = self._relu_backward(dh1, self._mask1)
        self.conv1.backward(da1)
        return (
            self.conv1.gradients + self.conv2.gradients
            + self.shared.gradients + self.policy_head.gradients + self.value_head.gradients
        )

    def _ensure_optimizer(self, learning_rate: float) -> AdamOptimizer:
        params = (
            self.conv1.parameters + self.conv2.parameters
            + self.shared.parameters + self.policy_head.parameters
            + self.value_head.parameters
        )
        if self._optimizer is None or self._optimizer.learning_rate_init != learning_rate:
            self._optimizer = AdamOptimizer(params, learning_rate_init=learning_rate)
        return self._optimizer

    def train(
        self,
        examples: Sequence[Tuple[np.ndarray, np.ndarray, np.ndarray, float]],
        *,
        epochs: int = 8,
        batch_size: int = 32,
        learning_rate: float = 1e-3,
        value_weight: float = 1.0,
        rng: Optional[np.random.Generator] = None,
    ) -> List[float]:
        """Supervised training on self-play examples.

        Parameters
        ----------
        examples : sequence of (obs, structure, policy_target, value_target)
            As collected by
            :meth:`~chisurf.core.fitting.mcts.mcts.MCTSFittingEngine.
            training_examples`.
        epochs, batch_size, learning_rate : int, int, float
            Optimisation controls.
        value_weight : float
            Weight of the value MSE relative to the policy cross-entropy.
        rng : numpy.random.Generator, optional
            Shuffling source; a default generator is created when omitted.

        Returns
        -------
        list of float
            Mean total loss per epoch (the training curve).
        """
        if not examples:
            return []
        rng = rng if rng is not None else np.random.default_rng(0)
        optimizer = self._ensure_optimizer(learning_rate)
        losses: List[float] = []
        n = len(examples)
        for _epoch in range(int(epochs)):
            order = rng.permutation(n)
            epoch_loss = 0.0
            batches = 0
            for start in range(0, n, int(batch_size)):
                idx = order[start:start + int(batch_size)]
                obs = np.stack([examples[i][0] for i in idx])
                feat = np.stack([examples[i][1] for i in idx])
                target_p = np.stack([examples[i][2] for i in idx])
                target_v = np.asarray([examples[i][3] for i in idx], dtype=float)

                logits, value = self.forward(obs, feat)
                probs = masked_softmax(logits, target_p > 0)
                # Cross-entropy against the (already normalised) visit targets,
                # and a squared value loss.
                policy_loss = -np.sum(target_p * np.log(np.maximum(probs, 1e-12)), axis=1)
                value_loss = (value - target_v) ** 2
                total = float(np.mean(policy_loss + value_weight * value_loss))

                # dCE/dlogit against a normalised target is (p − π);
                # dMSE/dz_value is 2(v − z)·(1 − v²) through the tanh.
                dlogits = probs - target_p
                dvalue = 2.0 * (value - target_v) * (1.0 - value ** 2)

                grads = self._backward(dlogits, dvalue)
                grads = [np.clip(g, -_GRAD_CLIP, _GRAD_CLIP) for g in grads]
                optimizer.update(grads)

                epoch_loss += total
                batches += 1
            losses.append(epoch_loss / max(batches, 1))
        return losses

    # ------------------------------------------------------------------ #
    # Persistence                                                        #
    # ------------------------------------------------------------------ #

    def save(self, path: str | Path) -> None:
        """Write all weights to an ``.npz`` archive."""
        arrays = {}
        for name, layer in (
            ("conv1", self.conv1), ("conv2", self.conv2), ("shared", self.shared),
            ("policy", self.policy_head), ("value", self.value_head),
        ):
            arrays[f"{name}_W"] = layer.W
            arrays[f"{name}_b"] = layer.b
        arrays["_meta"] = np.array(
            [self.obs_length, self.n_obs_channels, self.n_structure_features,
             self.n_actions, self.config.kernel, self.config.hidden]
        )
        np.savez(str(path), **arrays)

    @classmethod
    def load(cls, path: str | Path, seed: Optional[int] = None) -> "TCSPCNet":
        """Rebuild a network from :meth:`save` output."""
        data = np.load(str(path))
        obs_length, n_obs_channels, n_feat, n_actions, kernel, hidden = (
            int(v) for v in data["_meta"]
        )
        c1, c2 = data["conv1_W"].shape[0], data["conv2_W"].shape[0]
        net = cls(
            obs_length=obs_length,
            n_obs_channels=n_obs_channels,
            n_structure_features=n_feat,
            n_actions=n_actions,
            config=NetConfig(channels=(c1, c2), kernel=kernel, hidden=hidden),
            seed=seed,
        )
        for name, layer in (
            ("conv1", net.conv1), ("conv2", net.conv2), ("shared", net.shared),
            ("policy", net.policy_head), ("value", net.value_head),
        ):
            layer.W[...] = data[f"{name}_W"]
            layer.b[...] = data[f"{name}_b"]
        return net
