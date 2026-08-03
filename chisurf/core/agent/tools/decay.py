"""Agent tools for the parts of a fit that decide whether it is meaningful.

For a time-resolved fluorescence decay these are not optional extras: a TCSPC
fit without an instrument response function is systematically wrong, and one
with too few lifetime components cannot describe the data no matter how well
it is optimised.  On the sample donor decay in ``test/data`` the reduced
chi-square goes 8.5 (no IRF) -> 12.8 (IRF, one lifetime) -> 1.37 (two) ->
1.03 (three).  A model that cannot reach for these knobs cannot produce a
publishable fit, so they are tools of their own.
"""

from __future__ import annotations

import logging
from typing import Any

import chisurf as cs
from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.spec import SAFETY_READ, SAFETY_WRITE, ToolError, ToolRegistry
from chisurf.core.agent.tools._dto import _round, chi2r, fit_members, member_summary

logger = logging.getLogger(__name__)

registry = ToolRegistry()

#: Substrings that mark a dataset as a likely instrument-response measurement.
IRF_NAME_HINTS = ("irf", "prompt", "lamp", "instrument")


def looks_like_irf(dataset: Any) -> bool:
    """Return whether a dataset's name suggests it is an IRF measurement.

    Parameters
    ----------
    dataset : object
        A loaded dataset.

    Returns
    -------
    bool
    """
    name = str(getattr(dataset, "name", "") or "").lower()
    return any(hint in name for hint in IRF_NAME_HINTS)


def component_groups(model: Any) -> dict[str, int]:
    """Return the model's component groups and their current sizes.

    A component group is an attribute that behaves like a list of repeated
    model components -- the lifetimes of a decay, the distance distributions
    of a FRET model -- i.e. it supports ``append``, ``pop`` and ``len``.

    Parameters
    ----------
    model : object
        The model of a fit.

    Returns
    -------
    dict
        ``{attribute name: number of components}``.
    """
    groups: dict[str, int] = {}
    seen: dict[int, str] = {}
    for name in dir(model):
        if name.startswith("_"):
            continue
        try:
            candidate = getattr(model, name)
        except Exception:
            continue
        if (
            callable(getattr(candidate, "append", None))
            and callable(getattr(candidate, "pop", None))
            and hasattr(candidate, "__len__")
            and not isinstance(candidate, (str, bytes, list, tuple, dict))
        ):
            try:
                size = int(len(candidate))
            except Exception:
                continue
            # A parameter group is reachable both as its attribute and under
            # its own ``name``, so one group would otherwise be reported twice
            # and look like an ambiguous choice to :func:`_default_group`.
            previous = seen.get(id(candidate))
            if previous is not None:
                if len(name) < len(previous):
                    del groups[previous]
                    seen[id(candidate)] = name
                    groups[name] = size
                continue
            seen[id(candidate)] = name
            groups[name] = size
    return groups


def _default_group(model: Any) -> str:
    """Return the component group to use when the caller names none.

    Raises
    ------
    ToolError
        When the model has no component group, or several with no obvious
        default.
    """
    groups = component_groups(model)
    if not groups:
        raise ToolError(
            f"model {getattr(model, 'name', type(model).__name__)!r} has no "
            f"components that can be added or removed"
        )
    if "lifetimes" in groups:
        return "lifetimes"
    if len(groups) == 1:
        return next(iter(groups))
    raise ToolError(
        f"this model has several component groups {sorted(groups)}; "
        f"say which one with the 'component' argument"
    )


def _only_decay_dataset(context: AgentContext) -> int:
    """Return the single dataset that is a decay rather than a reference.

    Raises
    ------
    ToolError
        When there is nothing to fit, or more than one candidate.
    """
    candidates = [
        index for index, dataset in enumerate(context.datasets) if not looks_like_irf(dataset)
    ]
    if not candidates:
        raise ToolError(
            "no decay is loaded to fit — call load_data first "
            "(every loaded dataset looks like an IRF reference)"
        )
    if len(candidates) > 1:
        listing = [
            {"index": index, "name": str(getattr(context.datasets[index], "name", ""))}
            for index in candidates
        ]
        raise ToolError(f"say which decay to fit with 'dataset'. Candidates: {listing}")
    return candidates[0]


def _default_decay_model(context: AgentContext) -> str:
    """Return the lifetime model name to use when the caller names none.

    Raises
    ------
    ToolError
        When no lifetime model is registered for the session.
    """
    import chisurf as cs

    context.ensure_experiments()
    for experiment in cs.experiment.values():
        for name in experiment.model_names:
            if str(name).strip().lower().startswith("lifetime"):
                return str(name)
    raise ToolError(
        "no lifetime model is registered in this session; "
        "call list_experiments and pass 'model' explicitly"
    )


def assess_fit(fit: Any) -> dict[str, Any]:
    """Judge a fit — or every curve of a grouped fit — and say what to do.

    A dataset that arrived as several curves in one file is fitted as a group
    with one member per curve, and judging only the selected member would pass
    a group in which most curves fit badly.

    Parameters
    ----------
    fit : object
        The fit to judge.

    Returns
    -------
    dict
        The verdict for the fit; for a group, the verdict of its worst member
        together with the per-member reduced chi-squares.
    """
    verdict = _assess_one(fit)
    members = fit_members(fit)
    if not members:
        return verdict

    verdict.update(member_summary(fit, detailed=True))
    spread = verdict.get("members_chi2r")
    entries = verdict.get("members") or []
    if not spread or not entries:
        return verdict

    # The group is only as good as its worst curve.
    worst_entry = max(entries, key=lambda entry: entry["chi2r"] or 0.0)
    worst_verdict = _assess_one(members[worst_entry["member"]])
    ranking = {"good": 0, "acceptable": 1, "poor": 2, "unknown": 3}
    if ranking.get(worst_verdict.get("quality"), 0) > ranking.get(verdict.get("quality"), 0):
        verdict["quality"] = worst_verdict["quality"]
        verdict["reason"] = (
            f"the {len(members)} curves in this dataset span reduced chi2 "
            f"{spread['min']} to {spread['max']}; the worst is not acceptable "
            f"({worst_verdict.get('reason', '')})"
        )
        if "next_step" in worst_verdict:
            verdict["next_step"] = worst_verdict["next_step"]
    return verdict


def _assess_one(fit: Any) -> dict[str, Any]:
    """Judge a single fit and say what to do about it.

    A number alone does not tell a model to keep working: on the sample decay
    a language model happily reported ``chi2r = 12.8`` as a result because
    nothing in the payload said otherwise.  Every tool that produces a fit
    result therefore carries this verdict, naming the single most likely fix.

    Parameters
    ----------
    fit : object
        The fit to judge.

    Returns
    -------
    dict
        ``quality`` (``good``/``acceptable``/``poor``/``unknown``),
        ``reason``, and ``next_step`` when something should be done.
    """
    reduced = chi2r(fit)
    if reduced is None:
        return {"quality": "unknown", "reason": "no reduced chi2 could be computed"}

    model = getattr(fit, "model", None)
    convolve = getattr(model, "convolve", None)
    has_irf = getattr(convolve, "_irf", None) is not None if convolve is not None else None
    groups = component_groups(model) if model is not None else {}
    n_components = groups.get("lifetimes") or (max(groups.values()) if groups else 0)

    try:
        durbin_watson = float(fit.durbin_watson)
    except Exception:
        durbin_watson = float("nan")

    verdict: dict[str, Any] = {"chi2r": _round(reduced, 4)}
    if durbin_watson == durbin_watson:  # not NaN
        verdict["durbin_watson"] = _round(durbin_watson, 3)

    if reduced > 2.0:
        verdict["quality"] = "poor"
        verdict["reason"] = (
            f"reduced chi2 is {reduced:.2f}, far above 1 — the model does not describe the data"
        )
        if convolve is not None and has_irf is False:
            verdict["next_step"] = (
                "No IRF is attached. Load the instrument-response file (its "
                "name usually contains 'irf') and attach it with set_irf, "
                "then run_fit again."
            )
        elif n_components and n_components < 4:
            # Not "a single exponential": this advice now also reaches models
            # whose components are diffusing species rather than decay terms.
            verdict["next_step"] = (
                f"The model has {n_components} component(s). Call "
                f"set_components with n={n_components + 1} and run_fit again — "
                f"one component rarely describes a real sample."
            )
        else:
            verdict["next_step"] = (
                "Check the fit range for scattered light at the start or an "
                "empty tail (set_fit_range), or try a different model."
            )
        return verdict

    if reduced > 1.3:
        verdict["quality"] = "acceptable"
        verdict["reason"] = f"reduced chi2 is {reduced:.2f}, a little above 1"
        if n_components and n_components < 4:
            verdict["next_step"] = (
                f"One more component (set_components n={n_components + 1}) may "
                f"improve it; keep it only if chi2 drops materially."
            )
        return verdict

    verdict["quality"] = "good"
    verdict["reason"] = f"reduced chi2 is {reduced:.3f}, consistent with the noise"
    if durbin_watson == durbin_watson and durbin_watson < 1.5:
        verdict["quality"] = "acceptable"
        verdict["reason"] += (
            f", but Durbin-Watson is {durbin_watson:.2f} — the residuals are "
            f"correlated, so something systematic remains"
        )
    return verdict


@registry.add(
    name="set_irf",
    description=(
        "Attach an instrument response function (IRF) to a time-resolved "
        "decay fit, or remove the one it has.\n"
        "A TCSPC decay fit without an IRF is systematically wrong — the "
        "measured decay is the true decay convolved with the instrument's "
        "response, and fitting it without deconvolution inflates the "
        "lifetimes and the reduced chi2. Always look for an IRF (its file "
        "name usually contains 'irf', 'prompt' or 'lamp') and attach it "
        "before you judge a decay fit."
    ),
    parameters={
        "type": "object",
        "properties": {
            "irf": {
                "type": ["integer", "string"],
                "description": "Dataset index or name of the IRF measurement.",
            },
            "fit": {
                "type": ["integer", "string"],
                "description": "Fit index or name. Omit when there is only one fit.",
            },
            "remove": {
                "type": "boolean",
                "description": "Detach the current IRF instead of attaching one.",
            },
        },
    },
    safety=SAFETY_WRITE,
)
def set_irf(
    context: AgentContext,
    irf: Any = None,
    fit: Any = None,
    remove: bool = False,
) -> dict[str, Any]:
    """Attach or detach the IRF of a decay fit."""
    fit_object, fit_index = context.resolve_fit(fit)
    model = getattr(fit_object, "model", None)
    if model is None or not hasattr(model, "convolve"):
        raise ToolError(
            f"fit {fit_index} uses model "
            f"{getattr(model, 'name', '?')!r}, which does not convolve with an "
            f"IRF — this tool only applies to time-resolved decay models"
        )

    before = chi2r(fit_object)
    if remove:
        cs.core.actions.dispatch(name="model.unload_irf", payload={"fit_index": fit_index})
        return {"ok": True, "fit": fit_index, "irf": None, "chi2r_before": _round(before, 4)}

    if irf is None:
        candidates = [
            {"index": index, "name": str(getattr(dataset, "name", ""))}
            for index, dataset in enumerate(context.datasets)
            if looks_like_irf(dataset)
        ]
        raise ToolError(
            "name the IRF dataset to attach. "
            + (
                f"These loaded datasets look like IRF measurements: {candidates}"
                if candidates
                else "No loaded dataset looks like an IRF — load the IRF file first."
            )
        )

    irf_object, irf_index = context.resolve_dataset(irf)
    if irf_index == context.resolve_fit(fit)[1] and irf_object is getattr(fit_object, "data", None):
        raise ToolError("the IRF cannot be the same dataset as the decay being fitted")

    cs.core.actions.dispatch(
        name="model.change_irf",
        payload={
            "irf_idx": int(irf_index),
            "irf_name": str(getattr(irf_object, "name", "")),
            "fit_index": int(fit_index),
        },
    )
    try:
        fit_object.update()
    except Exception:
        logger.debug("fit.update after IRF change failed", exc_info=True)

    attached = getattr(getattr(model, "convolve", None), "_irf", None)
    if attached is None:
        raise ToolError("the IRF could not be attached to this model")

    from chisurf.core.agent.tools.fitting import refresh_gui

    refresh_gui()
    return {
        "ok": True,
        "fit": fit_index,
        "irf": {"index": irf_index, "name": str(getattr(irf_object, "name", ""))},
        "chi2r_before": _round(before, 4),
        "next_step": "Run the fit again — the IRF changes the model, so the old result is stale.",
    }


@registry.add(
    name="set_components",
    description=(
        "Set how many components a model has — the number of exponential "
        "lifetimes in a decay, for example.\n"
        "One lifetime rarely describes a real fluorophore. If the reduced "
        "chi2 stays well above 1 after fitting with an IRF attached, add a "
        "component and refit; stop when chi2 stops improving materially, "
        "because extra components eventually just fit the noise."
    ),
    parameters={
        "type": "object",
        "properties": {
            "n": {"type": "integer", "description": "Desired number of components (>= 1)."},
            "fit": {
                "type": ["integer", "string"],
                "description": "Fit index or name. Omit when there is only one fit.",
            },
            "component": {
                "type": "string",
                "description": "Component group, e.g. 'lifetimes'. Default: the model's main one.",
            },
        },
        "required": ["n"],
    },
    safety=SAFETY_WRITE,
)
def set_components(
    context: AgentContext,
    n: int,
    fit: Any = None,
    component: str | None = None,
) -> dict[str, Any]:
    """Add or remove model components until the group holds *n* of them."""
    fit_object, fit_index = context.resolve_fit(fit)
    model = getattr(fit_object, "model", None)
    if model is None:
        raise ToolError(f"fit {fit_index} has no model")

    wanted = int(n)
    if wanted < 1:
        raise ToolError("a model needs at least one component")

    groups = component_groups(model)
    name = component or _default_group(model)
    if name not in groups:
        raise ToolError(
            f"model has no component group {name!r}; available groups and "
            f"their current sizes: {groups}"
        )

    current = groups[name]
    for _ in range(max(0, wanted - current)):
        cs.core.actions.dispatch(
            name="model.add_component",
            payload={"component_name": name, "fit_index": fit_index},
        )
    for _ in range(max(0, current - wanted)):
        cs.core.actions.dispatch(
            name="model.remove_component",
            payload={"component_name": name, "fit_index": fit_index},
        )

    try:
        fit_object.update()
    except Exception:
        logger.debug("fit.update after component change failed", exc_info=True)

    reached = component_groups(model).get(name, current)
    from chisurf.core.agent.tools.fitting import refresh_gui

    refresh_gui()
    result: dict[str, Any] = {
        "ok": True,
        "fit": fit_index,
        "component": name,
        "n_components": reached,
        "next_step": "Run the fit again — the model changed, so the old result is stale.",
    }
    if reached != wanted:
        result["warning"] = (
            f"asked for {wanted} but the model settled on {reached} "
            f"(a model keeps at least one component)"
        )
    return result


@registry.add(
    name="auto_fit_decay",
    description=(
        "Fit a fluorescence decay the way an expert would, in one call: "
        "attach the IRF, then add lifetime components one at a time, refitting "
        "each time, until the reduced chi2 stops improving materially.\n"
        "Prefer this over driving set_irf / set_components / run_fit yourself "
        "when the user just wants the decay fitted — it is the same protocol "
        "but takes one step instead of ten, and it returns the whole trace so "
        "you can see how chi2 improved with each component.\n"
        "If no fit exists yet, pass the decay as 'dataset' and one is created "
        "for you; you do not need to call create_fit first."
    ),
    parameters={
        "type": "object",
        "properties": {
            "fit": {
                "type": ["integer", "string"],
                "description": "Fit index or name. Omit when there is only one fit.",
            },
            "dataset": {
                "type": ["integer", "string"],
                "description": (
                    "Decay dataset to fit, when no fit exists yet. A fit is "
                    "created for it with 'model' below."
                ),
            },
            "model": {
                "type": "string",
                "description": (
                    "Model to create the fit with when 'dataset' is given. "
                    "Default: the lifetime model of that experiment."
                ),
            },
            "irf": {
                "type": ["integer", "string"],
                "description": (
                    "Dataset index or name of the IRF. Omit to auto-detect a "
                    "loaded dataset whose name marks it as an IRF."
                ),
            },
            "max_components": {
                "type": "integer",
                "description": "Most components to try. Default 4.",
            },
        },
    },
    safety=SAFETY_WRITE,
)
def auto_fit_decay(
    context: AgentContext,
    fit: Any = None,
    irf: Any = None,
    max_components: int = 4,
    dataset: Any = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Attach the IRF and grow the model until the fit stops improving."""
    from chisurf.core.agent.tools.fitting import create_fit, run_fit

    steps: list[dict[str, Any]] = []
    notes: list[str] = []

    if fit is None and (dataset is not None or not context.fits):
        # "Fit this decay" is one instruction, not two: creating the fit here
        # saves a round trip and a chance to pick the wrong model.
        if dataset is None:
            dataset = _only_decay_dataset(context)
        created = create_fit(
            context,
            model_name=model or _default_decay_model(context),
            datasets=[dataset],
        )
        fit = created["fit_indices"][0]
        notes.append(f"created fit {fit} with model {created['model']!r}")

    fit_object, fit_index = context.resolve_fit(fit)

    model = getattr(fit_object, "model", None)
    convolve = getattr(model, "convolve", None)
    if convolve is None:
        raise ToolError(
            f"fit {fit_index} does not use a convolution model — "
            f"auto_fit_decay only applies to time-resolved decays"
        )

    if irf is None and getattr(convolve, "_irf", None) is None:
        candidates = [
            index for index, dataset in enumerate(context.datasets) if looks_like_irf(dataset)
        ]
        if len(candidates) == 1:
            irf = candidates[0]
            notes.append(f"auto-detected dataset {irf} as the IRF")
        elif len(candidates) > 1:
            notes.append(
                f"several datasets look like IRFs {candidates}; none was "
                f"attached — say which one with the 'irf' argument"
            )
        else:
            notes.append("no IRF was attached; the lifetimes will be overestimated")

    if irf is not None:
        set_irf(context, irf=irf, fit=fit_index)

    best_chi2r: float | None = None
    accepted = 0
    for n in range(1, max(1, int(max_components)) + 1):
        set_components(context, n=n, fit=fit_index)
        run_fit(context, fit=fit_index)
        current = chi2r(fit_object)
        steps.append({"n_components": n, "chi2r": _round(current, 4)})
        if current is None:
            break
        if best_chi2r is None:
            best_chi2r, accepted = float(current), n
            continue
        # An extra component must earn its place: a few per cent of chi2 is
        # noise, and every component costs a degree of freedom.
        improvement = (best_chi2r - float(current)) / best_chi2r
        if improvement < 0.02:
            steps[-1]["rejected"] = f"improvement {improvement:.1%} is not material"
            break
        best_chi2r, accepted = float(current), n
        if best_chi2r < 1.05:
            notes.append("stopped early: the fit already matches the noise")
            break

    if accepted and component_groups(model).get("lifetimes", accepted) != accepted:
        set_components(context, n=accepted, fit=fit_index)
        run_fit(context, fit=fit_index)

    from chisurf.core.agent.tools._dto import fit_parameters

    return {
        "ok": True,
        "fit": fit_index,
        # ``create_fit`` reports ``fit_indices``; a caller that has learned
        # that shape reasonably expects it here too, and a script written
        # against the wrong one fails with "no fit was created".
        "fit_indices": [fit_index],
        "n_components": accepted,
        "trace": steps,
        "notes": notes,
        "assessment": assess_fit(fit_object),
        "parameters": fit_parameters(fit_object),
    }


@registry.add(
    name="fit_report",
    description=(
        "Report how good a fit is: reduced chi2, degrees of freedom, the "
        "Durbin-Watson statistic of the residuals, whether an IRF is "
        "attached, how many components the model has, and every fitted "
        "parameter with its uncertainty.\n"
        "Use this to decide what to do next. Reduced chi2 near 1 with "
        "Durbin-Watson near 2 means the fit is good. Durbin-Watson well "
        "below 2 means the residuals are correlated — the model is missing "
        "something (a component, the IRF, a shifted fit range) even if chi2 "
        "looks acceptable."
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
def fit_report(context: AgentContext, fit: Any = None) -> dict[str, Any]:
    """Return a quality report for one fit."""
    import numpy as np

    from chisurf.core.agent.tools._dto import fit_parameters

    fit_object, fit_index = context.resolve_fit(fit)
    model = getattr(fit_object, "model", None)

    report: dict[str, Any] = {
        "ok": True,
        "fit": fit_index,
        "name": str(getattr(fit_object, "name", "")),
        "model": str(getattr(model, "name", "")),
        "dataset": str(getattr(getattr(fit_object, "data", None), "name", "")),
        "chi2r": _round(chi2r(fit_object), 4),
    }
    try:
        report["fit_range"] = [int(v) for v in fit_object.fit_range]
    except Exception:
        pass
    for key, attribute in (("n_points", "n_points"), ("n_free_parameters", "n_free")):
        try:
            report[key] = int(getattr(model, attribute))
        except Exception:
            pass
    if "n_points" in report and "n_free_parameters" in report:
        report["degrees_of_freedom"] = report["n_points"] - report["n_free_parameters"]

    try:
        report["durbin_watson"] = _round(fit_object.durbin_watson, 3)
    except Exception:
        logger.debug("durbin-watson unavailable", exc_info=True)

    try:
        residuals = np.asarray(fit_object.weighted_residuals.y, dtype=float)
        finite = residuals[np.isfinite(residuals)]
        if finite.size:
            report["residuals"] = {
                "rms": _round(float(np.sqrt(np.mean(finite**2))), 3),
                "max_abs": _round(float(np.max(np.abs(finite))), 3),
                "mean": _round(float(np.mean(finite)), 3),
            }
    except Exception:
        logger.debug("weighted residuals unavailable", exc_info=True)

    convolve = getattr(model, "convolve", None)
    if convolve is not None:
        attached = getattr(convolve, "_irf", None)
        report["irf_attached"] = attached is not None
        if attached is None:
            report["warning"] = (
                "no IRF is attached — a decay fit without one is "
                "systematically wrong; attach it with set_irf"
            )
    groups = component_groups(model) if model is not None else {}
    if groups:
        report["components"] = groups
    report["parameters"] = fit_parameters(fit_object)
    report["assessment"] = assess_fit(fit_object)
    return report


@registry.add(
    name="plot_fit",
    description=(
        "Draw a fit as a PNG the user can look at: the measured data with "
        "the fitted curve on a logarithmic axis, and the weighted residuals "
        "underneath.\n"
        "Residuals that wander systematically above or below zero are the "
        "clearest sign that a model is wrong, so produce this whenever the "
        "user asks to see a fit or asks whether it is any good."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Target PNG path."},
            "fit": {
                "type": ["integer", "string"],
                "description": "Fit index or name. Omit when there is only one fit.",
            },
            "title": {"type": "string", "description": "Optional plot title."},
        },
        "required": ["path"],
    },
    safety=SAFETY_WRITE,
)
def plot_fit(
    context: AgentContext,
    path: str,
    fit: Any = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Render a fit and its residuals to a PNG file."""
    import matplotlib

    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt
    import numpy as np

    fit_object, fit_index = context.resolve_fit(fit)
    data = getattr(fit_object, "data", None)
    model = getattr(fit_object, "model", None)
    if data is None or model is None:
        raise ToolError(f"fit {fit_index} has no data or no model to plot")

    x = np.asarray(getattr(data, "x", []), dtype=float)
    y = np.asarray(getattr(data, "y", []), dtype=float)
    model_x = np.asarray(getattr(model, "x", []), dtype=float)
    model_y = np.asarray(getattr(model, "y", []), dtype=float)
    if not x.size or not y.size:
        raise ToolError(f"fit {fit_index} has no data points to plot")

    try:
        start, stop = (int(v) for v in fit_object.fit_range)
    except Exception:
        start, stop = 0, x.size - 1

    figure, (upper, lower) = plt.subplots(
        2, 1, sharex=True, figsize=(7.0, 5.0), height_ratios=[3, 1]
    )
    upper.semilogy(x, np.clip(y, 1e-9, None), color="#666666", lw=0.8, label="data")
    if model_y.size:
        upper.semilogy(
            model_x if model_x.size == model_y.size else x[: model_y.size],
            np.clip(model_y, 1e-9, None),
            color="#c0392b",
            lw=1.2,
            label="fit",
        )
    upper.axvspan(
        x[max(0, min(start, x.size - 1))],
        x[max(0, min(stop, x.size - 1))],
        color="#3498db",
        alpha=0.07,
        label="fit range",
    )
    # Clipping keeps zeros plottable on a log axis, but the limit must follow
    # the data — otherwise the decay is squeezed into the top decade.
    positive = y[y > 0]
    if positive.size:
        upper.set_ylim(bottom=max(float(positive.min()) * 0.5, float(y.max()) * 1e-6))
    upper.set_ylabel("counts")
    upper.legend(loc="upper right", fontsize=8)
    reduced = chi2r(fit_object)
    upper.set_title(
        title
        or f"{getattr(fit_object, 'name', 'fit')}"
        + (f"  (chi2r = {reduced:.3f})" if reduced is not None else "")
    )

    try:
        residuals_curve = fit_object.weighted_residuals
        residual_x = np.asarray(residuals_curve.x, dtype=float)
        residual_y = np.asarray(residuals_curve.y, dtype=float)
        lower.plot(residual_x, residual_y, color="#2c3e50", lw=0.6)
        lower.axhline(0.0, color="#c0392b", lw=0.8)
        lower.set_ylabel("w. res.")
    except Exception:
        logger.debug("residuals unavailable for plotting", exc_info=True)
    lower.set_xlabel(str(getattr(data, "x_label", "") or "channel / time"))

    target = context.resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(target, dpi=130)
    plt.close(figure)

    return {
        "ok": True,
        "fit": fit_index,
        "path": str(target),
        "chi2r": _round(reduced, 4),
        "note": "Show this file to the user; you cannot see it yourself.",
    }
