"""Strict native model search for heterogeneous and global fits.

Member capabilities describe their own finite structure graphs.  This module
forms their reachable product and submits one declaration for the existing
``GlobalFitModel`` objective.  The product is assembled in Python once; every
candidate fit, joint residual evaluation, score, and tree traversal remains in
BFF.

Linked parameters are represented by their canonical owner exactly once.
Moves that change a linked structural owner are admitted only when all member
structures that declare that owner move consistently.  A member that cannot
provide a declaration refuses the whole global problem.
"""

from __future__ import annotations

import itertools
import math
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from chisurf.core.fitting.mcts.native import (
    NativeAction,
    NativeParameterGroup,
    NativeScore,
    NativeSearchDeclaration,
    NativeSearchPreparation,
    NativeSearchReason,
    NativeStructure,
    prepare_native_model_search,
    unsupported,
)

CAPABILITY_ID = "chisurf.global.native.v1"
MAX_ACTION_COMBINATIONS = 4096

MemberDeclaration = NativeSearchDeclaration | NativeSearchPreparation
MemberDeclarer = Callable[[Any], MemberDeclaration]

__all__ = [
    "CAPABILITY_ID",
    "MemberDeclaration",
    "MemberDeclarer",
    "prepare_global_model_search",
]


@dataclass(frozen=True)
class _LogicalGroup:
    member: int
    key: str
    owners: tuple[Any, ...]
    seeds: tuple[float | None, ...]
    initial: tuple[float | None, ...]


def _reason(
    code: str, message: str, feature: str = ""
) -> NativeSearchPreparation:
    return unsupported(CAPABILITY_ID, code, message, feature)


def _owner(parameter: Any) -> Any:
    """Return the terminal link owner, rejecting corrupt link cycles."""
    seen: set[int] = set()
    current = parameter
    while getattr(current, "is_linked", False):
        marker = id(current)
        if marker in seen:
            raise ValueError(f"parameter link cycle at {current.name!r}")
        seen.add(marker)
        linked = getattr(current, "link", None)
        if linked is None:
            raise ValueError(f"linked parameter {current.name!r} has no owner")
        current = linked
    return current


def _unique(items: Sequence[Any]) -> tuple[Any, ...]:
    seen: set[int] = set()
    result: list[Any] = []
    for item in items:
        if id(item) not in seen:
            seen.add(id(item))
            result.append(item)
    return tuple(result)


def _member_refusal(
    index: int, preparation: NativeSearchPreparation
) -> tuple[NativeSearchReason, ...]:
    reasons = preparation.reasons or (
        NativeSearchReason(
            "member_declaration_missing",
            "the member capability did not return a declaration",
        ),
    )
    return tuple(
        NativeSearchReason(
            reason.code,
            f"member {index + 1}: {reason.message}",
            f"member:{index + 1}/{reason.feature}" if reason.feature else f"member:{index + 1}",
        )
        for reason in reasons
    )


def _member_structures(
    declaration: NativeSearchDeclaration,
) -> tuple[dict[str, NativeStructure], dict[str, tuple[NativeAction, ...]]]:
    group_keys = {group.key for group in declaration.groups}
    if len(group_keys) != len(declaration.groups):
        raise ValueError("member parameter-group keys must be unique")
    structures = {structure.key: structure for structure in declaration.structures}
    if len(structures) != len(declaration.structures):
        raise ValueError("member structure keys must be unique")
    if declaration.initial_structure not in structures:
        raise ValueError("member initial structure was not declared")
    for structure in declaration.structures:
        unknown = set(structure.free_groups) - group_keys
        if unknown:
            raise ValueError(
                f"member structure {structure.key!r} names unknown groups: "
                f"{sorted(unknown)!r}"
            )
    actions: dict[str, list[NativeAction]] = {key: [] for key in structures}
    for action in declaration.actions:
        if action.parent not in structures or action.result not in structures:
            raise ValueError(f"action {action.key!r} names an unknown member structure")
        if not action.terminal:
            actions[action.parent].append(action)
    return structures, {key: tuple(value) for key, value in actions.items()}


def _score(declarations: Sequence[NativeSearchDeclaration]) -> NativeScore:
    """Require one score surface and combine BIC-style sample sizes.

    A joint BFF residual owns the numerical score.  Positive member penalties
    encode ``log(n_effective) / 2``; independent member sample sizes add.  Zero
    means that candidate structures have equal dimension (or no complexity
    penalty) and stays zero for the joint problem.
    """
    scores = [declaration.score for declaration in declarations]
    if any(
        score.residual_output != "residuals"
        or score.score_output
        or score.acceptable_output
        for score in scores
    ):
        raise ValueError(
            "global search requires BFF joint residual scoring without "
            "member-only score or acceptability outputs"
        )
    penalties = [float(score.complexity_penalty) for score in scores]
    if any(not math.isfinite(value) or value < 0.0 for value in penalties):
        raise ValueError("member complexity penalties must be finite and non-negative")
    positive = [value for value in penalties if value > 0.0]
    if not positive:
        penalty = 0.0
    elif len(positive) != len(penalties):
        raise ValueError(
            "members disagree on whether model complexity is penalized"
        )
    else:
        largest = max(2.0 * value for value in positive)
        penalty = 0.5 * (
            largest
            + math.log(sum(math.exp(2.0 * value - largest) for value in positive))
        )
    return NativeScore(residual_output="residuals", complexity_penalty=penalty)


def _state_key(state: tuple[str, ...]) -> str:
    return "|".join(
        f"member-{index + 1}={quote(key, safe='')}"
        for index, key in enumerate(state)
    )


def _combined_action_key(
    selected: Sequence[NativeAction | None],
) -> str:
    return "+".join(
        f"member-{index + 1}:{quote(action.key, safe='')}"
        for index, action in enumerate(selected)
        if action is not None
    )


def prepare_global_model_search(
    fit: Any,
    declare_member: MemberDeclarer,
) -> NativeSearchPreparation:
    """Prepare one strict BFF-native search over every member of ``fit``.

    ``declare_member`` runs only during preparation and must return a
    :class:`NativeSearchDeclaration`.  It is never installed as a numerical
    callback.  Returning a refusal, a prepared per-member problem, or an
    invalid declaration refuses the complete global fit.
    """
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.models.global_model.globalfit import GlobalFitModel

    if not isinstance(fit, FitGroup):
        return _reason(
            "not_global_fit", "native global model search requires a FitGroup"
        )
    objective_model = getattr(fit, "_model", None)
    if not isinstance(objective_model, GlobalFitModel):
        return _reason(
            "missing_global_objective",
            "the fit group has no GlobalFitModel objective",
        )
    members = tuple(objective_model.fits)
    if not members:
        return _reason("empty_global_fit", "the global fit has no members")

    declarations: list[NativeSearchDeclaration] = []
    refusals: list[NativeSearchReason] = []
    for index, member in enumerate(members):
        try:
            declared = declare_member(member)
        except Exception as error:
            refusals.append(
                NativeSearchReason(
                    "member_declaration_error",
                    f"member {index + 1}: capability declaration failed: {error}",
                    f"member:{index + 1}",
                )
            )
            continue
        if isinstance(declared, NativeSearchPreparation):
            refusals.extend(_member_refusal(index, declared))
            continue
        if not isinstance(declared, NativeSearchDeclaration):
            refusals.append(
                NativeSearchReason(
                    "invalid_member_declaration",
                    f"member {index + 1}: capability returned {type(declared).__name__}",
                    f"member:{index + 1}",
                )
            )
            continue
        if declared.fit is not member or declared.objective_model is not member.model:
            refusals.append(
                NativeSearchReason(
                    "foreign_member_declaration",
                    f"member {index + 1}: declaration belongs to another fit or model",
                    f"member:{index + 1}",
                )
            )
            continue
        declarations.append(declared)
    if refusals:
        return NativeSearchPreparation(CAPABILITY_ID, reasons=tuple(refusals))

    try:
        score = _score(declarations)
        member_graphs = [_member_structures(declaration) for declaration in declarations]
    except ValueError as error:
        return _reason("incompatible_member_contract", str(error))

    # Discover sharing from the complete member models, not merely from the
    # parameters a structural capability happens to make searchable.
    owner_members: dict[int, set[int]] = {}
    owners_by_id: dict[int, Any] = {}
    try:
        for index, member in enumerate(members):
            for parameter in member.model.parameters_all:
                owner = _owner(parameter)
                owners_by_id[id(owner)] = owner
                owner_members.setdefault(id(owner), set()).add(index)
        for parameter in objective_model.global_parameters_all:
            owner = _owner(parameter)
            owners_by_id[id(owner)] = owner
            owner_members.setdefault(id(owner), set()).update(range(len(members)))
    except ValueError as error:
        return _reason("invalid_parameter_links", str(error))
    logical: dict[tuple[int, str], _LogicalGroup] = {}
    owner_logical: dict[int, set[tuple[int, str]]] = {}
    try:
        for index, declaration in enumerate(declarations):
            seen_keys: set[str] = set()
            for group in declaration.groups:
                if not group.key or group.key in seen_keys:
                    raise ValueError(
                        f"member {index + 1} has an empty or duplicate parameter-group key"
                    )
                seen_keys.add(group.key)
                seeds = (
                    tuple(float(value) for value in group.enable_values)
                    if group.enable_values
                    else (None,) * len(group.parameters)
                )
                initial = (
                    tuple(float(value) for value in group.initial_values)
                    if group.initial_values
                    else (None,) * len(group.parameters)
                )
                if len(seeds) != len(group.parameters) or len(initial) != len(group.parameters):
                    raise ValueError(
                        f"member {index + 1} group {group.key!r} has invalid seed dimensions"
                    )
                if any(
                    value is not None and not math.isfinite(value)
                    for value in (*seeds, *initial)
                ):
                    raise ValueError(
                        f"member {index + 1} group {group.key!r} has a non-finite seed"
                    )
                entry_by_owner: dict[int, tuple[Any, float | None, float | None]] = {}
                for parameter, seed, first in zip(group.parameters, seeds, initial):
                    owner = _owner(parameter)
                    marker = id(owner)
                    previous = entry_by_owner.get(marker)
                    if previous is not None and (previous[1:] != (seed, first)):
                        raise ValueError(
                            f"member {index + 1} group {group.key!r} gives one owner conflicting values"
                        )
                    entry_by_owner[marker] = (owner, seed, first)
                    owner_logical.setdefault(marker, set()).add((index, group.key))
                    owners_by_id[marker] = owner
                    # Some family-level relations (notably a FRET model whose
                    # donor spectrum is owned by a separate reference fit)
                    # expose the external owner only through their declaration,
                    # rather than as a Parameter.link in parameters_all.
                    owner_members.setdefault(marker, set()).add(index)
                if not entry_by_owner:
                    raise ValueError(
                        f"member {index + 1} group {group.key!r} has no canonical owner"
                    )
                entries = tuple(entry_by_owner.values())
                logical[(index, group.key)] = _LogicalGroup(
                    index,
                    group.key,
                    tuple(entry[0] for entry in entries),
                    tuple(entry[1] for entry in entries),
                    tuple(entry[2] for entry in entries),
                )
    except ValueError as error:
        return _reason("invalid_member_groups", str(error))

    shared_owner_ids = {
        marker for marker, member_ids in owner_members.items() if len(member_ids) > 1
    }

    # An owner cannot belong to unrelated groups in one member. Across members
    # it is a shared group whose structural activity has to agree.
    for marker, references in owner_logical.items():
        per_member: dict[int, int] = {}
        for member_index, _group_key in references:
            per_member[member_index] = per_member.get(member_index, 0) + 1
        if any(count > 1 for count in per_member.values()):
            owner = owners_by_id[marker]
            return _reason(
                "owner_in_multiple_member_groups",
                f"canonical owner {owner.name!r} belongs to multiple groups in one member",
                str(owner.name),
            )

    owner_order = {
        id(parameter): index
        for index, parameter in enumerate(_unique(objective_model.parameters_all))
    }
    shared_ids = sorted(
        shared_owner_ids & set(owner_logical),
        key=lambda marker: owner_order.get(marker, len(owner_order)),
    )
    shared_key = {
        marker: f"shared:{position + 1}:{quote(str(owners_by_id[marker].name), safe='')}"
        for position, marker in enumerate(shared_ids)
    }

    native_groups: list[NativeParameterGroup] = []
    translated: dict[tuple[int, str], tuple[str, ...]] = {}
    shared_values: dict[int, tuple[float | None, float | None]] = {}
    for logical_key, group in logical.items():
        local_parameters: list[Any] = []
        local_seeds: list[float] = []
        local_initial: list[float] = []
        local_has_seeds = True
        local_has_initial = True
        keys: list[str] = []
        for owner, seed, first in zip(group.owners, group.seeds, group.initial):
            marker = id(owner)
            if marker in shared_key:
                keys.append(shared_key[marker])
                existing = shared_values.get(marker)
                values = (seed, first)
                if existing is not None:
                    for old, new in zip(existing, values):
                        if old is not None and new is not None and not math.isclose(old, new):
                            return _reason(
                                "shared_seed_conflict",
                                f"shared owner {owner.name!r} has conflicting member seeds",
                                str(owner.name),
                            )
                    values = tuple(
                        old if old is not None else new
                        for old, new in zip(existing, values)
                    )
                shared_values[marker] = values
            else:
                local_parameters.append(owner)
                local_has_seeds &= seed is not None
                local_has_initial &= first is not None
                if seed is not None:
                    local_seeds.append(seed)
                if first is not None:
                    local_initial.append(first)
        if local_parameters:
            key = f"member:{group.member + 1}:{quote(group.key, safe='')}"
            keys.insert(0, key)
            native_groups.append(
                NativeParameterGroup(
                    key,
                    tuple(local_parameters),
                    tuple(local_seeds) if local_has_seeds else (),
                    tuple(local_initial) if local_has_initial else (),
                )
            )
        translated[logical_key] = tuple(dict.fromkeys(keys))

    for marker in shared_ids:
        seed, first = shared_values.get(marker, (None, None))
        native_groups.append(
            NativeParameterGroup(
                shared_key[marker],
                (owners_by_id[marker],),
                (seed,) if seed is not None else (),
                (first,) if first is not None else (),
            )
        )

    structure_maps = [item[0] for item in member_graphs]
    action_maps = [item[1] for item in member_graphs]

    def active_logical(state: tuple[str, ...], logical_key: tuple[int, str]) -> bool:
        index, group_key = logical_key
        return group_key in structure_maps[index][state[index]].free_groups

    def consistent(state: tuple[str, ...]) -> bool:
        for marker, references in owner_logical.items():
            if marker not in shared_key or len(references) < 2:
                continue
            activity = {active_logical(state, reference) for reference in references}
            if len(activity) > 1:
                return False
        return True

    initial_state = tuple(
        declaration.initial_structure for declaration in declarations
    )
    if not consistent(initial_state):
        return _reason(
            "shared_initial_structure_mismatch",
            "linked member declarations disagree on the initial activity of a shared owner",
        )

    reachable: set[tuple[str, ...]] = {initial_state}
    queue = deque([initial_state])
    transitions: dict[
        tuple[str, ...], list[tuple[tuple[NativeAction | None, ...], tuple[str, ...]]]
    ] = {}
    while queue:
        state = queue.popleft()
        options: list[tuple[NativeAction | None, ...]] = []
        combinations = 1
        for index, structure_key in enumerate(state):
            member_options: tuple[NativeAction | None, ...] = (
                None,
                *action_maps[index].get(structure_key, ()),
            )
            options.append(member_options)
            combinations *= len(member_options)
        if combinations > MAX_ACTION_COMBINATIONS:
            return _reason(
                "global_branching_too_large",
                f"one global state expands to {combinations} coordinated action combinations",
            )
        outgoing: list[tuple[tuple[NativeAction | None, ...], tuple[str, ...]]] = []
        for selected in itertools.product(*options):
            if all(action is None for action in selected):
                continue
            target = tuple(
                action.result if action is not None else state[index]
                for index, action in enumerate(selected)
            )
            if not consistent(target):
                continue
            outgoing.append((selected, target))
            if target not in reachable:
                reachable.add(target)
                queue.append(target)
        transitions[state] = outgoing

    structures: list[NativeStructure] = []
    actions: list[NativeAction] = []
    for state in sorted(reachable, key=_state_key):
        free: list[str] = []
        for index, structure_key in enumerate(state):
            for group_key in structure_maps[index][structure_key].free_groups:
                free.extend(translated[(index, group_key)])
        key = _state_key(state)
        structures.append(NativeStructure(key, tuple(dict.fromkeys(free))))
        for selected, target in transitions.get(state, ()):
            priors = [action.prior for action in selected if action is not None]
            actions.append(
                NativeAction(
                    key,
                    _combined_action_key(selected),
                    _state_key(target),
                    prior=math.prod(priors),
                )
            )
        actions.append(NativeAction(key, "terminate", key, prior=0.25, terminal=True))

    capability_id = CAPABILITY_ID + "[" + ",".join(
        declaration.capability_id for declaration in declarations
    ) + "]"
    combined = NativeSearchDeclaration(
        capability_id=capability_id,
        fit=fit,
        objective_model=objective_model,
        live_parameters=_unique(objective_model.parameters_all),
        groups=tuple(native_groups),
        structures=tuple(structures),
        actions=tuple(actions),
        initial_structure=_state_key(initial_state),
        score=score,
    )
    return prepare_native_model_search(combined)
