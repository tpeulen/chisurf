"""Model-structure search for ChiSurf fits, run by BFF.

The package is in the middle of a migration and holds two implementations.

**The native bridge** (:mod:`.native`, :mod:`.dispatcher`, :mod:`.execution`,
:mod:`.fixed_structure`, :mod:`.global_fit`) is the one that ships.  A model
BFF describes in data (:class:`chisurf.core.models.description.DescriptionModel`)
is searched on its own live problem; nothing is declared or copied here.  A capability declares parameters, structures, actions and a score;
the bridge validates that declaration, maps it onto the complete native graph
the ordinary fitting backend already builds, and hands the whole problem to
``IMP.bff.ModelSearch``.  Nothing crosses back into Python per candidate, and a
model BFF cannot represent is refused rather than approximated.  These names are
exported here.

**The legacy engine** (:mod:`.environment`, :mod:`.mcts`, :mod:`.network`,
:mod:`.training`, :mod:`.torch_backend`, :mod:`.main`, :mod:`.apply`) is the
original pure-Python design: a Gymnasium-style environment whose every
transition ran an embedded optimizer, a Python tree search over its discrete
actions, and a convolutional policy/value network trained by self-play.  It is
superseded by the bridge and scheduled for deletion once BFF owns the remaining
model families.

Legacy names stay reachable from this package but are resolved **lazily**, on
first attribute access, and warn.  Importing them eagerly cost every caller the
whole engine -- roughly four thousand lines plus the fluorescence simulation and
machine-learning stack -- merely to reach the bridge, which is why the GUI
imports bridge submodules by full path instead of going through here.  Import
the submodule directly if you genuinely want the legacy engine.
"""

from __future__ import annotations

import importlib
import warnings
from typing import Any

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
from chisurf.core.fitting.mcts.dispatcher import (
    prepare_described_model_search,
)

#: Legacy engine name -> the submodule that defines it.  Reaching one through
#: this package imports that submodule and nothing else.
_LEGACY: dict[str, str] = {
    name: "environment"
    for name in (
        "AgentQuestion", "DiscreteAction", "EnvConfig", "FitEnv", "FitState",
        "FitStats", "FretEnv", "FretEnvConfig", "ModelStructure", "N_ACTIONS",
        "N_TOGGLE_SLOTS", "TOGGLE_PARAMETER_BASE",
    )
} | {
    name: "mcts"
    for name in ("MCTSConfig", "MCTSFittingEngine", "Node", "SearchResult")
} | {
    name: "network" for name in ("NetConfig", "TCSPCNet", "masked_softmax")
} | {
    name: "apply"
    for name in ("environment_from_fit", "fit_is_tcspc", "transfer_state_to_fit")
} | {
    name: "training"
    for name in (
        "FretSimulateConfig", "SelfPlayConfig", "SelfPlayReport",
        "SimulateConfig", "SimulatedDecay", "SimulatedFretDecay",
        "evaluate_network", "self_play_train", "simulate_decay",
        "simulate_fret_decay",
    )
}

_NATIVE = [
    "NativeAction", "NativeParameterGroup", "NativeScore",
    "NativeSearchDeclaration", "NativeSearchPreparation", "NativeSearchReason",
    "NativeStructure", "prepare_native_model_search",
    "prepare_described_model_search",
]

__all__ = [*_NATIVE, *sorted(_LEGACY)]


def __getattr__(name: str) -> Any:
    """Resolve a legacy engine name on first use (PEP 562)."""
    module = _LEGACY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    warnings.warn(
        f"{__name__}.{name} belongs to the superseded Python search engine and "
        f"is scheduled for deletion; import it from "
        f"{__name__}.{module} if you still need it.",
        DeprecationWarning,
        stacklevel=2,
    )
    return getattr(importlib.import_module(f"{__name__}.{module}"), name)


def __dir__() -> list[str]:
    return sorted(__all__)
