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
    prepare_native_model_search,
    unsupported,
)

CAPABILITY_ID = "chisurf.model-search.dispatch.v1"


def _single_fit(fit: Any) -> Any:
    """Unwrap the ordinary one-member GUI ``FitGroup``."""
    members = list(getattr(fit, "grouped_fits", []) or [])
    return members[0] if len(members) == 1 else fit


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

    from chisurf.core.fitting.mcts.fixed_structure import (
        build_fixed_structure_declaration,
    )

    return build_fixed_structure_declaration(fit)


def model_search_available(fit: Any) -> bool:
    """Whether BFF can search ``fit`` at all, without building anything.

    A described model is BFF's own, so it can, even while a measurement is
    still missing (the search then says which). Any other fit can where a
    capability declares it; a group can when every member can. There is no
    other engine to fall back on, so a fit this refuses has no model search.
    """
    try:
        from chisurf.core.models.description import DescriptionModel
    except ImportError:
        DescriptionModel = ()
    members = list(getattr(fit, "grouped_fits", []) or []) or [fit]
    for member in members:
        model = getattr(member, "model", None)
        if model is None:
            return False
        if isinstance(model, DescriptionModel):
            continue
        try:
            declaration = declare_model_search(member)
        except Exception:
            return False
        if isinstance(declaration, NativeSearchPreparation) and not declaration.supported:
            return False
    return True


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
    single = _single_fit(fit)
    try:
        from chisurf.core.models.description import DescriptionModel
    except ImportError:
        DescriptionModel = ()
    if isinstance(getattr(single, "model", None), DescriptionModel):
        return prepare_described_model_search(single)

    declaration = declare_model_search(fit)
    if isinstance(declaration, NativeSearchPreparation):
        return declaration
    return prepare_native_model_search(declaration)


__all__ = [
    "CAPABILITY_ID",
    "DescribedModelBinding",
    "declare_model_search",
    "model_search_available",
    "prepare_described_model_search",
    "prepare_model_search",
]
