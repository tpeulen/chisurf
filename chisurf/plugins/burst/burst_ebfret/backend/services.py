"""ServiceDispatcher-compatible RPC handlers for ebFRET binned-trace analysis."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..api.models import EbfretSettings, FretTraceSet
from ..core.analysis import EbfretAnalysis, analyse

METHOD_COMPUTE = "burst_ebfret.jobs.compute"


def register_services(dispatcher: Any) -> None:
    """Register ebFRET RPC handlers with a ServiceDispatcher."""
    dispatcher.register(METHOD_COMPUTE, lambda params: compute_handler(**(params or {})))


def list_methods() -> dict[str, str]:
    """Return ebFRET RPC method descriptions."""
    return {METHOD_COMPUTE: "Fit an empirical-Bayes Gaussian HMM over binned FRET traces."}


def run_analysis(
    traces: FretTraceSet | list[np.ndarray], settings: EbfretSettings
) -> EbfretAnalysis:
    """Run the ebFRET analysis for a trace set under the given settings.

    Parameters
    ----------
    traces : FretTraceSet or list of numpy.ndarray
        Binned FRET-efficiency traces.
    settings : EbfretSettings
        Analysis settings.

    Returns
    -------
    EbfretAnalysis
    """
    items = traces.traces if isinstance(traces, FretTraceSet) else list(traces)
    return analyse(
        items,
        min_states=settings.min_states,
        max_states=settings.max_states,
        max_iter=settings.max_iter,
        threshold=settings.threshold,
        vbem_max_iter=settings.vbem_max_iter,
        vbem_threshold=settings.vbem_threshold,
        seed=settings.seed,
    )


def _analysis_to_jsonable(analysis: EbfretAnalysis) -> dict[str, Any]:
    """Convert an :class:`EbfretAnalysis` into a JSON-serialisable dict."""
    return {
        "n_states": analysis.n_states,
        "evidence": analysis.evidence,
        "scan": {str(k): v for k, v in analysis.scan.items()},
        "states": [
            {
                "index": s.index,
                "mean": s.mean,
                "precision": s.precision,
                "std": s.std,
                "occupancy": s.occupancy,
            }
            for s in analysis.states
        ],
        "transition_counts": analysis.transition_counts.tolist(),
        "n_dwells": len(analysis.dwells),
    }


def compute_handler(
    traces: list[list[float]] | None = None,
    settings: dict[str, Any] | None = None,
    **_ignored: Any,
) -> dict[str, Any]:
    """RPC handler: fit an ebFRET model from JSON-transported traces.

    Parameters
    ----------
    traces : list of list of float
        Binned FRET-efficiency traces.
    settings : dict, optional
        Fields of :class:`EbfretSettings`.

    Returns
    -------
    dict
        JSON-serialisable analysis summary.
    """
    trace_arrays = [np.asarray(t, dtype=float) for t in (traces or [])]
    cfg = EbfretSettings(**(settings or {}))
    analysis = run_analysis(trace_arrays, cfg)
    return {"ok": True, "result": _analysis_to_jsonable(analysis)}
