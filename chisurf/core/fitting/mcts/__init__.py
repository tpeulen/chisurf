"""Reinforcement-learning model selection for TCSPC decays (MCTS + TCSPCNet).

The package turns structural model selection — how many lifetime components,
whether the IRF shift, prompt scatter and dark background are fitted — into a
search problem: a Gymnasium-style environment (:mod:`.environment`) whose
every transition runs an embedded continuous optimizer, a Monte Carlo tree
search over its discrete actions (:mod:`.mcts`) guided by a 1D convolutional
policy/value network (:mod:`.network`), a self-play trainer that simulates
decays and lets the network learn the selection (:mod:`.training`), a bridge
that applies the selected model to a live ChiSurf fit (:mod:`.apply`), and a
demonstration driver (:mod:`.main`).

The FRET environment (:class:`~chisurf.core.fitting.mcts.environment.FretEnv`)
extends the same mask to Gaussian distance-distribution fits, including the
linked donor-only reference analysis — and asks the user, through an
:class:`~chisurf.core.fitting.mcts.environment.AgentQuestion` (a message box
in the GUI), which loaded dataset is that reference when it is not clear.
"""

from chisurf.core.fitting.mcts.environment import (
    AgentQuestion,
    DiscreteAction,
    EnvConfig,
    FitEnv,
    FitState,
    FitStats,
    FretEnv,
    FretEnvConfig,
    ModelStructure,
    N_ACTIONS,
    N_TOGGLE_SLOTS,
    TOGGLE_PARAMETER_BASE,
)
from chisurf.core.fitting.mcts.mcts import (
    MCTSConfig,
    MCTSFittingEngine,
    Node,
    SearchResult,
)
from chisurf.core.fitting.mcts.network import (
    NetConfig,
    TCSPCNet,
    masked_softmax,
)
from chisurf.core.fitting.mcts.apply import (
    environment_from_fit,
    fit_is_tcspc,
    transfer_state_to_fit,
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
from chisurf.core.fitting.mcts.tcspc_lifetime import (
    prepare_tcspc_lifetime_search,
)
from chisurf.core.fitting.mcts.training import (
    FretSimulateConfig,
    SelfPlayConfig,
    SelfPlayReport,
    SimulateConfig,
    SimulatedDecay,
    SimulatedFretDecay,
    evaluate_network,
    self_play_train,
    simulate_decay,
    simulate_fret_decay,
)

__all__ = [
    "AgentQuestion", "DiscreteAction", "EnvConfig", "FitEnv", "FitState",
    "FitStats", "FretEnv", "FretEnvConfig", "ModelStructure", "N_ACTIONS", "N_TOGGLE_SLOTS",
    "TOGGLE_PARAMETER_BASE",
    "MCTSConfig", "MCTSFittingEngine", "Node", "SearchResult",
    "NetConfig", "TCSPCNet", "masked_softmax",
    "transfer_state_to_fit", "environment_from_fit", "fit_is_tcspc",
    "NativeAction", "NativeParameterGroup", "NativeScore",
    "NativeSearchDeclaration", "NativeSearchPreparation", "NativeSearchReason",
    "NativeStructure", "prepare_native_model_search",
    "prepare_tcspc_lifetime_search",
    "FretSimulateConfig", "SelfPlayConfig", "SelfPlayReport", "SimulateConfig",
    "SimulatedDecay", "SimulatedFretDecay", "evaluate_network", "self_play_train",
    "simulate_decay", "simulate_fret_decay",
]
