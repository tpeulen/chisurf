"""ServiceDispatcher RPC handlers for the TTTR LUT Tools plugin.

Thin adapters: accept JSON-compatible params, delegate to the ``api/`` layer,
return JSON-safe envelopes. No Qt.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..api import compute, io, settings
from ..api.contract import (
    METHOD_APPLY_PREVIEW,
    METHOD_AUTODETECT,
    METHOD_COMPUTE,
    METHOD_SETTINGS_BUILD,
    METHOD_SETTINGS_LOAD,
    service_error,
    service_success,
)


def _autodetect_handler(counts: list[float], noffset: int = 0, **_: Any) -> dict:
    start, stop = compute.lut.autodetect_linear_region(
        np.asarray(counts, dtype=float), noffset_guess=int(noffset)
    )
    return service_success({"linear_start": int(start), "linear_stop": int(stop)})


def _compute_handler(
    files: list[str],
    routine: str | None = None,
    n_bins: int = 0,
    linear_start: int | None = None,
    linear_stop: int | None = None,
    ntac_required: int = 0,
    noffset: int = 0,
    channel: int | None = None,
    **_: Any,
) -> dict:
    tbl = compute.compute_lut_from_files(
        list(files),
        routine=routine or None,
        n_bins=int(n_bins) or None,
        linear_start=linear_start,
        linear_stop=linear_stop,
        ntac_required=int(ntac_required) or None,
        noffset=int(noffset),
        channel=None if channel is None else int(channel),
    )
    return service_success(
        {
            "channel": None if channel is None else int(channel),
            "NTAC_fract": np.asarray(tbl["NTAC_fract"]).tolist(),
            "linear_start": tbl["linear_start"],
            "linear_stop": tbl["linear_stop"],
            "ntac_required": tbl["ntac_required"],
            "n_bins": tbl["n_bins"],
            "noffset": tbl["noffset"],
            "total_counts": tbl["total_counts"],
        }
    )


def _apply_preview_handler(
    path: str,
    channel: int,
    routine: str | None = None,
    channel_luts: dict | None = None,
    channel_shifts: dict | None = None,
    coarsening: int = 1,
    **_: Any,
) -> dict:
    luts = {int(k): np.asarray(v, dtype=float) for k, v in (channel_luts or {}).items()}
    shifts = {int(k): int(v) for k, v in (channel_shifts or {}).items()}
    counts, axis = settings.corrected_histogram(
        path, int(channel), luts, shifts, routine or None, int(coarsening) or 1
    )
    return service_success({"counts": counts.tolist(), "axis": axis.tolist()})


def _settings_build_handler(
    channel_luts: dict,
    channel_shifts: dict | None = None,
    reading_routine: str | None = None,
    out_path: str | None = None,
    **_: Any,
) -> dict:
    luts = {int(k): np.asarray(v, dtype=float) for k, v in channel_luts.items()}
    d = settings.build_settings_dict(
        luts,
        {int(k): int(v) for k, v in (channel_shifts or {}).items()},
        reading_routine=reading_routine,
    )
    if out_path:
        settings.save_settings(out_path, d)
    return service_success({"settings": d, "written": bool(out_path), "path": out_path})


def _settings_load_handler(path: str, **_: Any) -> dict:
    loaded = settings.load_settings(path)
    # JSON-safe: string keys so results survive a real ZMQ JSON transport too.
    return service_success(
        {
            "reading_routine": loaded["reading_routine"],
            "channel_luts": {
                str(k): np.asarray(v).tolist() for k, v in loaded["channel_luts"].items()
            },
            "channel_shifts": {str(k): int(v) for k, v in loaded["channel_shifts"].items()},
        }
    )


def register_services(dispatcher: Any, **_: Any) -> None:
    """Register LUT-tools RPC handlers with a ServiceDispatcher."""

    def _guard(handler):
        def _run(params):
            try:
                return handler(**(params or {}))
            except Exception as exc:  # pragma: no cover - surfaced to the client
                return service_error(str(exc))

        return _run

    dispatcher.register(METHOD_AUTODETECT, _guard(_autodetect_handler))
    dispatcher.register(METHOD_COMPUTE, _guard(_compute_handler))
    dispatcher.register(METHOD_APPLY_PREVIEW, _guard(_apply_preview_handler))
    dispatcher.register(METHOD_SETTINGS_BUILD, _guard(_settings_build_handler))
    dispatcher.register(METHOD_SETTINGS_LOAD, _guard(_settings_load_handler))


# io re-exported for symmetry with other plugins' backends
__all__ = ["register_services", "io"]
