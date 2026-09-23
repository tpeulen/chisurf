"""Declarative bridge from ChiSurf fits to BFF's native model search.

The bridge contains no model-family decisions.  A capability declares the
parameters, structures, actions, and score; this module only validates that
declaration and maps it onto the complete native graph built by the ordinary
ChiSurf fitting backend.  There is intentionally no Python evaluator fallback.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NativeSearchReason:
    """Machine-readable reason why a fit cannot use native model search."""

    code: str
    message: str
    feature: str = ""


@dataclass(frozen=True)
class NativeParameterGroup:
    """One independently enabled set of canonical ChiSurf parameters."""

    key: str
    parameters: tuple[Any, ...]
    enable_values: tuple[float, ...] = ()
    initial_values: tuple[float, ...] = ()


@dataclass(frozen=True)
class NativeStructure:
    """A stable structure key and the parameter groups free within it."""

    key: str
    free_groups: tuple[str, ...]


@dataclass(frozen=True)
class NativeAction:
    """A declared transition between two native structures."""

    parent: str
    key: str
    result: str
    prior: float = 1.0
    terminal: bool = False


@dataclass(frozen=True)
class NativeScore:
    """Scoring settings interpreted exclusively by BFF.

    Without a ``score_output`` every structure is compared by BIC over
    ``effective_sample_size`` observations; ``1`` charges nothing for a free
    parameter, which is right only when every candidate has the same number.
    """

    effective_sample_size: float = 1.0
    score_output: str = ""
    acceptable_output: str = ""


@dataclass(frozen=True)
class NativeSearchDeclaration:
    """Complete model-independent input needed to construct a BFF problem."""

    capability_id: str
    fit: Any
    objective_model: Any
    live_parameters: tuple[Any, ...]
    groups: tuple[NativeParameterGroup, ...]
    structures: tuple[NativeStructure, ...]
    actions: tuple[NativeAction, ...]
    initial_structure: str
    score: NativeScore = field(default_factory=NativeScore)


@dataclass
class NativeSearchBinding:
    """Objects needed to interpret cached BFF states after a search."""

    declaration: NativeSearchDeclaration
    parameters: tuple[Any, ...]
    ports: tuple[Any, ...]
    keepalive: tuple[Any, ...]

    def apply_state(self, problem: Any, state: Any) -> None:
        """Apply one cached winner to live owners as a single transaction."""
        values = tuple(problem.get_cached_values(state.get_key()))
        fixed = tuple(problem.get_cached_fixed(state.get_key()))
        if len(values) != len(self.parameters) or len(fixed) != len(self.parameters):
            raise ValueError("cached native state does not match the declared parameters")
        live_snapshot = _snapshot(self.declaration.live_parameters)
        try:
            for parameter, value, is_fixed in zip(self.parameters, values, fixed):
                parameter.value = float(value)
                parameter.fixed = bool(is_fixed)
            self.declaration.objective_model.find_parameters()
            self.declaration.objective_model.update()
            update_fit = getattr(self.declaration.fit, "update", None)
            if callable(update_fit):
                update_fit()
        except Exception:
            _restore(live_snapshot)
            self.declaration.objective_model.find_parameters()
            raise


@dataclass
class NativeSearchPreparation:
    """Either a ready native problem/binding or structured refusal reasons."""

    capability_id: str
    problem: Any | None = None
    binding: NativeSearchBinding | None = None
    reasons: tuple[NativeSearchReason, ...] = ()

    @property
    def supported(self) -> bool:
        """Whether preparation produced a usable native problem."""
        return self.problem is not None and not self.reasons


def unsupported(
    capability_id: str, code: str, message: str, feature: str = ""
) -> NativeSearchPreparation:
    """Construct one concise unsupported preparation result."""
    return NativeSearchPreparation(
        capability_id=capability_id,
        reasons=(NativeSearchReason(code, message, feature),),
    )


def _unique(items: Sequence[Any]) -> tuple[Any, ...]:
    seen: set[int] = set()
    return tuple(item for item in items if not (id(item) in seen or seen.add(id(item))))


def _snapshot(parameters: Sequence[Any]) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            parameter,
            float(parameter.value),
            bool(parameter.fixed),
            getattr(parameter, "link", None),
            bool(getattr(parameter, "redundant", False)),
        )
        for parameter in parameters
    )


def _restore(snapshot: Sequence[tuple[Any, ...]]) -> None:
    # Links are not changed during preparation.  Restore them first anyway so
    # value writes on followers retain their original canonical ownership.
    for parameter, _value, _fixed, link, _redundant in snapshot:
        if getattr(parameter, "link", None) is not link:
            parameter.link = link
    for parameter, value, fixed, _link, redundant in snapshot:
        current = float(parameter.value)
        values_differ = current != value and not (math.isnan(current) and math.isnan(value))
        if values_differ:
            parameter.value = value
        if (
            hasattr(parameter, "redundant")
            and bool(getattr(parameter, "redundant", False)) != redundant
        ):
            parameter.redundant = redundant
        if bool(parameter.fixed) != fixed:
            parameter.fixed = fixed


def _validate(declaration: NativeSearchDeclaration) -> NativeSearchReason | None:
    if not declaration.groups:
        return NativeSearchReason("empty_declaration", "no parameter groups were declared")
    group_keys = [group.key for group in declaration.groups]
    if len(group_keys) != len(set(group_keys)):
        return NativeSearchReason("duplicate_group", "parameter-group keys must be unique")
    structure_keys = [structure.key for structure in declaration.structures]
    if declaration.initial_structure not in structure_keys:
        return NativeSearchReason(
            "missing_initial_structure", "the initial structure was not declared"
        )
    known_groups = set(group_keys)
    known_structures = set(structure_keys)
    seen_parameters: set[int] = set()
    for group in declaration.groups:
        if not group.parameters:
            return NativeSearchReason("empty_group", f"group {group.key!r} is empty", group.key)
        if group.enable_values and len(group.enable_values) != len(group.parameters):
            return NativeSearchReason(
                "invalid_group_seed", f"group {group.key!r} has the wrong seed count", group.key
            )
        if group.initial_values and len(group.initial_values) != len(group.parameters):
            return NativeSearchReason(
                "invalid_initial_values",
                f"group {group.key!r} has the wrong initial-value count",
                group.key,
            )
        for parameter in group.parameters:
            if getattr(parameter, "is_linked", False):
                return NativeSearchReason(
                    "linked_follower_declared",
                    f"{parameter.name!r} is a follower; declare its canonical owner",
                    str(parameter.name),
                )
            if id(parameter) in seen_parameters:
                return NativeSearchReason(
                    "parameter_in_multiple_groups",
                    f"{parameter.name!r} belongs to more than one search group",
                    str(parameter.name),
                )
            seen_parameters.add(id(parameter))
    for structure in declaration.structures:
        if not set(structure.free_groups) <= known_groups:
            return NativeSearchReason(
                "unknown_structure_group", f"structure {structure.key!r} names an unknown group"
            )
    for action in declaration.actions:
        if action.parent not in known_structures or action.result not in known_structures:
            return NativeSearchReason(
                "unknown_action_structure", f"action {action.key!r} names an unknown structure"
            )
    return None


def prepare_native_model_search(
    declaration: NativeSearchDeclaration,
) -> NativeSearchPreparation:
    """Create a callback-free BFF problem or return a structured refusal.

    ``graph_objective()`` returning ``None`` is terminal.  This function never
    calls the director/scipy minimizer path and never evaluates a score in
    Python.
    """
    invalid = _validate(declaration)
    if invalid is not None:
        return NativeSearchPreparation(declaration.capability_id, reasons=(invalid,))

    try:
        import IMP.bff as bff
    except Exception as error:
        return unsupported(
            declaration.capability_id,
            "backend_unavailable",
            f"IMP.bff is unavailable: {error}",
        )
    if not hasattr(bff, "FitObjective"):
        return unsupported(
            declaration.capability_id,
            "backend_api_unavailable",
            "IMP.bff predates the FitObjective search API",
        )

    declared_parameters = _unique(
        [parameter for group in declaration.groups for parameter in group.parameters]
    )
    live_parameters = _unique(declaration.live_parameters)
    live_ids = {id(parameter) for parameter in live_parameters}
    missing = [parameter for parameter in declared_parameters if id(parameter) not in live_ids]
    if missing:
        return unsupported(
            declaration.capability_id,
            "foreign_parameter",
            f"declared parameter {missing[0].name!r} is not owned by the objective",
            str(missing[0].name),
        )

    snapshot = _snapshot(live_parameters)
    built = None
    try:
        # graph_objective exposes ports only for free canonical owners.  The
        # graph is private, so temporarily exposing declared owners is safe as
        # long as the complete live state is restored before returning.
        for parameter in declared_parameters:
            parameter.fixed = False
        declaration.objective_model.find_parameters()
        from chisurf.core.fitting.minimizer import graph_objective

        built = graph_objective(declaration.fit, declaration.objective_model)
    except Exception as error:
        reason = NativeSearchReason(
            "native_graph_error", f"native objective construction failed: {error}"
        )
    else:
        reason = None
    finally:
        _restore(snapshot)
        try:
            declaration.objective_model.find_parameters()
        except Exception:
            pass

    if reason is not None:
        return NativeSearchPreparation(declaration.capability_id, reasons=(reason,))
    if built is None:
        return unsupported(
            declaration.capability_id,
            "native_objective_unrepresentable",
            "the complete fit objective has no BFF-native graph representation",
        )

    minimizer, native_parameters = built
    try:
        objective, native_ports, _score_name = minimizer._sampler_surface
    except Exception:
        return unsupported(
            declaration.capability_id,
            "native_surface_missing",
            "the native objective does not expose parameter-owner ports",
        )
    port_by_parameter = {
        id(parameter): port for parameter, port in zip(native_parameters, native_ports)
    }
    unmapped = [
        parameter for parameter in declared_parameters if id(parameter) not in port_by_parameter
    ]
    if unmapped:
        return unsupported(
            declaration.capability_id,
            "native_port_unrepresentable",
            f"parameter {unmapped[0].name!r} has no canonical native owner port",
            str(unmapped[0].name),
        )

    group_by_key = {group.key: group for group in declaration.groups}
    initial = next(
        structure
        for structure in declaration.structures
        if structure.key == declaration.initial_structure
    )
    initially_free = set(initial.free_groups)
    problem = bff.FittingModelSearchProblem()
    ordered_parameters: list[Any] = []
    ordered_ports: list[Any] = []
    ids: list[str] = []
    group_of: list[str] = []
    start_values: list[float] = []
    enable_values: list[float] = []
    for group in declaration.groups:
        ports = [port_by_parameter[id(parameter)] for parameter in group.parameters]
        for index, (parameter, port) in enumerate(zip(group.parameters, ports)):
            if group.initial_values:
                port.value = float(group.initial_values[index])
            port.fixed = group.key not in initially_free
            canonical = f"{group.key}.{index}"
            problem.add_parameter(canonical, port)
            ids.append(canonical)
            group_of.append(group.key)
            start_values.append(float(port.value))
            enable_values.append(
                float(group.enable_values[index]) if group.enable_values else float(port.value)
            )
            ordered_parameters.append(parameter)
            ordered_ports.append(port)
    for structure in declaration.structures:
        free = set(structure.free_groups)
        # A group free at the root starts where the user left it; one this
        # structure frees on top starts from its declared seed.
        values = [
            enable if group in free and group not in initially_free else start
            for group, start, enable in zip(group_of, start_values, enable_values)
        ]
        mask = [0 if group in free else 1 for group in group_of]
        problem.add_structure(structure.key, objective, ids, ordered_ports, values, mask)
        score = declaration.score
        if score.score_output:
            problem.set_structure_score_output(structure.key, score.score_output)
        else:
            problem.set_structure_selection(
                structure.key,
                bff.MODEL_SELECTION_BIC,
                float(score.effective_sample_size),
                float(len(mask) - sum(mask)),
            )
        if score.acceptable_output:
            problem.set_structure_acceptable_output(structure.key, score.acceptable_output)
    problem.set_initial_structure(declaration.initial_structure)
    for action in declaration.actions:
        problem.add_action(
            action.parent, action.key, action.result, float(action.prior), bool(action.terminal)
        )

    keepalive = (minimizer, objective, tuple(native_ports), group_by_key)
    binding = NativeSearchBinding(
        declaration, tuple(ordered_parameters), tuple(ordered_ports), keepalive
    )
    problem._chisurf_binding = binding
    return NativeSearchPreparation(declaration.capability_id, problem, binding)
