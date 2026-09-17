"""Model-structure search for ChiSurf fits, run by BFF.

The bridge (:mod:`.native`, :mod:`.dispatcher`, :mod:`.execution`,
:mod:`.fixed_structure`, :mod:`.global_fit`) is the only implementation: a
model BFF describes in data
(:class:`chisurf.core.models.description.DescriptionModel`) is searched on its
own live problem, and any other fit is searched only where a capability maps it
onto a complete native graph handed to ``IMP.bff.ModelSearch``.  A model BFF
cannot search has no search; nothing is approximated in Python.
"""

from __future__ import annotations

from chisurf.core.fitting.mcts.dispatcher import (
    prepare_described_model_search,
)
from chisurf.core.fitting.mcts.native import (
    NativeAction,
    NativeParameterGroup,
    NativeScore,
    NativeSearchDeclaration,
    NativeSearchPreparation,
    NativeSearchReason,
    NativeStructure,
    prepare_native_model_search,
)

_NATIVE = [
    "NativeAction",
    "NativeParameterGroup",
    "NativeScore",
    "NativeSearchDeclaration",
    "NativeSearchPreparation",
    "NativeSearchReason",
    "NativeStructure",
    "prepare_native_model_search",
    "prepare_described_model_search",
]

__all__ = list(_NATIVE)
