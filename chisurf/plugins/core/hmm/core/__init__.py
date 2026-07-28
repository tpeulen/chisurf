"""Qt-free hidden-Markov-model analysis of binned time series."""

from .analysis import (
    as_matrix,
    dwell_times,
    fit_traces,
    scan_state_counts,
    state_segments,
    transition_rates,
)

__all__ = [
    "as_matrix",
    "dwell_times",
    "fit_traces",
    "scan_state_counts",
    "state_segments",
    "transition_rates",
]
