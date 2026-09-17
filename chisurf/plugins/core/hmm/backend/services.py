"""ServiceDispatcher-compatible RPC handlers for hidden-Markov-model analysis.

The handlers take and return plain JSON: traces come in as nested lists, the
fit goes back as the dictionary form of :class:`...api.models.HmmFit`. Any
client -- the ChiSurf GUI, another plugin, an external script over ZMQ -- gets
the same states, dwell times and transition matrix from the same code path.
"""

from __future__ import annotations

from typing import Any

from ..api.models import HmmSettings
from ..core.analysis import fit_traces, scan_state_counts

METHOD_FIT = "hmm.fit"
METHOD_SCAN = "hmm.scan"

__all__ = [
    "METHOD_FIT",
    "METHOD_SCAN",
    "fit_handler",
    "list_methods",
    "register_services",
    "scan_handler",
]


def register_services(dispatcher: Any) -> None:
    """Register the HMM RPC handlers with a ServiceDispatcher."""
    dispatcher.register(METHOD_FIT, lambda params: fit_handler(**(params or {})))
    dispatcher.register(METHOD_SCAN, lambda params: scan_handler(**(params or {})))


def list_methods() -> dict[str, str]:
    """Return the HMM RPC method descriptions."""
    return {
        METHOD_FIT: "Fit a Gaussian hidden Markov model to binned trace(s).",
        METHOD_SCAN: "Score a range of state counts by AIC and BIC.",
    }


def fit_handler(
    traces: list | None = None,
    settings: dict[str, Any] | None = None,
    **_ignored: Any,
) -> dict[str, Any]:
    """RPC handler: fit an HMM to JSON-transported traces.

    Parameters
    ----------
    traces : list
        One ``(n_bins, n_features)`` nested list, or a list of them for several
        sequences fitted jointly.
    settings : dict, optional
        Fields of :class:`...api.models.HmmSettings`.

    Returns
    -------
    dict
        The dictionary form of :class:`...api.models.HmmFit`.
    """
    return fit_traces(traces, HmmSettings.from_dict(settings)).to_dict()


def scan_handler(
    traces: list | None = None,
    settings: dict[str, Any] | None = None,
    min_states: int = 1,
    max_states: int = 6,
    **_ignored: Any,
) -> dict[str, Any]:
    """RPC handler: score state counts ``min_states`` to ``max_states`` by AIC/BIC.

    Returns
    -------
    dict
        The dictionary form of :class:`...api.models.StateScan`.
    """
    scan = scan_state_counts(
        traces, HmmSettings.from_dict(settings), min_states=min_states, max_states=max_states
    )
    return scan.to_dict()
