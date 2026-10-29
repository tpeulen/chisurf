"""Pure preparation API — thin wrapper over the MFD prepare core."""

from __future__ import annotations

import logging
from pathlib import Path

from .models import PrepareRequest, PrepareResult

logger = logging.getLogger(__name__)


def prepare_folder(request: PrepareRequest) -> PrepareResult:
    """Prepare a burst run (``m000.pto/<run>``) or a legacy burst folder; return a JSON-serializable
    result.

    Calls :func:`~chisurf.core.fluorescence.mfd.prepare.prepare_burst_folder`
    and extracts the key diagnostics. No Qt, no DB.
    """
    if not request.folder:
        return PrepareResult(error="No folder specified")
    from chisurf.core.fio.analysis_path import is_container_path, split_container_path

    folder = Path(request.folder)
    if is_container_path(folder):
        container, _run = split_container_path(folder)
        if container is None or not container.is_file():
            return PrepareResult(folder=str(folder), error=f"Burst run not found: {folder}")
    elif not folder.is_dir():
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
                "origin": dict(prep.sources.origin) if hasattr(prep.sources, "origin") else {},
                "container_type": dict(prep.sources.container_type)
                if hasattr(prep.sources, "container_type")
                else {},
            }

        warnings = window_warnings(prep)
        report = prep.report()
        if warnings:
            report = report.rstrip("\n") + "\n" + "\n".join(f"warning: {w}" for w in warnings)
        return PrepareResult(
            folder=str(folder),
            n_bursts=len(prep),
            channels=list(prep.channels),
            verified_channels=list(prep.verified_channels),
            count_agreement=_jsonable(prep.summary.get("count_agreement", {})),
            duration_s=float(prep.duration.sum()),
            total_photons=int(prep.total_counts.sum()),
            report=report,
            summary=_jsonable(prep.summary),
            sources=sources_summary,
            warnings=warnings,
        )
    except Exception as exc:
        logger.debug("prepare_folder failed", exc_info=True)
        return PrepareResult(folder=str(folder), error=str(exc))


def window_warnings(prep) -> list[str]:
    """The excitation-window pre-flight on the detector gates the preparation applied to the photons.

    The detectors' micro-time gates (``micro_time_ranges``, from the run's manifest, the caller or
    inferred from the photons) split each burst's photons into colours; the PIE windows the burst
    search recorded beside them are checked too. The gates are those the bursts were selected with,
    so they are reported, not replaced: taking other gates here would no longer reproduce the burst
    table. One line per measurement whose gates do not hold its excitation pulses; empty when every
    measurement fits, when no detector is gated, or when the photons cannot be opened.

    Parameters
    ----------
    prep : BurstPreparation
        The result of :func:`~chisurf.core.fluorescence.mfd.prepare.prepare_burst_folder`.

    Returns
    -------
    list of str
    """
    from chisurf.core.fluorescence.burst.streams import stream_detectors, window_warnings

    detectors = stream_detectors(
        {s.name: (s.channels, s.micro_time_ranges) for s in getattr(prep, "streams", ()) or ()}
    )
    if not any(d["micro_time_ranges"] for d in detectors.values()):
        return []
    try:
        tttrs = _photon_streams(prep)
    except Exception:  # noqa: BLE001 - photons that cannot be opened: nothing to check
        logger.debug("window pre-flight: photons not opened", exc_info=True)
        return []
    return window_warnings(tttrs, detectors, windows=_recorded_windows(prep))


def _photon_streams(prep) -> dict:
    """The opened measurements of *prep* (kept when it read the photons, opened otherwise)."""
    tttrs = (getattr(prep, "summary", {}) or {}).get("_tttrs")
    if tttrs:
        return dict(tttrs)
    from chisurf.core.fio.analysis_path import is_container_path
    from chisurf.core.fluorescence.mfd.prepare import (
        is_sentinel_file_reference,
        open_sources,
        resolve_sources,
    )

    folder = Path(str(prep.folder))
    if is_container_path(folder):
        from chisurf.core.fio.fluorescence.burst import _read_burst_analysis_from_container

        return dict(_read_burst_analysis_from_container(folder)[1])
    keys = [k for k in dict.fromkeys(prep.file_key.tolist()) if not is_sentinel_file_reference(k)]
    return open_sources(resolve_sources(folder, keys))


def _recorded_windows(prep) -> dict:
    """The PIE windows the burst search recorded in the run's manifest (empty when none)."""
    try:
        from chisurf.core.fio.fluorescence.burst_manifest import read_analysis_manifest

        manifest = read_analysis_manifest(Path(str(prep.folder))) or {}
    except Exception:  # noqa: BLE001
        return {}
    for source in manifest.get("sources") or []:
        windows = ((source or {}).get("settings") or {}).get("windows")
        if windows:
            return {str(k): [int(v[0]), int(v[1])] for k, v in dict(windows).items()}
    windows = (manifest.get("settings") or {}).get("windows")
    return {str(k): [int(v[0]), int(v[1])] for k, v in dict(windows or {}).items()}


def describe_preparation() -> dict:
    """Return the contract descriptor for this plugin."""
    from .contract import contract_descriptor

    return contract_descriptor()


def _jsonable(obj):
    """Best-effort conversion of numpy/path objects to JSON-serializable.

    Keys starting with ``_`` are in-process handles (the summary keeps the
    opened TTTR objects under ``_tttrs`` for the fit step) and are dropped: the
    result crosses the RPC boundary as JSON, where they cannot go.
    """
    import numpy as np

    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items() if not str(k).startswith("_")}
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
