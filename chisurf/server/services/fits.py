from __future__ import annotations

import logging

import numpy as np

from typing import Any, Dict, List, Optional

from chisurf.server.jobs import JobManager
from chisurf.server.services import (
    ServiceResult,
    service_error,
    NOT_FOUND,
    INVALID_INPUT,
    INVALID_STATE,
    OPERATION_FAILED,
    _resolve_fit,
)
from chisurf.server.services._stats import (
    _collect_fit_params,
    _collect_member_list,
    _collect_param_list,
    _safe_chi2,
    _safe_chi2r,
    _safe_n_free,
    _safe_n_points,
)
from chisurf.server.services.datasets import _resolve_dataset
from chisurf.server.session import SessionState

logger = logging.getLogger(__name__)


def _fit_data_payload(fit: Any) -> Dict[str, Any]:
    """Extract data-reference metadata from a fit.

    Parameters
    ----------
    fit : object
        Fit instance.

    """
    data = getattr(fit, "data", None)
    if data is None:
        return {}
    return {
        "name": str(getattr(data, "name", "") or ""),
        "uid": str(getattr(data, "unique_identifier", "") or ""),
        "filename": str(getattr(data, "filename", "") or ""),
        "experiment": str(getattr(data, "experiment", "") or getattr(getattr(data, "experiment", None), "name", "") or ""),
    }


def _fit_model_payload(
    fit: Any,
    *,
    fit_uid: str,
    n_points: Optional[int] = None,
    n_free: Optional[int] = None,
    chi2r: Optional[float] = None,
) -> Dict[str, Any]:
    """Extract model metadata from a fit.

    Parameters
    ----------
    fit : object
        Fit instance.
    fit_uid : str
        Fit UID to embed in parameter entries.
    n_points : int, optional
        Pre-computed point count (avoids re-reading).
    n_free : int, optional
        Pre-computed free-parameter count.
    chi2r : float, optional
        Pre-computed reduced chi-squared value.

    """
    model = getattr(fit, "model", None)
    if model is None:
        return {}
    return {
        "name": str(getattr(model, "name", "") or ""),
        "n_points": _safe_n_points(fit) if n_points is None else n_points,
        "n_free": _safe_n_free(fit) if n_free is None else n_free,
        "chi2r": _safe_chi2r(fit) if chi2r is None else chi2r,
        "parameters_all": _collect_param_list(fit, fit_uid=fit_uid),
    }


def _fit_dto(fit: Any, index: int, *, detailed: bool = False) -> Dict[str, Any]:
    """Build a serialisable summary dict for a fit.

    Parameters
    ----------
    fit : object
        Fit instance.
    index : int
        Positional index.
    detailed : bool
        If ``True``, include all parameter details.

    """
    fit_uid = str(getattr(fit, "unique_identifier", "") or "")
    chi2 = _safe_chi2(fit)
    chi2r = _safe_chi2r(fit)
    n_points = _safe_n_points(fit)
    n_free = _safe_n_free(fit)
    parameters = _collect_fit_params(fit)
    parameter_count = len(parameters) if detailed else len(getattr(getattr(fit, "model", None), "parameters_all_dict", {}) or {})
    members = _collect_member_list(fit) if detailed else []
    return {
        "members": members,
        "index": index,
        "uid": fit_uid,
        "name": str(getattr(fit, "name", "") or ""),
        "type": type(fit).__name__,
        "chi2": chi2,
        "chi2r": chi2r,
        "n_points": n_points,
        "n_free": n_free,
        "dataset_name": str(getattr(getattr(fit, "data", None), "name", "") or ""),
        "dataset_uid": str(getattr(getattr(fit, "data", None), "unique_identifier", "") or ""),
        "model_name": str(getattr(getattr(fit, "model", None), "name", "") or ""),
        "parameter_count": parameter_count,
        "data": _fit_data_payload(fit),
        "model": _fit_model_payload(fit, fit_uid=fit_uid, n_points=n_points, n_free=n_free, chi2r=chi2r),
        "parameters": parameters,
    }


def list_fits(state: SessionState) -> ServiceResult:
    """Return a summary of all fits in the session.

    Parameters
    ----------
    state : SessionState
        Server-side session state.

    """
    fits = list(state.fits)
    return {
        "ok": True,
        "fits": [_fit_dto(f, idx) for idx, f in enumerate(fits)],
    }


def get_fit_info(
    state: SessionState,
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
) -> ServiceResult:
    """Return detailed info for a single fit.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    fit_index : int, optional
        Positional index.
    fit_uid : str, optional
        Unique identifier.

    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    return {
        "ok": True,
        "fit": _fit_dto(fit, idx, detailed=True),
    }


def run_fit(
    state: SessionState,
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
    event_bus: Any = None,
) -> ServiceResult:
    """Execute a fit and return results.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    fit_index : int, optional
        Positional index.
    fit_uid : str, optional
        Unique identifier.
    event_bus : object, optional
        Event bus for broadcasting.

    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    try:
        chi2_before = _safe_chi2(fit, compute=True)
        fit.run()
        chi2_after = _safe_chi2(fit, compute=True)
        fit_uid_val = str(getattr(fit, "unique_identifier", "") or "")
        if event_bus is not None:
            event_bus.publish("fit.ran", {"fit_index": idx, "fit_uid": fit_uid_val})
        return {
            "ok": True,
            "fit_index": idx,
            "fit_uid": fit_uid_val,
            "chi2_before": chi2_before,
            "chi2_after": chi2_after,
        }
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def fit_set_dataset(
    state: SessionState,
    fit_index: Optional[int] = None,
    dataset_index: Optional[int] = None,
    dataset_uid: Optional[str] = None,
    fit_uid: Optional[str] = None,
    event_bus: Any = None,
) -> ServiceResult:
    """Associate a dataset with a fit.

    A fit is addressed by index *or* uid, as everywhere else in this module.
    ``fit_uid`` was missing from the signature while the RPC layer passes it,
    so every uid-addressed call died in the dispatcher with ``fit_set_dataset()
    got an unexpected keyword argument 'fit_uid'`` -- the method was reachable
    by index only, and no caller could tell why.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    fit_index : int, optional
        Fit index.
    dataset_index : int, optional
        Dataset index.
    dataset_uid : str, optional
        Dataset UID.
    fit_uid : str, optional
        Fit UID, used when ``fit_index`` is not given.
    event_bus : object, optional
        Event bus for broadcasting.

    """
    fit, fit_index = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    d, _ = _resolve_dataset(state, dataset_index, dataset_uid)
    if d is None:
        return service_error("dataset not found", error_code=NOT_FOUND)
    try:
        fit.data = d
        if event_bus is not None:
            event_bus.publish("fit.dataset_changed", {"fit_index": fit_index})
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def fit_set_result_idx(
    state: SessionState,
    result_idx: int = 0,
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
    event_bus: Any = None,
) -> ServiceResult:
    """Set the active result index on a fit.

    ``fit_index`` was a required positional while ``fit_uid`` was optional, so
    addressing the fit the documented way -- by uid -- raised
    ``fit_set_result_idx() missing 1 required positional argument:
    'fit_index'`` in the dispatcher.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    fit_index : int, optional
        Fit index.
    result_idx : int
        Result index to set.
    fit_uid : str, optional
        Fit UID.
    event_bus : object, optional
        Event bus for broadcasting.

    """
    fit, actual_index = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    try:
        fit.set_result_idx(int(result_idx))
        if event_bus is not None:
            event_bus.publish("fit.result_idx_changed", {"fit_index": actual_index, "fit_uid": str(getattr(fit, "unique_identifier", "") or ""), "result_idx": int(result_idx)})
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def fit_set_fit_range(
    state: SessionState,
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
    xmin: int = 0,
    xmax: int = 0,
) -> ServiceResult:
    """Set the fit range on a server-side fit object."""
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    try:
        fit.fit_range = (int(xmin), int(xmax))
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def ping(state: SessionState) -> ServiceResult:
    """Liveness check returning server version and session counts.

    Parameters
    ----------
    state : SessionState
        Server-side session state.

    """
    import chisurf as cs
    from chisurf.server.protocol import PROTOCOL_VERSION
    return {
        "ok": True,
        "status": "alive",
        "version": getattr(cs, "__version__", "unknown"),
        "protocol_version": PROTOCOL_VERSION,
        "dataset_count": len(state.datasets),
        "fit_count": len(state.fits),
    }


def remove_fits(
    state: SessionState,
    fit_indices: Optional[List[int]] = None,
    fit_uids: Optional[List[str]] = None,
    event_bus: Any = None,
) -> ServiceResult:
    """Remove fits by index or uid.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    fit_indices : list of int, optional
        Indices to remove.
    fit_uids : list of str, optional
        UIDs to remove.
    event_bus : object, optional
        Event bus for broadcasting.

    """
    to_remove: set[int] = set()
    fits = list(state.fits)

    if fit_uids:
        for i, f in enumerate(fits):
            if str(getattr(f, "unique_identifier", "")) in fit_uids:
                to_remove.add(i)

    if fit_indices:
        for i in fit_indices:
            if 0 <= int(i) < len(fits):
                to_remove.add(int(i))

    if not to_remove:
        return service_error("no fits specified for removal", error_code=INVALID_INPUT)

    kept = [f for i, f in enumerate(fits) if i not in to_remove]
    state.fits[:] = kept
    if event_bus is not None:
        event_bus.publish("fit.removed", {"removed_count": len(to_remove), "remaining_count": len(kept)})
    return {"ok": True, "removed_count": len(to_remove), "remaining_count": len(kept)}


def clear_fits(state: SessionState, event_bus: Any = None) -> ServiceResult:
    """Remove all fits from the session.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    event_bus : object, optional
        Event bus for broadcasting.

    """
    count = len(state.fits)
    state.fits.clear()
    if event_bus is not None:
        event_bus.publish("fit.cleared", {"cleared_count": count})
    return {"ok": True, "cleared_count": count}


def _initialise_fit_range(fit: Any) -> None:
    """Give a newly created fit a range it can actually be run over.

    A fresh fit's range is ``(0, 0)``, and the optimiser rejects that with
    ``Improper input: N=4 must not exceed M=(0,)`` — so a fit created over RPC
    could be created but never run. The reader's ``autofitrange`` is preferred,
    because that is what the GUI and the agent layer both use; a dataset built
    from raw ``curve_data`` over the wire has no reader, so the whole curve is
    the fallback rather than nothing.

    Parameters
    ----------
    fit : object
        The newly created fit.
    """
    data = getattr(fit, "data", None)
    if data is None:
        return
    reader = getattr(data, "data_reader", None)
    if reader is not None and hasattr(reader, "autofitrange"):
        try:
            start, stop = reader.autofitrange(data)
            fit.fit_range = (int(start), int(stop))
            return
        except Exception:
            logger.debug("autofitrange failed; falling back to the whole curve", exc_info=True)
    try:
        n = len(data)
        if n > 1:
            fit.fit_range = (0, int(n) - 1)
    except Exception:
        logger.debug("could not derive a fit range from the data", exc_info=True)


def _model_names() -> list:
    """Return the names of every model class currently reachable.

    Used only to make "model not found" actionable: a name that cannot be
    resolved is far easier to correct next to the list of ones that can.
    """
    from chisurf.core.models.model import Model

    found = []

    def walk(cls):
        for sc in cls.__subclasses__():
            name = getattr(sc, "name", None)
            if isinstance(name, str) and "not available" not in name:
                found.append(name)
            walk(sc)

    walk(Model)
    return sorted(set(found))


def fit_create(
    state: SessionState,
    dataset_index: int = 0,
    dataset_indices: Optional[List[int]] = None,
    model_name: Optional[str] = None,
    fit_name: Optional[str] = None,
    model_kw: Optional[Dict[str, Any]] = None,
    event_bus: Any = None,
) -> ServiceResult:
    """Create a new fit on the server and append to SessionState.

    Supports both a single ``dataset_index`` and a list ``dataset_indices``
    (matching the ``core_fit.add_fit`` macro).  ``model_kw`` is forwarded to
    the model constructor.
    """
    datasets = list(state.datasets)
    if not datasets:
        return service_error("no datasets available", error_code=INVALID_STATE)
    indices = dataset_indices if dataset_indices is not None else [dataset_index]
    for i in indices:
        if i < 0 or i >= len(datasets):
            return service_error(f"dataset index {i} out of range", error_code=INVALID_INPUT)
    data_groups = [datasets[i] for i in indices]
    try:
        from chisurf.core.models.model import Model
        from chisurf.core.fitting.fit import FitGroup
    except ImportError as e:
        return service_error(f"fit model/fit classes not importable: {e}", error_code=OPERATION_FAILED, exception=e)
    try:
        # A model is found by walking ``Model.__subclasses__()``, which only
        # sees classes that have been *imported*. The server imports none of
        # them: measured in a fresh server process, exactly one model class was
        # reachable ("Global fit", pulled in by the fitting machinery), so every
        # ``fit.create`` naming a real model answered "model 'X' not found" and
        # the RPC server could not build a fit at all. Registering the
        # experiments imports them -- the same headless bootstrap the agent
        # layer runs, and a no-op once something else has already done it.
        try:
            from chisurf.core.experiments.bootstrap import ensure_experiments_registered

            ensure_experiments_registered()
        except Exception:
            logger.debug("experiment registration failed", exc_info=True)

        model_class = None
        if model_name:
            def _find_model(cls):
                """Recursively search for a model subclass by ``name``."""
                for sc in cls.__subclasses__():
                    if getattr(sc, 'name', None) == model_name:
                        return sc
                    r = _find_model(sc)
                    if r is not None:
                        return r
                return None
            model_class = _find_model(Model)
        if model_class is None:
            return service_error(
                f"model '{model_name}' not found. Available: {sorted(_model_names())}",
                error_code=NOT_FOUND,
            )
        kw = dict(model_kw) if model_kw else {}
        # ``FitGroup`` *iterates* its data to build one member fit per dataset.
        # A bare ``DataCurve`` iterates into ``(x, y)`` tuples, so passing one
        # for the single-dataset case built member fits whose ``data`` was a
        # tuple, and the first thing to read ``data.x`` failed with
        # ``'tuple' object has no attribute 'x'``. A group is the type this
        # takes, one dataset or several.
        from chisurf.core.data import DataGroup

        data = data_groups[0] if isinstance(data_groups[0], DataGroup) else DataGroup(data_groups)
        fit = FitGroup(
            data=data,
            model_class=model_class,
            **kw,
        )
        if fit_name:
            fit.name = fit_name
        _initialise_fit_range(fit)
        state.add_fit(fit)
        if event_bus is not None:
            event_bus.publish("fit.created", {"fit_index": len(state.fits) - 1, "fit_uid": str(getattr(fit, "unique_identifier", "") or "")})
        return {
            "ok": True,
            "uid": str(getattr(fit, "unique_identifier", "") or ""),
            "name": str(getattr(fit, "name", "") or ""),
            "fit_index": len(state.fits) - 1,
        }
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def fit_update(
    state: SessionState,
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
    event_bus: Any = None,
) -> ServiceResult:
    """Update a fit (calls fit.update() on server-side object)."""
    fit, _ = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    try:
        if hasattr(fit, "update"):
            fit.update()
            if event_bus is not None:
                event_bus.publish("fit.updated", {"fit_index": fit_index, "fit_uid": fit_uid or str(getattr(fit, "unique_identifier", "") or "")})
            return {"ok": True}
        return service_error("fit has no update method", error_code=OPERATION_FAILED)
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def fit_save(
    state: SessionState,
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
    filename: str = "fit_export",
    file_type: str = "csv",
    save_curves: bool = False,
    event_bus: Any = None,
) -> ServiceResult:
    """Save a fit's results to disk on the server."""
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    try:
        fit.save(filename, file_type, save_curves=save_curves)
        return {"ok": True, "saved_to": filename}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def _downsample(
    values: Optional[List[float]],
    max_points: int,
) -> Optional[List[Optional[float]]]:
    """Downsample *values* to at most *max_points*.

    Parameters
    ----------
    values : list of float, optional
        Input array.
    max_points : int
        Maximum number of points to return.

    """
    if values is None or not values:
        return values
    if len(values) <= max_points:
        return values
    step = max(1, len(values) // max_points)
    return values[::step]


def _sanitize_metrics(value: Optional[float]) -> Optional[float]:
    """Return ``None`` for NaN / inf / None."""
    if value is None:
        return None
    import numpy as np
    try:
        v = float(value)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    except Exception:
        return None


def fit_diagnostics(
    state: SessionState,
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
    max_points: int = 500,
) -> ServiceResult:
    """Return comprehensive diagnostics for a fit.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    fit_index : int, optional
        Positional index.
    fit_uid : str, optional
        Unique identifier.
    max_points : int, default 500
        Maximum number of curve data points.

    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    try:
        from chisurf.server.services.datasets import _sanitize_float_list
        fit_uid_val = str(getattr(fit, "unique_identifier", "") or "")
        chi2 = _safe_chi2(fit, compute=True)
        chi2r = _safe_chi2r(fit, compute=True)
        n_points = _safe_n_points(fit)
        n_free = _safe_n_free(fit)
        parameters = _collect_fit_params(fit)
        params_list: List[Dict[str, Any]] = []
        for name, p in parameters.items():
            params_list.append({
                "name": name,
                "value": p.get("value"),
                "fixed": p.get("fixed", False),
                "bounds": p.get("bounds"),
                "bounds_on": p.get("bounds_on", False),
                "linked_to": p.get("linked_to", ""),
                "error_estimate": p.get("error_estimate"),
            })

        result: Dict[str, Any] = {
            "ok": True,
            "fit": {
                "index": idx,
                "uid": fit_uid_val,
                "name": str(getattr(fit, "name", "") or ""),
            },
            "metrics": {
                "chi2": _sanitize_metrics(chi2),
                "chi2r": _sanitize_metrics(chi2r),
                "n_points": n_points,
                "n_free": n_free,
            },
            "parameters": params_list,
        }

        data = getattr(fit, "data", None)
        model = getattr(fit, "model", None)
        x: Optional[List[Optional[float]]] = None
        y: Optional[List[Optional[float]]] = None
        if data is not None:
            x = _sanitize_float_list(getattr(data, "x", None))
            y = _sanitize_float_list(getattr(data, "y", None))

        fit_y: Optional[List[Optional[float]]] = None
        if model is not None:
            fit_y = _sanitize_float_list(getattr(model, "y", None))

        residuals: Optional[List[Optional[float]]] = None
        if model is not None:
            residuals = _sanitize_float_list(getattr(model, "residuals", None))

        result["curve"] = {
            "x": _downsample(x, max_points),
            "y": _downsample(y, max_points),
            "fit_y": _downsample(fit_y, max_points),
            "residuals": _downsample(residuals, max_points),
        }

        residual_stats: Optional[Dict[str, float]] = None
        if residuals and any(r is not None for r in residuals):
            import numpy as np
            arr = np.array([r for r in residuals if r is not None], dtype=float)
            if len(arr) > 0:
                residual_stats = {
                    "mean": float(np.mean(arr)),
                    "std": float(np.std(arr)),
                    "max_abs": float(np.max(np.abs(arr))),
                }
        result["residual_stats"] = residual_stats

        return result
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def fit_parameter_snapshot(
    state: SessionState,
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
) -> ServiceResult:
    """Capture a snapshot of all fit parameters for later restoration.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    fit_index : int, optional
        Positional index.
    fit_uid : str, optional
        Unique identifier.

    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    try:
        fit_uid_val = str(getattr(fit, "unique_identifier", "") or "")
        parameters = _collect_fit_params(fit)
        snapshot_params: List[Dict[str, Any]] = []
        for name, p in parameters.items():
            snapshot_params.append({
                "name": name,
                "value": p.get("value"),
                "fixed": p.get("fixed", False),
                "bounds": p.get("bounds"),
                "bounds_on": p.get("bounds_on", False),
                "linked_to": p.get("linked_to", ""),
            })
        return {
            "ok": True,
            "fit": {
                "index": idx,
                "uid": fit_uid_val,
                "name": str(getattr(fit, "name", "") or ""),
            },
            "snapshot": {
                "parameters": snapshot_params,
            },
        }
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def fit_restore_parameters(
    state: SessionState,
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
    snapshot: Optional[Dict[str, Any]] = None,
) -> ServiceResult:
    """Restore fit parameters from a previously captured snapshot.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    fit_index : int, optional
        Positional index.
    fit_uid : str, optional
        Unique identifier.
    snapshot : dict, optional
        Snapshot dict with a ``"parameters"`` list.

    """
    if not snapshot or "parameters" not in snapshot:
        return service_error(
            "snapshot must contain 'parameters' list",
            error_code=INVALID_INPUT,
        )
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    try:
        params_dict: Dict[str, Any] = {}
        if hasattr(fit, "model") and fit.model is not None:
            params_dict = getattr(fit.model, "parameters_all_dict", {}) or {}

        restored_count = 0
        for sp in snapshot["parameters"]:
            name = sp.get("name", "")
            param = params_dict.get(name)
            if param is None:
                continue
            if "value" in sp and sp["value"] is not None:
                param.value = float(sp["value"])
            if "fixed" in sp:
                param.fixed = bool(sp["fixed"])
            if "bounds" in sp and sp["bounds"] is not None:
                param.bounds = tuple(float(v) for v in sp["bounds"])
            if "bounds_on" in sp:
                param.bounds_on = bool(sp["bounds_on"])
            restored_count += 1

        if hasattr(fit.model, "update_model"):
            fit.model.update()
        if hasattr(fit.model, "finalize"):
            fit.model.finalize()

        diagnostics = fit_diagnostics(state, fit_index=idx)
        diag_data = diagnostics if diagnostics.get("ok") else {}

        return {
            "ok": True,
            "restored_count": restored_count,
            "diagnostics": diag_data,
        }
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def fit_curve_data(
    state: SessionState,
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
) -> ServiceResult:
    """Return the fit's calculated curve data for plotting."""
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    try:
        from chisurf.server.services.datasets import _sanitize_float_list
        result: Dict[str, Any] = {"ok": True}
        # Experimental data
        data = getattr(fit, "data", None)
        if data is not None:
            result["x"] = _sanitize_float_list(getattr(data, "x", None))
            result["y"] = _sanitize_float_list(getattr(data, "y", None))
        # Calculated curve from model
        model = getattr(fit, "model", None)
        if model is not None:
            result["fx"] = _sanitize_float_list(getattr(model, "x", None))
            result["fy"] = _sanitize_float_list(getattr(model, "y", None))
            result["residuals"] = _sanitize_float_list(getattr(model, "residuals", None))
        # Combined fit curve (for convenience)
        fit_curve = getattr(fit, "fit", None)
        if fit_curve is not None:
            result["fit_x"] = _sanitize_float_list(getattr(fit_curve, "x", None))
            result["fit_y"] = _sanitize_float_list(getattr(fit_curve, "y", None))
        return result
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


# ── New RPC methods for the ZMQ migration ────────────────────────────


def fit_reorder(
    state: SessionState,
    fit_order: List[str],
    event_bus: Any = None,
) -> ServiceResult:
    """Reorder fits by providing a list of UIDs in the desired order.

    Parameters
    ----------
    state : SessionState
    fit_order : list of str
        Fit UIDs in the new order.
    event_bus : object, optional
    """
    uid_to_fit = {}
    for f in state.fits:
        uid = str(getattr(f, "unique_identifier", "") or "")
        uid_to_fit[uid] = f
    missing = [uid for uid in fit_order if uid not in uid_to_fit]
    if missing:
        return service_error(
            f"fit UIDs not found: {missing}",
            error_code=NOT_FOUND,
        )
    reordered = [uid_to_fit[uid] for uid in fit_order]
    # Append any fits not in the new order to the end
    existing = set(fit_order)
    for f in state.fits:
        uid = str(getattr(f, "unique_identifier", "") or "")
        if uid not in existing:
            reordered.append(f)
    state.fits[:] = reordered
    if event_bus is not None:
        event_bus.publish("fit.reordered", {"fit_order": fit_order})
    return {"ok": True, "count": len(reordered)}


def fit_select(
    state: SessionState,
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
    _action: str = "set",
    event_bus: Any = None,
) -> ServiceResult:
    """Set or get the active (current) fit.

    When ``_action`` is ``"get"``, returns the current active fit DTO
    without changing anything.  When ``"set"``, sets the active fit from
    *fit_index* or *fit_uid*.
    """
    if _action == "get":
        active_uid = getattr(state, "current_fit_uid", None)
        if not active_uid:
            return {"ok": True, "fit": {}}
        fit, idx = _resolve_fit(state, fit_uid=active_uid)
        if fit is None:
            return {"ok": True, "fit": {}}
        return {"ok": True, "fit": _fit_dto(fit, idx)}
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    state.current_fit_uid = str(getattr(fit, "unique_identifier", "") or "")
    if event_bus is not None:
        event_bus.publish(
            "fit.selected",
            {"fit_index": idx, "fit_uid": state.current_fit_uid},
        )
    return {"ok": True}


def fit_group_select_member(
    state: SessionState,
    fit_uid: str,
    member_index: int,
    event_bus: Any = None,
) -> ServiceResult:
    """Change the selected member of a fit group.

    Parameters
    ----------
    state : SessionState
    fit_uid : str
        UID of the fit group.
    member_index : int
        Index of the member to select.
    event_bus : object, optional
    """
    fit, idx = _resolve_fit(state, fit_uid=fit_uid)
    if fit is None:
        return service_error("fit group not found", error_code=NOT_FOUND)
    try:
        grouped = getattr(fit, "grouped_fits", None)
        if not grouped:
            return service_error("fit has no grouped fits", error_code=INVALID_STATE)
        if member_index < 0 or member_index >= len(grouped):
            return service_error(
                f"member index {member_index} out of range (0-{len(grouped) - 1})",
                error_code=INVALID_INPUT,
            )
        # ``selected_fit`` stores the *index* of the active member (see
        # FitGroup.selected_fit). Assigning the Fit object here corrupted
        # ``_selected_fit_index`` and broke later ``grouped_fits[index]`` lookups.
        fit.selected_fit = member_index
        if event_bus is not None:
            event_bus.publish(
                "fit.group.member_selected",
                {"fit_uid": fit_uid, "member_index": member_index},
            )
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def fit_group_add_member(
    state: SessionState,
    group_fit_uid: str,
    member_fit_uid: str,
    event_bus: Any = None,
) -> ServiceResult:
    """Add a fit as a member of a fit group (global fit)."""
    group_fit, _ = _resolve_fit(state, fit_uid=group_fit_uid)
    if group_fit is None:
        return service_error("group fit not found", error_code=NOT_FOUND)
    member_fit, _ = _resolve_fit(state, fit_uid=member_fit_uid)
    if member_fit is None:
        return service_error("member fit not found", error_code=NOT_FOUND)
    try:
        from chisurf.core.fitting.fit import FitGroup
        if not isinstance(group_fit, FitGroup):
            return service_error("group fit is not a FitGroup", error_code=INVALID_STATE)
        grouped = getattr(group_fit, "grouped_fits", None)
        if grouped is None:
            return service_error("group fit has no grouped_fits attribute", error_code=INVALID_STATE)
        grouped.append(member_fit)
        if event_bus is not None:
            event_bus.publish(
                "fit.group.member_added",
                {"group_fit_uid": group_fit_uid, "member_fit_uid": member_fit_uid},
            )
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def fit_group_remove_member(
    state: SessionState,
    group_fit_uid: str,
    member_index: int,
    event_bus: Any = None,
) -> ServiceResult:
    """Remove a member from a fit group by index."""
    group_fit, _ = _resolve_fit(state, fit_uid=group_fit_uid)
    if group_fit is None:
        return service_error("group fit not found", error_code=NOT_FOUND)
    try:
        grouped = getattr(group_fit, "grouped_fits", None)
        if not grouped:
            return service_error("group fit has no members", error_code=INVALID_STATE)
        if member_index < 0 or member_index >= len(grouped):
            return service_error(
                f"member index {member_index} out of range",
                error_code=INVALID_INPUT,
            )
        removed = grouped.pop(member_index)
        if event_bus is not None:
            event_bus.publish(
                "fit.group.member_removed",
                {
                    "group_fit_uid": group_fit_uid,
                    "member_index": member_index,
                    "removed_fit_uid": str(getattr(removed, "unique_identifier", "") or ""),
                },
            )
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def fit_group_link_parameters_by_name(
    state: SessionState,
    group_fit_uid: str,
    parameter_name: str,
    event_bus: Any = None,
) -> ServiceResult:
    """Link a parameter across all members of a fit group by name."""
    group_fit, _ = _resolve_fit(state, fit_uid=group_fit_uid)
    if group_fit is None:
        return service_error("group fit not found", error_code=NOT_FOUND)
    try:
        grouped = getattr(group_fit, "grouped_fits", None)
        if not grouped:
            return service_error("group fit has no members", error_code=INVALID_STATE)
        # Find the master parameter from the first member
        master_param = None
        for member in grouped:
            model = getattr(member, "model", None)
            if model is None:
                continue
            params = getattr(model, "parameters_all_dict", {}) or {}
            if parameter_name in params:
                master_param = params[parameter_name]
                break
        if master_param is None:
            return service_error(
                f"parameter '{parameter_name}' not found in any group member",
                error_code=NOT_FOUND,
            )
        # Link all other members' parameters of the same name
        for member in grouped:
            model = getattr(member, "model", None)
            if model is None:
                continue
            params = getattr(model, "parameters_all_dict", {}) or {}
            if parameter_name in params:
                param = params[parameter_name]
                if param is not master_param and hasattr(param, "link"):
                    param.link = master_param
        if event_bus is not None:
            event_bus.publish(
                "fit.group.parameters_linked",
                {"group_fit_uid": group_fit_uid, "parameter_name": parameter_name},
            )
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def fit_range_auto(
    state: SessionState,
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
) -> ServiceResult:
    """Compute auto fit range on the server.

    Uses the data reader's ``autofitrange`` method when available.
    Returns ``xmin``, ``xmax`` (and ``xmin2``, ``xmax2`` for 2D datasets).
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    try:
        data = getattr(fit, "data", None)
        if data is None:
            return service_error("fit has no data", error_code=INVALID_STATE)
        reader = getattr(data, "data_reader", None)
        if reader is None or not hasattr(reader, "autofitrange"):
            return service_error("data reader has no autofitrange", error_code=INVALID_STATE)
        fit_range = reader.autofitrange(data)
        xmin, xmax = fit_range
        fit.fit_range = (int(xmin), int(xmax))
        result: Dict[str, Any] = {
            "ok": True,
            "xmin": int(xmin),
            "xmax": int(xmax),
            "applied": True,
        }
        # Check for 2D grid metadata
        meta = getattr(data, "meta_data", {}) or {}
        grid = meta.get("grid", {}) or {}
        if grid.get("ndim") == 2 and grid.get("shape") is not None:
            shape = grid["shape"]
            result["xmin2"] = 0
            result["xmax2"] = int(shape[1]) - 1
        return result
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def fit_mask_set(
    state: SessionState,
    mask: List[float],
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
    event_bus: Any = None,
) -> ServiceResult:
    """Set a fit mask from plot-side region selection.

    Parameters
    ----------
    state : SessionState
    mask : list of float
        Mask array (1 for included, 0 for excluded).
    fit_index : int, optional
    fit_uid : str, optional
    event_bus : object, optional
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    try:
        import numpy as np
        fit.mask = np.asarray(mask, dtype=float)
        if event_bus is not None:
            event_bus.publish(
                "fit.mask_changed",
                {"fit_index": idx, "fit_uid": str(getattr(fit, "unique_identifier", "") or "")},
            )
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


# ── Sampling (job-based) ─────────────────────────────────────────────


SAMPLE_ACTION = "fit.sample"
"""Job action of a posterior-sampling run."""

PARAMETER_SCAN_ACTION = "fit.parameter_scan"
"""Job action of a one-parameter chi-square scan."""

_JOBS = JobManager()
"""The one registry for the server's long-running fit work.

Sampling and parameter scans each used to keep their own bare ``dict`` of job
state, mutated from worker threads without a lock and never pruned. Both now go
through :class:`~chisurf.server.jobs.JobManager`, so status transitions,
cooperative cancellation and history trimming are implemented once (INC-08).
"""


def _job_or_error(job_id: str, action: str):
    """Return the job with *job_id* if it belongs to *action*, else an error.

    Parameters
    ----------
    job_id : str
        Job identifier as handed out by the matching ``*_start`` call.
    action : str
        Action the job must carry, so a sampling id cannot be polled through
        the parameter-scan endpoints and vice versa.

    Returns
    -------
    tuple
        ``(job, None)`` when found, otherwise ``(None, service_error(...))``.

    """
    job = _JOBS.get_job(job_id)
    if job is None or job.action != action:
        return None, service_error(f"job {job_id} not found", error_code=NOT_FOUND)
    return job, None


def fit_sample_start(
    state: SessionState,
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
    n_steps: int = 1000,
    n_runs: int = 1,
    target_directory: Optional[str] = None,
    **kwargs: Any,
) -> ServiceResult:
    """Start a sampling job on the server side (async).

    Launches ``sample_fit`` in a background thread and returns
    immediately with a ``job_id``. Poll ``fit.sample.status`` for
    progress and call ``fit.sample.cancel`` to request cancellation.

    Extra keyword arguments are merged over the ``optimization.sampling``
    settings and forwarded to
    :func:`chisurf.core.fitting.fit.sample_fit` -- notably ``method``
    (``blocked`` / ``collapsed`` / ``ensemble`` / ``slice`` / ``mcmc``) and
    ``global_posterior``.

    ``fit.sample.status`` reports the resulting convergence verdict, so a caller
    can tell a finished job from a trustworthy one.
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    job = _JOBS.create_job(SAMPLE_ACTION, {
        "fit_uid": str(getattr(fit, "unique_identifier", "") or ""),
        "fit_index": idx,
    })
    job_id = job.job_id

    import copy as _copy
    kw = _copy.copy(dict(
        n_runs=int(n_runs),
        steps=int(n_steps),
        **kwargs,
    ))
    target_dir_val = target_directory or ""

    def _run() -> Dict[str, Any]:
        def _progress_callback(done: int, total: int) -> None:
            _JOBS.set_progress(job_id, int(100.0 * done / total) if total > 0 else 0)

        def _check_cancel() -> bool:
            return _JOBS.should_cancel(job_id)

        import chisurf.core.settings
        settings_kw = chisurf.core.settings.cs_settings.get(
            'optimization', {}
        ).get('sampling', {}).copy()
        settings_kw.update(kw)

        from chisurf.core.fitting.fit import sample_fit
        report = sample_fit(
            fit,
            target_directory=target_dir_val,
            progress_callback=_progress_callback,
            check_cancel=_check_cancel,
            **settings_kw,
        )
        _JOBS.set_progress(job_id, 100)
        # A finished job is not the same as a trustworthy one. The convergence
        # report is the only thing that distinguishes a chain worth quoting from
        # one that never left its starting point, so it travels with the job
        # rather than being discarded.
        if isinstance(report, dict):
            return {
                "diagnostics": report,
                "warnings": list(report.get("warnings") or []),
                "converged": not report.get("warnings"),
            }
        return {"diagnostics": None, "warnings": [], "converged": None}

    _JOBS.start_threaded(job, _run)
    _JOBS.cleanup()
    return {"ok": True, "job_id": job_id}


def fit_posterior(
    state: SessionState,
    fit_index: int | None = None,
    fit_uid: str | None = None,
    engine: str = "stored",
    targets: list[str] | None = None,
    joint: list[str] | None = None,
    condition: dict[str, float] | None = None,
    p_value: float = 0.68,
    options: dict[str, Any] | None = None,
    global_posterior: bool = False,
) -> ServiceResult:
    """Ask one question of any uncertainty estimator.

    The three estimators reach RPC as three separate job protocols
    (``fit.sample.*``, ``fit.parameter_scan.*``, and error estimates riding
    along on a fit) even though they answer the same question. This is the one
    query surface over :mod:`chisurf.core.fitting.engine`.

    Parameters
    ----------
    state : SessionState
        Server session.
    fit_index, fit_uid : int or str, optional
        Which fit to query.
    engine : {"stored", "laplace", "profile", "mcmc", "auto"}, optional
        Which estimator. ``stored`` reports what has already been computed and
        costs nothing; ``laplace`` is a covariance evaluation. ``profile`` and
        ``mcmc`` **block** for as long as they take -- use the existing
        ``fit.sample.*`` / ``fit.parameter_scan.*`` job endpoints when the
        caller needs to poll.
    targets : list of str, optional
        Parameters to report. Defaults to every free parameter.
    joint : list of str, optional
        Parameters to report a joint answer over.
    condition : dict, optional
        Parameters to hold fixed (``name -> value``) while the rest are
        re-optimised.
    p_value : float, optional
        Interval coverage.
    options : dict, optional
        Engine options, e.g. ``steps`` and ``n_runs`` for ``mcmc``.
    global_posterior : bool, optional
        Query a group's *joint* posterior rather than its selected member's.

    Returns
    -------
    ServiceResult
        ``marginals`` (one entry per target), ``joint`` when requested,
        ``log_evidence``, and the ``engine`` that answered.
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)

    from chisurf.core.fitting import engine as engine_module
    from chisurf.core.fitting import factorgraph

    model = factorgraph.posterior_model(fit) if global_posterior else getattr(fit, "model", None)
    try:
        eng = engine_module.get_engine(str(engine), fit, model=model)
    except ValueError as e:
        return service_error(str(e), error_code=INVALID_INPUT)

    for name, value in (condition or {}).items():
        eng.condition(str(name), float(value))
    if targets:
        for name in targets:
            eng.add_target(str(name))
    else:
        eng.add_all_targets()
    if joint:
        eng.add_joint_target([str(n) for n in joint])

    try:
        eng.run(p_value=float(p_value), **(options or {}))
    except Exception as e:
        return service_error(f"{engine} engine failed: {e}")

    payload: dict[str, Any] = {
        "ok": True,
        "fit_index": idx,
        "engine": str(engine),
        "p_value": float(p_value),
        "marginals": [m.as_dict() for m in eng.marginals()],
    }
    evidence = eng.log_evidence()
    payload["log_evidence"] = float(evidence) if np.isfinite(evidence) else None
    if joint:
        j = eng.joint([str(n) for n in joint])
        payload["joint"] = None if j is None else {
            "names": list(j.names),
            "mean": [float(v) for v in np.asarray(j.mean).ravel()],
            "covariance": [[float(v) for v in row] for row in np.asarray(j.covariance)],
            "correlation": [[float(v) for v in row] for row in np.asarray(j.correlation)],
            "method": j.method,
        }
    return payload


def fit_reweight_prior(
    state: SessionState,
    priors: dict[str, Any],
    fit_index: int | None = None,
    fit_uid: str | None = None,
    p_value: float = 0.68,
) -> ServiceResult:
    """Reuse a completed sampling run under different priors, without sampling.

    A prior changes the posterior but not the likelihood, so draws already taken
    can be reweighted to the new posterior rather than discarded. This evaluates
    no model at all -- the ratio is a difference of two scalar prior densities at
    points already in hand -- so it answers in milliseconds what re-sampling
    answers in minutes.

    The shortcut is not always valid, and says so: ``pareto_k`` above 0.7 means
    the new prior favours a region the chain never explored, and the reported
    numbers must be discarded in favour of sampling again. See
    :mod:`chisurf.core.fitting.reweight`.

    Parameters
    ----------
    state : SessionState
        Server session.
    priors : dict
        Parameter name to the new prior as a ``get_state`` dict, e.g.
        ``{"tau1": {"kind": "normal", "mu": 4.0, "sigma": 0.2}}``. ``None``
        removes that parameter's prior.
    fit_index, fit_uid : int or str, optional
        Which fit to query.
    p_value : float, optional
        Interval coverage for the reported quantiles.

    Returns
    -------
    ServiceResult
        ``parameters``, ``pareto_k``, ``ess``, ``reliable``, ``changed`` and
        ``warnings``; an error when the fit carries no chain to reweight.
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    if not isinstance(priors, dict) or not priors:
        return service_error(
            "priors must be a non-empty mapping of parameter name to prior state",
            error_code=INVALID_INPUT,
        )

    chain = getattr(fit, "sampling_chain", None)
    if not isinstance(chain, dict) or chain.get("parameter_values") is None:
        return service_error(
            "this fit has no stored chain to reweight -- run a sampling job first",
            error_code=NOT_FOUND,
        )

    from chisurf.core.fitting import reweight as reweight_module

    # Quantiles matching the requested coverage, so the interval means the same
    # thing it does for every other estimator.
    tail = 0.5 * (1.0 - float(p_value))
    quantiles = (tail, 0.5, 1.0 - tail)
    try:
        out = reweight_module.reweight_prior(
            chain, priors, model=getattr(fit, "model", None), quantiles=quantiles
        )
    except KeyError as e:
        return service_error(str(e), error_code=INVALID_INPUT)
    except Exception as e:
        return service_error(f"reweighting failed: {e}")

    # ``pareto_k`` is deliberately inf when the weights are past smoothing, and
    # nan when the tail was too short to diagnose; neither survives JSON. The
    # verdict itself is in ``reliable`` and spelled out in ``warnings``.
    k = out["pareto_k"]
    return {
        "ok": True,
        "fit_index": idx,
        "p_value": float(p_value),
        "parameters": out["parameters"],
        "pareto_k": float(k) if np.isfinite(k) else None,
        "ess": out["ess"],
        "n_draws": out["n_draws"],
        "reliable": out["reliable"],
        "changed": out["changed"],
        "warnings": out["warnings"],
    }


def fit_derived(
    state: SessionState,
    fit_index: int | None = None,
    fit_uid: str | None = None,
    names: list[str] | None = None,
    p_value: float = 0.68,
    max_draws: int = 2048,
) -> ServiceResult:
    """Report the quantities a model computes but does not fit, with intervals.

    A FRET efficiency or a mean lifetime is a function of the fitted parameters,
    and until this existed it left the program as a bare number. It inherits the
    parameters' uncertainty, and -- being a non-linear function of them -- a
    shape as well: a ratio's posterior is skewed even when everything behind it
    is Gaussian. See :mod:`chisurf.core.fitting.derived`.

    Parameters
    ----------
    state : SessionState
        Server session.
    fit_index, fit_uid : int or str, optional
        Which fit to query.
    names : list of str, optional
        Quantities to report. Defaults to whatever the model declares.
    p_value : float, optional
        Central coverage of the reported interval.
    max_draws : int, optional
        Cap on posterior draws evaluated; the chain is thinned to fit.

    Returns
    -------
    ServiceResult
        ``quantities``, one entry each with ``value``, ``median``, ``low``,
        ``high``, ``method`` (``draws``, ``delta`` or ``none``), ``converged``
        and ``warning``.
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)

    from chisurf.core.fitting import derived as derived_module

    try:
        rows = derived_module.derived_posterior(
            fit,
            names=[str(n) for n in names] if names else None,
            p_value=float(p_value),
            max_draws=int(max_draws),
        )
    except Exception as e:
        return service_error(f"derived-quantity report failed: {e}")

    # nan/inf do not survive JSON; a missing end is None rather than a number
    # the caller would have to know to distrust.
    def _clean(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return v if np.isfinite(v) else None

    return {
        "ok": True,
        "fit_index": idx,
        "p_value": float(p_value),
        "quantities": [
            {**{k: v for k, v in row.items()
                if k not in ("value", "median", "low", "high", "sd", "asymmetry",
                             "skew")},
             "value": _clean(row.get("value")),
             "median": _clean(row.get("median")),
             "low": _clean(row.get("low")),
             "high": _clean(row.get("high")),
             "sd": _clean(row.get("sd")),
             "asymmetry": _clean(row.get("asymmetry")),
             "skew": _clean(row.get("skew"))}
            for row in rows
        ],
    }


def fit_sample_cancel(
    state: SessionState,
    job_id: str,
) -> ServiceResult:
    """Cancel a running sampling job.

    Sets the job's cancellation event, which the worker thread observes via the
    ``check_cancel`` callback passed to ``sample_fit``.
    """
    job, error = _job_or_error(job_id, SAMPLE_ACTION)
    if error is not None:
        return error
    _JOBS.cancel_job(job_id)
    return {"ok": True}


def fit_sample_status(
    state: SessionState,
    job_id: str,
) -> ServiceResult:
    """Get the status of a sampling job.

    Besides ``status`` and ``progress`` this reports whether the finished chain
    is worth believing: ``converged`` (``None`` while running, ``False`` when
    the chain failed its R-hat / effective-sample-size checks), the human
    readable ``warnings``, and the full per-parameter ``diagnostics`` report
    that was also written to ``diagnostics.json``.
    """
    job, error = _job_or_error(job_id, SAMPLE_ACTION)
    if error is not None:
        return error
    report = job.result if isinstance(job.result, dict) else {}
    return {
        "ok": True,
        "job_id": job_id,
        "status": job.status.value,
        "progress": job.progress,
        "error": job.error,
        # ``converged`` is None until the job finishes, then False when the
        # chain failed its own R-hat / effective-sample-size checks. A caller
        # that only looks at ``status`` cannot tell those apart.
        "converged": report.get("converged"),
        "warnings": report.get("warnings", []),
        "diagnostics": report.get("diagnostics"),
    }


# ── Parameter scan (job-based) ───────────────────────────────────────


def fit_parameter_scan_start(
    state: SessionState,
    parameter_name: str,
    fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
    n_steps: int = 50,
    range_factor: float = 2.0,
) -> ServiceResult:
    """Start a parameter scan job on the server (async).

    Launches the scan loop in a background thread and returns
    immediately with a ``job_id``. Poll ``fit.parameter_scan.result``
    for completion, call ``fit.parameter_scan.cancel`` to cancel.
    """
    fit, idx = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return service_error("fit not found", error_code=NOT_FOUND)
    model = getattr(fit, "model", None)
    if model is None:
        return service_error("fit has no model", error_code=INVALID_STATE)
    params = getattr(model, "parameters_all_dict", {}) or {}
    param = params.get(parameter_name)
    if param is None:
        return service_error(f"parameter '{parameter_name}' not found", error_code=NOT_FOUND)
    job = _JOBS.create_job(PARAMETER_SCAN_ACTION, {
        "parameter_name": parameter_name,
        "fit_uid": str(getattr(fit, "unique_identifier", "") or ""),
        "fit_index": idx,
    })
    job_id = job.job_id

    def _run() -> Optional[Dict[str, Any]]:
        value = getattr(param, "value", 0) or 0
        err = getattr(param, "error_estimate", None)
        half_range = (err * range_factor) if err else abs(value * 0.5)
        if half_range <= 0:
            half_range = 1.0
        lo = value - half_range
        hi = value + half_range
        import numpy as np
        values = np.linspace(lo, hi, int(n_steps))
        chi2s = []
        chi2rs = []
        n_total = len(values)

        try:
            for i, v in enumerate(values):
                if _JOBS.should_cancel(job_id):
                    return None
                param.value = float(v)
                model.update()
                chi2 = getattr(fit, "chi2", None)
                if chi2 is None:
                    chi2 = float("nan")
                chi2r = getattr(fit, "chi2r", None)
                if chi2r is None:
                    chi2r = float("nan")
                chi2s.append(float(chi2))
                chi2rs.append(float(chi2r))
                _JOBS.set_progress(job_id, int(100.0 * (i + 1) / n_total))
        finally:
            # The scan borrows the live parameter, so every exit owes the
            # starting point back -- a normal finish, a cancellation, and a
            # probe value outside the model's domain that made ``update_model``
            # raise alike. The assignment comes before the re-evaluation so the
            # parameter is restored even if evaluating there raises again.
            param.value = value
            model.update()

        _JOBS.set_progress(job_id, 100)
        return {
            "values": [float(v) for v in values],
            "chi2": chi2s,
            "chi2r": chi2rs,
        }

    _JOBS.start_threaded(job, _run)
    _JOBS.cleanup()
    return {"ok": True, "job_id": job_id}


def fit_parameter_scan_cancel(
    state: SessionState,
    job_id: str,
) -> ServiceResult:
    """Cancel a running parameter scan.

    Sets the job's cancellation event, which the worker thread observes between
    scan steps.
    """
    job, error = _job_or_error(job_id, PARAMETER_SCAN_ACTION)
    if error is not None:
        return error
    _JOBS.cancel_job(job_id)
    return {"ok": True}


def fit_parameter_scan_result(
    state: SessionState,
    job_id: str,
) -> ServiceResult:
    """Get the result of a completed parameter scan."""
    job, error = _job_or_error(job_id, PARAMETER_SCAN_ACTION)
    if error is not None:
        return error
    scan = job.result if isinstance(job.result, dict) else {}
    return {
        "ok": True,
        "job_id": job_id,
        "status": job.status.value,
        "progress": job.progress,
        "values": scan.get("values", []),
        "chi2": scan.get("chi2", []),
        "chi2r": scan.get("chi2r", []),
        "error": job.error,
    }
