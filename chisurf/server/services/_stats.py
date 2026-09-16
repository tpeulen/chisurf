from __future__ import annotations

from typing import Any, Dict, List, Optional


def _recorded_float(fit: Any, name: str) -> Optional[float]:
    """Return what a run recorded under *name*, without evaluating anything.

    Read straight from the instance dictionary: ``chi2`` and ``chi2r`` are
    properties that evaluate the model, and a listing must never do that.
    :meth:`chisurf.core.fitting.fit.Fit._record_achieved_chi2` is the one
    writer of these keys.
    """
    try:
        return float(fit.__dict__[name])
    except Exception:
        return None


def _safe_chi2(fit: Any, *, compute: bool = False) -> Optional[float]:
    """Return the chi-squared value of *fit*, or ``None``.

    Parameters
    ----------
    fit : object
        Fit instance.
    compute : bool, optional
        Evaluate the model when no run has recorded a value. Off by default,
        so that listing fits stays free of model evaluations.
    """
    recorded = _recorded_float(fit, "_last_chi2")
    if recorded is not None:
        return recorded
    if not compute:
        return None
    try:
        return float(fit.chi2)
    except Exception:
        return None


def _safe_chi2r(fit: Any, *, compute: bool = False) -> Optional[float]:
    """Return the reduced chi-squared value of *fit*, or ``None``.

    Parameters
    ----------
    fit : object
        Fit instance.
    compute : bool, optional
        See :func:`_safe_chi2`.
    """
    recorded = _recorded_float(fit, "_last_chi2r")
    if recorded is not None:
        return recorded
    if not compute:
        return None
    try:
        return float(fit.chi2r)
    except Exception:
        return None


def _safe_n_points(fit: Any) -> Optional[int]:
    """Return the number of fit points, or ``None`` on failure.

    Parameters
    ----------
    fit : object
        Fit instance.

    """
    try:
        model = getattr(fit, "model", None)
        if model is not None:
            return int(getattr(model, "n_points", 0))
    except Exception:
        pass
    return None


def _safe_n_free(fit: Any) -> Optional[int]:
    """Return the number of free (non-fixed) parameters, or ``None``.

    Parameters
    ----------
    fit : object
        Fit instance.

    """
    try:
        model = getattr(fit, "model", None)
        if model is not None:
            return int(getattr(model, "n_free", 0))
    except Exception:
        pass
    return None


def _group_names(model: Any) -> Dict[int, str]:
    """Map ``id(parameter)`` to the name of the sub-group that owns it.

    A model presents its parameters through nested
    :class:`~chisurf.core.fitting.parameter.FittingParameterGroup` instances
    (``convolve``, ``generic``, ``lifetimes``, …). The flat parameter list loses
    that structure, so it is carried alongside and the link menu rebuilds the
    per-group submenus from it.
    """
    names: Dict[int, str] = {}
    for group in getattr(model, "aggregated_parameters", None) or []:
        group_name = str(getattr(group, "name", "") or "")
        for p in getattr(group, "parameters_all", None) or []:
            names.setdefault(id(p), group_name)
    return names


def _param_entry(p: Any, fit_uid: str, group_name: str = "") -> Dict[str, Any]:
    """Serialise one parameter for a fit DTO."""
    return {
        "name": str(getattr(p, "name", "")),
        "uid": str(getattr(p, "unique_identifier", "") or ""),
        "group": group_name,
        "fit_uid": fit_uid,
        "value": getattr(p, "value", None),
        "fixed": bool(getattr(p, "fixed", False)),
        "bounds": getattr(p, "bounds", None),
        "bounds_on": bool(getattr(p, "bounds_on", False)),
        "is_linked": bool(getattr(p, "is_linked", False)),
        "linked_to": str(getattr(getattr(p, "link", None), "name", "") or ""),
        "error_estimate": getattr(p, "error_estimate", None),
    }


def _collect_param_list(fit: Any, fit_uid: str = "") -> List[Dict[str, Any]]:
    """Return parameters as an ordered list (for proxy ``parameters_all``).

    A failure is logged rather than swallowed: an empty list here reads as "this
    fit has no parameters" everywhere downstream — the link menu renders it as an
    empty submenu with nothing to click — and that is indistinguishable from a
    model that could not be read at all.
    """
    model = getattr(fit, "model", None)
    if model is None:
        return []
    try:
        plist = list(getattr(model, "parameters_all", None) or [])
        groups = _group_names(model)
        return [_param_entry(p, fit_uid, groups.get(id(p), "")) for p in plist]
    except Exception:
        import chisurf.logging

        chisurf.logging.exception(
            "could not read the parameters of fit '%s'", fit_uid or "?"
        )
        return []


def _collect_member_list(fit: Any) -> List[Dict[str, Any]]:
    """Return the member fits of a fit group, each with its own parameters.

    A :class:`~chisurf.core.fitting.fit.FitGroup` answers ``model`` with the
    *selected* member's model, so a DTO built from that alone can only ever
    describe one curve of a global fit. The members are carried separately so a
    caller can address a specific one by ``local_idx``.
    """
    grouped = getattr(fit, "grouped_fits", None)
    if not grouped:
        return []
    members: List[Dict[str, Any]] = []
    for idx, member in enumerate(grouped):
        member_uid = str(getattr(member, "unique_identifier", "") or "")
        members.append({
            "local_idx": idx,
            "uid": member_uid,
            "name": str(getattr(member, "name", "") or f"fit {idx}"),
            "parameters_all": _collect_param_list(member, fit_uid=member_uid),
        })
    return members


def _collect_fit_params(fit: Any) -> Dict[str, Dict[str, Any]]:
    """Return a dict of parameter-name → parameter properties.

    Parameters
    ----------
    fit : object
        Fit instance.

    """
    params = {}
    try:
        pdict = getattr(fit.model, "parameters_all_dict", {}) if hasattr(fit, "model") else {}
        for name, p in pdict.items():
            params[name] = {
                "value": getattr(p, "value", None),
                "fixed": bool(getattr(p, "fixed", False)),
                "bounds": getattr(p, "bounds", None),
                "bounds_on": bool(getattr(p, "bounds_on", False)),
                "linked_to": str(getattr(getattr(p, "link", None), "name", "") or ""),
                "error_estimate": getattr(p, "error_estimate", None),
            }
    except Exception:
        import chisurf.logging

        chisurf.logging.exception("could not read the parameters of a fit")
    return params
