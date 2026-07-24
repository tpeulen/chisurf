from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from chisurf.server.services import (
    ServiceResult,
    service_error,
    NOT_FOUND,
    OPERATION_FAILED,
    _resolve_fit,
)
from chisurf.server.session import SessionState


def _model_of(owner: Any) -> Any:
    """Return the parameter group to finalize/update for a resolved *owner*.

    A :class:`~chisurf.core.fitting.fit.Fit` exposes its group as ``owner.model``;
    a registered out-of-fit group (a :class:`~chisurf.core.models.model.Model` or
    other :class:`FittingParameterGroup`) *is* its own group and has no ``model``
    attribute. Returns ``None`` for a missing owner.

    Parameters
    ----------
    owner : object or None
        A fit, a model/group, or ``None``.
    """
    if owner is None:
        return None
    model = getattr(owner, "model", None)
    return model if model is not None else owner


def _finalize_owner(owner: Any) -> None:
    """Update and finalise the model/group of a resolved *owner*, best-effort.

    Works for both a fit (``owner.model``) and an out-of-fit group (``owner``
    itself). A missing owner (UUID path without ``owner_uid``) is a no-op.
    """
    model = _model_of(owner)
    if model is None:
        return
    if hasattr(model, "update_model"):
        model.update_model()
    if hasattr(model, "finalize"):
        model.finalize()


def _resolve_parameter(
    state: SessionState,
    parameter_name: Optional[str] = None,
    fit_index: int = 0,
    fit_uid: Optional[str] = None,
    local_idx: Optional[int] = None,
    *,
    parameter_uid: Optional[str] = None,
    owner_uid: Optional[str] = None,
    fit_error: str = "fit not found",
    access_error: Optional[str] = "cannot access model parameters",
    parameter_error: Optional[str] = None,
) -> tuple[Any, Any, Optional[ServiceResult]]:
    """Look up a parameter, addressed either by UUID or by fit + name.

    Returns ``(owner, parameter, None)`` or ``(owner_or_None, None, error)``. The
    first element is the *owner* to finalise after a mutation — a fit (fit-addressed
    path) or a model/group (UUID/owner-addressed path); pass it through
    :func:`_model_of` / :func:`_finalize_owner`.

    Resolution order:

    1. ``parameter_uid`` — resolve the parameter directly via
       :meth:`chisurf.core.base.Base.find_by_uuid`, independent of
       ``chisurf.fits``. This is what makes out-of-fit (plugin) parameters
       mutable and linkable through the same path as fit parameters. ``owner_uid``
       (when given) resolves the containing model/group for finalisation.
    2. ``owner_uid`` without ``parameter_uid`` — resolve the group by UUID, then
       look ``parameter_name`` up in its ``parameters_all_dict``.
    3. Otherwise — the legacy fit-addressed path.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    parameter_name : str, optional
        Parameter name (required for the fit/owner name-addressed paths).
    fit_index : int
        Fit index.
    fit_uid : str, optional
        Fit UID.
    local_idx : int, optional
        Local fit index when *fit* is a fit group.
    parameter_uid : str, optional
        Global UUID of the parameter (preferred; skips the fit lookup).
    owner_uid : str, optional
        Global UUID of the containing model/group.
    fit_error : str
        Error message when the fit/owner is not found.
    access_error : str or None
        Error message when parameters cannot be accessed.
    parameter_error : str or None
        Error message when the parameter is not found.

    """
    # 1. UUID-addressed parameter: resolve independently of chisurf.fits.
    if parameter_uid:
        from chisurf.core.base import Base

        p = Base.find_by_uuid(str(parameter_uid))
        if p is None:
            message = parameter_error or f"parameter uid '{parameter_uid}' not found"
            return None, None, service_error(message, error_code=NOT_FOUND)
        owner = Base.find_by_uuid(str(owner_uid)) if owner_uid else None
        return owner, p, None

    # 2. Owner group addressed by UUID, parameter by name.
    if owner_uid:
        from chisurf.core.base import Base

        owner = Base.find_by_uuid(str(owner_uid))
        if owner is None:
            return None, None, service_error(fit_error, error_code=NOT_FOUND)
        group = _model_of(owner)
        try:
            parameters = getattr(group, "parameters_all_dict", {}) or {}
        except Exception:
            if access_error is None:
                parameters = {}
            else:
                return owner, None, service_error(access_error, error_code=OPERATION_FAILED)
        parameter = parameters.get(parameter_name)
        if parameter is None:
            message = parameter_error or f"parameter '{parameter_name}' not found"
            return owner, None, service_error(message, error_code=NOT_FOUND)
        return owner, parameter, None

    # 3. Legacy fit-addressed path.
    fit, _ = _resolve_fit(state, fit_index, fit_uid)
    if fit is None:
        return None, None, service_error(fit_error, error_code=NOT_FOUND)
    if local_idx is not None:
        grouped_fits = getattr(fit, "grouped_fits", None)
        if not grouped_fits or not 0 <= local_idx < len(grouped_fits):
            return fit, None, service_error("local fit not found", error_code=NOT_FOUND)
        fit = grouped_fits[local_idx]
    try:
        parameters = getattr(fit.model, "parameters_all_dict", {}) or {}
    except Exception:
        if access_error is None:
            parameters = {}
        else:
            return fit, None, service_error(access_error, error_code=OPERATION_FAILED)
    parameter = parameters.get(parameter_name)
    if parameter is None:
        message = parameter_error or f"parameter '{parameter_name}' not found"
        return fit, None, service_error(message, error_code=NOT_FOUND)
    return fit, parameter, None


def _parameter_payload(parameter_name: str, parameter: Any) -> Dict[str, Any]:
    """Build a serialisable dict from a parameter object.

    Parameters
    ----------
    parameter_name : str
        Display name for the parameter.
    parameter : object
        Parameter instance.

    """
    return {
        "name": parameter_name,
        "value": getattr(parameter, "value", None),
        "fixed": bool(getattr(parameter, "fixed", False)),
        "bounds": getattr(parameter, "bounds", None),
        "bounds_on": bool(getattr(parameter, "bounds_on", False)),
        "error_estimate": getattr(parameter, "error_estimate", None),
        "linked_to": str(getattr(getattr(parameter, "link", None), "name", "") or ""),
    }


def get_parameter(
    state: SessionState,
    parameter_name: Optional[str] = None,
    fit_index: int = 0,
    fit_uid: Optional[str] = None,
    parameter_uid: Optional[str] = None,
    owner_uid: Optional[str] = None,
) -> ServiceResult:
    """Return the current state of a single parameter.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    parameter_name : str, optional
        Parameter name (used for the fit/owner name-addressed paths).
    fit_index : int
        Fit index.
    fit_uid : str, optional
        Fit UID.
    parameter_uid : str, optional
        Global UUID of the parameter (preferred; works for out-of-fit params).
    owner_uid : str, optional
        Global UUID of the containing model/group.

    """
    _, p, error = _resolve_parameter(
        state,
        parameter_name,
        fit_index,
        fit_uid,
        parameter_uid=parameter_uid,
        owner_uid=owner_uid,
        access_error=None,
    )
    if error is not None:
        return error
    return {
        "ok": True,
        "parameter": _parameter_payload(parameter_name or getattr(p, "name", ""), p),
    }


def set_parameter_value(
    state: SessionState,
    parameter_name: Optional[str] = None,
    value: float = 0.0,
    fit_index: int = 0,
    fit_uid: Optional[str] = None,
    local_idx: Optional[int] = None,
    parameter_uid: Optional[str] = None,
    owner_uid: Optional[str] = None,
) -> ServiceResult:
    """Set the numeric value of a parameter and update the model.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    parameter_name : str, optional
        Parameter name (used for the fit/owner name-addressed paths).
    value : float
        New value.
    fit_index : int
        Fit index.
    fit_uid : str, optional
        Fit UID.
    local_idx : int, optional
        Local fit index when the selected fit is a fit group.
    parameter_uid : str, optional
        Global UUID of the parameter (preferred; works for out-of-fit params).
    owner_uid : str, optional
        Global UUID of the containing model/group (finalisation target).

    """
    owner, p, error = _resolve_parameter(
        state, parameter_name, fit_index, fit_uid, local_idx,
        parameter_uid=parameter_uid, owner_uid=owner_uid,
    )
    if error is not None:
        return error
    try:
        p.value = float(value)
        _finalize_owner(owner)
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def set_parameter_fixed(
    state: SessionState,
    parameter_name: Optional[str] = None,
    fixed: bool = False,
    fit_index: int = 0,
    fit_uid: Optional[str] = None,
    local_idx: Optional[int] = None,
    parameter_uid: Optional[str] = None,
    owner_uid: Optional[str] = None,
) -> ServiceResult:
    """Fix or free a parameter and finalise the model.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    parameter_name : str, optional
        Parameter name (used for the fit/owner name-addressed paths).
    fixed : bool
        ``True`` to fix, ``False`` to free.
    fit_index : int
        Fit index.
    fit_uid : str, optional
        Fit UID.
    local_idx : int, optional
        Local fit index when the selected fit is a fit group.
    parameter_uid : str, optional
        Global UUID of the parameter (preferred; works for out-of-fit params).
    owner_uid : str, optional
        Global UUID of the containing model/group (finalisation target).

    """
    owner, p, error = _resolve_parameter(
        state, parameter_name, fit_index, fit_uid, local_idx,
        parameter_uid=parameter_uid, owner_uid=owner_uid,
    )
    if error is not None:
        return error
    try:
        p.fixed = bool(fixed)
        _finalize_owner(owner)
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def set_parameter_bounds(
    state: SessionState,
    parameter_name: Optional[str] = None,
    bounds: Tuple[float, float] = (0.0, 0.0),
    fit_index: int = 0,
    fit_uid: Optional[str] = None,
    local_idx: Optional[int] = None,
    parameter_uid: Optional[str] = None,
    owner_uid: Optional[str] = None,
) -> ServiceResult:
    """Set the (min, max) bounds for a parameter.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    parameter_name : str, optional
        Parameter name (used for the fit/owner name-addressed paths).
    bounds : tuple of float
        ``(min, max)`` bound values.
    fit_index : int
        Fit index.
    fit_uid : str, optional
        Fit UID.
    local_idx : int, optional
        Local fit index when the selected fit is a fit group.
    parameter_uid : str, optional
        Global UUID of the parameter (preferred; works for out-of-fit params).
    owner_uid : str, optional
        Global UUID of the containing model/group (finalisation target).

    """
    owner, p, error = _resolve_parameter(
        state, parameter_name, fit_index, fit_uid, local_idx,
        parameter_uid=parameter_uid, owner_uid=owner_uid,
    )
    if error is not None:
        return error
    try:
        p.bounds = tuple(float(v) for v in bounds)
        _finalize_owner(owner)
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def set_parameter_bounds_on(
    state: SessionState,
    parameter_name: Optional[str] = None,
    bounds_on: bool = False,
    fit_index: int = 0,
    fit_uid: Optional[str] = None,
    local_idx: Optional[int] = None,
    parameter_uid: Optional[str] = None,
    owner_uid: Optional[str] = None,
) -> ServiceResult:
    """Enable or disable bound constraints for a parameter.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    parameter_name : str, optional
        Parameter name (used for the fit/owner name-addressed paths).
    bounds_on : bool
        ``True`` to enable bounds, ``False`` to disable.
    fit_index : int
        Fit index.
    fit_uid : str, optional
        Fit UID.
    local_idx : int, optional
        Local fit index when the selected fit is a fit group.
    parameter_uid : str, optional
        Global UUID of the parameter (preferred; works for out-of-fit params).
    owner_uid : str, optional
        Global UUID of the containing model/group (finalisation target).

    """
    _, p, error = _resolve_parameter(
        state, parameter_name, fit_index, fit_uid, local_idx,
        parameter_uid=parameter_uid, owner_uid=owner_uid,
    )
    if error is not None:
        return error
    try:
        p.bounds_on = bool(bounds_on)
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def set_parameter_prior(
    state: SessionState,
    parameter_name: Optional[str] = None,
    prior: Optional[dict] = None,
    fit_index: int = 0,
    fit_uid: Optional[str] = None,
    local_idx: Optional[int] = None,
    parameter_uid: Optional[str] = None,
    owner_uid: Optional[str] = None,
) -> ServiceResult:
    """Set or clear a parameter's prior from its serialisable state dict.

    Bounds are the uniform-prior special case, so a ``{"kind": "uniform", ..}``
    spec is folded onto the parameter bounds by the core ``Parameter.prior``
    setter; smooth priors (Gaussian, log-normal, ...) are stored on the port and
    contribute to the maximum-a-posteriori objective. Passing ``None`` clears the
    prior.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    parameter_name : str, optional
        Parameter name (used for the fit/owner name-addressed paths).
    prior : dict, optional
        Prior state dict (``{"kind": ..., <params>}``) or ``None`` to clear it.
    fit_index : int
        Fit index.
    fit_uid : str, optional
        Fit UID.
    local_idx : int, optional
        Local fit index when the selected fit is a fit group.
    parameter_uid : str, optional
        Global UUID of the parameter (preferred; works for out-of-fit params).
    owner_uid : str, optional
        Global UUID of the containing model/group (finalisation target).
    """
    owner, p, error = _resolve_parameter(
        state, parameter_name, fit_index, fit_uid, local_idx,
        parameter_uid=parameter_uid, owner_uid=owner_uid,
    )
    if error is not None:
        return error
    try:
        p.prior = prior if isinstance(prior, dict) else None
        _finalize_owner(owner)
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def parameter_link(
    state: SessionState,
    parameter_name: Optional[str] = None,
    target_parameter_name: Optional[str] = None,
    fit_index: int = 0,
    target_fit_index: Optional[int] = None,
    fit_uid: Optional[str] = None,
    target_fit_uid: Optional[str] = None,
    local_idx: Optional[int] = None,
    target_local_idx: Optional[int] = None,
    parameter_uid: Optional[str] = None,
    owner_uid: Optional[str] = None,
    target_parameter_uid: Optional[str] = None,
    target_owner_uid: Optional[str] = None,
) -> ServiceResult:
    """Link a parameter to another parameter (same or different fit).

    Parameters may be addressed by UUID (``parameter_uid`` / ``target_parameter_uid``)
    so an out-of-fit (plugin) parameter joins the same link graph as fit
    parameters, or by fit + name for the legacy path.

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    parameter_name : str, optional
        Source parameter name.
    target_parameter_name : str, optional
        Target parameter name to link to.
    fit_index : int
        Source fit index.
    target_fit_index : int, optional
        Target fit index.
    fit_uid : str, optional
        Source fit UID.
    target_fit_uid : str, optional
        Target fit UID.
    local_idx : int, optional
        Source local fit index when the source fit is a fit group.
    target_local_idx : int, optional
        Target local fit index when the target fit is a fit group.
    parameter_uid : str, optional
        Global UUID of the source parameter (preferred).
    owner_uid : str, optional
        Global UUID of the source model/group (finalisation target).
    target_parameter_uid : str, optional
        Global UUID of the target parameter to link to (preferred).
    target_owner_uid : str, optional
        Global UUID of the target model/group (used with ``target_parameter_name``).

    """
    owner, p, error = _resolve_parameter(
        state,
        parameter_name,
        fit_index,
        fit_uid,
        local_idx,
        parameter_uid=parameter_uid,
        owner_uid=owner_uid,
        fit_error="source fit not found",
        access_error="cannot access source parameters",
        parameter_error=f"source parameter '{parameter_name}' not found",
    )
    if error is not None:
        return error

    link_to = None
    # Target addressed by UUID takes precedence — this is what lets a parameter
    # (in a fit or an out-of-fit plugin group) link to any other parameter.
    if target_parameter_uid:
        from chisurf.core.base import Base

        link_to = Base.find_by_uuid(str(target_parameter_uid))
        if link_to is None:
            return service_error(
                f"target parameter uid '{target_parameter_uid}' not found",
                error_code=NOT_FOUND,
            )
    elif target_owner_uid and target_parameter_name:
        from chisurf.core.base import Base

        target_owner = Base.find_by_uuid(str(target_owner_uid))
        if target_owner is None:
            return service_error("target group not found", error_code=NOT_FOUND)
        tdict = getattr(_model_of(target_owner), "parameters_all_dict", {}) or {}
        link_to = tdict.get(target_parameter_name)
        if link_to is None:
            return service_error(
                f"target parameter '{target_parameter_name}' not found", error_code=NOT_FOUND
            )
    elif target_parameter_name:
        target_fit = owner
        if target_fit_index is not None or target_fit_uid is not None:
            target_fit, _ = _resolve_fit(state, target_fit_index or 0, target_fit_uid)
            if target_fit is None:
                return service_error("target fit not found", error_code=NOT_FOUND)
        elif target_local_idx is not None:
            target_fit, _ = _resolve_fit(state, fit_index, fit_uid)
            if target_fit is None:
                return service_error("target fit not found", error_code=NOT_FOUND)
        if target_local_idx is not None:
            grouped_fits = getattr(target_fit, "grouped_fits", None)
            if not grouped_fits or not 0 <= target_local_idx < len(grouped_fits):
                return service_error("target local fit not found", error_code=NOT_FOUND)
            target_fit = grouped_fits[target_local_idx]
        try:
            tdict = getattr(_model_of(target_fit), "parameters_all_dict", {}) or {}
        except Exception:
            return service_error("cannot access target parameters", error_code=OPERATION_FAILED)
        link_to = tdict.get(target_parameter_name)
        if link_to is None:
            return service_error(f"target parameter '{target_parameter_name}' not found", error_code=NOT_FOUND)

    try:
        p.link = link_to
        _finalize_owner(owner)
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)


def parameter_unlink(
    state: SessionState,
    parameter_name: Optional[str] = None,
    fit_index: int = 0,
    fit_uid: Optional[str] = None,
    local_idx: Optional[int] = None,
    parameter_uid: Optional[str] = None,
    owner_uid: Optional[str] = None,
) -> ServiceResult:
    """Remove a parameter's link (make it independent).

    Parameters
    ----------
    state : SessionState
        Server-side session state.
    parameter_name : str, optional
        Parameter name (used for the fit/owner name-addressed paths).
    fit_index : int
        Fit index.
    fit_uid : str, optional
        Fit UID.
    local_idx : int, optional
        Local fit index when the selected fit is a fit group.
    parameter_uid : str, optional
        Global UUID of the parameter (preferred; works for out-of-fit params).
    owner_uid : str, optional
        Global UUID of the containing model/group (finalisation target).

    """
    owner, p, error = _resolve_parameter(
        state, parameter_name, fit_index, fit_uid, local_idx,
        parameter_uid=parameter_uid, owner_uid=owner_uid,
    )
    if error is not None:
        return error
    try:
        p.link = None
        _finalize_owner(owner)
        return {"ok": True}
    except Exception as e:
        return service_error(str(e), error_code=OPERATION_FAILED, exception=e)
