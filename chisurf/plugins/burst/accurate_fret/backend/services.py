"""ServiceDispatcher-compatible RPC handlers for the accurate-FRET calibration.

The heavy work (population finding, bootstrapping) runs on the backend; a client
sends burst columns and receives the factors, populations and FRET lines as plain
JSON-able values.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import tttrlib

from .. import core as _core


def _serialize(result: _core.CalibrationResult) -> dict:
    """Reduce a calibration run to JSON-able values for the RPC reply."""
    line = result.line
    return {
        "factors": result.factors,
        "uncertainties": result.calibration.uncertainties,
        "gamma_estimates": result.calibration.gamma_estimates,
        "populations": result.calibration.populations,
        "messages": result.calibration.messages,
        "converged": bool(result.calibration.converged),
        "report": result.calibration.report(),
        "static_line": None
        if line is None
        else {
            "tau_f": np.asarray(line.tau_f).tolist(),
            "efficiency": np.asarray(line.efficiency).tolist(),
        },
    }


def auto_calibrate(params: dict) -> dict:
    """Calibrate accurate FRET from per-burst channel arrays.

    Parameters
    ----------
    params : dict
        ``{"i_dd": [...], "i_da": [...], "i_aa": [...], "tau_f": [...]}`` plus any
        keyword of :func:`chisurf.plugins.burst.accurate_fret.core.calibrate`.

    Returns
    -------
    dict
        ``{"ok": True, "result": {...}}`` or ``{"ok": False, "error": "..."}``.
    """
    try:
        payload = dict(params or {})
        i_dd = payload.pop("i_dd")
        i_da = payload.pop("i_da")
        i_aa = payload.pop("i_aa", None)
        tau_f = payload.pop("tau_f", None)
        result = _core.calibrate(i_dd, i_da, i_aa, tau_f, **payload)
        return {"ok": True, "result": _serialize(result)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def calibrate_file(params: dict) -> dict:
    """Calibrate accurate FRET from a burst table on disk.

    Parameters
    ----------
    params : dict
        ``{"path": str, "columns": {role: column_name}}`` plus any keyword of
        :func:`chisurf.plugins.burst.accurate_fret.core.calibrate`.

    Returns
    -------
    dict
        ``{"ok": True, "result": {...}}`` or ``{"ok": False, "error": "..."}``.
    """
    try:
        payload = dict(params or {})
        path = payload.pop("path")
        wanted = payload.pop("columns", None) or {}
        columns = _core.read_burst_table(path)
        mapping = {**tttrlib.guess_burst_columns(list(columns)), **wanted}
        arrays = {
            role: (
                None
                if mapping.get(role) not in columns
                else np.asarray(columns[mapping[role]], dtype=float)
            )
            for role in ("i_dd", "i_da", "i_aa", "tau_f")
        }
        if arrays["i_dd"] is None or arrays["i_da"] is None:
            return {"ok": False, "error": "the donor and FRET channel columns are required"}
        result = _core.calibrate(
            arrays["i_dd"], arrays["i_da"], arrays["i_aa"], arrays["tau_f"], **payload
        )
        return {"ok": True, "result": {**_serialize(result), "columns": mapping}}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def list_lightpaths(_params: Any = None) -> dict:
    """List the saved light paths usable as the optics prior."""
    return {"ok": True, "result": {"lightpaths": _core.list_lightpaths()}}


def register_services(dispatcher: Any) -> None:
    """Register the accurate-FRET RPC methods with *dispatcher*."""
    dispatcher.register("accurate_fret.calibrate", auto_calibrate)
    dispatcher.register("accurate_fret.calibrate_file", calibrate_file)
    dispatcher.register("accurate_fret.list_lightpaths", list_lightpaths)
