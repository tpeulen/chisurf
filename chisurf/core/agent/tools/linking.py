"""Agent tools for global analysis: sharing parameters between fits.

ChiSurf is a *global* analysis platform, and linking is what makes it one.
A linked parameter has a single value fitted against several datasets at
once, so a quantity that is physically the same in every measurement -- a
donor lifetime, an instrument shift, a colour-correction factor -- is
determined by all of the data instead of drifting independently in each fit.

That is not a convenience: it is usually the only way to pin a parameter that
one dataset alone cannot constrain.
"""

from __future__ import annotations

import logging
from typing import Any

from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.spec import SAFETY_READ, SAFETY_WRITE, ToolError, ToolRegistry

logger = logging.getLogger(__name__)

registry = ToolRegistry()


def _parameters_of(fit: Any) -> dict[str, Any]:
    """Return a fit's parameters by name."""
    return getattr(getattr(fit, "model", None), "parameters_all_dict", None) or {}


def _link_state(fit: Any, index: int) -> list[dict[str, Any]]:
    """Return the linked parameters of one fit."""
    links: list[dict[str, Any]] = []
    for name, parameter in _parameters_of(fit).items():
        source = getattr(parameter, "link", None)
        if source is not None:
            links.append(
                {
                    "fit": index,
                    "parameter": name,
                    "follows": str(getattr(source, "name", "")),
                    "value": getattr(parameter, "value", None),
                }
            )
    return links


def _free_count(fit: Any) -> int | None:
    """Return the number of free parameters of a fit, if it can be read."""
    try:
        return int(getattr(fit.model, "n_free"))
    except Exception:
        return None


@registry.add(
    name="link_parameters",
    description=(
        "Share one or more parameters between fits, so a single value is "
        "fitted against several datasets at once (global analysis).\n"
        "Link a quantity that is physically the same in every measurement — a "
        "donor lifetime across a titration, an instrument time-shift across "
        "one session, a correction factor. The linked fits then constrain it "
        "together, which is often the only way to pin a parameter that one "
        "dataset alone cannot.\n"
        "The source fit keeps the value; the target fits follow it and lose "
        "those degrees of freedom. Run the fits again afterwards."
    ),
    parameters={
        "type": "object",
        "properties": {
            "parameters": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exact parameter names to share, e.g. ['tL1', 'tL2'].",
            },
            "source_fit": {
                "type": ["integer", "string"],
                "description": "The fit whose value the others follow.",
            },
            "target_fits": {
                "type": "array",
                "items": {"type": ["integer", "string"]},
                "description": "Fits that should follow. Omit for every other fit.",
            },
        },
        "required": ["parameters", "source_fit"],
    },
    safety=SAFETY_WRITE,
)
def link_parameters(
    context: AgentContext,
    parameters: list[str],
    source_fit: Any,
    target_fits: Any = None,
) -> dict[str, Any]:
    """Link parameters of one or more fits to a source fit."""
    source, source_index = context.resolve_fit(source_fit)
    if isinstance(parameters, str):
        parameters = [parameters]
    if not parameters:
        raise ToolError("name at least one parameter to link")

    if target_fits:
        targets = [context.resolve_fit(reference)[1] for reference in target_fits]
    else:
        targets = [index for index in range(len(context.fits)) if index != source_index]
    targets = [index for index in targets if index != source_index]
    if not targets:
        raise ToolError(
            "there is no other fit to link to — linking shares a value "
            "between fits, so at least two are needed"
        )

    source_parameters = _parameters_of(source)
    missing_in_source = [name for name in parameters if name not in source_parameters]
    if missing_in_source:
        raise ToolError(
            f"fit {source_index} has no parameter(s) {missing_in_source}. "
            f"Its parameters are: {sorted(source_parameters)}"
        )

    linked: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for index in targets:
        target = context.fits[index]
        free_before = _free_count(target)
        for name in parameters:
            if name not in _parameters_of(target):
                skipped.append({"fit": index, "parameter": name, "reason": "not in this model"})
                continue
            try:
                target.link_parameter(name, name, source)
            except Exception as error:
                skipped.append({"fit": index, "parameter": name, "reason": str(error)})
                continue
            linked.append({"fit": index, "parameter": name})
        free_after = _free_count(target)
        if free_before is not None and free_after is not None and free_after >= free_before:
            logger.debug("linking fit %s did not reduce its free parameters", index)

    if not linked:
        raise ToolError(
            "nothing could be linked: "
            + "; ".join(f"fit {e['fit']} {e['parameter']}: {e['reason']}" for e in skipped[:5])
        )

    from chisurf.core.agent.tools.fitting import refresh_gui

    refresh_gui()
    result: dict[str, Any] = {
        "ok": True,
        "source_fit": source_index,
        "linked": linked,
        "free_parameters": {
            str(index): _free_count(context.fits[index]) for index in [source_index, *targets]
        },
        "next_step": (
            "Run the fits again — the linked value is now determined by all of "
            "them together, so the previous results are stale."
        ),
    }
    if skipped:
        result["skipped"] = skipped
    return result


@registry.add(
    name="unlink_parameters",
    description=(
        "Release parameters that were shared between fits, so each fit "
        "determines its own value again."
    ),
    parameters={
        "type": "object",
        "properties": {
            "parameters": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Parameter names to release. Omit to release every link.",
            },
            "fits": {
                "type": "array",
                "items": {"type": ["integer", "string"]},
                "description": "Fits to release them in. Omit for all fits.",
            },
        },
    },
    safety=SAFETY_WRITE,
)
def unlink_parameters(
    context: AgentContext,
    parameters: list[str] | None = None,
    fits: Any = None,
) -> dict[str, Any]:
    """Remove parameter links."""
    if isinstance(parameters, str):
        parameters = [parameters]
    indices = (
        [context.resolve_fit(reference)[1] for reference in fits]
        if fits
        else list(range(len(context.fits)))
    )
    if not indices:
        raise ToolError("there are no fits in the session")

    released: list[dict[str, Any]] = []
    for index in indices:
        fit = context.fits[index]
        for name, parameter in _parameters_of(fit).items():
            if getattr(parameter, "link", None) is None:
                continue
            if parameters and name not in parameters:
                continue
            try:
                fit.unlink_parameter(name)
            except Exception as error:
                logger.debug("unlink %s on fit %s failed: %s", name, index, error)
                continue
            released.append({"fit": index, "parameter": name})

    from chisurf.core.agent.tools.fitting import refresh_gui

    refresh_gui()
    return {
        "ok": True,
        "released": released,
        "n_released": len(released),
        "next_step": "Run the fits again; each now determines its own value."
        if released
        else "Nothing was linked.",
    }


@registry.add(
    name="list_links",
    description=(
        "Show which parameters are currently shared between fits, and how "
        "many free parameters each fit has left.\n"
        "Check this before interpreting a global analysis — a result means "
        "something different depending on what was tied together."
    ),
    parameters={"type": "object", "properties": {}},
    safety=SAFETY_READ,
)
def list_links(context: AgentContext) -> dict[str, Any]:
    """Report every parameter link in the session."""
    fits = context.fits
    links: list[dict[str, Any]] = []
    for index, fit in enumerate(fits):
        links.extend(_link_state(fit, index))
    return {
        "ok": True,
        "n_links": len(links),
        "links": links,
        "free_parameters": {str(index): _free_count(fit) for index, fit in enumerate(fits)},
    }
