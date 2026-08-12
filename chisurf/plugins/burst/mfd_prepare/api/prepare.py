"""Pure preparation API — thin wrapper over the MFD prepare core."""

from __future__ import annotations

import logging
from pathlib import Path

from .models import PrepareRequest, PrepareResult

logger = logging.getLogger(__name__)


def prepare_folder(request: PrepareRequest) -> PrepareResult:
    """Prepare a burst folder and return a JSON-serializable result.

    Calls :func:`~chisurf.core.fluorescence.mfd.prepare.prepare_burst_folder`
    and extracts the key diagnostics. No Qt, no DB.
    """
    if not request.folder:
        return PrepareResult(error="No folder specified")
    folder = Path(request.folder)
    if not folder.is_dir():
        return PrepareResult(
            folder=str(folder),
            error=f"Folder does not exist: {folder}",
        )

    try:
        from chisurf.core.fluorescence.mfd.prepare import (
            prepare_burst_folder,
        )

        kwargs: dict = {}
        if request.streams:
            kwargs["streams"] = request.streams
        kwargs["with_photons"] = request.with_photons

        prep = prepare_burst_folder(folder, **kwargs)

        sources_summary: dict = {}
        if hasattr(prep, "sources") and prep.sources:
            sources_summary = {
                "origin": dict(prep.sources.origin)
                if hasattr(prep.sources, "origin")
                else {},
                "container_type": dict(prep.sources.container_type)
                if hasattr(prep.sources, "container_type")
                else {},
            }

        return PrepareResult(
            folder=str(folder),
            n_bursts=len(prep),
            channels=list(prep.channels),
            verified_channels=list(prep.verified_channels),
            count_agreement=_jsonable(prep.summary.get("count_agreement", {})),
            duration_s=float(prep.duration.sum()),
            total_photons=int(prep.total_counts.sum()),
            report=prep.report(),
            summary=_jsonable(prep.summary),
            sources=sources_summary,
        )
    except Exception as exc:
        logger.debug("prepare_folder failed", exc_info=True)
        return PrepareResult(folder=str(folder), error=str(exc))


def describe_preparation() -> dict:
    """Return the contract descriptor for this plugin."""
    from .contract import contract_descriptor

    return contract_descriptor()


def _jsonable(obj):
    """Best-effort conversion of numpy/path objects to JSON-serializable."""
    import numpy as np

    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, Path):
        return str(obj)
    return obj
