"""Agent tools for creating, configuring, running and reporting fits."""

from __future__ import annotations

import logging
from typing import Any

import chisurf as cs
from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.spec import SAFETY_READ, SAFETY_WRITE, ToolError, ToolRegistry
from chisurf.core.agent.tools._dto import chi2r, fit_summary, session_summary
from chisurf.core.agent.tools.decay import assess_fit

logger = logging.getLogger(__name__)

registry = ToolRegistry()


def refresh_gui() -> None:
    """Ask a running ChiSurf main window to refresh, if there is one."""
    gui = getattr(cs, "cs", None)
    if gui is None:
        return
    # Through the presentation seam, not `import chisurf.gui`: the model must
    # not need a widget toolkit to be importable. Headless there is no
    # presenter and this is a no-op on a `gui` that is already None.
        from chisurf.core.runtime import presentation

    presentation.notify(gui.update)


def apply_auto_fit_range(fit: Any) -> list[int] | None:
    """Set a fit's range from its reader's ``autofitrange``, if available.

    A freshly created fit has the range ``(0, 0)``, which makes the optimiser
    fail with "N must not exceed M".  Every creation path therefore runs this.

    Parameters
    ----------
    fit : object
        Fit whose range should be initialised.

    Returns
    -------
    list of int or None
        The applied ``[start, stop]``, or ``None`` when no range could be
        determined.
    """
    data = getattr(fit, "data", None)
    reader = getattr(data, "data_reader", None)
    if data is None or reader is None or not hasattr(reader, "autofitrange"):
        return None
    try:
        start, stop = reader.autofitrange(data)
        fit.fit_range = (int(start), int(stop))
        return [int(start), int(stop)]
    except Exception:
        logger.debug("autofitrange failed", exc_info=True)
        return None


def initialise_fit(fit: Any) -> list[int] | None:
    """Make a freshly created fit runnable and inspectable.

    Two things are missing right after creation: the fit range is ``(0, 0)``
    (the optimiser then fails with "N must not exceed M"), and the model's
    parameter list is empty until ``update()`` has run ``find_parameters``.
    Both are fixed here so ``get_fit`` and ``run_fit`` work on the fit the
    moment ``create_fit`` returns.

    Parameters
    ----------
    fit : object
        The newly created fit.

    Returns
    -------
    list of int or None
        The applied fit range, if one could be derived.
    """
    fit_range = apply_auto_fit_range(fit)
    try:
        fit.update()
    except Exception:
        logger.debug("fit.update after creation failed", exc_info=True)
    return fit_range


def _create_grouped_fit(indices: list[int], model_name: str) -> None:
    """Create a single fit over several datasets (a global fit).

    ``fit.add`` deliberately creates one fit per dataset when given several
    indices, so a genuine multi-dataset fit goes through the fit service,
    which builds one :class:`FitGroup` over all of them.

    Parameters
    ----------
    indices : list of int
        Dataset indices to combine.
    model_name : str
        Name of the model class.

    Raises
    ------
    ToolError
        When the service refuses to build the fit.
    """
    from chisurf.server.services.fits import fit_create
    from chisurf.server.session import SessionState

    state = SessionState(datasets=cs.imported_datasets, fits=cs.fits)
    result = fit_create(state, dataset_indices=list(indices), model_name=str(model_name))
    if not result.get("ok"):
        raise ToolError(str(result.get("error", "grouped fit could not be created")))


def _model_names() -> dict[str, list[str]]:
    """Return ``{experiment_name: [model names]}`` for the registered experiments."""
    return {
        str(name): [str(model) for model in experiment.model_names]
        for name, experiment in cs.experiment.items()
    }


def resolve_model_name(requested: str) -> str:
    """Return the registered model name matching *requested*.

    Model names are display strings, and some carry stray whitespace or
    capitalisation a user would never reproduce -- the daily-driver lifetime
    model is registered as ``"Lifetime "``, trailing space included. Rejecting
    ``"Lifetime"`` for that reason is a spelling test, not a safety check, so
    the match ignores case and surrounding space and falls back to a unique
    prefix.

    Parameters
    ----------
    requested : str
        The name asked for.

    Returns
    -------
    str
        The exact registered name to use.

    Raises
    ------
    ToolError
        When nothing matches, or when the name is ambiguous.
    """
    known = _model_names()
    everything = [name for names in known.values() for name in names]
    wanted = str(requested).strip().lower()

    exact = [name for name in everything if name == requested]
    if exact:
        return exact[0]
    relaxed = [name for name in everything if name.strip().lower() == wanted]
    if len(set(relaxed)) == 1:
        return relaxed[0]
    prefixed = [name for name in everything if name.strip().lower().startswith(wanted)]
    if len(set(prefixed)) == 1:
        return prefixed[0]
    if prefixed:
        raise ToolError(
            f"model name {requested!r} is ambiguous — it matches "
            f"{sorted(set(prefixed))}. Use the full name."
        )
    raise ToolError(f"unknown model {requested!r}. Available models per experiment: {known}")


@registry.add(
    name="describe_session",
    description=(
        "Describe the current ChiSurf session: which datasets are loaded and "
        "which fits exist, with their indices, models and reduced chi2.\n"
        "Call this first when you do not know the state of the session."
    ),
    parameters={"type": "object", "properties": {}},
    safety=SAFETY_READ,
)
def describe_session(context: AgentContext) -> dict[str, Any]:
    """Summarise datasets and fits in the session."""
    summary = session_summary(context.datasets, context.fits)
    summary["ok"] = True
    summary["working_directory"] = context.working_directory
    return summary


@registry.add(
    name="list_fits",
    description="List the fits in the session with their indices, models and reduced chi2.",
    parameters={"type": "object", "properties": {}},
    safety=SAFETY_READ,
)
def list_fits(context: AgentContext) -> dict[str, Any]:
    """Return every fit in the session."""
    fits = context.fits
    return {
        "ok": True,
        "n_fits": len(fits),
        "fits": [fit_summary(f, i) for i, f in enumerate(fits)],
    }


@registry.add(
    name="get_fit",
    description=(
        "Show one fit in detail: its model, its fit range, its reduced chi2 "
        "and every model parameter with value, fixed flag, bounds and "
        "uncertainty.\n"
        "Use this before changing parameters so you use their exact names."
    ),
    parameters={
        "type": "object",
        "properties": {
            "fit": {
                "type": ["integer", "string"],
                "description": "Fit index or name. Omit when there is only one fit.",
            }
        },
    },
    safety=SAFETY_READ,
)
def get_fit(context: AgentContext, fit: Any = None) -> dict[str, Any]:
    """Return the full description of a single fit."""
    obj, index = context.resolve_fit(fit)
    summary = fit_summary(obj, index, detailed=True)
    summary["ok"] = True
    return summary


@registry.add(
    name="create_fit",
    description=(
        "Create a fit for one or more datasets with a named model.\n"
        "This only sets the fit up with starting values — it does NOT "
        "optimise anything. Call run_fit afterwards; that is what produces "
        "the reduced chi2 you report to the user.\n"
        "By default one fit is created per dataset — that is what 'fit every "
        "file in the folder' means. The fit range is initialised "
        "automatically, so the fit is immediately runnable.\n"
        "The model name must be one of the names returned by "
        "list_experiments for the dataset's experiment type."
    ),
    parameters={
        "type": "object",
        "properties": {
            "model_name": {
                "type": "string",
                "description": "Exact model name, e.g. 'Lifetime' or 'Lifetime mixer'.",
            },
            "datasets": {
                "type": "array",
                "items": {"type": ["integer", "string"]},
                "description": ("Dataset indices or names. Omit to use every loaded dataset."),
            },
            "grouped": {
                "type": "boolean",
                "description": (
                    "Put all datasets into a single (global) fit instead of one "
                    "fit per dataset. Default false."
                ),
            },
        },
        "required": ["model_name"],
    },
    safety=SAFETY_WRITE,
)
def create_fit(
    context: AgentContext,
    model_name: str,
    datasets: Any = None,
    grouped: bool = False,
) -> dict[str, Any]:
    """Create one or more fits and initialise their fit ranges."""
    context.ensure_experiments()
    indices = context.resolve_datasets(datasets)
    if not indices:
        raise ToolError("no datasets are loaded — call load_data first")

    resolved_name = resolve_model_name(model_name)

    groups = [indices] if grouped else [[index] for index in indices]
    created: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for group in groups:
        before = len(context.fits)
        try:
            if grouped and len(group) > 1:
                _create_grouped_fit(group, resolved_name)
            else:
                cs.core.actions.dispatch(
                    name="fit.add",
                    payload={"dataset_indices": list(group), "model_name": resolved_name},
                )
        except Exception as error:
            failures.append({"datasets": group, "error": f"{type(error).__name__}: {error}"})
            continue
        fits = context.fits
        if len(fits) <= before:
            failures.append({"datasets": group, "error": "fit was not created"})
            continue
        for index in range(before, len(fits)):
            fit_range = initialise_fit(fits[index])
            summary = fit_summary(fits[index], index)
            # A created fit is not a fitted fit.  Reporting chi2r here invites
            # the model to present starting values as results, so the number
            # is withheld until run_fit has produced one.
            summary.pop("chi2r", None)
            summary["optimised"] = False
            if fit_range is not None:
                summary["fit_range"] = fit_range
            created.append(summary)

    refresh_gui()
    if not created:
        raise ToolError(
            "no fit could be created: " + "; ".join(str(f["error"]) for f in failures[:5])
        )
    result: dict[str, Any] = {
        "ok": True,
        "n_created": len(created),
        "model": resolved_name,
        "fits": created,
        "fit_indices": [entry["index"] for entry in created],
        "next_step": (
            "These fits hold starting values only. Call run_fit to optimise "
            "them; its result carries the reduced chi2 you should report."
        ),
    }
    if failures:
        result["failures"] = failures
    return result


@registry.add(
    name="run_fit",
    description=(
        "Run the optimiser on one fit, several fits, or all of them.\n"
        "Returns the reduced chi2 before and after, so you can tell whether "
        "the fit improved. A reduced chi2 near 1 is a good fit; much larger "
        "means the model does not describe the data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "fit": {
                "type": ["integer", "string"],
                "description": "Fit index or name. Omit to run every fit.",
            },
            "fits": {
                "type": "array",
                "items": {"type": ["integer", "string"]},
                "description": "Several fit indices or names.",
            },
        },
    },
    safety=SAFETY_WRITE,
)
def run_fit(
    context: AgentContext,
    fit: Any = None,
    fits: Any = None,
) -> dict[str, Any]:
    """Run one or more fits and report chi2r before/after."""
    all_fits = context.fits
    if not all_fits:
        raise ToolError("there are no fits to run — create one with create_fit")

    if fits:
        targets = [context.resolve_fit(reference)[1] for reference in fits]
    elif fit is not None:
        targets = [context.resolve_fit(fit)[1]]
    else:
        targets = list(range(len(all_fits)))

    results: list[dict[str, Any]] = []
    for index in targets:
        fit_object = all_fits[index]
        before = chi2r(fit_object)
        entry: dict[str, Any] = {
            "index": index,
            "name": str(getattr(fit_object, "name", "")),
            "chi2r_before": None if before is None else round(float(before), 4),
        }
        try:
            cs.core.actions.dispatch(name="fit.run", payload={"fit_index": int(index)})
            after = chi2r(fit_object)
            entry["chi2r"] = None if after is None else round(float(after), 4)
            entry["ok"] = True
            # A bare number does not tell a model that its work is unfinished.
            # For a grouped fit this judges every curve, not just the selected
            # one — a run over sixteen curves must not report one chi2r.
            entry["assessment"] = assess_fit(fit_object)
        except Exception as error:
            entry["ok"] = False
            entry["error"] = f"{type(error).__name__}: {error}"
            logger.debug("run_fit failed for fit %s", index, exc_info=True)
        results.append(entry)

    refresh_gui()
    succeeded = [entry for entry in results if entry.get("ok")]
    if not succeeded:
        raise ToolError(
            "every fit run failed: " + "; ".join(str(entry.get("error")) for entry in results[:5])
        )
    result: dict[str, Any] = {"ok": True, "n_run": len(succeeded), "results": results}
    poor = [
        entry["index"]
        for entry in succeeded
        if entry.get("assessment", {}).get("quality") == "poor"
    ]
    if poor:
        result["next_step"] = (
            f"Fits {poor} did not converge to an acceptable reduced chi2. "
            f"Follow the 'next_step' in each assessment before reporting these "
            f"numbers as a result."
        )
    return result


@registry.add(
    name="set_parameter",
    description=(
        "Change a model parameter of a fit: its value, whether it is fixed, "
        "and/or its bounds.\n"
        "Use get_fit first to see the exact parameter names. Fixing a "
        "parameter removes it from the optimisation; bounds keep it in a "
        "physically sensible range."
    ),
    parameters={
        "type": "object",
        "properties": {
            "parameter": {"type": "string", "description": "Exact parameter name."},
            "fit": {
                "type": ["integer", "string"],
                "description": "Fit index or name. Omit when there is only one fit.",
            },
            "value": {"type": "number", "description": "New value."},
            "fixed": {
                "type": "boolean",
                "description": "Fix (true) or release (false) the parameter.",
            },
            "bounds": {
                "type": "array",
                "items": {"type": ["number", "null"]},
                "description": "Two-element [lower, upper]; enables bounds for the parameter.",
            },
            "all_fits": {
                "type": "boolean",
                "description": "Apply the same change to every fit that has this parameter. Default false.",
            },
        },
        "required": ["parameter"],
    },
    safety=SAFETY_WRITE,
)
def set_parameter(
    context: AgentContext,
    parameter: str,
    fit: Any = None,
    value: float | None = None,
    fixed: bool | None = None,
    bounds: list[float | None] | None = None,
    all_fits: bool = False,
) -> dict[str, Any]:
    """Set a parameter's value, fixed flag and/or bounds."""
    from chisurf.core.actions import record_action
    from chisurf.core.agent.tools._dto import parameter_summary

    if value is None and fixed is None and bounds is None:
        raise ToolError("nothing to change — pass at least one of 'value', 'fixed' or 'bounds'")

    if all_fits:
        targets = list(range(len(context.fits)))
    else:
        targets = [context.resolve_fit(fit)[1]]

    changed: list[dict[str, Any]] = []
    missing: list[int] = []
    for index in targets:
        fit_object = context.fits[index]
        parameters = getattr(getattr(fit_object, "model", None), "parameters_all_dict", None) or {}
        if parameter not in parameters:
            missing.append(index)
            continue
        if bounds is not None:
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                raise ToolError("'bounds' must be a two-element list [lower, upper]")
            fit_object.set_parameter_bounds(parameter, tuple(bounds))
            fit_object.set_parameter_bounds_on(parameter, True)
        if value is not None:
            fit_object.set_parameter_value(parameter, float(value))
        if fixed is not None:
            fit_object.set_parameter_fixed(parameter, bool(fixed))
        changed.append({"fit": index, **parameter_summary(parameter, parameters[parameter])})

    if not changed:
        available = sorted(
            getattr(getattr(context.fits[targets[0]], "model", None), "parameters_all_dict", {})
            or {}
        )
        raise ToolError(
            f"no fit has a parameter called {parameter!r}. "
            f"Parameters of fit {targets[0]}: {available}"
        )

    record_action(
        action_type="agent.parameter.set",
        summary=f"agent set {parameter}",
        payload={"parameter": parameter, "fits": [entry["fit"] for entry in changed]},
    )
    refresh_gui()
    result: dict[str, Any] = {"ok": True, "changed": changed}
    if missing:
        result["fits_without_parameter"] = missing
    return result


@registry.add(
    name="set_fit_range",
    description=(
        "Set the channel/point range that a fit is evaluated over, or reset "
        "it to the automatic range derived from the data.\n"
        "Use this to exclude a scattered-light peak or a noisy tail."
    ),
    parameters={
        "type": "object",
        "properties": {
            "fit": {
                "type": ["integer", "string"],
                "description": "Fit index or name. Omit when there is only one fit.",
            },
            "start": {"type": "integer", "description": "First channel of the fit range."},
            "stop": {"type": "integer", "description": "Last channel of the fit range."},
            "auto": {
                "type": "boolean",
                "description": "Use the reader's automatic range instead of start/stop.",
            },
        },
    },
    safety=SAFETY_WRITE,
)
def set_fit_range(
    context: AgentContext,
    fit: Any = None,
    start: int | None = None,
    stop: int | None = None,
    auto: bool = False,
) -> dict[str, Any]:
    """Set or auto-derive the fit range of a fit."""
    fit_object, index = context.resolve_fit(fit)
    if auto or (start is None and stop is None):
        applied = apply_auto_fit_range(fit_object)
        if applied is None:
            raise ToolError(
                f"fit {index} has no reader that can derive a range; "
                f"pass explicit start and stop values"
            )
    else:
        if start is None or stop is None:
            raise ToolError("pass both 'start' and 'stop', or set auto=true")
        fit_object.fit_range = (int(start), int(stop))
        applied = [int(start), int(stop)]
    try:
        fit_object.update()
    except Exception:
        logger.debug("fit.update after range change failed", exc_info=True)
    refresh_gui()
    return {"ok": True, "fit": index, "fit_range": applied}


@registry.add(
    name="save_project",
    description=(
        "Save the whole ChiSurf session (datasets, fits and parameters) to a "
        "project file so the user can reopen it later."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Target path for the project file (.cs.pto).",
            }
        },
        "required": ["path"],
    },
    safety=SAFETY_WRITE,
)
def save_project(context: AgentContext, path: str) -> dict[str, Any]:
    """Save the session to a ChiSurf project archive.

    ``fit.save`` sounds like the right action and is not: it is a per-fit
    numeric export that needs an open fit window and does nothing at all
    head-lessly. The project archive is ``project.save``, which works without
    a GUI.
    """
    target = context.resolve_path(path)
    if not str(target).lower().endswith(".cs.pto"):
        target = target.with_name(f"{target.name}.cs.pto")
    target.parent.mkdir(parents=True, exist_ok=True)

    cs.core.actions.dispatch(
        name="project.save",
        payload={"target_path": str(target), "project_name": target.stem},
    )
    if not target.is_file():
        # The macro derives its own file name from the project name when the
        # target names a directory; find what it actually wrote.
        candidates = sorted(
            target.parent.glob("*.cs.pto"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if not candidates:
            raise ToolError(f"the project was not written to {target}")
        target = candidates[0]

    return {
        "ok": True,
        "path": str(target),
        "size_kb": round(target.stat().st_size / 1024.0, 1),
        "n_fits": len(context.fits),
        "n_datasets": len(context.datasets),
    }


@registry.add(
    name="export_fit_results",
    description=(
        "Write a table of the fitted parameters and reduced chi2 of every fit "
        "to a CSV file — the usual deliverable after a batch of fits."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Target CSV path."},
            "fits": {
                "type": "array",
                "items": {"type": ["integer", "string"]},
                "description": "Fits to include. Omit for all fits.",
            },
        },
        "required": ["path"],
    },
    safety=SAFETY_WRITE,
)
def export_fit_results(
    context: AgentContext,
    path: str,
    fits: Any = None,
) -> dict[str, Any]:
    """Export a per-fit parameter table as CSV."""
    import csv

    from chisurf.core.agent.tools._dto import fit_parameters

    all_fits = context.fits
    if not all_fits:
        raise ToolError("there are no fits to export")
    indices = (
        [context.resolve_fit(reference)[1] for reference in fits]
        if fits
        else list(range(len(all_fits)))
    )

    rows: list[dict[str, Any]] = []
    columns: list[str] = ["fit", "name", "dataset", "model", "chi2r"]
    for index in indices:
        fit_object = all_fits[index]
        reduced_chi2 = chi2r(fit_object)
        row: dict[str, Any] = {
            "fit": index,
            "name": str(getattr(fit_object, "name", "")),
            "dataset": str(getattr(getattr(fit_object, "data", None), "name", "")),
            "model": str(getattr(getattr(fit_object, "model", None), "name", "")),
            "chi2r": None if reduced_chi2 is None else round(float(reduced_chi2), 4),
        }
        for entry in fit_parameters(fit_object):
            row[entry["name"]] = entry["value"]
            if entry["name"] not in columns:
                columns.append(entry["name"])
        rows.append(row)

    target = context.resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return {
        "ok": True,
        "path": str(target),
        "n_rows": len(rows),
        "columns": columns,
    }
