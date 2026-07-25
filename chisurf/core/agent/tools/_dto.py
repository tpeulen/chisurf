"""Compact, model-friendly summaries of ChiSurf objects.

Everything a tool returns is spent from the model's context window, so these
summaries stay deliberately small: names, indices, a few numbers, and no raw
curve arrays unless a tool was explicitly asked for them.
"""

from __future__ import annotations

import math
import pathlib
from typing import Any

from chisurf.server.services._stats import (
    _safe_n_free,
    _safe_n_points,
)


def chi2r(fit: Any) -> float | None:
    """Return a fit's reduced chi-square, computing it if necessary.

    ``Fit.chi2r`` is a live property: it evaluates the model, so it raises
    while a fit is half-configured (no data, empty fit range).  The agent
    wants the real number whenever one exists and ``None`` otherwise, which
    is what the cached-only helper in the RPC services cannot give.

    Parameters
    ----------
    fit : object
        Fit or fit group.

    Returns
    -------
    float or None
    """
    try:
        return _finite(fit.chi2r)
    except Exception:
        return None


def _finite(value: Any) -> float | None:
    """Return *value* as a JSON-safe float, or ``None`` when not finite."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: Any, digits: int = 6) -> float | None:
    """Return *value* rounded to *digits*, or ``None`` when not finite."""
    number = _finite(value)
    return None if number is None else round(number, digits)


def dataset_label(dataset: Any) -> tuple[str, str]:
    """Return a meaningful ``(name, filename)`` for a dataset or group.

    Some readers wrap their result in a group whose own ``name`` is the class
    name (``"ExperimentDataCurveGroup"``) and whose ``filename`` is unset,
    while the curve inside carries the real identity. A user asked to pick
    between two datasets both called "ExperimentDataCurveGroup" cannot, so the
    child's identity is used when the group has none of its own.

    Parameters
    ----------
    dataset : object
        Dataset or dataset group.

    Returns
    -------
    tuple of str
        The display name and the filename, either possibly empty.
    """

    def _text(value: Any) -> str:
        """Return a stripped string, treating a literal "None" as empty."""
        text = str(value or "").strip()
        return "" if text == "None" else text

    name = _text(getattr(dataset, "name", ""))
    filename = _text(getattr(dataset, "filename", ""))
    if name and name != type(dataset).__name__ and filename:
        return name, filename

    child = None
    try:
        for candidate in dataset:
            child = candidate
            break
    except TypeError:
        child = None
    if child is not None:
        child_name = _text(getattr(child, "name", ""))
        child_file = _text(getattr(child, "filename", ""))
        if not name or name == type(dataset).__name__:
            name = child_name or name
        filename = filename or child_file
    return name, filename


def dataset_summary(dataset: Any, index: int) -> dict[str, Any]:
    """Return a one-line summary of a loaded dataset.

    Parameters
    ----------
    dataset : object
        Dataset or dataset group.
    index : int
        Position in ``chisurf.imported_datasets``.

    Returns
    -------
    dict
    """
    name, filename = dataset_label(dataset)
    experiment = getattr(dataset, "experiment", None)
    summary: dict[str, Any] = {
        "index": index,
        "name": name,
        "type": type(dataset).__name__,
        "experiment": str(getattr(experiment, "name", "") or experiment or ""),
    }
    if filename:
        summary["filename"] = filename
        summary["file"] = pathlib.Path(filename).name
    y_values = getattr(dataset, "y", None)
    if y_values is not None:
        try:
            summary["n_points"] = int(len(y_values))
        except TypeError:
            pass
    return summary


def parameter_summary(name: str, parameter: Any) -> dict[str, Any]:
    """Return a summary of a single fitting parameter."""
    summary: dict[str, Any] = {
        "name": name,
        "value": _round(getattr(parameter, "value", None)),
        "fixed": bool(getattr(parameter, "fixed", False)),
    }
    if getattr(parameter, "bounds_on", False):
        bounds = getattr(parameter, "bounds", None)
        if bounds is not None:
            summary["bounds"] = [_round(bounds[0]), _round(bounds[1])]
    error = _round(getattr(parameter, "error_estimate", None))
    if error is not None:
        summary["error"] = error
    link = getattr(getattr(parameter, "link", None), "name", "")
    if link:
        summary["linked_to"] = str(link)
    return summary


def fit_parameters(fit: Any) -> list[dict[str, Any]]:
    """Return summaries of every parameter of a fit's model."""
    model = getattr(fit, "model", None)
    parameters = getattr(model, "parameters_all_dict", None) or {}
    return [parameter_summary(name, p) for name, p in parameters.items()]


def fit_summary(fit: Any, index: int, detailed: bool = False) -> dict[str, Any]:
    """Return a summary of a fit.

    Parameters
    ----------
    fit : object
        Fit or fit group.
    index : int
        Position in ``chisurf.fits``.
    detailed : bool, default False
        Include the full parameter list and the fit range.

    Returns
    -------
    dict
    """
    data = getattr(fit, "data", None)
    summary: dict[str, Any] = {
        "index": index,
        "name": str(getattr(fit, "name", "") or ""),
        "model": str(getattr(getattr(fit, "model", None), "name", "") or ""),
        "dataset": dataset_label(data)[0] if data is not None else "",
        "chi2r": _round(chi2r(fit), 4),
    }
    if detailed:
        summary["n_points"] = _safe_n_points(fit)
        summary["n_free_parameters"] = _safe_n_free(fit)
        try:
            summary["fit_range"] = [int(v) for v in fit.fit_range]
        except Exception:
            pass
        summary["parameters"] = fit_parameters(fit)
    return summary


def session_summary(datasets: list[Any], fits: list[Any]) -> dict[str, Any]:
    """Return a compact description of the whole ChiSurf session."""
    return {
        "n_datasets": len(datasets),
        "n_fits": len(fits),
        "datasets": [dataset_summary(d, i) for i, d in enumerate(datasets)],
        "fits": [fit_summary(f, i) for i, f in enumerate(fits)],
    }
