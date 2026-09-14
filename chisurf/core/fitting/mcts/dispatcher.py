"""Strict capability routing for ChiSurf's BFF-native model search.

The dispatcher chooses a declaration; it never chooses an optimizer.  Every
successful route ultimately constructs an ``IMP.bff.FittingModelSearchProblem``
and every refusal is returned to the caller as ``NativeSearchReason`` data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chisurf.core.fitting.mcts.native import (
    NativeSearchDeclaration,
    NativeSearchPreparation,
    NativeSearchReason,
    prepare_native_model_search,
    unsupported,
)

CAPABILITY_ID = "chisurf.model-search.dispatch.v1"
_FIXED_STRUCTURE_REASONS = {"unsupported_model_family", "no_searchable_structure"}


def _allows_fixed_structure(result: NativeSearchPreparation) -> bool:
    """Whether a structural capability explicitly declined structure only."""
    return bool(result.reasons) and all(
        reason.code in _FIXED_STRUCTURE_REASONS for reason in result.reasons
    )


def _single_fit(fit: Any) -> Any:
    """Unwrap the ordinary one-member GUI ``FitGroup``."""
    members = list(getattr(fit, "grouped_fits", []) or [])
    return members[0] if len(members) == 1 else fit


def _with_reasons(
    result: NativeSearchDeclaration | NativeSearchPreparation,
    deferred: tuple[NativeSearchReason, ...],
) -> NativeSearchDeclaration | NativeSearchPreparation:
    """Prefix a refusal with why the model family's own capability declined.

    A successful fixed-structure declaration keeps no trace: the family
    limitation cost the fit nothing, so it is not a refusal to report.  Only
    when the fallback refuses too does the caller need both halves of the
    story.
    """
    # `supported` means a problem and no reasons, so prefixing a successful
    # fallback would turn a working refinement into a refusal.
    if (not deferred or not isinstance(result, NativeSearchPreparation)
            or result.problem is not None):
        return result
    return NativeSearchPreparation(
        capability_id=result.capability_id,
        problem=result.problem,
        binding=result.binding,
        reasons=deferred + tuple(result.reasons),
    )


@dataclass
class DescribedModelBinding:
    """A search over a live BFF model, and the way back if it is not accepted.

    The search writes the model's own ports while it runs. Accepting its
    winner is leaving the model standing at it; refusing it is putting back
    the values and the topology the user had.
    """

    fit: Any
    model: Any
    values: tuple[float, ...]
    structure: str

    def apply_state(self, problem: Any, state: Any) -> None:
        from chisurf.core.fitting import factorgraph

        problem.activate_state(state)
        factorgraph.bump_structure_version()
        self.model.update()
        update = getattr(self.fit, "update", None)
        if callable(update):
            update()

    def restore(self, problem: Any) -> None:
        from chisurf.core.fitting import factorgraph

        for canonical, value in zip(problem.get_parameter_ids(), self.values):
            port = problem.get_parameter(canonical)
            was = port.fixed
            port.fixed = False
            port.value = float(value)
            port.fixed = was
        if self.structure:
            problem.select_structure(self.structure)
        factorgraph.bump_structure_version()
        self.model.update()


def prepare_described_model_search(fit: Any) -> NativeSearchPreparation:
    """Search a described model on its own live problem, or say why not."""
    model = fit.model
    problem = model.problem
    if problem is None:
        return unsupported(
            CAPABILITY_ID,
            "incomplete_model",
            "the model is missing " + ", ".join(model.missing),
        )
    values = tuple(float(problem.get_parameter(i).value) for i in problem.get_parameter_ids())
    binding = DescribedModelBinding(fit, model, values, str(problem.get_active_structure()))
    return NativeSearchPreparation(CAPABILITY_ID, problem=problem, binding=binding)


def declare_model_search(
    fit: Any,
) -> NativeSearchDeclaration | NativeSearchPreparation:
    """Return one local fit's declaration without constructing its graph."""
    fit = _single_fit(fit)
    model = getattr(fit, "model", None)
    if model is None:
        return unsupported(
            CAPABILITY_ID,
            "missing_fitting_model",
            "the selected object does not expose a fitting model",
        )

    # A family capability that is *absent* must cost the fit no more than one
    # that declines structure only: both fall through to fixed-structure
    # refinement below.  Refusing outright would leave a model whose family
    # module has not been written yet unable to refine parameters it shares
    # with every other family.
    deferred: list[NativeSearchReason] = []

    # Family imports stay local.  Model search is optional at import time and
    # loading the fitting GUI must not import every scientific model family.
    try:
        from chisurf.core.models.tcspc.fret import FRETModel
    except ImportError:
        FRETModel = ()
    if isinstance(model, FRETModel):
        try:
            from chisurf.core.fitting.mcts.tcspc_fret import (
                declare_tcspc_fret_search,
            )
        except ImportError as error:
            deferred.append(
                NativeSearchReason(
                    "fret_capability_unavailable",
                    f"the BFF TCSPC/FRET capability is unavailable: {error}",
                    "fret",
                )
            )
        else:
            declaration = declare_tcspc_fret_search(fit)
            if (
                not isinstance(declaration, NativeSearchPreparation)
                or not _allows_fixed_structure(declaration)
            ):
                return declaration
            deferred.extend(declaration.reasons)

    from chisurf.core.fitting.mcts.fixed_structure import (
        build_fixed_structure_declaration,
    )

    return _with_reasons(build_fixed_structure_declaration(fit), tuple(deferred))


def prepare_model_search(fit: Any) -> NativeSearchPreparation:
    """Prepare the one native search appropriate for ``fit``.

    Multi-member and explicit global models are indivisible.  A refusal from
    their joint capability is returned as-is; members are never searched one
    at a time because that would violate shared-parameter semantics.
    """
    members = list(getattr(fit, "grouped_fits", []) or [])
    model = getattr(fit, "model", None)
    is_explicit_global = False
    try:
        from chisurf.core.models.global_model.globalfit import GlobalFitModel

        is_explicit_global = isinstance(model, GlobalFitModel)
    except ImportError:
        pass

    if len(members) > 1 or is_explicit_global:
        try:
            from chisurf.core.fitting.mcts.global_fit import (
                prepare_global_model_search,
            )
        except ImportError as error:
            return unsupported(
                CAPABILITY_ID,
                "global_capability_unavailable",
                f"the BFF global-search capability is unavailable: {error}",
            )
        return prepare_global_model_search(fit, declare_model_search)
    # A model BFF owns is searched where it stands: the problem *is* the
    # model the user sees, so there is nothing to declare and nothing to copy.
    deferred: tuple[NativeSearchReason, ...] = ()
    single = _single_fit(fit)
    try:
        from chisurf.core.models.description import DescriptionModel
    except ImportError:
        DescriptionModel = ()
    if isinstance(getattr(single, "model", None), DescriptionModel):
        return prepare_described_model_search(single)

    declaration = declare_model_search(fit)
    if isinstance(declaration, NativeSearchPreparation):
        return _with_reasons(declaration, deferred)
    return _with_reasons(prepare_native_model_search(declaration), deferred)


__all__ = [
    "CAPABILITY_ID",
    "DescribedModelBinding",
    "declare_model_search",
    "prepare_described_model_search",
    "prepare_model_search",
]
