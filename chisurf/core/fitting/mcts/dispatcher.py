"""Strict capability routing for ChiSurf's BFF-native model search.

The dispatcher chooses a declaration; it never chooses an optimizer.  Every
successful route ultimately constructs an ``IMP.bff.FittingModelSearchProblem``
and every refusal is returned to the caller as ``NativeSearchReason`` data.
"""

from __future__ import annotations

from typing import Any

from chisurf.core.fitting.mcts.native import (
    NativeSearchDeclaration,
    NativeSearchPreparation,
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
            return unsupported(
                CAPABILITY_ID,
                "fret_capability_unavailable",
                f"the BFF TCSPC/FRET capability is unavailable: {error}",
            )
        declaration = declare_tcspc_fret_search(fit)
        if (
            not isinstance(declaration, NativeSearchPreparation)
            or not _allows_fixed_structure(declaration)
        ):
            return declaration

    try:
        from chisurf.core.models.tcspc.lifetime import LifetimeModel
    except ImportError:
        LifetimeModel = ()
    if isinstance(model, LifetimeModel):
        try:
            from chisurf.core.fitting.mcts.tcspc_lifetime import (
                declare_tcspc_lifetime_search,
            )
        except ImportError as error:
            return unsupported(
                CAPABILITY_ID,
                "lifetime_capability_unavailable",
                f"the BFF TCSPC/lifetime capability is unavailable: {error}",
            )
        declaration = declare_tcspc_lifetime_search(fit)
        if (
            not isinstance(declaration, NativeSearchPreparation)
            or not _allows_fixed_structure(declaration)
        ):
            return declaration

    from chisurf.core.fitting.mcts.fixed_structure import (
        build_fixed_structure_declaration,
    )

    return build_fixed_structure_declaration(fit)


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
    declaration = declare_model_search(fit)
    if isinstance(declaration, NativeSearchPreparation):
        return declaration
    return prepare_native_model_search(declaration)


__all__ = ["CAPABILITY_ID", "declare_model_search", "prepare_model_search"]
