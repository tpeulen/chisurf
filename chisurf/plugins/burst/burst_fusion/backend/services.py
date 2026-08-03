"""ServiceDispatcher-compatible RPC handlers for burst fusion.

Database-free and Qt-free: the handlers take paths and a settings payload, run
the Qt-free core, and return plain JSON. The GUI client holds no analysis logic
of its own beyond plotting what comes back.
"""

from __future__ import annotations

import pathlib
from typing import Any

import numpy as np

from ..api.models import FusionSettings

METHOD_ANALYZE = "burst_fusion.jobs.analyze"
METHOD_FUSE = "burst_fusion.jobs.fuse"
METHOD_PREPARE = "burst_fusion.workflow.prepare"


def register_services(dispatcher: Any) -> None:
    """Register the burst-fusion RPC handlers with a ServiceDispatcher."""
    dispatcher.register(METHOD_ANALYZE, lambda params: analyze_handler(**(params or {})))
    dispatcher.register(METHOD_FUSE, lambda params: fuse_handler(**(params or {})))
    dispatcher.register(METHOD_PREPARE, lambda params: prepare_handler(**(params or {})))


def list_methods() -> dict[str, str]:
    """Return the burst-fusion RPC method descriptions."""
    return {
        METHOD_ANALYZE: "Estimate P_same and report what a threshold would fuse.",
        METHOD_FUSE: "Write the fused bursts as a new burst-analysis folder.",
        METHOD_PREPARE: "Resolve folder and detectors from a burst workflow context.",
    }


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "error": message}


def _ok(payload: dict[str, Any]) -> dict[str, Any]:
    out = {"status": "ok"}
    out.update(payload)
    return out


def _curve(window) -> dict[str, Any]:
    """The P_same curve as JSON (undetermined bins as ``None``)."""
    return {
        "tau_s": [float(v) for v in window.tau_s],
        "p_same": [None if not np.isfinite(v) else float(v) for v in window.p_same],
        "pairs": [float(v) for v in window.counts],
        "tau_max_s": float(window.tau_max_s),
        "resolved": bool(window.resolved),
        "threshold": float(window.threshold),
        "n_bursts": int(window.n_bursts),
    }


def analyze_handler(
    analysis_folder: str | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Estimate ``P_same`` for a burst folder and report the fusion it implies."""
    try:
        from ..core.fusion import analyze

        if not analysis_folder:
            return _error("analysis_folder is required")
        result = analyze(pathlib.Path(analysis_folder), FusionSettings.from_dict(settings))
        return _ok(
            {
                "analysis_folder": str(result.folder),
                "curve": _curve(result.window),
                "statistics": result.statistics,
                "settings": result.settings.to_dict(),
            }
        )
    except Exception as exc:  # pragma: no cover - transport-level guard
        return _error(str(exc))


def fuse_handler(
    analysis_folder: str | None = None,
    settings: dict[str, Any] | None = None,
    output_folder: str | None = None,
    detectors: dict[str, Any] | None = None,
    windows: dict[str, Any] | None = None,
    data_folder: str | None = None,
) -> dict[str, Any]:
    """Fuse a burst folder and write the result as a new burst folder."""
    try:
        from ..core.fusion import fuse_folder

        if not analysis_folder:
            return _error("analysis_folder is required")
        result = fuse_folder(
            pathlib.Path(analysis_folder),
            FusionSettings.from_dict(settings),
            output_folder=output_folder,
            detectors=detectors,
            windows=windows,
            data_folder=data_folder,
        )
        return _ok(result)
    except Exception as exc:  # pragma: no cover - transport-level guard
        return _error(str(exc))


def prepare_handler(
    workflow_context: dict[str, Any] | None = None,
    analysis_folder: str | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve the folder and detector definition from a burst workflow context."""
    context = workflow_context or {}
    folder = analysis_folder or context.get("burst_folder")
    channels = context.get("channel_settings") or {}
    return _ok(
        {
            "analysis_folder": str(folder) if folder else None,
            "detectors": channels.get("detectors") or {},
            "windows": channels.get("windows") or {},
            "settings": FusionSettings.from_dict(settings).to_dict(),
        }
    )
