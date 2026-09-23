"""BFF-native search for fits whose model structure is already chosen.

This is the common capability behind ordinary fitting models.  It does not
interpret a model family, manufacture components, or evaluate an objective in
Python.  It exposes the user's current free canonical parameters to BFF as one
or more declared groups and offers one native refinement before termination.

Model-family capabilities with structural moves should be selected before
this one.  Selecting this capability means "keep this structure and make the
routine fitting decision automatically".
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from chisurf.core.fitting.mcts.native import (
    NativeAction,
    NativeParameterGroup,
    NativeScore,
    NativeSearchDeclaration,
    NativeSearchPreparation,
    NativeStructure,
    prepare_native_model_search,
    unsupported,
)

CAPABILITY_ID = "chisurf.fixed-structure.v1"


def _current_free_parameters(model: Any) -> tuple[Any, ...]:
    """Return each user-free canonical owner once, in model order."""
    model.find_parameters()
    seen: set[int] = set()
    free = []
    for parameter in model.parameters_all:
        identity = id(parameter)
        if (
            identity in seen
            or bool(parameter.fixed)
            or bool(getattr(parameter, "is_linked", False))
            or bool(getattr(parameter, "redundant", False))
        ):
            continue
        seen.add(identity)
        free.append(parameter)
    return tuple(free)


def _complete_groups(
    free: tuple[Any, ...],
    parameter_groups: Sequence[NativeParameterGroup] | None,
) -> tuple[NativeParameterGroup, ...] | NativeSearchPreparation:
    """Normalize an explicit grouping and require exact free-owner coverage."""
    if parameter_groups is None:
        return (
            NativeParameterGroup(
                key="user-free",
                parameters=free,
                initial_values=tuple(float(parameter.value) for parameter in free),
            ),
        )

    groups = tuple(parameter_groups)
    declared = tuple(parameter for group in groups for parameter in group.parameters)
    free_ids = {id(parameter) for parameter in free}
    declared_ids = {id(parameter) for parameter in declared}
    extra = next((parameter for parameter in declared if id(parameter) not in free_ids), None)
    if extra is not None:
        return unsupported(
            CAPABILITY_ID,
            "non_free_parameter_declared",
            f"declared parameter {extra.name!r} is not a user-free canonical owner",
            str(extra.name),
        )
    missing = next((parameter for parameter in free if id(parameter) not in declared_ids), None)
    if missing is not None:
        return unsupported(
            CAPABILITY_ID,
            "incomplete_parameter_groups",
            f"user-free parameter {missing.name!r} is missing from the declared groups",
            str(missing.name),
        )
    return groups


def build_fixed_structure_declaration(
    fit: Any,
    *,
    parameter_groups: Sequence[NativeParameterGroup] | None = None,
) -> NativeSearchDeclaration | NativeSearchPreparation:
    """Describe native refinement without constructing or evaluating a graph.

    The separate declaration step lets a heterogeneous/global capability
    prefix and combine member-owned groups before it builds one joint BFF
    objective.  A structured refusal is returned when there is no meaningful
    native optimization problem.
    """
    model = getattr(fit, "model", None)
    if model is None or not hasattr(model, "find_parameters"):
        return unsupported(
            CAPABILITY_ID,
            "missing_fitting_model",
            "the selected object does not expose a fitting model",
        )

    try:
        free = _current_free_parameters(model)
    except Exception as error:
        return unsupported(
            CAPABILITY_ID,
            "parameter_discovery_failed",
            f"the model's free parameters could not be discovered: {error}",
        )
    if not free:
        return unsupported(
            CAPABILITY_ID,
            "no_free_parameters",
            "the selected fit has no user-free canonical parameters",
        )

    groups = _complete_groups(free, parameter_groups)
    if isinstance(groups, NativeSearchPreparation):
        return groups
    group_keys = tuple(group.key for group in groups)
    return NativeSearchDeclaration(
        capability_id=CAPABILITY_ID,
        fit=fit,
        objective_model=model,
        live_parameters=tuple(model.parameters_all),
        groups=groups,
        structures=(
            NativeStructure("initialized", group_keys),
            NativeStructure("refined", group_keys),
        ),
        actions=(
            NativeAction("initialized", "refine", "refined", prior=0.8),
            NativeAction("initialized", "terminate", "initialized", prior=0.2, terminal=True),
            NativeAction("refined", "terminate", "refined", terminal=True),
        ),
        initial_structure="initialized",
        # The number of free parameters is identical in both states, so a
        # complexity term would be a constant and cannot affect the decision.
        score=NativeScore(),
    )


def prepare_fixed_structure_search(
    fit: Any,
    *,
    parameter_groups: Sequence[NativeParameterGroup] | None = None,
) -> NativeSearchPreparation:
    """Prepare strict BFF-native refinement for any graph-backed fit."""
    declaration = build_fixed_structure_declaration(fit, parameter_groups=parameter_groups)
    if isinstance(declaration, NativeSearchPreparation):
        return declaration
    return prepare_native_model_search(declaration)


__all__ = [
    "CAPABILITY_ID",
    "build_fixed_structure_declaration",
    "prepare_fixed_structure_search",
]
