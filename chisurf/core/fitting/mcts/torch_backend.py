"""Torch backend of TCSPCNet, for training on a GPU node.

Division of labour (by design, not by accident): **training** runs wherever
the compute is — a compute node with a GPU, via this module — while
**inference** stays in the dependency-free NumPy implementation
(:mod:`chisurf.core.fitting.mcts.network`), which is what the GUI, the
headless CI and the tree search on a laptop use. The two are the same
architecture (two valid-correlation conv layers, global mean+max pooling,
shared hidden layer, policy and value heads) and exchange weights through
one ``.npz`` format, so a network trained here is loaded by the NumPy net
with :meth:`TCSPCNet.load <chisurf.core.fitting.mcts.network.TCSPCNet.load>`
and nothing else changes.

This module imports :mod:`torch` lazily and is therefore inert on machines
without it — importing the package never fails.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

from chisurf.core.fitting.mcts.environment import N_ACTIONS, N_TOGGLE_SLOTS
from chisurf.core.fitting.mcts.network import NetConfig, masked_softmax

logger = logging.getLogger(__name__)

_LAYER_NAMES = ("conv1", "conv2", "shared", "policy", "value")


def _torch():
    try:
        import torch
        return torch
    except ImportError as error:  # pragma: no cover - environment dependent
        raise ImportError(
            "the torch backend needs PyTorch; install it on the training node "
            "or fall back to the NumPy network"
        ) from error


class TCSPCNetTorch:
    """Torch twin of :class:`~chisurf.core.fitting.mcts.network.TCSPCNet`.

    Same constructor arguments, same :meth:`predict` / :meth:`train`
    interface (so :func:`~chisurf.core.fitting.mcts.training.self_play_train`
    and the MCTS engine accept either backend unchanged), same ``.npz``
    weight format. Extra: ``device`` — ``"cuda"`` trains on the GPU.
    """

    def __init__(
        self,
        obs_length: int = 128,
        n_obs_channels: int = 3 + 7 + N_TOGGLE_SLOTS,
        n_structure_features: int = 7 + N_TOGGLE_SLOTS,
        n_actions: int = N_ACTIONS,
        config: Optional[NetConfig] = None,
        seed: Optional[int] = None,
        device: str = "cpu",
    ):
        torch = _torch()
        self.torch = torch
        self.obs_length = int(obs_length)
        self.n_obs_channels = int(n_obs_channels)
        self.n_structure_features = int(n_structure_features)
        self.n_actions = int(n_actions)
        self.config = config if config is not None else NetConfig()
        torch.manual_seed(seed if seed is not None else 0)

        c1, c2 = self.config.channels
        k = self.config.kernel
        conv = torch.nn.Conv1d
        self._module = torch.nn.Module()
        self.conv1 = conv(self.n_obs_channels, c1, k)
        self.conv2 = conv(c1, c2, k)
        pooled = 2 * c2 + self.n_structure_features
        self.shared = torch.nn.Linear(pooled, self.config.hidden)
        self.policy_head = torch.nn.Linear(self.config.hidden, self.n_actions)
        self.value_head = torch.nn.Linear(self.config.hidden, 1)
        for layer in (self.conv1, self.conv2, self.shared, self.policy_head,
                      self.value_head):
            self._module.add_module(str(id(layer)), layer)

        self.device = torch.device(device)
        self._module.to(self.device)
        self._optimizer = torch.optim.Adam(self._module.parameters(), lr=1e-3)

    # ------------------------------------------------------------------ #
    # Inference (same contract as the NumPy net)                          #
    # ------------------------------------------------------------------ #

    def forward(self, obs: np.ndarray, structure: np.ndarray):
        """Logits and value for a batch, as NumPy in / torch out."""
        torch = self.torch
        x = torch.as_tensor(np.asarray(obs, dtype=np.float32), device=self.device)
        x = x.permute(0, 2, 1)  # (B, C, L)
        feat = torch.as_tensor(
            np.asarray(structure, dtype=np.float32), device=self.device
        )
        h = torch.relu(self.conv1(x))
        h = torch.relu(self.conv2(h))
        pooled = torch.cat([h.mean(dim=2), h.amax(dim=2), feat], dim=1)
        z = torch.relu(self.shared(pooled))
        logits = self.policy_head(z)
        value = torch.tanh(self.value_head(z)).squeeze(1)
        return logits, value

    def predict(
        self, obs: np.ndarray, structure: np.ndarray, valid_actions: np.ndarray
    ) -> Tuple[np.ndarray, float]:
        """Action priors and value for a single state (NumPy in/out)."""
        torch = self.torch
        with torch.no_grad():
            logits, value = self.forward(obs[None], structure[None])
            mask = torch.as_tensor(
                np.asarray(valid_actions, dtype=bool), device=self.device
            )
            masked = torch.where(
                mask, logits[0], torch.full_like(logits[0], -1e9)
            )
            probs = torch.softmax(masked, dim=0)
        return probs.cpu().numpy(), float(value[0].cpu())

    # ------------------------------------------------------------------ #
    # Training                                                            #
    # ------------------------------------------------------------------ #

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
        """Same signature and semantics as the NumPy net's :meth:`train`."""
        torch = self.torch
        if not examples:
            return []
        rng = rng if rng is not None else np.random.default_rng(0)
        for group in self._optimizer.param_groups:
            group["lr"] = float(learning_rate)

        n = len(examples)
        losses: List[float] = []
        for _epoch in range(int(epochs)):
            order = rng.permutation(n)
            epoch_loss = 0.0
            batches = 0
            for start in range(0, n, int(batch_size)):
                idx = order[start:start + int(batch_size)]
                obs = np.stack([examples[i][0] for i in idx]).astype(np.float32)
                feat = np.stack([examples[i][1] for i in idx]).astype(np.float32)
                target_p = np.stack([examples[i][2] for i in idx]).astype(np.float32)
                target_v = np.asarray(
                    [examples[i][3] for i in idx], dtype=np.float32
                )

                logits, value = self.forward(obs, feat)
                tp = torch.as_tensor(target_p, device=self.device)
                tv = torch.as_tensor(target_v, device=self.device)
                probs = torch.softmax(
                    torch.where(tp > 0, logits,
                                torch.full_like(logits, -1e9)),
                    dim=1,
                )
                policy_loss = -(tp * torch.log(torch.clamp(probs, 1e-12))).sum(dim=1)
                value_loss = (value - tv) ** 2
                loss = (policy_loss + value_weight * value_loss).mean()

                self._optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_value_(self._module.parameters(), 5.0)
                self._optimizer.step()

                epoch_loss += float(loss.cpu())
                batches += 1
            losses.append(epoch_loss / max(batches, 1))
        return losses

    # ------------------------------------------------------------------ #
    # Weight exchange with the NumPy net                                  #
    # ------------------------------------------------------------------ #

    def state_arrays(self) -> dict:
        """The weights as the NumPy net's ``.npz`` layout."""
        arrays = {}
        for name, layer in (
            ("conv1", self.conv1), ("conv2", self.conv2), ("shared", self.shared),
            ("policy", self.policy_head), ("value", self.value_head),
        ):
            weight = layer.weight.detach().cpu().numpy()
            if name in ("conv1", "conv2"):
                arrays[f"{name}_W"] = weight  # (out, in, k): identical layout
            else:
                # torch Linear stores (out, in); the NumPy Dense stores (in, out).
                arrays[f"{name}_W"] = weight.T
            arrays[f"{name}_b"] = layer.bias.detach().cpu().numpy()
        arrays["_meta"] = np.array(
            [self.obs_length, self.n_obs_channels, self.n_structure_features,
             self.n_actions, self.config.kernel, self.config.hidden]
        )
        return arrays

    def save(self, path: str | Path) -> None:
        """Write weights in the shared ``.npz`` format."""
        np.savez(str(path), **self.state_arrays())

    def load(self, path: str | Path) -> "TCSPCNetTorch":
        """Load weights from the shared ``.npz`` format."""
        torch = self.torch
        data = np.load(str(path))
        with torch.no_grad():
            for name, layer in (
                ("conv1", self.conv1), ("conv2", self.conv2), ("shared", self.shared),
                ("policy", self.policy_head), ("value", self.value_head),
            ):
                weight = data[f"{name}_W"]
                if name not in ("conv1", "conv2"):
                    weight = weight.T
                layer.weight.copy_(
                    torch.as_tensor(weight, device=self.device)
                )
                layer.bias.copy_(
                    torch.as_tensor(data[f"{name}_b"], device=self.device)
                )
        return self
