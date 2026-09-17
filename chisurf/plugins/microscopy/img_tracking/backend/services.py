"""ServiceDispatcher-compatible RPC handlers for single-particle tracking.

Detection and linking are the heavy part and run on the backend; a client sends
a path (or simulation settings) and receives tracks and transport parameters as
plain JSON-able values. No Qt and no image handling on the client side.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.imaging import tracking as tk

from .. import core as _core

#: Keys of :func:`chisurf.plugins.microscopy.img_tracking.core.analyse` a client
#: may set. Anything else in the request is a typo, and silently ignoring it
#: would hand back a result computed with settings the caller did not ask for.
_ANALYSIS_KEYS = frozenset(
    {
        "pixel_size",
        "frame_interval",
        "method",
        "threshold",
        "min_area",
        "min_separation",
        "max_distance",
        "max_frame_gap",
        "min_track_length",
        "fix_alpha",
        "n_bootstrap",
    }
)


def _split(params: dict) -> tuple[dict, dict]:
    """Split a request into loader keys and analysis keys, rejecting unknowns."""
    payload = dict(params or {})
    analysis = {k: payload.pop(k) for k in list(payload) if k in _ANALYSIS_KEYS}
    return payload, analysis


def track(params: dict) -> dict:
    """Detect, link and fit transport for an image stack.

    Parameters
    ----------
    params : dict
        ``{"filename": ..., "channel": 0, "max_frames": 0}`` plus any keyword of
        :func:`chisurf.plugins.microscopy.img_tracking.core.analyse`.

    Returns
    -------
    dict
        ``{"ok": True, "result": {...}}`` or ``{"ok": False, "error": "..."}``.
    """
    try:
        payload, analysis = _split(params)
        filename = payload.pop("filename", None)
        if not filename:
            raise ValueError("'filename' is required")
        frames, info = _core.load_frames(
            filename,
            channel=int(payload.pop("channel", 0)),
            max_frames=int(payload.pop("max_frames", 0)),
        )
        if payload:
            raise ValueError(f"unknown settings: {', '.join(sorted(payload))}")
        result = _core.analyse(frames, info=info, **analysis)
        return {"ok": True, "result": result.to_dict()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def simulate(params: dict) -> dict:
    """Track a simulated movie of Brownian particles with a known ``D``.

    Parameters
    ----------
    params : dict
        Keywords of
        :func:`chisurf.core.fluorescence.imaging.tracking.simulate_particle_movie`
        (``n_frames``, ``shape``, ``n_particles``, ``diffusion_coefficient``, …)
        plus any keyword of
        :func:`chisurf.plugins.microscopy.img_tracking.core.analyse`.

    Returns
    -------
    dict
        ``{"ok": True, "result": {...}}`` or ``{"ok": False, "error": "..."}``.
        An oversized movie is refused here rather than allocated.
    """
    try:
        payload, analysis = _split(params)
        if "shape" in payload:
            payload["shape"] = tuple(int(v) for v in payload["shape"])
        frames, truth = tk.simulate_particle_movie(**payload)
        info = {
            "source": "simulation",
            "n_frames": int(np.asarray(frames).shape[0]),
            "true_diffusion": float(payload.get("diffusion_coefficient", 1.0)),
            "n_particles": int(payload.get("n_particles", 20)),
        }
        result = _core.analyse(frames, info=info, **analysis)
        del truth
        return {"ok": True, "result": result.to_dict()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def register_services(dispatcher) -> None:
    """Register the plugin's RPC methods on *dispatcher*."""
    dispatcher.register("img_tracking.jobs.track", track)
    dispatcher.register("img_tracking.jobs.simulate", simulate)


__all__ = ["register_services", "simulate", "track"]
