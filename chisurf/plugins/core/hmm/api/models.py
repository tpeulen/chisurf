"""Transport-agnostic data models for the hidden-Markov-model analysis.

These dataclasses are the contract shared by the GUI, the RPC backend and the
CLI: the GUI edits :class:`HmmSettings`, the backend returns an :class:`HmmFit`
or a :class:`StateScan`, and both convert to plain JSON-able dictionaries so the
same result can cross a ZMQ boundary unchanged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from chisurf.core.math.hmm import COVARIANCE_TYPES

__all__ = ["HmmFit", "HmmSettings", "StateScan", "StateSummary"]


@dataclass
class HmmSettings:
    """Settings of a Gaussian hidden-Markov-model fit.

    Attributes
    ----------
    n_states : int
        Number of hidden states to fit.
    covariance_type : str
        Emission covariance parameterisation, one of
        :data:`chisurf.core.math.hmm.COVARIANCE_TYPES`.
    n_iter : int
        Maximum number of EM maps.
    tol : float
        Convergence threshold on the log-likelihood gain.
    accelerate : bool
        Use SQUAREM extrapolation to reach the same optimum in fewer maps.
    random_state : int
        Seed of the k-means initialisation, so a fit is reproducible.
    min_covar : float
        Floor added to the initial covariances.
    decode : str
        ``"viterbi"`` for the most probable state *path*, ``"map"`` for the
        sequence of individually most probable states.
    time_step : float
        Duration of one time bin, in seconds. Dwell times and transition rates
        are reported in those units; 1.0 leaves them in bins.
    """

    n_states: int = 2
    covariance_type: str = "full"
    n_iter: int = 1000
    tol: float = 1e-2
    accelerate: bool = True
    random_state: int = 0
    min_covar: float = 1e-3
    decode: str = "viterbi"
    time_step: float = 1.0

    def __post_init__(self) -> None:
        """Validate the enumerated fields early, where the message is still useful."""
        if self.covariance_type not in COVARIANCE_TYPES:
            raise ValueError(f"covariance_type must be one of {COVARIANCE_TYPES}")
        if self.decode not in ("viterbi", "map"):
            raise ValueError("decode must be 'viterbi' or 'map'")

    def to_dict(self) -> dict[str, Any]:
        """Return the settings as a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> HmmSettings:
        """Build settings from a dictionary, ignoring unknown keys."""
        payload = payload or {}
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in payload.items() if k in known})


@dataclass
class StateSummary:
    """What one fitted state looks like, in the units of the input.

    Attributes
    ----------
    index : int
        State index, ordered by increasing total emission mean (state 0 is the
        dimmest), so that the labels are stable between fits.
    mean : list of float
        Emission mean per feature.
    std : list of float
        Emission standard deviation per feature (the square root of the
        covariance diagonal).
    occupancy : float
        Fraction of time bins decoded into this state.
    n_dwells : int
        Number of separate visits to this state.
    mean_dwell : float
        Mean dwell time per visit, in the settings' time unit.
    """

    index: int
    mean: list[float]
    std: list[float]
    occupancy: float
    n_dwells: int
    mean_dwell: float


@dataclass
class HmmFit:
    """A fitted hidden Markov model and the state path it implies.

    Attributes
    ----------
    settings : HmmSettings
        Settings the fit was run with.
    n_states : int
        Number of states.
    log_likelihood, aic, bic : float
        Fit quality; ``aic``/``bic`` are what to compare across state counts.
    converged : bool
        Whether EM met ``tol`` before exhausting ``n_iter``.
    n_iterations : int
        EM iterations (SQUAREM cycles, when accelerated) performed.
    startprob : list of float
        Initial state distribution.
    transmat : list of list of float
        Row-stochastic transition matrix in the reported state order.
    means : list of list of float
        Emission means, one row per state.
    covars : list
        Emission covariances in the compact layout of ``covariance_type``.
    states : list of int
        Decoded state per time bin.
    lengths : list of int
        Length of each input sequence, so a concatenated ``states`` can be split
        back up.
    summaries : list of StateSummary
        Per-state summary, parallel to the state indices.
    dwell_times : list of list of float
        Dwell times per state, in the settings' time unit.
    transition_rates : list of list of float
        Off-diagonal transition rates in inverse time units; the diagonal is the
        negative row sum, as in a rate matrix.
    """

    settings: HmmSettings
    n_states: int
    log_likelihood: float
    aic: float
    bic: float
    converged: bool
    n_iterations: int
    startprob: list[float] = field(default_factory=list)
    transmat: list[list[float]] = field(default_factory=list)
    means: list[list[float]] = field(default_factory=list)
    covars: list = field(default_factory=list)
    states: list[int] = field(default_factory=list)
    lengths: list[int] = field(default_factory=list)
    summaries: list[StateSummary] = field(default_factory=list)
    dwell_times: list[list[float]] = field(default_factory=list)
    transition_rates: list[list[float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return the fit as a JSON-serialisable dictionary."""
        payload = asdict(self)
        payload["settings"] = self.settings.to_dict()
        return payload

    @property
    def state_array(self) -> np.ndarray:
        """The decoded state path as an integer array."""
        return np.asarray(self.states, dtype=int)


@dataclass
class StateScan:
    """Information criteria over a range of state counts.

    Attributes
    ----------
    n_states : list of int
        The state counts that were fitted.
    log_likelihood, aic, bic : list of float
        One entry per state count; ``nan`` where the fit failed.
    best_bic, best_aic : int
        State count minimising each criterion.
    """

    n_states: list[int] = field(default_factory=list)
    log_likelihood: list[float] = field(default_factory=list)
    aic: list[float] = field(default_factory=list)
    bic: list[float] = field(default_factory=list)
    best_bic: int = 0
    best_aic: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return the scan as a JSON-serialisable dictionary."""
        return asdict(self)
