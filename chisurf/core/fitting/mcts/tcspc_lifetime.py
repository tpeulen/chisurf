"""Native model-search capabilities shared by TCSPC decay models.

The declarations in this module describe finite, already allocated model
structures. BFF owns candidate fitting and scoring; these helpers only map
ChiSurf's parameter groups to stable structure and action identities.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np

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

CAPABILITY_ID = "chisurf.tcspc.lifetime.v2"

DeclarationResult = NativeSearchDeclaration | NativeSearchPreparation


def _unique_parameters(parameters: Iterable[Any]) -> tuple[Any, ...]:
    seen: set[int] = set()
    answer = []
    for parameter in parameters:
        if id(parameter) not in seen:
            seen.add(id(parameter))
            answer.append(parameter)
    return tuple(answer)


def _canonical_parameter(parameter: Any) -> Any | None:
    """Return the terminal owner of one parameter link, or ``None`` on a cycle."""
    seen: set[int] = set()
    current = parameter
    while getattr(current, "is_linked", False):
        if id(current) in seen:
            return None
        seen.add(id(current))
        current = getattr(current, "link", None)
        if current is None:
            return None
    return current


def _tcspc_score(fit: Any, capability_id: str) -> NativeScore | NativeSearchPreparation:
    """Declare a BIC penalty for the residual objective BFF already owns.

    Poisson search retains ChiSurf's historical photon-count sample size.
    Weighted least squares uses the number of fitted observations. Candidate
    residuals and the reward itself stay entirely inside BFF.
    """
    try:
        start, stop = int(fit.xmin), int(fit.xmax)
        values = np.asarray(fit.data.y, dtype=float).ravel()[start:stop]
        if str(getattr(fit, "noise_model", "")).lower() == "poisson":
            effective_size = float(values.sum())
        else:
            effective_size = float(values.size)
    except Exception:
        effective_size = 0.0
    if not math.isfinite(effective_size) or effective_size <= 0.0:
        return unsupported(
            capability_id,
            "invalid_effective_sample_size",
            "BIC scoring requires a non-empty finite fit range",
        )
    return NativeScore(
        residual_output="residuals",
        complexity_penalty=0.5 * math.log(effective_size),
    )


def _structural_group(
    capability_id: str,
    key: str,
    parameters: Sequence[Any],
    enabled_values: Sequence[float],
    inactive_values: Sequence[float],
    claimed_owners: set[int],
) -> NativeParameterGroup | NativeSearchPreparation:
    """Map a structural row to independent canonical owners.

    Linked followers are omitted in favour of their terminal owner. This is
    essential for global declarations: BFF must optimise the one owner port,
    while every member port follows it. Owners shared by two structural rows
    are refused because those rows cannot be enabled independently.
    """
    owners: list[Any] = []
    enabled: list[float] = []
    inactive: list[float] = []
    row_seen: set[int] = set()
    for parameter, enabled_value, inactive_value in zip(
        parameters, enabled_values, inactive_values
    ):
        if getattr(parameter, "redundant", False):
            continue
        owner = _canonical_parameter(parameter)
        if owner is None:
            return unsupported(
                capability_id,
                "cyclic_structural_link",
                f"structural parameter {parameter.name!r} has no terminal link owner",
                str(parameter.name),
            )
        if id(owner) in row_seen:
            continue
        if id(owner) in claimed_owners:
            return unsupported(
                capability_id,
                "coupled_structural_rows",
                f"canonical owner {owner.name!r} controls more than one structural row",
                str(owner.name),
            )
        if bool(getattr(owner, "fixed", False)):
            return unsupported(
                capability_id,
                "fixed_structural_parameter",
                f"user-fixed structural parameter {owner.name!r} will not be released",
                str(owner.name),
            )
        row_seen.add(id(owner))
        owners.append(owner)
        enabled.append(float(enabled_value))
        inactive.append(float(inactive_value))
    if not owners:
        return unsupported(
            capability_id,
            "unsearchable_component",
            f"structural group {key!r} has no independent owner parameter",
            key,
        )
    claimed_owners.update(row_seen)
    return NativeParameterGroup(key, tuple(owners), tuple(enabled), tuple(inactive))


def _count_lattice(
    dimensions: Sequence[tuple[str, int, int, str]],
    constant_groups: Sequence[str] = (),
) -> tuple[tuple[NativeStructure, ...], tuple[NativeAction, ...], str]:
    """Build an acyclic add-one lattice for independent component counts."""
    ranges = [range(minimum, maximum + 1) for _, minimum, maximum, _ in dimensions]
    counts = list(itertools.product(*ranges))

    def state_key(values: Sequence[int]) -> str:
        return ";".join(
            f"{label}:{value}" for (label, _minimum, _maximum, _prefix), value
            in zip(dimensions, values)
        )

    structures: list[NativeStructure] = []
    actions: list[NativeAction] = []
    for values in counts:
        key = state_key(values)
        free_groups = list(constant_groups)
        for (_label, _minimum, _maximum, prefix), value in zip(dimensions, values):
            free_groups.extend(f"{prefix}{index}" for index in range(1, value + 1))
        structures.append(NativeStructure(key, tuple(free_groups)))
        for dimension, (label, _minimum, maximum, _prefix) in enumerate(dimensions):
            if values[dimension] >= maximum:
                continue
            target = list(values)
            target[dimension] += 1
            actions.append(
                NativeAction(
                    key,
                    f"add-{label}-{target[dimension]}",
                    state_key(target),
                )
            )
        actions.append(NativeAction(key, "terminate", key, prior=0.25, terminal=True))
    initial = state_key([minimum for _label, minimum, _maximum, _prefix in dimensions])
    return tuple(structures), tuple(actions), initial


def _rotation_groups(
    model: Any,
    capability_id: str,
    claimed_owners: set[int],
) -> tuple[list[NativeParameterGroup], tuple[str, int, int, str] | None] | NativeSearchPreparation:
    """Declare allocated anisotropy rows when the decay is polarised.

    One rotation is the physical base structure. Its amplitude is the scale
    reference (the anisotropy group normalises amplitudes to ``r0``), so only
    its correlation time is fitted. Later rows add an amplitude ratio and a
    correlation time. Magic-angle data have no anisotropy node and therefore
    no rotation dimension.
    """
    anisotropy = getattr(model, "anisotropy", None)
    if anisotropy is None or anisotropy._is_vm_polarization(
        anisotropy.polarization_type
    ):
        return [], None
    rows = list(zip(anisotropy._bs, anisotropy._rhos))
    if not rows:
        # A VV/VH group may intentionally carry no rotation rows yet. The
        # native graph represents that exact empty spectrum; there is simply
        # no preallocated rotation decision for this search to make.
        return [], None

    groups: list[NativeParameterGroup] = []
    for index, (amplitude, correlation_time) in enumerate(rows, start=1):
        parameters = (correlation_time,) if index == 1 else (amplitude, correlation_time)
        enabled = (float(correlation_time.value),) if index == 1 else (
            0.2,
            float(correlation_time.value),
        )
        inactive = (float(correlation_time.value),) if index == 1 else (
            0.0,
            float(correlation_time.value),
        )
        group = _structural_group(
            capability_id,
            f"tcspc.rotation.{index}",
            parameters,
            enabled,
            inactive,
            claimed_owners,
        )
        if isinstance(group, NativeSearchPreparation):
            return group
        groups.append(group)
    return groups, ("rotation", 1, len(rows), "tcspc.rotation.")


def _always_free_group(
    model: Any,
    structural_parameters: Sequence[Any],
    claimed_owners: set[int],
) -> NativeParameterGroup | None:
    """Keep the user's independent non-structural free parameters in every state."""
    structural_ids = {id(parameter) for parameter in structural_parameters}
    always = []
    for parameter in model.parameters_all:
        if id(parameter) in structural_ids or getattr(parameter, "redundant", False):
            continue
        owner = _canonical_parameter(parameter)
        if owner is None or id(owner) in claimed_owners or id(owner) in structural_ids:
            continue
        if not bool(getattr(owner, "fixed", False)):
            always.append(owner)
    always = list(_unique_parameters(always))
    if not always:
        return None
    claimed_owners.update(id(parameter) for parameter in always)
    return NativeParameterGroup("tcspc.user-free", tuple(always))


def declare_tcspc_lifetime_search(fit: Any) -> DeclarationResult:
    """Declare component search for a plain, BFF-representable lifetime decay."""
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    model = getattr(fit, "model", None)
    if type(model) is not LifetimeModel:
        return unsupported(
            CAPABILITY_ID,
            "unsupported_model_family",
            "this capability supports plain TCSPC LifetimeModel fits",
        )
    score = _tcspc_score(fit, CAPABILITY_ID)
    if isinstance(score, NativeSearchPreparation):
        return score

    model.find_parameters()
    lifetime_rows = list(zip(model.lifetimes._amplitudes, model.lifetimes._lifetimes))
    if not lifetime_rows:
        return unsupported(CAPABILITY_ID, "empty_structure", "the model has no lifetime row")

    claimed_owners: set[int] = set()
    groups: list[NativeParameterGroup] = []
    structural_parameters: list[Any] = []
    for index, (amplitude, lifetime) in enumerate(lifetime_rows, start=1):
        structural_parameters.extend((amplitude, lifetime))
        group = _structural_group(
            CAPABILITY_ID,
            f"tcspc.lifetime.{index}",
            (amplitude, lifetime),
            (1.0 / index, float(lifetime.value)),
            ((float(amplitude.value) if index == 1 else 0.0), float(lifetime.value)),
            claimed_owners,
        )
        if isinstance(group, NativeSearchPreparation):
            return group
        groups.append(group)

    rotations = _rotation_groups(model, CAPABILITY_ID, claimed_owners)
    if isinstance(rotations, NativeSearchPreparation):
        return rotations
    rotation_groups, rotation_dimension = rotations
    groups.extend(rotation_groups)
    anisotropy = model.anisotropy
    structural_parameters.extend(anisotropy._bs)
    structural_parameters.extend(anisotropy._rhos)

    always = _always_free_group(model, structural_parameters, claimed_owners)
    constant_groups = ()
    if always is not None:
        groups.insert(0, always)
        constant_groups = (always.key,)

    dimensions = [("lifetime", 1, len(lifetime_rows), "tcspc.lifetime.")]
    if rotation_dimension is not None:
        dimensions.append(rotation_dimension)
    structures, actions, initial = _count_lattice(dimensions, constant_groups)
    live_parameters = _unique_parameters(
        tuple(model.parameters_all)
        + tuple(parameter for group in groups for parameter in group.parameters)
    )
    return NativeSearchDeclaration(
        capability_id=CAPABILITY_ID,
        fit=fit,
        objective_model=model,
        live_parameters=live_parameters,
        groups=tuple(groups),
        structures=structures,
        actions=actions,
        initial_structure=initial,
        score=score,
    )


def prepare_tcspc_lifetime_search(fit: Any) -> NativeSearchPreparation:
    """Build the strict BFF problem for a declared TCSPC lifetime search."""
    declaration = declare_tcspc_lifetime_search(fit)
    if isinstance(declaration, NativeSearchPreparation):
        return declaration
    return prepare_native_model_search(declaration)
