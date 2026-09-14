"""Monte Carlo tree search over model structures, guided by TCSPCNet.

The search treats model selection the way an experienced user performs it:
make a structural decision (add a component, switch on the scatter term, …),
let the local optimiser do its job, look at the residuals, decide again. The
tree caches the optimised state of every structure it has visited, so the
embedded inner loop runs once per (structure, warm start) — not once per
selection — and the discrete search never re-fits what it already knows.

Selection follows the PUCT rule of the mission statement,

.. math::

    \\mathrm{PUCT}(s, a) = \\frac{Q(s, a)}{N(s, a) + 1}
        + c_{\\mathrm{puct}} \\, P(s, a) \\,
          \\frac{\\sqrt{N(s)}}{1 + N(s, a)},

where :math:`Q(s, a)` is the **accumulated** value of the child (so the first
term is a damped mean that converges to the mean as visits grow), :math:`P`
comes from the network's policy head (uniform when untrained) and the second
term decays as the child is visited, letting exploration hand over to
exploitation.

Expansion is *lazy*: the priors of all valid actions are known before any
fitting (one network call), but a child's state is only optimised the first
time it is actually selected. Leaf evaluation is the state's reward — the
information-theoretic score — squashed with ``tanh`` against the root's reward
into ``[-1, 1]``, the same quantity the network's value head is trained to
predict. With an untrained network the search therefore reduces to
reward-guided UCT-style exploration, which already solves the task; the
network sharpens it with experience.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from chisurf.core.fitting.mcts.environment import (
    DiscreteAction,
    FitEnv,
    FitState,
    N_ACTIONS,
)

ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]


@dataclass
class MCTSConfig:
    """Search controls.

    Parameters
    ----------
    n_simulations : int
        Number of tree traversals per search. Each simulation performs at most
        one new inner-loop optimisation (lazy expansion), so the search cost
        is roughly ``n_simulations`` inner loops.
    c_puct : float
        Exploration constant of the PUCT rule. Higher trusts the prior longer.
    value_scale : float
        Multiplier on the *effective* value scale. Structural reward
        differences are thousands of log-likelihood units, but what "one unit
        of value" should mean is the Poisson noise floor of the likelihood
        surface, √(2·N_bins) (the 1σ fluctuation of a likelihood-ratio test):
        the leaf value is ``tanh((R_leaf − R_root) / (value_scale·√(2·N)))``.
        With the default 1.0, a model that is one likelihood-σ better than
        the root is worth ≈ 0.76 in value; clearly-better models saturate
        near +1 (which is fine — they are clearly better).
    dirichlet_alpha, dirichlet_fraction : float
        Dirichlet noise mixed into the root priors (exploration insurance
        against a wrong prior; 0 disables it, which is right for a fully
        deterministic evaluation).
    prior_blend : float
        Fraction of the uniform prior mixed into the network prior. The
        network's only contribution to a search is its priors (leaf values
        are the reward itself), so a systematically wrong prior can only
        lose simulations; a blend of 0.5 makes the learned prior advisory —
        able to reorder exploration, never to lock the tree.
    min_visits_for_training : int
        Only nodes visited at least this often contribute training examples;
        a node visited twice encodes the roll of the exploration dice, not a
        policy.
    """

    n_simulations: int = 200
    c_puct: float = 1.5
    value_scale: float = 4.0
    dirichlet_alpha: float = 0.15
    dirichlet_fraction: float = 0.25
    prior_blend: float = 0.5
    min_visits_for_training: int = 3


class Node:
    """One node of the search tree.

    Attributes
    ----------
    state : FitState or None
        The optimised state of this node's structure. ``None`` until the node
        is first selected (lazy evaluation).
    prior : float
        ``P(s, a)`` — the network's prior for the action leading into this
        node.
    children : dict
        Maps :class:`DiscreteAction` to child :class:`Node`.
    visit_count, value_sum : int, float
        ``N`` and the accumulated backed-up value ``Q`` of the mission
        statement's notation.
    terminal : bool
        True for the ``TERMINATE_FIT`` child (the episode ends here).
    """

    __slots__ = ("state", "prior", "children", "visit_count", "value_sum",
                 "expanded", "evaluated", "terminal", "parent_action", "parent",
                 "structure_id")

    def __init__(self, prior: float = 1.0, terminal: bool = False,
                 parent_action: Optional[DiscreteAction] = None,
                 parent: Optional["Node"] = None):
        self.state: Optional[FitState] = None
        self.prior = float(prior)
        self.children: Dict[DiscreteAction, Node] = {}
        self.visit_count = 0
        self.value_sum = 0.0
        self.expanded = False
        self.evaluated = False
        self.terminal = terminal
        self.parent_action = parent_action
        self.parent = parent
        self.structure_id: Optional[tuple] = None

    @property
    def mean_value(self) -> float:
        """Mean backed-up value ``Q/N`` (0 before the first visit)."""
        if self.visit_count == 0:
            return 0.0
        return self.value_sum / self.visit_count

    def puct(self, action: DiscreteAction, child: "Node",
             c_puct: float, parent_visits: int) -> float:
        """Upper confidence bound of one action, per the mission statement."""
        q_term = child.value_sum / (child.visit_count + 1)
        u_term = c_puct * child.prior * math.sqrt(parent_visits) / (1 + child.visit_count)
        return q_term + u_term


@dataclass
class SearchResult:
    """What one search found.

    Attributes
    ----------
    best_state : FitState
        The recommended model: the highest-reward state evaluated by the
        search (the information criterion is the objective; the greedy visit
        path is kept alongside as ``best_path`` for interpretation).
    best_path : list of DiscreteAction
        Greedy (most-visited) action sequence from the root until the search
        stopped choosing structural moves.
    root_state : FitState
        The state the search started from.
    n_states_evaluated, n_simulations : int, int
        Work actually done (inner-loop fits, traversals).
    improvement : float
        ``R(best) − R(root)`` in reward units.
    """

    root_state: FitState
    best_state: FitState
    best_path: List[DiscreteAction] = field(default_factory=list)
    n_states_evaluated: int = 0
    n_simulations: int = 0
    improvement: float = 0.0
    #: Whether the selected model's χ²ᵣ is statistically consistent with 1.
    acceptable: bool = False


@dataclass
class TrainingExample:
    """One (observation, structure, policy, value) training record."""

    observation: np.ndarray
    structure_features: np.ndarray
    policy_target: np.ndarray
    value_target: float


class MCTSFittingEngine:
    """Tree search over :class:`FitEnv` structures.

    Parameters
    ----------
    env : FitEnv
        The environment (data + inner loop). The engine only calls its
        functional interface, so the same environment instance is shared by
        every search.
    network : TCSPCNet, optional
        Policy/value guidance. Without a network the priors are uniform and
        the value is the squashed reward — a complete, network-free fallback.
    config : MCTSConfig, optional
        Search controls.

    Notes
    -----
    After :meth:`search`, :attr:`training_examples` holds one record per
    expanded node: the visit distribution over its children (the policy
    target) and the reward difference to the search root (the value target).
    """

    def __init__(
        self,
        env: FitEnv,
        network=None,
        config: Optional[MCTSConfig] = None,
    ):
        self.env = env
        self.network = network
        self.config = config if config is not None else MCTSConfig()
        self.training_examples: List[TrainingExample] = []
        #: Effective value squash scale: the Poisson noise floor of the
        #: likelihood surface (√(2·N_bins)), scaled by ``config.value_scale``.
        self._value_scale = float(
            self.config.value_scale * math.sqrt(2.0 * max(env.n_channels, 1))
        )

    # ------------------------------------------------------------------ #
    # Priors and values                                                  #
    # ------------------------------------------------------------------ #

    def _action_mask(self, structure) -> np.ndarray:
        mask = np.zeros(N_ACTIONS, dtype=bool)
        for action in self.env.valid_actions(structure):
            mask[int(action)] = True
        return mask

    def _priors(self, node: Node) -> Dict[DiscreteAction, float]:
        """Priors over the valid actions of a node's state.

        The network is consulted once per expansion; untrained or absent, the
        prior is uniform over the valid actions. Root priors are mixed with
        Dirichlet noise per ``config`` for exploration. The network prior is
        blended with the uniform one per ``prior_blend`` — the insurance that
        a wrong prior cannot lock the tree.
        """
        actions = self.env.valid_actions(node.state.structure, node.state)
        mask = self._action_mask(node.state.structure)
        if self.network is not None:
            obs = self.env.observation(node.state)
            feat = self.env.structure_features(node.state.structure)
            probs, _ = self.network.predict(obs, feat, mask)
            uniform = mask.astype(float) / mask.sum()
            blend = float(np.clip(self.config.prior_blend, 0.0, 1.0))
            probs = (1.0 - blend) * probs + blend * uniform
        else:
            probs = mask.astype(float) / mask.sum()
        priors = {a: float(probs[int(a)]) for a in actions}
        if node.parent_action is None and self.config.dirichlet_fraction > 0 \
                and len(actions) > 1:
            noise = np.random.dirichlet(
                [self.config.dirichlet_alpha] * len(actions)
            )
            frac = self.config.dirichlet_fraction
            for a, eps in zip(actions, noise):
                priors[a] = (1.0 - frac) * priors[a] + frac * float(eps)
        return priors

    def _reward_value(self, state: FitState, root_reward: float) -> float:
        """Squash a reward into ``[-1, 1]`` relative to the search root."""
        return float(np.tanh(
            (state.stats.reward - root_reward) / self._value_scale
        ))

    # ------------------------------------------------------------------ #
    # Tree search                                                        #
    # ------------------------------------------------------------------ #

    def _expand(self, node: Node, root_reward: float) -> None:
        """Attach children with priors; states are fitted lazily.

        Actions whose structural result recreates a structure already on the
        path from the root are refused: a toggle flipped back is a wasted
        simulation, and a confident-but-wrong prior must not be able to spend
        the whole budget walking a cycle.
        """
        priors = self._priors(node)
        # Structural sanity: the parent chain must be a chain. A cycle here
        # turns every tree walk into unbounded memory growth.
        seen_chain = set()
        walker = node
        while walker is not None:
            key = id(walker)
            if key in seen_chain:
                raise RuntimeError("MCTS: parent-chain cycle detected")
            seen_chain.add(key)
            walker = walker.parent
        on_path = set()
        ancestor: Optional[Node] = node.parent
        while ancestor is not None:
            if ancestor.structure_id is not None:
                on_path.add(ancestor.structure_id)
            ancestor = ancestor.parent
        for action, prior in priors.items():
            next_structure = self.env.next_structure(node.state, action)
            if next_structure.as_tuple() in on_path:
                continue
            terminal = action == DiscreteAction.TERMINATE_FIT
            child = Node(
                prior=prior, terminal=terminal, parent_action=action, parent=node
            )
            child.structure_id = next_structure.as_tuple()
            node.children[action] = child
        node.expanded = True

    def _evaluate(self, node: Node, parent: Node, root_reward: float) -> float:
        """Fit a node's state on first selection and return its value.

        ``TERMINATE_FIT`` children share their parent's state; every other
        child is optimised from the parent's warm start via the environment.
        """
        if node.terminal or node.parent_action == DiscreteAction.TERMINATE_FIT:
            node.state = parent.state
            node.evaluated = True
            return self._reward_value(node.state, root_reward)
        node.state = self.env.apply_action(parent.state, node.parent_action)
        node.evaluated = True
        # The observed structure overrides the predicted one: the optimiser
        # can drive an amplitude to exactly zero, which retires that pair
        # from the mask for real, and cycle prevention must track reality.
        node.structure_id = node.state.structure.as_tuple()
        # A refit can *collapse onto* an ancestor's canonical structure (the
        # optimiser retires a component by driving its amplitude to zero).
        # Such a node is a dead end: its value counts, but it must never be
        # expanded, or the tree would re-search a structure already on the
        # path.
        ancestor: Optional[Node] = node.parent
        while ancestor is not None:
            if ancestor.structure_id == node.structure_id:
                node.terminal = True
                node.expanded = True
                break
            ancestor = ancestor.parent
        return self._reward_value(node.state, root_reward)

    def _simulate(self, root: Node, root_reward: float) -> None:
        """One traversal: select, (expand,) evaluate, backpropagate."""
        path: List[Node] = [root]
        node = root
        while node.expanded and node.children:
            parent = node
            node = max(
                node.children.values(),
                key=lambda child: parent.puct(
                    child.parent_action, child, self.config.c_puct, parent.visit_count
                ),
            )
            path.append(node)
            if node.terminal:
                break

        if node.terminal:
            value = self._evaluate(node, path[-2], root_reward)
        elif not node.evaluated:
            value = self._evaluate(node, path[-2], root_reward)
        elif node.expanded and not node.children:
            # Every action was refused by cycle prevention: a dead end.
            value = self._reward_value(node.state, root_reward)
        else:
            # Second visit: open the node's own action set and evaluate the
            # tree's choice with the value of the best prior branch — one
            # network call, no fitting (the fitting happens next simulation).
            self._expand(node, root_reward)
            value = self._reward_value(node.state, root_reward)

        for visited in path:
            visited.visit_count += 1
            visited.value_sum += value

    def search(
        self,
        initial_state: Optional[FitState] = None,
        progress: Optional[ProgressCallback] = None,
        should_cancel: Optional[CancelCheck] = None,
    ) -> SearchResult:
        """Run the tree search and recommend a model.

        Parameters
        ----------
        initial_state : FitState, optional
            Where to start. Defaults to the environment's minimal model
            (one component, no nuisances), optimised now if the environment
            has no current state.
        progress : callable, optional
            ``progress(done, total, stage)`` after every simulation.
        should_cancel : callable, optional
            The search stops early when this returns True; the best state so
            far is returned (every state in the tree is already fully scored).

        Returns
        -------
        SearchResult
        """
        if initial_state is None:
            if self.env.state is None:
                self.env.reset()
            initial_state = self.env.state
        root_reward = float(initial_state.stats.reward)
        root = Node(prior=1.0)
        root.state = initial_state
        root.structure_id = initial_state.structure.as_tuple()
        root.evaluated = True
        root.visit_count = 1
        self.root = root
        self._expand(root, root_reward)

        total = int(self.config.n_simulations)
        evaluated = {id(root): root}
        done = 0
        cancelled = False
        while done < total:
            if should_cancel is not None and should_cancel():
                cancelled = True
                break
            self._simulate(root, root_reward)
            done += 1
            if progress is not None and (done % 5 == 0 or done == total):
                progress(done, total, "MCTS simulation")

        best = root.state
        stack = [root]
        while stack:
            node = stack.pop()
            if node.state is not None and node.state.stats.reward > best.stats.reward:
                best = node.state
            if node.expanded:
                stack.extend(node.children.values())
                self._record_training_example(node, root_reward)
            if node.evaluated and node.state is not None:
                evaluated[id(node)] = node

        path: List[DiscreteAction] = []
        node = root
        while node.expanded and node.children:
            best_child = max(node.children.values(), key=lambda c: c.visit_count)
            if best_child.terminal or best_child.visit_count == 0:
                break
            path.append(best_child.parent_action)
            if best_child.terminal:
                break
            node = best_child
            if not node.evaluated:
                break

        return SearchResult(
            root_state=initial_state,
            best_state=best,
            best_path=path,
            n_states_evaluated=sum(1 for n in evaluated.values() if n.evaluated and n.state is not None),
            n_simulations=done,
            improvement=float(best.stats.reward - root_reward),
            acceptable=bool(best.stats.chi2_acceptable),
        )

    # ------------------------------------------------------------------ #
    # Self-play bookkeeping                                              #
    # ------------------------------------------------------------------ #

    def _record_training_example(self, node: Node, root_reward: float) -> None:
        """Store (obs, structure, visits, value) for an expanded node.

        Only nodes whose children were actually visited contribute — a
        visit distribution of all zeros carries no information.
        """
        if node.state is None or not node.children:
            return
        if node.visit_count < self.config.min_visits_for_training:
            return
        visits = sum(child.visit_count for child in node.children.values())
        if visits <= 0:
            return
        target = np.zeros(N_ACTIONS, dtype=float)
        for action, child in node.children.items():
            target[int(action)] = child.visit_count / visits
        self.training_examples.append(
            TrainingExample(
                observation=self.env.observation(node.state),
                structure_features=self.env.structure_features(node.state.structure),
                policy_target=target,
                value_target=self._reward_value(node.state, root_reward),
            )
        )

    def training_examples_as_tuples(self) -> List[Tuple[np.ndarray, np.ndarray, np.ndarray, float]]:
        """Training examples in the tuple form :meth:`TCSPCNet.train` takes."""
        return [
            (ex.observation, ex.structure_features, ex.policy_target, ex.value_target)
            for ex in self.training_examples
        ]
