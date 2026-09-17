"""ServiceDispatcher-compatible RPC handlers for photon-by-photon kinetics.

The fit is the heavy part and runs on the backend; a client sends per-burst
photon times and colours and receives rates, efficiencies and the report as
plain JSON-able values. No Qt and no file access on the client side.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from chisurf.core.fluorescence.burst import gopich_szabo as gs

from .. import core as _core


def _bursts_from_params(params: dict) -> gs.PhotonBursts:
    """Build :class:`PhotonBursts` from an RPC payload.

    Accepts either per-burst nested lists (``times``/``colors``) or the flat
    layout (``times``/``colors``/``offsets``), whichever the client finds
    cheaper to serialise.
    """
    times = params.get("times")
    colors = params.get("colors")
    if times is None or colors is None:
        raise ValueError("both 'times' (seconds) and 'colors' are required")
    offsets = params.get("offsets")
    n_colors = params.get("n_colors")
    if offsets is not None:
        offsets = np.asarray(offsets, dtype=np.int64)
        flat_t = np.asarray(times, dtype=np.float64)
        flat_c = np.asarray(colors, dtype=np.int32)
        per_burst_t = [flat_t[offsets[i] : offsets[i + 1]] for i in range(offsets.size - 1)]
        per_burst_c = [flat_c[offsets[i] : offsets[i + 1]] for i in range(offsets.size - 1)]
    else:
        per_burst_t = [np.asarray(t, dtype=np.float64) for t in times]
        per_burst_c = [np.asarray(c, dtype=np.int32) for c in colors]
    return gs.PhotonBursts.from_lists(
        per_burst_t,
        per_burst_c,
        n_colors=None if n_colors is None else int(n_colors),
        min_photons=int(params.get("min_photons", 2)),
    )


def fit(params: dict) -> dict:
    """Fit a continuous-time kinetic scheme to coloured photons.

    Parameters
    ----------
    params : dict
        ``{"times": [...], "colors": [...]}`` (per burst or flat with
        ``offsets``) plus any keyword of
        :func:`chisurf.plugins.burst.burst_gs.core.analyse`. With
        ``{"simulate": {...}}`` instead, photons are simulated from a known
        two-state molecule using the keywords of
        :func:`~chisurf.plugins.burst.burst_gs.core.simulate_two_state`.

    Returns
    -------
    dict
        ``{"ok": True, "result": {...}}`` or ``{"ok": False, "error": "..."}``.
    """
    try:
        payload = dict(params or {})
        simulate = payload.pop("simulate", None)
        if simulate is not None:
            bursts = _core.simulate_two_state(**dict(simulate))
            info: dict[str, Any] = {"source": "simulation", **dict(simulate)}
        else:
            bursts = _bursts_from_params(payload)
            info = {"source": "client", "n_bursts": len(bursts), "n_photons": bursts.n_photons}
        for key in ("times", "colors", "offsets", "n_colors", "min_photons"):
            payload.pop(key, None)
        analysis = _core.analyse(bursts, info=info, **payload)
        return {"ok": True, "result": analysis.to_dict()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def log_likelihood(params: dict) -> dict:
    """Evaluate the log-likelihood of a given scheme without fitting.

    Parameters
    ----------
    params : dict
        Photons as for :func:`fit`, plus ``rate_matrix`` (``[target, source]``
        rates in s^-1) and either ``efficiencies`` (two-colour) or a full
        ``emission`` matrix.

    Returns
    -------
    dict
        ``{"ok": True, "log_likelihood": float}`` or an error.
    """
    try:
        payload = dict(params or {})
        bursts = _bursts_from_params(payload)
        matrix = np.asarray(payload["rate_matrix"], dtype=float)
        if "emission" in payload:
            emission = np.asarray(payload["emission"], dtype=float)
        else:
            emission = gs.emission_from_efficiencies(payload["efficiencies"])
        return {
            "ok": True,
            "log_likelihood": gs.log_likelihood(bursts, matrix, emission),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def transition_time_scan(params: dict) -> dict:
    """Scan the log-likelihood against the duration of a transition.

    Parameters
    ----------
    params : dict
        Photons as for :func:`fit`, plus ``k_forward``, ``k_backward``,
        ``efficiencies`` and optionally ``transit_times`` (seconds) and
        ``transit_efficiency``.

    Returns
    -------
    dict
        ``{"ok": True, "transit_times": [...], "delta_log_likelihood": [...],
        "baseline": float}`` or an error.
    """
    try:
        payload = dict(params or {})
        bursts = _bursts_from_params(payload)
        times, delta, baseline = gs.transition_time_scan(
            bursts,
            float(payload["k_forward"]),
            float(payload["k_backward"]),
            payload["efficiencies"],
            transit_times=payload.get("transit_times"),
            transit_efficiency=payload.get("transit_efficiency"),
        )
        return {
            "ok": True,
            "transit_times": np.asarray(times, dtype=float).tolist(),
            "delta_log_likelihood": np.asarray(delta, dtype=float).tolist(),
            "baseline": float(baseline),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def register_services(dispatcher) -> None:
    """Register the plugin's RPC methods on *dispatcher*."""
    dispatcher.register("burst_gs.jobs.fit", fit)
    dispatcher.register("burst_gs.jobs.log_likelihood", log_likelihood)
    dispatcher.register("burst_gs.jobs.transition_time_scan", transition_time_scan)


__all__ = ["fit", "log_likelihood", "register_services", "transition_time_scan"]
