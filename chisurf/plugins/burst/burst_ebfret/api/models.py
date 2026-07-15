"""Data models for the ebFRET (binned-trace HMM) API."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class EbfretSettings:
    """Settings for an empirical-Bayes HMM analysis of binned smFRET traces.

    Attributes
    ----------
    min_states : int
        Smallest state count to scan.
    max_states : int
        Largest state count to scan.
    max_iter : int
        Maximum empirical-Bayes iterations per state count.
    threshold : float
        Relative summed-evidence convergence threshold.
    vbem_max_iter : int
        Maximum per-trace VBEM iterations.
    vbem_threshold : float
        Relative ELBO convergence threshold for the per-trace VBEM.
    seed : int
        Base seed for the (deterministic) prior initialisation.
    """

    min_states: int = 2
    max_states: int = 4
    max_iter: int = 20
    threshold: float = 1e-4
    vbem_max_iter: int = 100
    vbem_threshold: float = 1e-5
    seed: int = 0


@dataclass
class FretTraceSet:
    """A collection of variable-length binned FRET-efficiency traces.

    Attributes
    ----------
    traces : list of numpy.ndarray
        One-dimensional FRET-efficiency time series, one per molecule.
    labels : list of str
        Optional per-trace identifiers, parallel to ``traces``.
    """

    traces: list[np.ndarray] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Coerce traces to 1-D float arrays and fill default labels."""
        self.traces = [np.asarray(t, dtype=float).ravel() for t in self.traces]
        if not self.labels:
            self.labels = [f"trace_{i}" for i in range(len(self.traces))]

    def __len__(self) -> int:
        """Return the number of traces in the set."""
        return len(self.traces)
